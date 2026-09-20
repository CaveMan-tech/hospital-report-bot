# Telegram Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram as a second channel on the unchanged engine, with no identifier ever stored or logged.

**Architecture:** `app/channels/telegram.py` turns one Telegram update into `Engine.handle_message` calls and `BotAPI` calls. `BotAPI` is a Protocol; `HttpBotAPI` implements it over httpx; tests use a fake. `app/main.py` exposes a webhook; `app/channels/telegram_poll.py` is a development poller. Chat ids are reduced to a salted HMAC held in memory only.

**Tech Stack:** Python 3.12+, FastAPI, httpx, pytest (asyncio auto mode), ruff (line length 110).

**Spec:** `docs/superpowers/specs/2026-09-20-telegram-channel-design.md`

**Rules that bind every task (from `CLAUDE.md`):** never write `"verified": true`; nothing in `app/engine/` may import `app.channels`, `fastapi` or `httpx`; never log or store a chat id, a name, a story or a reference code; log transport errors by `type(e).__name__` only. Run `uv run pytest` and `uv run ruff check app tests evals` before each commit.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `app/engine/packs.py` | modify | add `Pack.message_or_none` |
| `packs/ng-lagos/messages.json`, `packs/ke-nairobi/messages.json` | modify | three unverified Telegram strings |
| `app/config.py`, `.env.example` | modify | two settings, one production check |
| `app/channels/__init__.py` | create | empty |
| `app/channels/telegram.py` | create | adapter core |
| `app/channels/telegram_api.py` | create | Bot API over httpx |
| `app/channels/telegram_poll.py` | create | dev poller and webhook CLI |
| `app/main.py` | modify | webhook route, adapter in lifespan, fatal prefix, headers |
| `pyproject.toml` | modify | httpx to main dependencies |
| `tests/test_telegram.py`, `tests/test_telegram_api.py` | create | tests |
| `tests/test_packs.py`, `tests/test_deploy.py` | modify | tests |
| `SPEC.md`, `README.md`, `docs/deploy.md` | modify | docs |

---

### Task 1: `Pack.message_or_none` and the Telegram pack strings

**Files:** Modify `app/engine/packs.py`, `packs/ng-lagos/messages.json`, `packs/ke-nairobi/messages.json`. Test: `tests/test_packs.py`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_packs.py`)

```python
def test_message_or_none_skips_unverified_instead_of_sending_the_fallback():
    for pack_id in ("ng-lagos", "ke-nairobi"):
        pack = Pack(pack_id, allow_unverified=False)
        for key in ("S0.privacy.telegram", "T.forgotten", "T.status_usage"):
            assert pack.messages[key]["verified"] is False
            assert pack.message_or_none(key, "en") is None


def test_message_or_none_returns_verified_text_and_honours_dev_mode():
    assert "safe place" in Pack("ng-lagos").message_or_none("S0.greeting", "en")
    assert "/forget" in Pack("ng-lagos", allow_unverified=True).message_or_none("S0.privacy.telegram", "en")


def test_message_or_none_still_checks_nested_contacts():
    pack = Pack("ng-lagos", allow_unverified=False)
    pack.messages["X.test"] = {"verified": True, "en": "Call {contact:emergency}"}
    pack.contacts["emergency"] = {**pack.contacts["emergency"], "verified": False}
    assert pack.message_or_none("X.test", "en") is None
```

- [ ] **Step 2: Run** `uv run pytest tests/test_packs.py -q` — expect 3 failures (`KeyError` / `AttributeError`).

- [ ] **Step 3: Implement.** In `app/engine/packs.py`, directly after the `message` method:

```python
    def message_or_none(self, key: str, lang: str = "en", **fields: str) -> str | None:
        """For channel notices where the fallback would be untrue (it says "I have recorded what
        you told me"). Same gate as `message`; unverified text is simply not sent."""
        try:
            return self._message(key, lang, **fields)
        except UnverifiedContent:
            log.warning("Skipped unverified message %r", key)
            return None
