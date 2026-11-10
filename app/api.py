"""JS API exposed to the webview (window.pywebview.api.*). Events go out via window.__onEvent."""
from __future__ import annotations

import json
import os
import sys
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import config, dayexport, downloader, importer, langs, library, llm, power, recorder, transcriber

log = logging.getLogger(__name__)

AUDIO_EXTS = ("mp3", "m4a", "aac", "wav", "ogg", "opus", "amr", "3gp", "mp4", "flac", "wma")


MIN_ETA_AUDIO_S = 120.0   # need this much audio decoded in this run before trusting the rate
MIN_ETA_WALL_S = 20.0


def eta_for(start_at: float, cur: float | None, dur: float | None, t_decode0: float | None, now: float):
    """Seconds left, from rate = audio seconds per wall second over this run; None until enough data."""
    if not (cur and dur) or t_decode0 is None or cur >= dur:
        return None
    done, wall = cur - start_at, now - t_decode0
    if done < MIN_ETA_AUDIO_S or wall < MIN_ETA_WALL_S:
        return None
    return (dur - cur) / (done / wall)


class Api:
    def __init__(self, emit: Callable[[str, dict], None] | None = None):
        # Everything is underscore-prefixed so pywebview does not expose it to JS.
        self._window = None
        self._emit_fn = emit
        self._jobs: dict[str, threading.Event] = {}
        self._jobs_lock = threading.Lock()
        self._llm = llm.LlmClient()
        self._llm_lock = threading.Lock()
        self._rec: dict | None = None            # {rec: Recorder, lesson_id, done: bool}
        self._rec_lock = threading.Lock()
        self._rec_factory = None                 # tests inject a fake microphone stream factory here
        self._sys_factory = None                 # ... and a fake computer-sound (loopback) factory here
        try:
            n = library.recover_interrupted()
            if n:
                log.info("marked %d lesson(s) as interrupted", n)
        except Exception:  # noqa: BLE001
            log.exception("recover_interrupted failed")

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

    def _progress(self, job: str, id_: str, pct, message: str, eta_s=None, elapsed_s=None) -> None:
        p = {"job": job, "id": id_, "pct": None if pct is None else round(pct, 1), "message": message}
        if eta_s is not None:
            p["eta_s"] = int(eta_s)
        if elapsed_s is not None:
            p["elapsed_s"] = int(elapsed_s)
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
                  for k in ("fast", "best", "hebrew", "gemma")}
        return {"models": models, "lessons": library.list_lessons(), "days": library.list_days(),
                "settings": config.load_settings()}

    def set_settings(self, settings: dict) -> dict:
        return config.save_settings(settings or {})

    def get_log_path(self) -> str:
        return str(config.log_path())

    def pick_audio(self):
        return self._pick_file("Audio files", AUDIO_EXTS)

    def _pick_file(self, label: str, exts) -> str | None:
        if self._window is None:
            return None
        import webview
        types = (f"{label} ({';'.join('*.' + e for e in exts)})", "All files (*.*)")
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
        st = config.load_settings()
        model = opts.get("model") or st.get("model", "fast")
        if model not in ("fast", "best", "tiny-test", "hebrew"):
            raise ValueError("Unknown model")
        # per-recording choices win over the saved settings; "language" is the older name for "mode"
        mode = opts.get("language") or opts.get("mode") or st.get("mode", "auto")
        spoken = langs.norm_spoken(opts.get("spoken_languages") or st.get("spoken_languages"))
        dialect = langs.norm_dialect(opts.get("arabic_dialect") or st.get("arabic_dialect"))
        plan = langs.resolve(spoken, mode, dialect)
        self._check_model_languages(model, plan)
        language = "auto" if plan["kind"] == "auto" else plan["languages"][0]
        lang_plan = {"spoken_languages": spoken, "arabic_dialect": dialect, "mode": langs.norm_mode(mode)}
        recorded = library.file_mtime(path)
        if opts.get("date"):  # explicit 'YYYY-MM-DD' wins; keep the file's time of day
            day = library.parse_day(opts["date"])
            tod = (recorded or datetime.now()).time()
            recorded = datetime.strptime(day, "%Y-%m-%d").replace(hour=tod.hour, minute=tod.minute, second=tod.second)
        lid = library.create_lesson(opts.get("title"), path, None if language == "auto" else language, model,
                                    recorded, lang_plan)
        cancel = self._register(lid)
        self._spawn(self._transcribe_job, lid, path, model, plan, cancel)
        return {"lesson_id": lid}

    @staticmethod
    def _check_model_languages(model: str, plan: dict) -> None:
        only = config.MODELS.get(model, {}).get("only_languages")
        if only and plan["languages"] != only:
            raise ValueError("This model was trained for one language and gets worse at the others. "
                             "Use it only when that language is the only one of the lesson.")

    @staticmethod
    def _plan_from_meta(meta: dict) -> dict:
        """The language plan of a stored lesson (older lessons only have meta.language)."""
        if meta.get("mode") or meta.get("spoken_languages"):
            return langs.resolve(meta.get("spoken_languages"), meta.get("mode", "auto"), meta.get("arabic_dialect"))
        lang = meta.get("language")
        if lang in langs.SUPPORTED:
            return langs.resolve([lang], lang)
        return langs.resolve(langs.DEFAULT_SPOKEN, "auto")

    def resume_transcription(self, lesson_id: str, path: str | None = None) -> dict:
        """Continue an interrupted/cancelled/failed transcription from the last saved segment.
        Pass path when the original recording moved (see meta.audio_ok in get_lesson)."""
        lesson = library.get_lesson(lesson_id)
        meta = lesson["meta"]
        if meta.get("status") in ("done", "imported"):
            raise ValueError("This lesson is already complete")
        with self._jobs_lock:
            if lesson_id in self._jobs:
                raise ValueError("This lesson is already being transcribed")
        audio = path or meta.get("audio_path")
        if not audio or not Path(audio).is_file():
            raise ValueError("AUDIO_MISSING: the original recording was not found")
        if path:
            library.update_meta(lesson_id, audio_path=str(path))
        model = meta.get("model") or config.load_settings().get("model", "fast")
        plan = self._plan_from_meta(meta)
        library.update_meta(lesson_id, status="transcribing")
        cancel = self._register(lesson_id)
        self._spawn(self._transcribe_job, lesson_id, str(audio), model, plan, cancel, True)
        return {"lesson_id": lesson_id}

    def _transcribe_job(self, lid: str, path: str, model: str, plan: dict, cancel: threading.Event,
                        resume: bool = False) -> None:
        with power.keep_awake():
            self._transcribe_body(lid, path, model, plan, cancel, resume)

    def _transcribe_body(self, lid, path, model, plan, cancel, resume) -> None:
        try:
            self._download_with_events(model, cancel)
            existing = library.partial_segments(lid) if resume else []
            start_at = existing[-1]["end"] if existing else 0.0
            self._progress("transcribe", lid, None, "Loading speech model")
            t_job = time.monotonic()
            clock = {"t": None, "dur_saved": False}  # t = when real decoding started

            def on_status(st):
                if st == "decoding":
                    clock["t"] = time.monotonic()
                    self._progress("transcribe", lid, None, "Transcribing", elapsed_s=clock["t"] - t_job)

            def on_seg(seg):
                library.append_segment(lid, seg)
                self._emit("segment", {"lesson_id": lid, **seg})

            def on_prog(pct, cur, dur):
                now = time.monotonic()
                if dur and not clock["dur_saved"]:
                    clock["dur_saved"] = True
                    library.update_meta(lid, duration_s=round(dur, 1))
                eta = eta_for(start_at, cur, dur, clock["t"], now)
                self._progress("transcribe", lid, pct, "Transcribing", eta, now - t_job)

            language = "auto" if plan["kind"] == "auto" else plan["languages"][0]
            res = transcriber.transcribe(path, model, language, None, on_prog, cancel,
                                         start_at=start_at, on_status=on_status, languages=plan["languages"],
                                         dialect=plan["dialect"], on_lang=on_seg)
            segments = existing + res["segments"]
            library.finish_lesson(lid, segments, res["duration"], res["language"])
            self._unregister(lid)  # before "done", so the UI can restart this lesson right away
            self._done("transcribe", lid, True)
            self._after_part_added(lid)
        except (transcriber.Cancelled, downloader.DownloadCancelled):
            library.mark_failed(lid, "cancelled")
            self._unregister(lid)  # before "done", so the UI can restart this lesson right away
            self._done("transcribe", lid, False, "cancelled")
        except Exception as e:  # noqa: BLE001
            log.exception("transcription failed")
            library.mark_failed(lid)
            self._unregister(lid)  # before "done", so the UI can restart this lesson right away
            self._done("transcribe", lid, False, str(e))
        finally:
            self._unregister(lid)

    # ---- recording from the microphone ----------------------------------
    def list_input_devices(self) -> list:
        return recorder.list_input_devices()

    def list_audio_sources(self) -> dict:
        """{microphones:[{id,name,default}], loopback_available, outputs:[{id,name,default}]}. Never raises.
        loopback_available is false off Windows; the UI then hides the computer-sound option."""
        if self._sys_factory is not None:   # tests: pretend loopback exists
            try:
                mics = recorder.list_input_devices()
            except Exception:  # noqa: BLE001
                mics = []
            return {"microphones": mics, "loopback_available": True,
                    "outputs": [{"id": 0, "name": "Fake output", "default": True}]}
        return recorder.list_audio_sources()

    def _rec_sources(self, opts: dict) -> dict:
        """Which sources to record. Defaults: computer sound and microphone where loopback exists, else microphone."""
        avail = self._sys_factory is not None or recorder.loopback_available()
        req = opts.get("sources") or {}
        sysw = bool(req["system"]) if "system" in req else avail
        micw = bool(req["mic"]) if "mic" in req else True
        if not (sysw or micw):
            raise ValueError("NO_SOURCE: switch on at least one source: the computer's sound or your microphone")
        if sysw and not avail:
            raise ValueError("LOOPBACK_UNAVAILABLE: recording the computer's sound is not available on this computer; "
                             "record with the microphone only")
        return {"system": sysw, "mic": micw}

    def start_recording(self, options: dict | None = None) -> dict:
        """Start recording from a microphone into a new lesson (a part of today's lesson day).
        Raises ValueError("NO_MIC: ..."), ("MIC_DENIED: ..."), ("MIC_ERROR: ..."), ("DISK_FULL: ...")."""
        opts = options or {}
        with self._rec_lock:
            if self._rec and not self._rec["done"]:
                raise ValueError("BUSY: a recording is already running")
            st = config.load_settings()
            spoken = langs.norm_spoken(opts.get("spoken_languages") or st.get("spoken_languages"))
            dialect = langs.norm_dialect(opts.get("arabic_dialect") or st.get("arabic_dialect"))
            mode = langs.norm_mode(opts.get("mode") or st.get("mode"))
            plan = langs.resolve(spoken, mode, dialect)
            model = opts.get("model") or st.get("model", "fast")
            if model not in ("fast", "best", "tiny-test", "hebrew"):
                model = "fast"
            try:
                self._check_model_languages(model, plan)
            except ValueError:
                model = "fast"
            language = None if plan["kind"] == "auto" else plan["languages"][0]
            now = datetime.now()
            recorded = now
            if opts.get("date"):
                day = library.parse_day(opts["date"])
                recorded = datetime.strptime(day, "%Y-%m-%d").replace(hour=now.hour, minute=now.minute, second=now.second)
            title = (opts.get("title") or "").strip() or f"Recording {now:%H.%M}"
            srcs = self._rec_sources(opts)
            lid = library.create_lesson(title, "", language, model, recorded,
                                        {"spoken_languages": spoken, "arabic_dialect": dialect, "mode": mode})
            wav = config.library_dir() / lid / "recording.wav"
            kind = "microphone" if not srcs["system"] else ("computer" if not srcs["mic"] else "computer+microphone")
            library.update_meta(lid, status="recording", audio_path=str(wav), source=kind, sources=srcs)

            def on_event(p):
                self._emit("record", {"recording_id": lid, "lesson_id": lid, **p})

            rec = recorder.Recorder(wav, opts.get("device_id"), on_event, lambda info: self._rec_finished(lid, info),
                                    stream_factory=self._rec_factory, sources=srcs,
                                    system_device=opts.get("system_device_id"), system_factory=self._sys_factory)
            try:
                rec.start()
            except recorder.RecorderError as e:
                library.delete_lesson(lid)
                raise ValueError(str(e)) from e
            self._rec = {"rec": rec, "lesson_id": lid, "done": False, "info": None}
            self._emit("record", {"recording_id": lid, "lesson_id": lid, "state": "recording", "elapsed_s": 0.0,
                                  "level": 0.0, "level_system": 0.0 if srcs["system"] else None,
                                  "level_mic": 0.0 if srcs["mic"] else None, "sources": srcs,
                                  "peak_clipping": False, "silent": False})
        return {"recording_id": lid, "lesson_id": lid}

    def _current_rec(self) -> dict:
        if not self._rec or self._rec["done"]:
            raise ValueError("No recording is running")
        return self._rec

    def pause_recording(self) -> dict:
        self._current_rec()["rec"].pause()
        return {"state": "paused"}

    def resume_recording(self) -> dict:
        self._current_rec()["rec"].resume()
        return {"state": "recording"}

    def stop_recording(self) -> dict:
        """Finish the recording. The lesson becomes status "recorded"; transcribe it with
        resume_transcription(lesson_id) (the UI offers 'Transcribe now' or 'Later')."""
        r = self._current_rec()
        info = r["rec"].stop()
        return self._finalize_recording(r["lesson_id"], info)

    def cancel_recording(self) -> dict:
        r = self._current_rec()
        r["rec"].cancel()
        r["done"] = True
        try:
            library.delete_lesson(r["lesson_id"])
        except (OSError, FileNotFoundError, ValueError):
            pass
        return {"cancelled": True}

    def _finalize_recording(self, lid: str, info: dict) -> dict:
        with self._rec_lock:
            if self._rec and self._rec["lesson_id"] == lid:
                if self._rec["done"] and self._rec.get("result"):
                    return self._rec["result"]
                self._rec["done"] = True
            dur = float(info.get("duration_s") or 0)
            status = "recorded" if dur >= 1.0 else "failed"
            library.update_meta(lid, status=status, duration_s=round(dur, 1))
            res = {"lesson_id": lid, "audio_path": info["path"], "duration_s": round(dur, 1),
                   "reason": info.get("reason", "stopped")}
            if info.get("message"):
                res["message"] = info["message"]
            if info.get("tracks"):
                res["tracks"] = info["tracks"]
            if self._rec and self._rec["lesson_id"] == lid:
                self._rec["result"] = res
        return res

    def _rec_finished(self, lid: str, info: dict) -> None:
        """The recorder stopped by itself (microphone lost, disk full): keep what was recorded."""
        try:
            res = self._finalize_recording(lid, info)
            self._emit("record", {"recording_id": lid, "lesson_id": lid, "state": "stopped", "final": True, **res})
        except Exception:  # noqa: BLE001
            log.exception("finishing the recording failed")

    # ---- import ---------------------------------------------------------
    def import_transcript(self, path: str | None = None, title: str | None = None) -> dict:
        """Create a lesson from an existing transcript (.txt .md .srt .vtt). No audio, status "imported".
        With no path, a native file dialog opens; returns {lesson_id: None} if the user cancels."""
        if not path:
            path = self._pick_file("Transcripts", importer.TRANSCRIPT_EXTS)
            if not path:
                return {"lesson_id": None}
        stem, segments = importer.parse_transcript(path)
        lid = library.create_imported((title or "").strip() or stem, segments, str(path),
                                      library.file_mtime(str(path)))
        self._after_part_added(lid)
        return {"lesson_id": lid}

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

    # ---- lesson days ----------------------------------------------------
    def list_days(self) -> list:
        return library.list_days()

    def get_day(self, date: str) -> dict:
        return library.get_day(date)

    def set_lesson_date(self, lesson_id: str, date: str) -> dict:
        r = library.set_lesson_date(lesson_id, date)
        for d in {r["day"], r["old_day"]}:
            if d:
                library.mark_day_stale(d)
        self._maybe_auto_recap(r["day"])
        return r

    def set_quiz_mark(self, date: str, question_id: str, mark: str | None) -> dict:
        """Record the student's own right/wrong mark for one question (saved per day, stays local)."""
        if mark not in ("right", "wrong", None):
            raise ValueError("mark must be right, wrong or null")
        n = library.load_day_notes(date)
        quiz = n.get("quiz")
        if not quiz:
            raise ValueError("No questions for this day")
        marks = quiz.setdefault("marks", {})
        if mark is None:
            marks.pop(question_id, None)
        else:
            marks[question_id] = mark
        library.save_day_notes(date, n)
        return {"marks": marks, "score": sum(1 for v in marks.values() if v == "right")}

    def export_day(self, date: str, fmt: str = "md", with_answers: bool = True, what: str = "all") -> dict:
        return {"path": dayexport.export_day(date, fmt, bool(with_answers), what)}

    def open_file(self, path: str) -> dict:
        """Open an exported file (only files inside the lessons library)."""
        p = Path(path).resolve()
        if config.library_dir().resolve() not in p.parents or not p.is_file():
            raise ValueError("Not a library file")
        if sys.platform == "win32":
            os.startfile(str(p))  # noqa: S606
        else:
            import subprocess
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(p)])
        return {"path": str(p)}

    def ai_day_recap(self, date: str) -> dict:
        return self._start_day_job("recap", library.parse_day(date))

    def ai_day_quiz(self, date: str, options: dict | None = None) -> dict:
        day = library.parse_day(date)
        more = bool((options or {}).get("more"))
        if (library.load_day_notes(day).get("quiz") or {}).get("questions") and not more:
            return {"job_id": None, "cached": True}
        return self._start_day_job("quiz", day)

    def _start_day_job(self, kind: str, day: str) -> dict:
        parts = library.day_parts(day)
        if not any(library.get_lesson(p["id"])["segments"] for p in parts):
            raise ValueError("This day has no transcript yet")
        job_id = f"{kind}:{day}"
        with self._jobs_lock:
            if job_id in self._jobs or f"recap:{day}" in self._jobs or f"quiz:{day}" in self._jobs:
                return {"job_id": job_id, "already_running": True}
            cancel = self._jobs[job_id] = threading.Event()
        self._spawn(self._day_job, kind, day, job_id, cancel)
        return {"job_id": job_id}

    def _after_part_added(self, lesson_id: str) -> None:
        """A recording finished or a transcript was imported: its day's recap is out of date."""
        try:
            day = library.lesson_day(library.get_lesson(lesson_id)["meta"])
            library.mark_day_stale(day)
            self._maybe_auto_recap(day)
        except Exception:  # noqa: BLE001
            log.exception("after_part_added failed")

    def _maybe_auto_recap(self, day: str) -> None:
        """Only with the assistant already installed: never starts a 2.8 GB download on its own."""
        if not config.load_settings().get("auto_recap", True) or not config.is_installed("gemma"):
            return
        recap = library.load_day_notes(day).get("recap")
        if recap and not recap.get("stale"):
            return
        # skip days that still have a part being transcribed; it will trigger this when it finishes
        if any(p.get("status") == "transcribing" for p in library.day_parts(day)):
            return
        try:
            self._start_day_job("recap", day)
        except ValueError:
            pass

    def _day_job(self, kind: str, day: str, job_id: str, cancel: threading.Event) -> None:
        with power.keep_awake():
            self._day_body(kind, day, job_id, cancel)

    def _day_body(self, kind, day, job_id, cancel) -> None:
        result, err = None, None
        try:
            self._download_with_events("gemma", cancel)
            self._progress("llm", job_id, None, "Starting assistant")
            lang = config.load_settings().get("ui_lang", "en")

            def prog(pct, msg):
                self._progress("llm", job_id, pct, msg)

            with self._llm_lock:
                self._llm.model_path = None
                parts = [library.get_lesson(p["id"]) for p in library.day_parts(day)]
                part_ids = [p["meta"]["id"] for p in parts]
                seg_lists = [p["segments"] for p in parts]
                notes = library.load_day_notes(day)
                recap = notes.get("recap")
                tgt = [c for c in langs.SUPPORTED
                       if any(c in langs.lesson_languages(p["segments"], p["meta"]) for p in parts)] or ["ar"]
                if kind == "recap" or not recap or recap.get("stale"):
                    recap = self._llm.day_recap(seg_lists, lang, prog, cancel, tgt)
                    recap.update(generated_at=datetime.now().isoformat(timespec="seconds"), lang=lang,
                                 parts=part_ids, stale=False)
                    notes = library.load_day_notes(day)
                    notes["recap"] = recap
                    library.save_day_notes(day, notes)
                result = recap
                if kind == "quiz":
                    quiz = notes.get("quiz") or {}
                    history = quiz.get("history", [q["question"] for q in quiz.get("questions", [])])
                    norm = llm.norm_ar(" ".join(s["text"] for sl in seg_lists for s in sl))
                    qs = self._llm.day_quiz(recap, norm, lang, history, 10, prog, cancel, languages=tgt)
                    notes = library.load_day_notes(day)
                    notes["quiz"] = {"questions": qs, "marks": {}, "round": int(quiz.get("round", 0)) + 1,
                                     "history": (history + [q["question"] for q in qs])[-80:],
                                     "generated_at": datetime.now().isoformat(timespec="seconds"), "lang": lang}
                    library.save_day_notes(day, notes)
                    result = notes["quiz"]
                if library.load_day_notes(day).get("recap") and [p["id"] for p in library.day_parts(day)] != part_ids:
                    library.mark_day_stale(day)  # a part was added while we were working
        except downloader.DownloadCancelled:
            err = "cancelled"
        except Exception as e:  # noqa: BLE001
            log.exception("day job failed")
            err = "cancelled" if cancel.is_set() else str(e)
        self._unregister(job_id)
        if err:
            self._done("llm", job_id, False, err, kind=kind, date=day)
        else:
            self._done("llm", job_id, True, kind=kind, date=day, result=result)

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
        with power.keep_awake():
            self._ai_body(kind, lesson_id, question, job_id, cancel)

    def _ai_body(self, kind, lesson_id, question, job_id, cancel) -> None:
        try:
            self._download_with_events("gemma", cancel)
            self._progress("llm", job_id, None, "Starting assistant")
            with self._llm_lock:
                self._llm.model_path = None
                les = library.get_lesson(lesson_id)
                segs = les["segments"]
                tgt = langs.lesson_languages(segs, les["meta"])
                lang = config.load_settings().get("ui_lang", "en")

                def prog(pct, msg):
                    self._progress("llm", job_id, pct, msg)

                notes = library.load_notes(lesson_id)
                if kind == "summary":
                    result = self._llm.summarize(segs, lang, prog, cancel, tgt)
                    notes["summary"] = result
                elif kind == "vocab":
                    result = self._llm.vocab(segs, lang, prog, cancel, tgt)
                    notes["vocab"] = result
                elif kind == "classify":
                    result = self._llm.classify(segs, lang, progress=prog, cancel=cancel, languages=tgt)
                    notes["outline"] = result
                else:
                    result = self._llm.ask(segs, question, lang, prog, cancel, tgt)
                    notes["qa"].append({"q": question, "a": result})
                library.save_notes(lesson_id, notes)
            self._unregister(job_id)
            self._done("llm", job_id, True, result=result, kind=kind, lesson_id=lesson_id)
        except (downloader.DownloadCancelled,):
            self._unregister(job_id)
            self._done("llm", job_id, False, "cancelled")
        except Exception as e:  # noqa: BLE001
            log.exception("ai job failed")
            self._unregister(job_id)
            self._done("llm", job_id, False, "cancelled" if cancel.is_set() else str(e))
        finally:
            self._unregister(job_id)

    def _shutdown(self) -> None:
        try:  # closing the window during a recording keeps what was recorded
            if self._rec and not self._rec["done"]:
                self.stop_recording()
        except Exception:  # noqa: BLE001
            log.exception("stopping the recording at exit failed")
        self._llm.stop()
