"""faster-whisper wrapper: streaming segments, progress, cancel."""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from . import config, langs

log = logging.getLogger(__name__)

INITIAL_PROMPT = langs.prompt_for("ar", "msa")  # kept for callers that import it


class Cancelled(Exception):
    pass


def cpu_threads() -> int:
    return max(1, (os.cpu_count() or 2) // 2)


def transcribe(path: str | Path, model_key: str = "fast", language: str | None = "ar",
               on_segment: Callable[[float, float, str], None] | None = None,
               on_progress: Callable[[float | None, float | None, float | None], None] | None = None,
               cancel: threading.Event | None = None,
               model_dir: str | Path | None = None,
               start_at: float = 0.0,
               on_status: Callable[[str], None] | None = None,
               languages: list[str] | None = None,
               dialect: str = langs.DEFAULT_DIALECT,
               on_lang: Callable[[dict], None] | None = None) -> dict:
    """Transcribe an audio file. Returns {segments:[{start,end,text,lang}], duration, language, languages}.

    language: a code ("ar", "he", "en", "fr") forces that language for the whole file (the fast path: one
    faster-whisper call, VAD on, no detection). None or "auto" detects the language of every speech window
    among `languages` only (default Arabic and Hebrew); a language outside that list can never be chosen.
    on_progress(pct, elapsed_audio_s, duration_s). start_at > 0 resumes: only audio from that second on is
    used and all returned timestamps are absolute. on_segment(start, end, text) is called for every segment
    as soon as it exists; on_lang(segment) (optional) gets the full segment including its language.
    on_status("loading") / ("decoding") marks the phases, so callers can time the real decoding rate.
    """
    from faster_whisper import WhisperModel  # heavy import, keep lazy

    auto = language in ("auto", "", None)
    spoken = langs.norm_spoken(languages) if languages else list(langs.DEFAULT_SPOKEN)
    if auto and len(spoken) == 1:
        auto, language = False, spoken[0]
    mdir = Path(model_dir) if model_dir else config.model_path(model_key)
    compute = config.MODELS.get(model_key, {}).get("compute_type", "int8")
    if on_status:
        on_status("loading")
    model = WhisperModel(str(mdir), device="cpu", compute_type=compute, cpu_threads=cpu_threads())
    if on_status:
        on_status("decoding")
    ctx = _Ctx(model, on_segment, on_progress, cancel, start_at or 0.0, dialect, on_lang)
    if auto:
        return _transcribe_auto(ctx, path, spoken)
    return _transcribe_forced(ctx, path, language)


class _Ctx:
    def __init__(self, model, on_segment, on_progress, cancel, start_at, dialect, on_lang):
        self.model, self.on_segment, self.on_progress, self.cancel = model, on_segment, on_progress, cancel
        self.start_at, self.dialect, self.on_lang = start_at, dialect, on_lang
        self.out: list[dict] = []
        self.duration = 0.0

    def emit(self, start, end, text, lang):
        seg = {"start": round(float(start), 2), "end": round(float(end), 2), "text": text, "lang": lang}
        if self.start_at and seg["end"] <= self.start_at:
            return  # defensive: never re-emit audio before the resume point
        self.out.append(seg)
        if self.on_segment:
            self.on_segment(seg["start"], seg["end"], text)
        if self.on_lang:
            self.on_lang(seg)
        if self.on_progress:
            pct = min(100.0, seg["end"] / self.duration * 100) if self.duration else None
            self.on_progress(pct, seg["end"], self.duration)

    def check_cancel(self):
        if self.cancel and self.cancel.is_set():
            raise Cancelled()


def _transcribe_forced(ctx: _Ctx, path, language: str) -> dict:
    """One language for the whole file: a single faster-whisper call (the original, fast path)."""
    resume = ctx.start_at > 0
    segs_iter, info = ctx.model.transcribe(
        str(path), language=language, beam_size=5, vad_filter=not resume,
        clip_timestamps=[float(ctx.start_at)] if resume else "0",
        condition_on_previous_text=False, word_timestamps=False,
        initial_prompt=langs.prompt_for(language, ctx.dialect),
    )
    ctx.duration = float(getattr(info, "duration", 0) or 0)
    for s in segs_iter:
        ctx.check_cancel()
        text = s.text.strip()
        if text:
            ctx.emit(s.start, s.end, text, language)
    if ctx.on_progress:
        ctx.on_progress(100.0, ctx.duration, ctx.duration)
    return {"segments": ctx.out, "duration": ctx.duration, "language": language,
            "languages": [language] if ctx.out else []}


def _transcribe_auto(ctx: _Ctx, path, spoken: list[str]) -> dict:
    """Per-window language detection restricted to `spoken`, then each run of windows is transcribed with
    its language forced and that language's prompt. See langs.iter_runs for the decisions."""
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    sr = 16000
    audio = decode_audio(str(path), sampling_rate=sr)
    total = len(audio) / sr
    ctx.duration = float(total)
    off = float(ctx.start_at)
    sub = audio[int(off * sr):] if off else audio
    ctx.check_cancel()
    # a one second pause is a good place for the language to change; 2 s (the default) would glue a short
    # question in another language onto the sentence before it
    chunks = get_speech_timestamps(sub, VadOptions(max_speech_duration_s=langs.MAX_WINDOW_S,
                                                   min_silence_duration_ms=1000))
    wins = langs.build_windows([(c["start"] / sr, c["end"] / sr) for c in chunks])
    log.info("auto language: %d speech windows among %s", len(wins), spoken)

    def detect_many(ws):
        ctx.check_cancel()
        a = np.concatenate([sub[int(x * sr):int(y * sr)] for x, y in ws])[:30 * sr]
        return langs.restrict_probs(ctx.model.detect_language(audio=a, language_detection_segments=1)[2], spoken)

    def detect_one(w):
        return detect_many([w])

    detect = langs.BlockDetector(wins, detect_many, detect_one)

    used: list[str] = []
    for ra, rb, lang in langs.iter_runs(wins, detect):
        ctx.check_cancel()
        piece = sub[int(ra * sr):int(rb * sr)]
        segs_iter, _info = ctx.model.transcribe(
            piece, language=lang, beam_size=5, vad_filter=True, condition_on_previous_text=False,
            word_timestamps=False, initial_prompt=langs.prompt_for(lang, ctx.dialect))
        for s in segs_iter:
            ctx.check_cancel()
            text = s.text.strip()
            if text:
                ctx.emit(off + ra + s.start, off + ra + s.end, text, lang)
                if lang not in used:
                    used.append(lang)
        if ctx.on_progress:  # windows without text still move the bar
            cur = max(off + rb, ctx.out[-1]["end"] if ctx.out else 0.0)  # never move backwards
            ctx.on_progress(min(100.0, cur / total * 100) if total else None, cur, total)
    log.info("auto language: %d detection passes for %d windows", detect.passes, len(wins))
    if ctx.on_progress:
        ctx.on_progress(100.0, total, total)
    used = [c for c in langs.SUPPORTED if c in used]
    return {"segments": ctx.out, "duration": ctx.duration, "language": used[0] if used else None,
            "languages": used}
