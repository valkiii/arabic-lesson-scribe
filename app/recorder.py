"""Record a lesson: the microphone, the computer's own sound (WASAPI loopback, Windows), or both.

Output is 16 kHz mono 16-bit WAV written incrementally to disk (a few small blocks in memory at most).
The header is corrected every couple of seconds, so a crash leaves a nearly valid file, and `repair_wav`
fixes the rest.

Microphone only (the original path, kept as it was): every block the microphone delivers is written as it
arrives, the file length is the number of samples received.

With computer sound (alone or with the microphone) the file follows the WALL CLOCK. WASAPI loopback delivers
no data at all while nothing is playing, so the length of a stream says nothing about time. `Mixer` places
every block on a common timeline using its arrival time, fills gaps with silence, tolerates small clock
drift, and mixes both sources into recording.wav. When both are on, the two sources are also kept as
system.wav and mic.wav (same length, same timeline) so nothing is lost.

Libraries: sounddevice for the microphone, PyAudioWPatch (a PyAudio fork) for loopback; both are imported
lazily and replaced in tests by fake stream factories.
"""
from __future__ import annotations

import logging
import math
import os
import queue
import shutil
import struct
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from . import power

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
HEADER = 44
TICK_S = 0.1                 # about ten events per second
HEADER_FIX_S = 2.0
DISK_CHECK_S = 2.0
HEALTH_CHECK_S = 1.0         # is each source still alive, did the default speakers change
LOW_DISK_MB = 500
STOP_DISK_MB = 100
SILENT_LEVEL = 0.002         # RMS below this counts as silence
SILENT_HINT_S = 20.0
CLIP_PEAK = 32600

# Mixer (wall-clock mode)
HOLD_S = 0.3                 # output lags the clock by this much so late blocks still fit
GAP_TOL_S = 0.25             # a gap longer than this between blocks of a source is filled with silence
MAX_BUFFER_S = 0.8           # a source running fast piles up; above this the oldest audio is dropped
GAIN_BOTH = 0.5              # two sources: each at half, the sum can never clip

PRIVACY_HINT = ("Windows may be blocking the microphone. Open Settings, Privacy and security, Microphone, "
                "and switch on 'Let desktop apps access your microphone'.")
NO_SYSTEM_SOUND_HINT = ("No computer sound detected: is the lesson playing through this computer's "
                        "default speakers or headphones?")
SYSTEM_ONLY_HINT = "Switch off 'My microphone' to record only the computer's sound."


