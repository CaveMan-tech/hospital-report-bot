"""Deterministic severity rules, applied on top of the AI's output.

The AI never decides alone whether someone is in danger. A missed emergency is
the costliest failure this tool can have, so every ambiguous case asks the user.
"""

from __future__ import annotations

from typing import Literal

from .models import Extraction

Decision = Literal["severe", "not_severe", "ask"]

_PAST_TIMINGS = {"this_week", "this_month", "older"}


def clearly_past(ex: Extraction) -> bool:
    """True only when the user clearly placed the event in the past."""
    return ex.is_ongoing is False and ex.incident_timing in _PAST_TIMINGS


def decide(ex: Extraction, danger_answer: bool | None = None) -> Decision:
    # The user's own answer to the danger check always wins.
    if danger_answer is True:
        return "severe"

    if ex.category in ("emergency_refused", "detention") and ex.is_ongoing is not False:
        return "severe"

    if ex.category == "neglect" and ex.is_ongoing is True and ex.critical_condition:
        return "severe"

    if danger_answer is False:
        return "not_severe"

    if clearly_past(ex):
        return "not_severe"

    # Includes severity == "uncertain" and an AI "severe" we cannot confirm by rule.
    return "ask"
