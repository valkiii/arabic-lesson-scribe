# Arabic Lesson Scribe — SPEC (source of truth for all agents)

Goal: a Windows x64 desktop app for a NON-CODER. She installs ONE file (`ArabicLessonScribe-Setup.exe`
from GitHub Releases), opens it, drops in a phone recording of an Arabic lesson, gets a full
Arabic transcript, and can ask a small local LLM (Gemma 4 E2B) for summary / vocabulary / Q&A.
Everything runs offline after first-run model download. Minimalist UI, Arabic-first (RTL).

Lessons from our earlier workshop (do NOT repeat): no .vbs/.bat launchers, no Python install on the
user's machine, no admin rights, no long paths (install to %LOCALAPPDATA%\ArabicLessonScribe), ship x64
(runs on Windows-on-ARM via emulation), no UPX, PyInstaller onedir (not onefile).

## Stack (pinned, verified 2026-11-10)
- Python 3.12. faster-whisper==1.2.1 (CTranslate2, PyAV decodes m4a/aac/mp3/wav; AMR must be tested, fallback = bundled ffmpeg.exe).
- UI: pywebview 6.2.1 (Edge WebView2) showing local HTML/CSS/JS (vanilla, no build step, no CDN, fonts bundled or system).
- LLM: llama.cpp prebuilt `llama-server.exe` from tag b12244, asset `llama-b12244-bin-win-cpu-x64.zip`
  (https://github.com/ggml-org/llama.cpp/releases/download/b12244/llama-b12244-bin-win-cpu-x64.zip).
  Model: https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF  file `gemma-4-E2B-it-Q4_0.gguf` (~2.84 GB, Apache-2.0, no login).
  Sampling: temperature 1.0, top_p 0.95, top_k 64. Text only (no mmproj). App talks to llama-server via its
  OpenAI-compatible HTTP API on 127.0.0.1 random free port; server started lazily, killed on exit.
- Whisper models (downloaded on first use to `%LOCALAPPDATA%\ArabicLessonScribe\models`):
  - "fast"  (default): mobiuslabsgmbh/faster-whisper-large-v3-turbo (~1.6 GB), int8
  - "best": Systran/faster-whisper-large-v3 (~3.1 GB), int8, optional download, much slower
  - "tiny-test": Systran/faster-whisper-tiny (for CI/smoke tests only)
- Downloads: plain httpx streaming with Range resume, progress callbacks, retries, size check. No huggingface_hub in the frozen app
  (set HF_HUB_DISABLE_XET irrelevant). Download URL pattern https://huggingface.co/<repo>/resolve/main/<file>.
  A whisper model = model.bin, config.json, tokenizer.json, vocabulary.json (+ preprocessor_config.json if present) — fetch the file list via
  https://huggingface.co/api/models/<repo> (siblings) once, fall back to a hardcoded list.
- Data dir: `%LOCALAPPDATA%\ArabicLessonScribe\` (models, bin, settings.json, logs). On non-Windows (dev on macOS) use `~/.arabic-lesson-scribe/`.
- Library (user-visible): `Documents\Arabic Lessons\<YYYY-MM-DD HH.MM title>\` containing `transcript.json`, `transcript.txt`, `transcript.md`, `notes.md`, and a copy of the audio is NOT made (store original path only).

## Repo layout
```
app/
  main.py                 entry: starts pywebview window, exposes Api
  api.py                  class Api (js_api) — contract below
  config.py               paths, model registry, pinned URLs
  downloader.py           httpx Range download + progress
  transcriber.py          faster-whisper wrapper, progress, cancel
  llm.py                  llama-server manager + chat helpers + prompts
  library.py              save/load/list/delete lessons, export
  prompts/                plain-text prompt files (summary.txt, vocab.txt, classify.txt, qa.txt)
  ui/                     index.html, style.css, app.js, (fonts/)
tests/                    pytest, runs on macOS+Windows, uses tiny model
build/
  ArabicLessonScribe.spec PyInstaller spec (onedir, noupx, console=False)
  installer.iss           Inno Setup (per-user, PrivilegesRequired=lowest, bundles WebView2 bootstrapper check + vc_redist check)
  fetch_llama.py          downloads/extracts llama-server + DLLs into app bin dir at build time (bundled in installer)
.github/workflows/build.yml   windows-latest: test, build, smoke-test frozen exe headless, upload Release asset on tag v*
README.md                 for the maintainer (valkiii) + a plain "Download" section
docs/FOR_THE_USER.md      1-page, screenshots-free, non-technical guide (what to click; SmartScreen "More info → Run anyway"; how long it takes)
requirements.txt, pyproject.toml
```
llama-server.exe + its DLLs are bundled inside the installer (small, ~30–60 MB); only the Gemma GGUF and Whisper models are downloaded at first run.

## Js API contract (window.pywebview.api.<method>, all return JSON-serialisable; long jobs are async via events)
Python pushes events to JS by calling `window.__onEvent(name, payload)` (evaluate_js). Events:
- `progress` {job: "download"|"transcribe"|"llm", id, pct (0-100 or null), message, eta_s?}
- `segment` {lesson_id, start, end, text}            (live transcript streaming)
- `done` {job, id, ok, error?}
Methods:
- `get_state()` -> {models:{fast:{installed,size_mb}, best:{...}, gemma:{...}}, lessons:[{id,title,date,duration_s,preview}], settings}
- `pick_audio()` -> opens native file dialog (mp3,m4a,aac,wav,ogg,opus,amr,3gp,mp4,flac,wma), returns path or null
- `start_transcription(path, {model:"fast"|"best", language:"ar"|"auto", title?})` -> {lesson_id}; auto-downloads missing model first (progress events); cancellable
- `cancel(job_id)`
- `get_lesson(lesson_id)` -> {meta, segments:[{start,end,text}], notes:{summary?, vocab?, qa:[{q,a}]}}
- `rename_lesson(id,title)`, `delete_lesson(id)`, `open_folder(id)`, `export_lesson(id, fmt:"txt"|"md"|"docx"?)` (docx optional; skip if no pure-python dep)
- `ai_summary(lesson_id)`, `ai_vocab(lesson_id)` (list of {arabic, transliteration?, meaning, note}), `ai_classify(lesson_id)`
  (per ~2-min chunk: vocabulary / grammar / dialogue / explanation / homework / other, to build a lesson outline), `ai_ask(lesson_id, question)`
  — all async via events, results persisted into notes and returned in `done`. UI language for AI answers = `settings.ui_lang` ("en" default, "it" supported); Arabic words always quoted in Arabic script.
- `set_settings({...})`, `get_log_path()`
Transcription defaults: language "ar" hint but allow "auto" (lessons mix Arabic with English/Italian explanations — expose a toggle "Lesson mixes languages" => language=None);
vad_filter=True, beam_size=5, condition_on_previous_text=False (reduces loops), word_timestamps False; initial_prompt a short Arabic phrase to bias to MSA/dialect-neutral punctuation. Progress = segment.end / duration. Must handle 1–2 h files, run in a worker thread, never block UI. Write partial transcript to disk as it streams so a crash loses nothing.
LLM: chunk long transcripts (map-reduce, ~3000 tokens per chunk, n_ctx 8192 to keep RAM low), strip nothing from Arabic text, use `--jinja`, `-c 8192`, `-t` = physical cores-1.
Be honest in UI: AI answers can be wrong; transcript is source of truth.

## UI (minimalist)
One window ~1000x700. Three states on one page: (1) Home: big drop zone "Drop a recording here or click to choose", list of past lessons;
(2) Working: single progress bar + live Arabic text appearing; (3) Lesson: transcript on the right/centre (RTL, large Naskh-friendly font, e.g. system "Segoe UI"/"Tahoma"/"Noto Naskh Arabic" fallback chain; click a segment shows timestamp),
side panel with buttons Summary / Vocabulary / Outline / Ask a question (chat box), Copy, Export, Open folder. Light/dark follows system. First-run: friendly screen explaining "one-time download of ~1.6 GB (speech) and ~2.8 GB (assistant, optional)" with Download button; AI features download Gemma lazily when first used. English UI strings in one dict at the top of app.js (Italian dict stub included). No emojis-heavy styling, lots of whitespace.

## Quality gates
- `pytest` passes on macOS (dev) and Windows (CI) using Systran/faster-whisper-tiny + a ≤20 s Arabic sample (generate via macOS `say -v Majed`/Tarik if available, or commit a small CC0 clip; check licence) — if no sample obtainable in dev, tests must skip cleanly.
- Headless smoke mode: `ArabicLessonScribe.exe --selftest <audio>` transcribes with tiny model, prints JSON, exit 0 — used by CI against the frozen exe.
- No telemetry. No network except model/binary download hosts (huggingface.co, github.com) and 127.0.0.1.

## Addendum: import, resume, lesson days (implemented)
- `import_transcript(path=None, title=None)` -> {lesson_id} (.txt .md .srt .vtt; dialog if no path; {lesson_id:null} if cancelled). Status "imported", no audio, start/end may be null.
- `resume_transcription(lesson_id, path=None)`: continues an interrupted/cancelled/failed lesson from the last saved segment (faster-whisper clip_timestamps, absolute timestamps, no VAD on the resumed part). Startup marks leftover "transcribing" lessons "interrupted". `get_lesson().meta.audio_ok` says if the recording is still there; pass `path` if it moved.
- Progress events may carry `elapsed_s` and `eta_s` (rate = audio seconds per wall second, shown after ~2 min of audio).
- Lesson days: a part's day is `meta.day` (default the audio/import file's modified time; fallback date[:10]).
  - `list_days()` -> [{date, title, parts, has_recap, recap_stale, has_quiz, total_duration_s}] newest first; `get_state()` also returns `days`.
  - `get_day(date)` -> {date, title, parts, segments_by_part:{lesson_id:[segments]}, notes:{recap, quiz}}.
  - `set_lesson_date(lesson_id, 'YYYY-MM-DD')` moves a part (folders unchanged) and marks affected recaps stale.
  - Day notes live in `<library>/_days/YYYY-MM-DD.json` (recap, quiz with marks and history), never in part folders.
  - `ai_day_recap(date)` -> {job_id:"recap:DATE"}; `ai_day_quiz(date, {more})` -> {job_id:"quiz:DATE"} or {job_id:null, cached:true}. Both finish with `done` {job:"llm", kind, date, ok, result}. Recap = map-reduce over all parts (JSON schema: topic, taught, focus, vocab, grammar, homework, unclear_note); quiz = exactly 10 validated, de-duplicated questions {id,type,question,options?,answer,explanation,source_hint}; "more" avoids earlier questions.
  - `set_quiz_mark(date, question_id, 'right'|'wrong'|null)`; `export_day(date, fmt='md'|'html', with_answers=True, what='all'|'recap'|'quiz')` -> {path}; `open_file(path)` (library files only).
  - settings.auto_recap (default true): when a part finishes or is imported and the assistant is already installed, the day recap is (re)made automatically; never auto-downloads the 2.8 GB model.
