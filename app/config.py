"""Paths, model registry, pinned URLs and settings persistence."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "ArabicLessonScribe"
IS_WINDOWS = sys.platform == "win32"

LLAMA_TAG = "b12244"
LLAMA_ASSET = "llama-b12244-bin-win-cpu-x64.zip"
LLAMA_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/{LLAMA_ASSET}"

HF_BASE = "https://huggingface.co"

# kind "whisper" = directory of files; kind "gguf" = single file.
MODELS: dict[str, dict] = {
    "fast": {
        "kind": "whisper",
        "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "size_mb": 1600,
        "compute_type": "int8",
    },
    "best": {
        "kind": "whisper",
        "repo": "Systran/faster-whisper-large-v3",
        "size_mb": 3100,
        "compute_type": "int8",
    },
    "tiny-test": {
        "kind": "whisper",
        "repo": "Systran/faster-whisper-tiny",
        "size_mb": 75,
        "compute_type": "int8",
    },
    "gemma": {
        "kind": "gguf",
        "repo": "ggml-org/gemma-4-E2B-it-GGUF",
        "file": "gemma-4-E2B-it-Q4_0.gguf",
        "size_mb": 2840,
    },
}

WHISPER_FILES_FALLBACK = [
    "model.bin", "config.json", "tokenizer.json", "vocabulary.json", "vocabulary.txt",
    "preprocessor_config.json",
]
WHISPER_REQUIRED = ["model.bin", "config.json", "tokenizer.json"]

DEFAULT_SETTINGS = {
    "ui_lang": "en",
    "model": "fast",
    "mixed_languages": False,
}


def resource_dir() -> Path:
    """Directory holding bundled read-only resources (app/ package dir)."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "app"
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    override = os.environ.get("ALS_DATA_DIR")
    if override:
        p = Path(override)
    elif IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        p = Path(base) / APP_NAME
    else:
        p = Path.home() / ".arabic-lesson-scribe"
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_dir() -> Path:
    p = data_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def bin_dir() -> Path:
    p = data_dir() / "bin"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_path() -> Path:
    return logs_dir() / "app.log"


def library_dir() -> Path:
    override = os.environ.get("ALS_LIBRARY_DIR")
    if override:
        p = Path(override)
    else:
        docs = Path.home() / "Documents"
        p = docs / "Arabic Lessons"
    p.mkdir(parents=True, exist_ok=True)
    return p


def model_path(key: str) -> Path:
    """Local path of a model: a directory (whisper) or a file (gguf)."""
    m = MODELS[key]
    if m["kind"] == "gguf":
        return models_dir() / m["file"]
    return models_dir() / m["repo"].replace("/", "__")


def is_installed(key: str) -> bool:
    p = model_path(key)
    if MODELS[key]["kind"] == "gguf":
        return p.is_file() and p.stat().st_size > 1_000_000
    return p.is_dir() and all((p / f).is_file() for f in WHISPER_REQUIRED)


def find_llama_server() -> Path | None:
    """Locate llama-server: env override, bundled next to app, or data bin dir."""
    exe = "llama-server.exe" if IS_WINDOWS else "llama-server"
    env = os.environ.get("LLAMA_SERVER_PATH")
    if env and Path(env).is_file():
        return Path(env)
    cands = [resource_dir().parent / "bin" / exe, resource_dir() / "bin" / exe, bin_dir() / exe]
    if getattr(sys, "frozen", False):
        cands.insert(0, Path(sys.executable).parent / "bin" / exe)
    for c in cands:
        if c.is_file():
            return c
    return None


def _settings_file() -> Path:
    return data_dir() / "settings.json"


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    try:
        s.update(json.loads(_settings_file().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(updates: dict) -> dict:
    s = load_settings()
    for k, v in (updates or {}).items():
        if k in DEFAULT_SETTINGS:
            s[k] = v
    _settings_file().write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s
