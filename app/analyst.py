"""Analyst view logic: patterns, slices, brief and CSV.

Everything here is template fill over counted data. No LLM is involved, so a
number in a brief can only be a number that exists in the store.

Privacy rule: the threshold applies to every cell of every slice, not only the
top-level pattern. Enough facets combined can describe one family.
"""

from __future__ import annotations

import csv
import io
import re
import textwrap
from collections import Counter
from datetime import UTC, datetime, timedelta
from html import escape
from urllib.parse import quote

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
    law_line, ask_text = _law_and_ask(pattern, pack)

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


REVIEW_REASONS = {
    "unknown_hospital": "Hospital name not recognised",
    "possible_duplicate": "Possible duplicate (same source, hospital and problem within 24 hours)",
    "implausible": "Story flagged as inconsistent or spam-like",
    "ai_unavailable": "AI was unreachable; classified by keywords only",
    "": "Held by an analyst",
}


def review_queue(reports: list[Report], pack: Pack) -> list[dict]:
    """Everything held back for this pack, newest first, with why. Without this screen a held
    report would simply vanish: it is in no pattern, so nobody would ever see it."""
    names = {h.id: h.name for h in pack.hospitals}
    rows = []
    for r in sorted(reports, key=lambda r: r.created_at, reverse=True):
        if r.pack != pack.id or r.credibility != "review":
            continue
        reason = str(r.extra.get("review_reason", ""))
        rows.append({"report": r, "hospital": names.get(r.hospital_id or ""), "reason_code": reason,
                     "reason": REVIEW_REASONS.get(reason, reason)})
    return rows


def weekly_counts(rs: list[Report], weeks: int = 13, now: datetime | None = None) -> list[int]:
    """Credible reports per week, oldest first. For the analyst's eyes only: weekly numbers are
    small, so they never go into a brief, a thread or a card."""
    now = now or datetime.now(UTC)
    counts = [0] * weeks
    for r in rs:
        if r.credibility != "ok":
            continue
        age = (now - r.created_at).days // 7
        if 0 <= age < weeks:
            counts[weeks - 1 - age] += 1
    return counts


def trend(rs: list[Report], now: datetime | None = None) -> dict:
    """Compare the last 45 days with the 45 before. Words and totals only when both halves are
    big enough to show; otherwise just the word."""
    now = now or datetime.now(UTC)
    ok = [r for r in rs if r.credibility == "ok"]
    recent = sum((now - r.created_at).days < 45 for r in ok)
    earlier = sum(45 <= (now - r.created_at).days < 90 for r in ok)
    if recent >= earlier * 1.5 and recent - earlier >= 2:
        word = "rising"
    elif earlier >= recent * 1.5 and earlier - recent >= 2:
        word = "falling"
    else:
        word = "steady"
    showable = recent >= THRESHOLD and earlier >= THRESHOLD
    return {"word": word, "recent": recent if showable else None, "earlier": earlier if showable else None}


def sparkline_svg(counts: list[int], width: int = 104, height: int = 24) -> str:
    top = max(counts) or 1
    bar = width / len(counts)
    rects = "".join(
        f'<rect x="{i * bar + 1:.1f}" y="{height - max(c / top * (height - 2), 1 if c else 0):.1f}" '
        f'width="{bar - 2:.1f}" height="{max(c / top * (height - 2), 1 if c else 0):.1f}" rx="1"/>'
        for i, c in enumerate(counts))
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="Reports per week, last {len(counts)} weeks">{rects}</svg>')


def _dominant(rs: list[Report], field: str, labels: dict[str, str]) -> str | None:
    """A plain-words fact like "mostly at night", only when it is both safe and true: the top
    value covers at least half the credible reports and at least THRESHOLD of them."""
    ok = [r for r in rs if r.credibility == "ok"]
    if not ok:
        return None
    value, n = Counter(getattr(r, field) for r in ok).most_common(1)[0]
    if value in labels and n >= THRESHOLD and n * 2 >= len(ok):
        return labels[value]
    return None


_TIME_WORDS = {"night": "at night", "weekend": "at weekends", "day": "during the day"}
_DEPT_WORDS = {"emergency": "the emergency department", "maternity": "maternity", "paediatrics": "the children's ward",
               "ward": "the wards", "outpatient": "outpatients", "pharmacy": "the pharmacy", "records": "records"}


def _law_and_ask(pattern: dict, pack: Pack) -> tuple[str, str]:
    ask = pack.asks.get(pattern["category"])
    law_line, ask_text = "[legal reference pending verification]", "[ask to be agreed]"
    if ask:
        ask_text = ask["ask_text"]
        try:
            pack._check("ask", pattern["category"], ask, always_gated=True)
            law_line = ask["law_line"]
        except UnverifiedContent:
            pass
    return law_line, ask_text


