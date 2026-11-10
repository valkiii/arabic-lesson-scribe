"""Parse an existing transcript (.txt, .md, .srt, .vtt) into segments [{start,end,text}].

start/end are None when the file carries no timestamps.
"""
from __future__ import annotations

import re
from pathlib import Path

TRANSCRIPT_EXTS = ("txt", "md", "srt", "vtt")
MAX_SEG_CHARS = 300

_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?")
_CUE = re.compile(r"^\s*((?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)")
_TAG = re.compile(r"<[^>]+>|\{\\[^}]*\}")
_MD_TS = re.compile(r"^\*\*\[((?:\d+:)?\d{1,2}:\d{2})\]\*\*\s*(.*)$")
_SENT_END = re.compile(r"(?<=[.!?؟۔…])\s+")


def read_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1256")  # legacy Windows Arabic
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _secs(ts: str) -> float:
    m = _TS.fullmatch(ts.strip())
    if not m:
        raise ValueError(ts)
    h, mi, s, frac = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + (int(frac.ljust(3, "0")) / 1000 if frac else 0)


def _clean_cue(lines: list[str]) -> str:
    return " ".join(_TAG.sub("", ln).strip() for ln in lines if ln.strip()).strip()


def parse_cues(text: str) -> list[dict]:
    """SRT and WebVTT: blocks with a 'a --> b' line followed by text lines."""
    segs: list[dict] = []
    cur: tuple[float, float] | None = None
    buf: list[str] = []

    def flush():
        nonlocal cur, buf
        if cur is not None:
            body = _clean_cue(buf)
            if body:
                segs.append({"start": round(cur[0], 2), "end": round(cur[1], 2), "text": body})
        cur, buf = None, []

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = _CUE.match(line)
        if m:
            flush()
            cur = (_secs(m.group(1)), _secs(m.group(2)))
        elif not line.strip():
            flush()
        elif cur is not None:
            buf.append(line)
        # else: header, cue index, NOTE/STYLE blocks: ignored
    flush()
    return segs


def _split_sentences(par: str) -> list[str]:
    """Break a long paragraph into pieces of at most MAX_SEG_CHARS, on sentence ends when possible."""
    par = " ".join(par.split())
    if len(par) <= MAX_SEG_CHARS:
        return [par] if par else []
    out: list[str] = []
    cur = ""
    for sent in _SENT_END.split(par):
        while len(sent) > MAX_SEG_CHARS:  # no punctuation: cut on a space
            cut = sent.rfind(" ", 0, MAX_SEG_CHARS)
            cut = cut if cut > 0 else MAX_SEG_CHARS
            if cur:
                out.append(cur)
                cur = ""
            out.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if cur and len(cur) + 1 + len(sent) > MAX_SEG_CHARS:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return [s for s in out if s]


def parse_plain(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # our own markdown export: **[mm:ss]** text
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    md = [(_MD_TS.match(ln)) for ln in lines if _MD_TS.match(ln)]
    if len(md) >= 2:
        segs = []
        for i, m in enumerate(md):
            start = float(_secs(m.group(1)))
            end = float(_secs(md[i + 1].group(1))) if i + 1 < len(md) else start
            segs.append({"start": start, "end": end, "text": m.group(2).strip()})
        return [s for s in segs if s["text"]]
    pars = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(pars) <= 1:  # no blank lines: every line is its own paragraph
        pars = [ln for ln in lines]
    segs = []
    for p in pars:
        p = re.sub(r"^#+\s*", "", p.strip())  # markdown headings
        for piece in _split_sentences(p.replace("\n", " ")):
            segs.append({"start": None, "end": None, "text": piece})
    return segs


def parse_transcript(path: str | Path) -> tuple[str, list[dict]]:
    """Returns (title, segments). Title is the file name without extension."""
    p = Path(path)
    if not p.is_file():
        raise ValueError("File not found")
    ext = p.suffix.lower().lstrip(".")
    if ext not in TRANSCRIPT_EXTS:
        raise ValueError("Unsupported file type (use .txt, .md, .srt or .vtt)")
    text = read_text(p)
    segs = parse_cues(text) if (ext in ("srt", "vtt") or "-->" in text) else []
    if not segs:
        segs = parse_plain(text)
    if not segs:
        raise ValueError("The file has no text")
    return p.stem, segs
