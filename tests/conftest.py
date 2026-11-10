import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tests" / ".cache"
CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("ALS_DATA_DIR", str(CACHE / "data"))  # persistent model cache between runs
sys.path.insert(0, str(ROOT))

SAMPLE_TEXT = "مرحبا بكم في درسنا اليوم. سنتعلم كلمات جديدة عن البيت والعائلة."


@pytest.fixture(autouse=True)
def _library(tmp_path, monkeypatch):
    monkeypatch.setenv("ALS_LIBRARY_DIR", str(tmp_path / "lib"))


@pytest.fixture(scope="session")
def arabic_sample() -> Path:
    """A short Arabic clip: tests/.cache/sample_ar.wav, or generated with macOS `say`, else skip."""
    wav = CACHE / "sample_ar.wav"
    if wav.exists():
        return wav
    if sys.platform == "darwin" and shutil.which("say") and shutil.which("afconvert"):
        aiff = CACHE / "sample_ar.aiff"
        r = subprocess.run(["say", "-v", "Majed", "-o", str(aiff), SAMPLE_TEXT], capture_output=True)
        if r.returncode == 0 and aiff.exists():
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(wav)], check=True)
            return wav
    pytest.skip("no Arabic sample available (put one at tests/.cache/sample_ar.wav)")


def pytest_collection_modifyitems(config, items):
    # tests marked "long" (an hour of audio) only run with ALS_RUN_LONG=1
    if os.environ.get("ALS_RUN_LONG") == "1":
        return
    skip = pytest.mark.skip(reason="long test: set ALS_RUN_LONG=1")
    for it in items:
        if "long" in it.keywords:
            it.add_marker(skip)
