# [BOT_NAME]: private hospital reporting, public patterns

Built for the Andela x Open Society Foundations hackathon, 2026.
Tracks: Safety, Reporting & Protection + Transparency & Accountability.

People with no audience report what happened to them at a public hospital, privately, in English
or Pidgin. They get immediate help: a danger check, their rights, practical next steps and a
reference code. An advocacy organisation gets clean, anonymised, aggregated patterns per hospital
that it can turn into public pressure.

> All hospitals and the partner organisation in this repository are fictional. All seeded reports
> are generated sample data and are labelled as such everywhere they appear.

## How it works

```
 Web chat ─────────────┐
 WhatsApp (adapter) ───┼─▶ engine.handle_message(session_id, channel, text)
 Telegram (adapter) ───┘        ├─ state machine + deterministic severity rules
                                ├─ extract()  → gpt-5-mini via Pydantic AI (structured output)
                                ├─ country pack: verified messages, rights, contacts, asks
                                └─ Store      → Postgres or in-memory
                                          │
                                          ▼
                          /analyst: patterns ≥ 5 reports, masked breakdowns,
                          one-click pattern brief, CSV export
```

- **The AI classifies and extracts. It never writes legal claims, phone numbers or statistics.**
  Every such message is pre-written in the country pack and carries a `verified` flag. The engine
  refuses to send unverified content and degrades to a safe fallback. This is enforced in code and
  covered by tests.
- **A missed emergency is the costliest failure**, so severity is decided by rules on top of the
  AI's output, and anything ambiguous asks the user directly. See `evals/`.
- **No identity is collected.** No name, phone number or login. The original message is removed the
  moment the report is written. The reference code is never stored, only an HMAC of it.
- **Patterns, not stories.** Nothing is public. Analysts see a pattern only once 5 credible reports
  exist, see redacted summaries only, and breakdown cells under 5 are masked.
- **Scales by country pack.** Everything jurisdiction-specific is in `packs/<id>/`. A new country or
  organisation is a new folder, not new code.

## Run it

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --port 8000
```

Chat: http://localhost:8000 · Analyst view: http://localhost:8000/analyst (any username, password
from `ANALYST_PASSWORD`).

With `EXTRACT_MODE=mock` and `STORE=memory` (the defaults) it runs with no API key and no database.
Set `EXTRACT_MODE=llm` and `OPENAI_API_KEY` for real extraction, and `STORE=postgres` with a
`DATABASE_URL` for persistence. The schema in `db/schema.sql` is applied automatically at startup.

`ALLOW_UNVERIFIED=true` is for local development only: it lets you see messages that have not yet
been checked against primary sources. Leave it off anywhere real people could reach.

## Test and evaluate

```bash
uv run pytest
TEST_DATABASE_URL=postgresql://localhost/hospital_bot_test uv run pytest   # also runs the store contract on real Postgres
uv run python -m evals.run
```

`evals/stories.jsonl` holds 30 hand-written stories: emergencies, past events, ambiguous reports,
clinical complaints, out-of-scope text, prompt injection, safety handoffs and a privacy check.
The headline metric is **missed emergencies, target zero**. Results are written to
`evals/RESULTS.llm.md`.

## Layout

| Path | What |
|---|---|
| `SPEC.md` | The build spec this repository was built from |
| `app/engine/` | Channel-independent engine: state machine, severity rules, extraction, packs, reference codes |
| `app/analyst.py` | Patterns, masked breakdowns, brief and CSV. Template fill only, no LLM |
| `app/store/` | `Store` interface with Postgres and in-memory implementations, held to one contract test suite |
| `app/main.py` | FastAPI wrapper: chat API, lookup, follow-up simulation, analyst pages |
| `packs/ng-lagos/` | Lagos country pack (fictional hospitals) |
| `evals/` | Evaluation set and runner |
| `docs/ai-workflow.md` | How AI coding tools were used |

## Limits

This is a proof of concept. It is not an emergency service and cannot send help. Escalation guidance
and every legal statement need review by a medical and a legal professional before any real-world use.
