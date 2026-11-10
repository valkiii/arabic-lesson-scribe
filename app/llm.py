"""llama-server manager, chunking, prompts and map-reduce helpers."""
from __future__ import annotations

import atexit
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
CHARS_PER_TOKEN = 2.5  # conservative for Arabic
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
    """Group segments into ~window_s windows (for classification/outline)."""
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
            out.append({"start": w[0]["start"], "end": w[-1]["end"], "kind": label, "summary": topic})
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
        text = text[: int(CHUNK_TOKENS * CHARS_PER_TOKEN * 1.5)]
        return self.chat(render("qa", ui_lang, text=text, question=question), cancel=cancel)
