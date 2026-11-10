"""Lesson storage under Documents/Arabic Lessons/<YYYY-MM-DD HH.MM title>/."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import config

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe(title: str) -> str:
    t = _BAD.sub("", title).strip().rstrip(". ")
    return t[:60] or "Lesson"


def _dir(lesson_id: str) -> Path:
    if _BAD.search(lesson_id) or lesson_id in ("", ".", ".."):
        raise ValueError("bad lesson id")
    d = config.library_dir() / lesson_id
    if not d.is_dir():
        raise FileNotFoundError(lesson_id)
    return d


def _write_json(p: Path, data) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def fmt_ts(sec: float) -> str:
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def create_lesson(title: str | None, audio_path: str, language: str | None, model: str) -> str:
    now = datetime.now()
    base = f"{now:%Y-%m-%d %H.%M} {_safe(title or Path(audio_path).stem)}"
    lid, n = base, 2
    while (config.library_dir() / lid).exists():
        lid = f"{base} ({n})"
        n += 1
    d = config.library_dir() / lid
    d.mkdir(parents=True)
    meta = {"id": lid, "title": (title or Path(audio_path).stem).strip(), "date": now.isoformat(timespec="seconds"),
            "audio_path": str(audio_path), "language": language, "model": model, "duration_s": 0,
            "status": "transcribing"}
    _write_json(d / "meta.json", meta)
    (d / "segments.partial.jsonl").write_text("", encoding="utf-8")
    return lid


def append_segment(lesson_id: str, seg: dict) -> None:
    with open(_dir(lesson_id) / "segments.partial.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(seg, ensure_ascii=False) + "\n")


def _read_partial(d: Path) -> list[dict]:
    p = d / "segments.partial.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def finish_lesson(lesson_id: str, segments: list[dict], duration: float, language: str | None) -> None:
    d = _dir(lesson_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    meta.update(duration_s=round(duration or (segments[-1]["end"] if segments else 0), 1),
                status="done", detected_language=language)
    _write_json(d / "meta.json", meta)
    _write_json(d / "transcript.json", {"meta": meta, "segments": segments})
    (d / "transcript.txt").write_text("\n".join(s["text"] for s in segments) + "\n", encoding="utf-8")
    (d / "transcript.md").write_text(
        f"# {meta['title']}\n\n" + "\n\n".join(f"**[{fmt_ts(s['start'])}]** {s['text']}" for s in segments) + "\n",
        encoding="utf-8")
    (d / "segments.partial.jsonl").unlink(missing_ok=True)
    save_notes(lesson_id, load_notes(lesson_id))


def mark_failed(lesson_id: str, status: str = "failed") -> None:
    try:
        d = _dir(lesson_id)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        meta["status"] = status
        _write_json(d / "meta.json", meta)
    except (OSError, ValueError):
        pass


def load_notes(lesson_id: str) -> dict:
    p = _dir(lesson_id) / "notes.json"
    try:
        n = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        n = {}
    n.setdefault("qa", [])
    return n


def save_notes(lesson_id: str, notes: dict) -> None:
    d = _dir(lesson_id)
    _write_json(d / "notes.json", notes)
    md = ["# Notes\n"]
    if notes.get("summary"):
        md.append("## Summary\n\n" + notes["summary"] + "\n")
    if notes.get("vocab"):
        md.append("## Vocabulary\n")
        for v in notes["vocab"]:
            line = f"- {v.get('arabic', '')}"
            if v.get("transliteration"):
                line += f" ({v['transliteration']})"
            line += f" - {v.get('meaning', '')}"
            if v.get("note"):
                line += f" ({v['note']})"
            md.append(line)
        md.append("")
    if notes.get("outline"):
        md.append("## Outline\n")
        for o in notes["outline"]:
            md.append(f"- [{fmt_ts(o['start'])}] {o.get('kind', '')}: {o.get('summary', '')}")
        md.append("")
    if notes.get("qa"):
        md.append("## Questions\n")
        for qa in notes["qa"]:
            md.append(f"**Q:** {qa['q']}\n\n{qa['a']}\n")
    (d / "notes.md").write_text("\n".join(md), encoding="utf-8")


def get_lesson(lesson_id: str) -> dict:
    d = _dir(lesson_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    tj = d / "transcript.json"
    if tj.exists():
        segs = json.loads(tj.read_text(encoding="utf-8")).get("segments", [])
    else:
        segs = _read_partial(d)
    return {"meta": meta, "segments": segs, "notes": load_notes(lesson_id)}


def list_lessons() -> list[dict]:
    out = []
    for d in sorted(config.library_dir().iterdir(), reverse=True):
        mp = d / "meta.json"
        if not mp.is_file():
            continue
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
            segs = json.loads((d / "transcript.json").read_text(encoding="utf-8"))["segments"] \
                if (d / "transcript.json").exists() else _read_partial(d)
        except (OSError, ValueError, KeyError):
            continue
        out.append({"id": meta["id"], "title": meta.get("title", d.name), "date": meta.get("date"),
                    "duration_s": meta.get("duration_s", 0), "status": meta.get("status"),
                    "preview": " ".join(s["text"] for s in segs[:3])[:140]})
    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return out


def rename_lesson(lesson_id: str, title: str) -> dict:
    d = _dir(lesson_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    meta["title"] = title.strip() or meta["title"]
    _write_json(d / "meta.json", meta)
    if (d / "transcript.json").exists():
        tj = json.loads((d / "transcript.json").read_text(encoding="utf-8"))
        tj["meta"] = meta
        _write_json(d / "transcript.json", tj)
    return {"id": lesson_id, "title": meta["title"]}


def delete_lesson(lesson_id: str) -> None:
    shutil.rmtree(_dir(lesson_id))


def open_folder(lesson_id: str) -> str:
    d = _dir(lesson_id)
    if sys.platform == "win32":
        import os
        os.startfile(str(d))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(d)])
    else:
        subprocess.Popen(["xdg-open", str(d)])
    return str(d)


def export_lesson(lesson_id: str, fmt: str = "txt") -> str:
    d = _dir(lesson_id)
    if fmt not in ("txt", "md"):
        raise ValueError("unsupported format (txt, md)")
    p = d / f"transcript.{fmt}"
    if not p.exists():
        raise FileNotFoundError("transcript not ready")
    return str(p)
