"""JS API exposed to the webview (window.pywebview.api.*). Events go out via window.__onEvent."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable

from . import config, downloader, library, llm, transcriber

log = logging.getLogger(__name__)

AUDIO_EXTS = ("mp3", "m4a", "aac", "wav", "ogg", "opus", "amr", "3gp", "mp4", "flac", "wma")


class Api:
    def __init__(self, emit: Callable[[str, dict], None] | None = None):
        # Everything is underscore-prefixed so pywebview does not expose it to JS.
        self._window = None
        self._emit_fn = emit
        self._jobs: dict[str, threading.Event] = {}
        self._jobs_lock = threading.Lock()
        self._llm = llm.LlmClient()
        self._llm_lock = threading.Lock()

    # ---- plumbing -------------------------------------------------------
    def _set_window(self, window) -> None:
        self._window = window

    def _emit(self, name: str, payload: dict) -> None:
        if self._emit_fn:
            self._emit_fn(name, payload)
            return
        if self._window is None:
            return
        try:
            self._window.evaluate_js(f"window.__onEvent && window.__onEvent({json.dumps(name)}, {json.dumps(payload)})")
        except Exception:  # noqa: BLE001
            log.exception("emit failed")

    def _progress(self, job: str, id_: str, pct, message: str, eta_s=None) -> None:
        p = {"job": job, "id": id_, "pct": None if pct is None else round(pct, 1), "message": message}
        if eta_s is not None:
            p["eta_s"] = int(eta_s)
        self._emit("progress", p)

    def _done(self, job: str, id_: str, ok: bool, error: str | None = None, **extra) -> None:
        p = {"job": job, "id": id_, "ok": ok, **extra}
        if error:
            p["error"] = error
        self._emit("done", p)

    def _register(self, job_id: str) -> threading.Event:
        ev = threading.Event()
        with self._jobs_lock:
            self._jobs[job_id] = ev
        return ev

    def _unregister(self, job_id: str) -> None:
        with self._jobs_lock:
            self._jobs.pop(job_id, None)

    def _spawn(self, fn, *a) -> None:
        threading.Thread(target=fn, args=a, daemon=True).start()

    def _download_with_events(self, key: str, cancel: threading.Event) -> None:
        if config.is_installed(key):
            return
        t0 = time.monotonic()

        def cb(pct, msg, eta):
            self._progress("download", key, pct, msg, eta)

        self._progress("download", key, 0, "Starting download")
        downloader.ensure_model(key, cb, cancel)
        log.info("downloaded %s in %.0fs", key, time.monotonic() - t0)
        self._done("download", key, True)

    # ---- state ----------------------------------------------------------
    def get_state(self) -> dict:
        models = {k: {"installed": config.is_installed(k), "size_mb": config.MODELS[k]["size_mb"]}
                  for k in ("fast", "best", "gemma")}
        return {"models": models, "lessons": library.list_lessons(), "settings": config.load_settings()}

    def set_settings(self, settings: dict) -> dict:
        return config.save_settings(settings or {})

    def get_log_path(self) -> str:
        return str(config.log_path())

    def pick_audio(self):
        if self._window is None:
            return None
        import webview
        types = (f"Audio files ({';'.join('*.' + e for e in AUDIO_EXTS)})", "All files (*.*)")
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        res = self._window.create_file_dialog(dialog, allow_multiple=False, file_types=types)
        return str(res[0]) if res else None

    def cancel(self, job_id: str) -> dict:
        with self._jobs_lock:
            ev = self._jobs.get(job_id)
        if ev:
            ev.set()
        return {"cancelled": bool(ev)}

    # ---- transcription --------------------------------------------------
    def start_transcription(self, path: str, options: dict | None = None) -> dict:
        opts = options or {}
        if not path or not Path(path).is_file():
            raise ValueError("File not found")
        model = opts.get("model") or config.load_settings().get("model", "fast")
        if model not in ("fast", "best", "tiny-test"):
            raise ValueError("Unknown model")
        language = opts.get("language") or ("auto" if config.load_settings().get("mixed_languages") else "ar")
        lid = library.create_lesson(opts.get("title"), path, None if language == "auto" else language, model)
        cancel = self._register(lid)
        self._spawn(self._transcribe_job, lid, path, model, language, cancel)
        return {"lesson_id": lid}

    def _transcribe_job(self, lid: str, path: str, model: str, language: str, cancel: threading.Event) -> None:
        try:
            self._download_with_events(model, cancel)
            self._progress("transcribe", lid, None, "Loading speech model")
            t0 = time.monotonic()

            def on_seg(s, e, text):
                seg = {"start": s, "end": e, "text": text}
                library.append_segment(lid, seg)
                self._emit("segment", {"lesson_id": lid, "start": s, "end": e, "text": text})

            def on_prog(pct, cur, dur):
                eta = None
                if pct and pct > 2:
                    el = time.monotonic() - t0
                    eta = el * (100 - pct) / pct
                self._progress("transcribe", lid, pct, "Transcribing", eta)

            res = transcriber.transcribe(path, model, language, on_seg, on_prog, cancel)
            library.finish_lesson(lid, res["segments"], res["duration"], res["language"])
            self._done("transcribe", lid, True)
        except (transcriber.Cancelled, downloader.DownloadCancelled):
            library.mark_failed(lid, "cancelled")
            self._done("transcribe", lid, False, "cancelled")
        except Exception as e:  # noqa: BLE001
            log.exception("transcription failed")
            library.mark_failed(lid)
            self._done("transcribe", lid, False, str(e))
        finally:
            self._unregister(lid)

    # ---- library --------------------------------------------------------
    def get_lesson(self, lesson_id: str) -> dict:
        return library.get_lesson(lesson_id)

    def rename_lesson(self, lesson_id: str, title: str) -> dict:
        return library.rename_lesson(lesson_id, title)

    def delete_lesson(self, lesson_id: str) -> dict:
        library.delete_lesson(lesson_id)
        return {"ok": True}

    def open_folder(self, lesson_id: str) -> dict:
        return {"path": library.open_folder(lesson_id)}

    def export_lesson(self, lesson_id: str, fmt: str = "txt") -> dict:
        return {"path": library.export_lesson(lesson_id, fmt)}

    # ---- AI -------------------------------------------------------------
    def ai_summary(self, lesson_id: str) -> dict:
        return self._start_ai("summary", lesson_id)

    def ai_vocab(self, lesson_id: str) -> dict:
        return self._start_ai("vocab", lesson_id)

    def ai_classify(self, lesson_id: str) -> dict:
        return self._start_ai("classify", lesson_id)

    def ai_ask(self, lesson_id: str, question: str) -> dict:
        if not (question or "").strip():
            raise ValueError("Empty question")
        return self._start_ai("ask", lesson_id, question.strip())

    def _start_ai(self, kind: str, lesson_id: str, question: str | None = None) -> dict:
        lesson = library.get_lesson(lesson_id)  # raises if missing
        if not lesson["segments"]:
            raise ValueError("Lesson has no transcript yet")
        job_id = f"{kind}:{lesson_id}"
        cancel = self._register(job_id)
        self._spawn(self._ai_job, kind, lesson_id, question, job_id, cancel)
        return {"job_id": job_id}

    def _ai_job(self, kind, lesson_id, question, job_id, cancel) -> None:
        try:
            self._download_with_events("gemma", cancel)
            self._progress("llm", job_id, None, "Starting assistant")
            with self._llm_lock:
                self._llm.model_path = None
                segs = library.get_lesson(lesson_id)["segments"]
                lang = config.load_settings().get("ui_lang", "en")

                def prog(pct, msg):
                    self._progress("llm", job_id, pct, msg)

                notes = library.load_notes(lesson_id)
                if kind == "summary":
                    result = self._llm.summarize(segs, lang, prog, cancel)
                    notes["summary"] = result
                elif kind == "vocab":
                    result = self._llm.vocab(segs, lang, prog, cancel)
                    notes["vocab"] = result
                elif kind == "classify":
                    result = self._llm.classify(segs, lang, progress=prog, cancel=cancel)
                    notes["outline"] = result
                else:
                    result = self._llm.ask(segs, question, lang, prog, cancel)
                    notes["qa"].append({"q": question, "a": result})
                library.save_notes(lesson_id, notes)
            self._done("llm", job_id, True, result=result, kind=kind, lesson_id=lesson_id)
        except (downloader.DownloadCancelled,):
            self._done("llm", job_id, False, "cancelled")
        except Exception as e:  # noqa: BLE001
            log.exception("ai job failed")
            self._done("llm", job_id, False, "cancelled" if cancel.is_set() else str(e))
        finally:
            self._unregister(job_id)

    def _shutdown(self) -> None:
        self._llm.stop()