class RecorderError(RuntimeError):
    """message starts with a code: NO_MIC, MIC_DENIED, MIC_ERROR, NO_OUTPUT, LOOPBACK_DENIED, LOOPBACK_ERROR,
    LOOPBACK_UNAVAILABLE, NO_SOURCE, DISK_FULL, BUSY."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.text = code, message


# ---- WAV helpers ------------------------------------------------------------
def _header(data_bytes: int, rate: int = SAMPLE_RATE) -> bytes:
    return (b"RIFF" + struct.pack("<I", 36 + data_bytes) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", data_bytes))


def repair_wav(path: str | Path) -> float:
    """Make a WAV written by this module valid again after a crash (header sizes fixed, a torn last sample
    dropped). Returns the duration in seconds. Raises ValueError if the file is not one of ours."""
    p = Path(path)
    size = p.stat().st_size
    with open(p, "r+b") as f:
        head = f.read(HEADER)
        if len(head) < HEADER or head[:4] != b"RIFF" or head[8:16] != b"WAVEfmt " or head[36:40] != b"data":
            raise ValueError("not a recording made by this app")
        rate = struct.unpack("<I", head[24:28])[0] or SAMPLE_RATE
        n = max(0, size - HEADER) // 2 * 2
        if size != HEADER + n:
            f.truncate(HEADER + n)
        f.seek(0)
        f.write(_header(n, rate))
    return n / 2 / rate


def repair_tracks(folder: str | Path) -> list[str]:
    """Repair the separate tracks (system.wav, mic.wav) of an unfinished recording; returns those repaired."""
    done = []
    for name in ("system.wav", "mic.wav"):
        p = Path(folder) / name
        if p.is_file():
            try:
                repair_wav(p)
                done.append(name)
            except (OSError, ValueError):
                pass
    return done


def wav_duration(path: str | Path) -> float:
    with open(path, "rb") as f:
        head = f.read(HEADER)
    if len(head) < HEADER:
        return 0.0
    rate = struct.unpack("<I", head[24:28])[0] or SAMPLE_RATE
    return max(0, Path(path).stat().st_size - HEADER) // 2 / rate


class _WavOut:
    """A WAV file written incrementally, header kept nearly valid."""

    def __init__(self, path: Path):
        self.path = path
        self.f = open(path, "wb")
        self.n = 0
        self.f.write(_header(0))
        self.f.flush()

    def write(self, x: np.ndarray) -> None:
        """x: float or int array on the int16 scale."""
        if x.dtype != np.int16:
            x = np.clip(np.rint(x), -32768, 32767).astype(np.int16)
        self.f.write(x.astype("<i2").tobytes())
        self.n += len(x)

    def fix_header(self) -> None:
        try:
            self.f.flush()
            end = self.f.tell()
            self.f.seek(0)
            self.f.write(_header(self.n * 2))
            self.f.seek(end)
            self.f.flush()
            os.fsync(self.f.fileno())
        except (OSError, ValueError):
            pass

    def close(self) -> None:
        self.fix_header()
        try:
            self.f.close()
        except OSError:
            pass

    def discard(self) -> None:
        try:
            self.f.close()
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


# ---- resampling -------------------------------------------------------------
class PolyResampler:
    """Streaming polyphase windowed-sinc resampler (numpy only) from rate_in to 16 kHz, zero delay.

    Block sizes do not matter: the output is the same however the input is cut. Cutoff is 0.45 of the lower
    of the two rates, Kaiser window (beta 8.6, about 80 dB stop band), 12 zero crossings each side."""

    def __init__(self, rate_in: int, rate_out: int = SAMPLE_RATE):
        g = math.gcd(int(rate_in), int(rate_out))
        self.L, self.M = int(rate_out) // g, int(rate_in) // g
        self.identity = self.L == self.M
        if self.identity:
            return
        f = 0.45 * min(rate_in, rate_out) / (rate_in * self.L)       # cutoff, cycles per upsampled sample
        self.half = int(math.ceil(12 / (2 * f)))
        n = np.arange(-self.half, self.half + 1, dtype=np.float64)
        h = 2 * f * np.sinc(2 * f * n) * np.kaiser(2 * self.half + 1, 8.6) * self.L
        self.h = h
        self.taps = (2 * self.half) // self.L + 2
        self.hist = np.zeros(0, dtype=np.float64)    # input samples from index self.base on
        self.base = 0
        self.total = 0                               # input samples received
        self.n_out = 0                               # next output index

    def __call__(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32).reshape(-1)
        if self.identity:
            return x
        self.hist = np.concatenate([self.hist, x.astype(np.float64)])
        self.total += len(x)
        end = (self.total * self.L - self.half - 1) // self.M + 1       # outputs whose inputs are all here
        if end <= self.n_out:
            return np.zeros(0, dtype=np.float32)
        n = np.arange(self.n_out, end, dtype=np.int64)
        u = n * self.M
        j = (u + self.half) // self.L
        jj = j[:, None] - np.arange(self.taps, dtype=np.int64)[None, :]       # input indices
        hi = self.half + u[:, None] - jj * self.L                             # filter indices
        ok = (hi >= 0) & (hi <= 2 * self.half) & (jj >= 0)
        xv = self.hist[np.clip(jj - self.base, 0, max(0, len(self.hist) - 1))]
        out = np.sum(np.where(ok, xv * self.h[np.clip(hi, 0, 2 * self.half)], 0.0), axis=1)
        self.n_out = end
        keep_from = max(0, -(-(end * self.M - self.half) // self.L) - 1)      # first input still needed
        if keep_from > self.base:
            self.hist = self.hist[keep_from - self.base:]
            self.base = keep_from
        return out.astype(np.float32)


def to_mono(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x)
    if x.ndim > 1:
        x = x.astype(np.float32).mean(axis=1) if x.shape[1] > 1 else x.reshape(-1)
    return x.astype(np.float32, copy=False)


# ---- the timeline mixer (wall-clock mode) -------------------------------------
class Mixer:
    """Places blocks of several sources on one timeline measured in 16 kHz samples.

    push(name, t_end, x): x is a block of 16 kHz mono (int16 scale) whose last sample arrived at t_end seconds.
    pull(now): returns (mix, {name: track}) for everything due up to `now` minus HOLD_S (or all of it with
    flush=True). Short sources are padded with silence, so every track is exactly as long as the wall clock."""

    def __init__(self, names, hold_s: float = HOLD_S, gap_tol_s: float = GAP_TOL_S, max_buffer_s: float = MAX_BUFFER_S):
        self.names = list(names)
        self.hold = int(hold_s * SAMPLE_RATE)
        self.gap_tol = int(gap_tol_s * SAMPLE_RATE)
        self.max_buf = int(max_buffer_s * SAMPLE_RATE)
        self.out_pos = 0
        self.buf = {n: np.zeros(0, dtype=np.float32) for n in self.names}
        self.stall_fills = 0       # how many gaps were filled with silence (diagnostics)
        self.drift_drops = 0       # how many times a fast source had audio dropped

    def reset_sources(self) -> None:
        for n in self.names:
            self.buf[n] = np.zeros(0, dtype=np.float32)

    def push(self, name: str, t_end: float, x: np.ndarray) -> None:
        if name not in self.buf or len(x) == 0:
            return
        b = self.buf[name]
        start = int(round(t_end * SAMPLE_RATE)) - len(x)
        gap = start - (self.out_pos + len(b))
        if gap > self.gap_tol:                        # the source was silent/stalled: keep time honest
            b = np.concatenate([b, np.zeros(gap, dtype=np.float32)])
            self.stall_fills += 1
        self.buf[name] = np.concatenate([b, x.astype(np.float32, copy=False)])

    def pull(self, now: float, flush: bool = False) -> tuple[np.ndarray, dict]:
        target = int(round(now * SAMPLE_RATE)) - (0 if flush else self.hold)
        n = target - self.out_pos
        if n <= 0:
            return np.zeros(0, dtype=np.int16), {k: np.zeros(0, dtype=np.int16) for k in self.names}
        tracks = {}
        for k in self.names:
            b = self.buf[k]
            if len(b) >= n:
                seg, rest = b[:n], b[n:]
            else:
                seg, rest = np.concatenate([b, np.zeros(n - len(b), dtype=np.float32)]), b[:0]
            if len(rest) > self.max_buf:              # clock drift: this source runs faster than the wall clock
                rest = rest[len(rest) - self.hold:]
                self.drift_drops += 1
            self.buf[k] = rest
            tracks[k] = seg
        self.out_pos += n
        gain = GAIN_BOTH if len(self.names) > 1 else 1.0
        mix = sum(tracks.values()) * gain
        to16 = lambda a: np.clip(np.rint(a), -32768, 32767).astype(np.int16)  # noqa: E731
        return to16(mix), {k: to16(v) for k, v in tracks.items()}


# ---- audio libraries --------------------------------------------------------
def _sd():
    try:
        import sounddevice as sd
        return sd
    except Exception as e:  # noqa: BLE001  (ImportError, or OSError when PortAudio is missing)
        raise RecorderError("MIC_ERROR", f"The audio library could not be loaded ({e}).") from e


def _load_pyaudio():
    """PyAudioWPatch (module name pyaudiowpatch). Only useful on Windows; tests replace this function."""
    import pyaudiowpatch as pyaudio
    return pyaudio


def list_input_devices(sd=None) -> list[dict]:
    """[{id, name, default}] of the microphones. On Windows the same device appears once per audio system
    (MME, DirectSound, WASAPI...): only the default audio system's list is returned."""
    sd = sd or _sd()
    try:
        devs = sd.query_devices()
        default_in = sd.default.device[0] if hasattr(sd.default.device, "__getitem__") else sd.default.device
        host = sd.default.hostapi
    except Exception as e:  # noqa: BLE001
        raise RecorderError("MIC_ERROR", f"The microphones could not be listed ({e}).") from e
    out = []
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0 and (host is None or d.get("hostapi") in (host, None)):
            out.append({"id": i, "name": str(d["name"]), "default": i == default_in})
    return out


