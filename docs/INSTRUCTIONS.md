# Arabic Lesson Scribe: full instructions

Two audiences: Part A is for you (the person who sets this up and shares it), Part B is the step-by-step you can send to the person who will use it. Part C is troubleshooting for both.

## Part A. For you (maintainer)

### A1. What you are shipping
One file, `ArabicLessonScribe-Setup.exe`, built automatically by GitHub Actions on a Windows machine. It contains the app, the speech engine and the llama.cpp engine. The two big AI models are not inside it. They download on first use (speech about 1.6 GB, assistant about 2.8 GB).

### A2. First release (do this before sending anything to anybody)
1. Open the repo on GitHub, tab Actions. Check that the workflow "build" is enabled.
2. Create a test tag from the project folder: `git tag v0.1.0-test` then `git push origin v0.1.0-test`.
3. Watch the run in the Actions tab. It runs the tests, builds the app with PyInstaller, runs the built exe in selftest mode on a spoken Arabic sample, builds the installer and publishes a Release with the installer and its SHA256 file.
4. If a step is red, open it, copy the error and fix it. The most likely first-run failures are: a missing PyInstaller hidden import (pythonnet, clr, onnxruntime), an Inno Setup compile error, or the selftest not printing JSON. Nothing in the Windows build has been run before the first Actions run, so expect one or two iterations.
5. Download the installer from the Release on a real Windows 10 or 11 PC (ideally one that has never had Python), and go through Part B yourself. Only then send the link.

### A3. Testing checklist on Windows (about 1 hour)
- Install without admin rights. The app starts from the Start Menu.
- Choose a short Arabic recording from a phone (m4a). Check the text appears live and is saved.
- Try an AMR or 3gp file. If it fails to decode, tell me; the fallback is to bundle ffmpeg.
- Try a one-hour recording with the default model on the laptop she will use, plugged in. Note the time and the memory use in Task Manager. On the Mac the tiny model peaked at 2.7 GB of RAM for a one-hour file, and the turbo model will use more. If the laptop has 8 GB or less, this must be checked.
- Click Summary. The 2.8 GB assistant downloads. Then check the recap, the focus points and the 10 practice questions on real Arabic. The quality of Gemma 4 E2B on Arabic is not verified, so read the output critically.
- Close the app during a transcription, reopen, and use Continue transcription.
- Open an existing transcript (.txt, .srt) with "Have a transcript already? Open it".
- Uninstall from Windows Settings and confirm her lessons in Documents\Arabic Lessons stay.

### A4. Releasing an update
1. Change the code, run `pytest` locally.
2. `git tag v0.2.0` and `git push origin v0.2.0`. A tag starting with v builds and publishes a Release. Tags containing "test" should be marked pre-release.
3. She downloads the new Setup.exe and runs it over the old one. Her lessons and downloaded models stay (they live outside the install folder).

### A5. The Windows warning
The installer is not code-signed, so Windows SmartScreen shows "Windows protected your PC". The user clicks "More info", then "Run anyway". Some antivirus programs may flag it because PyInstaller apps are often misreported. Options: publish the SHA256 (done automatically), submit the file to Microsoft and the antivirus vendor as a false positive, or buy a code-signing certificate (the only real fix).

### A6. Updating the pinned versions
Everything is pinned on purpose: faster-whisper 1.2.1, av below 16 (newer breaks it), pywebview 6.2.1, PyInstaller 6.22.3, llama.cpp tag b12244 (in build/fetch_llama.py, with a SHA256). To update llama.cpp, change the tag and hash in that file, rebuild, and run the selftest and a real Gemma request.

### A7. Run it on your own machine (development)
- Mac or Windows, Python 3.12: create a venv, `pip install -r requirements.txt pytest`, then `python -m app.main`.
- Tests: `pytest` (quick). One-hour stress test: set `ALS_RUN_LONG=1` and run pytest.
- UI only, in a browser: `cd app/ui`, `python3 -m http.server 8000`, open `http://localhost:8000/index.html?mock=1`. This uses a fake backend with sample Arabic.
- Use a throwaway data folder: set `ALS_DATA_DIR` and `ALS_LIBRARY_DIR` so your real lessons and models are not touched.

