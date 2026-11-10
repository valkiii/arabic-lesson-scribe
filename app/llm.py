"""llama-server manager, chunking, prompts and map-reduce helpers."""
from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import httpx

from . import config

log = logging.getLogger(__name__)

CHUNK_TOKENS = 3000
CHARS_PER_TOKEN = 2.0  # conservative: Arabic is token-heavy with Gemma (real ratio is about 2.5-3.5)
N_CTX = 8192
OUTLINE_CHUNK_TOKENS = 900  # ~2 minutes of speech; used when segments carry no timestamps
LANG_NAMES = {"en": "English", "it": "Italian"}
LABELS = ("vocabulary", "grammar", "dialogue", "explanation", "homework", "other")
SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 64}


def load_prompt(name: str) -> str:
    return (config.resource_dir() / "prompts" / f"{name}.txt").read_text(encoding="utf-8")


def render(name: str, ui_lang: str = "en", **kw) -> str:
    return load_prompt(name).format(lang_name=LANG_NAMES.get(ui_lang, "English"), **kw)


def est_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


def chunk_segments(segments: list[dict], max_tokens: int = CHUNK_TOKENS) -> list[list[dict]]:
    """Group consecutive segments into chunks of about max_tokens (never splits a segment
    unless one segment alone exceeds the budget, in which case it is split on spaces)."""
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    cur_t = 0
    for seg in segments:
        t = est_tokens(seg["text"])
        if t > max_tokens:
            if cur:
                chunks.append(cur)
                cur, cur_t = [], 0
            words, buf = seg["text"].split(), []
            for w in words:
                buf.append(w)
                if est_tokens(" ".join(buf)) >= max_tokens:
                    chunks.append([{**seg, "text": " ".join(buf)}])
                    buf = []
            if buf:
                cur, cur_t = [{**seg, "text": " ".join(buf)}], est_tokens(" ".join(buf))
            continue
        if cur and cur_t + t > max_tokens:
            chunks.append(cur)
            cur, cur_t = [], 0
        cur.append(seg)
        cur_t += t
    if cur:
        chunks.append(cur)
    return chunks


def chunk_by_time(segments: list[dict], window_s: float = 120.0) -> list[list[dict]]:
    """Group segments into ~window_s windows (for classification/outline).
    Without timestamps (imported plain text) fall back to token-sized groups."""
    if any(s.get("start") is None for s in segments):
        return chunk_segments(segments, OUTLINE_CHUNK_TOKENS)
    out: list[list[dict]] = []
    cur: list[dict] = []
    start = None
    for s in segments:
        if start is None:
            start = s["start"]
        if cur and s["start"] - start >= window_s:
            out.append(cur)
            cur, start = [], s["start"]
        cur.append(s)
    if cur:
        out.append(cur)
    return out


def chunk_text(chunk: list[dict]) -> str:
    return "\n".join(s["text"] for s in chunk)


