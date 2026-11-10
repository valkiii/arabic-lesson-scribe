"""Recording from the microphone, with a fake input stream (a sine wave plus silence)."""
import struct
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app import api as api_mod
from app import library, recorder

SR = recorder.SAMPLE_RATE


class FakeStream:
    """Stands in for sounddevice.InputStream; the test feeds blocks through feed()."""
    instances = []

    def __init__(self, **kw):
        self.kw, self.active, self.cb = kw, False, kw["callback"]
        FakeStream.instances.append(self)

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def close(self):
        self.active = False

    def feed(self, seconds, kind="sine", amp=0.3):
        n = int(SR * seconds)
        t = np.arange(n) / SR
        x = (amp * 32767 * np.sin(2 * np.pi * 440 * t)) if kind == "sine" else np.zeros(n)
        x = x.astype(np.int16).reshape(-1, 1)
        for i in range(0, n, 1600):
            self.cb(x[i:i + 1600], len(x[i:i + 1600]), None, None)


def factory(**kw):
    return FakeStream(**kw)


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def disk(free_mb):
    return lambda p: SimpleNamespace(total=10**12, used=0, free=int(free_mb * 1e6))


def make(tmp_path, events=None, finish=None, free_mb=5000):
    FakeStream.instances.clear()
    r = recorder.Recorder(tmp_path / "rec.wav", None, (events.append if events is not None else None), finish,
                          stream_factory=factory, disk_usage=disk(free_mb))
    r.start()
    return r, FakeStream.instances[0]


def test_wav_is_written_correctly_and_stop_returns_duration(tmp_path):
    ev = []
    r, st = make(tmp_path, ev)
    st.feed(2.0)
    st.feed(1.0, "silence")
    info = r.stop()
    assert info["reason"] == "stopped" and info["duration_s"] == pytest.approx(3.0, abs=0.05)
    with wave.open(str(tmp_path / "rec.wav")) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 16000)
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    assert len(data) == 48000
    assert np.abs(data[:32000]).max() > 9000 and np.abs(data[32000:]).max() == 0
    assert ev[-1]["state"] == "stopped" and r.state == "stopped"
    assert r.stop()["duration_s"] == info["duration_s"]  # idempotent


def test_level_events_clipping_and_rate(tmp_path):
    ev = []
    r, st = make(tmp_path, ev)
    st.feed(1.0, amp=0.5)
    time.sleep(0.3)
    st.feed(0.5, amp=1.0)
    time.sleep(0.3)
    r.stop()
    lv = [e["level"] for e in ev if e["state"] == "recording"]
    assert lv and max(lv) > 0.2 and all(0 <= x <= 1 for x in lv)
    assert any(e["peak_clipping"] for e in ev)
    assert all("elapsed_s" in e and "free_disk_mb" in e for e in ev)
    assert ev[0]["free_disk_mb"] == 5000


def test_pause_and_resume_leave_no_gap_and_no_pause_audio(tmp_path):
    ev = []
    r, st = make(tmp_path, ev)
    st.feed(1.0)
    time.sleep(0.4)
    r.pause()
    assert r.state == "paused"
    st.feed(2.0)           # arrives while paused: must not be recorded
    time.sleep(0.4)
    r.resume()
    st.feed(1.0)
    info = r.stop()
    assert info["duration_s"] == pytest.approx(2.0, abs=0.15)
    assert any(e["state"] == "paused" for e in ev)


def test_header_is_valid_even_while_recording_and_repair_after_crash(tmp_path):
    r, st = make(tmp_path)
    st.feed(2.0)
    time.sleep(2.4)                        # the header is corrected about every two seconds
    p = tmp_path / "rec.wav"
    copy = tmp_path / "crash.wav"
    copy.write_bytes(p.read_bytes())       # what a crash would leave
    r.stop()
    n = len(copy.read_bytes())
    copy.write_bytes(copy.read_bytes() + b"\x01")      # a torn last sample
    dur = recorder.repair_wav(copy)
    assert dur == pytest.approx((n - 44) / 2 / SR)
    with wave.open(str(copy)) as w:
        assert w.getnframes() == (n - 44) // 2
    # a header that was never fixed (size 0) is repaired from the file size
    raw = bytearray(p.read_bytes())
    raw[40:44] = struct.pack("<I", 0)
    raw[4:8] = struct.pack("<I", 36)
    bad = tmp_path / "bad.wav"
    bad.write_bytes(bytes(raw))
    assert recorder.repair_wav(bad) == pytest.approx(2.0, abs=0.01)
    with wave.open(str(bad)) as w:
        assert w.getnframes() == 32000
    (tmp_path / "junk.wav").write_bytes(b"x" * 100)
    with pytest.raises(ValueError):
        recorder.repair_wav(tmp_path / "junk.wav")


