# Telegram channel: design

## Purpose

Show that the engine is channel agnostic by running a second channel, Telegram, against the same
`Engine.handle_message` the web chat uses. A report made in Telegram lands in the same store and
appears on the same analyst screen. `app/engine/` changes by one small method; everything else is
an adapter.

`SPEC.md` currently lists Telegram as cut. This work reverses that for text conversations and
updates `SPEC.md` to match. Telegram voice notes stay on the roadmap.

## Scope

In: text messages, native tap-to-answer buttons, `/start [pack]`, `/forget`, `/status <code>`,
`/nextday <code>` (demo mode only), webhook transport for Railway, long polling for local
development.

Out: voice notes, photos or documents, group chats, proactive next-day messages (the follow-up is
still started by the reporter or the demo control, as on web).

## Components

| File | Responsibility | Depends on |
|---|---|---|
| `app/channels/telegram.py` | `TelegramAdapter.handle_update(update: dict)`: turns one Telegram update into engine calls and Bot API calls. No FastAPI import. | `Engine`, `BotAPI` protocol, `RateLimiter`, `DailyDedupe`, settings values passed in |
| `app/channels/telegram_api.py` | `HttpBotAPI`: the Bot API over httpx. `send_message`, `answer_callback`, `strip_keyboard`, `typing`, `get_updates`, `set_webhook`, `delete_webhook`, `webhook_info`. | httpx |
| `app/channels/telegram_poll.py` | `python -m app.channels.telegram_poll [poll \| set-webhook <url> \| delete-webhook]`. Development runner. | the two above, `build_engine()` |
| `app/main.py` | `POST /telegram/webhook`, adapter construction in `lifespan`. | adapter |
| `app/engine/packs.py` | New `Pack.message_or_none(key, lang, **fields)`. | none new |

`BotAPI` is a `typing.Protocol`, so tests use a fake that records calls and no test touches the
network.

`httpx` moves from the dev dependency group to the main dependencies.

## Identity and privacy

A Telegram chat id is an identifier, so CLAUDE.md rule 4 applies.

- `key = HMAC-SHA256(salt, chat_id)`, where `salt` is 32 random bytes generated when the process
  starts and held only in memory.
- The adapter keeps one in-memory map: `key -> ChatState(session_id, pack, nonce, last_seen)`.
  The same `key` feeds the rate limiter and `DailyDedupe.key("tg:" + key)`.
- The raw chat id exists only as a local variable for the duration of one update, to address the
  reply. It is never written to the store, never logged, and never put in an exception message.
- Update bodies, names and usernames are never read beyond `chat.id`, `chat.type`, `text`,
  `callback_query.data` and ids needed to reply. None of them is logged.
- Transport errors are logged by exception type only (`type(e).__name__`), because httpx error
  messages contain the request URL and the URL contains the bot token. The `httpx` and `httpcore`
  loggers are set to WARNING for the same reason.
- A restart drops the map. The next message from that chat starts a new conversation. Finished
  reports are unaffected; they never held a link to the chat.
- Map entries idle longer than the session TTL are pruned, along with their locks, on each update
  once the map holds more than 1,000 entries, and by the purge loop.
- Only `chat.type == "private"` is answered. Anything from a group, supergroup or channel is
  dropped without a reply, so a story is never invited into a shared space.

## Update handling

1. Webhook: check `X-Telegram-Bot-Api-Secret-Token` against `TELEGRAM_WEBHOOK_SECRET` with
   `secrets.compare_digest`; 403 on mismatch; 404 when no bot token is configured. Parse the JSON,
   schedule `adapter.handle_update(update)` as a background task, return 200 at once. Telegram
   never waits on extraction, so it does not time out and redeliver.
2. Duplicate protection: the adapter keeps the last 2,000 `update_id`s in memory (a deque plus a
   set) and drops any it has seen. This matters because the engine creates the report before it
   saves the session, so a replayed final message could otherwise count twice.
