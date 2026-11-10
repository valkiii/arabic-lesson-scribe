"""Languages of a lesson: settings normalisation, per-language prompts, script checks, and the pure
logic for restricted per-window language detection (no heavy imports, easy to unit test)."""
from __future__ import annotations

import re

SUPPORTED = ("ar", "he", "en", "fr")          # canonical order, also the order shown in the UI
NAMES = {"ar": "Arabic", "he": "Hebrew", "en": "English", "fr": "French"}
DIALECTS = ("msa", "levantine", "egyptian", "gulf", "maghrebi")
DEFAULT_SPOKEN = ["ar", "he"]
DEFAULT_DIALECT = "msa"

# Whisper has no dialect switch. These prompts are written in the dialect (or MSA) and only nudge
# vocabulary and spelling of the output; they do not make the model understand a dialect better.
PROMPTS = {
    "ar": {
        "msa": "مرحبا بكم في هذا الدرس. سنتعلم اليوم كلمات جديدة، وقواعد اللغة العربية.",
        "levantine": "أهلا وسهلا، كيفك اليوم؟ شو رأيك نتعلم كلمات جديدة؟ هلق بدي إياكم تكرروا ورايي. "
                     "ما بعرف، ليش هيك؟ إنشالله منتعلم كتير.",
        "egyptian": "أهلا بيكم في الدرس. النهارده هنتعلم كلمات جديدة. إزيك؟ عايز أسمعكم تكرروا ورايا. "
                    "مش فاهم، ليه كده؟ إن شاء الله هنتعلم كتير.",
        "gulf": "هلا والله، شلونكم اليوم؟ اليوم بنتعلم كلمات جديدة. أبغى منكم تعيدون ورايي. "
                "مب فاهم، ليش جذي؟ إن شاء الله نتعلم زين.",
        "maghrebi": "مرحبا بيكم فهاد الدرس. اليوم غادي نتعلمو كلمات جداد. كيداير؟ بغيت نسمعكم تعاودو معايا. "
                    "ما فهمتش، علاش هاكا؟ إن شاء الله نتعلمو بزاف.",
    },
    "he": "שלום וברוכים הבאים לשיעור. היום נלמד מילים חדשות. אפשר לשאול שאלה? מה זה אומר?",
    "en": "Hello, and welcome to the lesson. Today we will learn new words. Can I ask a question?",
    "fr": "Bonjour et bienvenue au cours. Aujourd'hui, nous allons apprendre de nouveaux mots. Puis-je poser une question ?",
}


def prompt_for(lang: str, dialect: str = DEFAULT_DIALECT) -> str | None:
    p = PROMPTS.get(lang)
    if isinstance(p, dict):
        return p.get(dialect) or p[DEFAULT_DIALECT]
    return p


# ---- settings -------------------------------------------------------------
def norm_spoken(v) -> list[str]:
    """Supported language codes in canonical order, no duplicates; never empty."""
    got = {str(x).lower() for x in (v if isinstance(v, (list, tuple, set)) else [v] if v else [])}
    out = [c for c in SUPPORTED if c in got]
    return out or list(DEFAULT_SPOKEN)


def norm_dialect(v) -> str:
    v = str(v or "").lower()
    return v if v in DIALECTS else DEFAULT_DIALECT


def norm_mode(v) -> str:
    v = str(v or "auto").lower()
    return v if v == "auto" or v in SUPPORTED else "auto"


def resolve(spoken, mode, dialect=DEFAULT_DIALECT) -> dict:
    """The transcription plan: {kind: 'forced'|'auto', languages: [...], dialect}.
    'auto' needs two or more languages; with one it is the same as forcing it."""
    sp = norm_spoken(spoken)
    mode = norm_mode(mode)
    if mode != "auto":
        return {"kind": "forced", "languages": [mode], "dialect": norm_dialect(dialect)}
    if len(sp) == 1:
        return {"kind": "forced", "languages": sp, "dialect": norm_dialect(dialect)}
    return {"kind": "auto", "languages": sp, "dialect": norm_dialect(dialect)}


