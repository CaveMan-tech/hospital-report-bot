"""Deterministic severity rules, applied on top of the AI's output.

The AI never decides alone whether someone is in danger. A missed emergency is
the costliest failure this tool can have, so every ambiguous case asks the user.
"""

from __future__ import annotations

import re
from typing import Literal

from .models import Extraction

Decision = Literal["severe", "not_severe", "ask"]

# Safety net for handoffs. The model usually catches these; "usually" is not good enough for
# someone saying they want to die. First-person phrases only, to avoid "my father wan die".
_SELF_HARM = re.compile(
    r"\b(kill myself|end my (own )?life|take my (own )?life|suicid\w*|i (just )?(want to|wan|wanna) die"
    r"|(want to|wan) end (it all|my life)|no (wan|want to) live( again)?|make i (just )?die)\b", re.IGNORECASE)
_SEXUAL_VIOLENCE = re.compile(
    r"\b(rap(e|ed|ing)|sexual(ly)? (assault\w*|abus\w*|harass\w*)|molest\w*|defil\w*"
    r"|forced? (himself|herself|themselves) on)\b", re.IGNORECASE)


_PIDGIN = re.compile(
    r"\b(dey|wetin|abeg|dem|una|pikin|wahala|sharp sharp|comot|wey|no gree|na|sey|wan|abi|oga|well well"
    r"|no be|e don|don tire|sef)\b", re.IGNORECASE)  # no bare "am"/"don": they collide with "I am", "don't"
_NAME_INTRO = re.compile(
    r"\b(?i:my name is|my name na|i am|i be|na me be|call me|(?:mr|mrs|miss|ms|dr|nurse|sister|matron|doctor)\.?)"
    r"\s+((?:[A-Z][\w'\-]+\s?){1,3})")
_IDENTIFIERS = re.compile(r"(\+?\d[\d\s\-]{6,}\d)|\b(bed|room|ward|file|card|folder)\s*(no\.?|number|#)?\s*\d+\w*", re.IGNORECASE)


def apply_safety_net(ex: Extraction, user_text: str, languages: list[str] | None = None) -> Extraction:
    """Deterministic post-processing of the reporter's own words, on top of the AI output.

    The model is good at all of this. It is not the last line of defence for any of it.
    """
    # 1. Handoffs.
    if _SEXUAL_VIOLENCE.search(user_text):
        ex.safety_handoff = "sexual_violence"
    elif ex.safety_handoff == "none" and _SELF_HARM.search(user_text):
        ex.safety_handoff = "self_harm"
    if ex.safety_handoff != "none":
        ex.is_nonsense = False  # never bounce someone in crisis with "I did not understand"

    # 2. Reply language: enough Pidgin markers means Pidgin, whatever the model guessed.
    if languages and "pcm" in languages and ex.language != "pcm":
        words = max(len(user_text.split()), 1)
        hits = len(_PIDGIN.findall(user_text))
        if hits >= 3 and hits / words >= 0.08:
            ex.language = "pcm"

    # 3. Privacy: the stored summary must not carry identifiers, even if the model slips.
    ex.summary_redacted = scrub_summary(ex.summary_redacted, user_text)
    return ex


def scrub_summary(summary: str, user_text: str) -> str:
    names = set()
    for m in _NAME_INTRO.finditer(user_text):
        names.update(w for w in m.group(1).split() if len(w) > 2)
    for name in names:
        summary = re.sub(rf"\b{re.escape(name)}\b", "[name removed]", summary, flags=re.IGNORECASE)
    summary = _IDENTIFIERS.sub("[removed]", summary)
    return re.sub(r"(\[name removed\]\s*){2,}", "[name removed] ", summary).strip()


_PAST_TIMINGS = {"this_week", "this_month", "older"}


def clearly_past(ex: Extraction) -> bool:
    """True only when the user clearly placed the event in the past."""
    return ex.is_ongoing is False and ex.incident_timing in _PAST_TIMINGS


def decide(ex: Extraction, danger_answer: bool | None = None) -> Decision:
    # The user's own answer to the danger check always wins.
    if danger_answer is True:
        return "severe"

    if ex.category in ("emergency_refused", "detention"):
        # A member of staff describing a practice ("we are told to collect deposits", "people have
        # died waiting") trips the critical and timing signals in both directions, and is not
        # necessarily beside a patient in danger this minute. So staff are always asked.
        if ex.reporter_role == "staff":
            return "ask" if danger_answer is None else "not_severe"  # True was handled above
        if ex.is_ongoing is not False:
            return "severe"

    if ex.category == "neglect" and ex.is_ongoing is True and ex.critical_condition:
        return "severe"

    if danger_answer is False:
        return "not_severe"

    if clearly_past(ex):
        return "not_severe"

    # Includes severity == "uncertain" and an AI "severe" we cannot confirm by rule.
    return "ask"
