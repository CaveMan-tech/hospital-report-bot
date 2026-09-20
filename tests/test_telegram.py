import json
import logging
import re

from app.channels.telegram import Blocked, TelegramAdapter, split_text
from app.engine.extract import mock_extract
from app.engine.machine import Engine
from app.engine.packs import Pack
from app.store.memory import MemoryStore

CHAT = 987654321
STORY_ASK = "A nurse slapped me and insulted me in front of everybody"
STORY_FULL = "A nurse slapped me last week at Harmattan General Hospital maternity ward"


class FakeAPI:
    def __init__(self):
        self.sent, self.answered, self.stripped, self.block = [], [], [], False

    async def send_message(self, chat_id, text, buttons=None):
        if self.block:
            raise Blocked
        self.sent.append((chat_id, text, buttons))

    async def answer_callback(self, callback_id):
        self.answered.append(callback_id)

    async def strip_keyboard(self, chat_id, message_id):
        self.stripped.append(message_id)

    async def typing(self, chat_id):
        pass

    def texts(self):
        return [t for _, t, _ in self.sent]

    def last_buttons(self):
        return self.sent[-1][2]


def make(allow_unverified=True, demo_mode=True):
    store, api = MemoryStore(), FakeAPI()
    packs = [Pack("ng-lagos", allow_unverified), Pack("ke-nairobi", allow_unverified)]
    engine = Engine(store, mock_extract, packs, ref_secret="test-secret")
    return TelegramAdapter(engine, api, demo_mode=demo_mode), api, store, engine


_n = iter(range(1, 10_000))


def msg(text, chat=CHAT, chat_type="private", **extra):
    return {"update_id": next(_n), "message": {"message_id": next(_n), "text": text,
            "from": {"id": chat, "first_name": "Adaeze", "username": "adaeze_o"},
            "chat": {"id": chat, "type": chat_type, "first_name": "Adaeze"}, **extra}}


def tap(data, chat=CHAT):
    return {"update_id": next(_n), "callback_query": {"id": "cb1", "data": data,
            "from": {"id": chat, "first_name": "Adaeze"},
            "message": {"message_id": 55, "chat": {"id": chat, "type": "private"}}}}


def mask(texts):
    return [re.sub(r"[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}", "CODE", t) for t in texts]


def test_same_conversation_gives_the_same_replies_as_the_web_channel():
    """The proof: one script, through POST /api/chat and through Telegram, turn by turn."""
    import asyncio
    script = ["hi", STORY_ASK, "no", "Lagoon View General Hospital", "maternity", "last week", "no"]
    with _client() as c:
        engine, api = c.app.state.engine, FakeAPI()
        adapter = TelegramAdapter(engine, api)
        sid = None
        for line in script:
            web = c.post("/api/chat", json={"session_id": sid, "text": line}).json()
            sid = web["session_id"]
            before = len(api.sent)
            asyncio.run(adapter.handle_update(msg(line)))
            telegram = [t for t in api.texts()[before:] if "Telegram itself" not in t]
            state = next(iter(adapter._chats.values()))
            assert mask(telegram) == mask(web["replies"]), line
            assert engine.store.sessions[state.session_id].state == web["state"], line
            assert [d.partition(":")[2] for _, d in api.last_buttons() or []] == \
                [q["value"] for q in web["quick_replies"]], line
        assert web["state"] == "DONE"
        channels = sorted(r.channel for r in engine.store.reports.values() if r.category == "abuse"
                          and r.hospital_id and r.department == "maternity")
        assert "telegram" in channels and "web" in channels


async def test_telegram_report_counts_in_the_analyst_patterns():
    from app import analyst as A
    adapter, _api, store, engine = make()
    for i in range(5):
        await adapter.handle_update(msg(STORY_FULL, chat=CHAT + i))
    assert len(store.reports) == 5 and {r.channel for r in store.reports.values()} == {"telegram"}
    rows = A.patterns(list(store.reports.values()), engine.pack)
    assert any(p["category"] == "abuse" for p in rows)


