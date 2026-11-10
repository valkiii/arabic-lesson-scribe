"""Download the pinned llama.cpp Windows CPU build and unpack llama-server into bin/.

Usage:  python build/fetch_llama.py [--dest bin]

Note: in recent llama.cpp builds llama-server.exe is a tiny launcher (~10 KB)
that loads llama-server-impl.dll, llama.dll, ggml*.dll, etc. So ALL .dll files
from the zip are required, not just the exe. Other tools (llama-cli, bench...)
are skipped to keep the installer small.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

TAG = "b12244"
ASSET = f"llama-{TAG}-bin-win-cpu-x64.zip"
URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG}/{ASSET}"
# SHA256 of the asset as downloaded on 2026-11-10. Empty string disables the check.
EXPECTED_SHA256 = "318f11fadcbc3a86541ec55d9930cc76646c6b8d2ff18798c8477e9ff0dc452a"


def fail(msg: str) -> "None":
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def download(url: str) -> bytes:
    last = None
    for attempt in range(1, 4):
        try:
            print(f"Downloading {url} (attempt {attempt})")
            req = urllib.request.Request(url, headers={"User-Agent": "fetch-llama"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  failed: {e}", file=sys.stderr)
    fail(f"could not download {url}: {last}")


def main() -> None:
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parent.parent
    ap.add_argument("--dest", default=str(root / "bin"))
    dest = Path(ap.parse_args().dest)

    data = download(URL)
    digest = hashlib.sha256(data).hexdigest()
    print(f"Downloaded {len(data) / 1e6:.1f} MB, sha256 {digest}")
    if EXPECTED_SHA256 and digest != EXPECTED_SHA256:
        fail(f"sha256 mismatch: expected {EXPECTED_SHA256}")

    dest.mkdir(parents=True, exist_ok=True)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        fail(f"bad zip: {e}")

    wanted = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = Path(info.filename).name
        low = name.lower()
        if low == "llama-server.exe" or low.endswith(".dll") or name.startswith("LICENSE"):
            wanted.append((info, name))

    for info, name in wanted:
        (dest / name).write_bytes(zf.read(info))

    server = dest / "llama-server.exe"
    if not server.is_file() or server.stat().st_size == 0:
        fail(f"llama-server.exe missing from {ASSET}; members: {zf.namelist()}")
    dlls = [p for p in dest.glob("*.dll")]
    if not any(p.name.lower() == "llama-server-impl.dll" for p in dlls) and not any(
        p.name.lower() == "llama.dll" for p in dlls
    ):
        fail("no llama DLLs extracted; llama-server.exe would not start")

    print(f"\nContents of {dest}:")
    total = 0
    for p in sorted(dest.iterdir()):
        total += p.stat().st_size
        print(f"  {p.name:40s} {p.stat().st_size:>12,d}")
    print(f"Total {total / 1e6:.1f} MB, llama.cpp {TAG}")


if __name__ == "__main__":
    main()
