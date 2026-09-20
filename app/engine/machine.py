"""The engine. One entry point, no knowledge of HTTP or any chat platform.

    Engine.handle_message(session_id, channel, text) -> EngineReply

Web chat, WhatsApp, Telegram and anything later are thin adapters around this.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta

from app.store.base import Store

from . import refcode
from .extract import Extractor, mock_extract
from .models import Channel, EngineReply, Extraction, Followup, QuickReply, Report, Session
from .packs import Pack
from .severity import apply_safety_net, decide

log = logging.getLogger(__name__)

TAP = "tap:"  # prefix on quick-reply values that map straight to a field value
MAX_QUESTIONS = 3
LOW_CONFIDENCE = 0.6
MAX_STORY_CHARS = 4000

_YES = {"yes", "y", "yeah", "yep", "yea", "true", "ok", "okay", "sure", "beeni", "ehen", "1"}
_NO = {"no", "n", "nope", "nah", "rara", "mba", "false", "2"}
_YES_PHRASES = ("na so", "e dey", "yes o", "in danger", "person dey")
_NO_PHRASES = ("no o", "not now", "nobody", "no one", "e no dey")
_FOLLOWUP_STATUS = {"1": "resolved", "2": "unchanged", "3": "worse", "4": "left"}


MORE_STORY_WORDS = 8  # longer than any hospital name or yes/no answer: the person is still telling us


def _more_story(text: str) -> bool:
    """People type in bursts. A long message sent while we wait for a short answer is more of the
    story, and must go to the classifier: never into a field, where it would be stored as typed."""
    return not text.startswith(TAP) and len(text.split()) > MORE_STORY_WORDS


def parse_yes_no(text: str) -> bool | None:
    low = re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()
    if not low:
        return None
    first = low.split()[0]
    if first in _YES:
        return True
    if first in _NO:
        return False
    if any(p in low for p in _NO_PHRASES):
        return False
    if any(p in low for p in _YES_PHRASES):
        return True
    return None


class Engine:
    def __init__(self, store: Store, extractor: Extractor, pack: Pack | list[Pack], ref_secret: str,
                 extract_timeout: float = 15.0):
        """`pack` may be one pack or several. The first is the default; each conversation
        picks its pack once, when it starts, and keeps it."""
        packs = pack if isinstance(pack, list) else [pack]
        self.store = store
        self.extract = extractor
        self.extract_timeout = extract_timeout
        self.packs: dict[str, Pack] = {p.id: p for p in packs}
        self.pack = packs[0]
        self.ref_secret = ref_secret

    def pack_for(self, pack_id: str | None) -> Pack:
        return self.packs.get(pack_id or "", self.pack)

    # ------------------------------------------------------------------ entry

    async def handle_message(
        self,
        session_id: str | None,
        channel: Channel,
        text: str,
        dedupe_key: str | None = None,
        pack_id: str | None = None,
    ) -> EngineReply:
        text = (text or "").strip()[:MAX_STORY_CHARS]
        session = await self.store.get_session(session_id) if session_id else None

        prefix: list[str] = []
        if session and (session.expired or session.state == "DONE"):
            if session.expired:
                prefix = [self._msg("E.expired", session)]
            session = None

        if session is None:
            pack = self.pack_for(pack_id)
            session = Session(channel=channel, pack=pack.id, context={"lang": pack.languages[0]})
            if dedupe_key:
                session.context["dedupe_key"] = dedupe_key
            await self.store.create_session(session)
            if len(text.split()) < 4:  # "hi", "hello", empty: greet and wait for the story
                greeting = [self._msg("S0.greeting", session), self._msg("S0.privacy", session)]
                return await self._reply(session, prefix + greeting)

        handler = {
            "S1": self._on_story,
            "S2": self._on_danger_answer,
            "A2": self._on_severe_hospital,
            "B1": self._on_field_answer,
            "B5": self._on_optin,
            "F1": self._on_followup_choice,
            "FS2": self._on_followup_danger,
        }[session.state]
        replies, ref_code = await handler(session, text)
        return await self._reply(session, prefix + replies, ref_code)

    async def _reply(self, session: Session, replies: list[str], ref_code: str | None = None) -> EngineReply:
        await self.store.save_session(session)
        return EngineReply(
            session_id=session.id,
            replies=[r for r in replies if r],
            state=session.state,
            ref_code=ref_code,
            done=session.state == "DONE",
            quick_replies=self._quick_replies(session),
        )

    def _quick_replies(self, s: Session) -> list[QuickReply]:
        """Tap-to-answer for every closed question. A stressed person, or one who does not type
        easily, should never have to spell out YES."""
        pack, lang = self.pack_for(s.pack), s.context.get("lang", "en")
        yes_no = s.state in ("S2", "B5", "FS2") or (
            s.state == "B1" and s.context.get("pending_field") == "category_confirm")
        if yes_no:
            return [QuickReply(label=pack.quick("yes", lang), value="yes"),
                    QuickReply(label=pack.quick("no", lang), value="no")]
        if s.state == "S1" and s.context.get("asked_for_story") and not s.context.get("danger_answer"):
            return [QuickReply(label=pack.quick("danger", lang), value=f"{TAP}danger")]
        if s.state == "F1":
            return [QuickReply(label=pack.quick("followup", lang, n), value=n) for n in ("1", "2", "3", "4")]
        field = s.context.get("pending_field") if s.state == "B1" else None
        if field in ("when", "department"):
            # Values are prefixed so a tap is recognised exactly and needs no AI call.
            return [QuickReply(label=pack.quick(field, lang, key), value=f"{TAP}{key}")
                    for key in pack.labels["quick"][field]]
        return []

    # ------------------------------------------------- extraction, fail-safe

    async def _extract(self, transcript: list[dict[str, str]], pack: Pack) -> tuple[Extraction, bool]:
        """Run the extractor. If the AI is slow, down or returns rubbish, DEGRADE, never fail.

        Returns (extraction, degraded). A person in an emergency ward must still get the danger
        question and the pre-written escalation when the model is unreachable. The keyword
        extractor stands in for the facets; the caller forces the danger question.
        """
        try:
            ex = await asyncio.wait_for(self.extract(transcript, pack.extraction_context()),
                                        timeout=self.extract_timeout)
            return ex, False
        except Exception as e:  # noqa: BLE001 - any failure here must degrade, not surface
            log.error("Extractor failed (%s); using keyword fallback", type(e).__name__)
            ex = await mock_extract(transcript, pack.extraction_context())
            ex.is_nonsense = False          # never bounce someone because our AI is down
            ex.category_confidence = 1.0    # no "is this mainly about…" question on a keyword guess
            ex.summary_redacted = "[Automatic summary unavailable: the AI service could not be reached.]"
            return ex, True

    # ------------------------------------------------------------ S1: story

    async def _on_story(self, s: Session, text: str):
        ctx = s.context
        if ctx.get("asked_for_story") and not ctx.get("danger_answer") and parse_yes_no(text) is True:
            text = f"{TAP}danger"  # they typed YES to "if someone is in danger…" instead of tapping
        if text == f"{TAP}danger":
            # Danger first, story later. Nothing is stored until they say what happened.
            ctx["danger_answer"] = True
            ctx["escalation_shown"] = True
            ctx["generic_escalation_sent"] = True
            return [self._msg("A1.generic", s), self._msg("S1.after_danger", s)], None
        ctx.setdefault("transcript", []).append({"role": "user", "text": text})
        pack = self.pack_for(s.pack)
        ex, degraded = await self._extract(ctx["transcript"], pack)
        if degraded:
            ctx["degraded"] = True
        ex = apply_safety_net(ex, " ".join(t["text"] for t in ctx["transcript"] if t["role"] == "user"),
                              pack.languages)
        ex.language = pack.language_or_default(ex.language)
        ctx["lang"] = ex.language

        if ex.safety_handoff != "none":
            # Out of scope for patterns. Hand off, store nothing. Checked before "nonsense"
            # so that a short message like "I wan die" is never met with a retry prompt.
            # Someone who wants to end their life needs a crisis line, not the sexual-violence
            # service, and the other way round. Packs may provide a message per kind.
            specific = f"E.handoff.{ex.safety_handoff}"
            return self._end(s, [specific if specific in pack.messages else "E.handoff"])

        if ex.is_nonsense:
            if ctx.get("retried"):
                return self._end(s, ["E.end"])
            ctx["retried"] = True
            ctx["transcript"] = []
            return [self._msg("E.retry", s)], None

        if not ex.has_incident and not ctx.get("degraded"):
            # "I would like to report an issue" is an intention, not a report. Do not sympathise
            # with nothing, do not run triage on nothing, and never store an empty report. Ask.
            # The danger button stays one tap away for someone who cannot type more right now.
            ctx["asked_for_story"] = ctx.get("asked_for_story", 0) + 1
            if ctx["asked_for_story"] > 2:
                return self._end(s, ["E.end"])
            ctx["transcript"] = []  # an announcement carries nothing worth keeping or re-reading
            return [self._msg("S1.tell_me", s)], None

        ctx["extraction"] = ex.model_dump()
        decision = decide(ex, ctx.get("danger_answer"))
        if ctx.get("degraded") and decision == "not_severe":
            decision = "ask"  # a keyword guess is never allowed to skip the danger question
        # The acknowledgement is pre-written, like everything else a reporter reads.
        ack = self._msg("S1.ack", s)
        if decision == "severe":
            return await self._severe(s, ex, ack=ack)
        if decision == "ask":
            s.state = "S2"
            return [self._msg("S2.danger_check", s, ack=ack)], None
        return await self._non_severe(s, ex, lead=[ack])

    # ----------------------------------------------------- S2: danger check

    async def _on_danger_answer(self, s: Session, text: str):
        ex = self._ex(s)
        answer = parse_yes_no(text)
        first = re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()[:1]
        if _more_story(text) and not (first and first[0] in _YES | _NO):
            return await self._on_story(s, text)   # not an answer: "nobody attended to her…" is no NO
        if answer is None:
            if not s.context.get("danger_retried"):
                s.context["danger_retried"] = True
                return [self._msg("S2.danger_retry", s)], None
            answer = True  # Still unclear: showing emergency steps costs little, missing one costs a lot.
        s.context["danger_answer"] = answer
        if decide(ex, danger_answer=answer) == "severe":
            return await self._severe(s, ex)
        return await self._non_severe(s, ex)

    # -------------------------------------------------------- severe branch

    async def _severe(self, s: Session, ex: Extraction, ack: str = ""):
        s.context["severity"] = "severe"
        s.context["escalation_shown"] = True
        key = self._escalation_key(ex.category, ex.subtype)
        escalation = self._msg(key, s)
        if s.context.get("generic_escalation_sent") and escalation == self._msg("A1.generic", s):
            escalation = ""  # they already have it from the danger button; do not repeat it
        if s.context.get("escalation_sent") == key:
            ack = escalation = ""  # they added to the story: the steps are already on their screen
        s.context["escalation_sent"] = key
        replies = [ack, escalation]
        if escalation:  # the law to show them, after what to do and never before it
            replies += self.pack_for(s.pack).escalation_references(key, s.context.get("lang", "en"))
        if not ex.hospital_name_raw:
            s.state = "A2"
            return replies + [self._msg("Q.hospital", s)], None
        more, code = await self._finalise(s, ex)
        return replies + more, code

    @staticmethod
    def _escalation_key(category: str, subtype: str = "") -> str:
        key = f"A1.{category}" if category in ("emergency_refused", "detention") else "A1.generic"
        if category == "detention" and subtype == "body_held":
            key = "A1.detention_body"  # a bereaved family needs different words, and no talk of "discharge"
        return key

    def _escalation(self, s: Session, category: str, subtype: str = "") -> str:
        return self._msg(self._escalation_key(category, subtype), s)

    async def _on_severe_hospital(self, s: Session, text: str):
        ex = self._ex(s)
        if _more_story(text) and not self.pack_for(s.pack).match_hospital(text):
            s.context["danger_answer"] = True   # more detail never takes someone out of the emergency branch
            return await self._on_story(s, text)
        ex.hospital_name_raw = text[:120] or None
        return await self._finalise(s, ex)

    # ---------------------------------------------------- non-severe branch

    async def _non_severe(self, s: Session, ex: Extraction, lead: list[str] | None = None):
        s.context["severity"] = "not_severe"
        replies = list(lead or [])
        if ex.clinical_complaint and not s.context.get("clinical_shown"):
            s.context["clinical_shown"] = True
            replies.append(self._msg("E.clinical", s))

        question = self._next_question(s, ex)
        if question:
            s.context["extraction"] = ex.model_dump()
            s.state = "B1"
            return replies + [question], None

        if ex.reporter_role == "staff":
            # Rights and self-help text is written for patients. A member of staff reporting
            # a practice gets wording for them, and nothing that nudges them to expose themselves.
            help_key = "B3.staff"
        else:
            rights = self.pack_for(s.pack).rights_for(ex.category, s.context["lang"])
            s.context["rights_shown"] = [rid for rid, _ in rights]
            replies += [text for _, text in rights]
            for rid, _ in rights:   # never on the emergency branch: that reply is what to do, not reading
                replies += self.pack_for(s.pack).references_for(rid, s.context["lang"])
            help_key = f"B3.{ex.category}" if ex.category in ("abuse", "neglect") else "B3.other"
        replies.append(self._msg(help_key, s))
        more, code = await self._finalise(s, ex)
        return replies + more, code

    def _next_question(self, s: Session, ex: Extraction) -> str | None:
        asked: list[str] = s.context.setdefault("asked", [])
        if len(asked) >= MAX_QUESTIONS:
            return None
        still_missing = {
            "hospital": not ex.hospital_name_raw,
            "department": ex.department == "unknown",
            "when": ex.incident_timing == "unknown",
        }
        for field in ("hospital", "department", "when"):
            if still_missing[field] and field not in asked:
                asked.append(field)
                s.context["pending_field"] = field
                return self._msg(f"Q.{field}", s)
        if (
            ex.category != "other"
            and ex.category_confidence < LOW_CONFIDENCE
            and "category_confirm" not in asked
        ):
            asked.append("category_confirm")
            s.context["pending_field"] = "category_confirm"
            plain = self.pack_for(s.pack).category_plain(ex.category, s.context["lang"])
            return self._msg("Q.category_confirm", s, category_plain=plain)
        return None

    async def _on_field_answer(self, s: Session, text: str):
        ex = self._ex(s)
        field = s.context.pop("pending_field", None)
        if field == "hospital" and _more_story(text) and not self.pack_for(s.pack).match_hospital(text):
            s.context["asked"].remove("hospital")       # not answered yet, so it does not use up a question
            if s.context.get("danger_answer") is False:
                s.context.pop("danger_answer")          # that NO was about a smaller story than this one
            return await self._on_story(s, text)
        if field == "hospital":
            ex.hospital_name_raw = text[:120] or None
        elif field == "category_confirm":
            if parse_yes_no(text) is False:
                ex.category, ex.subtype = "other", "other"
            ex.category_confidence = 1.0
        elif field in ("department", "when") and text.startswith(TAP):
            # A tapped option maps directly: instant, and it works when the AI is down.
            value = text[len(TAP):]
            if field == "department" and value in self.pack_for(s.pack).labels["quick"]["department"]:
                ex.department = value  # type: ignore[assignment]
            elif field == "when" and value in ("today", "this_week", "older"):
                ex.incident_timing = value  # type: ignore[assignment]
                if value == "older":
                    ex.is_ongoing = False if ex.is_ongoing is None else ex.is_ongoing
        elif field in ("department", "when"):
            transcript = s.context.get("transcript", [])
            transcript += [
                {"role": "bot", "text": self.pack_for(s.pack).message(f"Q.{field}", "en")},
                {"role": "user", "text": text},
            ]
            s.context["transcript"] = transcript
            fresh, degraded = await self._extract(transcript, self.pack_for(s.pack))
            if degraded:
                s.context["degraded"] = True
            # Only fill gaps. An answer to a follow-up never rewrites the category or severity.
            if ex.department == "unknown":
                ex.department = fresh.department
            if ex.incident_timing == "unknown":
                ex.incident_timing = fresh.incident_timing
            if ex.is_ongoing is None:
                ex.is_ongoing = fresh.is_ongoing
            if ex.time_bucket == "unknown":
                ex.time_bucket = fresh.time_bucket
            if ex.patient_group == "unknown":
                ex.patient_group = fresh.patient_group
            # A follow-up answer can reveal an emergency ("e dey happen now").
            if decide(ex, s.context.get("danger_answer")) == "severe":
                return await self._severe(s, ex)
        return await self._non_severe(s, ex)

    # --------------------------------------------------- receipt and opt-in

    async def _finalise(self, s: Session, ex: Extraction):
        ctx = s.context
        lang = ctx["lang"]
        pack = self.pack_for(s.pack)
        hospital = pack.match_hospital(ex.hospital_name_raw)
        code = refcode.generate()

        # Anything we are not sure about is held for a human, with the reason, never silently counted.
        dedupe_key = ctx.get("dedupe_key")
        reason = ""
        if ctx.get("degraded"):
            reason = "ai_unavailable"      # classified by keywords only: help the person, do not count it blind
        elif ex.implausible:
            reason = "implausible"
        elif ex.hospital_name_raw and hospital is None:
            reason = "unknown_hospital"
        elif dedupe_key and await self.store.find_recent_duplicate(
            dedupe_key, hospital.id if hospital else None, ex.category
        ):
            reason = "possible_duplicate"
        credibility = "review" if reason else "ok"
        extra = {"review_reason": reason} if reason else {}
        if ctx.get("degraded"):
            extra["degraded_extraction"] = True

        report = Report(
            ref_code_hmac=refcode.digest(code, self.ref_secret),
            channel=s.channel,
            pack=pack.id,
            language=lang,
            hospital_id=hospital.id if hospital else None,
            hospital_name_raw=None if hospital else ex.hospital_name_raw,
            department=ex.department,
            category=ex.category,
            secondary_categories=ex.secondary_categories,
            severity=ctx.get("severity", "not_severe"),
            incident_timing=ex.incident_timing,
            is_ongoing=ex.is_ongoing,
            reporter_role=ex.reporter_role,
            patient_group=ex.patient_group,
            subtype=ex.subtype,
            harm_outcome=ex.harm_outcome,
            time_bucket=ex.time_bucket,
            money_demanded=ex.money_demanded,
            amount_bucket=ex.amount_bucket,
            summary_redacted=ex.summary_redacted,
            extra=extra,
            rights_shown=ctx.get("rights_shown", []),
            escalation_shown=ctx.get("escalation_shown", False),
            credibility=credibility,
            dedupe_key=dedupe_key,
        )
        await self.store.create_report(report)

        # The raw story has done its job. Remove it from the session now, not at expiry.
        s.context = {"lang": lang}
        s.report_id = report.id
        s.state = "B5"

        replies = [self._msg("B4.receipt", s, ref_code=code)]
        # Only say "counted" when it is. A held report is recorded, not yet counted, and saying
        # otherwise would be a small lie at the exact moment we are asking to be trusted.
        if not ex.hospital_name_raw:
            outcome = "B4.no_hospital"
        elif reason == "unknown_hospital":
            outcome = "B4.unknown_hospital"
        elif credibility == "review":
            outcome = "B4.recorded"      # deliberately vague: do not teach a spammer what tripped
        else:
            outcome = "B4.counted"
        replies.append(self._msg(outcome, s))
        replies.append(self._msg("B5.optin", s))
        return replies, code

    async def _on_optin(self, s: Session, text: str):
        answer = parse_yes_no(text)
        if answer is None and not s.context.get("optin_reasked"):
            s.context["optin_reasked"] = True   # an unclear reply is not a NO: ask once more, then let it go
            return [self._msg("B5.optin", s)], None
        yes = answer is True
        report = await self.store.get_report(s.report_id) if s.report_id else None
        if report and yes:
            report.followup_opt_in = True
            report.followup_due_at = datetime.now(UTC) + timedelta(days=1)
            await self.store.save_report(report)
        return self._end(s, ["B5.yes" if yes else "B5.no"])

    # ------------------------------------------------------------ follow-up

    async def start_followup(self, ref_code: str, channel: Channel = "web") -> EngineReply | None:
        report = await self._report_for(ref_code)
        if report is None:
            return None
        s = Session(channel=channel, pack=report.pack, state="F1",
                    context={"lang": report.language}, report_id=report.id)
        await self.store.create_session(s)
        return await self._reply(s, [self._msg("F1.question", s, **self._report_fields(report))])

    async def _on_followup_choice(self, s: Session, text: str):
        status = _FOLLOWUP_STATUS.get(text.strip()[:1])
        report = await self.store.get_report(s.report_id) if s.report_id else None
        if status is None or report is None:
            return [self._msg("F1.retry", s)], None
        await self.store.add_followup(Followup(report_id=report.id, status=status))  # type: ignore[arg-type]
        report.status = status  # type: ignore[assignment]
        await self.store.save_report(report)
        if status == "worse":
            s.state = "FS2"
            return [self._msg("F2.worse", s), self._msg("S2.danger_check", s, ack="")], None
        if status == "unchanged":
            help_key = f"B3.{report.category}" if report.category in ("abuse", "neglect") else "B3.other"
            return self._end(s, ["F2.unchanged", help_key])
        return self._end(s, [f"F2.{status}"])

    async def _on_followup_danger(self, s: Session, text: str):
        report = await self.store.get_report(s.report_id) if s.report_id else None
        category = report.category if report else "other"
        if parse_yes_no(text) is False:
            help_key = f"B3.{category}" if category in ("abuse", "neglect") else "B3.other"
            return self._end(s, [help_key])
        if report:
            report.escalation_shown = True
            await self.store.save_report(report)
        s.state = "DONE"
        return [self._escalation(s, category, report.subtype if report else "")], None

    async def lookup(self, ref_code: str, lang: str = "en") -> str:
        report = await self._report_for(ref_code)
        if report is None:
            return self.pack.message("L.not_found", lang)
        return self.pack_for(report.pack).message("L.found", report.language, status=report.status,
                                                  **self._report_fields(report))

    async def _report_for(self, ref_code: str) -> Report | None:
        if not refcode.is_wellformed(ref_code):
            return None
        return await self.store.get_report_by_ref(refcode.digest(ref_code, self.ref_secret))

    def _report_fields(self, report: Report) -> dict[str, str]:
        lang = report.language
        pack = self.pack_for(report.pack)
        hospital = next((h.name for h in pack.hospitals if h.id == report.hospital_id), None)
        return {
            "category_plain": pack.category_plain(report.category, lang),
            "hospital": hospital or report.hospital_name_raw or pack.label("unknown_hospital", "", lang),
        }

    # --------------------------------------------------------------- helpers

    def _msg(self, key: str, s: Session, **fields: str) -> str:
        text = self.pack_for(s.pack).message(key, s.context.get("lang", "en"), **fields)
        return re.sub(r"^\s+", "", text)  # an empty {ack} leaves a leading space

    def _end(self, s: Session, keys: list[str]):
        replies = [self._msg(k, s) for k in keys]
        s.state = "DONE"
        s.context = {"lang": s.context.get("lang", "en")}
        return replies, None

    @staticmethod
    def _ex(s: Session) -> Extraction:
        return Extraction.model_validate(s.context.get("extraction", {}))
