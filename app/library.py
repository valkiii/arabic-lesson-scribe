"""Lesson storage under Documents/Arabic Lessons/<YYYY-MM-DD HH.MM title>/."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import config, langs

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


def fmt_ts(sec: float | None) -> str:
    if sec is None:
        return ""
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def file_mtime(path: str | None) -> datetime | None:
    """Local modification time of a file (phone recordings keep the recording time here)."""
    try:
        return datetime.fromtimestamp(Path(path).stat().st_mtime) if path else None
    except OSError:
        return None


def parse_day(day: str) -> str:
    return datetime.strptime(str(day), "%Y-%m-%d").strftime("%Y-%m-%d")


def lesson_day(meta: dict) -> str:
    return meta.get("day") or str(meta.get("date") or "")[:10]


def create_lesson(title: str | None, audio_path: str, language: str | None, model: str,
                  recorded: datetime | None = None, lang_plan: dict | None = None) -> str:
    """lang_plan: {spoken_languages, arabic_dialect, mode} as used for this recording (kept for resume)."""
    now = datetime.now()
    recorded = recorded or now
    base = f"{now:%Y-%m-%d %H.%M} {_safe(title or Path(audio_path).stem)}"
    lid, n = base, 2
    while (config.library_dir() / lid).exists():
        lid = f"{base} ({n})"
        n += 1
    d = config.library_dir() / lid
    d.mkdir(parents=True)
    meta = {"id": lid, "title": (title or Path(audio_path).stem).strip(), "date": recorded.isoformat(timespec="seconds"),
            "day": f"{recorded:%Y-%m-%d}", "created": now.isoformat(timespec="seconds"), "audio_path": str(audio_path), "language": language, "model": model, "duration_s": 0,
            "status": "transcribing"}
    if lang_plan:
        meta.update(spoken_languages=lang_plan["spoken_languages"], arabic_dialect=lang_plan["arabic_dialect"],
                    mode=lang_plan["mode"])
    _write_json(d / "meta.json", meta)
    (d / "segments.partial.jsonl").write_text("", encoding="utf-8")
    return lid


def create_imported(title: str, segments: list[dict], source: str | None = None,
                    recorded: datetime | None = None) -> str:
    """A lesson built from an existing transcript: no audio, status "imported"."""
    now = datetime.now()
    recorded = recorded or now
    title = (title or "Imported transcript").strip()
    base = f"{now:%Y-%m-%d %H.%M} {_safe(title)}"
    lid, n = base, 2
    while (config.library_dir() / lid).exists():
        lid = f"{base} ({n})"
        n += 1
    d = config.library_dir() / lid
    d.mkdir(parents=True)
    ends = [s["end"] for s in segments if s.get("end") is not None]
    meta = {"id": lid, "title": title, "date": recorded.isoformat(timespec="seconds"),
            "day": f"{recorded:%Y-%m-%d}", "created": now.isoformat(timespec="seconds"), "audio_path": None,
            "language": None, "model": None, "duration_s": round(max(ends), 1) if ends else 0,
            "status": "imported", "source_file": source,
            "preview": " ".join(s["text"] for s in segments[:3])[:140]}
    _write_json(d / "meta.json", meta)
    _write_transcript(d, meta, segments)
    save_notes(lid, load_notes(lid))
    return lid


def update_meta(lesson_id: str, **fields) -> dict:
    d = _dir(lesson_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    meta.update(fields)
    _write_json(d / "meta.json", meta)
    return meta


def append_segment(lesson_id: str, seg: dict) -> None:
    # open/append/close per segment: the data reaches the OS on every segment, so a crash loses at most one
    with open(_dir(lesson_id) / "segments.partial.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(seg, ensure_ascii=False) + "\n")
        f.flush()


def _read_partial(d: Path, limit: int | None = None) -> list[dict]:
    p = d / "segments.partial.jsonl"
    out: list[dict] = []
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue  # torn last line after a crash
                if limit and len(out) >= limit:
                    break
    return out


def partial_segments(lesson_id: str) -> list[dict]:
    return _read_partial(_dir(lesson_id))


def _write_transcript(d: Path, meta: dict, segments: list[dict]) -> None:
    _write_json(d / "transcript.json", {"meta": meta, "segments": segments})
    (d / "transcript.txt").write_text("\n".join(s["text"] for s in segments) + "\n", encoding="utf-8")
    lines = []
    for s in segments:
        ts = fmt_ts(s.get("start"))
        lines.append(f"**[{ts}]** {s['text']}" if ts else s["text"])
    (d / "transcript.md").write_text(f"# {meta['title']}\n\n" + "\n\n".join(lines) + "\n", encoding="utf-8")


def _recover_recording(d: Path, meta: dict) -> str:
    """Repair an unfinished recording; it becomes an interrupted lesson that can be transcribed."""
    from . import recorder
    wav = Path(meta.get("audio_path") or d / "recording.wav")
    try:
        dur = recorder.repair_wav(wav)
    except (OSError, ValueError):
        return "failed"
    if dur < 1.0:
        return "failed"
    meta["duration_s"] = round(dur, 1)
    meta["recovered"] = True
    return "interrupted"


def recover_interrupted() -> int:
    """At startup: lessons left in 'transcribing' (app closed or crashed) become 'interrupted'
    when they have partial segments, otherwise 'failed'. Returns how many were changed."""
    n = 0
    for d in config.library_dir().iterdir():
        mp = d / "meta.json"
        if not mp.is_file():
            continue
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
            if meta.get("status") == "recording":   # the app closed during a recording: repair the WAV
                meta["status"] = _recover_recording(d, meta)
                _write_json(mp, meta)
                n += 1
                continue
            if meta.get("status") != "transcribing":
                continue
            has = bool(_read_partial(d, 1))
            meta["status"] = "interrupted" if has else "failed"
            _write_json(mp, meta)
            n += 1
        except (OSError, ValueError):
            continue
    return n


def finish_lesson(lesson_id: str, segments: list[dict], duration: float, language: str | None) -> None:
    d = _dir(lesson_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    meta.update(duration_s=round(duration or (segments[-1]["end"] if segments else 0), 1),
                status="done", detected_language=language,
                languages=langs.lesson_languages(segments, meta) if segments else meta.get("languages", []),
                preview=" ".join(s["text"] for s in segments[:3])[:140])
    _write_json(d / "meta.json", meta)
    _write_transcript(d, meta, segments)
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
            ts = fmt_ts(o.get("start"))
            md.append(f"- {'[' + ts + '] ' if ts else ''}{o.get('kind', '')}: {o.get('summary', '')}")
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
    ap = meta.get("audio_path")
    meta["audio_ok"] = bool(ap and Path(ap).is_file())
    return {"meta": meta, "segments": segs, "notes": load_notes(lesson_id)}


def list_lessons() -> list[dict]:
    out = []
    for d in sorted(config.library_dir().iterdir(), reverse=True):
        mp = d / "meta.json"
        if not mp.is_file():
            continue
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
            if "preview" in meta:
                preview = meta["preview"]
            elif (d / "transcript.json").exists():
                segs = json.loads((d / "transcript.json").read_text(encoding="utf-8"))["segments"]
                preview = " ".join(s["text"] for s in segs[:3])[:140]
            else:
                preview = " ".join(s["text"] for s in _read_partial(d, 3))[:140]
        except (OSError, ValueError, KeyError):
            continue
        out.append({"id": meta["id"], "day": lesson_day(meta), "title": meta.get("title", d.name), "date": meta.get("date"),
                    "duration_s": meta.get("duration_s", 0), "status": meta.get("status"),
                    "preview": preview})
    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return out


def set_lesson_date(lesson_id: str, day: str) -> dict:
    """Move a recording to another lesson day (keeps its time of day and its folder)."""
    day = parse_day(day)
    d = _dir(lesson_id)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    old = lesson_day(meta)
    tod = str(meta.get("date") or "")[10:] or "T12:00:00"
    meta.update(day=day, date=f"{day}{tod}")
    _write_json(d / "meta.json", meta)
    if (d / "transcript.json").exists():
        tj = json.loads((d / "transcript.json").read_text(encoding="utf-8"))
        tj["meta"] = meta
        _write_json(d / "transcript.json", tj)
    return {"id": lesson_id, "day": day, "old_day": old}


# ---- lesson days -------------------------------------------------------------
_DAYNAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def day_title(day: str) -> str:
    dt = datetime.strptime(day, "%Y-%m-%d")
    return f"{_DAYNAMES[dt.weekday()]} {dt.day} {_MONTHS[dt.month - 1]}"


def _days_dir() -> Path:
    p = config.library_dir() / "_days"
    p.mkdir(exist_ok=True)
    return p


def load_day_notes(day: str) -> dict:
    day = parse_day(day)
    try:
        n = json.loads((_days_dir() / f"{day}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        n = {}
    return n


def save_day_notes(day: str, notes: dict) -> None:
    _write_json(_days_dir() / f"{parse_day(day)}.json", notes)


def mark_day_stale(day: str) -> bool:
    """A part was added/changed/moved: the day's recap no longer covers everything."""
    notes = load_day_notes(day)
    if notes.get("recap") and not notes["recap"].get("stale"):
        notes["recap"]["stale"] = True
        save_day_notes(day, notes)
        return True
    return False


