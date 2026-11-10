"""Record a lesson from the microphone: 16 kHz mono 16-bit WAV written incrementally to disk.

Nothing but a few small blocks is ever held in memory. The WAV header is corrected every couple of seconds,
so a crash leaves a file that is nearly valid, and `repair_wav` fixes the rest. The audio library
(sounddevice, PortAudio inside its Windows wheel) is imported lazily and can be replaced in tests by a fake
stream factory.
"""
from __future__ import annotations

import logging
import os
import queue
import shutil
import struct
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
LOW_DISK_MB = 500
STOP_DISK_MB = 100
SILENT_LEVEL = 0.002         # RMS below this counts as silence
SILENT_HINT_S = 20.0
CLIP_PEAK = 32600

PRIVACY_HINT = ("Windows may be blocking the microphone. Open Settings, Privacy and security, Microphone, "
                "and switch on 'Let desktop apps access your microphone'.")


class RecorderError(RuntimeError):
    """message starts with a code: NO_MIC, MIC_DENIED, MIC_ERROR, DISK_FULL, BUSY."""

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


def wav_duration(path: str | Path) -> float:
    with open(path, "rb") as f:
        head = f.read(HEADER)
    if len(head) < HEADER:
        return 0.0
    rate = struct.unpack("<I", head[24:28])[0] or SAMPLE_RATE
    return max(0, Path(path).stat().st_size - HEADER) // 2 / rate


# ---- audio library ----------------------------------------------------------
def _sd():
    try:
        import sounddevice as sd
        return sd
    except Exception as e:  # noqa: BLE001  (ImportError, or OSError when PortAudio is missing)
        raise RecorderError("MIC_ERROR", f"The audio library could not be loaded ({e}).") from e


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


def explain_open_error(e: Exception) -> RecorderError:
    msg = str(e)
    low = msg.lower()
    if any(k in low for k in ("access", "denied", "permission", "-9999", "host error", "mme error 5")):
        return RecorderError("MIC_DENIED", PRIVACY_HINT)
    return RecorderError("MIC_ERROR", f"The microphone could not be opened ({msg}). {PRIVACY_HINT}")


class _Resampler:
    """Only used when a microphone refuses 16 kHz: linear interpolation to 16 kHz, mono."""

    def __init__(self, rate_in: int):
        self.step = rate_in / SAMPLE_RATE
        self.pos = 0.0
        self.tail = np.zeros(1, dtype=np.float32)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        x = np.concatenate([self.tail, x.astype(np.float32)])
        n = int(np.floor((len(x) - 1 - self.pos) / self.step)) + 1
        if n <= 0:
            self.tail = x
            return np.zeros(0, dtype=np.int16)
        idx = self.pos + np.arange(n) * self.step
        out = np.interp(idx, np.arange(len(x)), x)
        nxt = self.pos + n * self.step
        keep = int(nxt)
        self.tail, self.pos = x[keep:], nxt - keep
        return np.clip(out, -32768, 32767).astype(np.int16)


