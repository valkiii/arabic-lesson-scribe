"""faster-whisper wrapper: streaming segments, progress, cancel."""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable

from . import config

log = logging.getLogger(__name__)

INITIAL_PROMPT = "مرحبا بكم في هذا الدرس. سنتعلم اليوم كلمات جديدة، وقواعد اللغة العربية."


class Cancelled(Exception):
    pass


def cpu_threads() -> int:
    return max(1, (os.cpu_count() or 2) // 2)


def transcribe(path: str | Path, model_key: str = "fast", language: str | None = "ar",
               on_segment: Callable[[float, float, str], None] | None = None,
               on_progress: Callable[[float | None, float | None, float | None], None] | None = None,
               cancel: threading.Event | None = None,
               model_dir: str | Path | None = None) -> dict:
    """Transcribe an audio file. Returns {segments:[{start,end,text}], duration, language}.

    on_progress(pct, elapsed_audio_s, duration_s). language None/"auto" = autodetect.
    """
    from faster_whisper import WhisperModel  # heavy import, keep lazy

    if language in ("auto", "", None):
        language = None
    mdir = Path(model_dir) if model_dir else config.model_path(model_key)
    compute = config.MODELS.get(model_key, {}).get("compute_type", "int8")
    model = WhisperModel(str(mdir), device="cpu", compute_type=compute, cpu_threads=cpu_threads())
    segs_iter, info = model.transcribe(
        str(path), language=language, beam_size=5, vad_filter=True,
        condition_on_previous_text=False, word_timestamps=False,
        initial_prompt=INITIAL_PROMPT if language in (None, "ar") else None,
    )
    duration = float(getattr(info, "duration", 0) or 0)
    out: list[dict] = []
    for s in segs_iter:
        if cancel and cancel.is_set():
            raise Cancelled()
        text = s.text.strip()
        if not text:
            continue
        seg = {"start": round(float(s.start), 2), "end": round(float(s.end), 2), "text": text}
        out.append(seg)
        if on_segment:
            on_segment(seg["start"], seg["end"], text)
        if on_progress:
            pct = min(100.0, seg["end"] / duration * 100) if duration else None
            on_progress(pct, seg["end"], duration)
    if on_progress:
        on_progress(100.0, duration, duration)
    return {"segments": out, "duration": duration, "language": getattr(info, "language", language)}