def test_silence_hint_after_20_seconds(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "SILENT_HINT_S", 0.5)
    ev = []
    r, st = make(tmp_path, ev)
    st.feed(0.2, "silence")
    time.sleep(0.8)
    st.feed(0.2, "silence")
    time.sleep(0.3)
    assert any(e["silent"] for e in ev)
    st.feed(0.5)
    time.sleep(0.3)
    assert ev[-1]["silent"] is False
    r.stop()


def test_device_unplugged_keeps_what_was_recorded(tmp_path):
    ev, fin = [], []
    r, st = make(tmp_path, ev, fin.append)
    st.feed(1.5)
    time.sleep(0.3)
    st.active = False                       # the library stops delivering: the microphone is gone
    assert wait_for(lambda: fin)
    assert fin[0]["reason"] == "device_lost" and "unplugged" in fin[0]["message"]
    assert fin[0]["duration_s"] == pytest.approx(1.5, abs=0.15)
    assert recorder.wav_duration(tmp_path / "rec.wav") == pytest.approx(1.5, abs=0.15)


def test_low_disk_warns_then_stops_safely(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "DISK_CHECK_S", 0.1)
    ev, fin = [], []
    free = {"mb": 400}
    FakeStream.instances.clear()
    r = recorder.Recorder(tmp_path / "rec.wav", None, ev.append, fin.append, stream_factory=factory,
                          disk_usage=lambda p: SimpleNamespace(free=int(free["mb"] * 1e6)))
    r.start()
    st = FakeStream.instances[0]
    st.feed(1.0)
    assert wait_for(lambda: any(e.get("low_disk") for e in ev))
    free["mb"] = 50
    assert wait_for(lambda: fin)
    assert fin[0]["reason"] == "disk_full" and "almost full" in fin[0]["message"]
    assert recorder.wav_duration(tmp_path / "rec.wav") == pytest.approx(1.0, abs=0.15)


def test_refuses_to_start_on_a_full_disk(tmp_path):
    FakeStream.instances.clear()
    r = recorder.Recorder(tmp_path / "rec.wav", None, stream_factory=factory, disk_usage=disk(50))
    with pytest.raises(recorder.RecorderError) as e:
        r.start()
    assert e.value.code == "DISK_FULL" and not (tmp_path / "rec.wav").exists()


def test_permission_denied_and_no_device_messages(tmp_path):
    def denied(**kw):
        raise OSError("Error opening InputStream: Unanticipated host error [PaErrorCode -9999]: 'Undefined external error.' [MME error 5]")
    r = recorder.Recorder(tmp_path / "a.wav", None, stream_factory=denied, disk_usage=disk(5000))
    with pytest.raises(recorder.RecorderError) as e:
        r.start()
    assert e.value.code == "MIC_DENIED" and "Let desktop apps access your microphone" in str(e.value)
    assert not (tmp_path / "a.wav").exists()

    class NoDevices:
        default = SimpleNamespace(device=[-1, -1], hostapi=0)

        @staticmethod
        def query_devices():
            return [{"name": "Speakers", "max_input_channels": 0, "hostapi": 0}]
    assert recorder.list_input_devices(NoDevices) == []
    import sys
    fake = SimpleNamespace(**{k: getattr(NoDevices, k) for k in ("default", "query_devices")}, InputStream=factory)
    sys.modules["sounddevice"], old = fake, sys.modules.get("sounddevice")
    try:
        r = recorder.Recorder(tmp_path / "b.wav", None, disk_usage=disk(5000))
        with pytest.raises(recorder.RecorderError) as e:
            r.start()
        assert e.value.code == "NO_MIC" and "No microphone" in e.value.text
    finally:
        if old is None:
            sys.modules.pop("sounddevice")
        else:
            sys.modules["sounddevice"] = old


def test_device_list_keeps_default_audio_system_only():
    class SD:
        default = SimpleNamespace(device=[2, 5], hostapi=0)

        @staticmethod
        def query_devices():
            return [{"name": "Out", "max_input_channels": 0, "hostapi": 0},
                    {"name": "Mic A", "max_input_channels": 2, "hostapi": 1},
                    {"name": "Mic A", "max_input_channels": 2, "hostapi": 0},
                    {"name": "Mic B", "max_input_channels": 1, "hostapi": 0}]
    assert recorder.list_input_devices(SD) == [{"id": 2, "name": "Mic A", "default": True},
                                               {"id": 3, "name": "Mic B", "default": False}]