def loopback_available() -> bool:
    """True when this machine can record the computer's own sound: Windows with PyAudioWPatch importable."""
    if sys.platform != "win32":
        return False
    try:
        _load_pyaudio()
        return True
    except Exception:  # noqa: BLE001
        return False


def _clean_name(name: str) -> str:
    return name.replace(" [Loopback]", "").strip()


def _loopback_info(pa) -> tuple[list[dict], int | None]:
    """(loopback device dicts, index of the one for the default speakers or None)."""
    devs = list(pa.get_loopback_device_info_generator())
    default = None
    try:
        default = pa.get_default_wasapi_loopback()["index"]
    except Exception:  # noqa: BLE001  (no default output device)
        pass
    return devs, default


def list_outputs(pyaudio=None) -> list[dict]:
    """[{id, name, default}] of the speakers/headphones whose sound can be recorded. [] when there is none."""
    mod = pyaudio or _load_pyaudio()
    pa = mod.PyAudio()
    try:
        devs, default = _loopback_info(pa)
        return [{"id": d["index"], "name": _clean_name(str(d["name"])), "default": d["index"] == default} for d in devs]
    finally:
        pa.terminate()


def list_audio_sources(sd=None, pyaudio=None) -> dict:
    """{microphones:[{id,name,default}], loopback_available, outputs:[{id,name,default}]}; never raises."""
    try:
        mics = list_input_devices(sd)
    except Exception:  # noqa: BLE001
        mics = []
    avail, outs = False, []
    try:
        if pyaudio is not None or loopback_available():
            avail = True
            outs = list_outputs(pyaudio)
    except Exception as e:  # noqa: BLE001
        log.warning("listing outputs failed: %s", e)
    return {"microphones": mics, "loopback_available": avail, "outputs": outs}


