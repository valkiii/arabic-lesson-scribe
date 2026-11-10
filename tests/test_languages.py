"""Languages: settings migration, restricted per-window detection and smoothing, the transcription
orchestration (with a fake model), Hebrew-aware checks for the assistant, and one real integration test."""
import json
import shutil
import subprocess
import sys
import threading
import types
import wave
from pathlib import Path

import numpy as np
import pytest

from app import config, langs, llm, transcriber

ROOT = Path(__file__).resolve().parent.parent


# ---- settings -------------------------------------------------------------
def _write_settings(d: dict):
    (config.data_dir() / "settings.json").write_text(json.dumps(d), encoding="utf-8")


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("ALS_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


def test_defaults(data):
    s = config.load_settings()
    assert s["spoken_languages"] == ["ar", "he"] and s["arabic_dialect"] == "msa" and s["mode"] == "auto"
    assert "mixed_languages" not in s


def test_migrate_mixed_languages(data):
    _write_settings({"mixed_languages": True, "model": "best"})
    s = config.load_settings()
    assert s["mode"] == "auto" and s["spoken_languages"] == ["ar", "he"] and s["model"] == "best"
    assert "mixed_languages" not in s
    _write_settings({"mixed_languages": False})
    s = config.load_settings()
    assert s["mode"] == "ar"
    assert langs.resolve(s["spoken_languages"], s["mode"])["kind"] == "forced"
    config.save_settings({"model": "fast"})  # saving rewrites the file without the old key
    raw = json.loads((config.data_dir() / "settings.json").read_text(encoding="utf-8"))
    assert "mixed_languages" not in raw and raw["mode"] == "ar"


def test_settings_are_sanitised(data):
    s = config.save_settings({"spoken_languages": ["he", "xx", "ar", "he"], "arabic_dialect": "klingon", "mode": "de"})
    assert s["spoken_languages"] == ["ar", "he"] and s["arabic_dialect"] == "msa" and s["mode"] == "auto"
    assert config.save_settings({"spoken_languages": []})["spoken_languages"] == ["ar", "he"]


def test_italian_ui_setting_migrates_to_english(data):
    _write_settings({"ui_lang": "it"})
    assert config.load_settings()["ui_lang"] == "en"
    _write_settings({"ui_lang": "fr"})
    assert config.load_settings()["ui_lang"] == "fr"
    assert "it" not in langs.SUPPORTED and "fr" in langs.SUPPORTED
    assert langs.norm_spoken(["it", "fr"]) == ["fr"]
    assert "French" in llm.render("summary", "fr", text="x")


def test_resolve_plan():
    assert langs.resolve(["ar"], "auto") == {"kind": "forced", "languages": ["ar"], "dialect": "msa"}
    assert langs.resolve(["ar", "he"], "auto", "levantine")["kind"] == "auto"
    assert langs.resolve(["ar", "he"], "he")["languages"] == ["he"]


def test_prompts_per_language_and_dialect():
    lev, msa = langs.prompt_for("ar", "levantine"), langs.prompt_for("ar", "msa")
    assert lev != msa and "شو" in lev and "هلق" in lev and "كيفك" in lev and "بدي" in lev
    assert all(langs.prompt_for("ar", d) for d in langs.DIALECTS)
    assert langs.has_hebrew(langs.prompt_for("he"))
    assert langs.prompt_for("ar", "nonsense") == msa
    assert all(langs.prompt_for(c) for c in langs.SUPPORTED)


def test_hebrew_model_entry_is_opt_in():
    m = config.MODELS["hebrew"]
    assert m["repo"].startswith("ivrit-ai/") and m["only_languages"] == ["he"]
    assert config.DEFAULT_SETTINGS["model"] == "fast"
    from app import api as api_mod
    with pytest.raises(ValueError):  # a one-language fine-tune must not be used for mixed lessons
        api_mod.Api._check_model_languages("hebrew", langs.resolve(["ar", "he"], "auto"))
    api_mod.Api._check_model_languages("hebrew", langs.resolve(["he"], "auto"))
    api_mod.Api._check_model_languages("fast", langs.resolve(["ar", "he"], "auto"))


# ---- restriction and smoothing (synthetic probabilities) -------------------
def probs(**kw):
    return [(k, v) for k, v in sorted(kw.items(), key=lambda x: -x[1])]


def test_restrict_removes_other_languages_and_renormalises():
    r = langs.restrict_probs(probs(fa=0.5, ar=0.3, he=0.15, en=0.05), ["ar", "he"])
    assert set(r) == {"ar", "he", "_mass"}
    assert r["ar"] == pytest.approx(0.3 / 0.45) and r["he"] == pytest.approx(0.15 / 0.45)
    assert r["_mass"] == pytest.approx(0.45)
    assert langs.top(r)[0] == "ar"


def test_restrict_can_never_return_a_language_that_is_not_allowed():
    # Whisper is sure it is English, but English is not in the lesson: Hebrew still beats Arabic here
    r = langs.restrict_probs(probs(en=0.9, he=0.06, ar=0.04), ["ar", "he"])
    assert langs.top(r)[0] == "he"
    assert langs.decide_language(r, 12.0) in ("ar", "he")


def test_restrict_with_no_mass_is_uniform_and_distrusted():
    r = langs.restrict_probs(probs(fr=1.0), ["ar", "he"])
    assert r["ar"] == r["he"] == 0.5 and r["_mass"] == 0
    assert langs.decide_language(r, 20.0, prev="he") == "he"  # no information: inherit


def test_short_windows_need_confidence():
    unsure = langs.restrict_probs(probs(ar=0.35, he=0.65), ["ar", "he"])
    sure = langs.restrict_probs(probs(ar=0.02, he=0.98), ["ar", "he"])
    assert langs.decide_language(unsure, 1.0, prev="ar") == "ar"          # a one-second window inherits
    assert langs.decide_language(sure, 1.0, prev="ar") == "he"            # unless it is clearly Hebrew
    assert langs.decide_language(unsure, 12.0, prev="ar") == "he"         # long windows trust themselves
    assert langs.decide_language(unsure, 3.0, prev="ar") == "ar" and langs.decide_language(unsure, 3.0) == "he"


def test_inherit_picks_nearer_neighbour():
    unsure = langs.restrict_probs(probs(ar=0.5, he=0.5), ["ar", "he"])
    nxt = langs.restrict_probs(probs(he=0.95, ar=0.05), ["ar", "he"])
    assert langs.decide_language(unsure, 1.0, "ar", nxt, gap_prev=5.0, gap_next=0.8) == "he"
    assert langs.decide_language(unsure, 1.0, "ar", nxt, gap_prev=0.8, gap_next=5.0) == "ar"


def test_low_mass_lowers_confidence():
    # 99% "Hebrew" among the allowed, but they hold 1% of Whisper's mass: it was noise or music
    r = langs.restrict_probs(probs(zz=0.99, he=0.0099, ar=0.0001), ["ar", "he"])
    assert langs.decide_language(r, 4.0, prev="ar") == "ar"


def test_smooth_sequence():
    def w(a, b, **p):
        return {"start": a, "end": b, "probs": langs.restrict_probs(probs(**p), ["ar", "he", "en"])}
    seq = [w(0, 9, ar=0.9, he=0.05, en=0.05),
           w(10, 11, ar=0.4, he=0.35, en=0.25),                   # a coughed word between two Arabic sentences
           w(12, 20, ar=0.95, he=0.03, en=0.02),
           w(21, 23.5, he=0.97, ar=0.02, en=0.01),                # a clear Hebrew question
           w(24, 25, en=0.5, he=0.3, ar=0.2),                     # short and unsure, next to Hebrew
           w(30, 40, en=0.9, he=0.05, ar=0.05)]
    assert langs.smooth_languages(seq) == ["ar", "ar", "ar", "he", "he", "en"]


def test_build_windows_merges_tiny_neighbours():
    wins = langs.build_windows([(0, 8), (8.5, 9.0), (12, 20), (40, 40.3), (60, 65)])
    assert wins[0] == (0, 9.0)                       # the half second joined its nearer neighbour
    assert (12, 20) in wins and (60, 65) in wins and (40, 40.3) in wins   # too far from anything to merge
    assert langs.build_windows([(0, 29.5), (29.7, 30.2)]) == [(0, 29.5), (29.7, 30.2)]   # never beyond 30 s
    assert langs.build_windows([(3, 3.4)]) == [(3, 3.4)]


def test_iter_runs_joins_same_language_and_calls_detect_lazily():
    calls = []
    table = {0: "ar", 1: "ar", 2: "he", 3: "ar", 4: "ar"}
    wins = [(0, 8), (9, 17), (18, 21), (22, 28), (29, 31)]

    def detect(w):
        calls.append(w)
        lang = table[wins.index(w)]
        return langs.restrict_probs(probs(**{lang: 0.97, "ar" if lang != "ar" else "he": 0.03}), ["ar", "he"])
    gen = langs.iter_runs(wins, detect)
    first = next(gen)
    assert first == (0, 17, "ar") and len(calls) == 4        # decided window 2, looked one ahead, no more
    assert list(gen) == [(18, 21, "he"), (22, 31, "ar")]
    assert len(calls) == len(wins)                           # each window detected exactly once


def test_iter_runs_respects_30_seconds_and_gaps():
    wins = [(0, 20), (21, 40), (60, 65)]
    det = lambda w: langs.restrict_probs(probs(ar=1.0), ["ar", "he"])
    assert list(langs.iter_runs(wins, det)) == [(0, 20, "ar"), (21, 40, "ar"), (60, 65, "ar")]


def test_make_blocks_groups_up_to_28_speech_seconds():
    wins = [(0, 10), (11, 21), (22, 32), (33, 36), (40, 41)]
    assert langs.make_blocks(wins) == [[0, 1], [2, 3, 4]]
    assert langs.make_blocks([(0, 5)]) == [[0]] and langs.make_blocks([]) == []


def test_block_detector_trusts_a_very_sure_block_and_refines_an_unsure_one():
    wins = [(0, 10), (11, 21), (22, 28), (40, 45), (46, 50)]
    log = []

    def many(ws):
        log.append(("many", len(ws)))
        return langs.restrict_probs(probs(ar=0.999, he=0.001), ["ar", "he"])

    def one(w):
        log.append(("one", w))
        return langs.restrict_probs(probs(he=0.9, ar=0.1), ["ar", "he"])
    d = langs.BlockDetector(wins, many, one)
    assert [langs.top(d(w))[0] for w in wins] == ["ar"] * 5
    assert d.passes == 2 and all(k == "many" for k, _ in log)       # two blocks, no per-window pass
    log.clear()

    def unsure(ws):
        log.append(("many", len(ws)))
        return langs.restrict_probs(probs(ar=0.93, he=0.07), ["ar", "he"])
    d = langs.BlockDetector(wins, unsure, one)
    assert [langs.top(d(w))[0] for w in wins] == ["he"] * 5          # refined window by window
    assert sum(1 for k, _ in log if k == "one") == 5


# ---- orchestration with a fake faster-whisper ------------------------------
SR = 16000


class FakeModel:
    """Looks like WhisperModel: language is decided by the 'tone' (sample value) of the window."""
    instances = []
    TONES = {0.1: "ar", 0.2: "he", 0.3: "en"}

    def __init__(self, *a, **k):
        FakeModel.instances.append(self)
        self.detected, self.calls = [], []

    def detect_language(self, audio=None, **k):
        tone = round(float(audio[len(audio) // 2]), 1)
        self.detected.append(len(audio) / SR)
        lang = self.TONES.get(tone, "fa")
        rest = {"fa": 0.6, "ar": 0.1, "he": 0.05, "en": 0.05}
        rest[lang] = 0.9 if lang != "fa" else 0.9
        return lang, rest[lang], sorted(rest.items(), key=lambda x: -x[1])

    def transcribe(self, audio, language=None, initial_prompt=None, **k):
        self.calls.append({"language": language, "prompt": initial_prompt, "audio": audio, "kw": k})
        if isinstance(audio, str):  # forced fast path on a file
            segs = [types.SimpleNamespace(start=1.0, end=3.0, text=" one "), types.SimpleNamespace(start=4.0, end=6.0, text=" two ")]
            return iter(segs), types.SimpleNamespace(duration=10.0, language=language)
        d = len(audio) / SR
        seg = types.SimpleNamespace(start=0.5, end=d - 0.1, text=f" text-{language} ")
        return iter([seg]), types.SimpleNamespace(duration=d, language=language)


@pytest.fixture
def fake_fw(monkeypatch):
    import faster_whisper
    import faster_whisper.audio
    import faster_whisper.vad
    FakeModel.instances.clear()
    # 40 s of audio: Arabic 2-8 s, Hebrew 9-12 s, Arabic 13-25 s, English 27-31 s
    audio = np.zeros(40 * SR, dtype=np.float32)
    for a, b, tone in [(2, 8, 0.1), (9, 12, 0.2), (13, 25, 0.1), (27, 31, 0.3)]:
        audio[a * SR:b * SR] = tone
    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    monkeypatch.setattr(faster_whisper.audio, "decode_audio", lambda p, sampling_rate=16000: audio)

    def fake_vad(a, opts=None, **k):  # "speech" = non-zero samples, so it works on a resumed slice too
        on = np.flatnonzero(np.abs(a) > 0)
        if not len(on):
            return []
        cuts = np.flatnonzero(np.diff(on) > 1)
        starts, ends = np.r_[on[0], on[cuts + 1]], np.r_[on[cuts], on[-1] + 1]
        return [{"start": int(x), "end": int(y)} for x, y in zip(starts, ends)]
    monkeypatch.setattr(faster_whisper.vad, "get_speech_timestamps", fake_vad)
    return audio


def _run(**kw):
    return transcriber.transcribe("x.wav", "tiny-test", model_dir="/nowhere", **kw)


def test_auto_detects_per_window_with_absolute_timestamps(fake_fw):
    got, langs_seen = [], []
    r = _run(language="auto", languages=["ar", "he", "en"], dialect="levantine",
             on_segment=lambda s, e, t: got.append((s, e)), on_lang=lambda seg: langs_seen.append(seg["lang"]))
    assert [s["lang"] for s in r["segments"]] == ["ar", "he", "ar", "en"]
    assert [s["text"] for s in r["segments"]] == ["text-ar", "text-he", "text-ar", "text-en"]
    assert r["segments"][1]["start"] == pytest.approx(9.5, abs=0.01)   # window start 9 s + 0.5 s inside it
    assert all(a >= 2 for a, _ in got) and got == [(s["start"], s["end"]) for s in r["segments"]]
    assert r["languages"] == ["ar", "he", "en"] and r["duration"] == 40.0
    m = FakeModel.instances[0]
    prompts = {c["language"]: c["prompt"] for c in m.calls}
    assert "شو" in prompts["ar"] and langs.has_hebrew(prompts["he"]) and prompts["en"].startswith("Hello")
    assert all(c["language"] in ("ar", "he", "en") for c in m.calls)


def test_auto_never_returns_a_language_outside_the_selection(fake_fw):
    r = _run(language="auto", languages=["ar", "he"])
    assert {s["lang"] for s in r["segments"]} <= {"ar", "he"}
    assert [s["lang"] for s in r["segments"]][1] == "he"
    assert all(c["language"] in ("ar", "he") for c in FakeModel.instances[0].calls)


def test_auto_resume_offsets_and_progress(fake_fw):
    prog = []
    r = _run(language="auto", languages=["ar", "he", "en"], start_at=12.0,
             on_progress=lambda p, c, d: prog.append((p, c)))
    assert r["segments"] and all(s["start"] >= 12.0 for s in r["segments"])
    assert [s["lang"] for s in r["segments"]] == ["ar", "en"] and r["segments"][0]["start"] == pytest.approx(13.5)
    pcts = [p for p, _ in prog]
    assert pcts == sorted(pcts) and pcts[-1] == 100.0


def test_auto_cancel(fake_fw):
    ev = threading.Event()
    seen = []

    def on_seg(s, e, t):
        seen.append(t)
        ev.set()
    with pytest.raises(transcriber.Cancelled):
        _run(language="auto", languages=["ar", "he", "en"], on_segment=on_seg, cancel=ev)
    assert len(seen) == 1


def test_single_language_keeps_the_fast_path(fake_fw):
    for kw in ({"language": "ar"}, {"language": "auto", "languages": ["ar"]}, {"language": "auto", "languages": ["he"]}):
        FakeModel.instances.clear()
        r = _run(**kw)
        m = FakeModel.instances[0]
        assert m.detected == [] and len(m.calls) == 1            # no detection pass, one transcribe call
        assert isinstance(m.calls[0]["audio"], str) and m.calls[0]["kw"]["vad_filter"] is True
        assert m.calls[0]["language"] == (kw.get("languages") or ["ar"])[0]
        assert [s["text"] for s in r["segments"]] == ["one", "two"]
        assert {s["lang"] for s in r["segments"]} == {m.calls[0]["language"]}


def test_forced_resume_uses_clip_timestamps(fake_fw):
    r = _run(language="ar", start_at=4.5)
    m = FakeModel.instances[0]
    assert m.calls[0]["kw"]["clip_timestamps"] == [4.5] and m.calls[0]["kw"]["vad_filter"] is False
    assert [s["text"] for s in r["segments"]] == ["two"]         # the segment before the resume point is skipped


# ---- assistant: Hebrew and Arabic ------------------------------------------
def test_scripts_and_normalisation():
    assert langs.script_of("שלום") == "he" and langs.script_of("سلام") == "ar" and langs.script_of("hello") is None
    assert langs.norm_he("שָׁלוֹם") == langs.norm_he("שלום")
    assert langs.norm_he("ספר") == langs.norm_he("ספר") and langs.norm_he("מלך") == langs.norm_he("מלכ")


def test_in_transcript_hebrew_and_arabic():
    norm = llm.norm_ar("המורה שואל שאלה בבית הספר. المعلم يكتب الكتاب")
    assert llm.in_transcript("שְׁאֵלָה", norm)            # niqqud is optional
    assert llm.in_transcript("הבית", norm)               # the article attaches to a word that is in the text
    assert not llm.in_transcript("חתולים", norm)
    assert llm.in_transcript("الكتاب", norm) and not llm.in_transcript("زرافة", norm)
    assert llm.in_transcript("school", norm)             # a word in another script has nothing to check


def test_hebrew_vocab_survives_recap_validation_and_keeps_lang():
    seg = [{"start": 0, "end": 5, "text": "המורה שואל שאלה. المعلم يكتب الكتاب."}]

    class Fake(llm.LlmClient):
        prompts = []

        def chat(self, prompt, max_tokens=1500, cancel=None):
            Fake.prompts.append(prompt)
            return json.dumps({"topic": "t", "taught": [], "focus": [], "grammar": [], "homework": [], "unclear_note": "",
                               "vocab": [{"arabic": "שאלה", "lang": "he", "meaning": "question"},
                                         {"arabic": "الكتاب", "meaning": "the book"},
                                         {"arabic": "חתול", "lang": "he", "meaning": "cat (invented)"},
                                         {"arabic": "זרפה", "meaning": "giraffe (no lang given)"}]}, ensure_ascii=False)
    r = Fake(base_url="http://x").day_recap([seg], "en", languages=["ar", "he"])
    assert [(v["arabic"], v["lang"]) for v in r["vocab"]] == [("שאלה", "he"), ("الكتاب", "ar")]
    assert "Arabic, Hebrew" in Fake.prompts[0] and "own script" in Fake.prompts[0]


def test_vocab_items_get_language_from_script():
    class Fake(llm.LlmClient):
        def chat(self, prompt, max_tokens=1500, cancel=None):
            return json.dumps([{"arabic": "שלום", "meaning": "peace"}, {"arabic": "سلام", "meaning": "peace"},
                               {"arabic": "hello", "lang": "en", "meaning": "hi"}])
    v = Fake(base_url="http://x").vocab([{"start": 0, "end": 1, "text": "x"}], "en", languages=["ar", "he", "en"])
    assert [i["lang"] for i in v] == ["he", "ar", "en"]


def test_prompts_name_the_target_languages():
    for name in ("summary", "summary_reduce", "vocab", "classify", "qa", "qa_extract", "day_recap", "day_recap_reduce"):
        out = llm.render(name, "en", languages=["he", "ar"], text="x", question="q")
        assert "Hebrew" in out and "Arabic" in out, name
    q = llm.render("quiz", "en", languages=["he"], count=10, avoid="", text="x")
    assert "Hebrew" in q and "Arabic" not in q.split("Notes:")[0].replace("Arabic or Hebrew", "")


def test_quiz_validation_accepts_hebrew_answers_from_the_transcript():
    norm = llm.norm_ar("הילד הולך לבית הספר")
    ok = {"type": "translate_to_arabic", "question": "Say 'school'", "answer": "בית ספר", "explanation": ""}
    bad = {"type": "translate_to_arabic", "question": "Say 'giraffe'", "answer": "ג'ירפה", "explanation": ""}
    assert llm.validate_question(ok, norm) and llm.validate_question(bad, norm) is None


def test_library_stores_languages(data, tmp_path, monkeypatch):
    from app import library
    monkeypatch.setenv("ALS_LIBRARY_DIR", str(tmp_path / "lib"))
    lid = library.create_lesson("t", "x.wav", None, "fast", None,
                                {"spoken_languages": ["ar", "he"], "arabic_dialect": "levantine", "mode": "auto"})
    library.finish_lesson(lid, [{"start": 0, "end": 1, "text": "a", "lang": "ar"},
                                {"start": 1, "end": 2, "text": "ש", "lang": "he"}], 2, "ar")
    meta = library.get_lesson(lid)["meta"]
    assert meta["languages"] == ["ar", "he"] and meta["arabic_dialect"] == "levantine" and meta["mode"] == "auto"
    assert library.get_lesson(lid)["segments"][1]["lang"] == "he"


def test_api_plan_from_meta():
    from app import api as api_mod
    f = api_mod.Api._plan_from_meta
    assert f({"language": "ar"}) == {"kind": "forced", "languages": ["ar"], "dialect": "msa"}
    assert f({"language": None})["kind"] == "auto" and f({"language": None})["languages"] == ["ar", "he"]
    assert f({"mode": "auto", "spoken_languages": ["ar", "he"], "arabic_dialect": "levantine"}) == \
        {"kind": "auto", "languages": ["ar", "he"], "dialect": "levantine"}


# ---- real model and real voices (slow, skipped when unavailable) -----------
def _multilingual_model() -> Path | None:
    import os
    cands = [os.environ.get("ALS_MULTI_MODEL_DIR", ""),
             str(config.models_dir() / "Systran__faster-whisper-small"),
             str(ROOT / "tests" / ".cache" / "data" / "models" / "Systran__faster-whisper-small")]
    for c in cands:
        if c and (Path(c) / "model.bin").is_file():
            return Path(c)
    return None


def _voices_ok() -> bool:
    if sys.platform != "darwin" or not shutil.which("say"):
        return False
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return all(v in out for v in ("Majed", "Carmit", "Samantha"))


@pytest.fixture(scope="module")
def mixed_wav(tmp_path_factory):
    if not _voices_ok():
        pytest.skip("macOS voices Majed, Carmit and Samantha are needed")
    d = tmp_path_factory.mktemp("mixed")
    parts = [("Majed", "مرحبا بكم في درسنا اليوم. سنتعلم كلمات جديدة عن البيت والعائلة."),
             ("Carmit", "המורה, אפשר לשאול שאלה? מה פירוש המשפט הזה בעברית?"),
             ("Samantha", "Please repeat the sentence after me, slowly and clearly."),
             ("Majed", "الكتاب على الطاولة والمعلم في الصف. هل فهمتم الدرس؟")]
    pcs = []
    for i, (v, t) in enumerate(parts):
        subprocess.run(["say", "-v", v, "-o", str(d / f"{i}.aiff"), t], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(d / f"{i}.aiff"), str(d / f"{i}.wav")], check=True)
        with wave.open(str(d / f"{i}.wav")) as w:
            pcs += [np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), np.zeros(int(16000 * 1.5), dtype=np.int16)]
    out = d / "mixed.wav"
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(np.concatenate(pcs).tobytes())
    return out


@pytest.mark.slow
def test_real_mixed_audio_restricted_detection(mixed_wav):
    model = _multilingual_model()
    if model is None:
        pytest.skip("no multilingual model (set ALS_MULTI_MODEL_DIR, e.g. Systran/faster-whisper-small)")
    full = transcriber.transcribe(mixed_wav, "tiny-test", "auto", model_dir=model, languages=["ar", "he", "en"])
    by = [(s["lang"], s["text"]) for s in full["segments"]]
    assert [c for c, _ in by][:4] == ["ar", "he", "en", "ar"] or {"ar", "he", "en"} <= {c for c, _ in by}
    assert any(langs.has_hebrew(t) for c, t in by if c == "he")
    assert any(t.isascii() for c, t in by if c == "en")
    only = transcriber.transcribe(mixed_wav, "tiny-test", "auto", model_dir=model, languages=["ar", "he"])
    assert {s["lang"] for s in only["segments"]} <= {"ar", "he"}
    assert not any(any("a" <= ch.lower() <= "z" for ch in s["text"]) for s in only["segments"])
    forced = transcriber.transcribe(mixed_wav, "tiny-test", "ar", model_dir=model)
    assert not any(langs.has_hebrew(s["text"]) for s in forced["segments"])  # the old behaviour loses the Hebrew
