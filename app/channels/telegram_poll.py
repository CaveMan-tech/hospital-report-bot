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
    from app.main import build_engine  # imported here: only the runner needs the web app's wiring
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