def explain_open_error(e: Exception) -> RecorderError:
    msg = str(e)
    low = msg.lower()
    if any(k in low for k in ("access", "denied", "permission", "-9999", "host error", "mme error 5")):
        return RecorderError("MIC_DENIED", PRIVACY_HINT)
    return RecorderError("MIC_ERROR", f"The microphone could not be opened ({msg}). {PRIVACY_HINT}")


def explain_loopback_error(e: Exception) -> RecorderError:
    msg = str(e)
    low = msg.lower()
    if "no default" in low or "no output" in low or "default output" in low or "default wasapi" in low:
        return RecorderError("NO_OUTPUT", "No speakers or headphones were found, so the computer's sound cannot be "
                                          "recorded. Plug in or switch on an output device, or record with the microphone only.")
    if any(k in low for k in ("access", "denied", "permission", "exclusive", "in use", "-9985", "device unavailable")):
        return RecorderError("LOOPBACK_DENIED", "Windows did not allow the computer's sound to be recorded. Another app "
                                                "may have taken exclusive control of the speakers: close it, or switch off "
                                                "its exclusive mode in the Windows sound settings, then try again.")
    return RecorderError("LOOPBACK_ERROR", f"The computer's sound could not be recorded ({msg}). "
                                           "You can still record with your microphone only.")


class LoopbackStream:
    """The computer's sound through PyAudioWPatch (WASAPI loopback). Callback gets (indata int16 frames x channels,
    frames, None, None) like sounddevice. Delivers NOTHING while no sound plays: the Recorder fills the gaps."""

    def __init__(self, device: int | None, callback, pyaudio=None):
        self._mod = pyaudio or _load_pyaudio()
        self._cb = callback
        self._pa = self._mod.PyAudio()
        self.stream = None
        try:
            devs, default = _loopback_info(self._pa)
            if device is None:
                if default is None:
                    raise OSError("No default output device")
                device = default
            info = next((d for d in devs if d["index"] == device), None)
            if info is None:
                raise OSError("The chosen output device is not available")
            self.device, self.name = device, _clean_name(str(info["name"]))
            self.default_at_open = default
            self.channels = max(1, int(info["maxInputChannels"]))
            self.samplerate = int(info["defaultSampleRate"])
            self.stream = self._pa.open(format=self._mod.paInt16, channels=self.channels, rate=self.samplerate,
                                        frames_per_buffer=int(self.samplerate * TICK_S), input=True,
                                        input_device_index=device, stream_callback=self._raw)
            self.stream.stop_stream()           # opened stopped; start() starts it
        except Exception:
            self.close()
            raise

    def _raw(self, data, frames, time_info, status):
        try:
            self._cb(np.frombuffer(data, dtype=np.int16).reshape(-1, self.channels), frames, None, None)
        except Exception:  # noqa: BLE001
            pass
        return (None, self._mod.paContinue)

    @property
    def active(self) -> bool:
        try:
            return bool(self.stream is not None and self.stream.is_active())
        except Exception:  # noqa: BLE001
            return False

    def default_changed(self) -> bool:
        """The default speakers are no longer the ones this stream was opened on."""
        try:
            return _loopback_info(self._pa)[1] != self.default_at_open
        except Exception:  # noqa: BLE001
            return False

    def start(self) -> None:
        self.stream.start_stream()

    def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop_stream()

    def close(self) -> None:
        s, self.stream = self.stream, None
        try:
            if s is not None:
                s.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._pa.terminate()
        except Exception:  # noqa: BLE001
            pass