async def test_buttons_mirror_quick_replies_and_a_tap_sends_the_value():
    adapter, api, store, _ = make()
    await adapter.handle_update(msg(STORY_ASK))
    buttons = api.last_buttons()
    assert [label for label, _ in buttons] == ["Yes", "No"]
    assert [data.split(":", 1)[1] for _, data in buttons] == ["yes", "no"]
    await adapter.handle_update(tap(buttons[1][1]))
    assert api.answered == ["cb1"] and api.stripped == [55]
    assert next(iter(store.sessions.values())).state == "B1"


async def test_a_stale_button_never_answers_the_danger_check():
    adapter, api, store, _ = make()
    await adapter.handle_update(msg(STORY_FULL))                 # ends at the opt-in question
    old_no = api.last_buttons()[1][1]
    await adapter.handle_update(msg("/start"))
    await adapter.handle_update(msg(STORY_ASK))                  # now at the danger check
    sent_before = len(api.sent)
    await adapter.handle_update(tap(old_no))
    session = [s for s in store.sessions.values() if s.state != "DONE"][-1]
    assert session.state == "S2" and len(api.sent) == sent_before
    assert api.answered == ["cb1"]                               # the spinner still stops


async def test_typing_an_answer_retires_the_buttons():
    adapter, api, _store, _ = make()
    await adapter.handle_update(msg(STORY_ASK))
    old_yes = api.last_buttons()[0][1]
    await adapter.handle_update(msg("no"))                       # typed instead of tapped
    sent_before = len(api.sent)
    await adapter.handle_update(tap(old_yes))
    assert len(api.sent) == sent_before


async def test_a_redelivered_update_is_handled_once():
    adapter, api, store, _ = make()
    update = msg(STORY_FULL)
    await adapter.handle_update(update)
    sent, state = len(api.sent), next(iter(store.sessions.values())).state
    await adapter.handle_update(update)
    assert len(store.reports) == 1 and len(api.sent) == sent     # no second report, no second answer
    assert next(iter(store.sessions.values())).state == state    # and the replay did not answer the opt-in


async def test_no_identifier_is_stored_or_logged(caplog):
    caplog.set_level(logging.DEBUG)
    adapter, _api, store, _ = make()
    for line in ("hi", STORY_FULL, "yes", "/status nonsense", "/forget"):
        await adapter.handle_update(msg(line))
    dump = json.dumps([s.model_dump(mode="json") for s in store.sessions.values()]
                      + [r.model_dump(mode="json") for r in store.reports.values()])
    for needle in (str(CHAT), "Adaeze", "adaeze_o"):
        assert needle not in dump and needle not in caplog.text
    assert str(CHAT) not in repr(vars(adapter))


async def test_groups_get_no_reply_and_no_session():
    adapter, api, store, _ = make()
    await adapter.handle_update(msg(STORY_FULL, chat=-100123, chat_type="supergroup"))
    assert api.sent == [] and store.sessions == {} and store.reports == {}


async def test_forget_deletes_the_session_and_says_so():
    adapter, api, store, _ = make()
    await adapter.handle_update(msg(STORY_ASK))
    assert len(store.sessions) == 1
    await adapter.handle_update(msg("/forget"))
    assert store.sessions == {} and "deleted this unfinished conversation" in api.texts()[-1]
    assert next(iter(adapter._chats.values())).session_id is None


async def test_start_with_a_pack_name_uses_that_pack_and_adds_the_telegram_privacy_line():
    adapter, api, store, _ = make()
    await adapter.handle_update(msg("/start ke-nairobi"))
    assert next(iter(store.sessions.values())).pack == "ke-nairobi"
    assert any("Telegram itself can see" in t for t in api.texts())


async def test_unverified_notices_are_skipped_not_replaced_by_the_fallback():
    adapter, api, _store, _ = make(allow_unverified=False)
    await adapter.handle_update(msg("/start"))
    await adapter.handle_update(msg("/forget"))
    await adapter.handle_update(msg("/status"))
    joined = "\n".join(api.texts())
    assert "Telegram itself" not in joined and "I have recorded what you told me" not in joined
    assert "safe place" in joined                                # the conversation itself is unaffected


