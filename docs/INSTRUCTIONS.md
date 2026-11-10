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

### A8. Where things live
- Code: `app/` (backend), `app/ui/` (screens), `app/prompts/` (the instructions given to Gemma, plain text files you can edit).
- Packaging: `build/` and `.github/workflows/build.yml`.
- Design contract: `SPEC.md`.

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
5. If the teacher mixes Arabic with English or Italian, turn on "Lesson mixes languages".

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
- The text is empty or wrong: check that the recording is audible; try "Lesson mixes languages".
- The window is blank or says WebView2 is missing: the installer normally adds it. Install "Microsoft Edge WebView2 Runtime" from Microsoft and reopen.
- The assistant does not answer or crashes: it needs about 4 GB of free memory. Close other programs and retry. The log file path is shown in the app settings.
- Reporting a problem: send the log file from `%LOCALAPPDATA%\ArabicLessonScribe\logs`.
