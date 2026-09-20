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
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

from app.engine import refcode
from app.engine.machine import Engine
from app.engine.models import SESSION_TTL, EngineReply
from app.engine.packs import Pack
from app.ratelimit import DailyDedupe, RateLimiter

log = logging.getLogger(__name__)

CHANNEL = "telegram"
MAX_TEXT = 4096              # Telegram's limit for one message
MAX_CALLBACK_BYTES = 64      # Telegram's limit for a button's callback_data
SEEN_UPDATES = 2000
_DASHED = re.compile(r"\s*\w{4}-\w{4}-\w{4}\s*")


def _looks_like_code(text: str) -> bool:
    """Stricter than refcode.is_wellformed, which forgives spaces and I/L/O: "Alpha General" and
    "Appendicitis" are well-formed codes to it, and they are answers, not codes. So: the dashed shape
    the bot prints, or one unbroken word with a digit in it."""
    if not refcode.is_wellformed(text):
        return False
    word = text.strip()
    return bool(_DASHED.fullmatch(text)) or (" " not in word and any(c.isdigit() for c in word))


COMMANDS = ("start", "status", "forget")     # shown in Telegram's menu; "nextday" joins them in demo mode
PRUNE_ABOVE = 1000

Buttons = list[tuple[str, str]]  # (label, callback_data)


class Blocked(Exception):
    """The person blocked the bot or deleted the chat. Stop, and keep nothing of theirs."""


class BotAPI(Protocol):
    async def send_message(self, chat_id: int, text: str, buttons: Buttons | None = None) -> None: ...
    async def answer_callback(self, callback_id: str) -> None: ...
    async def strip_keyboard(self, chat_id: int, message_id: int) -> None: ...
    async def typing(self, chat_id: int) -> None: ...
    async def set_commands(self, commands: list[tuple[str, str]]) -> None: ...


@dataclass
class ChatState:
    session_id: str | None = None
    pack: str | None = None      # only read when a conversation starts, as on web
    nonce: str | None = None     # ties buttons to the question they were sent with
    offered: frozenset[str] = frozenset()   # the values those buttons carried; nothing else is a tap
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
        self._timers: dict[str, asyncio.Task] = {}   # a quiet emergency is recorded; see _auto_record
        self._seen: set[int] = set()
        self._seen_order: deque[int] = deque()

    async def publish_commands(self) -> None:
        """Put the commands in Telegram's menu so nobody has to know them. The wording is the default
        pack's: the menu belongs to the bot, not to a conversation. Best effort; never blocks a start."""
        pack = self.engine.pack
        names = (*COMMANDS, "nextday") if self.demo_mode else COMMANDS
        menu = [(name, pack.label("telegram_commands", name, pack.languages[0])) for name in names]
        await self._quiet(self.api.set_commands(menu))

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
                    if tapped.get("id"):    # inside the lock: a later message must not overtake this tap
                        await self._quiet(self.api.answer_callback(tapped["id"]))
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
        current, offered = state.nonce, state.offered
        state.nonce, state.offered = None, frozenset()
        if not current or not hmac.compare_digest(nonce, current) or value not in offered:
            return
        session = await self.engine.store.get_session(state.session_id) if state.session_id else None
        if session is None or session.expired or session.state == "DONE":
            return                      # the question those buttons belonged to is gone
        await self._converse(chat_id, key, state, value)

    # ---------------------------------------------------------------- messages

    async def _on_message(self, chat_id: int, key: str, state: ChatState, message: dict) -> None:
        text = message.get("text")
        if not isinstance(text, str):
            pack, lang = await self._pack_lang(state)
            return await self._send(chat_id, state, [pack.message("E.retry", lang)])
        word, _, arg = text.strip().partition(" ")
        command, arg = word.split("@")[0].lower(), arg.strip()
        if _looks_like_code(text):
            # A code on its own is what T.status_usage has just asked for. It must never be read as
            # the answer to whatever question is still on screen.
            command, arg = "/status", text.strip()
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
        if command.startswith("/"):
            # Never hand a command to the engine as if it were the story: "/nextday <code>" with demo
            # mode off would otherwise put a reference code where a hospital name is expected.
            pack, lang = await self._pack_lang(state)
            return await self._send(chat_id, state, [pack.message("E.retry", lang)], keep_buttons=True)
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
        self._wait_for_quiet(chat_id, state, reply)
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
            state.nonce, state.offered = None, frozenset()
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
                state.offered = frozenset(data.partition(":")[2] for _, data in keyboard)
        for i, part in enumerate(parts):
            try:
                await self.api.send_message(chat_id, part, keyboard if keyboard and i == len(parts) - 1 else None)
            except Blocked:
                raise
            except Exception as e:  # noqa: BLE001 - one lost message must not lose the rest
                log.warning("Telegram send failed (%s)", type(e).__name__)

    # -------------------------------------------------- a quiet emergency

    def _wait_for_quiet(self, chat_id: int, state: ChatState, reply: EngineReply) -> None:
        """Every reply restarts or ends the wait. The chat id lives only in the waiting task, in
        memory, for as long as the wait: it is never stored, and a restart simply drops it."""
        key = self._key(chat_id)
        if (old := self._timers.pop(key, None)) and old is not asyncio.current_task():
            old.cancel()
        if reply.auto_record_after is not None:
            self._timers[key] = asyncio.create_task(
                self._auto_record(chat_id, key, state, reply.session_id, reply.auto_record_after))

    async def _auto_record(self, chat_id: int, key: str, state: ChatState, session_id: str, after: float) -> None:
        await asyncio.sleep(after)
        try:
            async with state.lock:
                if state.session_id != session_id:
                    return
                reply = await self.engine.auto_record(session_id)
                if reply is not None:
                    await self._render(chat_id, state, reply)
        except Blocked:
            await self._quiet(self._forget(state))
        except Exception as e:  # noqa: BLE001 - a background task has nobody to raise to
            log.warning("Auto-record failed (%s)", type(e).__name__)
        finally:
            if self._timers.get(key) is asyncio.current_task():
                del self._timers[key]

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
        state.nonce, state.offered = None, frozenset()
        if state.session_id:        # if this fails the id is kept, so /forget can be tried again
            await self.engine.store.delete_session(state.session_id)
        state.session_id, state.pack = None, None
