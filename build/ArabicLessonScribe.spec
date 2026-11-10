# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 6.22.x, onedir, no UPX, windowed.
# Build from repo root:  pyinstaller --noconfirm build/ArabicLessonScribe.spec
# Run `python build/fetch_llama.py` first so bin/llama-server.exe exists.
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # SPECPATH = build/

datas, binaries, hiddenimports = [], [], []
for pkg in ("ctranslate2", "faster_whisper", "onnxruntime", "av", "webview",
            "clr_loader", "pythonnet"):
    try:
        d, b, h = collect_all(pkg)
    except Exception as exc:  # package missing -> fail loudly for the core ones
        if pkg in ("clr_loader", "pythonnet"):
            print(f"WARNING: collect_all({pkg}) failed: {exc}")
            continue
        raise
    datas += d
    binaries += b
    hiddenimports += h

# pywebview talks to WebView2 through pythonnet (module name "clr")
hiddenimports += ["clr", "clr_loader", "pythonnet", "webview.platforms.edgechromium",
                  "webview.platforms.winforms", "tokenizers", "httpx", "h11", "certifi"]

# App data: UI and prompts keep their relative layout so config.py can find them
# next to the code (sys._MEIPASS/app/ui, sys._MEIPASS/app/prompts).
datas += [
    (os.path.join(ROOT, "app", "ui"), os.path.join("app", "ui")),
    (os.path.join(ROOT, "app", "prompts"), os.path.join("app", "prompts")),
]

# llama-server.exe + DLLs (from build/fetch_llama.py) -> <bundle>/bin
bin_dir = os.path.join(ROOT, "bin")
if not os.path.isfile(os.path.join(bin_dir, "llama-server.exe")):
    raise SystemExit("bin/llama-server.exe not found - run build/fetch_llama.py first")
datas += [(bin_dir, "bin")]

a = Analysis(
    [os.path.join(ROOT, "app", "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch", "tensorflow", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ArabicLessonScribe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ArabicLessonScribe",
)
