import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import config, downloader, library, llm


def segs(n, text="كلمة " * 40, step=10):
    return [{"start": i * step, "end": i * step + step, "text": text.strip()} for i in range(n)]


def test_chunking_respects_budget():
    s = segs(200)
    chunks = llm.chunk_segments(s, 3000)
    assert sum(len(c) for c in chunks) == 200
    assert len(chunks) > 1
    for c in chunks:
        assert llm.est_tokens(llm.chunk_text(c)) <= 3100
    assert len(llm.chunk_segments(segs(3))) == 1


def test_chunk_oversized_segment_and_time_windows():
    big = [{"start": 0, "end": 5, "text": "كلمة " * 5000}]
    assert len(llm.chunk_segments(big, 3000)) > 1
    w = llm.chunk_by_time(segs(30, step=10), 120)
    assert len(w) == 3 and all(w)


def test_extract_json_and_prompts():
    assert llm.extract_json('```json\n[{"arabic":"بيت"}]\n```') == [{"arabic": "بيت"}]
    assert llm.extract_json('Sure! {"label": "grammar"} ok')["label"] == "grammar"
    with pytest.raises(ValueError):
        llm.extract_json("nothing")
    for name in ("summary", "summary_reduce", "vocab", "classify", "qa", "qa_extract"):
        out = llm.render(name, "it", text="نص {x}", question="ما؟")
        assert "Italian" in out and "نص {x}" in out


class FakeLLM(BaseHTTPRequestHandler):
    prompts = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        p = body["messages"][0]["content"]
        FakeLLM.prompts.append(p)
        assert body["temperature"] == 1.0 and body["top_k"] == 64
        if "Reply with ONLY a JSON array" in p:
            reply = '```json\n[{"arabic":"بيت","transliteration":"bayt","meaning":"house","note":""}]\n```'
        elif "Classify" in p:
            reply = '{"label": "Grammar", "topic": "verbs"}'
        elif "Copy out" in p:
            reply = "NONE" if "كلمة" not in p else "- fact"
        else:
            reply = "REPLY"
        out = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers()
        self.wfile.write(out)


@pytest.fixture
def client():
    FakeLLM.prompts.clear()
    srv = HTTPServer(("127.0.0.1", 0), FakeLLM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield llm.LlmClient(f"http://127.0.0.1:{srv.server_port}")
    srv.shutdown()


def test_llm_flows_with_mock_server(client):
    s = segs(200)
    n_chunks = len(llm.chunk_segments(s))
    assert client.summarize(s) == "REPLY"
    assert len(FakeLLM.prompts) >= n_chunks + 1  # map + reduce
    assert client.summarize(segs(2)) == "REPLY"
    v = client.vocab(segs(2))
    assert v == [{"arabic": "بيت", "transliteration": "bayt", "meaning": "house", "note": ""}]
    o = client.classify(segs(30))
    assert len(o) == 3 and o[0]["kind"] == "grammar" and o[0]["summary"] == "verbs" and "end" in o[0] and o[0]["start"] == 0
    assert client.ask(s, "ما؟") == "REPLY"
    assert "Italian" in (client.ask(segs(1), "q", "it") and FakeLLM.prompts[-1])


def test_library_roundtrip():
    lid = library.create_lesson("Test: lesson?", "/x/a.mp3", "ar", "fast")
    library.append_segment(lid, {"start": 0, "end": 1, "text": "مرحبا"})
    assert library.get_lesson(lid)["segments"][0]["text"] == "مرحبا"  # partial readable
    library.finish_lesson(lid, [{"start": 0, "end": 1, "text": "مرحبا"}], 1.0, "ar")
    d = config.library_dir() / lid
    for f in ("transcript.json", "transcript.txt", "transcript.md", "notes.md"):
        assert (d / f).exists()
    assert library.list_lessons()[0]["preview"] == "مرحبا"
    library.rename_lesson(lid, "New")
    assert library.get_lesson(lid)["meta"]["title"] == "New"
    assert library.export_lesson(lid, "md").endswith("transcript.md")
    with pytest.raises(ValueError):
        library.get_lesson("../etc")
    library.delete_lesson(lid)
    assert library.list_lessons() == []


class RangeServer(BaseHTTPRequestHandler):
    DATA = bytes(range(256)) * 4000

    def log_message(self, *a):
        pass

    def do_GET(self):
        rng = self.headers.get("Range")
        d = self.DATA
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(d)-1}/{len(d)}")
            d = d[start:]
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)


def test_download_resume(tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), RangeServer)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    dest = tmp_path / "f.bin"
    (tmp_path / "f.bin.part").write_bytes(RangeServer.DATA[:5000])
    seen = []
    downloader.download_file(f"http://127.0.0.1:{srv.server_port}/f", dest, lambda d, t, s: seen.append((d, t)))
    srv.shutdown()
    assert dest.read_bytes() == RangeServer.DATA
    assert seen[-1][0] == seen[-1][1] == len(RangeServer.DATA)
    assert not (tmp_path / "f.bin.part").exists()


def test_download_cancel(tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), RangeServer)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ev = threading.Event(); ev.set()
    with pytest.raises(downloader.DownloadCancelled):
        downloader.download_file(f"http://127.0.0.1:{srv.server_port}/f", tmp_path / "g", cancel=ev)
    srv.shutdown()