# ---- through the Api and the library ---------------------------------------
def api_with_fake(events):
    a = api_mod.Api(lambda n, p: events.append((n, p)))
    a._rec_factory = factory
    return a


def test_api_record_stop_creates_a_part_of_today(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "list_input_devices", lambda sd=None: [{"id": 0, "name": "x", "default": True}])
    ev = []
    a = api_with_fake(ev)
    r = a.start_recording({"title": "My lesson"})
    st = FakeStream.instances[-1]
    st.feed(1.5)
    time.sleep(0.3)
    a.pause_recording(); a.resume_recording()
    with pytest.raises(ValueError, match="BUSY"):
        a.start_recording()
    res = a.stop_recording()
    assert res["lesson_id"] == r["lesson_id"] and res["duration_s"] == pytest.approx(1.5, abs=0.2)
    les = a.get_lesson(r["lesson_id"])
    assert les["meta"]["status"] == "recorded" and les["meta"]["audio_ok"] and les["meta"]["source"] == "microphone"
    assert les["meta"]["spoken_languages"] and les["meta"]["day"] == time.strftime("%Y-%m-%d")
    assert any(n == "record" and p["state"] == "recording" and p["level"] > 0 for n, p in ev)
    assert a.list_days()[0]["parts"][0]["id"] == r["lesson_id"]
    # 'Transcribe later' keeps the lesson; the same call the UI uses later accepts it
    assert api_mod.Api._plan_from_meta(les["meta"])["kind"] in ("auto", "forced")
    with pytest.raises(ValueError):
        a.stop_recording()


def test_api_cancel_discards_everything():
    ev = []
    a = api_with_fake(ev)
    import app.recorder as rec
    rec.list_input_devices = lambda sd=None: [{"id": 0, "name": "x", "default": True}]
    r = a.start_recording()
    FakeStream.instances[-1].feed(0.5)
    a.cancel_recording()
    assert library.list_lessons() == []


def test_api_start_failure_leaves_no_lesson():
    a = api_mod.Api(lambda n, p: None)
    def denied(**kw):
        raise OSError("Access denied")
    a._rec_factory = denied
    with pytest.raises(ValueError, match="MIC_DENIED"):
        a.start_recording()
    assert library.list_lessons() == []


def test_api_device_lost_marks_lesson_recorded_and_emits_message():
    ev = []
    a = api_with_fake(ev)
    r = a.start_recording()
    st = FakeStream.instances[-1]
    st.feed(1.5)
    time.sleep(0.3)
    st.active = False
    assert wait_for(lambda: any(n == "record" and p.get("final") for n, p in ev))
    p = [p for n, p in ev if n == "record" and p.get("final")][-1]
    assert p["reason"] == "device_lost" and p["message"] and p["lesson_id"] == r["lesson_id"]
    assert a.get_lesson(r["lesson_id"])["meta"]["status"] == "recorded"


def test_recovery_of_an_unfinished_recording_on_startup(tmp_path):
    lid = library.create_lesson("Crashed", "", None, "fast", None,
                                {"spoken_languages": ["ar", "he"], "arabic_dialect": "msa", "mode": "auto"})
    wav = Path(library.config.library_dir()) / lid / "recording.wav"
    r = recorder.Recorder(wav, None, stream_factory=factory, disk_usage=disk(5000))
    FakeStream.instances.clear()
    r.start()
    FakeStream.instances[0].feed(3.0)
    time.sleep(0.4)
    library.update_meta(lid, status="recording", audio_path=str(wav))
    raw = wav.read_bytes()                       # simulate the crash: stale header, no clean stop
    r.stop()
    wav.write_bytes(raw[:44 + 2 * 40000][:-1])   # truncated mid-sample, header says 0 bytes
    b = bytearray(wav.read_bytes()); b[40:44] = struct.pack("<I", 0); wav.write_bytes(bytes(b))
    a = api_mod.Api(lambda n, p: None)           # startup runs recover_interrupted
    meta = a.get_lesson(lid)["meta"]
    assert meta["status"] == "interrupted" and meta["audio_ok"] and meta["recovered"]
    assert meta["duration_s"] == pytest.approx(39999 / SR, abs=0.1)
    with wave.open(str(wav)) as w:
        assert w.getnframes() == 39999
    # an empty recording cannot be recovered
    lid2 = library.create_lesson("Empty", "", None, "fast")
    w2 = Path(library.config.library_dir()) / lid2 / "recording.wav"
    w2.write_bytes(recorder._header(0))
    library.update_meta(lid2, status="recording", audio_path=str(w2))
    library.recover_interrupted()
    assert library.get_lesson(lid2)["meta"]["status"] == "failed"
