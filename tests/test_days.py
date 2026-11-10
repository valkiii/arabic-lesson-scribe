import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import api as api_mod
from app import config, dayexport, downloader, library, llm

WORDS = ["المدرسة", "الكتاب", "القلم", "البيت", "الطالب", "المعلم", "النافذة", "الباب", "الطاولة", "الكرسي",
         "السيارة", "الحديقة", "الشجرة", "الماء"]


def recap_json(topic="Topic"):
    return json.dumps({"topic": topic, "taught": ["a"], "focus": ["You can say المدرسة"], "grammar": ["g"], "homework": [],
                       "vocab": [{"arabic": "المدرسة", "meaning": "school", "transliteration": "al-madrasa"},
                                 {"arabic": "غائب", "meaning": "not in transcript"}], "unclear_note": ""},
                      ensure_ascii=False)


class Fake(BaseHTTPRequestHandler):
    prompts: list = []
    quiz_replies: list = []   # scripted replies, consumed first
    counter = [0]

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        p = body["messages"][0]["content"]
        Fake.prompts.append(p)
        assert len(p) / 1.5 + body["max_tokens"] < llm.N_CTX, "prompt would overflow n_ctx"
        if "practice questions" in p:
            if Fake.quiz_replies:
                reply = Fake.quiz_replies.pop(0)
            else:
                n = int(re.search(r"exactly (\d+) questions", p).group(1))
                reply = json.dumps([self.make_q() for _ in range(n)], ensure_ascii=False)
        elif "JSON notes made from" in p:
            reply = recap_json("merged")
        elif "review one day" in p:
            reply = recap_json("part")
        else:
            reply = "REPLY"
        out = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers()
        self.wfile.write(out)

    @staticmethod
    def make_q():
        Fake.counter[0] += 1
        i = Fake.counter[0]
        w = WORDS[i % len(WORDS)]
        kind = i % 5
        if kind == 0:
            return {"type": "translate_from_arabic", "question": f"Translate #{i}: {w}", "answer": f"thing {i}", "explanation": "e"}
        if kind == 1:
            return {"type": "translate_to_arabic", "question": f"Say 'thing {i}' in Arabic", "answer": w, "explanation": "e"}
        if kind == 2:
            return {"type": "fill_blank", "question": f"#{i} ____ {w}", "answer": w, "explanation": "e"}
        if kind == 3:
            return {"type": "multiple_choice", "question": f"#{i} which means {w}?", "options": ["a", "b", "c", "d"], "answer": "B"}
        return {"type": "grammar", "question": f"#{i} grammar of {w}", "answer": "x", "explanation": "e"}


@pytest.fixture
def server():
    Fake.prompts.clear(); Fake.quiz_replies.clear(); Fake.counter[0] = 0
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def seg_list(n=4, words=WORDS):
    return [{"start": i * 5.0, "end": i * 5.0 + 5, "text": f"هذه {words[i % len(words)]} وتلك {words[(i + 3) % len(words)]}"} for i in range(n)]


def make_part(day, title="p", n=4, hour=10, status_done=True):
    from datetime import datetime
    y, m, d = map(int, day.split("-"))
    lid = library.create_lesson(title, "/x/a.mp3", "ar", "fast", datetime(y, m, d, hour, 0))
    library.finish_lesson(lid, seg_list(n), 20.0, "ar")
    return lid


def wait(a, timeout=10):
    t0 = time.time()
    while a._jobs and time.time() - t0 < timeout:
        time.sleep(0.05)
    assert not a._jobs


@pytest.fixture
def installed(monkeypatch):
    monkeypatch.setattr(config, "is_installed", lambda k: True)


