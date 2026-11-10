import json

import pytest

from app import api as api_mod
from app import config, importer, library, llm, power


def test_parse_plain_text(tmp_path):
    p = tmp_path / "lesson.txt"
    p.write_text("مرحبا بكم.\n\nاليوم درس جديد؟ نعم! سنبدأ الآن.\n\n" + ("كلمة " * 120), encoding="utf-8")
    title, segs = importer.parse_transcript(p)
    assert title == "lesson"
    assert segs[0]["text"] == "مرحبا بكم."
    assert all(s["start"] is None and s["end"] is None for s in segs)
    assert all(len(s["text"]) <= importer.MAX_SEG_CHARS for s in segs)
    assert len(segs) >= 4


def test_parse_plain_single_lines_and_cp1256(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes("سلام\nكيف حالك".encode("cp1256"))
    _, segs = importer.parse_transcript(p)
    assert [s["text"] for s in segs] == ["سلام", "كيف حالك"]


def test_parse_srt(tmp_path):
    p = tmp_path / "a.srt"
    p.write_text("1\n00:00:01,500 --> 00:00:04,000\nمرحبا\nبكم\n\n2\n01:02:03,250 --> 01:02:05,000\n<i>درس</i>\n", encoding="utf-8")
    _, segs = importer.parse_transcript(p)
    assert segs == [{"start": 1.5, "end": 4.0, "text": "مرحبا بكم"},
                    {"start": 3723.25, "end": 3725.0, "text": "درس"}]


def test_parse_vtt(tmp_path):
    p = tmp_path / "a.vtt"
    p.write_text("WEBVTT\n\nNOTE hi\n\ncue1\n00:01.000 --> 00:03.500 align:start\nمرحبا\n\n00:03.500 --> 00:05.000\nشكرا\n", encoding="utf-8")
    _, segs = importer.parse_transcript(p)
    assert [(s["start"], s["end"], s["text"]) for s in segs] == [(1.0, 3.5, "مرحبا"), (3.5, 5.0, "شكرا")]


def test_parse_own_markdown_export_and_errors(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# T\n\n**[00:05]** أول\n\n**[01:10]** ثان\n", encoding="utf-8")
    _, segs = importer.parse_transcript(p)
    assert segs[0]["start"] == 5 and segs[1]["start"] == 70
    (tmp_path / "e.txt").write_text("  \n", encoding="utf-8")
    with pytest.raises(ValueError):
        importer.parse_transcript(tmp_path / "e.txt")
    (tmp_path / "x.pdf").write_text("x")
    with pytest.raises(ValueError):
        importer.parse_transcript(tmp_path / "x.pdf")


def test_import_api_and_ai_chunking_without_timestamps(tmp_path):
    p = tmp_path / "l.txt"
    p.write_text("\n\n".join("جملة رقم %d في الدرس." % i for i in range(300)), encoding="utf-8")
    a = api_mod.Api(lambda n, d: None)
    lid = a.import_transcript(str(p))["lesson_id"]
    les = a.get_lesson(lid)
    assert les["meta"]["status"] == "imported" and les["meta"]["audio_ok"] is False
    assert len(les["segments"]) == 300
    assert (config.library_dir() / lid / "transcript.md").exists()
    assert a.get_state()["lessons"][0]["status"] == "imported"
    wins = llm.chunk_by_time(les["segments"])
    assert sum(len(w) for w in wins) == 300 and len(wins) >= 2

    class Fake(llm.LlmClient):
        def chat(self, prompt, max_tokens=1500, cancel=None):
            return '{"label": "grammar", "topic": "x"}'
    out = Fake(base_url="http://x").classify(les["segments"])
    assert out[0]["start"] is None and out[0]["index"] == 0 and out[1]["index"] == len(wins[0])
    library.save_notes(lid, {"outline": out, "qa": []})  # null timestamps must not break notes.md


def test_chunk_size_bound_for_12k_arabic_words():
    word = "المدرسة"  # 7 chars + space
    text = " ".join([word] * 12000)
    sents = [text[i:i + 150] for i in range(0, len(text), 150)]
    segs = [{"start": i * 4.0, "end": i * 4.0 + 4, "text": t} for i, t in enumerate(sents)]
    chunks = llm.chunk_segments(segs)
    assert 8 <= len(chunks) <= 40
    assert sum(len(c) for c in chunks) == len(segs)
    out_budget = {"summary": 700, "vocab": 1500, "qa_extract": 500}
    for c in chunks:
        body = llm.chunk_text(c)
        # at 2 chars/token the estimate is conservative; even at 1.5 chars/token real use fits n_ctx
        for name, out in out_budget.items():
            prompt = llm.render(name, "fr", text=body, question="ما معنى الكلمة؟")
            assert llm.est_tokens(prompt) + out < llm.N_CTX
            assert len(prompt) / 1.5 + out < llm.N_CTX
    assert max(llm.est_tokens(llm.chunk_text(c)) for c in chunks) <= llm.CHUNK_TOKENS + 5


def test_recover_interrupted_and_resume_guards(tmp_path):
    lid = library.create_lesson("t", str(tmp_path / "gone.wav"), "ar", "tiny-test")
    library.append_segment(lid, {"start": 0, "end": 5, "text": "مرحبا"})
    empty = library.create_lesson("e", str(tmp_path / "gone.wav"), "ar", "tiny-test")
    done = library.create_lesson("d", "x", "ar", "tiny-test")
    library.finish_lesson(done, [{"start": 0, "end": 1, "text": "a"}], 1, "ar")
    a = api_mod.Api(lambda n, d: None)  # startup recovery
    assert library.get_lesson(lid)["meta"]["status"] == "interrupted"
    assert library.get_lesson(empty)["meta"]["status"] == "failed"
    assert library.get_lesson(done)["meta"]["status"] == "done"
    assert library.get_lesson(lid)["meta"]["audio_ok"] is False
    with pytest.raises(ValueError, match="AUDIO_MISSING"):
        a.resume_transcription(lid)
    with pytest.raises(ValueError):
        a.resume_transcription(done)


def test_partial_torn_line_and_get_lesson_speed(tmp_path):
    import time
    lid = library.create_lesson("t", "x", "ar", "tiny-test")
    for i in range(1000):
        library.append_segment(lid, {"start": i * 4.0, "end": i * 4.0 + 4, "text": "كلمة " * 12})
    with open(config.library_dir() / lid / "segments.partial.jsonl", "a", encoding="utf-8") as f:
        f.write('{"start": 4000, "en')  # crash mid-write
    t0 = time.perf_counter()
    les = library.get_lesson(lid)
    assert len(les["segments"]) == 1000 and time.perf_counter() - t0 < 0.5


def test_eta_for():
    assert api_mod.eta_for(0, 60, 3600, 0, 100) is None            # not enough audio yet
    assert api_mod.eta_for(0, 600, 3600, 0, 5) is None             # not enough wall time
    eta = api_mod.eta_for(0, 600, 3600, 0, 300)                    # 2 audio s per wall s
    assert eta == pytest.approx(1500)
    assert api_mod.eta_for(1000, 1600, 3600, 0, 300) == pytest.approx(1000)  # resume: rate over this run only


def test_keep_awake_noop_and_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(power, "_set_state", lambda f: calls.append(f) or 0)
    with power.keep_awake():
        pass
    assert calls == [power.ES_CONTINUOUS | power.ES_SYSTEM_REQUIRED, power.ES_CONTINUOUS]
    monkeypatch.undo()
    with power.keep_awake():  # real function: harmless off Windows
        pass