def migrate_settings(raw: dict) -> dict:
    """Old settings had a boolean mixed_languages. true -> auto between Arabic and Hebrew, false -> forced Arabic."""
    out = dict(raw)
    if "mixed_languages" in out:
        old = out.pop("mixed_languages")
        if "mode" not in out and "spoken_languages" not in out:
            out["spoken_languages"] = list(DEFAULT_SPOKEN)
            out["mode"] = "auto" if old else "ar"
    return out


# ---- scripts --------------------------------------------------------------
ARABIC_RE = re.compile(r"[؀-ۿ]")
HEBREW_RE = re.compile(r"[֐-׿]")
_HE_MARKS = re.compile(r"[֑-ׇ]")           # cantillation and niqqud
_HE_FINAL = str.maketrans("ךםןףץ", "כמנפצ")          # final letters -> regular
_AR_DIAC = re.compile(r"[ً-ْٰـ]")


def has_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(str(text or "")))


def has_hebrew(text: str) -> bool:
    return bool(HEBREW_RE.search(str(text or "")))


def script_of(text: str) -> str | None:
    """'ar' or 'he' when the text contains that script, else None."""
    a, h = len(ARABIC_RE.findall(text or "")), len(HEBREW_RE.findall(text or ""))
    if not a and not h:
        return None
    return "ar" if a >= h else "he"


def norm_he(text: str) -> str:
    """Hebrew comparison form: no niqqud, no cantillation, final letters folded."""
    return _HE_MARKS.sub("", str(text or "")).replace("־", "-").translate(_HE_FINAL)


def norm_ar(text: str) -> str:
    t = _AR_DIAC.sub("", str(text or ""))
    return t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")


def norm_text(text: str) -> str:
    """Normalise Arabic and Hebrew at once (both leave other scripts untouched)."""
    return norm_he(norm_ar(text))


_AR_WORD = re.compile(r"[؀-ۿ]+")
_HE_WORD = re.compile(r"[֐-׿]+")


def in_transcript(term: str, norm_transcript: str) -> bool:
    """True when every Arabic or Hebrew word (3+ letters for Arabic after dropping the article, 2+ for
    Hebrew) of `term` occurs in the already normalised transcript. A term in another script has nothing
    to check and passes; a term with no word to check also passes."""
    for w in _AR_WORD.findall(norm_ar(term)):
        w = w[2:] if w.startswith("ال") and len(w) > 4 else w
        if len(w) >= 3 and w not in norm_transcript:
            return False
    for w in _HE_WORD.findall(norm_he(term)):
        # Hebrew prefixes (ה ו ב ל מ ש כ) glue to the next word: accept the bare stem too
        stem = w[1:] if len(w) > 3 and w[0] in "הובלמשכ" else w
        if len(stem) >= 2 and stem not in norm_transcript:
            return False
    return True


def lesson_languages(segments: list[dict], meta: dict | None = None) -> list[str]:
    """Languages of a lesson: those found in the segments' 'lang' field, else the stored selection."""
    seen = {s.get("lang") for s in segments if s.get("lang")}
    got = [c for c in SUPPORTED if c in seen]
    if got:
        return got
    if meta:
        return norm_spoken(meta.get("languages") or ["ar"])
    return ["ar"]


def target_names(langs: list[str]) -> str:
    return ", ".join(NAMES[c] for c in langs if c in NAMES) or "Arabic"