# ---- the recorder -----------------------------------------------------------
class Recorder:
    def __init__(self, path: str | Path, device: int | None = None,
                 on_event: Callable[[dict], None] | None = None,
                 on_finish: Callable[[dict], None] | None = None,
                 stream_factory=None, disk_usage=None):
        self.path = Path(path)
        self.device = device
        self.on_event = on_event
        self.on_finish = on_finish
        self._factory = stream_factory
        self._disk = disk_usage or shutil.disk_usage
        self._q: queue.Queue = queue.Queue(maxsize=1200)   # about 2 minutes of 0.1 s blocks, a few MB
        self._stream = None
        self._state = "idle"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._cancel = False
        self._thread: threading.Thread | None = None
        self._samples = 0
        self._resample: _Resampler | None = None
        self._result: dict | None = None
        self._finished = threading.Event()
        self.dropped_blocks = 0

    # public -------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def elapsed_s(self) -> float:
        return self._samples / SAMPLE_RATE

    def start(self) -> None:
        if self._state != "idle":
            raise RecorderError("BUSY", "A recording is already running.")
        free = self._free_mb()
        if free is not None and free < STOP_DISK_MB:
            raise RecorderError("DISK_FULL", f"Only {free:.0f} MB of disk space is free. Free some space and try again.")
        self._open_stream()
        self._f = open(self.path, "wb")
        self._f.write(_header(0))
        self._f.flush()
        self._state = "recording"
        try:
            self._stream.start()
        except Exception as e:  # noqa: BLE001
            self._abort_start()
            raise explain_open_error(e) from e
        self._thread = threading.Thread(target=self._run, name="recorder", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            if self._state == "recording":
                self._state = "paused"

    def resume(self) -> None:
        with self._lock:
            if self._state == "paused":
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
        """Stop and delete the file."""
        self._cancel = True
        self.stop("cancelled")
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    # internals ----------------------------------------------------------
    def _free_mb(self) -> float | None:
        try:
            return self._disk(str(self.path.parent)).free / 1e6
        except OSError:
            return None

    def _open_stream(self) -> None:
        factory = self._factory
        if factory is None:
            sd = _sd()
            if not list_input_devices(sd):
                raise RecorderError("NO_MIC", "No microphone was found. Plug one in (or switch it on) and try again.")
            factory = sd.InputStream
        kw = dict(samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=self.device,
                  blocksize=int(SAMPLE_RATE * TICK_S), callback=self._callback)
        try:
            self._stream = factory(**kw)
        except Exception as e:  # noqa: BLE001
            low = str(e).lower()
            if "sample rate" in low and self._factory is None:   # the device will not do 16 kHz: take its own rate
                self._stream = self._open_native(factory, kw)
            else:
                raise explain_open_error(e) from e

    def _open_native(self, factory, kw):
        sd = _sd()
        try:
            info = sd.query_devices(self.device, "input")
            rate = int(info["default_samplerate"])
            ch = max(1, min(2, int(info["max_input_channels"])))
            self._resample = _Resampler(rate)
            kw2 = dict(kw, samplerate=rate, channels=ch, blocksize=int(rate * TICK_S))
            self._native_channels = ch
            return factory(**kw2)
        except Exception as e:  # noqa: BLE001
            raise explain_open_error(e) from e

    def _callback(self, indata, frames, time_info, status) -> None:
        try:
            self._q.put_nowait(np.array(indata, copy=True))
        except queue.Full:
            self.dropped_blocks += 1

    def _abort_start(self) -> None:
        self._close_stream()
        try:
            self._f.close()
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
        self._state = "idle"

    def _flat(self, x: np.ndarray) -> np.ndarray:
        """One block from the library -> mono 16 kHz int16."""
        if self._resample is not None:
            return self._resample(x.astype(np.float32).mean(axis=1) if x.ndim > 1 and x.shape[1] > 1 else x.reshape(-1))
        return x.reshape(-1)

    def _close_stream(self) -> None:
        s, self._stream = self._stream, None
        if s is not None:
            for fn in ("stop", "close"):
                try:
                    getattr(s, fn)()
                except Exception:  # noqa: BLE001
                    pass

    def _emit(self, **kw) -> None:
        if self.on_event:
            try:
                self.on_event({"state": self._state, "elapsed_s": round(self.elapsed_s, 1), **kw})
            except Exception:  # noqa: BLE001
                log.exception("record event failed")

    def _run(self) -> None:
        with power.keep_awake():       # keeps Windows awake for as long as this thread records
            self._loop()

    def _loop(self) -> None:
        f = self._f
        t_tick = t_fix = t_disk = time.monotonic()
        win_sq, win_n, win_peak = 0.0, 0, 0
        clip_until = 0.0
        last_sound = time.monotonic()
        free = self._free_mb()
        low = False
        reason, message = None, None
        while True:
            now = time.monotonic()
            try:
                blk = self._q.get(timeout=TICK_S / 2)
            except queue.Empty:
                blk = None
            if blk is not None:
                x = self._flat(blk)
                if len(x):
                    xf = x.astype(np.float32)
                    win_sq += float(np.sum(xf * xf))
                    win_n += len(x)
                    win_peak = max(win_peak, int(np.max(np.abs(x.astype(np.int32)))))
                    if self._state == "recording":
                        f.write(x.astype("<i2").tobytes())
                        self._samples += len(x)
            if now - t_disk >= DISK_CHECK_S:
                t_disk = now
                free = self._free_mb()
                if free is not None:
                    low = free < LOW_DISK_MB
                    if free < STOP_DISK_MB:
                        reason, message = "disk_full", "The disk is almost full, so the recording was stopped safely. Everything recorded so far is saved."
            if now - t_fix >= HEADER_FIX_S:
                t_fix = now
                self._fix_header(f)
            if reason is None and not self._stop.is_set() and self._stream is not None and not getattr(self._stream, "active", True):
                reason, message = "device_lost", "The microphone stopped (unplugged or switched off?). Everything recorded so far is saved."
            if now - t_tick >= TICK_S:
                t_tick = now
                level = (win_sq / win_n) ** 0.5 / 32768 if win_n else 0.0
                if win_peak >= CLIP_PEAK:
                    clip_until = now + 1.0
                if level >= SILENT_LEVEL:
                    last_sound = now
                silent = self._state == "recording" and now - last_sound >= SILENT_HINT_S
                self._emit(level=round(min(1.0, level), 4), peak_clipping=now < clip_until, silent=silent,
                           low_disk=low, free_disk_mb=None if free is None else int(free))
                win_sq, win_n, win_peak = 0.0, 0, 0
                if self._state != "recording":
                    last_sound = now      # no "silent" hint while paused
            if reason or (self._stop.is_set() and self._q.empty()):
                break
        reason = reason or getattr(self, "_stop_reason", None) or "stopped"
        self._close_stream()
        while True:                      # whatever the library delivered before it stopped
            try:
                x = self._q.get_nowait()
            except queue.Empty:
                break
            if self._state == "recording":
                x = self._flat(x)
                f.write(x.astype("<i2").tobytes())
                self._samples += len(x)
        self._fix_header(f)
        f.close()
        self._state = "stopped"
        self._result = {"path": str(self.path), "duration_s": round(self.elapsed_s, 1), "reason": reason}
        if message:
            self._result["message"] = message
        self._emit(level=0.0, peak_clipping=False, silent=False, low_disk=low,
                   free_disk_mb=None if free is None else int(free), reason=reason, **({"message": message} if message else {}))
        self._finished.set()
        if reason in ("disk_full", "device_lost") and self.on_finish and not self._cancel:
            try:
                self.on_finish(dict(self._result))
            except Exception:  # noqa: BLE001
                log.exception("on_finish failed")

    def _fix_header(self, f) -> None:
        try:
            f.flush()
            n = self._samples * 2
            end = f.tell()
            f.seek(0)
            f.write(_header(n))
            f.seek(end)
            f.flush()
            os.fsync(f.fileno())
        except (OSError, ValueError):
            pass
