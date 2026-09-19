# Deploying to Railway

One always-on service. The engine, the chat page and the analyst view are the same process.
Run exactly **one replica with one worker**: the rate limiter and the daily dedupe salt live in
memory on purpose, so that IP addresses never touch a database.

## 1. Create the project, database and service

```bash
railway login
railway init -n hospital-pattern-bot
railway add -d postgres
railway add -s web
railway service web
```

## 2. Deploy

```bash
railway up --detach
railway domain
```

`railway.json` sets the builder (Railpack, which detects `uv.lock`), the start command and the
`/healthz` health check. The app creates its own tables on first start from `db/schema.sql`, so
there is no migration step.

## 3. Variables

Set these in the Railway dashboard (Service > Variables) so secrets never enter shell history.

| Variable | Value |
|---|---|
| `EXTRACT_MODE` | `llm` |
| `OPENAI_API_KEY` | your key |
| `OPENAI_MODEL` | `openai:gpt-5-mini` |
| `STORE` | `postgres` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (a Railway reference variable: it resolves to the private-network URL, so the database is never exposed publicly) |
| `REF_CODE_SECRET` | long random string, e.g. `openssl rand -hex 32`. **Never change it afterwards**: every issued reference code stops working if you do. |
| `ANALYST_PASSWORD` | 10+ characters. Share it with judges in the submission notes. |
| `ALLOW_UNVERIFIED` | `false` |
| `DEMO_MODE` | `true` for the hackathon (seeds labelled sample data, enables "simulate next day") |
| `PACK` | `ng-lagos` |

## 4. What the app checks for you

On Railway the app refuses to start if `REF_CODE_SECRET` or `ANALYST_PASSWORD` are defaults, or if
`ALLOW_UNVERIFIED` is on. It logs a loud `DEPLOYMENT CHECK` warning, but still starts, if the
extractor is the mock or the store is in-memory, so a throwaway demo deployment is possible.

Because `ALLOW_UNVERIFIED` must be off, **any gated pack entry without a recorded sign-off is
replaced by the safe fallback message in production.** Before recording the demo video against the
deployed app, open `/analyst/content`, check each entry against its primary source, and sign it off
with `uv run python -m app.verify mark ...`, then commit and redeploy.

## 5. After deploying

```bash
railway status
railway logs        # streams; press Ctrl+C after a few seconds
curl https://<your-domain>/healthz
```

Then open `/` on a phone, send one English and one Pidgin report, and confirm they show up in
`/analyst`.

## Privacy notes for operators

- Access logs are disabled (`--no-access-log`) so reporter IP addresses are never written anywhere.
- `/analyst` and `/api` responses are `no-store` and `noindex`.
- The database has no public endpoint; only the app service can reach it, over Railway's private network.
- Analysts see redacted summaries only. There is nothing in the database that identifies a reporter.
