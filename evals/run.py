"""Evaluate the extraction step plus the deterministic severity rules.

    uv run python -m evals.run            # uses EXTRACT_MODE / OPENAI_MODEL from .env
    EXTRACT_MODE=mock uv run python -m evals.run

Headline metric: MISSED EMERGENCIES. A story that is a real emergency must end up
either on the severe branch or at the danger check. It must never be treated as
not severe without asking. Target: zero.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.engine.extract import get_extractor
from app.engine.models import EXTRACTION_VERSION, Extraction
from app.engine.packs import Pack
from app.engine.severity import decide

HERE = Path(__file__).parent
CONCURRENCY = 5


def check(expect: dict, ex: Extraction, decision: str) -> dict[str, bool]:
    """One boolean per thing this story is meant to test."""
    out: dict[str, bool] = {}
    if expect.get("is_nonsense"):
        out["nonsense"] = ex.is_nonsense
        return out
    if "safety_handoff" in expect:
        out["handoff"] = ex.safety_handoff == expect["safety_handoff"]
        return out
    out["not_nonsense"] = not ex.is_nonsense
    if expect.get("severity") == "severe":
        out["emergency_caught"] = decision in ("severe", "ask")
    if expect.get("severity") == "not_severe":
        out["no_false_alarm"] = decision != "severe"
    if expect.get("must_ask"):
        out["asked"] = decision == "ask"
    if "category" in expect:
        out["category"] = ex.category in expect["category"]
    for field in ("subtype", "patient_group", "language", "reporter_role", "clinical_complaint"):
        if field in expect:
            out[field] = getattr(ex, field) == expect[field]
    if "hospital_contains" in expect:
        out["hospital"] = expect["hospital_contains"].lower() in (ex.hospital_name_raw or "").lower()
    if "ack_must_not_contain" in expect:
        out["ack_clean"] = expect["ack_must_not_contain"] not in ex.ack
    if "summary_must_not_contain" in expect:
        low = ex.summary_redacted.lower()
        out["summary_redacted"] = not any(x.lower() in low for x in expect["summary_must_not_contain"])
    return out


async def main() -> int:
    cfg = get_settings()
    extract = get_extractor(cfg.extract_mode, cfg.openai_model)
    stories = [json.loads(line) for line in (HERE / "stories.jsonl").read_text().splitlines() if line]
    sem = asyncio.Semaphore(CONCURRENCY)
    packs: dict[str, Pack] = {}

    def pack_of(story: dict) -> Pack:
        pid = story.get("pack", "ng-lagos")
        return packs.setdefault(pid, Pack(pid))

    async def run(story: dict):
        async with sem:
            try:
                pack = pack_of(story)
                ex = await extract([{"role": "user", "text": story["text"]}], pack.extraction_context())
                ex.language = pack.language_or_default(ex.language)  # same normalisation as the engine
            except Exception as e:  # noqa: BLE001 - a crash is a failed case, not a failed run
                return story, None, "error", {"extractor_ok": False}, str(e)
        decision = decide(ex)
        return story, ex, decision, check(story["expect"], ex, decision), ""

    results = await asyncio.gather(*(run(s) for s in stories))

    totals: dict[str, list[int]] = {}
    rows, missed = [], []
    for story, ex, decision, checks, err in results:
        for name, ok in checks.items():
            totals.setdefault(name, [0, 0])
            totals[name][0] += ok
            totals[name][1] += 1
        if checks.get("emergency_caught") is False or (
            story["expect"].get("severity") == "severe" and ex is None
        ):
            missed.append(story["id"])
        failed = [n for n, ok in checks.items() if not ok]
        rows.append((story["id"], ex.category if ex else "-", decision, "PASS" if not failed else "FAIL: " + ", ".join(failed), err))

    model = "mock keyword stub" if cfg.extract_mode == "mock" else cfg.openai_model
    lines = [
        "# Evaluation results",
        "",
        f"- Run: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        f"- Extractor: `{model}`, extraction version `{EXTRACTION_VERSION}`",
        f"- Stories: {len(stories)} hand-written (English and Pidgin; Nigeria and Kenya packs)",
        "",
        f"## Headline: missed emergencies = {len(missed)}" + (f" ({', '.join(missed)})" if missed else " (target: 0)"),
        "",
        "An emergency counts as caught if the rules put it on the severe branch or at the danger",
        "check. It is missed only if it would be treated as not severe without asking.",
        "",
        "| Check | Passed | Of |",
        "|---|---|---|",
        *[f"| {name} | {ok} | {n} |" for name, (ok, n) in sorted(totals.items())],
        "",
        "| Story | Category | Decision | Result |",
        "|---|---|---|---|",
        *[f"| {i} | {c} | {d} | {r}{' ' + e if e else ''} |" for i, c, d, r, e in rows],
        "",
    ]
    report = "\n".join(lines)
    suffix = "mock" if cfg.extract_mode == "mock" else "llm"
    (HERE / f"RESULTS.{suffix}.md").write_text(report)
    print(report)
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