# ---- restricted detection --------------------------------------------------
def restrict_probs(all_probs, allowed) -> dict:
    """Keep only the allowed languages and renormalise (so a language that is not used cannot win).
    all_probs is faster-whisper's [(lang, prob), ...] or a dict. The key '_mass' carries how much of the
    original probability the allowed languages held; low mass means Whisper thought it was something else."""
    items = dict(all_probs)
    allowed = list(allowed)
    mass = sum(float(items.get(c, 0.0)) for c in allowed)
    if mass <= 1e-9:
        out = {c: 1.0 / len(allowed) for c in allowed}
        out["_mass"] = 0.0
        return out
    out = {c: float(items.get(c, 0.0)) / mass for c in allowed}
    out["_mass"] = mass
    return out


def top(probs: dict) -> tuple[str, float]:
    best = max((c for c in probs if c != "_mass"), key=lambda c: probs[c])
    return best, probs[best]


MIN_MASS = 0.10   # below this the allowed languages together got almost no probability


def confidence_needed(dur: float) -> float:
    """Short windows must be clearly one language to keep their own; long ones may be less sure."""
    if dur < 2.0:
        return 0.92
    if dur < 5.0:
        return 0.80
    if dur < 10.0:
        return 0.55
    return 0.45


def decide_language(probs: dict, dur: float, prev: str | None = None, next_probs: dict | None = None,
                    gap_prev: float | None = None, gap_next: float | None = None) -> str:
    """Language for one window. Its own restricted argmax wins when confident enough for its length;
    otherwise it inherits from the previous (already decided) window or the next window's argmax,
    whichever is closer in time (ties: the one the window itself rates higher, then the previous)."""
    own, conf = top(probs)
    mass = probs.get("_mass", 1.0)
    if mass < MIN_MASS:  # not any of our languages: do not trust the argmax at all
        conf *= mass / MIN_MASS
    if conf >= confidence_needed(dur):
        return own
    cands: list[tuple[str, float]] = []
    if prev:
        cands.append((prev, gap_prev if gap_prev is not None else 0.0))
    if next_probs:
        n_lang = top(next_probs)[0]
        cands.append((n_lang, gap_next if gap_next is not None else 0.0))
    if not cands:
        return own
    if len(cands) == 2 and cands[0][0] != cands[1][0]:
        a, b = cands
        if abs(a[1] - b[1]) > 1.0:                     # one side is clearly closer in time
            return a[0] if a[1] < b[1] else b[0]
        return a[0] if probs.get(a[0], 0) >= probs.get(b[0], 0) else b[0]
    return cands[0][0]


def smooth_languages(windows: list[dict], start_lang: str | None = None) -> list[str]:
    """Batch version of decide_language over windows [{start, end, probs}] (used by tests and tools;
    the transcriber runs the same decisions with a one-window lookahead)."""
    out: list[str] = []
    for i, w in enumerate(windows):
        nxt = windows[i + 1] if i + 1 < len(windows) else None
        prev = out[-1] if out else start_lang
        gp = (w["start"] - windows[i - 1]["end"]) if i else None
        gn = (nxt["start"] - w["end"]) if nxt else None
        out.append(decide_language(w["probs"], w["end"] - w["start"], prev, nxt["probs"] if nxt else None, gp, gn))
    return out


# ---- windows ---------------------------------------------------------------
MIN_WINDOW_S = 1.2
MAX_WINDOW_S = 30.0
MAX_RUN_GAP_S = 3.0


def build_windows(chunks: list[tuple[float, float]], min_len: float = MIN_WINDOW_S,
                  max_len: float = MAX_WINDOW_S) -> list[tuple[float, float]]:
    """Speech chunks (start, end) in seconds -> detection windows. A chunk shorter than min_len (a cough,
    a clipped word) is merged into its nearer neighbour so it does not get a language of its own."""
    wins = [list(c) for c in chunks if c[1] > c[0]]
    i = 0
    while i < len(wins):
        w = wins[i]
        if w[1] - w[0] < min_len and len(wins) > 1:
            gp = w[0] - wins[i - 1][1] if i > 0 else None
            gn = wins[i + 1][0] - w[1] if i + 1 < len(wins) else None
            tgt = None
            if gp is not None and gp <= MAX_RUN_GAP_S and (gn is None or gp <= gn):
                tgt = i - 1
            elif gn is not None and gn <= MAX_RUN_GAP_S:
                tgt = i + 1
            if tgt is not None:
                t = wins[tgt]
                if max(t[1], w[1]) - min(t[0], w[0]) <= max_len:
                    t[0], t[1] = min(t[0], w[0]), max(t[1], w[1])
                    del wins[i]
                    continue
        i += 1
    return [(a, b) for a, b in wins]


