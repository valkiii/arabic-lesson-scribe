"""httpx streaming downloads with Range resume, retries, progress and cancel."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

import httpx

from . import config

log = logging.getLogger(__name__)

ProgressCb = Callable[[int, int | None, float], None]  # done_bytes, total_bytes, bytes_per_s


class DownloadCancelled(Exception):
    pass


def _client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0, read=60.0),
                        headers={"User-Agent": "ArabicLessonScribe/0.1"})


def download_file(url: str, dest: Path, progress: ProgressCb | None = None,
                  cancel: threading.Event | None = None, expected_size: int | None = None,
                  retries: int = 5, client: httpx.Client | None = None) -> Path:
    """Download url to dest (via dest.part, resumable). Returns dest."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    own = client is None
    client = client or _client()
    try:
        last_err: Exception | None = None
        for attempt in range(retries):
            if cancel and cancel.is_set():
                raise DownloadCancelled()
            try:
                _attempt(client, url, dest, part, progress, cancel, expected_size)
                return dest
            except DownloadCancelled:
                raise
            except (httpx.HTTPError, OSError, IOError) as e:
                last_err = e
                if isinstance(e, httpx.HTTPStatusError) and 400 <= e.response.status_code < 500 \
                        and e.response.status_code != 416:
                    raise
                log.warning("download attempt %d failed: %s", attempt + 1, e)
                time.sleep(min(2 ** attempt, 15) if attempt < retries - 1 else 0)
        raise RuntimeError(f"Download failed after {retries} attempts: {last_err}")
    finally:
        if own:
            client.close()


def _attempt(client, url, dest, part, progress, cancel, expected_size):
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with client.stream("GET", url, headers=headers) as r:
        if r.status_code == 416:  # already complete or bad part
            if expected_size and have == expected_size:
                part.replace(dest)
                return
            part.unlink(missing_ok=True)
            raise httpx.HTTPError("range not satisfiable, restarting")
        r.raise_for_status()
        if r.status_code == 206:
            cr = r.headers.get("content-range", "")
            total = int(cr.rsplit("/", 1)[-1]) if "/" in cr and cr.rsplit("/", 1)[-1].isdigit() else None
            mode = "ab"
        else:
            cl = r.headers.get("content-length")
            total = int(cl) if cl and cl.isdigit() else None
            have = 0
            mode = "wb"
        if total is None:
            total = expected_size
        done = have
        t0, last_emit, base = time.monotonic(), 0.0, have
        with open(part, mode) as f:
            for chunk in r.iter_bytes(1024 * 256):
                if cancel and cancel.is_set():
                    raise DownloadCancelled()
                f.write(chunk)
                done += len(chunk)
                now = time.monotonic()
                if progress and now - last_emit > 0.25:
                    last_emit = now
                    progress(done, total, (done - base) / max(now - t0, 1e-6))
    size = part.stat().st_size
    if total is not None and size != total:
        raise IOError(f"size mismatch: got {size}, expected {total}")
    if expected_size and size != expected_size:
        raise IOError(f"size mismatch: got {size}, expected {expected_size}")
    part.replace(dest)
    if progress:
        progress(size, size, 0.0)


def list_repo_files(repo: str, client: httpx.Client | None = None) -> list[str]:
    own = client is None
    client = client or _client()
    try:
        r = client.get(f"{config.HF_BASE}/api/models/{repo}")
        r.raise_for_status()
        names = [s["rfilename"] for s in r.json().get("siblings", [])]
        names = [n for n in names if n in config.WHISPER_FILES_FALLBACK]
        if all(req in names for req in config.WHISPER_REQUIRED):
            return names
    except Exception as e:  # noqa: BLE001
        log.warning("file list fetch failed (%s), using fallback", e)
    finally:
        if own:
            client.close()
    return list(config.WHISPER_FILES_FALLBACK)


def resolve_url(repo: str, filename: str) -> str:
    return f"{config.HF_BASE}/{repo}/resolve/main/{filename}"


def ensure_model(key: str, progress: Callable[[int | None, str, float | None], None] | None = None,
                 cancel: threading.Event | None = None) -> Path:
    """Make sure model `key` is installed; progress(pct, message, eta_s)."""
    m = config.MODELS[key]
    target = config.model_path(key)
    if config.is_installed(key):
        return target
    state = {"base": 0, "total_all": None}

    def emit(done_all: int, total_all: int | None, speed: float, label: str):
        if not progress:
            return
        pct = (done_all / total_all * 100) if total_all else None
        eta = ((total_all - done_all) / speed) if total_all and speed > 1 else None
        progress(pct, label, eta)

    if m["kind"] == "gguf":
        url = resolve_url(m["repo"], m["file"])
        download_file(url, target, cancel=cancel,
                      progress=lambda d, t, s: emit(d, t, s, f"Downloading {m['file']}"))
        return target

    files = list_repo_files(m["repo"])
    target.mkdir(parents=True, exist_ok=True)
    # Sizes via HEAD so overall percent is meaningful.
    sizes: dict[str, int] = {}
    with _client() as c:
        for fn in files:
            if (target / fn).is_file():
                sizes[fn] = (target / fn).stat().st_size
                continue
            try:
                h = c.head(resolve_url(m["repo"], fn))
                sizes[fn] = int(h.headers.get("content-length", 0))
            except Exception:  # noqa: BLE001
                sizes[fn] = 0
        total_all = sum(sizes.values()) or None
        done_prev = 0
        for fn in files:
            if (target / fn).is_file():
                done_prev += sizes[fn]
                continue
            base = done_prev
            try:
                download_file(resolve_url(m["repo"], fn), target / fn, cancel=cancel, client=c,
                              progress=lambda d, t, s, base=base: emit(base + d, total_all, s,
                                                                      f"Downloading {fn}"))
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and fn not in config.WHISPER_REQUIRED:
                    continue
                raise
            done_prev += sizes[fn]
    if not config.is_installed(key):
        raise RuntimeError(f"Model {key} incomplete after download")
    return target
