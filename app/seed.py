"""Clearly-labelled sample reports for the demo. Fictional hospitals only.

Every row has is_sample=True, and every surface that shows them carries a
SAMPLE DATA banner. Deterministic, so the demo looks the same every time.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from app.engine import refcode
from app.engine.models import SUBTYPES, Followup, Report
from app.engine.packs import Pack
from app.store.base import Store

# (hospital index in the pack, category, count, department weights, patient_group weights,
#  time weights, severe share). Index-based so every country pack gets the same demo shape.
PLAN = [
    (0, "emergency_refused", 14, {"emergency": 9, "maternity": 1},
     {"adult": 6, "child": 3, "elderly": 2, "pregnant": 1}, {"night": 6, "day": 3, "weekend": 2}, 0.6),
    (0, "neglect", 7, {"ward": 5, "emergency": 2},
     {"elderly": 4, "adult": 3}, {"night": 5, "weekend": 2}, 0.15),
    (1, "abuse", 9, {"maternity": 7, "outpatient": 2},
     {"pregnant": 7, "adult": 2}, {"day": 5, "night": 4}, 0.0),
    (2, "detention", 6, {"maternity": 4, "ward": 2},
     {"pregnant": 3, "adult": 2, "newborn": 1}, {"unknown": 6}, 0.5),
    (4, "neglect", 8, {"maternity": 5, "paediatrics": 3},
     {"newborn": 4, "pregnant": 3, "child": 1}, {"night": 6, "weekend": 2}, 0.25),
    # Below the threshold on purpose: these must never appear in the analyst view.
    (3, "abuse", 3, {"records": 2, "outpatient": 1}, {"elderly": 2, "adult": 1}, {"day": 3}, 0.0),
    (2, "abuse", 4, {"ward": 4}, {"adult": 4}, {"day": 2, "night": 2}, 0.0),
]

SUMMARY = {
    "emergency_refused": "Reporter says emergency treatment was delayed until a payment was made ({subtype}).",
    "detention": "Reporter says a {subtype} situation continued over an unpaid bill.",
    "abuse": "Reporter describes {subtype} abuse by a member of staff.",
    "neglect": "Reporter says the patient went without attention for a long period ({subtype}).",
}


def _pick(rng: random.Random, weights: dict[str, int]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def build(pack: Pack | None = None, now: datetime | None = None) -> tuple[list[Report], list[Followup]]:
    pack = pack or Pack("ng-lagos")
    rng = random.Random(7)  # per pack, so adding a country never reshuffles another's demo data
    now = now or datetime.now(UTC)
    reports, followups = [], []
    for hospital_index, category, count, depts, groups, times, severe_share in PLAN:
        hospital_id = pack.hospitals[hospital_index].id
        subtypes = [s for s in SUBTYPES[category] if s != "other"]
        for i in range(count):
            subtype = rng.choice(subtypes)
            status = rng.choices(["new", "unchanged", "resolved", "worse", "left"], [4, 4, 1, 1, 1])[0]
            r = Report(
                ref_code_hmac=refcode.digest(refcode.generate(), "sample"),
                created_at=now - timedelta(days=rng.randint(1, 80), hours=rng.randint(0, 23)),
                pack=pack.id,
                language=rng.choice([pack.languages[0], pack.languages[0], pack.languages[-1]]),
                hospital_id=hospital_id,
                department=_pick(rng, depts),  # type: ignore[arg-type]
                category=category,  # type: ignore[arg-type]
                severity="severe" if rng.random() < severe_share else "not_severe",
                incident_timing=rng.choice(["today", "this_week", "this_month"]),
                reporter_role=rng.choice(["patient", "relative", "relative"]),
                patient_group=_pick(rng, groups),  # type: ignore[arg-type]
                subtype=subtype,
                harm_outcome=rng.choices(["unknown", "none", "condition_worsened", "death"], [5, 3, 3, 1])[0],
                time_bucket=_pick(rng, times),  # type: ignore[arg-type]
                money_demanded=True if category in ("emergency_refused", "detention") else None,
                amount_bucket=rng.choice(["medium", "large", "very_large"])
                if category in ("emergency_refused", "detention") else "unknown",
                summary_redacted=SUMMARY[category].format(subtype=subtype.replace("_", " ")),
                followup_opt_in=status != "new",
                status=status,  # type: ignore[arg-type]
                # One held-back report per larger pattern, so the analyst sees the review queue working.
                credibility="review" if (i == 0 and count >= 8) else "ok",
                extra={"review_reason": "possible_duplicate"} if (i == 0 and count >= 8) else {},
                is_sample=True,
            )
            reports.append(r)
            if status != "new":
                followups.append(Followup(report_id=r.id, status=status,  # type: ignore[arg-type]
                                          created_at=r.created_at + timedelta(days=1)))
    return reports, followups


async def seed(store: Store, packs: list[Pack]) -> int:
    existing = {r.pack for r in await store.list_reports() if r.is_sample}
    total = 0
    for pack in packs:
        if pack.id in existing:
            continue
        reports, followups = build(pack)
        for r in reports:
            await store.create_report(r)
        for f in followups:
            await store.add_followup(f)
        total += len(reports)
    return total