### A7b. Recording: microphone and computer sound (maintainer notes)
- `app/recorder.py`. Microphone: `sounddevice` 0.5.6 (PortAudio inside its wheel), unchanged. Computer sound (WASAPI loopback): `PyAudioWPatch` 0.2.12.9 (Windows only, marker `sys_platform == "win32"` in requirements.txt and pyproject.toml). It was chosen over `soundcard` because it has a cp312 win_amd64 wheel (100 KB, no compiler), Apache-2.0, a release in 2026, no numpy dependency (soundcard needs cffi and numpy, and had numpy 2 breakage fixed only in recent releases), and loopback devices are plain input devices. Its PortAudio is separate from sounddevice's, so the two libraries do not interfere.
- Microphone only: the original path (samples written as they arrive). With computer sound: `Mixer` places every block on a wall-clock timeline using its arrival time. WASAPI loopback delivers NO data while nothing plays, so gaps longer than 0.25 s are filled with silence and both tracks stay exactly as long as the clock. Output lags the clock by 0.3 s so late blocks fit, then is flushed at stop. Small clock drift is absorbed by that buffer (a fast source drops its oldest audio above 0.8 s buffered). Resampling to 16 kHz is `PolyResampler`, a numpy polyphase windowed-sinc (no scipy, no soxr, nothing added to the install). Mixing: each source at gain 0.5 when both are on (cannot clip), gain 1 when alone. Files: `recording.wav` (the mix, used for transcription) and, when both sources are on, `system.wav` and `mic.wav`, same length and timeline. All three are written incrementally with repaired headers after a crash.
- Default output changed (headphones plugged in): checked every second; the stream is re-attached to the new default device and the UI is told (`notice_key: output_changed`). If that fails and the microphone is on, recording continues with the microphone and says so; if nothing is left, it stops, keeps the audio and sends a final event with `reason: device_lost`. An explicitly chosen output that disappears is retried the same way.
- API: `list_audio_sources()` returns microphones, `loopback_available`, outputs. `start_recording({sources:{system,mic}, system_device_id?, device_id?})`; defaults on Windows are both on, elsewhere microphone only. Events `record` carry `level_system`, `level_mic`, `sources`, optional `hint: "no_system_audio"` (computer sound silent for 20 s while the microphone is heard), optional `notice`/`notice_key`. Error codes: NO_MIC, MIC_DENIED, MIC_ERROR, NO_OUTPUT, LOOPBACK_DENIED, LOOPBACK_ERROR, LOOPBACK_UNAVAILABLE, NO_SOURCE, DISK_FULL, BUSY.
- There is no echo cancellation. With speakers and the microphone both on, the teacher can be recorded twice (the UI tip says to use headphones). Building acoustic echo cancellation is out of scope.
- `ArabicLessonScribe.exe --list-audio` prints JSON (`microphones`, `outputs`, `loopback_available`, `imports`, `errors`) and exits 0 even without devices. In CI on the frozen exe check that `imports.sounddevice` and `imports.pyaudiowpatch` are both true. `python tools/check_loopback.py` on a Windows PC lists devices and records 5 s of system sound plus microphone to wav files and prints levels.
- PyInstaller: `collect_all("pyaudiowpatch")` plus hidden imports `pyaudiowpatch` and `_portaudiowpatch` (the extension module is a top-level `_portaudiowpatch.cp312-win_amd64.pyd`, PortAudio is statically inside it, no extra DLL). The existing `sounddevice` entry stays.
- Tests use fake streams and a fake pyaudiowpatch module (`tests/test_recorder.py`, `tests/test_loopback.py`); mixing, resampling, silence fill, a simulated 10 minute drift run, device change, crash recovery of the tracks and error messages are covered. The real loopback has NOT been run on the Mac build machine. It must be validated on Windows with the checklist below.

#### Windows validation checklist for computer-sound recording
Run on a real Windows 11 PC (and once on Windows 10 if you can). For each item record about 2 minutes, stop, and listen to `recording.wav`, `system.wav` and `mic.wav` in the lesson folder.
- `ArabicLessonScribe.exe --list-audio` from a terminal: JSON with `imports.pyaudiowpatch: true`, `loopback_available: true`, your speakers in `outputs`.
- `python tools/check_loopback.py` with music playing: system_rms above 0.002.
- Zoom (desktop app): teacher voice in system.wav, your voice in mic.wav, both in recording.wav, both bars move.
- Google Meet in Chrome, and WhatsApp Web (voice or video call): same checks.
- Silence handling: pause the music for 30 s in the middle; the files must keep their length (compare with the clock) and the voices must stay in sync after the pause.
- After 20 s with the lesson muted but the microphone heard: the "No computer sound detected" hint appears.
- Bluetooth headset (as output and microphone): does it record, and how does it sound in call mode? Note the quality.
- HDMI monitor with speakers as the default output: recorded?
- Unplug the headphones (or plug them in) mid-recording: the app should say the speakers changed and keep recording, with audio from the new device afterwards, or stop safely with everything kept.
- Another app with exclusive audio (for example a DAW or a game in exclusive mode): a clear LOOPBACK_DENIED message, no crash.
- Microphone privacy off: a clear message with the Settings path; computer-sound-only still works.
- One hour with both sources on: no growth in memory, files the same length, no drift between system.wav and mic.wav at the end.