3. Ordering: one `asyncio.Lock` per `key`. Updates from one chat are processed one at a time.
   The deployment runs a single uvicorn worker (`railway.json`, `Dockerfile`); the adapter relies
   on that and the spec says so.
4. Rate limit: 40 messages per 10 minutes per `key`, the same numbers as web. Over the limit, the
   update is dropped silently.
5. Malformed updates (no chat, no text and no callback data) are dropped.
6. Any exception while handling: log the type, send `E.unavailable` from the chat's pack. If that
   send also fails, give up quietly.

## Rendering

- Each string in `EngineReply.replies` is one `sendMessage`, plain text, no `parse_mode`, so pack
  text is never interpreted as markup. A string longer than 4,096 characters is split on the last
  newline or space before the limit. (The longest pack message today is about 800 characters.)
- `quick_replies` become an inline keyboard attached to the last message of the turn, one button
  per row. `callback_data = f"{nonce}:{value}"`.
- `nonce` is 8 random URL-safe characters, regenerated every time the adapter sends a turn that
  carries buttons, and cleared when a turn carries none. Engine values are short (`yes`, `no`,
  `1` to `4`, `tap:danger`, `tap:<key>`), and the adapter asserts that `callback_data` is at most
  64 bytes; a longer one is sent as a plain message without that button and logged as a warning
  naming the pack key, not the chat.
- `sendChatAction: typing` is sent before each engine call.

### Taps

On `callback_query`: answer the callback first (so the button stops spinning), then compare the
nonce in `callback_data` with the chat's current nonce.

- Match: clear the nonce, strip the keyboard from that message (best effort; failure is ignored),
  and pass `value` to the engine as the user's text.
- No match, or no current nonce: strip the keyboard and do nothing else. The value never reaches
  the engine.

This guarantees that a button from an earlier question cannot answer the current one. In
particular an old "No" cannot land on the danger check. Typing an answer instead of tapping also
retires the buttons, because the next turn issues a new nonce or none. The adapter makes no
severity decision at any point; it only relays text.

## Commands

| Command | Behaviour |
|---|---|
| `/start`, `/start <pack>` | Delete any open session for this chat, clear the nonce, begin a new conversation by calling the engine with empty text and `pack_id`. An unknown pack falls back to the default, as on web. Then send `S0.privacy.telegram` if it passes the verified gate. |
| `/forget` | `store.delete_session`, drop the map entry, send `T.forgotten` if verified. |
| `/status <code>` | `engine.lookup(code)`. Limited to 10 per 10 minutes per `key`, as on web. With no code, send `T.status_usage` if verified. |
| `/nextday <code>` | Only when `DEMO_MODE` is on; otherwise treated as ordinary text. `engine.start_followup(code, "telegram")`; on `None`, send the pack's existing `L.not_found`, which is what `engine.lookup` returns for an unknown code. Shares the lookup limit. |

A first message that is not a command starts a conversation exactly as on web: the engine greets
short openers and treats anything longer as the story. The Telegram privacy line is sent after the
engine's greeting whenever a new session is created.

Non-text messages (voice, photo, sticker, document, location) get `E.retry`.

## Transport failures

- `403` from `sendMessage` (the person blocked the bot): delete the open session, drop the map
  entry, stop.
- `429`: wait `retry_after` seconds, capped at 5, retry once, then give up on that message.
- Timeouts (10 s per call) and other errors: log the exception type, continue with the next
  message in the turn.

## Polling runner

Development only.

- Refuses to start when `RAILWAY_ENVIRONMENT` is set.
- Refuses to start when `getWebhookInfo` reports a webhook, and says to use a separate development
  bot or run `delete-webhook` on purpose. It never deletes a webhook by itself.
- Builds the engine with `build_engine()`, runs the same 10 minute `purge_expired_sessions` loop
  the web app runs, seeds demo data when `DEMO_MODE` is on, then loops on `getUpdates` with a 25 s
  long poll, advancing `offset` past each update after it has been handled.
