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