def day_parts(day: str) -> list[dict]:
    """Lessons of that day, in recording order."""
    day = parse_day(day)
    parts = [l for l in list_lessons() if l.get("day") == day]
    parts.sort(key=lambda l: (l.get("date") or "", l["id"]))
    return parts


def list_days() -> list[dict]:
    by: dict[str, list[dict]] = {}
    for l in list_lessons():
        if l.get("day"):
            by.setdefault(l["day"], []).append(l)
    out = []
    for day in sorted(by, reverse=True):
        try:
            title = day_title(day)
        except ValueError:
            continue
        parts = sorted(by[day], key=lambda l: (l.get("date") or "", l["id"]))
        n = load_day_notes(day)
        out.append({"date": day, "title": title, "parts": parts,
                    "has_recap": bool(n.get("recap")), "recap_stale": bool((n.get("recap") or {}).get("stale")),
                    "has_quiz": bool((n.get("quiz") or {}).get("questions")),
                    "total_duration_s": round(sum(p.get("duration_s") or 0 for p in parts), 1)})
    return out


def get_day(day: str) -> dict:
    day = parse_day(day)
    parts = day_parts(day)
    seg_by = {}
    for p in parts:
        try:
            seg_by[p["id"]] = get_lesson(p["id"])["segments"]
        except (OSError, ValueError):
            seg_by[p["id"]] = []
    n = load_day_notes(day)
    return {"date": day, "title": day_title(day), "parts": parts, "segments_by_part": seg_by,
            "notes": {"recap": n.get("recap"), "quiz": n.get("quiz")}}


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