- With `STORE=memory` the poller has its own store, so its reports are not visible to a separately
  running web app. To see them on `/analyst`, point both at the same Postgres, or use the webhook.

## The verified gate

`Pack.message_or_none` calls the existing `_message` and returns `None` on `UnverifiedContent`.
It goes through the same `_check`, including the nested `{contact:…}` checks, and honours
`ALLOW_UNVERIFIED` exactly as `message` does. It exists because `message` substitutes
`E.unverified_fallback` ("I have recorded what you told me…"), which would be a false statement
after `/forget` or in place of a privacy line.

New pack entries, in both `ng-lagos` and `ke-nairobi`, all written with `"verified": false` and
no translation (`pcm: null`), for a human to review, translate and switch on:

| Key | English draft |
|---|---|
| `S0.privacy.telegram` | "On Telegram, we do not keep or record your Telegram name, username or phone number. Telegram itself can see that you messaged this bot. Send /forget to delete an unfinished report here. To clear this chat from your phone, delete it in Telegram." |
| `T.forgotten` | "Done. I have deleted this unfinished conversation. Anything you already finished reporting holds no name and no story. To clear this chat from your phone, delete it in Telegram." |
| `T.status_usage` | "Send /status followed by your code, like this: /status 7K3M-9QWX-2B4D" |

The example follows the `XXXX-XXXX-XXXX` format produced by `app/engine/refcode.py`.

Until they are switched on, production sends none of them; the conversation itself is unaffected
because it uses only existing messages. Local development sees them with `ALLOW_UNVERIFIED=true`.

## Configuration

| Variable | Meaning |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From BotFather. Empty means the channel is off and the webhook route returns 404. |
| `TELEGRAM_WEBHOOK_SECRET` | Sent to Telegram by `set-webhook`, checked on every webhook call. |

`production_problems()` adds "TELEGRAM_WEBHOOK_SECRET must be 24+ characters when
TELEGRAM_BOT_TOKEN is set", and `lifespan` treats problems starting with `TELEGRAM_` as fatal.
Both variables are added to `.env.example`.

## Tests

`tests/test_telegram.py`, with a fake `BotAPI`, `MemoryStore` and the mock extractor:

1. Parity: the same scripted conversation through `POST /api/chat` and through the adapter yields
   the same reply texts (reference code masked) and the same states, and the Telegram report is
   stored with `channel == "telegram"` and counted by the analyst pattern query.
2. Buttons match `quick_replies`; a tap with the current nonce sends `value` to the engine.
3. A stale tap (old nonce) never reaches the engine; specifically, an opt-in "No" button replayed
   during a danger check leaves the session in `S2`.
4. A repeated `update_id` is handled once; one report is created.
5. The chat id appears nowhere in stored sessions, stored reports, or captured log output.
6. Group chats get no reply and create no session.
7. Webhook: wrong secret is 403, no token is 404, right secret is 200.
8. `/forget` deletes the session and the map entry.
9. `/start ke-nairobi` creates a session on that pack.
10. `/nextday` is ignored as a command when demo mode is off.
11. Unverified `T.*` text is skipped, and `E.unverified_fallback` is not sent in its place.
12. A reply over 4,096 characters is split and the keyboard is on the last part.
13. A 403 from the fake API deletes the session.
14. Nothing under `app/engine/` imports `app.channels`, `fastapi` or `httpx`.
15. `production_problems()` flags a token without a secret.

`tests/test_packs.py` gains a case for `message_or_none`.

## Documentation changes

- `SPEC.md`: Telegram moves out of "cut entirely" and is described as the second channel; Telegram
  voice joins the roadmap list; the endpoint table gains `POST /telegram/webhook`; a short
  paragraph records the identity rule above and what Telegram itself can see.
- `README.md`: setup in five steps (BotFather token, two env vars, `set-webhook`, or the poller
  with a separate development bot).
- `docs/deploy.md`: the two variables and the single-worker requirement.
