"""Computer sound (WASAPI loopback) and mixing, with fakes only: no audio hardware is touched.

The real loopback cannot be exercised on the macOS dev machine; see tools/check_loopback.py and the Windows
validation checklist in docs/INSTRUCTIONS.md."""
import sys
import time
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from app import api as api_mod
from app import library, main, recorder
from app.recorder import Mixer, PolyResampler, SAMPLE_RATE as SR


def sine(freq, seconds, rate=SR, amp=0.3):
    t = np.arange(int(rate * seconds)) / rate
    return (amp * 32767 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def dominant(x, rate=SR):
    sp = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.argmax(sp) * rate / len(x)


def read(p):
    with wave.open(str(p)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


# ---- resampling ---------------------------------------------------------------
@pytest.mark.parametrize("rate", [48000, 44100, 96000, 8000, 22050])
def test_resampling_keeps_the_frequency_and_length(rate):
    rs = PolyResampler(rate)
    x = sine(1000, 2.0, rate)
    out = np.concatenate([rs(x[i:i + 1234]) for i in range(0, len(x), 1234)])   # odd block sizes
    assert abs(len(out) - 2 * SR) < 40
    assert abs(dominant(out[2000:-2000]) - 1000) < 5
    assert np.abs(out[2000:-2000]).max() == pytest.approx(0.3 * 32767, rel=0.03)


def test_resampling_is_block_size_independent_and_rejects_aliasing():
    x = sine(700, 1.0, 48000) + sine(20000, 1.0, 48000, amp=0.2)     # 20 kHz must not fold into the band
    a = PolyResampler(48000)(x)
    rs = PolyResampler(48000)
    b = np.concatenate([rs(x[i:i + 777]) for i in range(0, len(x), 777)])
    n = min(len(a), len(b))
    assert np.allclose(a[:n], b[:n], atol=1e-2)
    seg = a[1000:-1000]
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    assert abs(dominant(seg) - 700) < 5
    assert sp[np.argmin(abs(f - 4000))] < 0.01 * sp.max()       # 20 kHz would alias to 4 kHz without the filter


def test_resampler_native_16k_is_untouched():
    x = sine(300, 0.5)
    assert np.array_equal(PolyResampler(16000)(x), x)


# ---- mixer ---------------------------------------------------------------------
def feed(mx, name, x, t_start, step=0.1):
    """Deliver x in 100 ms blocks as a real callback would, each stamped with its end time."""
    n = int(SR * step)
    for i in range(0, len(x), n):
        mx.push(name, t_start + (i + len(x[i:i + n])) / SR, x[i:i + n])


def test_mixer_gain_never_clips_with_two_full_scale_sources():
    mx = Mixer(["system", "mic"])
    full = np.full(SR, 32767, dtype=np.float32)
    feed(mx, "system", full, 0.0)
    feed(mx, "mic", full, 0.0)
    mix, tr = mx.pull(1.3)
    assert len(mix) == SR and mix.max() <= 32767 and mix.min() >= -32768
    assert (mix == 32767).all()                       # 0.5 + 0.5 reaches full scale, no wrap-around
    neg = np.full(SR, -32768, dtype=np.float32)
    feed(mx, "system", neg, 1.0); feed(mx, "mic", neg, 1.0)
    assert (mx.pull(2.3)[0] == -32768).all()
    assert np.array_equal(tr["system"], full.astype(np.int16))        # the separate tracks keep full level


def test_mixer_single_source_has_unit_gain():
    mx = Mixer(["system"])
    x = sine(440, 1.0)
    feed(mx, "system", x, 0.0)
    mix, _ = mx.pull(1.3)
    assert np.allclose(mix, x.astype(np.int16), atol=1)


def test_silence_is_filled_when_the_loopback_stalls_so_streams_stay_aligned():
    """Loopback delivers nothing while nothing plays: a tone at 0-2 s, nothing 2-8 s, a tone again at 8-10 s,
    while the microphone runs continuously. The marker tone in the mic at 9 s must still line up."""
    mx = Mixer(["system", "mic"])
    out_sys, out_mic = [], []
    t = 0.0
    while t < 10.0:
        t = round(t + 0.1, 3)
        if t <= 2.0 or t > 8.0:
            mx.push("system", t, sine(500, 0.1))
        mx.push("mic", t, sine(900, 0.1))
        _, tr = mx.pull(t)
        out_sys.append(tr["system"]); out_mic.append(tr["mic"])
    _, tr = mx.pull(10.0, flush=True)
    out_sys.append(tr["system"]); out_mic.append(tr["mic"])
    s, m = np.concatenate(out_sys), np.concatenate(out_mic)
    assert len(s) == len(m) == 10 * SR                           # exactly wall-clock long
    assert np.abs(s[2 * SR + 800:8 * SR - 800]).max() == 0       # silence in the gap
    assert np.abs(s[:2 * SR]).max() > 5000 and np.abs(s[8 * SR + 200:]).max() > 5000
    first = np.argmax(np.abs(s[7 * SR:]) > 1000) / SR + 7        # tone restarts at 8.0 s, not at 2.0 s
    assert first == pytest.approx(8.0, abs=0.05)
    assert mx.stall_fills >= 1


def test_drift_over_a_simulated_ten_minutes():
    """Microphone clock 200 ppm fast, loopback 150 ppm slow. Both tracks stay as long as the wall clock and a
    click placed at 9:50 stays within 100 ms in both."""
    for sys_ppm, mic_ppm in ((-150, 200), (300, -300)):
        mx = Mixer(["system", "mic"])
        total = 600.0
        tracks = {"system": [], "mic": []}
        click_at = 590.0
        t = 0.0
        sys_t = mic_t = 0.0         # each source's own clock (seconds of audio delivered so far)
        while t < total:
            t = round(t + 0.1, 4)
            for name, ppm in (("system", sys_ppm), ("mic", mic_ppm)):
                own = t * (1 + ppm * 1e-6)
                n_new = int(own * SR) - int((own - 0.1 * (1 + ppm * 1e-6)) * SR)
                st = own - n_new / SR
                blk = np.zeros(n_new, dtype=np.float32)
                idx = int(round((click_at - st) * SR))     # a click at wall-clock 590 s in each source's own time
                if 0 <= idx < n_new:
                    blk[idx] = 20000
                mx.push(name, t, blk)
            _, tr = mx.pull(t)
            for k in tracks:
                tracks[k].append(tr[k])
        _, tr = mx.pull(total, flush=True)
        for k in tracks:
            tracks[k].append(tr[k])
        for k in tracks:
            a = np.concatenate(tracks[k])
            assert len(a) == int(total * SR)
            pos = np.argmax(np.abs(a))
            assert abs(pos / SR - click_at) < 0.1, (k, pos / SR)
        assert mx.drift_drops < 10


# ---- recorder with fake streams -------------------------------------------------
class FakeSys:
    instances = []

    def __init__(self, device, cb, rate=48000, channels=2, name="Fake speakers"):
        self.device, self.cb, self.samplerate, self.channels, self.name = device, cb, rate, channels, name
        self.active = False
        self.moved = False
        FakeSys.instances.append(self)

    def start(self): self.active = True
    def stop(self): self.active = False
    def close(self): self.active = False
    def default_changed(self): return self.moved

    def feed(self, seconds, freq=500, amp=0.3):
        x = sine(freq, seconds, self.samplerate, amp).astype(np.int16)
        x = np.repeat(x[:, None], self.channels, axis=1)
        step = self.samplerate // 10
        for i in range(0, len(x), step):
            self.cb(x[i:i + step], len(x[i:i + step]), None, None)
            time.sleep(0.1)


class FakeMic:
    instances = []

    def __init__(self, **kw):
        self.kw, self.cb, self.active = kw, kw["callback"], False
        FakeMic.instances.append(self)

    def start(self): self.active = True
    def stop(self): self.active = False
    def close(self): self.active = False

    def feed(self, seconds, freq=900, amp=0.3):
        x = sine(freq, seconds).astype(np.int16).reshape(-1, 1)
        for i in range(0, len(x), 1600):
            self.cb(x[i:i + 1600], 1600, None, None)
            time.sleep(0.1)


def sysf(**kw):
    return lambda dev, cb: FakeSys(dev, cb, **kw)


def disk(mb=5000):
    return lambda p: SimpleNamespace(total=10**12, used=0, free=int(mb * 1e6))


def make(tmp_path, sources, ev=None, fin=None, sys_factory=None, **kw):
    FakeSys.instances.clear(); FakeMic.instances.clear()
    r = recorder.Recorder(tmp_path / "recording.wav", None, ev.append if ev is not None else None, fin.append if fin is not None else None,
                          stream_factory=lambda **k: FakeMic(**k), disk_usage=disk(), sources=sources,
                          system_factory=sys_factory or sysf(), **kw)
    r.start()
    return r


def wait_for(cond, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_both_sources_write_mix_and_two_separate_tracks_at_16k(tmp_path):
    ev = []
    r = make(tmp_path, {"system": True, "mic": True}, ev)
    s, m = FakeSys.instances[0], FakeMic.instances[0]
    import threading
    t = threading.Thread(target=lambda: s.feed(1.5)); t.start()
    m.feed(1.5)
    t.join()
    info = r.stop()
    assert info["tracks"]["system"].endswith("system.wav") and info["reason"] == "stopped"
    mix, sy, mi = (read(tmp_path / n) for n in ("recording.wav", "system.wav", "mic.wav"))
    assert len(mix) == len(sy) == len(mi)
    assert len(mix) / SR == pytest.approx(info["duration_s"], abs=0.1) and 1.4 < info["duration_s"] < 2.2
    assert abs(dominant(sy[SR // 2:SR // 2 + 8000].astype(float)) - 500) < 8      # the 48 kHz stereo source arrived right
    assert abs(dominant(mi[SR // 2:SR // 2 + 8000].astype(float)) - 900) < 8
    sp = np.abs(np.fft.rfft(mix[SR // 2:SR // 2 + 8000] * np.hanning(8000)))       # both voices are in the mix
    f = np.fft.rfftfreq(8000, 1 / SR)
    assert sp[np.argmin(abs(f - 500))] > 50 * np.median(sp) and sp[np.argmin(abs(f - 900))] > 50 * np.median(sp)
    lv = [e for e in ev if e["state"] == "recording"]
    assert max(e["level_system"] for e in lv) > 0.05 and max(e["level_mic"] for e in lv) > 0.05
    assert ev[-1]["state"] == "stopped" and ev[-1]["level_mic"] == 0.0


def test_loopback_that_delivers_nothing_still_gives_a_full_length_aligned_file(tmp_path):
    r = make(tmp_path, {"system": True, "mic": True})
    FakeMic.instances[0].feed(2.0)           # the microphone talks; nothing plays on the speakers
    info = r.stop()
    mix, sy, mi = (read(tmp_path / n) for n in ("recording.wav", "system.wav", "mic.wav"))
    assert len(sy) == len(mi) == len(mix) and info["duration_s"] == pytest.approx(2.0, abs=0.25)
    assert np.abs(sy).max() == 0 and np.abs(mi).max() > 5000
    assert np.abs(mix).max() > 4000                  # the learner's voice is not lost


def test_system_only_has_no_separate_tracks_and_toggles(tmp_path):
    r = make(tmp_path, {"system": True, "mic": False})
    assert not FakeMic.instances
    FakeSys.instances[0].feed(1.0)
    info = r.stop()
    assert "tracks" not in info and not (tmp_path / "system.wav").exists() and not (tmp_path / "mic.wav").exists()
    assert np.abs(read(tmp_path / "recording.wav")).max() > 5000
    ev = []
    r = make(tmp_path / "..", {"system": False, "mic": True}, ev)      # mic only: the original path
    assert not FakeSys.instances
    FakeMic.instances[0].feed(1.0)
    r.stop()
    assert ev[0]["level_system"] is None and ev[0]["level_mic"] is not None
    with pytest.raises(recorder.RecorderError) as e:
        recorder.Recorder(tmp_path / "x.wav", sources={"system": False, "mic": False})
    assert e.value.code == "NO_SOURCE"


def test_pause_does_not_record_and_keeps_tracks_aligned(tmp_path):
    r = make(tmp_path, {"system": True, "mic": True})
    FakeMic.instances[0].feed(1.0)
    r.pause()
    time.sleep(0.8)
    FakeMic.instances[0].feed(0.5)          # delivered while paused: dropped
    r.resume()
    FakeMic.instances[0].feed(1.0)
    info = r.stop()
    a, b = read(tmp_path / "system.wav"), read(tmp_path / "mic.wav")
    assert len(a) == len(b) and info["duration_s"] == pytest.approx(2.0, abs=0.4)


def test_no_system_sound_hint_while_microphone_is_heard(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "SILENT_HINT_S", 0.6)
    ev = []
    r = make(tmp_path, {"system": True, "mic": True}, ev)
    FakeMic.instances[0].feed(1.5)
    r.stop()
    hints = [e for e in ev if e.get("hint")]
    assert hints and hints[0]["hint"] == "no_system_audio" and "No computer sound detected" in hints[0]["hint_text"]
    assert not hints[0]["silent"]            # the microphone is fine


def test_default_output_change_reattaches_and_continues(tmp_path):
    ev, fin = [], []
    r = make(tmp_path, {"system": True, "mic": True}, ev, fin)
    FakeMic.instances[0].feed(0.5)
    FakeSys.instances[0].moved = True       # headphones plugged in: the default output changed
    assert wait_for(lambda: len(FakeSys.instances) == 2, 4)
    FakeSys.instances[1].feed(1.0)
    info = r.stop()
    assert info["reason"] == "stopped" and not fin
    notes = [e for e in ev if e.get("notice_key") == "output_changed"]
    assert notes and "continues" in notes[0]["notice"]
    assert np.abs(read(tmp_path / "system.wav")).max() > 5000       # audio from the new device was recorded


def test_default_output_change_that_cannot_reattach_keeps_the_microphone(tmp_path):
    ev, fin = [], []
    calls = {"n": 0}

    def flaky(dev, cb):
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("No default output device")
        return FakeSys(dev, cb)
    r = make(tmp_path, {"system": True, "mic": True}, ev, fin, sys_factory=flaky)
    FakeMic.instances[0].feed(0.5)
    FakeSys.instances[0].moved = True
    assert wait_for(lambda: any(e.get("notice_key") == "system_stopped" for e in ev), 4)
    FakeMic.instances[0].feed(0.5)
    info = r.stop()
    assert info["reason"] == "stopped" and not fin and info["duration_s"] > 0.8


def test_system_only_lost_stops_safely_and_tells_the_user(tmp_path):
    ev, fin = [], []
    calls = {"n": 0}

    def flaky(dev, cb):
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("No default output device")
        return FakeSys(dev, cb)
    r = make(tmp_path, {"system": True, "mic": False}, ev, fin, sys_factory=flaky)
    FakeSys.instances[0].feed(1.0)
    FakeSys.instances[0].active = False
    assert wait_for(lambda: fin, 5)
    assert fin[0]["reason"] == "device_lost" and "saved" in fin[0]["message"]
    assert recorder.wav_duration(tmp_path / "recording.wav") > 0.8


def test_crash_recovery_repairs_the_separate_tracks_too(tmp_path):
    lid = library.create_lesson("Crashed", "", None, "fast", None,
                                {"spoken_languages": ["ar", "he"], "arabic_dialect": "msa", "mode": "auto"})
    d = library.config.library_dir() / lid
    r = make(d, {"system": True, "mic": True})
    FakeMic.instances[0].feed(2.0)
    time.sleep(0.2)
    library.update_meta(lid, status="recording", audio_path=str(d / "recording.wav"))
    r.stop()
    for n in ("recording.wav", "system.wav", "mic.wav"):        # the crash: header says 0 bytes, torn last sample
        raw = bytearray((d / n).read_bytes())[:-1]
        raw[40:44] = b"\0\0\0\0"
        (d / n).write_bytes(bytes(raw))
    a = api_mod.Api(lambda n_, p: None)
    meta = a.get_lesson(lid)["meta"]
    assert meta["status"] == "interrupted" and meta["recovered"]
    for n in ("system.wav", "mic.wav"):
        assert recorder.wav_duration(d / n) > 1.5
        with wave.open(str(d / n)) as w:
            assert w.getnframes() > 24000


def test_cancel_deletes_all_tracks(tmp_path):
    r = make(tmp_path, {"system": True, "mic": True})
    FakeMic.instances[0].feed(0.5)
    r.cancel()
    assert not list(tmp_path.glob("*.wav"))


# ---- errors -----------------------------------------------------------------------
def test_error_messages(tmp_path):
    def boom(msg):
        def f(dev, cb):
            raise OSError(msg)
        return f
    for msg, code, words in (("No default output device", "NO_OUTPUT", "No speakers or headphones"),
                             ("Error opening stream: Device unavailable [PaErrorCode -9985]", "LOOPBACK_DENIED", "exclusive control"),
                             ("weird failure", "LOOPBACK_ERROR", "microphone only")):
        r = recorder.Recorder(tmp_path / "a.wav", sources={"system": True, "mic": False}, system_factory=boom(msg), disk_usage=disk())
        with pytest.raises(recorder.RecorderError) as e:
            r.start()
        assert e.value.code == code and words in e.value.text and not (tmp_path / "a.wav").exists()
    def denied(**kw):
        raise OSError("Error opening InputStream: Unanticipated host error [PaErrorCode -9999] [MME error 5]")
    r = recorder.Recorder(tmp_path / "b.wav", sources={"system": True, "mic": True}, system_factory=sysf(),
                          stream_factory=denied, disk_usage=disk())
    FakeSys.instances.clear()
    with pytest.raises(recorder.RecorderError) as e:
        r.start()
    assert e.value.code == "MIC_DENIED" and "Let desktop apps access your microphone" in e.value.text
    assert "Switch off 'My microphone'" in e.value.text
    assert not FakeSys.instances[0].active and not (tmp_path / "b.wav").exists()      # the open loopback was released


def test_loopback_unavailable_off_windows(tmp_path):
    assert recorder.loopback_available() is (sys.platform == "win32")
    if sys.platform != "win32":
        r = recorder.Recorder(tmp_path / "a.wav", sources={"system": True, "mic": True}, disk_usage=disk())
        with pytest.raises(recorder.RecorderError) as e:
            r.start()
        assert e.value.code == "LOOPBACK_UNAVAILABLE"
        info = recorder.list_audio_sources(sd=SimpleNamespace(default=SimpleNamespace(device=[0, 0], hostapi=0),
                                           query_devices=lambda: [{"name": "M", "max_input_channels": 1, "hostapi": 0}]))
        assert info == {"microphones": [{"id": 0, "name": "M", "default": True}], "loopback_available": False, "outputs": []}


# ---- the PyAudioWPatch wrapper, with a fake module ---------------------------------
class FakePA:
    paInt16, paContinue = 8, 0
    devices = [{"index": 5, "name": "Speakers (Realtek) [Loopback]", "maxInputChannels": 2, "defaultSampleRate": 48000.0},
               {"index": 6, "name": "Headphones (USB) [Loopback]", "maxInputChannels": 2, "defaultSampleRate": 44100.0}]
    default = 5
    opened = []

    class PyAudio:
        def get_loopback_device_info_generator(self):
            return iter(FakePA.devices)

        def get_default_wasapi_loopback(self):
            if FakePA.default is None:
                raise OSError("Default WASAPI output not found")
            return next(d for d in FakePA.devices if d["index"] == FakePA.default)

        def open(self, **kw):
            FakePA.opened.append(kw)
            return SimpleNamespace(stop_stream=lambda: None, start_stream=lambda: None, close=lambda: None, is_active=lambda: True)

        def terminate(self):
            pass


def test_list_audio_sources_and_loopback_stream_with_a_fake_library(monkeypatch):
    info = recorder.list_audio_sources(sd=SimpleNamespace(default=SimpleNamespace(device=[0, 0], hostapi=0), query_devices=lambda: []),
                                       pyaudio=FakePA)
    assert info["loopback_available"] and info["microphones"] == []
    assert info["outputs"] == [{"id": 5, "name": "Speakers (Realtek)", "default": True},
                               {"id": 6, "name": "Headphones (USB)", "default": False}]
    got = []
    ls = recorder.LoopbackStream(None, lambda *a: got.append(a), pyaudio=FakePA)
    assert (ls.samplerate, ls.channels, ls.device) == (48000, 2, 5) and FakePA.opened[-1]["input_device_index"] == 5
    ls._raw(np.zeros((480, 2), dtype=np.int16).tobytes(), 480, None, None)
    assert got[0][0].shape == (480, 2)
    FakePA.default = 6                                  # the user plugged headphones in
    assert ls.default_changed()
    ls2 = recorder.LoopbackStream(6, lambda *a: None, pyaudio=FakePA)
    assert ls2.samplerate == 44100
    FakePA.default = None
    with pytest.raises(OSError):
        recorder.LoopbackStream(None, lambda *a: None, pyaudio=FakePA)
    assert recorder.explain_loopback_error(OSError("No default output device")).code == "NO_OUTPUT"
    FakePA.default = 5


# ---- through the Api ----------------------------------------------------------------
def api_fake(events):
    a = api_mod.Api(lambda n, p: events.append((n, p)))
    a._rec_factory = lambda **k: FakeMic(**k)
    return a


def test_api_defaults_and_both_sources(monkeypatch):
    monkeypatch.setattr(recorder, "list_input_devices", lambda sd=None: [{"id": 0, "name": "x", "default": True}])
    ev = []
    a = api_fake(ev)
    a._sys_factory = sysf()
    FakeSys.instances.clear(); FakeMic.instances.clear()
    src = a.list_audio_sources()
    assert src["loopback_available"] and src["outputs"] and src["microphones"]
    r = a.start_recording({})                                 # defaults: both on
    assert FakeSys.instances and FakeMic.instances
    FakeMic.instances[-1].feed(1.2)
    res = a.stop_recording()
    meta = a.get_lesson(r["lesson_id"])["meta"]
    assert meta["source"] == "computer+microphone" and meta["sources"] == {"system": True, "mic": True}
    assert res["tracks"]["system"].endswith("system.wav")
    assert any(n == "record" and "level_system" in p and p.get("level_mic") is not None for n, p in ev)
    with pytest.raises(ValueError, match="NO_SOURCE"):
        a.start_recording({"sources": {"system": False, "mic": False}})
    assert len(library.list_lessons()) == 1                   # the refused start left nothing behind


def test_api_without_loopback_behaves_as_before(monkeypatch):
    monkeypatch.setattr(recorder, "list_input_devices", lambda sd=None: [{"id": 0, "name": "x", "default": True}])
    monkeypatch.setattr(recorder, "loopback_available", lambda: False)
    a = api_fake([])
    assert a.list_audio_sources()["loopback_available"] is False
    r = a.start_recording({})                                 # default = microphone only
    FakeMic.instances[-1].feed(1.2)
    a.stop_recording()
    assert a.get_lesson(r["lesson_id"])["meta"]["source"] == "microphone"
    with pytest.raises(ValueError, match="LOOPBACK_UNAVAILABLE"):
        a.start_recording({"sources": {"system": True, "mic": True}})


def test_list_audio_cli_prints_json_and_exits_zero(capsys):
    assert main.main(["--list-audio"]) == 0
    import json
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["ok"] is True and set(("microphones", "outputs", "loopback_available", "imports")) <= set(out)
