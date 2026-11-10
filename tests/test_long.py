"""Long-audio end-to-end checks (real tiny model). Skipped unless ALS_RUN_LONG=1.

  ALS_RUN_LONG=1 pytest tests/test_long.py -s            # 60 min stream test + 15 min cancel/resume test
  ALS_LONG_MINUTES=10 ALS_RESUME_MINUTES=6 ...            # shorter smoke run

The synthetic recording is built in pytest's tmp dir (never committed) by repeating the Arabic sample.
"""
import os
import resource
import sys
import threading
import time
import wave

import numpy as np
import pytest

from app import api as api_mod
from app import downloader

pytestmark = [pytest.mark.slow, pytest.mark.long]

if os.environ.get("ALS_RUN_LONG") != "1":
    pytest.skip("long test: set ALS_RUN_LONG=1", allow_module_level=True)

MINUTES = float(os.environ.get("ALS_LONG_MINUTES", "60"))
RESUME_MINUTES = float(os.environ.get("ALS_RESUME_MINUTES", "15"))


def peak_rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if sys.platform == "darwin" else r / 1024


def make_long_wav(sample, out, minutes: float, gap_s: float = 1.0) -> float:
    with wave.open(str(sample), "rb") as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        pcm = w.readframes(w.getnframes())
    silence = b"\x00" * int(rate * gap_s) * ch * width
    unit = pcm + silence
    target = int(minutes * 60 * rate) * ch * width
    with wave.open(str(out), "wb") as o:
        o.setnchannels(ch)
        o.setsampwidth(width)
        o.setframerate(rate)
        written = 0
        while written < target:
            o.writeframes(unit)
            written += len(unit)
    return written / (rate * ch * width)


@pytest.fixture(scope="module")
def tiny():
    try:
        return downloader.ensure_model("tiny-test")
    except Exception as e:  # offline
        pytest.skip(f"cannot get tiny model: {e}")


class Rec:
    def __init__(self):
        self.events = []
        self.t0 = time.monotonic()
        self.finished = threading.Event()
        self.seg_times = []

    def __call__(self, n, p):
        self.events.append((n, p))
        if n == "segment":
            self.seg_times.append(time.monotonic() - self.t0)
        if n == "done" and p["job"] == "transcribe":
            self.finished.set()

    def arm(self):
        self.finished.clear()
        self.t0 = time.monotonic()

    def segs(self):
        return [p for n, p in self.events if n == "segment"]

    def last_done(self):
        return [p for n, p in self.events if n == "done" and p["job"] == "transcribe"][-1]


def check_timeline(segs, duration):
    starts = [s["start"] for s in segs]
    assert starts == sorted(starts), "starts not monotonic"
    assert len({(s["start"], s["end"]) for s in segs}) == len(segs), "duplicate segments"
    prev_end = 0.0
    max_gap = 0.0
    for s in segs:
        assert s["end"] >= s["start"]
        assert s["start"] >= prev_end - 0.6, f"overlap at {s}"
        max_gap = max(max_gap, s["start"] - prev_end)
        prev_end = max(prev_end, s["end"])
    assert prev_end <= duration + 1.0
    return max_gap


def test_long_stream(arabic_sample, tiny, tmp_path):
    wav = tmp_path / "long.wav"
    dur = make_long_wav(arabic_sample, wav, MINUTES)
    rec = Rec()
    a = api_mod.Api(rec)
    rss0 = peak_rss_mb()
    lid = a.start_transcription(str(wav), {"model": "tiny-test", "language": "ar"})["lesson_id"]
    rec.arm()
    assert rec.finished.wait(MINUTES * 60 * 3), "timed out"
    wall = time.monotonic() - rec.t0
    assert rec.last_done()["ok"], rec.last_done()
    segs = rec.segs()
    t_get = time.monotonic()
    les = a.get_lesson(lid)
    get_s = time.monotonic() - t_get
    gap = check_timeline(les["segments"], dur)
    prog = [p for n, p in rec.events if n == "progress" and p["job"] == "transcribe"]
    etas = [p for p in prog if "eta_s" in p]
    print(f"\nLONG: audio {dur:.0f}s, wall {wall:.0f}s (x{dur / wall:.1f} realtime), segments {len(segs)}, "
          f"first segment at {rec.seg_times[0]:.1f}s, peak RSS {peak_rss_mb():.0f} MB (before {rss0:.0f}), "
          f"get_lesson {get_s * 1000:.0f} ms, max gap {gap:.1f}s, last end {les['segments'][-1]['end']:.0f}s, "
          f"eta events {len(etas)}")
    assert len(segs) == len(les["segments"]) > MINUTES
    assert rec.seg_times[0] < wall * 0.2, "segments did not stream"
    assert get_s < 1.0
    assert les["meta"]["status"] == "done"
    assert peak_rss_mb() < 4000  # measured ~2.7 GB for 60 min with tiny (whole file is decoded + featurised up front)


def test_cancel_then_resume(arabic_sample, tiny, tmp_path):
    wav = tmp_path / "mid.wav"
    dur = make_long_wav(arabic_sample, wav, RESUME_MINUTES)
    rec = Rec()
    a = api_mod.Api(rec)
    lid = a.start_transcription(str(wav), {"model": "tiny-test", "language": "ar"})["lesson_id"]
    rec.arm()
    t_end = time.monotonic() + RESUME_MINUTES * 60 * 3
    while (not rec.segs() or rec.segs()[-1]["end"] < dur * 0.4) and time.monotonic() < t_end:
        time.sleep(0.1)
    a.cancel(lid)
    assert rec.finished.wait(120)
    assert not rec.last_done()["ok"]
    part = a.get_lesson(lid)
    cut = part["segments"][-1]["end"]
    n_part = len(part["segments"])
    assert part["meta"]["status"] == "cancelled" and 0 < cut < dur and n_part >= 5
    # simulate an app restart: a new Api (status stays cancelled; resume works for interrupted too)
    rec.arm()
    a.resume_transcription(lid)
    assert rec.finished.wait(RESUME_MINUTES * 60 * 3)
    assert rec.last_done()["ok"]
    fin = a.get_lesson(lid)
    segs = fin["segments"]
    assert segs[:n_part] == part["segments"], "saved prefix changed"
    new = segs[n_part:]
    assert new and new[0]["start"] >= cut - 0.01, "resumed timestamps are not absolute"
    gap = check_timeline(segs, dur)
    print(f"\nRESUME: audio {dur:.0f}s, cancelled at {cut:.0f}s with {n_part} segs, final {len(segs)} segs, "
          f"first new start {new[0]['start']:.1f}s, max gap {gap:.1f}s, last end {segs[-1]['end']:.0f}s")
    # tiny sometimes emits nothing for a whole 30 s window (also in an uninterrupted run), so the global gap
    # bound is one window; the resume boundary itself must be seamless
    assert new[0]["start"] - cut < 2.0, "gap at the resume point"
    assert gap <= 31.0, "gap in transcript"
    assert segs[-1]["end"] > dur - 15
    assert fin["meta"]["status"] == "done"
