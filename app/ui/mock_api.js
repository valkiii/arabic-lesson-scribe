"use strict";
/* Mock backend for testing the UI in a normal browser (?mock=1). Loaded only when window.pywebview is absent. */
(function () {
  const SEGS = [
    "السلام عليكم ورحمة الله وبركاته، أهلاً بكم في درس اللغة العربية.",
    "اليوم سنتحدث عن الأفعال في صيغة الماضي والمضارع.",
    "الفعل الماضي يدل على حدث وقع وانتهى قبل زمن التكلم، مثل: كَتَبَ وذَهَبَ وقَرَأَ.",
    "أما الفعل المضارع فيدل على حدث يقع الآن أو في المستقبل، مثل: يَكْتُبُ ويَذْهَبُ ويَقْرَأُ.",
    "Now repeat after me, please. Ripetete insieme a me.",
    "كلمة جديدة: المَدْرَسَة، وتعني المكان الذي يتعلم فيه الطلاب.",
    "من يستطيع أن يكوّن جملة بهذه الكلمة؟ نعم، تفضلي.",
    "המורה, איך אומרים school בערבית? אפשר לחזור על זה?",
    "ذهبتُ إلى المدرسة صباحاً مع صديقتي.",
    "ممتاز، أحسنتِ. والآن الواجب المنزلي: اكتبوا خمس جمل باستخدام الأفعال الجديدة.",
    "إلى اللقاء، وشكراً لكم على حسن الاستماع."
  ];
  const langOf = text => /[\u0590-\u05FF]/.test(text) ? "he" : /[\u0600-\u06FF]/.test(text) && !/^[A-Za-z]/.test(text) ? "ar" : "en";
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const emit = (n, p) => window.__onEvent && window.__onEvent(n, p);
  const lessons = {
    l1: { meta: { id: "l1", title: "Past and present verbs", date: "2026-11-03T18:30:00", duration_s: 2700 },
      segments: SEGS.map((text, i) => ({ start: i * 12, end: i * 12 + 11, text, lang: langOf(text) })), notes: { qa: [] } }
  };
  // an interrupted lesson (original recording present) and one whose recording moved (?moved=1 is not needed: l_moved)
  lessons.l_int = { meta: { id: "l_int", title: "Lesson 11 (interrupted)", date: "2026-11-05T18:30:00", duration_s: 3600, status: "interrupted",
    audio_path: "C:\\Users\\Sara\\Recordings\\lesson11.m4a", audio_ok: true },
    segments: SEGS.slice(0, 4).map((text, i) => ({ start: i * 12, end: i * 12 + 11, text, lang: langOf(text) })), notes: { qa: [] } };
  lessons.l_moved = { meta: { id: "l_moved", title: "Lesson 10 (recording moved)", date: "2026-11-04T18:30:00", duration_s: 1800, status: "interrupted",
    audio_path: "D:\\old\\lesson10.m4a", audio_ok: false },
    segments: SEGS.slice(0, 3).map((text, i) => ({ start: i * 12, end: i * 12 + 11, text, lang: langOf(text) })), notes: { qa: [] } };
  lessons.l1b = { meta: { id: "l1b", title: "Past and present verbs, part 2", date: "2026-11-03T20:10:00", duration_s: 900, status: "done" },
    segments: SEGS.slice(5).map((text, i) => ({ start: i * 12, end: i * 12 + 11, text, lang: langOf(text) })), notes: { qa: [] } };
  const dayNotes = {};
  const dayOf = l => l.meta.day || String(l.meta.date).slice(0, 10);
  const partsOf = day => Object.values(lessons).filter(l => dayOf(l) === day).sort((a, b) => a.meta.date < b.meta.date ? -1 : 1);
  const mkQuiz = (round) => Array.from({ length: 10 }, (_, i) => {
    const type = ["translate_from_arabic", "translate_to_arabic", "fill_blank", "multiple_choice", "grammar"][i % 5], id = "q" + round + "_" + i;
    const base = { id, type, explanation: "The teacher says this in the lesson.", source_hint: "part 1" };
    if (type === "translate_from_arabic") return { ...base, question: "ذَهَبْتُ إلى المدرسة", answer: "I went to school" };
    if (type === "translate_to_arabic") return { ...base, question: "He wrote (round " + round + ")", answer: "كَتَبَ" };
    if (type === "fill_blank") return { ...base, question: "ذهبتُ إلى ____ صباحاً", answer: "المدرسة" };
    if (type === "multiple_choice") return { ...base, question: "Which word means 'he writes'?", options: ["يَكْتُبُ", "كَتَبَ", "ذَهَبَ", "قَرَأَ"], answer: "يَكْتُبُ" };
    return { ...base, question: "When do we use the past tense?", answer: "For an action that is finished." };
  });
  async function dayJob(kind, day, work) {
    if (!st.gemma) { if (!await download("gemma", "Downloading assistant", 2840)) return; }
    const id = kind + ":" + day;
    emit("progress", { job: "llm", id, pct: null, message: "Thinking" });
    await sleep(1200); work();
    emit("done", { job: "llm", id, ok: true, kind, date: day });
  }
  const makeRecap = day => ({ topic: "Past and present Arabic verbs, with new school vocabulary.", taught: ["The past tense: كَتَبَ, ذَهَبَ", "The present tense: يَكْتُبُ, يَذْهَبُ"],
    focus: ["You can use the past tense to say that something already happened.", "You can say 'he writes' with يَكْتُبُ.", "You can say 'school' with المَدْرَسَة."],
    vocab: [{ arabic: "المَدْرَسَة", meaning: "school", transliteration: "al-madrasa" }, { arabic: "كَتَبَ", meaning: "he wrote", transliteration: "kataba" }, { arabic: "שאלה", lang: "he", meaning: "question", transliteration: "she'ela" }],
    grammar: ["Past tense describes finished actions."], homework: ["Write five sentences with the new verbs."], unclear_note: "", stale: false, parts: partsOf(day).map(l => l.meta.id) });
  const STRESS = new URLSearchParams(location.search).get("stress"); // ?stress=3000 streams that many segments fast
  const st = { fast: false, best: false, gemma: false, settings: { ui_lang: "en", model: "fast", spoken_languages: ["ar", "he"], arabic_dialect: "levantine", mode: "auto", auto_recap: true } };
  let n = 2, cancelled = {}, rec = null;
  const meta = l => ({ id: l.meta.id, day: dayOf(l), title: l.meta.title, date: l.meta.date, duration_s: l.meta.duration_s, status: l.meta.status || "done", preview: (l.segments[0] || {}).text || "" });

  async function download(id, label, mb) {
    for (let i = 0; i <= 20; i++) {
      if (cancelled.all) return false;
      emit("progress", { job: "download", id, pct: i * 5, message: `${label}: ${Math.round(mb * i / 20)} of ${mb} MB`, eta_s: (20 - i) * 6 });
      await sleep(120);
    }
    st[id === "gemma" ? "gemma" : id] = true;
    emit("done", { job: "download", id, ok: true });
    return true;
  }
  async function llm(lessonId, work) {
    cancelled = {};
    if (!st.gemma) { if (!await download("gemma", "Downloading assistant", 2840)) return; }
    emit("progress", { job: "llm", id: lessonId, pct: null, message: "Thinking" });
    await sleep(1500);
    work(lessons[lessonId].notes);
    emit("done", { job: "llm", id: lessonId, ok: true });
  }

  const api = {
    async get_state() {
      return { models: { fast: { installed: st.fast, size_mb: 1600 }, best: { installed: st.best, size_mb: 3100 }, hebrew: { installed: false, size_mb: 1620 }, gemma: { installed: st.gemma, size_mb: 2840 } },
        lessons: Object.values(lessons).map(meta), days: api.list_days_sync(), settings: st.settings };
    },
    list_days_sync() {
      const by = {}; for (const l of Object.values(lessons)) (by[dayOf(l)] = by[dayOf(l)] || []).push(l);
      return Object.keys(by).sort().reverse().map(d => { const ps = partsOf(d); return { date: d, parts: ps.map(meta), has_recap: !!(dayNotes[d] || {}).recap,
        recap_stale: !!((dayNotes[d] || {}).recap || {}).stale, has_quiz: !!(dayNotes[d] || {}).quiz, total_duration_s: ps.reduce((a, l) => a + (l.meta.duration_s || 0), 0) }; });
    },
    async list_days() { return api.list_days_sync(); },
    async get_day(day) {
      const ps = partsOf(day), n = dayNotes[day] || {};
      return JSON.parse(JSON.stringify({ date: day, parts: ps.map(meta), segments_by_part: Object.fromEntries(ps.map(l => [l.meta.id, l.segments])), notes: { recap: n.recap || null, quiz: n.quiz || null } }));
    },
    async set_lesson_date(id, day) {
      const l = lessons[id], old = dayOf(l); l.meta.day = day; l.meta.date = day + String(l.meta.date).slice(10);
      if ((dayNotes[old] || {}).recap) dayNotes[old].recap.stale = true;
      if ((dayNotes[day] || {}).recap) dayNotes[day].recap.stale = true;
      return { id, day, old_day: old };
    },
    async ai_day_recap(day) { dayJob("recap", day, () => { dayNotes[day] = { ...(dayNotes[day] || {}), recap: makeRecap(day) }; }); return { job_id: "recap:" + day }; },
    async ai_day_quiz(day, o) {
      const n = dayNotes[day] = dayNotes[day] || {};
      if (n.quiz && !(o && o.more)) return { job_id: null, cached: true };
      dayJob("quiz", day, () => { if (!n.recap) n.recap = makeRecap(day); const r = (n.quiz ? n.quiz.round : 0) + 1; n.quiz = { questions: mkQuiz(r), marks: {}, round: r }; });
      return { job_id: "quiz:" + day };
    },
    async set_quiz_mark(day, qid, mark) {
      const q = dayNotes[day].quiz; if (mark) q.marks[qid] = mark; else delete q.marks[qid];
      return { marks: q.marks, score: Object.values(q.marks).filter(v => v === "right").length };
    },
    async export_day(day, fmt, ans, what) { return { path: "C:\\Users\\Sara\\Documents\\Arabic Lessons\\_days\\" + day + "-" + what + "." + fmt }; },
    async open_file() { return { path: "" }; },
    // ---- microphone recording (simulated: ?rec=nomic or ?rec=denied make start fail) ----
    async list_input_devices() {
      if (new URLSearchParams(location.search).get("rec") === "nomic") return [];
      return [{ id: 0, name: "MacBook Microphone (built-in)", default: true }, { id: 3, name: "USB headset microphone", default: false }];
    },
    async start_recording(o) {
      if (new URLSearchParams(location.search).get("rec") === "denied")
        throw new Error("MIC_DENIED: Windows may be blocking the microphone.");
      if (rec) throw new Error("BUSY: a recording is already running");
      const id = "l" + (n++);
      lessons[id] = { meta: { id, title: "Recording " + new Date().toTimeString().slice(0, 5), date: new Date().toISOString(), duration_s: 0, status: "recording" }, segments: [], notes: { qa: [] } };
      rec = { id, t: 0, paused: false, tick: 0 };
      rec.timer = setInterval(() => {
        if (!rec.paused) rec.t += 0.1;
        const level = rec.paused ? 0 : Math.max(0, 0.02 + 0.06 * Math.abs(Math.sin(rec.tick / 3)) * (0.5 + Math.random()));
        rec.tick++;
        const silent = new URLSearchParams(location.search).get("rec") === "silent" && rec.t > 3;
        emit("record", { recording_id: id, lesson_id: id, state: rec.paused ? "paused" : "recording", elapsed_s: Math.round(rec.t * 10) / 10,
          level: silent ? 0 : level, peak_clipping: false, silent, low_disk: false, free_disk_mb: 50000 });
      }, 100);
      return { recording_id: id, lesson_id: id };
    },
    async pause_recording() { rec.paused = true; return { state: "paused" }; },
    async resume_recording() { rec.paused = false; return { state: "recording" }; },
    async stop_recording() {
      clearInterval(rec.timer); const l = lessons[rec.id];
      Object.assign(l.meta, { status: "recorded", duration_s: Math.round(rec.t), audio_path: "C:\\Users\\Sara\\Documents\\Arabic Lessons\\" + rec.id + "\\recording.wav", audio_ok: true });
      const r = { lesson_id: rec.id, audio_path: l.meta.audio_path, duration_s: Math.round(rec.t * 10) / 10, reason: "stopped" }; rec = null; return r;
    },
    async cancel_recording() { clearInterval(rec.timer); delete lessons[rec.id]; rec = null; return { cancelled: true }; },
    async pick_audio() { await sleep(200); return "C:\\Users\\Sara\\Recordings\\Arabic lesson 12.m4a"; },
    async start_transcription(path, opts) {
      const id = "l" + (n++); cancelled = {};
      const title = path.split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
      lessons[id] = { meta: { id, title, date: new Date().toISOString(), duration_s: 600 }, segments: [], notes: { qa: [] } };
      (async () => {
        if (!st.fast && !await download("fast", "Downloading speech model", 1600)) { delete lessons[id]; emit("done", { job: "transcribe", id, ok: false }); return; }
        const total = STRESS ? +STRESS : SEGS.length, t0 = performance.now();
        for (let i = 0; i < total; i++) {
          if (cancelled.all) { lessons[id].meta.status = "interrupted"; lessons[id].meta.audio_path = path; lessons[id].meta.audio_ok = true;
            if (!lessons[id].segments.length) delete lessons[id]; emit("done", { job: "transcribe", id, ok: false, error: "cancelled" }); return; }
          await sleep(STRESS ? 2 : 900);
          const sg = { start: i * 12, end: i * 12 + 11, text: SEGS[i % SEGS.length], lang: langOf(SEGS[i % SEGS.length]) };
          lessons[id].segments.push(sg);
          emit("segment", { lesson_id: id, ...sg });
          emit("progress", { job: "transcribe", id, pct: Math.round((i + 1) / total * 100), message: "Transcribing",
            eta_s: i > 3 ? (total - i - 1) * 2400 : undefined, elapsed_s: (performance.now() - t0) / 1000 });
        }
        lessons[id].meta.status = "done";
        emit("done", { job: "transcribe", id, ok: true });
      })();
      return { lesson_id: id };
    },
    async resume_transcription(id, path) {
      const l = lessons[id]; cancelled = {};
      if (!l.meta.audio_ok && !path) throw new Error("AUDIO_MISSING: the original recording was not found");
      l.meta.audio_ok = true; l.meta.status = "transcribing";
      (async () => {
        const total = STRESS ? +STRESS : SEGS.length, t0 = performance.now();
        for (let i = l.segments.length; i < total; i++) {
          if (cancelled.all) { l.meta.status = "interrupted"; emit("done", { job: "transcribe", id, ok: false, error: "cancelled" }); return; }
          await sleep(STRESS ? 2 : 900);
          const last = l.segments.length ? l.segments[l.segments.length - 1].end : 0;
          const sg = { start: last, end: last + 11, text: SEGS[i % SEGS.length], lang: langOf(SEGS[i % SEGS.length]) };
          l.segments.push(sg);
          emit("segment", { lesson_id: id, ...sg });
          const el = (performance.now() - t0) / 1000;
          emit("progress", { job: "transcribe", id, pct: Math.round((i + 1) / total * 100), message: "Transcribing", eta_s: i > 3 ? (total - i - 1) * 2400 : undefined, elapsed_s: el });
        }
        l.meta.status = "done";
        emit("done", { job: "transcribe", id, ok: true });
      })();
      return { lesson_id: id };
    },
    async import_transcript(path) {
      await sleep(150);
      const name = (path || "C:\\Users\\Sara\\Documents\\lesson notes.txt").split(/[\\/]/).pop();
      const id = "l" + (n++), srt = /\.(srt|vtt)$/i.test(name);
      const segments = SEGS.map((text, i) => srt ? { start: i * 12, end: i * 12 + 11, text } : { start: null, end: null, text });
      lessons[id] = { meta: { id, title: name.replace(/\.[^.]+$/, ""), date: new Date().toISOString(), duration_s: srt ? 120 : 0, status: "imported", audio_path: null, audio_ok: false },
        segments, notes: { qa: [] } };
      return { lesson_id: id };
    },
    async cancel() { cancelled.all = true; return true; },
    async get_lesson(id) { return JSON.parse(JSON.stringify(lessons[id])); },
    async rename_lesson(id, title) { lessons[id].meta.title = title; return true; },
    async delete_lesson(id) { delete lessons[id]; return true; },
    async open_folder() { return true; },
    async export_lesson(id, fmt) { return "C:\\Users\\Sara\\Documents\\Arabic Lessons\\export." + fmt; },
    async ai_summary(id) { llm(id, nt => nt.summary = "The teacher introduces past and present Arabic verbs, with examples such as كَتَبَ (he wrote) and يَكْتُبُ (he writes).\n\nNew word: المَدْرَسَة (school). Students practise forming sentences, and the homework is to write five sentences with the new verbs."); return true; },
    async ai_vocab(id) { llm(id, nt => nt.vocab = [
      { arabic: "كَتَبَ", transliteration: "kataba", meaning: "he wrote", note: "past tense" },
      { arabic: "يَكْتُبُ", transliteration: "yaktubu", meaning: "he writes", note: "present tense" },
      { arabic: "المَدْرَسَة", transliteration: "al-madrasa", meaning: "the school", note: "" },
      { arabic: "الواجب", transliteration: "al-wājib", meaning: "homework", note: "" }]); return true; },
    async ai_classify(id) { llm(id, nt => nt.outline = [
      { start: 0, end: 24, kind: "dialogue", summary: "Greetings" },
      { start: 24, end: 48, kind: "grammar", summary: "Past vs present verbs" },
      { start: 48, end: 72, kind: "vocabulary", summary: "Word: المَدْرَسَة" },
      { start: 72, end: 120, kind: "homework", summary: "Five sentences" }]); return true; },
    async ai_ask(id, q) { llm(id, nt => nt.qa.push({ q, a: "According to the transcript, the teacher says the past tense describes something finished, as in كَتَبَ, while the present tense يَكْتُبُ describes something happening now." })); return true; },
    async set_settings(s) { Object.assign(st.settings, s); return st.settings; },
    async get_log_path() { return "C:\\Users\\Sara\\AppData\\Local\\ArabicLessonScribe\\logs\\app.log"; }
  };
  window.pywebview = { api };
})();
