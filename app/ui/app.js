"use strict";
/* Arabic Lesson Scribe UI. Vanilla JS, no dependencies. */

const STRINGS = {
  en: {
    app_name: "Arabic Lesson Scribe",
    drop_title: "Drop a recording here or click to choose",
    drop_hint: "mp3, m4a, wav, ogg, opus, amr, 3gp, mp4, flac",
    opt_mixed: "Lesson mixes languages",
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
    chip_offline: "Works offline",
    untitled: "Untitled lesson",
    min: "min",
    api_missing: "Backend not available.",
    kind_vocabulary: "vocabulary", kind_grammar: "grammar", kind_dialogue: "dialogue",
    kind_explanation: "explanation", kind_homework: "homework", kind_other: "other"
  },
  it: { // stub: missing keys fall back to English
    app_name: "Arabic Lesson Scribe",
    drop_title: "Trascina qui una registrazione o clicca per sceglierla",
    opt_mixed: "La lezione mescola più lingue",
    opt_best: "Qualità migliore (più lenta)",
    lessons_title: "Le tue lezioni",
    cancel: "Annulla", back: "Indietro", rename: "Rinomina",
    summary: "Riassunto", vocab: "Vocabolario", outline: "Schema", ask: "Fai una domanda",
    copy: "Copia trascrizione", export: "Esporta", open_folder: "Apri cartella", delete: "Elimina lezione",
    ai_warning: "Le risposte dell'IA possono essere sbagliate. La trascrizione è la fonte affidabile."
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
  aiTab: null, selSeg: null, pendingQ: null, segCount: 0
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
  for (const v of ["home", "working", "lesson"]) $("view-" + v).hidden = v !== view;
  const h = { home: "home-title", working: "work-title", lesson: "lesson-title" }[view];
  const el = $(h); if (el) { el.tabIndex = -1; el.focus({ preventScroll: true }); }
  window.scrollTo(0, 0);
}
function fmtTime(s) {
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
  LANG = s.ui_lang === "it" ? "it" : "en"; applyI18n();
  $("opt-mixed").checked = !!s.mixed_languages;
  $("opt-best").checked = s.model === "best";
  const fast = st.models && st.models.fast && st.models.fast.installed;
  $("firstrun").hidden = !!fast;
  renderLessons(st.lessons || []);
  show("home");
}
function renderLessons(list) {
  const ul = $("lesson-list"); ul.textContent = "";
  $("lessons-empty").hidden = list.length > 0;
  for (const l of list) {
    const li = el("li"), b = el("button", "lesson-item"); b.type = "button";
    b.append(el("span", "t", l.title || t("untitled")));
    b.append(el("span", "d", [fmtDate(l.date), fmtDur(l.duration_s)].filter(Boolean).join(" · ")));
    if (l.preview) { const p = el("span", "p", l.preview); p.lang = "ar"; b.append(p); }
    b.onclick = () => openLesson(l.id);
    li.append(b); ul.append(li);
  }
}
function fmtDate(d) {
  if (!d) return "";
  const dt = new Date(d); if (isNaN(dt)) return String(d);
  return dt.toLocaleDateString(LANG === "it" ? "it-IT" : "en-GB", { day: "numeric", month: "short", year: "numeric" });
}
function currentOpts() {
  return { model: $("opt-best").checked ? "best" : "fast", language: $("opt-mixed").checked ? "auto" : "ar" };
}
function saveOpts() {
  call("set_settings", { mixed_languages: $("opt-mixed").checked, model: currentOpts().model });
}

/* ---------- pick / drop ---------- */
async function pickAndStart() {
  const p = await call("pick_audio");
  if (p) startWith(p);
}
async function startWith(path) {
  if (S.job) return;
  S.segCount = 0; $("live").textContent = "";
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
    if (path) startWith(path);
    else { toast(t("no_path")); pickAndStart(); }
  });
}

