"use strict";
/* Arabic Lesson Scribe UI. Vanilla JS, no dependencies. */

const STRINGS = {
  en: {
    app_name: "Arabic Lesson Scribe",
    drop_title: "Drop a recording here or click to choose",
    drop_hint: "mp3, m4a, wav, ogg, opus, amr, 3gp, mp4, flac",
    rec_btn: "Record a lesson", rec_btn_hint: "with this computer's microphone", rec_title: "Record a lesson",
    rec_device: "Microphone", rec_start: "Start recording", rec_pause: "Pause", rec_resume: "Resume", rec_stop: "Stop and save",
    rec_tip: "Put the computer close to the teacher, in a quiet room. Keep this window open while recording.",
    rec_state_ready: "Ready", rec_state_recording: "Recording", rec_state_paused: "Paused",
    rec_silent: "No sound detected. Check your microphone.", rec_clip: "The sound is too loud. Move the microphone away or lower its volume.",
    rec_low_disk: "The disk is getting full. Recording stops automatically when almost no space is left.",
    rec_done_title: "Recording saved", rec_done_len: "{t} recorded. It is saved as a part of today's lessons.",
    rec_now: "Transcribe now", rec_later: "Later", rec_confirm_discard: "Discard this recording? It cannot be recovered.",
    rec_lost: "The microphone stopped (unplugged or switched off?). Everything recorded so far is saved.",
    rec_disk_stopped: "The disk is almost full, so the recording was stopped safely. Everything recorded so far is saved.",
    rec_err_NO_MIC: "No microphone was found. Plug one in or switch it on, then try again.",
    rec_err_MIC_DENIED: "Windows is not allowing this app to use the microphone. Open Settings, Privacy and security, Microphone, and switch on 'Let desktop apps access your microphone'.",
    rec_err_DISK_FULL: "There is not enough free disk space to record. Free some space and try again.",
    rec_err_MIC_ERROR: "The microphone could not be started.",
    rec_not_transcribed: "This recording has not been transcribed yet.", rec_transcribe: "Transcribe", status_recorded: "Recorded",
    lang_title: "Languages in my lessons",
    lang_ar: "Arabic", lang_he: "Hebrew", lang_en: "English", lang_fr: "French",
    dialect_label: "Arabic dialect",
    dia_msa: "Standard Arabic (MSA)", dia_levantine: "Levantine", dia_egyptian: "Egyptian", dia_gulf: "Gulf", dia_maghrebi: "Maghrebi",
    dialect_note: "Whisper does not have a dialect switch. This only nudges the spelling and word choice; recognition of heavy dialect stays imperfect.",
    opt_detect: "Detect automatically between these",
    forced_hint: "Everything will be written as {lang}. Other languages in the recording will be lost or garbled.",
    opt_hebmodel: "Use the Hebrew-specialised speech model (extra download, about 1.6 GB)",
    opt_best: "Best quality (slower)",
    lessons_title: "Your lessons",
    lessons_empty: "No lessons yet. Your transcripts will appear here.",
    fr_title: "Welcome. One quick setup first.",
    fr_body: "To turn speech into text, the app needs a speech model. It is downloaded once and then everything works without internet.",
    fr_speech: "Speech model: about 1.6 GB (needed now)",
    fr_llm: "Assistant for summaries and questions: about 2.8 GB (optional, downloaded only when you first use it)",
    fr_offline: "Nothing leaves your computer. Keep the app open while it downloads.",
    fr_button: "Choose a recording and download",
    cancel: "Cancel",
    back: "Back",
    rename: "Rename",
    summary: "Summary",
    vocab: "Vocabulary",
    outline: "Outline",
    ask: "Ask a question",
    copy: "Copy transcript",
    export: "Export",
    open_folder: "Open folder",
    delete: "Delete lesson",
    close: "Close",
    ask_placeholder: "Ask about this lesson",
    ask_send: "Ask",
    ai_warning: "AI answers can be wrong. The transcript is the source of truth.",
    confirm_delete: "Delete this lesson and its transcript? This cannot be undone.",
    copied: "Transcript copied",
    exported: "Exported",
    folder_opened: "Folder opened",
    no_path: "Could not read the file location. Please click to choose the file instead.",
    working_default: "Working",
    preparing: "Preparing",
    downloading_model: "Downloading speech model (one time)",
    downloading_llm: "Downloading assistant (one time)",
    transcribing: "Transcribing",
    thinking: "Thinking",
    done_ok: "Done",
    failed: "Something went wrong",
    cancelled: "Cancelled",
    eta: "about {m} min left",
    eta_s: "less than a minute left",
    summary_title: "Summary",
    vocab_title: "Vocabulary",
    outline_title: "Outline",
    ask_title: "Ask a question",
    empty_summary: "No summary yet.",
    generate: "Generate",
    regenerate: "Regenerate",
    import_q: "Have a transcript already?", import_link: "Open it",
    import_ok: "Transcript opened", status_imported: "Imported transcript", status_interrupted: "Interrupted", status_failed: "Failed",
    resume: "Continue transcription",
    resume_msg: "Transcription stopped at {at} of {total}. The text so far is saved.",
    resume_msg_nototal: "Transcription stopped at {at}. The text so far is saved.",
    resume_none: "Transcription did not finish. You can start it again from the beginning.",
    resume_missing: "The original recording was not found, so you will be asked to choose it again.",
    elapsed: "Elapsed {t}", eta_h: "about {h} h {m} min left",
    opt_auto: "Make the daily recap automatically",
    open_day: "Whole day", change_day: "Change day", day_changed: "Moved to another day",
    day_parts_n: "{n} recordings", day_part_1: "1 recording",
    recap: "Daily recap", quiz: "Practice questions", save_recap: "Save recap",
    print_ans: "Print quiz (with answers)", print_noans: "Print quiz (without answers)",
    saved_to: "Saved: {p}", tag_recap: "Recap ready", open_part: "Open this recording",
    recap_make: "Make today's recap", recap_make_dl: "Make today's recap (downloads the assistant, 2.8 GB, once)",
    recap_stale: "A recording was added or moved after this recap was made.", recap_update: "Update recap",
    recap_working: "Writing the recap", recap_none: "No recap yet.",
    rc_taught: "What was taught", rc_focus: "Focus points: what you should have learned today",
    rc_vocab: "Key vocabulary", rc_grammar: "Grammar points", rc_homework: "Homework or things to review", rc_note: "Note",
    quiz_make: "Make 10 practice questions", quiz_make_dl: "Make 10 practice questions (downloads the assistant, 2.8 GB, once)",
    quiz_more: "New set of 10", quiz_working: "Writing questions", quiz_none: "No questions yet.",
    show_answer: "Show answer", hide_answer: "Hide answer", right: "I got it right", wrong: "I got it wrong",
    score: "Score: {r} / 10 ({m} marked)", q_answer: "Answer", q_source: "From",
    qtype_translate_from_arabic: "Translate into your language", qtype_translate_to_arabic: "Translate into the lesson language",
    qtype_fill_blank: "Fill in the blank", qtype_multiple_choice: "Multiple choice", qtype_grammar: "Grammar and usage",
    chip_offline: "Works offline",
    untitled: "Untitled lesson",
    min: "min",
    api_missing: "Backend not available.",
    kind_vocabulary: "vocabulary", kind_grammar: "grammar", kind_dialogue: "dialogue",
    kind_explanation: "explanation", kind_homework: "homework", kind_other: "other"
  },
  fr: { // partial stub: missing keys fall back to English
    app_name: "Arabic Lesson Scribe",
    drop_title: "Déposez un enregistrement ici ou cliquez pour le choisir",
    rec_btn: "Enregistrer un cours", rec_btn_hint: "avec le microphone de cet ordinateur", rec_title: "Enregistrer un cours",
    rec_device: "Microphone", rec_start: "Démarrer l'enregistrement", rec_pause: "Pause", rec_resume: "Reprendre", rec_stop: "Arrêter et enregistrer",
    rec_tip: "Placez l'ordinateur près de l'enseignant, dans une pièce calme. Gardez cette fenêtre ouverte pendant l'enregistrement.",
    rec_state_ready: "Prêt", rec_state_recording: "Enregistrement", rec_state_paused: "En pause",
    rec_silent: "Aucun son détecté. Vérifiez votre microphone.",
    rec_done_title: "Enregistrement sauvegardé", rec_now: "Transcrire maintenant", rec_later: "Plus tard",
    rec_err_NO_MIC: "Aucun microphone trouvé. Branchez-en un ou allumez-le, puis réessayez.",
    rec_err_MIC_DENIED: "Windows n'autorise pas cette application à utiliser le microphone. Ouvrez Paramètres, Confidentialité et sécurité, Microphone, et activez « Autoriser les applications de bureau à accéder à votre microphone ».",
    status_recorded: "Enregistré",
    lang_title: "Langues de mes cours",
    lang_ar: "Arabe", lang_he: "Hébreu", lang_en: "Anglais", lang_fr: "Français",
    dialect_label: "Dialecte arabe",
    dia_msa: "Arabe standard (MSA)", dia_levantine: "Levantin", dia_egyptian: "Égyptien", dia_gulf: "Du Golfe", dia_maghrebi: "Maghrébin",
    dialect_note: "Whisper n'a pas de réglage de dialecte. Ce choix oriente seulement l'orthographe et le choix des mots ; les dialectes marqués restent imparfaitement reconnus.",
    opt_detect: "Détecter automatiquement entre celles-ci",
    forced_hint: "Tout sera écrit en {lang}. Les autres langues de l'enregistrement seront perdues ou mal écrites.",
    opt_hebmodel: "Utiliser le modèle vocal spécialisé pour l'hébreu (téléchargement supplémentaire, environ 1,6 Go)",
    opt_best: "Meilleure qualité (plus lent)",
    lessons_title: "Vos cours",
    cancel: "Annuler", back: "Retour", rename: "Renommer",
    summary: "Résumé", vocab: "Vocabulaire", outline: "Plan", ask: "Poser une question",
    copy: "Copier la transcription", export: "Exporter", open_folder: "Ouvrir le dossier", delete: "Supprimer le cours",
    ai_warning: "Les réponses de l'IA peuvent être fausses. La transcription fait foi.",
    qtype_translate_to_arabic: "Traduire dans la langue du cours"
  }
};
let LANG = "en";
const t = (k, vars) => {
  let s = (STRINGS[LANG] && STRINGS[LANG][k]) || STRINGS.en[k] || k;
  if (vars) for (const v in vars) s = s.replace("{" + v + "}", vars[v]);
  return s;
};

