# Deploying to Railway

One always-on service. The engine, the chat page and the analyst view are the same process.
Run exactly **one replica with one worker**: the rate limiter and the daily dedupe salt live in
memory on purpose, so that IP addresses never touch a database.

## 1. Supabase (once)

1. Create a project at supabase.com.
2. SQL editor: paste and run `db/schema.sql`.
3. Settings > API: copy the **Project URL** and the **service_role** key. The service key is a
   secret. It goes in Railway variables only, never in the repository or the browser.

## 2. Railway

```bash
railway login
railway init -n hospital-pattern-bot
railway up --detach
railway domain
```

`railway.json` sets the builder (Railpack, which detects `uv.lock`), the start command and the
`/healthz` health check.

## 3. Variables

Set these in the Railway dashboard (Service > Variables) so secrets never enter shell history.

| Variable | Value |
|---|---|
| `EXTRACT_MODE` | `llm` |
| `OPENAI_API_KEY` | your key |
| `OPENAI_MODEL` | `openai:gpt-5-mini` |
| `STORE` | `supabase` |
| `SUPABASE_URL` | project URL |
| `SUPABASE_SERVICE_KEY` | service_role key |
| `REF_CODE_SECRET` | long random string, e.g. `openssl rand -hex 32`. **Never change it afterwards**: every issued reference code stops working if you do. |
| `ANALYST_PASSWORD` | 10+ characters. Share it with judges in the submission notes. |
| `ALLOW_UNVERIFIED` | `false` |
| `DEMO_MODE` | `true` for the hackathon (seeds labelled sample data, enables "simulate next day") |
| `PACK` | `ng-lagos` |

## 4. What the app checks for you

On Railway the app refuses to start if `REF_CODE_SECRET` or `ANALYST_PASSWORD` are defaults, or if
`ALLOW_UNVERIFIED` is on. It logs a loud `DEPLOYMENT CHECK` warning, but still starts, if the
extractor is the mock or the store is in-memory, so a throwaway demo deployment is possible.

Because `ALLOW_UNVERIFIED` must be off, **any pack entry still marked `"verified": false` is replaced
by the safe fallback message in production.** Before recording the demo video against the deployed
app, verify each entry against its primary source and flip its flag in `packs/ng-lagos/`.

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
- Analysts see redacted summaries only. There is nothing in the database that identifies a reporter.