```

In **both** `packs/*/messages.json`, add before the final `}` (ng-lagos entries also get `"pcm": null`; ke-nairobi has no `pcm` field, so omit it there):

```json
  "S0.privacy.telegram": {
    "verified": false,
    "en": "On Telegram, we do not keep or record your Telegram name, username or phone number. Telegram itself can see that you messaged this bot. Send /forget to delete an unfinished report here. To clear this chat from your phone, delete it in Telegram.",
    "pcm": null
  },
  "T.forgotten": {
    "verified": false,
    "en": "Done. I have deleted this unfinished conversation. Anything you already finished reporting holds no name and no story. To clear this chat from your phone, delete it in Telegram.",
    "pcm": null
  },
  "T.status_usage": {
    "verified": false,
    "en": "Send /status followed by your code, like this: /status 7K3M-9QWX-2B4D",
    "pcm": null
  }
```

- [ ] **Step 4: Run** `uv run pytest tests/test_packs.py tests/test_multipack.py -q` — expect all pass. (If `test_every_message_with_law_or_numbers_is_gated` objects to the digits in `T.status_usage`, read that test and change the example text, not the test: use "like this: /status followed by the code you were given".)

- [ ] **Step 5: Commit** `git commit -am "Packs: message_or_none, and unverified Telegram notices awaiting review"`

---

### Task 2: Settings and the production check

**Files:** Modify `app/config.py`, `.env.example`, `app/main.py` (fatal prefixes). Test: `tests/test_deploy.py`.

- [ ] **Step 1: Failing test** (append to `tests/test_deploy.py`)

```python
def test_telegram_token_needs_a_real_webhook_secret():
    bad = Settings(**{**GOOD, "telegram_bot_token": "123:abc", "telegram_webhook_secret": "short"})
    assert any(p.startswith("TELEGRAM_WEBHOOK_SECRET") for p in bad.production_problems())
    ok = Settings(**{**GOOD, "telegram_bot_token": "123:abc", "telegram_webhook_secret": "s" * 24})
    assert ok.production_problems() == []
    assert Settings(**GOOD).production_problems() == []          # channel off: nothing to check
```

- [ ] **Step 2: Run** `uv run pytest tests/test_deploy.py -q` — expect FAIL (extra field ignored, no problem reported).

- [ ] **Step 3: Implement.** In `app/config.py` after `demo_mode`:

```python
    # Telegram channel. Empty token = channel off. The secret is checked on every webhook call.
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
```

and in `production_problems()` before `return problems`:

```python
        if self.telegram_bot_token and len(self.telegram_webhook_secret) < 24:
            problems.append("TELEGRAM_WEBHOOK_SECRET must be 24+ characters when TELEGRAM_BOT_TOKEN is set")
```

In `app/main.py` `lifespan`, change the fatal tuple to
`("REF_CODE_SECRET", "ANALYST_PASSWORD", "ALLOW_UNVERIFIED", "TELEGRAM_")`.

Append to `.env.example`:

```
# Telegram channel. Leave the token empty to keep it off. Secret: openssl rand -hex 32
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
```

- [ ] **Step 4: Run** `uv run pytest tests/test_deploy.py -q` — PASS.
- [ ] **Step 5: Commit** `git commit -am "Config: Telegram token and webhook secret, refused in production without a real secret"`

---

### Task 3: The adapter core

**Files:** Create `app/channels/__init__.py` (empty), `app/channels/telegram.py`, `tests/test_telegram.py`.

- [ ] **Step 1: Write the tests** — `tests/test_telegram.py`:

```python
import json
import logging
import re

import pytest

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


async def test_same_conversation_gives_the_same_replies_as_the_web_channel():
    script = ["hi", STORY_ASK, "no", "Lagoon View General Hospital", "maternity", "last week", "no"]
    adapter, api, store, _ = make(allow_unverified=False)       # no Telegram extras: text must match exactly
    _, _, _, web = make(allow_unverified=False)
    sid, web_texts, web_states = None, [], []
    for line in script:
        r = await web.handle_message(sid, "web", line)
        sid = r.session_id
        web_texts += r.replies
        web_states.append(r.state)
    tg_states = []
    for line in script:
        await adapter.handle_update(msg(line))
        tg_states.append(next(iter(store.sessions.values())).state if store.sessions else None)
    assert mask(api.texts()) == mask(web_texts)
    assert tg_states[-1] == web_states[-1] == "DONE"
    report = next(iter(store.reports.values()))
    assert report.channel == "telegram" and report.category == "abuse"


async def test_telegram_report_counts_in_the_analyst_patterns():
    from app import analyst as A
    adapter, api, store, engine = make()
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
    adapter, api, store, _ = make()
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
    await adapter.handle_update(update)
    assert len(store.reports) == 1


async def test_no_identifier_is_stored_or_logged(caplog):
    caplog.set_level(logging.DEBUG)
    adapter, api, store, _ = make()
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
    adapter, api, store, _ = make(allow_unverified=False)
    await adapter.handle_update(msg("/start"))
    await adapter.handle_update(msg("/forget"))
    await adapter.handle_update(msg("/status"))
    joined = "\n".join(api.texts())
    assert "Telegram itself" not in joined and "I have recorded what you told me" not in joined
    assert "safe place" in joined                                # the conversation itself is unaffected


async def test_status_and_nextday():
    adapter, api, store, _ = make()
    await adapter.handle_update(msg(STORY_FULL))
    code = re.search(r"[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}", "\n".join(api.texts())).group()
    await adapter.handle_update(msg(f"/status {code}"))
    assert "on record" in api.texts()[-1]
    await adapter.handle_update(msg(f"/nextday {code}"))
    assert [d.split(":", 1)[1] for _, d in api.last_buttons()] == ["1", "2", "3", "4"]
    await adapter.handle_update(msg("/nextday AAAA-AAAA-AAAA"))
    assert "could not find" in api.texts()[-1]


async def test_nextday_is_not_a_command_outside_demo_mode():
    adapter, api, store, _ = make(demo_mode=False)
    await adapter.handle_update(msg("/nextday AAAA-AAAA-AAAA"))
    assert "could not find" not in "\n".join(api.texts())


async def test_non_text_messages_get_the_retry_line():
    adapter, api, store, _ = make()
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
    adapter, api, store, engine = make()

    async def boom(*a, **k):
        raise RuntimeError(f"db down for chat {CHAT}")

    engine.handle_message = boom
    await adapter.handle_update(msg("hello there my friend"))
    assert "nearest other hospital" in api.texts()[-1]


async def test_rate_limit_drops_silently():
    adapter, api, store, _ = make()
    for _ in range(45):
        await adapter.handle_update(msg("/status"))
    assert len(api.sent) <= 40


def test_long_text_is_split_under_the_telegram_limit():
    parts = split_text("word " * 2000)
    assert len(parts) == 3 and all(len(p) <= 4096 for p in parts)
    assert split_text("short") == ["short"] and split_text("") == []


async def test_keyboard_goes_on_the_last_part_only():
    adapter, api, store, _ = make()
    state = adapter._state("k")
    await adapter._send(CHAT, state, ["a " * 3000, "b"], [("Yes", "yes")])
    assert [b is not None for _, _, b in api.sent] == [False, False, True]


async def test_oversized_callback_data_is_dropped_not_sent():
    adapter, api, store, _ = make()
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
            assert not re.search(rf"^\s*(from|import)\s+{re.escape(banned)}", source, re.M), (path.name, banned)


def test_the_adapter_does_not_import_fastapi():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "app" / "channels" / "telegram.py").read_text()
    assert "fastapi" not in source and "httpx" not in source
```

- [ ] **Step 2: Run** `uv run pytest tests/test_telegram.py -q` — expect collection error (`No module named app.channels`).

- [ ] **Step 3: Implement** `app/channels/telegram.py`:

```python
"""Telegram channel: one update in, engine calls and Bot API calls out.

Knows nothing about web frameworks. The same `Engine.handle_message` the web chat uses does all
the thinking; this file only translates. It never decides severity and never writes a word the
reporter acts on: every string comes from the engine or the pack.

A Telegram chat id is an identifier, so it is never stored or logged. It is reduced to an HMAC
under a salt that lives only in this process, and the raw id is used for nothing but addressing
the reply. A restart forgets every chat; the next message simply starts a new conversation.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

from app.engine.machine import Engine
from app.engine.models import SESSION_TTL, EngineReply
from app.engine.packs import Pack
from app.ratelimit import DailyDedupe, RateLimiter

log = logging.getLogger(__name__)

CHANNEL = "telegram"
MAX_TEXT = 4096              # Telegram's limit for one message
MAX_CALLBACK_BYTES = 64      # Telegram's limit for a button's callback_data
SEEN_UPDATES = 2000
PRUNE_ABOVE = 1000

Buttons = list[tuple[str, str]]  # (label, callback_data)


class Blocked(Exception):
    """The person blocked the bot or deleted the chat. Stop, and keep nothing of theirs."""


class BotAPI(Protocol):
    async def send_message(self, chat_id: int, text: str, buttons: Buttons | None = None) -> None: ...
    async def answer_callback(self, callback_id: str) -> None: ...
    async def strip_keyboard(self, chat_id: int, message_id: int) -> None: ...
    async def typing(self, chat_id: int) -> None: ...


@dataclass
class ChatState:
    session_id: str | None = None
    pack: str | None = None      # only read when a conversation starts, as on web
    nonce: str | None = None     # ties buttons to the question they were sent with
    last_seen: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def split_text(text: str, limit: int = MAX_TEXT) -> list[str]:
    parts = []
    while len(text) > limit:
        cut = max(text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        if cut <= 0:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return [*parts, text] if text else parts


class TelegramAdapter:
    def __init__(self, engine: Engine, api: BotAPI, demo_mode: bool = False):
        self.engine, self.api, self.demo_mode = engine, api, demo_mode
        self.limiter = RateLimiter(limit=40, window_seconds=600)        # same numbers as web
        self.lookup_limiter = RateLimiter(limit=10, window_seconds=600)
        self.dedupe = DailyDedupe()
        self._salt = secrets.token_bytes(32)
        self._chats: dict[str, ChatState] = {}
        self._seen: set[int] = set()
        self._seen_order: deque[int] = deque()

    # ---------------------------------------------------------------- identity

    def _key(self, chat_id: int) -> str:
        return hmac.new(self._salt, str(chat_id).encode(), hashlib.sha256).hexdigest()[:32]

    def _state(self, key: str) -> ChatState:
        if len(self._chats) > PRUNE_ABOVE:
            self.prune()
        return self._chats.setdefault(key, ChatState())

    def prune(self) -> None:
        cutoff = time.monotonic() - SESSION_TTL.total_seconds()
        for key in [k for k, s in self._chats.items() if s.last_seen < cutoff and not s.lock.locked()]:
            del self._chats[key]

    def _is_replay(self, update: dict) -> bool:
        """The engine writes the report before it saves the session, so a redelivered final
        message could count twice. Telegram redelivers when it thinks a webhook call failed."""
        uid = update.get("update_id")
        if not isinstance(uid, int):
            return False
        if uid in self._seen:
            return True
        self._seen.add(uid)
        self._seen_order.append(uid)
        if len(self._seen_order) > SEEN_UPDATES:
            self._seen.discard(self._seen_order.popleft())
        return False

    # ------------------------------------------------------------------- entry

    async def handle_update(self, update: dict) -> None:
        if self._is_replay(update):
            return
        tapped = update.get("callback_query")
        message = (tapped or {}).get("message") if tapped else update.get("message")
        if tapped and tapped.get("id"):
            await self._quiet(self.api.answer_callback(tapped["id"]))   # stop the spinner, whatever follows
        chat = (message or {}).get("chat") or {}
        chat_id = chat.get("id")
        if not isinstance(chat_id, int) or chat.get("type") != "private":
            return                      # a story must never be invited into a group
        key = self._key(chat_id)
        if not self.limiter.allow(key):
            return
        state = self._state(key)
        async with state.lock:          # one chat's messages are handled in order
            state.last_seen = time.monotonic()
            try:
                if tapped:
                    await self._on_tap(chat_id, key, state, tapped, message)
                else:
                    await self._on_message(chat_id, key, state, message)
            except Blocked:
                await self._quiet(self._forget(state))
            except Exception as e:  # noqa: BLE001 - the reporter must still be told what to do
                # Type only: a message could carry the story, the chat, or a URL with the bot token.
                log.error("Telegram update failed (%s)", type(e).__name__)
                pack = self.engine.pack_for(state.pack)
                await self._quiet(self.api.send_message(chat_id, pack.message("E.unavailable", pack.languages[0])))

    async def _quiet(self, awaitable) -> None:
        try:
            await awaitable
        except Exception as e:  # noqa: BLE001
            log.warning("Telegram call failed (%s)", type(e).__name__)

    # -------------------------------------------------------------------- taps

    async def _on_tap(self, chat_id: int, key: str, state: ChatState, tapped: dict, message: dict) -> None:
        nonce, _, value = str(tapped.get("data") or "").partition(":")
        if isinstance(message.get("message_id"), int):
            await self._quiet(self.api.strip_keyboard(chat_id, message["message_id"]))
        # A button belongs to the question it was sent with. An old "No" must never answer a new
        # danger check, so anything but the current nonce stops here and never reaches the engine.
        if not state.nonce or not value or not hmac.compare_digest(nonce, state.nonce):
            return
        state.nonce = None
        await self._converse(chat_id, key, state, value)

    # ---------------------------------------------------------------- messages

    async def _on_message(self, chat_id: int, key: str, state: ChatState, message: dict) -> None:
        text = message.get("text")
        if not isinstance(text, str):
            pack, lang = await self._pack_lang(state)
            return await self._send(chat_id, state, [pack.message("E.retry", lang)])
        word, _, arg = text.strip().partition(" ")
        command, arg = word.split("@")[0].lower(), arg.strip()
        if command == "/start":
            await self._forget(state)
            state.pack = arg if arg in self.engine.packs else None
            return await self._converse(chat_id, key, state, "")
        if command == "/forget":
            pack, lang = await self._pack_lang(state)
            await self._forget(state)
            return await self._send(chat_id, state, [pack.message_or_none("T.forgotten", lang)])
        if command == "/status" or (command == "/nextday" and self.demo_mode):
            if not self.lookup_limiter.allow(key):
                return None
            if command == "/status":
                pack, lang = await self._pack_lang(state)
                reply = await self.engine.lookup(arg) if arg else pack.message_or_none("T.status_usage", lang)
                return await self._send(chat_id, state, [reply], keep_buttons=True)
            return await self._next_day(chat_id, state, arg)
        return await self._converse(chat_id, key, state, text)

    async def _next_day(self, chat_id: int, state: ChatState, code: str) -> None:
        reply = await self.engine.start_followup(code, CHANNEL)
        if reply is None:
            return await self._send(chat_id, state, [self.engine.pack.message("L.not_found")], keep_buttons=True)
        await self._forget(state)
        state.session_id = reply.session_id
        await self._render(chat_id, state, reply)

    async def _converse(self, chat_id: int, key: str, state: ChatState, text: str) -> None:
        await self._quiet(self.api.typing(chat_id))
        reply = await self.engine.handle_message(
            state.session_id, CHANNEL, text, dedupe_key=self.dedupe.key("tg:" + key), pack_id=state.pack)
        started = reply.session_id != state.session_id
        state.session_id = reply.session_id
        notice = None
        if started:
            pack, lang = await self._pack_lang(state)
            notice = pack.message_or_none("S0.privacy.telegram", lang)
        await self._render(chat_id, state, reply, notice)

    # --------------------------------------------------------------- rendering

    async def _render(self, chat_id: int, state: ChatState, reply: EngineReply, notice: str | None = None) -> None:
        texts = list(reply.replies)
        buttons = [(q.label, q.value) for q in reply.quick_replies]
        if notice:  # keep the question, and its buttons, as the last thing on screen
            texts.insert(len(texts) - 1 if buttons and texts else len(texts), notice)
        await self._send(chat_id, state, texts, buttons)

    async def _send(self, chat_id: int, state: ChatState, texts: list[str | None],
                    buttons: Buttons | None = None, keep_buttons: bool = False) -> None:
        """`keep_buttons`: a side answer (/status) must not retire the question still on screen."""
        parts = [p for t in texts if t for p in split_text(t)]
        if not parts:
            return
        keyboard: Buttons = []
        if not keep_buttons:
            state.nonce = None
        if buttons:
            nonce = secrets.token_urlsafe(6)
            for label, value in buttons:
                data = f"{nonce}:{value}"
                if len(data.encode()) > MAX_CALLBACK_BYTES:
                    log.warning("Quick reply value too long for a Telegram button: %r", value)
                    continue
                keyboard.append((label, data))
            if keyboard:
                state.nonce = nonce
        for i, part in enumerate(parts):
            try:
                await self.api.send_message(chat_id, part, keyboard if keyboard and i == len(parts) - 1 else None)
            except Blocked:
                raise
            except Exception as e:  # noqa: BLE001 - one lost message must not lose the rest
                log.warning("Telegram send failed (%s)", type(e).__name__)

    # ----------------------------------------------------------------- helpers

    async def _pack_lang(self, state: ChatState) -> tuple[Pack, str]:
        session = await self.engine.store.get_session(state.session_id) if state.session_id else None
        pack = self.engine.pack_for(session.pack if session else state.pack)
        lang = session.context.get("lang") if session else None
        return pack, pack.language_or_default(lang)

    async def _forget(self, state: ChatState) -> None:
        """Delete the unfinished conversation now. A finished report is untouched: it holds no
        story, and nothing links it to this chat. The entry is reset rather than removed so an
        update already waiting on its lock does not end up with a second state for one chat."""
        session_id, state.session_id, state.pack, state.nonce = state.session_id, None, None, None
        if session_id:
            await self.engine.store.delete_session(session_id)
```

Note on `test_a_stale_button_never_answers_the_danger_check`: `STORY_FULL` ends in state `B5` with Yes/No buttons; `/start` clears the nonce; the new story issues a new one. The old `No` carries the old nonce.

- [ ] **Step 4: Run** `uv run pytest tests/test_telegram.py -q` — all pass. Then `uv run ruff check app tests`.
- [ ] **Step 5: Commit** `git add app/channels tests/test_telegram.py && git commit -m "Telegram adapter: same engine, native buttons bound to their question, no identifier kept"`

---

### Task 4: `HttpBotAPI`

**Files:** Create `app/channels/telegram_api.py`, `tests/test_telegram_api.py`. Modify `pyproject.toml`.

- [ ] **Step 1: Tests** — `tests/test_telegram_api.py`:

```python
import json
import logging

import httpx
import pytest

from app.channels.telegram import Blocked
from app.channels.telegram_api import HttpBotAPI, TelegramError

TOKEN = "123456:SECRET-TOKEN"


def api_with(handler):
    return HttpBotAPI(TOKEN, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_send_message_is_plain_text_with_one_button_per_row():
    seen = {}

    def handler(request):
        seen["path"], seen["body"] = request.url.path, json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {}})

    await api_with(handler).send_message(5, "Hello *not bold*", [("Yes", "n:yes"), ("No", "n:no")])
    assert seen["path"].endswith("/sendMessage") and "parse_mode" not in seen["body"]
    assert seen["body"]["reply_markup"]["inline_keyboard"] == [
        [{"text": "Yes", "callback_data": "n:yes"}], [{"text": "No", "callback_data": "n:no"}]]


async def test_403_means_blocked():
    with pytest.raises(Blocked):
        await api_with(lambda r: httpx.Response(403, json={"ok": False, "error_code": 403})).send_message(5, "x")


async def test_429_waits_and_retries_once(monkeypatch):
    calls, slept = [], []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr("app.channels.telegram_api.asyncio.sleep", fake_sleep)

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"ok": False, "error_code": 429, "parameters": {"retry_after": 60}})
        return httpx.Response(200, json={"ok": True, "result": {}})

    await api_with(handler).send_message(5, "x")
    assert len(calls) == 2 and slept == [5]                     # capped


async def test_errors_never_carry_the_token(caplog):
    caplog.set_level(logging.DEBUG)

    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(TelegramError) as err:
        await api_with(handler).send_message(5, "x")
    assert TOKEN not in str(err.value) and TOKEN not in repr(err.value.__cause__) and TOKEN not in caplog.text
    assert logging.getLogger("httpx").level >= logging.WARNING
```

- [ ] **Step 2: Run** `uv run pytest tests/test_telegram_api.py -q` — collection error.

- [ ] **Step 3: Implement** `app/channels/telegram_api.py`:

```python
"""The Telegram Bot API over httpx. The bot token is part of every URL, so nothing here may log
a URL or let an httpx exception (whose text includes the URL) travel upwards."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.channels.telegram import Blocked, Buttons

MAX_RETRY_WAIT = 5


class TelegramError(Exception):
    pass


class HttpBotAPI:
    def __init__(self, token: str, client: httpx.AsyncClient | None = None):
        for noisy in ("httpx", "httpcore"):     # they log full request URLs at INFO
            logging.getLogger(noisy).setLevel(logging.WARNING)
        self._base = f"https://api.telegram.org/bot{token}/"
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, *, _retry: bool = True, _timeout: float = 10.0, **params):
        try:
            response = await self._client.post(self._base + method, json=params, timeout=_timeout)
            body = response.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TelegramError(f"{method}: {type(e).__name__}") from None
        if body.get("ok"):
            return body.get("result")
        code = body.get("error_code") or response.status_code
        if code == 403:
            raise Blocked
        if code == 429 and _retry:
            wait = (body.get("parameters") or {}).get("retry_after", 1)
            await asyncio.sleep(min(int(wait), MAX_RETRY_WAIT))
            return await self._call(method, _retry=False, _timeout=_timeout, **params)
        raise TelegramError(f"{method}: {code}")

    async def send_message(self, chat_id: int, text: str, buttons: Buttons | None = None) -> None:
        params: dict = {"chat_id": chat_id, "text": text}       # no parse_mode: pack text is never markup
        if buttons:
            params["reply_markup"] = {"inline_keyboard": [[{"text": label, "callback_data": data}]
                                                          for label, data in buttons]}
        await self._call("sendMessage", **params)

    async def answer_callback(self, callback_id: str) -> None:
        await self._call("answerCallbackQuery", callback_query_id=callback_id)

    async def strip_keyboard(self, chat_id: int, message_id: int) -> None:
        await self._call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                         reply_markup={"inline_keyboard": []})

    async def typing(self, chat_id: int) -> None:
        await self._call("sendChatAction", chat_id=chat_id, action="typing")

    async def get_updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        params: dict = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        return await self._call("getUpdates", _timeout=timeout + 10, **params) or []

    async def set_webhook(self, url: str, secret: str) -> None:
        await self._call("setWebhook", url=url, secret_token=secret, drop_pending_updates=True,
                         allowed_updates=["message", "callback_query"])

    async def delete_webhook(self) -> None:
        await self._call("deleteWebhook")

    async def webhook_info(self) -> dict:
        return await self._call("getWebhookInfo") or {}
```

In `pyproject.toml`, add `"httpx>=0.28.1",` to `[project] dependencies` (alphabetical, after `fastapi`) and remove it from the `dev` group. Run `uv lock`.

- [ ] **Step 4: Run** `uv run pytest tests/test_telegram_api.py tests/test_telegram.py -q` and ruff — pass.
- [ ] **Step 5: Commit** `git add -A && git commit -m "Bot API client over httpx; the token never reaches a log or an exception"`

---

### Task 5: Webhook route and lifespan wiring

**Files:** Modify `app/main.py`. Test: append to `tests/test_telegram.py`.

- [ ] **Step 1: Tests** (append; note the env line must sit above the `app.main` import, so put these imports inside the test functions)

```python
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
```

- [ ] **Step 2: Run** — expect 404s / attribute errors.

- [ ] **Step 3: Implement** in `app/main.py`.

Imports: add `from app.channels.telegram import TelegramAdapter` and `from app.channels.telegram_api import HttpBotAPI`.

In `lifespan`, after the transcriber line:

```python
    app.state.telegram, app.state.telegram_secret, bot_api = None, cfg.telegram_webhook_secret, None
    if cfg.telegram_bot_token and cfg.telegram_webhook_secret:
        bot_api = HttpBotAPI(cfg.telegram_bot_token)
        app.state.telegram = TelegramAdapter(app.state.engine, bot_api, demo_mode=cfg.demo_mode)
```

In `purge_loop`, after the purge call:

```python
            if app.state.telegram:
                app.state.telegram.prune()
```

After `task.cancel()`:

```python
    if bot_api:
        await bot_api.close()
```

In `privacy_headers`, change the prefix tuple to `("/analyst", "/api", "/telegram")`. In `robots`, add `Disallow: /telegram\n`.

After the `forget` route:

```python
_telegram_tasks: set[asyncio.Task] = set()


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Telegram adapter, webhook side. Answers at once and does the work afterwards, so Telegram
    never times out waiting on extraction and sends the same story again."""
    adapter = getattr(request.app.state, "telegram", None)
    if adapter is None:
        raise HTTPException(404)
    expected = getattr(request.app.state, "telegram_secret", "")
    sent = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not expected or not secrets.compare_digest(sent.encode(), expected.encode()):
        raise HTTPException(403)
    try:
        update = await request.json()
    except ValueError:
        return {"ok": True}
    if isinstance(update, dict):
        task = asyncio.create_task(adapter.handle_update(update))
        _telegram_tasks.add(task)                      # keep a reference until it finishes
        task.add_done_callback(_telegram_tasks.discard)
    return {"ok": True}
```

- [ ] **Step 4: Run** `uv run pytest -q` (whole suite) and ruff — pass.
- [ ] **Step 5: Commit** `git commit -am "Webhook: secret checked, answered at once, handled in the background"`

---

### Task 6: Development poller and webhook CLI

**Files:** Create `app/channels/telegram_poll.py`. Test: append to `tests/test_telegram.py`.

- [ ] **Step 1: Tests**

```python
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
    adapter, api, store, _ = make()

    async def get_updates(offset, timeout=25):
        return [msg("hi"), msg("hello")]

    api.get_updates = get_updates
    offset = await poll_once(adapter, api, None)
    assert offset > 0 and len(api.sent) >= 2
```

- [ ] **Step 2: Run** — import error.

- [ ] **Step 3: Implement** `app/channels/telegram_poll.py`:

```python
"""Development runner for the Telegram channel, and the webhook setup commands.

    uv run python -m app.channels.telegram_poll                 long polling, local only
    uv run python -m app.channels.telegram_poll set-webhook https://your-app.up.railway.app
    uv run python -m app.channels.telegram_poll delete-webhook

Use a separate development bot for polling: one bot cannot poll and have a webhook.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.channels.telegram import TelegramAdapter
from app.channels.telegram_api import HttpBotAPI
from app.config import get_settings

log = logging.getLogger(__name__)


async def refuse_reason(api, railway_environment: str) -> str | None:
    if railway_environment:
        return "The poller is for development only. On Railway the webhook does this job."
    if (await api.webhook_info()).get("url"):
        return ("This bot has a webhook set, so polling would fail and deleting it would switch off the "
                "deployed bot. Use a separate development bot, or run delete-webhook on purpose.")
    return None


async def poll_once(adapter: TelegramAdapter, api, offset: int | None) -> int | None:
    for update in await api.get_updates(offset):
        await adapter.handle_update(update)
        if isinstance(update.get("update_id"), int):
            offset = update["update_id"] + 1
    return offset


async def poll() -> None:
    from app.main import build_engine        # imported here: only the runner needs the web app's wiring
    from app.seed import seed

    cfg = get_settings()
    api = HttpBotAPI(cfg.telegram_bot_token)
    reason = await refuse_reason(api, cfg.railway_environment)
    if reason:
        sys.exit(reason)
    engine = await build_engine()
    if cfg.demo_mode:
        await seed(engine.store, list(engine.packs.values()))
    adapter = TelegramAdapter(engine, api, demo_mode=cfg.demo_mode)

    async def purge_loop():
        while True:  # same promise as the web app: expired sessions may hold an unfinished story
            await asyncio.sleep(600)
            await engine.store.purge_expired_sessions()
            adapter.prune()

    purge = asyncio.create_task(purge_loop())
    log.info("Telegram poller running. Ctrl-C to stop.")
    offset = None
    try:
        while True:
            try:
                offset = await poll_once(adapter, api, offset)
            except Exception as e:  # noqa: BLE001
                log.warning("Polling failed (%s); retrying", type(e).__name__)
                await asyncio.sleep(3)
    finally:
        purge.cancel()
        await api.close()


async def main(argv: list[str]) -> None:
    cfg = get_settings()
    if not cfg.telegram_bot_token:
        sys.exit("Set TELEGRAM_BOT_TOKEN first (from @BotFather).")
    command = argv[0] if argv else "poll"
    if command == "poll":
        return await poll()
    api = HttpBotAPI(cfg.telegram_bot_token)
    try:
        if command == "set-webhook" and len(argv) == 2 and argv[1].startswith("https://"):
            if len(cfg.telegram_webhook_secret) < 24:
                sys.exit("Set TELEGRAM_WEBHOOK_SECRET to 24+ characters first (openssl rand -hex 32).")
            await api.set_webhook(argv[1].rstrip("/") + "/telegram/webhook", cfg.telegram_webhook_secret)
            print("Webhook set.")
        elif command == "delete-webhook":
            await api.delete_webhook()
            print("Webhook deleted.")
        else:
            sys.exit(__doc__)
    finally:
        await api.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main(sys.argv[1:]))
    except KeyboardInterrupt:
        pass
```

- [ ] **Step 4: Run** `uv run pytest -q` and ruff — pass.
- [ ] **Step 5: Commit** `git add -A && git commit -m "Telegram poller for local development; never deletes a webhook by itself"`

---

### Task 7: Documentation

**Files:** Modify `SPEC.md`, `README.md`, `docs/deploy.md`.

- [ ] **Step 1: `SPEC.md`**
  - Line 421 paragraph: replace `Cut entirely: Telegram. Roadmap only: voice notes,` with `Roadmap only: Telegram voice notes,` (web voice notes are built; keep the rest of the list).
  - API table: add after the `/api/chat/forget` row:
    `| \`POST /telegram/webhook\` | Telegram adapter. Checks Telegram's secret header, answers at once, then passes the update to the same \`engine.handle_message\`. 404 when no bot token is set. |`
  - After the "engine is framework-independent" paragraph, add:

    ```markdown
    **Telegram is the second channel, and the proof of that claim.** `app/channels/telegram.py` translates updates into `engine.handle_message` calls and renders `quick_replies` as native buttons; the engine did not change. A chat id is an identifier, so it is never stored or logged: it is reduced to an HMAC under a salt that exists only in the running process, and used to find the conversation, rate-limit, and derive the daily dedupe key. A restart forgets every chat. Buttons carry a one-time token so a button from an earlier question can never answer the current one (an old "No" must not land on the danger check). Only private chats are answered. Telegram itself can see that a person messaged the bot; the pack says so in `S0.privacy.telegram`. The adapter relies on the service running as one process.
    ```

- [ ] **Step 2: `README.md`** — after the `VOICE_ENABLED` paragraph in "Run it":

    ```markdown
    ### Telegram

    The same engine answers on Telegram; `app/channels/telegram.py` is only a translator.

    1. Create a bot with [@BotFather](https://t.me/BotFather) and put its token in `TELEGRAM_BOT_TOKEN`.
    2. Set `TELEGRAM_WEBHOOK_SECRET` to a long random string (`openssl rand -hex 32`).
    3. Deployed: `uv run python -m app.channels.telegram_poll set-webhook https://<your-app>`.
    4. Local: `uv run python -m app.channels.telegram_poll`, with a separate development bot, because
       one bot cannot poll and have a webhook. With `STORE=memory` the poller has its own store; point
       it and the web app at the same Postgres to see Telegram reports on `/analyst`.
    5. Commands: `/start` (or `/start ke-nairobi`), `/forget`, `/status <code>`, and in demo mode `/nextday <code>`.

    No Telegram id, name or username is stored or logged. The Telegram-specific notices in the packs
    are unverified until a person reviews them, so production stays silent on those until then.
    ```

  Layout table: add `| \`app/channels/\` | Telegram adapter, Bot API client, development poller |` after the `app/engine/` row.

- [ ] **Step 3: `docs/deploy.md`** — add two rows to the Variables table:

    ```markdown
    | `TELEGRAM_BOT_TOKEN` | optional. From @BotFather. Empty keeps the Telegram channel off. |
    | `TELEGRAM_WEBHOOK_SECRET` | required with the token: 24+ random characters. The app refuses to start without it. Then run `set-webhook` once (see README). Keep `--workers 1`: the Telegram adapter holds its chat map in one process. |
    ```

- [ ] **Step 4:** `uv run pytest -q && uv run ruff check app tests evals` — pass.
- [ ] **Step 5: Commit** `git commit -am "Spec and docs: Telegram is the second channel"`

---

### Task 8: Verification

- [ ] `uv run pytest -q` — all green; `uv run ruff check app tests evals` — clean.
- [ ] `git grep -n '"verified": true' -- packs | grep -c 'T\.\|telegram'` — expect `0`.
- [ ] `grep -rn "fastapi\|httpx\|app.channels" app/engine/` — expect no output.
- [ ] Start the web preview and confirm the chat page still loads and is still under 10 KB (`test_page_is_tiny` covers the size).
- [ ] Report to the user what remains for them: review and switch on the three pack strings, write the Pidgin, create the bot, set the two variables, run `set-webhook`.
