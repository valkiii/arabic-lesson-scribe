# Arabic Lesson Scribe

A Windows desktop app that turns a phone recording of an Arabic lesson into a full Arabic
transcript, and lets you ask a small local AI (Gemma 4 E2B) for a summary, vocabulary list,
lesson outline, or answers to questions. Everything runs on your own PC; the only network use
is the one-time download of the models (huggingface.co) and the installer prerequisites.

## Download

Get `ArabicLessonScribe-Setup.exe` from the latest
[GitHub Release](../../releases/latest). Run it; no administrator rights are needed.
The step-by-step guide for end users is in [docs/FOR_THE_USER.md](docs/FOR_THE_USER.md).

The installer is **unsigned**, so Windows SmartScreen may show "Windows protected your PC".
Click **More info**, then **Run anyway**. Some antivirus programs flag freshly built PyInstaller
apps as false positives. If that happens, check the SHA256 file published next to the installer
(`Get-FileHash .\ArabicLessonScribe-Setup.exe` in PowerShell), then either allow the file in your
antivirus or restore it from quarantine. The full source and the CI build log are public, so you
can also build it yourself.

## Maintainer notes

- Spec and contracts: [SPEC.md](SPEC.md).
- Stack: Python 3.12, faster-whisper, pywebview (WebView2), llama.cpp `llama-server` (tag b12244).
- Dev run (any OS): `pip install -r requirements.txt && python -m app.main`.
- Tests: `pytest` (uses the tiny Whisper model; skips cleanly if no sample is available).

### Local Windows build

```
pip install -r requirements.txt pyinstaller==6.22.3
python build/fetch_llama.py
pyinstaller --noconfirm --clean build/ArabicLessonScribe.spec
iscc /DMyAppVersion=0.1.0 build\installer.iss
```

Output: `dist\ArabicLessonScribe\` (the app folder) and `dist_installer\ArabicLessonScribe-Setup.exe`.

### CI (`.github/workflows/build.yml`)

On every push and pull request: install requirements, run pytest, fetch llama-server, build with
PyInstaller, run the frozen exe with `--selftest` on a generated Arabic sample, build the installer
with Inno Setup, compute SHA256 and upload both as a workflow artifact.

The selftest sample is generated in the workflow with the `edge-tts` package (Arabic voice
`ar-SA-HamedNeural`) so no third-party audio licence is involved. If that online service is down,
the job falls back to a generated tone, which still checks that the exe starts, decodes audio, loads
the model and prints JSON, but cannot check Arabic output.

### Release

```
git tag v0.1.0 && git push --tags
```

A tag starting with `v` makes the workflow create a GitHub Release with
`ArabicLessonScribe-Setup.exe` and `ArabicLessonScribe-Setup.exe.sha256` attached. The version
shown in the installer comes from the tag.

### Installer behaviour

Per-user install into `%LOCALAPPDATA%\ArabicLessonScribe` (no admin). Setup checks for the WebView2
runtime and the Visual C++ x64 redistributable, downloads and installs them if missing (the VC++
one may show a single Windows permission prompt), and continues with a warning if the download fails.

### Updating llama.cpp

Edit `TAG`, `ASSET` and `EXPECTED_SHA256` in `build/fetch_llama.py`. Note that `llama-server.exe` is a
small launcher that needs the accompanying DLLs, so the script copies all of them.
