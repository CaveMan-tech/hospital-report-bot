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
        # No parse_mode: pack text is never markup. No preview: a link stays a link, not a large card.
        params: dict = {"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}}
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

    async def set_commands(self, commands: list[tuple[str, str]]) -> None:
        await self._call("setMyCommands", commands=[{"command": name, "description": text}
                                                    for name, text in commands])

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
