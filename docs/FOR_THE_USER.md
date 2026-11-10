# Arabic Lesson Scribe: a short guide

This program listens to the recording of your Arabic lesson and writes down everything that was
said, in Arabic. You can then ask it for a summary, a list of new words, or answers to questions.
It all works on your own computer, and your recordings never leave it.

## 1. Download and install

1. Open the download page your friend sent you and click **ArabicLessonScribe-Setup.exe**.
2. Double-click the file once it has downloaded.
3. If Windows shows a blue box saying "Windows protected your PC", don't worry. The program is
   new and not yet known to Microsoft. Click **More info**, then **Run anyway**.
4. Click Next until it finishes. It does not ask for an administrator password. If it says it needs
   to install a Microsoft component, let it. That takes a minute or two and needs the internet.
5. Tick "Create a desktop shortcut" if you would like one.

## 2. The first time you open it

The first time, the program needs to download its "brain". This happens only once.

- Speech to text: about 1.6 GB. Allow 5 to 30 minutes depending on your internet.
- The AI assistant (summary, words, questions): about 2.8 GB more. It downloads only when you first
  use one of those buttons, so you can skip it if you only want the text.

After that, no internet is needed. You can leave the window open while it downloads.

## 3. Getting your lesson onto the computer

1. Record the lesson with your phone's voice recorder app as usual.
2. Send the file to the PC. Easiest ways: email it to yourself, use a USB cable and copy it from
   the phone's "Recordings" or "Music" folder, or use Google Drive / iCloud / WhatsApp Web and
   download it on the PC.
3. Remember where you saved it, for example in Downloads.

## 4. Turning it into text

1. Open Arabic Lesson Scribe.
2. Drag the recording into the big box, or click the box and choose the file.
3. Wait. The words appear as it goes, and the program shows how long it has been running and, after
   a few minutes, roughly how much is left. Keep the program open. While it works, the program asks
   Windows not to go to sleep (the screen may still turn off).
4. If the teacher also explains in English or Italian, tick **Lesson mixes languages**.

### A one-hour recording

- Expect roughly one to three hours of waiting on an ordinary laptop, so start it before a break or
  overnight. The first estimate appears after a few minutes and gets more accurate as it goes.
- Keep the laptop plugged in. On battery, Windows may slow the computer down a lot.
- If the program is closed, the computer restarts, or you press Cancel, nothing is lost: the text
  written so far is saved. Open the lesson in your list and click **Continue transcription**. It
  carries on from where it stopped. The program needs the original recording, so don't move or
  delete it. If you did move it, the program asks you to choose the file again.
- Summary, Vocabulary and the other AI buttons on a very long lesson take several minutes too.

### If you already have a transcript

Under the big box, click **Open it** (or drag a `.txt`, `.md`, `.srt` or `.vtt` file onto the box).
The program opens it as a lesson, without any recording, and Summary, Vocabulary, Outline and Ask a
question all work on it. Subtitle files (`.srt`, `.vtt`) keep their times. Plain text has no times.

### Days, the daily recap and practice questions

Recordings are grouped by day, using the date the file was recorded (your phone usually keeps it).
Two recordings from the same lesson day appear together under one date on the home screen. Click the
date to open the whole day: all recordings in order, one after the other. Click a single recording
to open just that part. Wrong date? Open the recording, click **Change day**, and pick the right one.

- **Daily recap**: a short page for the day with the topic, what was taught, the focus points ("what
  you should have learned today"), key vocabulary, grammar points, and homework only if the teacher
  mentioned it. If you have already downloaded the assistant, the recap is made by itself when a
  recording finishes, and refreshed when you add another recording to that day. If not, you will see a
  button **Make today's recap (downloads the assistant, 2.8 GB, once)**. Nothing big is ever
  downloaded without you clicking it. You can turn the automatic recap off on the home screen.
- **Practice questions**: exactly 10 questions about that day only (translate, fill in the blank,
  multiple choice, grammar). Click **Show answer**, then mark yourself right or wrong to get a score
  out of 10. Your marks stay on your computer. **New set of 10** makes different questions.
- **Save recap** saves a text file, and **Print quiz** opens a page you can print, with or without
  the answers. These files are in Documents, Arabic Lessons, in the folder named `_days`.

The recap and questions are written by the AI from the transcript, so check anything important.

## 5. What the buttons do

- **Summary**: a short summary of the lesson.
- **Vocabulary**: a list of the new words with meanings.
- **Outline**: shows which parts were vocabulary, grammar, conversation, or homework.
- **Ask a question**: type a question about the lesson and get an answer.
- **Copy**: copies the text so you can paste it elsewhere.
- **Export**: saves the text as a file you can open in Notepad or Word.
- **Open folder**: shows the lesson's files in Windows.

## 6. Where are my files?

Every lesson is saved in your **Documents** folder, in **Arabic Lessons**, one folder per lesson.
Inside you will find the transcript as text files. Your original recording is not copied, so keep it
where it is. The program itself and its downloaded models live in
`C:\Users\<you>\AppData\Local\ArabicLessonScribe`. To remove everything, uninstall it from
Windows Settings, Apps.

## 7. If Windows or your antivirus complains

- "Windows protected your PC": click **More info**, then **Run anyway**.
- Antivirus says the file is suspicious: this happens with new, unsigned programs. If your friend
  who sent it to you trusts it, choose to allow it or restore it from quarantine.
- If the program does not open at all, restart the computer and try again, then tell your friend.

## 8. An honest note

The transcript is the real record of your lesson, but it is made by a computer and can contain
mistakes, especially with unclear audio, names, or mixed languages. The AI answers (summary, words,
answers to questions) can be wrong too. Treat them as helpful hints and check anything important
against the transcript or your teacher.
