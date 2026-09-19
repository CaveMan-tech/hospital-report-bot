import os

os.environ.update(EXTRACT_MODE="mock", STORE="memory", ALLOW_UNVERIFIED="true", DEMO_MODE="true")

from fastapi.testclient import TestClient

from app.main import app


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


def test_total_failure_still_tells_the_reporter_what_to_do():
    with TestClient(app) as c:
        engine = c.app.state.engine
        original = engine.handle_message

        async def boom(*a, **k):
            raise RuntimeError("database is down")

        engine.handle_message = boom
        try:
            r = c.post("/api/chat", json={"text": "hello there my friend"})
        finally:
            engine.handle_message = original
        assert r.status_code == 503
        assert "nearest other hospital" in r.json()["detail"] and "Traceback" not in r.text
        assert "nearest other hospital" in c.get("/").text          # offline text is baked into the page


def test_static_urls_are_versioned():
    import re
    with TestClient(app) as c:
        page = c.get("/").text
        assert re.search(r"/static/chat\.js\?v=[0-9a-f]{8}", page) and re.search(r"/static/app\.css\?v=[0-9a-f]{8}", page)


def test_forget_deletes_an_unfinished_conversation_but_never_a_finished_report():
    with TestClient(app) as c:
        store = c.app.state.engine.store
        r = c.post("/api/chat", json={"text": "A nurse slapped me and insulted me in front of everybody"}).json()
        sid = r["session_id"]
        assert "slapped" in store.sessions[sid].model_dump_json()         # the story is held while the chat is live
        assert c.post("/api/chat/forget", json={"session_id": sid}).status_code == 204
        assert sid not in store.sessions                                  # gone now, not in two hours
        assert c.post("/api/chat/forget", json={"session_id": "not-a-session"}).status_code == 204

        done = c.post("/api/chat", json={"text": "A nurse slapped me last week at Harmattan General Hospital maternity ward"}).json()
        n = len(store.reports)
        c.post("/api/chat/forget", json={"session_id": done["session_id"]})
        assert len(store.reports) == n and "on record" in c.post(
            "/api/report/lookup", json={"ref_code": done["ref_code"]}).json()["message"]


def test_chat_page_has_quick_exit_and_stays_small():
    with TestClient(app) as c:
        page = c.get("/").text
        assert 'id="exit"' in page
        js = c.get("/static/chat.js").text
        assert "location.replace" in js and "sendBeacon" in js and "Try again" in js and "continuing your report" in js
        assert "localStorage" not in js                                   # never persist a chat beyond the tab
        total = sum(len(c.get(p).content) for p in ("/", "/static/app.css", "/static/chat.js"))
        assert total < 10_000, total
