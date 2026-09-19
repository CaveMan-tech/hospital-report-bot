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


def test_voice_is_off_by_default_and_the_page_has_no_microphone():
    with TestClient(app) as c:
        assert 'id="mic"' not in c.get("/").text and "voice.js" not in c.get("/").text
        assert c.post("/api/transcribe", content=b"abc", headers={"content-type": "audio/webm"}).status_code == 404


def test_voice_note_is_transcribed_returned_and_never_kept():
    seen = {}

    async def fake(audio: bytes, mime: str, hint: str) -> str:
        seen.update(size=len(audio), mime=mime, hint=hint)
        return "Nurse slap my pikin for ward"

    with TestClient(app) as c:
        c.app.state.transcriber = fake
        page = c.get("/").text
        assert 'id="mic"' in page and "voice.js" in page and "never keep your voice" in page
        r = c.post("/api/transcribe?pack=ng-lagos", content=b"\x1aE\xdf\xa3fake", headers={"content-type": "audio/webm;codecs=opus"})
        assert r.status_code == 200 and r.json() == {"text": "Nurse slap my pikin for ward"}
        assert seen["size"] == 8 and "Pidgin" in seen["hint"] and "pikin" in seen["hint"]
        assert "Nairobi" in (c.post("/api/transcribe?pack=ke-nairobi", content=b"x", headers={"content-type": "audio/mp4"}) and seen["hint"])

        store = c.app.state.engine.store
        assert not store.sessions or all("fake" not in s.model_dump_json() for s in store.sessions.values())

        assert c.post("/api/transcribe", content=b"", headers={"content-type": "audio/webm"}).status_code == 400
        assert c.post("/api/transcribe", content=b"x" * 1_500_001, headers={"content-type": "audio/webm"}).status_code == 413
        assert c.post("/api/transcribe", content=b"x", headers={"content-type": "text/plain"}).status_code == 415

        async def broken(audio, mime, hint):
            raise RuntimeError("upstream down")
        c.app.state.transcriber = broken
        r = c.post("/api/transcribe", content=b"x", headers={"content-type": "audio/webm"})
        assert r.status_code == 503 and "type instead" in r.json()["detail"] and "Traceback" not in r.text

        async def silent(audio, mime, hint):
            return ""
        c.app.state.transcriber = silent
        assert c.post("/api/transcribe", content=b"x", headers={"content-type": "audio/webm"}).status_code == 422
        c.app.state.transcriber = None


def test_voice_script_is_small_and_never_auto_sends():
    from pathlib import Path
    js = Path("app/web/static/voice.js").read_text()
    assert len(js) < 3000 and "getTracks().forEach" in js            # microphone released after each note
    assert "send(" not in js and "requestSubmit" not in js            # text goes to the box for the person to check
