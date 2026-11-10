"""Entry point: pywebview window, or `--selftest <audio>` headless mode."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

if __package__ in (None, ""):  # run as a script / frozen entry
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402


def setup_logging() -> None:
    handlers: list[logging.Handler] = []
    try:
        handlers.append(RotatingFileHandler(config.log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    if sys.stderr:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def index_html() -> Path:
    return config.resource_dir() / "ui" / "index.html"


def _emit_result(obj: dict) -> None:
    """Print JSON to real stdout even when frozen windowed (sys.stdout is None); also save to a file."""
    text = json.dumps(obj, ensure_ascii=False)
    try:
        (config.logs_dir() / "selftest.json").write_text(text, encoding="utf-8")
    except OSError:
        pass
    out = sys.stdout
    if out is None:
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.AttachConsole(-1)  # parent console, if any
            except Exception:  # noqa: BLE001
                pass
        try:
            out = os.fdopen(1, "w", encoding="utf-8", closefd=False)
        except OSError:
            return
    try:
        out.write(text + "\n")
        out.flush()
    except (OSError, ValueError, UnicodeEncodeError):
        try:
            os.write(1, (text + "\n").encode("utf-8"))
        except OSError:
            pass


def selftest(audio: str) -> int:
    from app import downloader, transcriber
    if not Path(audio).is_file():
        _emit_result({"ok": False, "error": f"file not found: {audio}"})
        return 2
    try:
        mdir = downloader.ensure_model("tiny-test")
        res = transcriber.transcribe(audio, "tiny-test", "ar", model_dir=mdir)
    except Exception as e:  # noqa: BLE001
        logging.exception("selftest failed")
        _emit_result({"ok": False, "error": str(e)})
        return 1
    _emit_result({"ok": True, "language": res["language"], "duration": res["duration"],
                  "segments": res["segments"], "text": " ".join(s["text"] for s in res["segments"])})
    return 0


def run_gui() -> int:
    import webview
    from app.api import Api

    api = Api()
    window = webview.create_window("Arabic Lesson Scribe", url=str(index_html()), js_api=api,
                                   width=1000, height=700, min_size=(720, 520))
    api._set_window(window)
    window.events.closed += api._shutdown
    webview.start()
    api._shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ArabicLessonScribe")
    ap.add_argument("--selftest", metavar="AUDIO", help="headless: transcribe AUDIO with the tiny model, print JSON")
    args = ap.parse_args(argv)
    setup_logging()
    if args.selftest:
        return selftest(args.selftest)
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