### A8. Where things live
- Code: `app/` (backend), `app/ui/` (screens), `app/prompts/` (the instructions given to Gemma, plain text files you can edit).
- Packaging: `build/` and `.github/workflows/build.yml`.
- Design contract: `SPEC.md`.

### A9. Languages, dialects and models (research notes, 2026-11-10)
- Per-chunk language detection is our own: VAD windows, `detect_language`, restricted to the ticked languages, smoothed, then forced-language transcription (details in SPEC.md, "Addendum: languages"). One language ticked skips all of it.
- Hebrew: `ivrit-ai/whisper-large-v3-turbo-ct2` (Apache-2.0, not gated, CTranslate2, 1618 MB model.bin, 307,639 downloads all time, 46,770 in the last 30 days, trained on about 388 hours of Hebrew). Added as the opt-in model key `hebrew`, allowed only when Hebrew is the only lesson language, because one-language fine-tunes get worse at other languages. Not verified here: its real Hebrew quality (the 480 MB multilingual test model was used for all checks).
- Levantine: the only CTranslate2 candidate found was `HebArabNlpProject/WhisperLevantine` (Apache-2.0, not gated, large-v3 fine-tune on about 1,200 hours of Israeli-Arabic, reported WER 33 percent, 6,175 MB so not quantised, 14,590 downloads all time, 96 in the last 30 days, thin model card). Other Levantine fine-tunes (otozz, Laith05 and similar) are small PyTorch models with under 40 downloads a month and no CT2 files. Not added: heavy, narrow (Israeli Arabic), unproven, and a fine-tune would hurt mixed lessons. General Arabic CT2 fine-tunes exist (for example Omar10lfc/whisper-large-v3-turbo-arabic-ct2-int8, 814 MB, Apache-2.0, about 220 downloads a month) but are small community uploads and not dialect specific. Revisit if a well-used Levantine CT2 model appears.
- Speed: see the measured numbers in the report for this change; automatic detection costs extra encoder passes (one per 30 s block when the audio is clearly one language, one per speech window otherwise).

## Part B. For the person using the app (send this part)

### B1. Install
1. Open the link you were sent and download `ArabicLessonScribe-Setup.exe`.
2. Double-click it. If Windows says "Windows protected your PC", click "More info", then "Run anyway". This appears because the app is new and unsigned; it is expected.
3. Click Next until it finishes. No password or administrator rights are needed.
4. Open "Arabic Lesson Scribe" from the Start Menu.

### B2. Record your lesson
- Use your phone's voice recorder. Put the phone close to the teacher or on the table, in a quiet room.
- Any recording works: m4a, mp3, wav, amr and similar.
- Move the file to the computer: email it to yourself, use Google Drive or OneDrive, WhatsApp Web, or a USB cable. Make sure the file is fully on the computer, not only in the cloud.

### B3. Turn it into text
1. Open the app and click the big box, or drop the file onto it.
2. First time only: the app downloads the speech model (about 1.6 GB). Keep the app open and the computer connected to the internet. If the connection drops, just reopen and click again; it continues.
3. The Arabic text appears on screen while it works. A one-hour lesson can take 40 to 90 minutes. Keep the laptop plugged in. You can leave it and do something else. The computer will not go to sleep while it works.
4. If you close the app or it stops, open the lesson and click "Continue transcription".
5. Under the big box, tick the languages of your lessons (see B3a).

### B3a. Languages, dialect and mixed lessons
- **Languages in my lessons**: tick Arabic, Hebrew, English and/or French. Only the ticked languages can appear in the text.
- With two or more ticked and "Detect automatically between these" on, every stretch of speech is assigned to one of your ticked languages. A Hebrew question in the middle of an Arabic lesson is written in Hebrew. Where the language changes, a small tag (AR, HE, EN, FR) is shown in the transcript. With one language ticked there is no detection and no tag.
- Switch "Detect automatically" off to force the first ticked language for the whole recording.
- **Arabic dialect** (shown when Arabic is ticked): Levantine, Egyptian, Gulf, Maghrebi or Standard. Be aware that Whisper has no dialect switch. The app puts a short sentence in that dialect in front of the audio as a hint, which nudges spelling and word choice. It does not teach the engine a dialect it does not know.
- A language that is not ticked can never be chosen, so speech in it is written wrongly as one of the ticked languages (a nonsense transcription) instead of being labelled correctly. If in doubt, tick it.
- Very short utterances (about one or two seconds) are the weak spot. They are given the language of their neighbours unless the engine is very sure.
- The AI buttons (summary, words, outline, questions, recap) know which languages the lesson contains, and quote Hebrew in Hebrew letters and Arabic in Arabic letters. Vocabulary from the lesson keeps its language.

