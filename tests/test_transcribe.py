import json
import subprocess
import sys

import pytest

from app import api as api_mod
from app import downloader, transcriber, config

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def tiny():
    try:
        return downloader.ensure_model("tiny-test")
    except Exception as e:  # offline
        pytest.skip(f"cannot get tiny model: {e}")


def test_transcribe_tiny(arabic_sample, tiny):
    segs, prog = [], []
    r = transcriber.transcribe(arabic_sample, "tiny-test", "ar", lambda s, e, t: segs.append(t),
                               lambda p, c, d: prog.append(p), model_dir=tiny)
    assert r["segments"] and segs
    assert any("؀" <= ch <= "ۿ" for ch in r["segments"][0]["text"])
    assert prog[-1] == 100.0


def test_api_end_to_end(arabic_sample, tiny):
    import threading
    events = []
    done = threading.Event()

    def emit(n, p):
        events.append((n, p))
        if n == "done" and p["job"] == "transcribe":
            done.set()

    a = api_mod.Api(emit)
    lid = a.start_transcription(str(arabic_sample), {"model": "tiny-test", "language": "ar"})["lesson_id"]
    assert done.wait(120)
    d = [p for n, p in events if n == "done"][-1]
    assert d["ok"], d
    assert any(n == "segment" for n, _ in events)
    les = a.get_lesson(lid)
    assert les["segments"] and les["meta"]["status"] == "done"
    assert a.get_state()["lessons"][0]["id"] == lid


def test_selftest_cli(arabic_sample, tiny):
    r = subprocess.run([sys.executable, "-m", "app.main", "--selftest", str(arabic_sample)],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(config.resource_dir().parent))
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout.strip().splitlines()[-1])
    assert data["ok"] and data["text"]