async def test_status_and_nextday():
    adapter, api, _store, _ = make()
    await adapter.handle_update(msg(STORY_FULL))
    code = re.search(r"[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}", "\n".join(api.texts())).group()
    await adapter.handle_update(msg(f"/status {code}"))
    assert "on record" in api.texts()[-1]
    await adapter.handle_update(msg(f"/nextday {code}"))
    assert [d.split(":", 1)[1] for _, d in api.last_buttons()] == ["1", "2", "3", "4"]
    await adapter.handle_update(msg("/nextday AAAA-AAAA-AAAA"))
    assert "could not find" in api.texts()[-1]


async def test_a_command_never_reaches_the_engine_as_text():
    """With demo mode off, "/nextday <code>" must not become the answer to "which hospital?"."""
    adapter, api, store, engine = make(demo_mode=False)
    seen = []
    original = engine.handle_message

    async def spy(session_id, channel, text, **kw):
        seen.append(text)
        return await original(session_id, channel, text, **kw)

    engine.handle_message = spy
    await adapter.handle_update(msg(STORY_ASK))
    await adapter.handle_update(msg("/nextday 7K3M-9QWX-2B4D"))
    await adapter.handle_update(msg("/whatever"))
    assert seen == [STORY_ASK] and "could not find" not in "\n".join(api.texts())
    assert "did not quite understand" in api.texts()[-1]
    assert "7K3M" not in json.dumps([x.model_dump(mode="json") for x in store.sessions.values()])
    assert api.last_buttons() is None and adapter._chats                 # and the danger buttons still work
    danger_no = next(b for _, _, b in api.sent if b)[1][1]
    await adapter.handle_update(tap(danger_no))
    assert next(iter(store.sessions.values())).state == "B1"


async def test_a_tap_with_a_value_that_was_never_offered_is_ignored():
    adapter, api, store, _ = make()
    await adapter.handle_update(msg(STORY_ASK))
    nonce, sent = api.last_buttons()[0][1].split(":")[0], len(api.sent)
    await adapter.handle_update(tap(f"{nonce}:tap:danger"))
    assert next(iter(store.sessions.values())).state == "S2" and len(api.sent) == sent   # engine never asked


async def test_a_tap_after_the_session_expired_is_ignored():
    from datetime import UTC, datetime, timedelta
    adapter, api, store, _ = make()
    await adapter.handle_update(msg(STORY_ASK))
    session = next(iter(store.sessions.values()))
    session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    sent = len(api.sent)
    await adapter.handle_update(tap(api.last_buttons()[1][1]))
    assert len(api.sent) == sent and len(store.sessions) == 1


async def test_forget_can_be_retried_when_the_delete_fails():
    adapter, _api, store, _engine = make()
    await adapter.handle_update(msg(STORY_ASK))
    original = store.delete_session

    async def down(session_id):
        raise RuntimeError("database is down")

    store.delete_session = down
    await adapter.handle_update(msg("/forget"))
    assert len(store.sessions) == 1 and next(iter(adapter._chats.values())).session_id
    store.delete_session = original
    await adapter.handle_update(msg("/forget"))
    assert store.sessions == {}


async def test_a_tap_is_acknowledged_in_order_with_other_messages():
    adapter, api, _store, _ = make()
    await adapter.handle_update(msg(STORY_ASK))
    state = next(iter(adapter._chats.values()))
    async with state.lock:                                   # an earlier update is still being handled
        import asyncio
        pending = asyncio.create_task(adapter.handle_update(tap(api.last_buttons()[1][1])))
        await asyncio.sleep(0.01)
        assert api.answered == []                            # nothing happens out of turn
    await pending
    assert api.answered == ["cb1"]


async def test_non_text_messages_get_the_retry_line():
    adapter, api, _store, _ = make()
    update = msg("x")
    del update["message"]["text"]
    update["message"]["sticker"] = {"file_id": "abc"}
    await adapter.handle_update(update)
    assert "did not quite understand" in api.texts()[-1]


async def test_blocked_bot_deletes_the_open_session():
    adapter, api, store, _ = make()
    await adapter.handle_update(msg(STORY_ASK))
    api.block = True
    await adapter.handle_update(msg("no"))
    assert store.sessions == {}


async def test_engine_failure_sends_the_safety_text_not_silence():
    adapter, api, _store, engine = make()

    async def boom(*a, **k):
        raise RuntimeError(f"db down for chat {CHAT}")

    engine.handle_message = boom
    await adapter.handle_update(msg("hello there my friend"))
    assert "nearest other hospital" in api.texts()[-1]