/* ---------- state ---------- */
const S = {
  state: null, view: "home", lessonId: null, lesson: null,
  job: null,            // {id, kind:"transcribe"} while transcribing
  ai: null,             // {kind, lessonId} currently running AI job
  aiTab: null, selSeg: null, pendingQ: null, segCount: 0,
  day: null, dayDate: null, dayTab: "recap", dayJob: null,
  el: null              // {s, at}: elapsed seconds reported by the backend, and when we got it
};
const $ = (id) => document.getElementById(id);
const api = () => window.pywebview && window.pywebview.api;

function applyI18n() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach(e => e.textContent = t(e.dataset.i18n));
  document.querySelectorAll("[data-i18n-ph]").forEach(e => e.placeholder = t(e.dataset.i18nPh));
  const c = $("status-chip"); c.textContent = t("chip_offline"); c.hidden = false;
}
let toastTimer;
function toast(msg, err) {
  const el = $("toast"); el.textContent = msg; el.className = "toast" + (err ? " err" : ""); el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.hidden = true, err ? 6000 : 2500);
}
async function call(name, ...args) {
  try { return await api()[name](...args); }
  catch (e) { toast(String(e && e.message || e), true); return null; }
}
function show(view) {
  S.view = view;
  for (const v of ["home", "record", "working", "lesson", "day"]) $("view-" + v).hidden = v !== view;
  const h = { home: "home-title", record: "rec-title", working: "work-title", lesson: "lesson-title", day: "day-title" }[view];
  const el = $(h); if (el) { el.tabIndex = -1; el.focus({ preventScroll: true }); }
  window.scrollTo(0, 0);
}
function fmtTime(s) {
  if (s == null) return "";
  s = Math.max(0, Math.floor(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  const p = n => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(x)}` : `${m}:${p(x)}`;
}
function fmtDur(s) { return Math.max(1, Math.round((s || 0) / 60)) + " " + t("min"); }
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

/* ---------- home ---------- */
async function loadHome() {
  const st = await call("get_state"); if (!st) return;
  S.state = st;
  const s = st.settings || {};
  LANG = s.ui_lang === "fr" ? "fr" : "en"; applyI18n();
  const sp = Array.isArray(s.spoken_languages) && s.spoken_languages.length ? s.spoken_languages : ["ar", "he"];
  document.querySelectorAll(".opt-lang").forEach(c => c.checked = sp.includes(c.value));
  $("opt-dialect").value = s.arabic_dialect || "msa";
  $("opt-detect").checked = (s.mode || "auto") === "auto";
  S.forcedLang = s.mode && s.mode !== "auto" ? s.mode : null;
  $("opt-hebmodel").checked = s.model === "hebrew";
  $("opt-best").checked = s.model === "best";
  refreshLangUi();
  $("opt-auto").checked = s.auto_recap !== false;
  const fast = st.models && st.models.fast && st.models.fast.installed;
  $("firstrun").hidden = !!fast;
  renderDays(st.days || groupByDay(st.lessons || []));
  show("home");
}
function groupByDay(lessons) {
  const m = {};
  for (const l of lessons) { const d = l.day || String(l.date || "").slice(0, 10); (m[d] = m[d] || []).push(l); }
  return Object.keys(m).sort().reverse().map(d => ({ date: d, parts: m[d].slice().reverse(), has_recap: false,
    total_duration_s: m[d].reduce((a, l) => a + (l.duration_s || 0), 0) }));
}
function fmtDayTitle(date) {
  const dt = new Date(date + "T12:00:00"); if (isNaN(dt)) return date;
  return dt.toLocaleDateString(LANG === "fr" ? "fr-FR" : "en-GB", { weekday: "long", day: "numeric", month: "short" });
}
function lessonItem(l) {
  const li = el("li"), b = el("button", "lesson-item"); b.type = "button";
  const tt = el("span", "t", l.title || t("untitled"));
  const tag = { imported: "status_imported", interrupted: "status_interrupted", cancelled: "status_interrupted", failed: "status_failed", recorded: "status_recorded" }[l.status];
  if (tag) tt.append(el("span", "tag", t(tag)));
  b.append(tt);
  b.append(el("span", "d", [l.duration_s ? fmtDur(l.duration_s) : ""].filter(Boolean).join(" · ")));
  if (l.preview) { const p = el("span", "p", l.preview); p.lang = "ar"; b.append(p); }
  b.onclick = () => openLesson(l.id);
  li.append(b); return li;
}
function renderDays(days) {
  const box = $("day-list"); box.textContent = "";
  $("lessons-empty").hidden = days.length > 0;
  for (const d of days) {
    const sec = el("section", "day"), h = el("button", "day-head"); h.type = "button";
    const tt = el("span", "day-title", fmtDayTitle(d.date));
    if (d.has_recap) tt.append(el("span", "tag", t("tag_recap")));
    h.append(tt);
    const n = d.parts.length;
    h.append(el("span", "d", [n === 1 ? t("day_part_1") : t("day_parts_n", { n }), d.total_duration_s ? fmtDur(d.total_duration_s) : ""].filter(Boolean).join(" · ")));
    h.onclick = () => openDay(d.date);
    const ul = el("ul", "lessons");
    for (const p of d.parts) ul.append(lessonItem(p));
    sec.append(h, ul); box.append(sec);
  }
}
function fmtDate(d) {
  if (!d) return "";
  const dt = new Date(d); if (isNaN(dt)) return String(d);
  return dt.toLocaleDateString(LANG === "fr" ? "fr-FR" : "en-GB", { day: "numeric", month: "short", year: "numeric" });
}
/* Languages of the lessons: checkboxes + dialect (when Arabic is ticked) + "detect automatically". */
const LANG_ORDER = ["ar", "he", "en", "fr"];
function ticked() { return LANG_ORDER.filter(c => { const b = document.querySelector('.opt-lang[value="' + c + '"]'); return b && b.checked; }); }
function refreshLangUi() {
  const sel = ticked();
  $("dialect-row").hidden = !sel.includes("ar");
  $("detect-row").hidden = sel.length < 2;
  const forced = sel.length >= 2 && !$("opt-detect").checked;
  const hint = $("forced-hint"); hint.hidden = !forced;
  if (forced) hint.textContent = t("forced_hint", { lang: t("lang_" + sel[0]) });
  $("hebmodel-row").hidden = !(sel.length === 1 && sel[0] === "he");
}
function currentOpts() {
  let sel = ticked(); if (!sel.length) sel = ["ar"];
  const auto = sel.length >= 2 && $("opt-detect").checked;
  const heb = sel.length === 1 && sel[0] === "he" && $("opt-hebmodel").checked;
  return { model: heb ? "hebrew" : $("opt-best").checked ? "best" : "fast", spoken_languages: sel,
    arabic_dialect: $("opt-dialect").value, mode: auto ? "auto" : sel[0] };
}
function saveOpts() {
  refreshLangUi();
  const o = currentOpts();
  call("set_settings", { spoken_languages: o.spoken_languages, arabic_dialect: o.arabic_dialect, mode: o.mode,
    model: o.model, auto_recap: $("opt-auto").checked });
}
function onLangChange(e) {
  if (!ticked().length) e.target.checked = true;   // at least one language stays ticked
  saveOpts();
}


/* ---------- recording from the microphone ---------- */
const R = { active: false, paused: false, lessonId: null, silent: false };
function fmtClock(s) {
  s = Math.max(0, Math.floor(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60, p = n => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(x)}` : `${m}:${p(x)}`;
}
function recErr(e) {
  const msg = String(e && e.message || e || "");
  const m = /^(?:[\w.]*:)?\s*(NO_MIC|MIC_DENIED|DISK_FULL|MIC_ERROR|BUSY)\b/.exec(msg) || /(NO_MIC|MIC_DENIED|DISK_FULL|MIC_ERROR)/.exec(msg);
  if (m && STRINGS.en["rec_err_" + m[1]]) return t("rec_err_" + m[1]);
  return msg;
}
function recSetState(st) {
  $("rec-state").textContent = st ? t("rec_state_" + st) : "";
  $("btn-rec-start").hidden = R.active;
  $("btn-rec-pause").hidden = !R.active; $("btn-rec-stop").hidden = !R.active;
  $("btn-rec-pause").textContent = t(R.paused ? "rec_resume" : "rec_pause");
  $("rec-device").disabled = R.active;
}
function recHint(msg) { const h = $("rec-hint"); h.textContent = msg || ""; h.hidden = !msg; }
async function openRecord() {
  if (S.job) return;
  R.active = false; R.paused = false; R.lessonId = null;
  $("rec-live").hidden = false; $("rec-done").hidden = true;
  $("rec-time").textContent = "0:00"; $("rec-meter").style.width = "0"; recHint("");
  const sel = $("rec-device"); sel.textContent = "";
  let devs = null;
  try { devs = await api().list_input_devices(); } catch (e) { toast(recErr(e), true); return; }
  for (const d of devs || []) { const o = el("option", "", d.name); o.value = d.id; if (d.default) o.selected = true; sel.append(o); }
  if (!devs || !devs.length) { toast(t("rec_err_NO_MIC"), true); return; }
  recSetState("ready"); show("record");
}
async function recStart() {
  const dev = $("rec-device").value;
  try {
    const r = await api().start_recording({ device_id: dev === "" ? null : +dev });
    R.active = true; R.paused = false; R.lessonId = r.lesson_id; recHint("");
    recSetState("recording");
  } catch (e) { toast(recErr(e), true); }
}
async function recPause() {
  if (!R.active) return;
  const r = await call(R.paused ? "resume_recording" : "pause_recording");
  if (r) { R.paused = !R.paused; recSetState(R.paused ? "paused" : "recording"); }
}
async function recStop() {
  if (!R.active) return;
  const r = await call("stop_recording"); if (!r) return;
  recDone(r);
}
function recDone(r) {
  R.active = false; R.lessonId = r.lesson_id;
  $("rec-live").hidden = true; $("rec-done").hidden = false;
  let msg = t("rec_done_len", { t: fmtClock(r.duration_s) });
  if (r.reason === "device_lost") msg = t("rec_lost") + " " + msg;
  else if (r.reason === "disk_full") msg = t("rec_disk_stopped") + " " + msg;
  $("rec-done-msg").textContent = msg;
  loadHomeSilent();
}
async function recCancel() {
  if (R.active) {
    if (!window.confirm(t("rec_confirm_discard"))) return;
    await call("cancel_recording"); R.active = false;
  }
  loadHome();
}
async function recTranscribeNow() {
  const lid = R.lessonId; if (!lid || S.job) return;
  resetLive(); S.segCount = 0; S.lessonId = lid;
  setWork(t("preparing"), null, null);
  $("work-title").textContent = (S.state && (S.state.lessons || []).find(l => l.id === lid) || {}).title || t("untitled");
  show("working");
  const r = await call("resume_transcription", lid, null);
  if (!r || !r.lesson_id) { openLesson(lid); return; }
  S.job = { id: lid, kind: "transcribe" };
}
function onRecordEvent(p) {
  if (S.view !== "record") return;
  if (p.state === "stopped" && p.final && R.active) { recDone(p); return; }
  if (!R.active) return;
  $("rec-time").textContent = fmtClock(p.elapsed_s);
  const lv = Math.min(1, Math.sqrt(p.level || 0) * 1.6);
  const m = $("rec-meter"); m.style.width = Math.round(lv * 100) + "%"; m.classList.toggle("hot", !!p.peak_clipping);
  recHint(p.silent ? t("rec_silent") : p.peak_clipping ? t("rec_clip") : p.low_disk ? t("rec_low_disk") : "");
}

/* ---------- import ---------- */
const TRANSCRIPT_EXT = /\.(txt|md|srt|vtt)$/i;
async function importTranscript(path) {
  const r = await call("import_transcript", path || null, null);
  if (!r || !r.lesson_id) return;
  toast(t("import_ok")); loadHomeSilent(); openLesson(r.lesson_id);
}

/* ---------- pick / drop ---------- */
async function pickAndStart() {
  const p = await call("pick_audio");
  if (p) startWith(p);
}
async function startWith(path) {
  if (S.job) return;
  S.segCount = 0; S.lessonId = null; resetLive();
  setWork(t("preparing"), null, null);
  $("work-title").textContent = baseName(path);
  show("working");
  const r = await call("start_transcription", path, currentOpts());
  if (!r || !r.lesson_id) { await loadHome(); return; }
  S.job = { id: r.lesson_id, kind: "transcribe" };
  S.lessonId = r.lesson_id;
}
function baseName(p) { return String(p).split(/[\\/]/).pop().replace(/\.[^.]+$/, ""); }

function setupDrop() {
  const dz = $("dropzone");
  dz.addEventListener("click", pickAndStart);
  dz.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickAndStart(); } });
  let depth = 0;
  const hasFiles = e => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
  window.addEventListener("dragenter", e => { if (hasFiles(e)) { depth++; document.body.classList.add("dragging"); } });
  window.addEventListener("dragleave", e => { if (hasFiles(e) && --depth <= 0) { depth = 0; document.body.classList.remove("dragging"); } });
  window.addEventListener("dragover", e => { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener("drop", async e => {
    e.preventDefault(); depth = 0; document.body.classList.remove("dragging");
    if (S.view !== "home") return;
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    const path = f.path || f.pywebviewFullPath;
    const isTr = TRANSCRIPT_EXT.test(f.name || path || "");
    if (path) { if (isTr) importTranscript(path); else startWith(path); }
    else { toast(t("no_path")); if (isTr) importTranscript(null); else pickAndStart(); }
  });
}

/* ---------- working ---------- */
function fmtEta(eta) {
  if (eta < 60) return t("eta_s");
  const m = Math.round(eta / 60);
  return m >= 60 ? t("eta_h", { h: Math.floor(m / 60), m: m % 60 }) : t("eta", { m });
}
function setWork(msg, pct, eta, elapsed) {
  $("work-msg").textContent = msg || "";
  const bar = $("work-bar"), fill = $("work-fill");
  if (pct == null) { bar.classList.add("indet"); bar.removeAttribute("aria-valuenow"); $("work-pct").textContent = ""; }
  else { bar.classList.remove("indet"); fill.style.width = pct + "%"; bar.setAttribute("aria-valuenow", Math.round(pct)); $("work-pct").textContent = Math.round(pct) + "%"; }
  $("work-eta").textContent = eta ? fmtEta(eta) : "";
  if (elapsed != null) S.el = { s: elapsed, at: performance.now() };
  tickElapsed();
}
function tickElapsed() {
  const n = $("work-elapsed");
  if (!S.el || S.view !== "working") { n.textContent = ""; return; }
  n.textContent = t("elapsed", { t: fmtTime(S.el.s + (performance.now() - S.el.at) / 1000) });
}
setInterval(tickElapsed, 1000);

/* Live transcript: append one node per segment, batched per animation frame. Never re-reads or
   re-renders the existing text, so it stays fast with thousands of segments. */
const LIVE = { q: [], raf: 0, n: 0 };
function resetLive() { $("live").textContent = ""; LIVE.q = []; LIVE.n = 0; S.el = null; }
function addLiveSegment(text, lang) {
  LIVE.q.push({ text, lang });
  if (!LIVE.raf) LIVE.raf = requestAnimationFrame(flushLive);
}
function flushLive() {
  LIVE.raf = 0;
  const live = $("live");
  const near = LIVE.n === 0 || live.scrollHeight - live.scrollTop - live.clientHeight < 60;
  const frag = document.createDocumentFragment();
  for (const q of LIVE.q) {
    const sp = el("span", null, (LIVE.n++ ? " " : "") + q.text); sp.dir = "auto"; if (q.lang) sp.lang = q.lang;
    frag.append(sp);
  }
  LIVE.q = [];
  live.append(frag);
  if (near) live.scrollTop = live.scrollHeight;
}

/* ---------- lesson ---------- */
async function openLesson(id) {
  const l = await call("get_lesson", id); if (!l) return;
  S.lessonId = id; S.lesson = l; S.aiTab = null; S.selSeg = null; S.pendingQ = null;
  renderLesson(); show("lesson");
}
async function reloadLesson() {
  const l = await call("get_lesson", S.lessonId); if (!l) return;
  S.lesson = l; renderTranscript(); renderAi();
}
function renderLesson() {
  const m = S.lesson.meta || {};
  $("lesson-title").textContent = m.title || t("untitled");
  $("lesson-meta").textContent = [fmtDate(m.date), m.duration_s ? fmtDur(m.duration_s) : "",
    m.status === "imported" ? t("status_imported") : ""].filter(Boolean).join(" · ");
  renderResume();
  $("lesson-date").hidden = true; $("lesson-date").value = m.day || String(m.date || "").slice(0, 10);
  $("ai-panel").hidden = true;
  document.querySelectorAll(".tool").forEach(b => b.setAttribute("aria-pressed", "false"));
  renderTranscript();
}
function renderTranscript() {
  const box = $("transcript"); box.textContent = "";
  const frag = document.createDocumentFragment();
  const segs = S.lesson.segments || [];
  const multi = new Set(segs.map(x => x.lang).filter(Boolean)).size > 1;   // tags only for mixed lessons
  let prevLang = null;
  segs.forEach((sg, i) => {
    if (multi && sg.lang && sg.lang !== prevLang) frag.append(langTag(sg.lang));
    prevLang = sg.lang || prevLang;
    const sp = el("span", "seg", sg.text); sp.dir = "auto"; if (sg.lang) sp.lang = sg.lang; sp.dataset.i = i;
    if (sg.start != null) { sp.dataset.start = sg.start; sp.tabIndex = 0; sp.setAttribute("role", "button"); }
    else sp.classList.add("nots");
    frag.append(sp, document.createTextNode(" "));
  });
  box.append(frag);
}
function langTag(code) {
  const tg = el("span", "lt", code.toUpperCase()); tg.title = t("lang_" + code); tg.setAttribute("aria-label", t("lang_" + code));
  return tg;
}
function segFromEvent(e) {
  const sp = e.target.closest && e.target.closest(".seg");
  if (!sp || sp.dataset.start === undefined) return null;
  return { sp, i: +sp.dataset.i };
}
function selectSeg(i, sp, sg) {
  document.querySelectorAll(".seg .ts").forEach(n => n.remove());
  const was = S.selSeg === i;
  document.querySelectorAll(".seg.sel").forEach(n => n.classList.remove("sel"));
  S.selSeg = null;
  if (was) return;
  S.selSeg = i; sp.classList.add("sel");
  sp.append(el("span", "ts", fmtTime(sg.start) + " – " + fmtTime(sg.end)));
}
function renderResume() {
  const m = S.lesson.meta || {}, segs = S.lesson.segments || [];
  const can = ["interrupted", "cancelled", "failed", "recorded"].includes(m.status) && m.audio_path && !(S.job && S.job.id === S.lessonId);
  $("resume-box").hidden = !can;
  if (!can) return;
  $("btn-resume").textContent = t(m.status === "recorded" ? "rec_transcribe" : "resume");
  let msg;
  if (m.status === "recorded" && !segs.length) msg = t("rec_not_transcribed");
  else if (!segs.length) msg = t("resume_none");
  else {
    const at = fmtTime(segs[segs.length - 1].end);
    msg = m.duration_s ? t("resume_msg", { at, total: fmtTime(m.duration_s) }) : t("resume_msg_nototal", { at });
  }
  if (!m.audio_ok) msg += " " + t("resume_missing");
  $("resume-msg").textContent = msg;
}
async function resumeLesson() {
  if (S.job) return;
  const m = S.lesson.meta || {}, segs = S.lesson.segments || [];
  let path = null;
  if (!m.audio_ok) { path = await call("pick_audio"); if (!path) return; }
  resetLive(); S.segCount = 0;
  for (const sg of segs) LIVE.q.push({ text: sg.text, lang: sg.lang });
  flushLive();
  const last = segs.length ? segs[segs.length - 1].end : 0;
  setWork(t("preparing"), m.duration_s ? last / m.duration_s * 100 : null, null);
  $("work-title").textContent = m.title || t("untitled");
  show("working");
  const r = await call("resume_transcription", S.lessonId, path);
  if (!r || !r.lesson_id) { openLesson(S.lessonId); return; }
  S.job = { id: S.lessonId, kind: "transcribe" };
}
function seekToSeg(start, index) {
  let best;
  if (start == null) best = document.querySelector('#transcript .seg[data-i="' + (index || 0) + '"]');
  else {
    best = document.querySelector("#transcript .seg");
    for (const n of document.querySelectorAll("#transcript .seg[data-start]")) if (parseFloat(n.dataset.start) <= start) best = n;
  }
  if (best) { best.scrollIntoView({ behavior: "smooth", block: "center" }); if (best.dataset.start !== undefined && !best.classList.contains("sel")) best.click(); }
}

/* ---------- day view: recap and practice questions ---------- */
const gemmaInstalled = () => !!(S.state && S.state.models && S.state.models.gemma && S.state.models.gemma.installed);
async function openDay(date) {
  const d = await call("get_day", date); if (!d) return;
  S.day = d; S.dayDate = date; S.dayTab = S.dayTab || "recap";
  renderDay(); show("day");
}
async function reloadDay() {
  if (!S.dayDate) return;
  const d = await call("get_day", S.dayDate); if (!d) return;
  S.day = d; renderDay();
}
function renderDay() {
  const d = S.day, n = d.parts.length;
  $("day-title").textContent = fmtDayTitle(d.date);
  const dur = d.parts.reduce((a, p) => a + (p.duration_s || 0), 0);
  $("day-meta").textContent = [n === 1 ? t("day_part_1") : t("day_parts_n", { n }), dur ? fmtDur(dur) : ""].filter(Boolean).join(" · ");
  renderDayTranscript(); renderDayPanel();
}
function renderDayTranscript() {
  const box = $("day-transcript"); box.textContent = "";
  const frag = document.createDocumentFragment();
  for (const p of S.day.parts) {
    const sep = el("div", "part-sep");
    const tm = p.date ? new Date(p.date) : null;
    sep.append(el("span", "", p.title || t("untitled")));
    if (tm && !isNaN(tm)) sep.append(el("span", "", tm.toLocaleTimeString(LANG === "fr" ? "fr-FR" : "en-GB", { hour: "2-digit", minute: "2-digit" })));
    const open = el("button", "linkbtn", t("open_part")); open.type = "button"; open.onclick = () => openLesson(p.id);
    sep.append(open); frag.append(sep);
    for (const sg of (S.day.segments_by_part[p.id] || [])) { const sp = el("span", "seg nots", sg.text); sp.dir = "auto"; if (sg.lang) sp.lang = sg.lang; frag.append(sp, document.createTextNode(" ")); }
  }
  box.append(frag);
}
function dayBusy() { return S.dayJob && S.dayJob.date === S.dayDate; }
function renderDayPanel() {
  const tab = S.dayTab, body = $("day-body"); body.textContent = "";
  $("btn-recap").setAttribute("aria-pressed", String(tab === "recap"));
  $("btn-quiz").setAttribute("aria-pressed", String(tab === "quiz"));
  const busy = dayBusy();
  if (!busy) { $("day-status").textContent = ""; $("day-bar").hidden = true; }
  const notes = S.day.notes || {};
  if (tab === "recap") renderRecap(body, notes.recap, busy); else renderQuiz(body, notes.quiz, busy);
}
function cta(label, fn) {
  const w = el("div", "cta"), b = el("button", "btn primary", label); b.type = "button"; b.onclick = fn; w.append(b); return w;
}
function renderRecap(body, rc, busy) {
  if (!rc) {
    if (!busy) { body.append(el("p", "muted", t("recap_none"))); body.append(cta(gemmaInstalled() ? t("recap_make") : t("recap_make_dl"), () => runDay("recap"))); }
    return;
  }
  const w = el("div", "rc");
  if (rc.stale && !busy) {
    const n = el("div", "notice"); n.append(el("div", "", t("recap_stale")));
    const b = el("button", "btn small", t("recap_update")); b.type = "button"; b.style.marginTop = "8px"; b.onclick = () => runDay("recap"); n.append(b); w.append(n);
  }
  if (rc.topic) w.append(textWithArabic(rc.topic, "topic"));
  const list = (key, items) => {
    if (!items || !items.length) return;
    w.append(el("h3", "", t(key)));
    const ul = el("ul"); for (const x of items) { const li = el("li"); li.append(textWithArabic(x, "")); ul.append(li); } w.append(ul);
  };
  list("rc_taught", rc.taught); list("rc_focus", rc.focus);
  if (rc.vocab && rc.vocab.length) {
    w.append(el("h3", "", t("rc_vocab")));
    const tb = el("table", "vocab");
    for (const v of rc.vocab) {
      const tr = el("tr"), a = el("td"), b = el("td");
      const ar = el("div", v.lang === "en" || v.lang === "fr" ? "lat" : "ar", v.arabic); ar.lang = v.lang || "ar"; a.append(ar);
      if (v.transliteration) a.append(el("div", "tr", v.transliteration));
      b.append(el("div", "", v.meaning)); tr.append(a, b); tb.append(tr);
    }
    w.append(tb);
  }
  list("rc_grammar", rc.grammar); list("rc_homework", rc.homework);
  if (rc.unclear_note) w.append(el("p", "muted", t("rc_note") + ": " + rc.unclear_note));
  body.append(w);
}
function quizScore(qz) {
  const marks = qz.marks || {}; const vals = Object.values(marks);
  return { r: vals.filter(v => v === "right").length, m: vals.length };
}
function renderQuiz(body, qz, busy) {
  const qs = qz && qz.questions || [];
  if (!qs.length) {
    if (!busy) { body.append(el("p", "muted", t("quiz_none"))); body.append(cta(gemmaInstalled() ? t("quiz_make") : t("quiz_make_dl"), () => runDay("quiz"))); }
    return;
  }
  const sc = el("div", "score"); sc.id = "quiz-score"; body.append(sc);
  const upd = () => { const x = quizScore(qz); sc.textContent = t("score", x); };
  qs.forEach((q, i) => {
    const card = el("div", "qcard");
    card.append(el("div", "qt", `${i + 1}. ${t("qtype_" + q.type) !== "qtype_" + q.type ? t("qtype_" + q.type) : q.type}`));
    card.append(textWithArabic(q.question, "qq"));
    if (q.options && q.options.length) { const ol = el("ol"); for (const o of q.options) { const li = el("li"); li.append(textWithArabic(o, "")); ol.append(li); } card.append(ol); }
    const ans = el("div", "qa"); ans.hidden = true;
    ans.append(textWithArabic(t("q_answer") + ": " + q.answer, "")); 
    if (q.explanation) ans.append(el("div", "muted", q.explanation));
    if (q.source_hint) ans.append(el("div", "muted small", t("q_source") + ": " + q.source_hint));
    const row = el("div", "row");
    const show = el("button", "btn small", t("show_answer")); show.type = "button";
    show.onclick = () => { ans.hidden = !ans.hidden; show.textContent = t(ans.hidden ? "show_answer" : "hide_answer"); };
    row.append(show);
    const mk = (mark, label) => {
      const b = el("button", "btn small", label); b.type = "button";
      const sync = () => b.setAttribute("aria-pressed", String((qz.marks || {})[q.id] === mark));
      b.onclick = async () => {
        const next = (qz.marks || {})[q.id] === mark ? null : mark;
        const r = await call("set_quiz_mark", S.dayDate, q.id, next); if (!r) return;
        qz.marks = r.marks; row.querySelectorAll("[data-mark]").forEach(x => x.dispatchEvent(new Event("sync"))); upd();
      };
      b.dataset.mark = mark; b.addEventListener("sync", sync); sync(); return b;
    };
    row.append(mk("right", t("right")), mk("wrong", t("wrong")));
    card.append(row, ans); body.append(card);
  });
  upd();
  if (!busy) { const b = el("button", "btn", t("quiz_more")); b.type = "button"; b.onclick = () => runDay("quiz", true); body.append(b); }
}
async function runDay(kind, more) {
  S.dayJob = { id: kind + ":" + S.dayDate, date: S.dayDate, kind };
  S.dayTab = kind; renderDayPanel();
  setDayProgress(t(kind === "recap" ? "recap_working" : "quiz_working"), null);
  const r = kind === "quiz" ? await call("ai_day_quiz", S.dayDate, { more: !!more }) : await call("ai_day_recap", S.dayDate);
  if (r === null || (r && r.cached)) { S.dayJob = null; renderDayPanel(); }
}
function setDayProgress(msg, pct) {
  if (!dayBusy() || S.view !== "day") return;
  $("day-status").textContent = msg;
  const bar = $("day-bar"); bar.hidden = false; bar.classList.toggle("indet", pct == null);
  $("day-fill").style.width = (pct == null ? 30 : pct) + "%";
}
async function exportDay(fmt, withAnswers, what, open) {
  const r = await call("export_day", S.dayDate, fmt, withAnswers, what); if (!r) return;
  if (open) await call("open_file", r.path); else toast(t("saved_to", { p: r.path }));
}

/* ---------- AI panel ---------- */
const AI = {
  summary: { title: "summary_title", btn: "btn-summary", method: "ai_summary" },
  vocab: { title: "vocab_title", btn: "btn-vocab", method: "ai_vocab" },
  outline: { title: "outline_title", btn: "btn-outline", method: "ai_classify" },
  ask: { title: "ask_title", btn: "btn-ask", method: "ai_ask" }
};
function openAi(kind) {
  S.aiTab = kind; renderAi();
  const n = S.lesson.notes || {};
  const have = { summary: n.summary, vocab: n.vocab && n.vocab.length, outline: n.outline && n.outline.length, ask: true }[kind];
  if (!have && !(S.ai && S.ai.kind === kind)) runAi(kind);
  if (kind === "ask") setTimeout(() => $("ask-input").focus(), 0);
}
async function runAi(kind, question) {
  S.ai = { kind, lessonId: S.lessonId };
  renderAi();
  const m = AI[kind].method;
  const r = kind === "ask" ? await call(m, S.lessonId, question) : await call(m, S.lessonId);
  if (r === null && S.ai) { S.ai = null; S.pendingQ = null; renderAi(); }
}
function renderAi() {
  const kind = S.aiTab, panel = $("ai-panel");
  for (const k in AI) $(AI[k].btn).setAttribute("aria-pressed", String(k === kind));
  if (!kind) { panel.hidden = true; return; }
  panel.hidden = false;
  $("ai-title").textContent = t(AI[kind].title);
  const busy = S.ai && S.ai.kind === kind && S.ai.lessonId === S.lessonId;
  const body = $("ai-body"); body.textContent = "";
  $("ask-form").hidden = kind !== "ask";
  if (!busy) { $("ai-status").textContent = ""; $("ai-bar").hidden = true; }
  const n = S.lesson.notes || {};
  if (kind === "summary") {
    if (n.summary) body.append(textWithArabic(n.summary, "ai-text"));
    else if (!busy) body.append(el("p", "muted", t("empty_summary")));
  } else if (kind === "vocab") {
    if (n.vocab && n.vocab.length) {
      const tb = el("table", "vocab");
      for (const v of n.vocab) {
        const tr = el("tr"), a = el("td"), b = el("td");
        const ar = el("div", v.lang === "en" || v.lang === "fr" ? "lat" : "ar", v.arabic); ar.lang = v.lang || "ar"; a.append(ar);
        if (v.transliteration) a.append(el("div", "tr", v.transliteration));
        b.append(el("div", "", v.meaning));
        if (v.note) b.append(el("div", "muted small", v.note));
        tr.append(a, b); tb.append(tr);
      }
      body.append(tb);
    }
  } else if (kind === "outline") {
    if (n.outline && n.outline.length) {
      const ul = el("ul", "outline");
      for (const o of n.outline) {
        const li = el("li"), bt = el("button", "", o.start != null ? fmtTime(o.start) : "#" + (ul.children.length + 1)); bt.type = "button";
        bt.onclick = () => seekToSeg(o.start, o.index);
        const k = o.kind || o.label || "other";
        li.append(bt, el("span", "lab", t("kind_" + k) !== "kind_" + k ? t("kind_" + k) : k));
        if (o.summary) li.append(el("span", "muted", o.summary));
        ul.append(li);
      }
      body.append(ul);
    }
  } else if (kind === "ask") {
    for (const qa of (n.qa || [])) {
      const d = el("div", "qa"); d.append(el("div", "q", qa.q), textWithArabic(qa.a, "a")); body.append(d);
    }
    if (S.pendingQ && busy) { const d = el("div", "qa"); d.append(el("div", "q", S.pendingQ)); body.append(d); }
    $("ask-input").disabled = !!busy;
  }
  if (kind !== "ask" && !busy) {
    const has = { summary: n.summary, vocab: n.vocab && n.vocab.length, outline: n.outline && n.outline.length }[kind];
    if (has) { const b = el("button", "btn small", t("regenerate")); b.type = "button"; b.style.marginTop = "16px"; b.onclick = () => runAi(kind); body.append(b); }
  }
}
// wrap Arabic runs in spans so they render with the Arabic font and correct direction
function textWithArabic(text, cls) {
  const d = el("div", cls); const re = /[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF][\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u064B-\u0652\s]*/g;
  let last = 0, m; text = String(text || "");
  while ((m = re.exec(text))) {
    if (m.index > last) d.append(document.createTextNode(text.slice(last, m.index)));
    const s = el("span", "ar", m[0].trimEnd()); s.lang = "ar"; d.append(s);
    const trail = m[0].slice(m[0].trimEnd().length); if (trail) d.append(document.createTextNode(trail));
    last = m.index + m[0].length;
  }
  if (last < text.length) d.append(document.createTextNode(text.slice(last)));
  return d;
}

/* ---------- events from Python ---------- */
window.__onEvent = async function (name, p) {
  p = p || {};
  if (name === "record") { onRecordEvent(p); return; }
  if (name === "progress") {
    if (p.job === "download") {
      const llm = p.id === "gemma";
      if (S.view === "working" && !llm) setWork(p.message || t("downloading_model"), p.pct, p.eta_s);
      else if (llm && S.dayJob) setDayProgress(p.message || t("downloading_llm"), p.pct);
      else if (llm && S.ai) setAiProgress(p.message || t("downloading_llm"), p.pct);
    } else if (p.job === "transcribe") {
      if (S.view === "working") setWork(p.message || t("transcribing"), p.pct, p.eta_s, p.elapsed_s);
    } else if (p.job === "llm") {
      const m = /^(recap|quiz):(.+)$/.exec(p.id || "");
      if (m) {
        if (!S.dayJob) { S.dayJob = { id: p.id, date: m[2], kind: m[1] }; if (S.view === "day") renderDayPanel(); }
        setDayProgress(p.message || t("thinking"), p.pct);
      } else setAiProgress(p.message || t("thinking"), p.pct);
    }
  } else if (name === "segment") {
    if (S.view === "working" && (!S.lessonId || p.lesson_id === S.lessonId)) {
      if (!S.job) S.job = { id: p.lesson_id, kind: "transcribe" };
      addLiveSegment(p.text, p.lang);
    }
  } else if (name === "done") {
    if (p.job === "transcribe") {
      S.job = null;
      if (p.ok) { openLesson(p.id); toast(t("done_ok")); loadHomeSilent(); }
      else {
        toast(p.error && p.error !== "cancelled" ? `${t("failed")}: ${p.error}` : t("cancelled"), !!p.error && p.error !== "cancelled");
        // keep what was transcribed so far: open the lesson (it offers "Continue transcription")
        let l = null; try { l = await api().get_lesson(p.id); } catch (e) { l = null; }
        if (l && l.segments && l.segments.length) openLesson(p.id); else loadHome();
      }
    } else if (p.job === "download") {
      // a failed download surfaces through the owning job's done event; show errors if nothing else will
      if (p.ok === false && p.error) toast(`${t("failed")}: ${p.error}`, true);
    } else if (p.job === "llm" && (p.kind === "recap" || p.kind === "quiz")) {
      S.dayJob = null;
      if (!p.ok && p.error !== "cancelled") toast(`${t("failed")}${p.error ? ": " + p.error : ""}`, true);
      loadHomeSilent();
      if (S.view === "day" && p.date === S.dayDate) reloadDay();
    } else if (p.job === "llm") {
      const was = S.ai; S.ai = null; S.pendingQ = null;
      if (S.view === "lesson" && was && was.lessonId === S.lessonId) {
        if (!p.ok) { $("ai-status").textContent = ""; toast(`${t("failed")}${p.error ? ": " + p.error : ""}`, true); }
        reloadLesson();
      }
    }
  }
};
function setAiProgress(msg, pct) {
  if (!S.ai) return;
  $("ai-status").textContent = msg;
  const bar = $("ai-bar"); bar.hidden = false;
  bar.classList.toggle("indet", pct == null);
  $("ai-fill").style.width = (pct == null ? 30 : pct) + "%";
}
async function loadHomeSilent() { const st = await call("get_state"); if (st) { S.state = st; renderDays(st.days || groupByDay(st.lessons || [])); $("firstrun").hidden = !!(st.models && st.models.fast && st.models.fast.installed); } }

/* ---------- wiring ---------- */
function wire() {
  $("brand").onclick = () => { if (!S.job) loadHome(); };
  $("btn-firstrun").onclick = pickAndStart;
  $("btn-import").onclick = () => importTranscript(null);
  $("btn-record").onclick = openRecord;
  $("btn-rec-start").onclick = recStart; $("btn-rec-pause").onclick = recPause; $("btn-rec-stop").onclick = recStop;
  $("btn-rec-cancel").onclick = recCancel;
  $("btn-rec-now").onclick = recTranscribeNow; $("btn-rec-later").onclick = () => { toast(t("status_recorded")); loadHome(); };
  $("btn-resume").onclick = resumeLesson;
  $("opt-auto").onchange = saveOpts;
  $("btn-day-back").onclick = loadHome;
  $("btn-recap").onclick = () => { S.dayTab = "recap"; renderDayPanel(); };
  $("btn-quiz").onclick = () => { S.dayTab = "quiz"; renderDayPanel(); };
  $("btn-save-recap").onclick = () => exportDay("md", true, "recap", false);
  $("btn-print-ans").onclick = () => exportDay("html", true, "quiz", true);
  $("btn-print-noans").onclick = () => exportDay("html", false, "quiz", true);
  $("btn-day").onclick = () => { const m = S.lesson.meta || {}; openDay(m.day || String(m.date || "").slice(0, 10)); };
  $("btn-redate").onclick = () => { const i = $("lesson-date"); i.hidden = !i.hidden; if (!i.hidden) i.focus(); };
  $("lesson-date").onchange = async e => {
    const v = e.target.value; if (!v) return;
    const r = await call("set_lesson_date", S.lessonId, v); if (!r) return;
    S.lesson.meta.day = v; e.target.hidden = true; toast(t("day_changed")); loadHomeSilent();
  };
  const tr = $("transcript");
  tr.addEventListener("click", e => { const h = segFromEvent(e); if (h) selectSeg(h.i, h.sp, S.lesson.segments[h.i]); });
  tr.addEventListener("keydown", e => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const h = segFromEvent(e); if (h) { e.preventDefault(); selectSeg(h.i, h.sp, S.lesson.segments[h.i]); }
  });
  document.querySelectorAll(".opt-lang").forEach(c => c.onchange = onLangChange);
  $("opt-dialect").onchange = saveOpts; $("opt-detect").onchange = saveOpts; $("opt-hebmodel").onchange = saveOpts;
  $("opt-best").onchange = saveOpts;
  $("btn-cancel").onclick = () => { if (S.job) call("cancel", S.job.id); };
  $("btn-back").onclick = loadHome;
  $("btn-summary").onclick = () => toggleAi("summary");
  $("btn-vocab").onclick = () => toggleAi("vocab");
  $("btn-outline").onclick = () => toggleAi("outline");
  $("btn-ask").onclick = () => toggleAi("ask");
  $("ai-close").onclick = () => { S.aiTab = null; renderAi(); };
  $("ask-form").onsubmit = e => {
    e.preventDefault();
    const q = $("ask-input").value.trim(); if (!q || S.ai) return;
    $("ask-input").value = ""; S.pendingQ = q; runAi("ask", q);
  };
  $("btn-copy").onclick = async () => {
    const txt = (S.lesson.segments || []).map(s => s.text).join("\n");
    try { await navigator.clipboard.writeText(txt); }
    catch (e) { const ta = el("textarea"); ta.value = txt; document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove(); }
    toast(t("copied"));
  };
  $("btn-export").onclick = async () => { const r = await call("export_lesson", S.lessonId, $("export-fmt").value); if (r !== null) toast(t("exported")); };
  $("btn-folder").onclick = async () => { await call("open_folder", S.lessonId); };
  $("btn-delete").onclick = async () => {
    if (!confirm(t("confirm_delete"))) return;
    await call("delete_lesson", S.lessonId); loadHome();
  };
  $("btn-rename").onclick = startRename;
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && S.view === "lesson" && S.aiTab && document.activeElement.tagName !== "INPUT") { S.aiTab = null; renderAi(); }
  });
}
function toggleAi(kind) { if (S.aiTab === kind) { S.aiTab = null; renderAi(); } else openAi(kind); }
function startRename() {
  const h = $("lesson-title"), inp = el("input"); inp.type = "text"; inp.value = h.textContent; inp.setAttribute("aria-label", t("rename"));
  h.replaceWith(inp); inp.focus(); inp.select();
  let done = false;
  const finish = async (save) => {
    if (done) return; done = true;
    const v = inp.value.trim();
    if (save && v && v !== h.textContent) { await call("rename_lesson", S.lessonId, v); h.textContent = v; S.lesson.meta.title = v; }
    inp.replaceWith(h);
  };
  inp.onkeydown = e => { if (e.key === "Enter") finish(true); else if (e.key === "Escape") finish(false); };
  inp.onblur = () => finish(true);
}

/* ---------- boot ---------- */
async function init() {
  applyI18n(); wire(); setupDrop();
  if (!api()) { toast(t("api_missing"), true); return; }
  loadHome();
}
function boot() {
  applyI18n();
  const mock = new URLSearchParams(location.search).get("mock") === "1";
  if (api()) return init();
  if (mock) {
    const s = document.createElement("script"); s.src = "mock_api.js"; s.onload = init;
    s.onerror = () => toast("mock_api.js failed to load", true); document.head.append(s);
  } else {
    let started = false;
    window.addEventListener("pywebviewready", () => { started = true; init(); });
    setTimeout(() => { if (!started && !api()) toast(t("api_missing"), true); else if (!started) { started = true; init(); } }, 4000);
  }
}
boot();
