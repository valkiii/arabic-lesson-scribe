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
    "ذهبتُ إلى المدرسة صباحاً مع صديقتي.",
    "ممتاز، أحسنتِ. والآن الواجب المنزلي: اكتبوا خمس جمل باستخدام الأفعال الجديدة.",
    "إلى اللقاء، وشكراً لكم على حسن الاستماع."
  ];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const emit = (n, p) => window.__onEvent && window.__onEvent(n, p);
  const lessons = {
    l1: { meta: { id: "l1", title: "Past and present verbs", date: "2026-11-03T18:30:00", duration_s: 2700 },
      segments: SEGS.map((text, i) => ({ start: i * 12, end: i * 12 + 11, text })), notes: { qa: [] } }
  };
  const st = { fast: false, best: false, gemma: false, settings: { ui_lang: "en", model: "fast", mixed_languages: false } };
  let n = 2, cancelled = {};
  const meta = l => ({ id: l.meta.id, title: l.meta.title, date: l.meta.date, duration_s: l.meta.duration_s, preview: (l.segments[0] || {}).text || "" });

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
    if (!st.gemma) { if (!await download("gemma", "Downloading assistant", 2840)) return; }
    emit("progress", { job: "llm", id: lessonId, pct: null, message: "Thinking" });
    await sleep(1500);
    work(lessons[lessonId].notes);
    emit("done", { job: "llm", id: lessonId, ok: true });
  }

  const api = {
    async get_state() {
      return { models: { fast: { installed: st.fast, size_mb: 1600 }, best: { installed: st.best, size_mb: 3100 }, gemma: { installed: st.gemma, size_mb: 2840 } },
        lessons: Object.values(lessons).map(meta), settings: st.settings };
    },
    async pick_audio() { await sleep(200); return "C:\\Users\\Sara\\Recordings\\Arabic lesson 12.m4a"; },
    async start_transcription(path, opts) {
      const id = "l" + (n++); cancelled = {};
      const title = path.split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
      lessons[id] = { meta: { id, title, date: new Date().toISOString(), duration_s: 600 }, segments: [], notes: { qa: [] } };
      (async () => {
        if (!st.fast && !await download("fast", "Downloading speech model", 1600)) { delete lessons[id]; emit("done", { job: "transcribe", id, ok: false }); return; }
        for (let i = 0; i < SEGS.length; i++) {
          if (cancelled.all) { delete lessons[id]; emit("done", { job: "transcribe", id, ok: false }); return; }
          await sleep(900);
          const sg = { start: i * 12, end: i * 12 + 11, text: SEGS[i] };
          lessons[id].segments.push(sg);
          emit("segment", { lesson_id: id, ...sg });
          emit("progress", { job: "transcribe", id, pct: Math.round((i + 1) / SEGS.length * 100), message: "Transcribing", eta_s: (SEGS.length - i - 1) * 40 });
        }
        emit("done", { job: "transcribe", id, ok: true });
      })();
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