async def test_rate_limit_drops_silently():
    adapter, api, _store, _ = make()
    for _ in range(45):
        await adapter.handle_update(msg("/status"))
    assert len(api.sent) <= 40


def test_long_text_is_split_under_the_telegram_limit():
    parts = split_text("word " * 2000)
    assert len(parts) == 3 and all(len(p) <= 4096 for p in parts)
    assert split_text("short") == ["short"] and split_text("") == []


async def test_keyboard_goes_on_the_last_part_only():
    adapter, api, _store, _ = make()
    state = adapter._state("k")
    await adapter._send(CHAT, state, ["a " * 3000, "b"], [("Yes", "yes")])
    assert [b is not None for _, _, b in api.sent] == [False, False, True]


async def test_oversized_callback_data_is_dropped_not_sent():
    adapter, api, _store, _ = make()
    state = adapter._state("k")
    await adapter._send(CHAT, state, ["q"], [("Long", "x" * 80), ("Yes", "yes")])
    assert [label for label, _ in api.last_buttons()] == ["Yes"]


def test_idle_chats_are_pruned():
    adapter, *_ = make()
    adapter._state("old").last_seen -= 3 * 3600
    adapter._state("new")
    adapter.prune()
    assert list(adapter._chats) == ["new"]


def test_the_engine_knows_nothing_about_channels_or_http():
    from pathlib import Path
    for path in (Path(__file__).resolve().parents[1] / "app" / "engine").glob("*.py"):
        source = path.read_text()
        for banned in ("app.channels", "fastapi", "httpx", "telegram_api"):
            assert not re.search(rf"^\s*(from|import)\s+{re.escape(banned)}", source, re.MULTILINE), (path.name, banned)


def test_the_adapter_does_not_import_fastapi():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "app" / "channels" / "telegram.py").read_text()
    assert "fastapi" not in source and "httpx" not in source


def _client():
    import os
    os.environ.update(EXTRACT_MODE="mock", STORE="memory", ALLOW_UNVERIFIED="true", DEMO_MODE="true")
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


def test_webhook_is_absent_when_the_channel_is_off():
    with _client() as c:
        c.app.state.telegram = None
        assert c.post("/telegram/webhook", json={}).status_code == 404


def test_webhook_checks_the_secret_then_hands_the_update_to_the_adapter():
    import time
    with _client() as c:
        api = FakeAPI()
        c.app.state.telegram = TelegramAdapter(c.app.state.engine, api, demo_mode=True)
        c.app.state.telegram_secret = "s" * 32
        assert c.post("/telegram/webhook", json=msg("hi")).status_code == 403
        assert c.post("/telegram/webhook", json=msg("hi"),
                      headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}).status_code == 403
        r = c.post("/telegram/webhook", json=msg("hi"), headers={"X-Telegram-Bot-Api-Secret-Token": "s" * 32})
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        for _ in range(50):
            if api.sent:
                break
            time.sleep(0.02)
        assert "safe place" in api.texts()[0]


def test_webhook_never_accepts_an_empty_secret():
    with _client() as c:
        c.app.state.telegram = TelegramAdapter(c.app.state.engine, FakeAPI())
        c.app.state.telegram_secret = ""
        assert c.post("/telegram/webhook", json=msg("hi")).status_code == 403


async def test_poller_refuses_when_a_webhook_is_set_and_never_deletes_it():
    from app.channels.telegram_poll import refuse_reason

    class Api:
        deleted = False

        async def webhook_info(self):
            return {"url": "https://example.test/telegram/webhook"}

        async def delete_webhook(self):
            self.deleted = True

    api = Api()
    assert "separate development bot" in await refuse_reason(api, railway_environment="")
    assert api.deleted is False
    assert "development only" in await refuse_reason(api, railway_environment="production")


async def test_poll_once_advances_the_offset_past_handled_updates():
    from app.channels.telegram_poll import poll_once
    adapter, api, _store, _ = make()

    async def get_updates(offset, timeout=25):
        return [msg("hi"), msg("hello")]

    api.get_updates = get_updates
    offset = await poll_once(adapter, api, None)
    assert offset > 0 and len(api.sent) >= 2