def thread(pattern: dict, rs: list[Report], pack: Pack) -> list[str]:
    """A ready-to-post X thread for the partner organisation. Template fill only: every number is
    a number from the pattern, and the organisation, not this tool, is the publisher."""
    law_line, ask_text = _law_and_ask(pattern, pack)
    target = pack.meta.get("target", {})
    handle = target.get("x_handle", "")
    n = pattern["reports_90d"]
    sample = "[SAMPLE DATA, fictional hospital] " if pattern["includes_sample_data"] else ""

    what = [f"{pattern['severe']} of the {n} said someone was in danger at the moment they reported."]
    where, when = _dominant(rs, "department", _DEPT_WORDS), _dominant(rs, "time_bucket", _TIME_WORDS)
    if where or when:
        what.append("Most reports were " + " ".join(x for x in (f"about {where}" if where else "", when or "") if x) + ".")
    if pattern["followed_up"] >= THRESHOLD:
        what.append(f"Of {pattern['followed_up']} people who answered a check-in the next day, "
                    f"{pattern['unchanged_or_worse']} said nothing had changed or it was worse.")

    posts = [
        f"{sample}{n} people have privately reported {pattern['category_plain']} at {pattern['hospital']} "
        f"in the last {WINDOW_DAYS} days. These reports are unverified. Here is why they still need an answer. {handle}".strip(),
        " ".join(what),
        f"The rule: {law_line}",
        f"What we are asking {target.get('name', 'the hospital')} for: {ask_text} We will post the response here. Day 0.",
        f"Method: anonymous, unverified, self-selected reports collected by {pack.org_name}. They are signals that "
        f"warrant investigation, not rates, and not a ranking. Groups under {THRESHOLD} are never shown. "
        f"{pack.meta.get('method_url', '')}".strip(),
    ]
    posts = [part for p in posts for part in _split_post(p)]
    total = len(posts)
    return [f"{i}/{total} {p}" for i, p in enumerate(posts, 1)]


POST_LIMIT = 280 - len("10/10 ")


def _split_post(text: str) -> list[str]:
    """Pack content changes; a thread must never silently overflow. Split on sentence ends,
    then on words as a last resort."""
    if len(text) <= POST_LIMIT:
        return [text]
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.;:?!])\s+", text):
        for chunk in textwrap.wrap(sentence, POST_LIMIT) or [""]:
            if current and len(current) + 1 + len(chunk) > POST_LIMIT:
                parts.append(current)
                current = chunk
            else:
                current = f"{current} {chunk}".strip()
    return parts + ([current] if current else [])


def intent_url(text: str) -> str:
    return "https://x.com/intent/tweet?text=" + quote(text, safe="")


def card_svg(pattern: dict, pack: Pack) -> str:
    """1200x675 share card. Count, problem, hospital, the ask. No story, no slice, no small number."""
    _, ask_text = _law_and_ask(pattern, pack)
    esc = escape
    ask_lines = textwrap.wrap("We are asking: " + ask_text, 62)[:4]
    title_lines = textwrap.wrap(f"unverified reports of {pattern['category_plain']}", 34)[:2]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" width="1200" height="675" '
        'font-family="Helvetica, Arial, sans-serif">',
        '<rect width="1200" height="675" fill="#f6f4ef"/><rect width="1200" height="14" fill="#1f4d3a"/>',
        f'<text x="80" y="230" font-size="200" font-weight="700" fill="#1f4d3a">{pattern["reports_90d"]}</text>',
    ]
    for i, line in enumerate(title_lines):
        parts.append(f'<text x="420" y="{150 + i * 62}" font-size="50" font-weight="700" fill="#1d1b18">{esc(line)}</text>')
    parts.append(f'<text x="420" y="{150 + len(title_lines) * 62 + 4}" font-size="36" fill="#1d1b18">at {esc(pattern["hospital"])}</text>')
    parts.append(f'<text x="80" y="338" font-size="28" fill="#6b655c">in the last {WINDOW_DAYS} days · anonymous, unverified · '
                 'signals that warrant investigation, not rates</text>')
    parts.append('<line x1="80" y1="372" x2="1120" y2="372" stroke="#ddd6c9" stroke-width="2"/>')
    for i, line in enumerate(ask_lines):
        parts.append(f'<text x="80" y="{430 + i * 46}" font-size="34" fill="#1d1b18">{esc(line)}</text>')
    parts.append(f'<text x="80" y="630" font-size="26" fill="#6b655c">{esc(pack.org_name)}</text>')
    if pattern["includes_sample_data"]:
        parts.append('<g transform="rotate(-18 600 340)"><text x="600" y="360" text-anchor="middle" font-size="120" '
                     'font-weight="700" fill="#8a2d1c" fill-opacity="0.16">SAMPLE DATA</text></g>'
                     '<text x="1120" y="630" text-anchor="end" font-size="26" font-weight="700" fill="#8a2d1c">'
                     'SAMPLE DATA · fictional hospital</text>')
    parts.append("</svg>")
    return "".join(parts)


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