def test_day_grouping_and_set_date():
    a1 = make_part("2026-11-10", "morning", hour=9)
    a2 = make_part("2026-11-10", "evening", hour=18)
    b = make_part("2026-11-09", "old")
    days = library.list_days()
    assert [d["date"] for d in days] == ["2026-11-10", "2026-11-09"]
    assert days[0]["title"] == "Tuesday 10 Nov"
    assert [p["id"] for p in days[0]["parts"]] == [a1, a2]
    assert days[0]["total_duration_s"] == 40.0 and not days[0]["has_recap"]
    d = library.get_day("2026-11-10")
    assert list(d["segments_by_part"]) == [a1, a2] and len(d["segments_by_part"][a1]) == 4
    # old lessons without a "day" field group by their date
    meta = json.loads((config.library_dir() / b / "meta.json").read_text(encoding="utf-8"))
    meta.pop("day")
    (config.library_dir() / b / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    assert "2026-11-09" in [x["date"] for x in library.list_days()]
    # day notes never live inside part folders; _days is not mistaken for a lesson
    library.save_day_notes("2026-11-10", {"recap": {"topic": "x"}})
    assert (config.library_dir() / "_days" / "2026-11-10.json").is_file()
    assert all(l["id"] != "_days" for l in library.list_lessons())
    a = api_mod.Api(lambda n, p: None)
    r = a.set_lesson_date(a2, "2026-11-12")
    assert r["old_day"] == "2026-11-10" and library.get_lesson(a2)["meta"]["date"].startswith("2026-11-12T18")
    assert library.load_day_notes("2026-11-10")["recap"]["stale"] is True
    with pytest.raises(ValueError):
        a.set_lesson_date(a2, "12/11/2026")


def test_start_transcription_uses_file_mtime(tmp_path, monkeypatch):
    import os
    f = tmp_path / "rec.m4a"
    f.write_bytes(b"x")
    ts = time.mktime((2026, 3, 4, 15, 30, 0, 0, 0, -1))
    os.utime(f, (ts, ts))
    monkeypatch.setattr(api_mod.Api, "_spawn", lambda self, *a: None)
    a = api_mod.Api(lambda n, p: None)
    lid = a.start_transcription(str(f), {"model": "fast"})["lesson_id"]
    assert library.get_lesson(lid)["meta"]["day"] == "2026-03-04"
    lid2 = a.start_transcription(str(f), {"model": "fast", "date": "2026-03-01"})["lesson_id"]
    assert library.get_lesson(lid2)["meta"]["date"].startswith("2026-03-01T15:30")


def test_recap_map_reduce_fits_context(server):
    c = llm.LlmClient(server)
    # about one hour of Arabic: 12k words over two recordings
    words = " ".join(WORDS * 70)
    segs_a = [{"start": i * 4.0, "end": i * 4.0 + 4, "text": words[i * 100:(i + 1) * 100 + 40]} for i in range(0, 300)]
    parts = [segs_a[:150], segs_a[150:]]
    n_chunks = sum(len(llm.chunk_segments(p)) for p in parts)
    r = c.day_recap(parts)
    assert n_chunks >= 2
    assert r["topic"] == "merged" and r["focus"] and r["unclear_note"] == ""
    assert [v["arabic"] for v in r["vocab"]] == ["المدرسة"]  # vocabulary not in the transcript is dropped
    assert len(Fake.prompts) >= n_chunks + 1
    # single small part: one call, no reduce
    Fake.prompts.clear()
    assert c.day_recap([seg_list(3)], "fr")["topic"] == "part" and len(Fake.prompts) == 1 and "French" in Fake.prompts[0]


def test_quiz_exactly_ten_repair_and_dedupe(server):
    c = llm.LlmClient(server)
    recap = llm.clean_recap(json.loads(recap_json()))
    norm = llm.norm_ar(" ".join(s["text"] for s in seg_list(14)))
    q = Fake.make_q
    good = [q() for _ in range(6)]
    # 1st reply: truncated JSON with 6 good questions, a duplicate, a bad MCQ (3 options), and an ungrounded answer
    bad_mc = {"type": "multiple_choice", "question": "bad", "options": ["a", "b", "c"], "answer": "a"}
    ungrounded = {"type": "translate_to_arabic", "question": "Say x", "answer": "زرافة", "explanation": ""}
    reply = json.dumps(good + [good[0], bad_mc, ungrounded], ensure_ascii=False)
    Fake.quiz_replies.append("Here you go:\n" + reply[:-1] + ',{"type": "gram')  # truncated, chatty
    out = c.day_quiz(recap, norm)
    assert len(out) == 10 and len({x["question"] for x in out}) == 10
    assert len(Fake.prompts) == 2 and "exactly 4 questions" in Fake.prompts[1]  # topped up
    assert all(x["id"] for x in out) and all(x["type"] in llm.QUIZ_TYPES for x in out)
    mc = next(x for x in out if x["type"] == "multiple_choice")
    assert mc["answer"] in mc["options"] and len(mc["options"]) == 4  # letter answer mapped to option text
    # not enough valid questions even after retries -> honest error
    Fake.quiz_replies.extend(["not json"] * 4)
    with pytest.raises(RuntimeError, match="valid questions"):
        c.day_quiz(recap, norm, previous=[x["question"] for x in out])


def test_quiz_more_avoids_repeats_and_marks(server, installed):
    make_part("2026-11-10")
    a = api_mod.Api(lambda n, p: None)
    a._llm = llm.LlmClient(server)
    events = []
    a._emit_fn = lambda n, p: events.append((n, p))
    assert a.ai_day_quiz("2026-11-10")["job_id"] == "quiz:2026-11-10"
    wait(a)
    done = [p for n, p in events if n == "done" and p["job"] == "llm"][-1]
    assert done["ok"], done
    day = library.get_day("2026-11-10")
    q1 = day["notes"]["quiz"]["questions"]
    assert len(q1) == 10 and day["notes"]["recap"]["topic"] == "part"  # recap was made on the way
    assert a.ai_day_quiz("2026-11-10") == {"job_id": None, "cached": True}
    r = a.set_quiz_mark("2026-11-10", q1[0]["id"], "right")
    a.set_quiz_mark("2026-11-10", q1[1]["id"], "wrong")
    assert r["score"] == 1 and library.load_day_notes("2026-11-10")["quiz"]["marks"][q1[1]["id"]] == "wrong"
    Fake.prompts.clear()
    a.ai_day_quiz("2026-11-10", {"more": True})
    wait(a)
    q2 = library.get_day("2026-11-10")["notes"]["quiz"]
    assert len(q2["questions"]) == 10 and q2["marks"] == {} and q2["round"] == 2
    assert not {x["question"] for x in q1} & {x["question"] for x in q2["questions"]}
    assert "Do NOT repeat" in Fake.prompts[0] and q1[0]["question"][:20] in Fake.prompts[0]


def test_auto_recap_installed_vs_not_and_stale(server, monkeypatch):
    events = []
    a = api_mod.Api(lambda n, p: events.append((n, p)))
    a._llm = llm.LlmClient(server)
    monkeypatch.setattr(downloader, "ensure_model", lambda *x, **k: pytest.fail("must not download automatically"))
    # assistant not installed: nothing runs, no download
    monkeypatch.setattr(config, "is_installed", lambda k: False)
    p1 = make_part("2026-11-10", "one")
    a._after_part_added(p1)
    assert not a._jobs and not library.load_day_notes("2026-11-10").get("recap")
    # installed: the recap is made automatically
    monkeypatch.setattr(config, "is_installed", lambda k: True)
    a._after_part_added(p1)
    wait(a)
    rc = library.load_day_notes("2026-11-10")["recap"]
    assert rc["topic"] == "part" and rc["stale"] is False and rc["parts"] == [p1]
    # setting off: a new part only marks the recap stale
    config.save_settings({"auto_recap": False})
    p2 = make_part("2026-11-10", "two", hour=15)
    a._after_part_added(p2)
    assert not a._jobs and library.load_day_notes("2026-11-10")["recap"]["stale"] is True
    # setting on: the stale recap is refreshed and covers both parts
    config.save_settings({"auto_recap": True})
    a._after_part_added(p2)
    wait(a)
    rc = library.load_day_notes("2026-11-10")["recap"]
    assert rc["stale"] is False and rc["parts"] == [p1, p2]
    assert any(n == "done" and p.get("kind") == "recap" and p["ok"] for n, p in events)
    # no auto download when explicitly asked is still allowed: ai_day_recap with gemma missing would download
    monkeypatch.setattr(config, "is_installed", lambda k: False)
    called = []
    monkeypatch.setattr(downloader, "ensure_model", lambda *x, **k: called.append(x))
    a.ai_day_recap("2026-11-10")
    wait(a)
    assert called


def test_export_day(server, installed, tmp_path):
    make_part("2026-11-10")
    a = api_mod.Api(lambda n, p: None)
    a._llm = llm.LlmClient(server)
    a.ai_day_quiz("2026-11-10")
    wait(a)
    p = a.export_day("2026-11-10", "md", True)["path"]
    text = open(p, encoding="utf-8").read()
    assert "Tuesday 10 Nov" in text and "Focus points" in text and "Answer:" in text and "Practice questions" in text
    p2 = a.export_day("2026-11-10", "html", False, "quiz")["path"]
    h = open(p2, encoding="utf-8").read()
    assert "Answer:" not in h and "window.print" in h and "<h2" in h
    with pytest.raises(ValueError):
        a.export_day("2026-11-11")
    with pytest.raises(ValueError):
        a.open_file(str(tmp_path / "x.txt"))
