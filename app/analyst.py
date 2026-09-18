"""Analyst view logic: patterns, slices, brief and CSV.

Everything here is template fill over counted data. No LLM is involved, so a
number in a brief can only be a number that exists in the store.

Privacy rule: the threshold applies to every cell of every slice, not only the
top-level pattern. Enough facets combined can describe one family.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import UTC, datetime, timedelta

from app.engine.models import Report
from app.engine.packs import Pack, UnverifiedContent

THRESHOLD = 5
WINDOW_DAYS = 90
SLICE_FIELDS = ("department", "patient_group", "subtype", "harm_outcome", "time_bucket")
_FOLLOWED_UP = {"resolved", "unchanged", "worse", "left"}


def _in_window(r: Report, now: datetime) -> bool:
    return r.created_at > now - timedelta(days=WINDOW_DAYS)


def patterns(reports: list[Report], pack: Pack, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    hospitals = {h.id: h for h in pack.hospitals}
    groups: dict[tuple[str, str], list[Report]] = {}
    for r in reports:
        h = hospitals.get(r.hospital_id or "") if r.pack == pack.id else None
        if h is None or h.facility_type == "private" or r.credibility == "excluded":
            continue
        if not _in_window(r, now):
            continue
        groups.setdefault((h.id, r.category), []).append(r)

    out = []
    for (hid, category), rs in groups.items():
        ok = [r for r in rs if r.credibility == "ok"]
        if len(ok) < THRESHOLD:
            continue
        out.append({
            "hospital_id": hid,
            "hospital": hospitals[hid].name,
            "category": category,
            "category_plain": pack.category_plain(category, "en"),
            "reports_90d": len(ok),
            "followed_up": sum(r.status in _FOLLOWED_UP for r in ok),
            "unchanged_or_worse": sum(r.status in ("unchanged", "worse") for r in ok),
            "severe": sum(r.severity == "severe" for r in ok),
            "flagged": sum(r.credibility == "review" for r in rs),
            "includes_sample_data": any(r.is_sample for r in ok),
        })
    return sorted(out, key=lambda p: (-p["reports_90d"], p["hospital"]))


def pattern_reports(reports: list[Report], hospital_id: str, category: str,
                    now: datetime | None = None) -> list[Report]:
    now = now or datetime.now(UTC)
    return sorted(
        (r for r in reports
         if r.hospital_id == hospital_id and r.category == category
         and r.credibility != "excluded" and _in_window(r, now)),
        key=lambda r: r.created_at, reverse=True,
    )


def slices(rs: list[Report]) -> dict[str, list[tuple[str, str]]]:
    """Breakdowns by facet. Cells under the threshold are masked, never shown as a number.

    If any cell in a breakdown is masked, the visible cells are rounded down to a
    multiple of the threshold ("10+"). Otherwise the masked value could be worked
    out by subtracting the visible cells from the pattern total.
    """
    ok = [r for r in rs if r.credibility == "ok"]
    out = {}
    for field in SLICE_FIELDS:
        counts = Counter(getattr(r, field) for r in ok).most_common()
        any_masked = any(n < THRESHOLD for _, n in counts)
        cells = []
        for value, n in counts:
            if n < THRESHOLD:
                cells.append((value, f"fewer than {THRESHOLD}"))
            elif any_masked:
                cells.append((value, f"{n // THRESHOLD * THRESHOLD}+"))
            else:
                cells.append((value, str(n)))
        out[field] = cells
    return out


def brief(pattern: dict, pack: Pack, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    start = now - timedelta(days=WINDOW_DAYS)
    ask = pack.asks.get(pattern["category"])
    law_line = "[legal reference pending verification]"
    ask_text = "[ask to be agreed]"
    if ask:
        ask_text = ask["ask_text"]
        try:
            pack._check("ask", pattern["category"], ask["verified"])
            law_line = ask["law_line"]
        except UnverifiedContent:
            pass

    n = pattern["reports_90d"]
    lines = [
        f"# {n} unverified reports of {pattern['category_plain']} at {pattern['hospital']}",
        "",
        f"Period: {start:%d %b %Y} to {now:%d %b %Y}. Prepared by {pack.org_name}.",
        "",
    ]
    if pattern["includes_sample_data"]:
        lines += ["> SAMPLE DATA. Fictional hospital, generated reports. For demonstration only.", ""]
    lines += [
        "## What was reported",
        "",
        f"In the last {WINDOW_DAYS} days, {n} people privately reported {pattern['category_plain']} "
        f"at {pattern['hospital']}. {pattern['severe']} of them said someone was in danger at the time "
        "they reported.",
    ]
    if pattern["followed_up"] >= THRESHOLD:
        lines.append(
            f"Of the {pattern['followed_up']} people who answered a follow-up the next day, "
            f"{pattern['unchanged_or_worse']} said nothing had changed or things had got worse."
        )
    lines += [
        "",
        "## The rule",
        "",
        law_line,
        "",
        "## What we are asking for",
        "",
        ask_text,
        "",
        "## Method and caveats",
        "",
        "- Reports are anonymous and unverified. No names, phone numbers or original messages are kept.",
        "- People who report are self-selected. These numbers are signals that warrant investigation, "
        "not rates, and must not be used to rank hospitals.",
        f"- Patterns are only shown once at least {THRESHOLD} separate credible reports exist. "
        "Duplicate and implausible reports are held back for review and not counted.",
        "- Many of these problems reflect how emergency care is funded and staffed. "
        "The ask is addressed to management and policy, not to individual staff.",
        "",
    ]
    return "\n".join(lines)


def patterns_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    cols = ["hospital", "category", "reports_90d", "severe", "followed_up",
            "unchanged_or_worse", "flagged", "includes_sample_data"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def facets_csv(reports: list[Report], pack: Pack) -> str:
    """Report-level facets for patterns above threshold. No summaries, no codes, no dedupe keys."""
    above = {(p["hospital_id"], p["category"]) for p in patterns(reports, pack)}
    names = {h.id: h.name for h in pack.hospitals}
    buf = io.StringIO()
    cols = ["week", "hospital", "category", "subtype", "severity", "department", "patient_group",
            "harm_outcome", "time_bucket", "money_demanded", "amount_bucket", "status", "is_sample"]
    w = csv.writer(buf)
    w.writerow(cols)
    for r in reports:
        if (r.hospital_id, r.category) not in above or r.credibility != "ok":
            continue
        week = r.created_at.strftime("%G-W%V")  # week, not day: exact dates can identify
        w.writerow([week, names[r.hospital_id], r.category, r.subtype, r.severity, r.department,
                    r.patient_group, r.harm_outcome, r.time_bucket, r.money_demanded,
                    r.amount_bucket, r.status, r.is_sample])
    return buf.getvalue()