class _Src:
    """One live source (microphone or computer sound) of a recording."""

    def __init__(self, name: str):
        self.name = name
        self.stream = None
        self.rate = SAMPLE_RATE
        self.resampler: PolyResampler | None = None
        self.alive = True
        self.sq, self.n, self.peak = 0.0, 0, 0       # level window, reset every tick
        self.last_sound = 0.0
        self.level = 0.0


# ---- the recorder -----------------------------------------------------------
class Recorder:
    def __init__(self, path: str | Path, device: int | None = None,
                 on_event: Callable[[dict], None] | None = None,
                 on_finish: Callable[[dict], None] | None = None,
                 stream_factory=None, disk_usage=None,
                 sources: dict | None = None, system_device: int | None = None,
                 system_factory=None, clock=None):
        self.path = Path(path)
        self.device = device
        self.system_device = system_device
        src = sources or {"system": False, "mic": True}
        self.want_system, self.want_mic = bool(src.get("system")), bool(src.get("mic", False))
        if not (self.want_system or self.want_mic):
            raise RecorderError("NO_SOURCE", "Switch on at least one source: the computer's sound or your microphone.")
        self.on_event = on_event
        self.on_finish = on_finish
        self._factory = stream_factory
        self._sys_factory = system_factory
        self._disk = disk_usage or shutil.disk_usage
        self._clock = clock or time.monotonic
        self._q: queue.Queue = queue.Queue(maxsize=1200)   # about 2 minutes of 0.1 s blocks, a few MB
        self._srcs: dict[str, _Src] = {}
        self._state = "idle"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._cancel = False
        self._thread: threading.Thread | None = None
        self._samples = 0
        self._result: dict | None = None
        self._finished = threading.Event()
        self.dropped_blocks = 0
        self._wall = self.want_system            # wall-clock mode (computer sound involved)
        self._mixer: Mixer | None = None
        self._outs: dict[str, _WavOut] = {}
        self._t0 = 0.0
        self._paused_total = 0.0
        self._pause_start: float | None = None
        self._flush_at: float | None = None
        self._notice: tuple[str, str] | None = None   # (key for the UI, English text)
        self.mixer_stats: dict = {}

    # public -------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def elapsed_s(self) -> float:
        return self._samples / SAMPLE_RATE

    @property
    def separate_tracks(self) -> bool:
        return self.want_system and self.want_mic

    def start(self) -> None:
        if self._state != "idle":
            raise RecorderError("BUSY", "A recording is already running.")
        free = self._free_mb()
        if free is not None and free < STOP_DISK_MB:
            raise RecorderError("DISK_FULL", f"Only {free:.0f} MB of disk space is free. Free some space and try again.")
        try:
            if self.want_system:
                self._open_system()
            if self.want_mic:
                self._open_mic()
        except RecorderError as e:
            self._close_streams()
            if self.want_system and e.code in ("NO_MIC", "MIC_DENIED", "MIC_ERROR"):
                e = RecorderError(e.code, f"{e.text} {SYSTEM_ONLY_HINT}")
            raise e
        names = [n for n in ("system", "mic") if n in self._srcs]
        self._outs["mix"] = _WavOut(self.path)
        if self.separate_tracks:
            self._outs["system"] = _WavOut(self.path.with_name("system.wav"))
            self._outs["mic"] = _WavOut(self.path.with_name("mic.wav"))
        self._mixer = Mixer(names) if self._wall else None
        self._state = "recording"
        self._t0 = self._clock()
        try:
            for s in self._srcs.values():
                s.last_sound = self._t0
                s.stream.start()
        except Exception as e:  # noqa: BLE001
            self._abort_start()
            raise (explain_loopback_error(e) if "system" in self._srcs and not self.want_mic else explain_open_error(e)) from e
        self._thread = threading.Thread(target=self._run, name="recorder", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            if self._state == "recording":
                self._state = "paused"
                self._pause_start = self._clock()
                self._flush_at = self._pause_start - self._t0 - self._paused_total

    def resume(self) -> None:
        with self._lock:
            if self._state == "paused":
                if self._pause_start is not None:
                    self._paused_total += self._clock() - self._pause_start
                self._pause_start = None
                if self._mixer:
                    self._mixer.reset_sources()
                self._state = "recording"

    def stop(self, reason: str = "stopped") -> dict:
        """Finish the file and return {path, duration_s, reason}. Safe to call twice."""
        if self._thread is None:
            return self._result or {"path": str(self.path), "duration_s": 0.0, "reason": reason}
        self._stop_reason = getattr(self, "_stop_reason", None) or reason
        self._stop.set()
        if threading.current_thread() is not self._thread:
            self._finished.wait(15)
        return self._result or {"path": str(self.path), "duration_s": self.elapsed_s, "reason": reason}

    def cancel(self) -> None:
        """Stop and delete the files."""
        self._cancel = True
        self.stop("cancelled")
        for p in (self.path, self.path.with_name("system.wav"), self.path.with_name("mic.wav")):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    # internals ----------------------------------------------------------
    def _free_mb(self) -> float | None:
        try:
            return self._disk(str(self.path.parent)).free / 1e6
        except OSError:
            return None

    def _open_system(self) -> None:
        s = _Src("system")
        factory = self._sys_factory
        if factory is None:
            if not loopback_available():
                raise RecorderError("LOOPBACK_UNAVAILABLE", "Recording the computer's sound is not available on this "
                                                            "computer. Record with the microphone only.")
            factory = lambda dev, cb: LoopbackStream(dev, cb)  # noqa: E731
        try:
            s.stream = factory(self.system_device, self._sys_callback)
        except RecorderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise explain_loopback_error(e) from e
        self._set_rate(s)
        self._srcs["system"] = s

    def _set_rate(self, s: _Src) -> None:
        s.rate = int(getattr(s.stream, "samplerate", SAMPLE_RATE) or SAMPLE_RATE)
        s.resampler = PolyResampler(s.rate) if s.rate != SAMPLE_RATE else None

    def _open_mic(self) -> None:
        s = _Src("mic")
        factory = self._factory
        if factory is None:
            sd = _sd()
            if not list_input_devices(sd):
                raise RecorderError("NO_MIC", "No microphone was found. Plug one in (or switch it on) and try again.")
            factory = sd.InputStream
        kw = dict(samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=self.device,
                  blocksize=int(SAMPLE_RATE * TICK_S), callback=self._callback)
        try:
            s.stream = factory(**kw)
        except Exception as e:  # noqa: BLE001
            low = str(e).lower()
            if "sample rate" in low and self._factory is None:   # the device will not do 16 kHz: take its own rate
                s.stream = self._open_native(factory, kw, s)
            else:
                raise explain_open_error(e) from e
        else:
            self._set_rate(s)
        self._srcs["mic"] = s

    def _open_native(self, factory, kw, s: _Src):
        sd = _sd()
        try:
            info = sd.query_devices(self.device, "input")
            rate = int(info["default_samplerate"])
            ch = max(1, min(2, int(info["max_input_channels"])))
            stream = factory(**dict(kw, samplerate=rate, channels=ch, blocksize=int(rate * TICK_S)))
            s.rate, s.resampler = rate, PolyResampler(rate)
            return stream
        except Exception as e:  # noqa: BLE001
            raise explain_open_error(e) from e

    def _callback(self, indata, frames, time_info, status) -> None:
        self._enqueue("mic", indata)

    def _sys_callback(self, indata, frames, time_info, status) -> None:
        self._enqueue("system", indata)

    def _enqueue(self, name: str, indata) -> None:
        try:
            self._q.put_nowait((name, self._clock(), np.array(indata, copy=True)))
        except queue.Full:
            self.dropped_blocks += 1

    def _abort_start(self) -> None:
        self._close_streams()
        for o in self._outs.values():
            o.discard()
        self._outs.clear()
        self._state = "idle"

    def _prep(self, s: _Src, arr: np.ndarray) -> np.ndarray:
        """One block from the library -> mono 16 kHz float32 on the int16 scale."""
        x = to_mono(arr)
        return s.resampler(x) if s.resampler is not None else x

    def _close_streams(self) -> None:
        for s in self._srcs.values():
            self._close_stream(s)

    @staticmethod
    def _close_stream(s: _Src) -> None:
        st, s.stream = s.stream, None
        if st is not None:
            for fn in ("stop", "close"):
                try:
                    getattr(st, fn)()
                except Exception:  # noqa: BLE001
                    pass

    def _emit(self, **kw) -> None:
        if self.on_event:
            try:
                self.on_event({"state": self._state, "elapsed_s": round(self.elapsed_s, 1), **kw})
            except Exception:  # noqa: BLE001
                log.exception("record event failed")

    def _active_now(self, now: float) -> float:
        return now - self._t0 - self._paused_total

    def _run(self) -> None:
        with power.keep_awake():       # keeps Windows awake for as long as this thread records
            self._loop()

    def _write_due(self, active_s: float, flush: bool = False) -> None:
        with self._lock:
            mix, tracks = self._mixer.pull(active_s, flush)
        if len(mix) == 0:
            return
        self._outs["mix"].write(mix)
        if self.separate_tracks:
            for k in ("system", "mic"):
                self._outs[k].write(tracks[k])
        self._samples = self._outs["mix"].n

    def _handle(self, item) -> None:
        name, t, arr = item
        s = self._srcs.get(name)
        if s is None:
            return
        x = self._prep(s, arr)
        if not len(x):
            return
        s.sq += float(np.sum(x.astype(np.float64) ** 2))
        s.n += len(x)
        s.peak = max(s.peak, int(np.max(np.abs(x))))
        if self._state != "recording":
            return
        if self._wall:
            with self._lock:
                self._mixer.push(name, self._active_now(t), x)
        else:
            self._outs["mix"].write(x)
            self._samples = self._outs["mix"].n

    def _source_lost(self, s: _Src, text: str) -> str | None:
        """A source stopped. Returns a final message when nothing is left, else sets a notice."""
        s.alive = False
        self._close_stream(s)
        if any(o.alive for o in self._srcs.values()):
            self._notice = (f"{s.name}_stopped", text)
            return None
        return text

    def _try_reattach_system(self, s: _Src) -> bool:
        """The default speakers changed or the stream died: open the loopback of the new default device."""
        old = s.stream
        self._close_stream(s)
        try:
            factory = self._sys_factory or (lambda dev, cb: LoopbackStream(dev, cb))
            s.stream = factory(self.system_device, self._sys_callback)
            self._set_rate(s)
            s.stream.start()
        except Exception as e:  # noqa: BLE001
            log.warning("re-attaching the computer sound failed: %s", e)
            self._close_stream(s)
            s.stream = None
            return False
        name = getattr(s.stream, "name", None)
        self._notice = ("output_changed", "The speakers or headphones changed" + (f" (now: {name})" if name else "")
                        + ". The recording continues with the new device.")
        log.info("loopback re-attached (old stream %r)", old)
        return True

    def _health(self) -> str | None:
        """Check sources; return a final message when nothing can be recorded any more."""
        final = None
        for s in list(self._srcs.values()):
            if not s.alive or s.stream is None or self._stop.is_set():
                continue
            if s.name == "system":
                changed = getattr(s.stream, "default_changed", None)
                moved = self.system_device is None and callable(changed) and changed()
                if moved or not getattr(s.stream, "active", True):
                    if self._try_reattach_system(s):
                        continue
                    msg = ("The speakers or headphones changed and the computer's sound could not be recorded any more"
                           if moved else "The computer's sound stopped (speakers unplugged or switched off?)")
                    final = self._source_lost(s, msg + ". Everything recorded so far is saved.") or final
            elif not getattr(s.stream, "active", True):
                final = self._source_lost(s, "The microphone stopped (unplugged or switched off?). "
                                             "Everything recorded so far is saved.") or final
        return final

    def _loop(self) -> None:
        clock = self._clock
        t_tick = t_fix = t_disk = t_health = clock()
        peak_win = 0
        clip_until = 0.0
        free = self._free_mb()
        low = False
        reason, message = None, None
        enabled = {n: True for n in self._srcs}
        while True:
            now = clock()
            try:
                self._handle(self._q.get(timeout=TICK_S / 2))
            except queue.Empty:
                pass
            if self._wall and self._state == "recording":
                if now - t_tick >= TICK_S:
                    self._write_due(self._active_now(now))
            elif self._wall and self._flush_at is not None:        # just paused: write everything up to that moment
                at, self._flush_at = self._flush_at, None
                self._write_due(at, flush=True)
            if now - t_disk >= DISK_CHECK_S:
                t_disk = now
                free = self._free_mb()
                if free is not None:
                    low = free < LOW_DISK_MB
                    if free < STOP_DISK_MB:
                        reason, message = "disk_full", "The disk is almost full, so the recording was stopped safely. Everything recorded so far is saved."
            if now - t_fix >= HEADER_FIX_S:
                t_fix = now
                for o in self._outs.values():
                    o.fix_header()
            if reason is None and not self._stop.is_set() and now - t_health >= (HEALTH_CHECK_S if self._wall else 0):
                t_health = now
                final = self._health()
                if final:
                    reason, message = "device_lost", final
            if now - t_tick >= TICK_S:
                t_tick = now
                ev = self._tick_event(now, low, free, clip_until)
                clip_until = ev.pop("_clip_until")
                self._emit(**ev)
            if reason or (self._stop.is_set() and self._q.empty()):
                break
        reason = reason or getattr(self, "_stop_reason", None) or "stopped"
        self._close_streams()
        while True:                      # whatever the library delivered before it stopped
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if self._state == "recording":
                self._handle(item)
        if self._wall and self._state == "recording" and not self._cancel:
            self._write_due(self._active_now(clock()), flush=True)
        if self._mixer:
            self.mixer_stats = {"stall_fills": self._mixer.stall_fills, "drift_drops": self._mixer.drift_drops}
        for o in self._outs.values():
            o.close()
        self._state = "stopped"
        self._result = {"path": str(self.path), "duration_s": round(self.elapsed_s, 1), "reason": reason}
        if self.separate_tracks:
            self._result["tracks"] = {"system": str(self.path.with_name("system.wav")),
                                      "mic": str(self.path.with_name("mic.wav"))}
        if message:
            self._result["message"] = message
        self._emit(**self._idle_levels(), peak_clipping=False, silent=False, low_disk=low,
                   free_disk_mb=None if free is None else int(free), reason=reason,
                   **({"message": message} if message else {}))
        self._finished.set()
        if reason in ("disk_full", "device_lost") and self.on_finish and not self._cancel:
            try:
                self.on_finish(dict(self._result))
            except Exception:  # noqa: BLE001
                log.exception("on_finish failed")

    def _idle_levels(self) -> dict:
        return {"level": 0.0, "level_system": 0.0 if self.want_system else None,
                "level_mic": 0.0 if self.want_mic else None}

    def _tick_event(self, now: float, low: bool, free, clip_until: float) -> dict:
        peak = 0
        silent_of = {}
        for n, s in self._srcs.items():
            s.level = (s.sq / s.n) ** 0.5 / 32768 if s.n else 0.0
            peak = max(peak, s.peak)
            if s.level >= SILENT_LEVEL or self._state != "recording":
                s.last_sound = now                    # no "silent" hint while paused
            silent_of[n] = self._state == "recording" and now - s.last_sound >= SILENT_HINT_S
            s.sq, s.n, s.peak = 0.0, 0, 0
        if peak >= CLIP_PEAK:
            clip_until = now + 1.0
        live = [n for n, s in self._srcs.items() if s.alive]
        silent = bool(live) and all(silent_of[n] for n in live)
        ev = {"level": round(min(1.0, max((self._srcs[n].level for n in self._srcs), default=0.0)), 4),
              "level_system": round(min(1.0, self._srcs["system"].level), 4) if self.want_system else None,
              "level_mic": round(min(1.0, self._srcs["mic"].level), 4) if self.want_mic else None,
              "peak_clipping": now < clip_until, "silent": silent, "low_disk": low,
              "free_disk_mb": None if free is None else int(free), "_clip_until": clip_until}
        if self.want_system and self.want_mic and silent_of.get("system") and not silent_of.get("mic", True):
            ev["hint"] = "no_system_audio"
            ev["hint_text"] = NO_SYSTEM_SOUND_HINT
        if self._notice:
            (ev["notice_key"], ev["notice"]), self._notice = self._notice, None
        return ev
