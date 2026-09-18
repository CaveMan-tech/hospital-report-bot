import os

os.environ.update(EXTRACT_MODE="mock", STORE="memory", ALLOW_UNVERIFIED="true", DEMO_MODE="true")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_full_conversation_over_http():
    with TestClient(app) as c:
        assert "Report a hospital problem" in c.get("/").text
        r = c.post("/api/chat", json={"text": ""}).json()
        sid = r["session_id"]
        assert "safe place" in r["replies"][0]
        r = c.post("/api/chat", json={"session_id": sid, "text":
                   "A nurse slapped me last week at Harmattan General Hospital maternity ward"}).json()
        code = r["ref_code"]
        assert code and r["state"] == "B5"
        assert "on record" in c.post("/api/report/lookup", json={"ref_code": code}).json()["message"]
        f = c.post("/api/demo/next-day", json={"ref_code": code}).json()
        assert f["state"] == "F1"
        assert c.post("/api/demo/next-day", json={"ref_code": "AAAA-AAAA-AAAA"}).status_code == 404


def test_page_is_tiny():
    with TestClient(app) as c:
        total = sum(len(c.get(p).content) for p in ("/", "/static/app.css", "/static/chat.js"))
        assert total < 10_000, total
