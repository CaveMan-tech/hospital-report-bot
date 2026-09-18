# Rules for AI coding agents working in this repository

Read `SPEC.md` first. It is the source of truth; if code and spec disagree, raise it.

Non-negotiable design rules:

1. The LLM only classifies and extracts (`app/engine/extract.py`). It never writes legal claims,
   phone numbers, statistics, or anything the user will act on. Those come from `packs/`.
2. Never bypass the verified gate in `app/engine/packs.py`. Do not flip a `verified` flag to true;
   only a human who has checked the primary source does that.
3. Severity is decided by `app/engine/severity.py`, not by the model. When unsure, ask the user.
   Never add a path that treats a possible emergency as not severe without asking.
4. Never persist the raw story, the reference code, an IP address, or any identifier.
5. Nothing is public. Patterns need 5 credible reports; breakdown cells under 5 are masked.
6. Demo data uses fictional hospitals and a fictional organisation only.
7. Everything country-specific goes in `packs/<id>/`, never in code.
8. The engine must not import FastAPI or know about HTTP. Channels are adapters.

Workflow: write or update a test with every behaviour change. `uv run pytest` and
`uv run ruff check app tests evals` must pass before committing. Keep the chat page under 10 KB.