COARSE_ACCEPT = 0.995     # restricted top probability of a whole block needed to skip per-window detection
BLOCK_SPEECH_S = 28.0     # speech seconds per block (one Whisper window is 30 s)


def make_blocks(windows: list[tuple[float, float]], max_speech: float = BLOCK_SPEECH_S) -> list[list[int]]:
    """Indices of consecutive windows whose speech adds up to at most max_speech seconds."""
    blocks: list[list[int]] = []
    cur: list[int] = []
    total = 0.0
    for i, (a, b) in enumerate(windows):
        d = b - a
        if cur and total + d > max_speech:
            blocks.append(cur)
            cur, total = [], 0.0
        cur.append(i)
        total += d
    if cur:
        blocks.append(cur)
    return blocks


class BlockDetector:
    """Detection that costs about one model pass per 30 s of speech when the audio is clearly one language,
    and one pass per window when it is not (a language switch hides inside a block with high probability,
    so a block is only trusted when its restricted top probability is very high).

    detect_many(windows) -> restricted probs of the concatenated windows; detect_one(window) -> the same
    for one window. Call the instance with a window; results are cached per block."""

    def __init__(self, windows, detect_many, detect_one, accept: float = COARSE_ACCEPT):
        self.windows = list(windows)
        self.detect_many, self.detect_one, self.accept = detect_many, detect_one, accept
        self.index = {w: i for i, w in enumerate(self.windows)}
        self.blocks = make_blocks(self.windows)
        self.block_of = {i: bi for bi, blk in enumerate(self.blocks) for i in blk}
        self.coarse: dict[int, dict | None] = {}
        self.passes = 0

    def __call__(self, w):
        i = self.index[w]
        bi = self.block_of[i]
        blk = self.blocks[bi]
        if len(blk) > 1:
            if bi not in self.coarse:
                self.passes += 1
                pr = self.detect_many([self.windows[j] for j in blk])
                self.coarse[bi] = pr if top(pr)[1] >= self.accept and pr.get("_mass", 1.0) >= 0.5 else None
            if self.coarse[bi] is not None:
                return self.coarse[bi]
        self.passes += 1
        return self.detect_one(w)


def iter_runs(windows: list[tuple[float, float]], detect, max_span: float = MAX_WINDOW_S,
              max_gap: float = MAX_RUN_GAP_S):
    """Decide a language for every window (detect(window) -> restricted probs; called lazily, one window
    ahead) and yield transcription runs (start, end, lang): consecutive windows of the same language
    close in time are joined up to max_span seconds, so the model sees whole sentences and the number
    of decoding passes stays near the plain (single language) case."""
    probs: dict[int, dict] = {}

    def get(i):
        if i not in probs:
            probs[i] = detect(windows[i])
        return probs[i]

    run = None
    prev = None
    for i, (a, b) in enumerate(windows):
        nxt_p = get(i + 1) if i + 1 < len(windows) else None
        gp = (a - windows[i - 1][1]) if i else None
        gn = (windows[i + 1][0] - b) if i + 1 < len(windows) else None
        lang = decide_language(get(i), b - a, prev, nxt_p, gp, gn)
        prev = lang
        probs.pop(i - 1, None)
        if run and run[2] == lang and a - run[1] <= max_gap and b - run[0] <= max_span:
            run = (run[0], b, lang)
            continue
        if run:
            yield run
        run = (a, b, lang)
    if run:
        yield run