### B3b. Record an online lesson, or with the microphone
1. Join the online lesson as usual (Zoom, Meet, Teams, WhatsApp Web...). Keep its sound on the computer's normal speakers or headphones.
2. Open the program, click "Record a lesson". Leave both switches on: "Computer sound (your teacher in the online lesson)" and "My microphone (your own voice)". Click "Start recording".
3. Two bars: the top one moves with the lesson's sound, the bottom one with your voice. If the top one never moves for 20 seconds the program warns you. Use headphones so your microphone does not pick up the teacher a second time (echo). Tell your teacher you are recording; some places require consent.
4. "Pause" and "Stop and save". Then choose "Transcribe now" (uses your language settings) or "Later". The recording is a part of today's lesson day. The sound is saved to disk while recording (about 115 MB per hour per file, 16 kHz mono) and Windows is kept awake. The lesson folder also keeps `system.wav` and `mic.wav`.
5. If the output is unplugged or the disk gets almost full, the recording stops safely and keeps what was recorded. After a crash the unfinished recording shows up as an interrupted lesson (the files are repaired automatically).
6. Windows blocks the microphone? Settings, Privacy and security, Microphone, switch on "Let desktop apps access your microphone".
7. Limits: virtual audio devices, a Bluetooth headset that switches to low-quality call mode, and apps that take exclusive control of the speakers can prevent or degrade the computer sound. In the same room as the teacher: switch "Computer sound" off and use only the microphone.

### B4. Lessons are grouped by day
Every recording is filed under the day it was recorded. Two recordings on the same day belong to the same lesson day. You can open a day to read everything from that day in order. If a recording is filed under the wrong day, open it and choose "Change day".

### B5. The daily recap
Open a day and click the recap. You get:
- what was taught,
- focus points: what you should have learned today,
- the key words with meanings,
- grammar points,
- homework, only if the teacher mentioned it.
The first time, the app downloads the assistant (about 2.8 GB, once). After that, the recap is made automatically when a transcription finishes.

### B6. Ten practice questions
In the same day, open Questions. You get 10 questions made only from what was taught that day: translate, fill in the blank, multiple choice and grammar. Think of your answer, click "Show answer", and mark yourself right or wrong to see your score. "New set of 10" gives different questions. You can print the questions with or without the answers.

### B7. Ask a question
Use Ask to ask about the lesson, for example "What did the teacher say about the word for house?". The assistant only looks at your lesson.

### B8. Already have a transcript?
On the first screen, click "Have a transcript already? Open it", and choose a .txt, .md or .srt file. The recap, words and questions work on it too.

### B9. Where are my files?
In the folder Documents, then "Arabic Lessons". Each recording has its own folder with the text (txt and md) and your notes. The recap and questions for each day are in the `_days` folder. You can copy them anywhere. Uninstalling the app does not delete them.

### B10. Good to know
- Everything happens on your computer. Nothing is uploaded after the one-time downloads.
- The assistant is a small AI. It can be wrong, especially with Arabic grammar. The transcript is the real record. Check anything important with your teacher.
- The text can have mistakes with names, dialect words and noisy rooms.

## Part C. Troubleshooting

- "Windows protected your PC": More info, then Run anyway.
- Antivirus blocks or deletes the installer: add an exception for it, or ask the sender for the checksum file to verify the download, and report it as a false positive.
- The download is very slow or stops: keep the app open; reopening continues where it stopped. The models are on huggingface.co, so a work network that blocks it will fail.
- Not enough space: you need about 5 GB free. Models are in `%LOCALAPPDATA%\ArabicLessonScribe\models` and can be deleted; the app downloads them again when needed.
- Transcription is very slow: use the default model, plug in the laptop, close other heavy programs. Do not choose the "best" model on a laptop without a strong CPU.
- The app uses a lot of memory on a long recording: close other programs, or split the recording into two files.
- The text is empty or wrong: check that the recording is audible; check that every language of the lesson is ticked under "Languages in my lessons".
- The window is blank or says WebView2 is missing: the installer normally adds it. Install "Microsoft Edge WebView2 Runtime" from Microsoft and reopen.
- The assistant does not answer or crashes: it needs about 4 GB of free memory. Close other programs and retry. The log file path is shown in the app settings.
- Reporting a problem: send the log file from `%LOCALAPPDATA%\ArabicLessonScribe\logs`.