def extract_json(text: str):
    """Pull the first JSON value out of a model reply (handles ``` fences and chatter)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = t.find(opener), t.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except ValueError:
                continue
    raise ValueError("no JSON in model reply")


# ---- day recap / quiz helpers ---------------------------------------------
_DIAC = re.compile(r"[\u064B-\u0652\u0670\u0640]")
_ARW = re.compile(r"[\u0600-\u06FF]+")
RECAP_CAPS = {"taught": 10, "focus": 7, "vocab": 25, "grammar": 8, "homework": 8}
QUIZ_TYPES = ("translate_from_arabic", "translate_to_arabic", "fill_blank", "multiple_choice", "grammar")
_TYPE_ALIASES = {"translate_ar_to_native": "translate_from_arabic", "translate_arabic": "translate_from_arabic",
                 "translate_from_ar": "translate_from_arabic", "translate_to_ar": "translate_to_arabic",
                 "translate_into_arabic": "translate_to_arabic", "fill_in_the_blank": "fill_blank",
                 "fill_in_blank": "fill_blank", "mcq": "multiple_choice", "multiple-choice": "multiple_choice"}


def norm_ar(text: str) -> str:
    t = _DIAC.sub("", str(text or ""))
    return t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")


def in_transcript(arabic: str, norm_text: str) -> bool:
    """True when every Arabic word (3+ letters, without the article) of `arabic` occurs in the transcript."""
    for w in _ARW.findall(norm_ar(arabic)):
        w = w[2:] if w.startswith("ال") and len(w) > 4 else w
        if len(w) >= 3 and w not in norm_text:
            return False
    return True


def extract_objects(text: str) -> list[dict]:
    """Repair helper: collect every complete JSON object in a (possibly truncated or chatty) reply."""
    dec, out, i = json.JSONDecoder(), [], 0
    while True:
        i = text.find("{", i)
        if i == -1:
            return out
        try:
            obj, end = dec.raw_decode(text, i)
            out.append(obj)
            i = end
        except ValueError:
            i += 1


def parse_list(text: str, key_hint: str = "questions") -> list[dict]:
    try:
        data = extract_json(text)
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [data])
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except ValueError:
        pass
    objs = extract_objects(text)
    if len(objs) == 1 and isinstance(objs[0].get(key_hint), list):
        return [d for d in objs[0][key_hint] if isinstance(d, dict)]
    return [o for o in objs if "question" in o]


def _strs(v, cap: int) -> list[str]:
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()][:cap]


def clean_recap(d: dict) -> dict:
    """Coerce a model reply into the recap schema."""
    out = {"topic": str(d.get("topic", "") or "").strip(),
           "taught": _strs(d.get("taught"), RECAP_CAPS["taught"]),
           "focus": _strs(d.get("focus"), RECAP_CAPS["focus"]),
           "grammar": _strs(d.get("grammar"), RECAP_CAPS["grammar"]),
           "homework": _strs(d.get("homework"), RECAP_CAPS["homework"]),
           "unclear_note": str(d.get("unclear_note", "") or "").strip(), "vocab": []}
    seen = set()
    for v in d.get("vocab") or []:
        if not isinstance(v, dict) or not str(v.get("arabic", "")).strip():
            continue
        ar = str(v["arabic"]).strip()
        if ar in seen:
            continue
        seen.add(ar)
        out["vocab"].append({"arabic": ar, "meaning": str(v.get("meaning", "") or "").strip(),
                             "transliteration": str(v.get("transliteration", "") or "").strip()})
    out["vocab"] = out["vocab"][:RECAP_CAPS["vocab"]]
    return out


def merge_recaps(parts: list[dict]) -> dict:
    """Deterministic merge (fallback when model reduction does not converge)."""
    out = {"topic": " ".join(p.get("topic", "") for p in parts[:2]).strip(), "unclear_note": "",
           "taught": [], "focus": [], "vocab": [], "grammar": [], "homework": []}
    for p in parts:
        for k in ("taught", "focus", "grammar", "homework"):
            out[k] += [x for x in p.get(k, []) if x not in out[k]]
        out["vocab"] += [v for v in p.get("vocab", []) if v["arabic"] not in {x["arabic"] for x in out["vocab"]}]
        out["unclear_note"] = out["unclear_note"] or p.get("unclear_note", "")
    return clean_recap(out)


def compact_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _fit(d: dict, max_tokens: int) -> str:
    """Serialise recap material, dropping the tail of the longest lists until it fits the budget."""
    d = {k: (list(v) if isinstance(v, list) else v) for k, v in d.items()}
    while est_tokens(compact_json(d)) > max_tokens:
        k = max((k for k in d if isinstance(d[k], list) and d[k]), key=lambda k: len(compact_json(d[k])), default=None)
        if k is None:
            break
        d[k].pop()
    return compact_json(d)


def validate_question(q: dict, norm_text: str | None = None) -> dict | None:
    """Return a clean question dict, or None if it is malformed / not grounded in the transcript."""
    if not isinstance(q, dict):
        return None
    typ = str(q.get("type", "")).strip().lower().replace(" ", "_")
    typ = _TYPE_ALIASES.get(typ, typ)
    question = str(q.get("question", "") or "").strip()
    answer = q.get("answer")
    if typ not in QUIZ_TYPES or not question or answer is None or not str(answer).strip():
        return None
    answer = str(answer).strip()
    out = {"type": typ, "question": question, "explanation": str(q.get("explanation", "") or "").strip(),
           "source_hint": str(q.get("source_hint", "") or "").strip()}
    if typ == "multiple_choice":
        opts = [str(o).strip() for o in (q.get("options") or []) if str(o).strip()]
        opts = list(dict.fromkeys(opts))
        if len(opts) != 4:
            return None
        if answer not in opts:
            m = re.fullmatch(r"\(?([A-Da-d1-4])[).:]?", answer)
            if m:
                c = m.group(1).upper()
                answer = opts["ABCD".index(c)] if c in "ABCD" else opts[int(c) - 1]
            else:
                hit = [o for o in opts if o.lower() == answer.lower()]
                if not hit:
                    return None
                answer = hit[0]
        out["options"] = opts
    if typ == "fill_blank" and "_" not in question and "…" not in question:
        return None
    out["answer"] = answer
    if norm_text is not None:
        # the Arabic the student is asked to know must come from the lesson
        arabic = answer if typ in ("translate_to_arabic", "fill_blank", "multiple_choice") else ""
        arabic += " " + (question if typ in ("translate_from_arabic", "fill_blank") else "")
        if not in_transcript(arabic, norm_text):
            return None
    return out


def question_key(text: str) -> str:
    return re.sub(r"[\W_]+", " ", norm_ar(text).lower()).strip()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LlmClient:
    """Talks to an OpenAI-compatible server; manages llama-server when base_url is None."""

    def __init__(self, base_url: str | None = None, model_path: Path | None = None):
        self.base_url = base_url
        self.model_path = model_path
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._owns = base_url is None
        if self._owns:
            atexit.register(self.stop)

    # server management
    def ensure_started(self, timeout: float = 180.0) -> str:
        with self._lock:
            if self.base_url and (not self._owns or (self._proc and self._proc.poll() is None)):
                return self.base_url
            exe = config.find_llama_server()
            if not exe:
                raise RuntimeError("llama-server not found (expected bundled with the app)")
            model = self.model_path or config.model_path("gemma")
            if not Path(model).is_file():
                raise RuntimeError("Assistant model not downloaded")
            port = _free_port()
            threads = max(1, (os.cpu_count() or 4) // 2 - 1)
            cmd = [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                   "-c", "8192", "-t", str(threads), "--jinja",
                   "--temp", "1.0", "--top-p", "0.95", "--top-k", "64"]
            kw: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "cwd": str(Path(exe).parent)}
            if sys.platform == "win32":
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            log.info("starting llama-server: %s", cmd)
            self._proc = subprocess.Popen(cmd, **kw)
            self.base_url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    self.base_url = None
                    raise RuntimeError("llama-server exited during startup")
                try:
                    if httpx.get(self.base_url + "/health", timeout=2).status_code == 200:
                        return self.base_url
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            self.stop()
            raise RuntimeError("llama-server did not become ready")

    def stop(self) -> None:
        p, self._proc = self._proc, None
        if self._owns:
            self.base_url = None
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()

    # chat
    def chat(self, prompt: str, max_tokens: int = 1500, cancel: threading.Event | None = None) -> str:
        if cancel and cancel.is_set():
            raise RuntimeError("cancelled")
        url = self.ensure_started()
        body = {"model": "gemma", "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "stream": False, **SAMPLING}
        last: Exception | None = None
        for attempt in range(2):
            try:
                r = httpx.post(url + "/v1/chat/completions", json=body, timeout=httpx.Timeout(600, connect=10))
                r.raise_for_status()
                return (r.json()["choices"][0]["message"]["content"] or "").strip()
            except (httpx.HTTPError, KeyError, ValueError) as e:
                last = e
                time.sleep(1)
        raise RuntimeError(f"LLM request failed: {last}")

    # tasks
    def summarize(self, segments: list[dict], ui_lang: str = "en",
                  progress: Callable[[float, str], None] | None = None,
                  cancel: threading.Event | None = None) -> str:
        chunks = chunk_segments(segments)
        if not chunks:
            return ""
        if len(chunks) == 1:
            return self.chat(render("summary", ui_lang, text=chunk_text(chunks[0])), cancel=cancel)
        parts = []
        for i, c in enumerate(chunks):
            if progress:
                progress(i / (len(chunks) + 1) * 100, f"Summarising part {i + 1} of {len(chunks)}")
            parts.append(self.chat(render("summary", ui_lang, text=chunk_text(c)), 700, cancel))
        # reduce, recursively if the partial summaries are themselves too long
        while True:
            joined = "\n\n---\n\n".join(parts)
            if est_tokens(joined) <= CHUNK_TOKENS or len(parts) <= 1:
                break
            groups, cur = [], []
            for p in parts:
                if cur and est_tokens("\n\n".join(cur + [p])) > CHUNK_TOKENS:
                    groups.append(cur)
                    cur = []
                cur.append(p)
            groups.append(cur)
            if len(groups) == len(parts):
                break
            parts = [self.chat(render("summary_reduce", ui_lang, text="\n\n---\n\n".join(g)), 700, cancel)
                     for g in groups]
        if progress:
            progress(95, "Combining")
        return self.chat(render("summary_reduce", ui_lang, text=joined), cancel=cancel)

    def vocab(self, segments: list[dict], ui_lang: str = "en",
              progress: Callable[[float, str], None] | None = None,
              cancel: threading.Event | None = None) -> list[dict]:
        chunks = chunk_segments(segments)
        items: list[dict] = []
        seen: set[str] = set()
        for i, c in enumerate(chunks):
            if progress:
                progress(i / max(len(chunks), 1) * 100, f"Vocabulary {i + 1} of {len(chunks)}")
            reply = self.chat(render("vocab", ui_lang, text=chunk_text(c)), 1500, cancel)
            try:
                data = extract_json(reply)
            except ValueError:
                log.warning("vocab chunk %d: unparsable reply", i)
                continue
            if isinstance(data, dict):
                data = next((v for v in data.values() if isinstance(v, list)), [])
            for it in data:
                if not isinstance(it, dict) or not it.get("arabic"):
                    continue
                key = str(it["arabic"]).strip()
                if key in seen:
                    continue
                seen.add(key)
                items.append({"arabic": key, "transliteration": str(it.get("transliteration", "") or ""),
                              "meaning": str(it.get("meaning", "") or ""), "note": str(it.get("note", "") or "")})
        return items

    def classify(self, segments: list[dict], ui_lang: str = "en", window_s: float = 120.0,
                 progress: Callable[[float, str], None] | None = None,
                 cancel: threading.Event | None = None) -> list[dict]:
        windows = chunk_by_time(segments, window_s)
        out = []
        idx = 0  # index of the window's first segment (lets the UI jump even without timestamps)
        for i, w in enumerate(windows):
            if progress:
                progress(i / max(len(windows), 1) * 100, f"Outline {i + 1} of {len(windows)}")
            text = chunk_text(w)
            max_chars = int(CHUNK_TOKENS * CHARS_PER_TOKEN)
            reply = self.chat(render("classify", ui_lang, text=text[:max_chars]), 200, cancel)
            label, topic = "other", ""
            try:
                d = extract_json(reply)
                if isinstance(d, dict):
                    label = str(d.get("label", "other")).strip().lower()
                    topic = str(d.get("topic", "") or "")
            except ValueError:
                pass
            if label not in LABELS:
                label = "other"
            out.append({"start": w[0].get("start"), "end": w[-1].get("end"), "index": idx,
                        "kind": label, "summary": topic})
            idx += len(w)
        return out

    def ask(self, segments: list[dict], question: str, ui_lang: str = "en",
            progress: Callable[[float, str], None] | None = None,
            cancel: threading.Event | None = None) -> str:
        chunks = chunk_segments(segments)
        if len(chunks) <= 1:
            return self.chat(render("qa", ui_lang, text=chunk_text(chunks[0]) if chunks else "",
                                    question=question), cancel=cancel)
        notes = []
        for i, c in enumerate(chunks):
            if progress:
                progress(i / (len(chunks) + 1) * 100, f"Reading part {i + 1} of {len(chunks)}")
            r = self.chat(render("qa_extract", ui_lang, text=chunk_text(c), question=question), 500, cancel)
            if r.strip().upper().strip(".") != "NONE" and r.strip():
                notes.append(r)
        # keep the final context within budget
        text = "\n\n".join(notes) or "(nothing relevant found)"
        text = text[: int(CHUNK_TOKENS * CHARS_PER_TOKEN)]
        return self.chat(render("qa", ui_lang, text=text, question=question), cancel=cancel)

    # ---- day recap and quiz -------------------------------------------------
    def _chat_json(self, prompt: str, max_tokens: int, cancel) -> dict:
        last = None
        for _ in range(2):  # one retry on unparsable output
            reply = self.chat(prompt, max_tokens, cancel)
            try:
                d = extract_json(reply)
                if isinstance(d, dict):
                    return d
            except ValueError as e:
                last = e
        raise RuntimeError(f"The assistant did not return usable notes ({last})")

    def day_recap(self, parts: list[list[dict]], ui_lang: str = "en",
                  progress: Callable[[float, str], None] | None = None,
                  cancel: threading.Event | None = None) -> dict:
        """Map-reduce over the transcripts of all parts of a day. Returns the cleaned recap schema."""
        chunks: list[list[dict]] = []
        for segs in parts:  # chunk each part on its own so a chunk never straddles two recordings
            chunks += chunk_segments(segs)
        if not chunks:
            raise ValueError("Nothing to summarise")
        norm_all = norm_ar(" ".join(chunk_text(c) for c in chunks))
        if len(chunks) == 1:
            res = clean_recap(self._chat_json(render("day_recap", ui_lang, text=chunk_text(chunks[0])), 1500, cancel))
        else:
            notes = []
            for i, c in enumerate(chunks):
                if progress:
                    progress(i / (len(chunks) + 2) * 100, f"Reading part {i + 1} of {len(chunks)}")
                notes.append(clean_recap(self._chat_json(render("day_recap", ui_lang, text=chunk_text(c)), 1200, cancel)))
            level = 0
            while len(notes) > 1:
                level += 1
                groups, cur = [], []
                for n in notes:
                    if cur and est_tokens(compact_json(cur + [n])) > CHUNK_TOKENS:
                        groups.append(cur)
                        cur = []
                    cur.append(n)
                groups.append(cur)
                if len(groups) >= len(notes) or level > 6:  # not shrinking: merge in code
                    notes = [merge_recaps(notes)]
                    break
                if progress:
                    progress(80 + min(level, 3) * 5, "Combining")
                notes = [clean_recap(self._chat_json(
                    render("day_recap_reduce", ui_lang, text=compact_json(g)), 1800, cancel)) if len(g) > 1 else g[0]
                    for g in groups]
            res = notes[0]
            if len(chunks) > 1 and progress:
                progress(95, "Combining")
        # drop vocabulary the transcript does not contain (the model must copy it, not invent it)
        res["vocab"] = [v for v in res["vocab"] if in_transcript(v["arabic"], norm_all)]
        return res

    def day_quiz(self, recap: dict, norm_text: str, ui_lang: str = "en", previous: list[str] | None = None,
                 count: int = 10, progress: Callable[[float, str], None] | None = None,
                 cancel: threading.Event | None = None, max_calls: int = 4) -> list[dict]:
        """Exactly `count` validated, de-duplicated questions (raises if the model cannot deliver)."""
        material = _fit({k: recap.get(k) for k in ("topic", "taught", "focus", "vocab", "grammar") if recap.get(k)}, 2400)
        seen = {question_key(p) for p in (previous or [])}
        good: list[dict] = []
        for call in range(max_calls):
            need = count - len(good)
            if need <= 0:
                break
            if progress:
                progress(call / max_calls * 100, "Writing questions")
            avoid_list = [p for p in (previous or [])] + [g["question"] for g in good]
            prev_txt = ""
            if avoid_list:
                lines, total = [], 0
                for a in reversed(avoid_list):  # most recent first, capped to keep the prompt small
                    a = a[:90]
                    if total + len(a) > 1200:
                        break
                    lines.append("- " + a)
                    total += len(a) + 2
                prev_txt = render("quiz_avoid", ui_lang, previous="\n".join(lines))
            prompt = render("quiz", ui_lang, count=need if call else count, avoid=prev_txt, text=material)
            reply = self.chat(prompt, 2600, cancel)
            for raw in parse_list(reply):
                q = validate_question(raw, norm_text)
                if not q:
                    continue
                k = question_key(q["question"])
                if k in seen:
                    continue
                seen.add(k)
                good.append(q)
        if len(good) < count:
            raise RuntimeError(f"The assistant could only make {len(good)} valid questions. Please try again.")
        good = good[:count]
        for q in good:
            q["id"] = "q" + hashlib.md5(question_key(q["question"]).encode("utf-8")).hexdigest()[:8]
        return good