/* ---------- working ---------- */
function setWork(msg, pct, eta) {
  $("work-msg").textContent = msg || "";
  const bar = $("work-bar"), fill = $("work-fill");
  if (pct == null) { bar.classList.add("indet"); bar.removeAttribute("aria-valuenow"); $("work-pct").textContent = ""; }
  else { bar.classList.remove("indet"); fill.style.width = pct + "%"; bar.setAttribute("aria-valuenow", Math.round(pct)); $("work-pct").textContent = Math.round(pct) + "%"; }
  $("work-eta").textContent = eta ? (eta < 60 ? t("eta_s") : t("eta", { m: Math.round(eta / 60) })) : "";
}
function addLiveSegment(text) {
  const live = $("live");
  const near = live.scrollHeight - live.scrollTop - live.clientHeight < 60;
  live.append(document.createTextNode((live.textContent ? " " : "") + text));
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
  $("lesson-meta").textContent = [fmtDate(m.date), m.duration_s ? fmtDur(m.duration_s) : ""].filter(Boolean).join(" · ");
  $("ai-panel").hidden = true;
  document.querySelectorAll(".tool").forEach(b => b.setAttribute("aria-pressed", "false"));
  renderTranscript();
}
function renderTranscript() {
  const box = $("transcript"); box.textContent = "";
  for (const [i, sg] of (S.lesson.segments || []).entries()) {
    const sp = el("span", "seg", sg.text); sp.dir = "auto"; sp.dataset.i = i; sp.dataset.start = sg.start;
    sp.tabIndex = 0; sp.setAttribute("role", "button");
    const toggle = () => selectSeg(i, sp, sg);
    sp.onclick = toggle; sp.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } };
    box.append(sp, document.createTextNode(" "));
  }
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
function seekToSeg(start) {
  const nodes = Array.from(document.querySelectorAll(".seg"));
  let best = nodes[0];
  for (const n of nodes) if (parseFloat(n.dataset.start) <= start) best = n;
  if (best) { best.scrollIntoView({ behavior: "smooth", block: "center" }); best.click(); }
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
        const ar = el("div", "ar", v.arabic); ar.lang = "ar"; a.append(ar);
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
        const li = el("li"), bt = el("button", "", fmtTime(o.start)); bt.type = "button";
        bt.onclick = () => seekToSeg(o.start);
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
window.__onEvent = function (name, p) {
  p = p || {};
  if (name === "progress") {
    if (p.job === "download") {
      const llm = p.id === "gemma";
      if (S.view === "working" && !llm) setWork(p.message || t("downloading_model"), p.pct, p.eta_s);
      else if (llm && S.ai) setAiProgress(p.message || t("downloading_llm"), p.pct);
    } else if (p.job === "transcribe") {
      if (S.view === "working") setWork(p.message || t("transcribing"), p.pct, p.eta_s);
    } else if (p.job === "llm") {
      setAiProgress(p.message || t("thinking"), p.pct);
    }
  } else if (name === "segment") {
    if (S.view === "working" && (!S.lessonId || p.lesson_id === S.lessonId)) {
      if (!S.job) S.job = { id: p.lesson_id, kind: "transcribe" };
      addLiveSegment(p.text);
    }
  } else if (name === "done") {
    if (p.job === "transcribe") {
      S.job = null;
      if (p.ok) { openLesson(p.id); toast(t("done_ok")); loadHomeSilent(); }
      else { toast(p.error ? `${t("failed")}: ${p.error}` : t("cancelled"), !!p.error); loadHome(); }
    } else if (p.job === "download") {
      // a failed download surfaces through the owning job's done event; show errors if nothing else will
      if (p.ok === false && p.error) toast(`${t("failed")}: ${p.error}`, true);
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
async function loadHomeSilent() { const st = await call("get_state"); if (st) { S.state = st; renderLessons(st.lessons || []); $("firstrun").hidden = true; } }

/* ---------- wiring ---------- */
function wire() {
  $("brand").onclick = () => { if (!S.job) loadHome(); };
  $("btn-firstrun").onclick = pickAndStart;
  $("opt-mixed").onchange = saveOpts; $("opt-best").onchange = saveOpts;
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
