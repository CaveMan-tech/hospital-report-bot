import pytest

from app.engine.extract import mock_extract
from app.engine.machine import Engine, parse_yes_no
from app.engine.packs import Pack
from app.store.memory import MemoryStore


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def engine(store):
    return Engine(store, mock_extract, Pack("ng-lagos", allow_unverified=True), ref_secret="test-secret")


async def say(engine, sid, text, **kw):
    return await engine.handle_message(sid, "web", text, **kw)


def test_yes_no_parser():
    assert parse_yes_no("YES") is True
    assert parse_yes_no("yes o, e dey happen") is True
    assert parse_yes_no("No.") is False
    assert parse_yes_no("no o") is False
    assert parse_yes_no("hmm maybe") is None


async def test_greeting_then_nothing_stored(engine, store):
    r = await say(engine, None, "hi")
    assert r.state == "S1" and "safe place" in r.replies[0]
    assert "AI service" in r.replies[1]
    assert store.reports == {}


async def test_severe_branch_emergency_refused(engine, store):
    r = await say(engine, None, "hello")
    r = await say(engine, r.session_id,
                  "My mother is bleeding right now at Harmattan General Hospital emergency and they "
                  "refused to treat her until we pay deposit of 50 thousand")
    text = "\n".join(r.replies)
    assert "Section 20" in text and "112" in text          # escalation came first, no danger question
    assert r.ref_code and r.state == "B5"
    report = next(iter(store.reports.values()))
    assert report.severity == "severe" and report.escalation_shown
    assert report.category == "emergency_refused" and report.subtype == "deposit_demanded"
    assert report.hospital_id == "h-harmattan"
    r = await say(engine, r.session_id, "yes")
    assert r.done
    assert next(iter(store.reports.values())).followup_opt_in is True


async def test_severe_without_hospital_asks_only_for_hospital(engine, store):
    r = await say(engine, None, "They refused to treat my brother right now unless we pay deposit, he is unconscious")
    assert r.state == "A2" and "Which hospital" in r.replies[-1]
    r = await say(engine, r.session_id, "Iroko District Hospital")
    assert r.ref_code and next(iter(store.reports.values())).hospital_id == "h-iroko"


async def test_non_severe_branch_with_questions(engine, store):
    r = await say(engine, None, "A nurse slapped me and insulted me in front of everybody")
    assert r.state == "S2" and "danger right now" in r.replies[0]
    r = await say(engine, r.session_id, "no")
    assert r.state == "B1" and "Which hospital" in r.replies[-1]
    r = await say(engine, r.session_id, "Lagoon View General Hospital")
    assert "Which part" in r.replies[-1]
    r = await say(engine, r.session_id, "maternity ward")
    assert "When did this happen" in r.replies[-1]
    r = await say(engine, r.session_id, "last week")
    text = "\n".join(r.replies)
    assert "respect and dignity" in text                   # rights check
    assert "nurse in charge" in text                       # self-help
    assert r.ref_code and r.ref_code in text
    assert "counted" in text and "Open Ward Initiative" in text
    report = next(iter(store.reports.values()))
    assert (report.category, report.subtype, report.department) == ("abuse", "physical", "maternity")
    assert report.severity == "not_severe" and report.rights_shown == ["dignity"]


async def test_never_more_than_three_questions(engine, store):
    r = await say(engine, None, "something bad happened to us there and we are not happy at all")
    r = await say(engine, r.session_id, "no")
    asked = 0
    while r.state == "B1":
        asked += 1
        r = await say(engine, r.session_id, "i don't know")
    assert asked <= 3 and r.ref_code


async def test_past_story_skips_danger_check(engine):
    r = await say(engine, None, "Last month a nurse insulted my wife at Palm Grove Teaching Hospital maternity")
    assert all("danger right now" not in m for m in r.replies)


async def test_unclear_danger_answer_retries_then_assumes_severe(engine, store):
    r = await say(engine, None, "nobody is attending to my father on the ward, no doctor anywhere")
    assert r.state == "S2"
    r = await say(engine, r.session_id, "hmm")
    assert r.state == "S2"
    r = await say(engine, r.session_id, "what do you mean")
    assert "112" in "\n".join(r.replies)


async def test_raw_story_is_purged_once_report_is_written(engine, store):
    story = "My mother is bleeding right now at Harmattan General Hospital and they refused to treat her, pay deposit"
    r = await say(engine, None, story)
    session = store.sessions[r.session_id]
    assert "transcript" not in session.context and "extraction" not in session.context
    assert story not in session.model_dump_json()
    assert all(story not in rep.model_dump_json() for rep in store.reports.values())


async def test_ref_code_is_never_stored(engine, store):
    r = await say(engine, None, "My mother is bleeding right now at Harmattan General Hospital, refused to treat, deposit")
    dump = "".join(x.model_dump_json() for x in store.reports.values()) + \
           "".join(x.model_dump_json() for x in store.sessions.values())
    assert r.ref_code not in dump and r.ref_code.replace("-", "") not in dump


async def test_sexual_violence_hands_off_and_stores_nothing(engine, store):
    r = await say(engine, None, "a staff member sexually assaulted my sister on the ward at night")
    assert r.done and store.reports == {}


async def test_nonsense_gets_one_retry_then_ends(engine, store):
    r = await say(engine, None, "hi")
    r = await say(engine, r.session_id, "asdf qwer")
    assert "did not quite understand" in r.replies[0]
    r = await say(engine, r.session_id, "lol ok")
    assert r.done and store.reports == {}


async def test_pidgin_replies_in_pidgin(engine):
    r = await say(engine, None, "Nurse slap my pikin for ward, dem dey shout for us, wetin be this wahala")
    assert "Anybody dey for danger" in r.replies[0]


async def test_duplicate_from_same_source_is_flagged_for_review(engine, store):
    story = "A nurse slapped me last week at Harmattan General Hospital maternity ward"
    for _ in range(2):
        await say(engine, None, story, dedupe_key="k1")
    creds = sorted(r.credibility for r in store.reports.values())
    assert creds == ["ok", "review"]


async def test_unknown_hospital_name_is_kept_but_flagged(engine, store):
    await say(engine, None, "A nurse slapped me last week at Zebra Crossing Hospital maternity ward")
    report = next(iter(store.reports.values()))
    assert report.hospital_id is None and report.hospital_name_raw and report.credibility == "review"


async def test_followup_flow_and_lookup(engine, store):
    r = await say(engine, None, "A nurse slapped me last week at Harmattan General Hospital maternity ward")
    code = r.ref_code
    assert "on record" in await engine.lookup(code)
    assert "could not find" in await engine.lookup("AAAA-BBBB-CCCC")
    f = await engine.start_followup(code)
    assert f.state == "F1" and "Harmattan General Hospital" in f.replies[0]
    f = await say(engine, f.session_id, "2")
    assert f.done and next(iter(store.reports.values())).status == "unchanged"
    assert store.followups[0].status == "unchanged"


async def test_followup_worse_reenters_danger_check(engine, store):
    r = await say(engine, None, "Nobody attended to my father last week at Iroko District Hospital ward, no doctor")
    f = await engine.start_followup(r.ref_code)
    f = await say(engine, f.session_id, "3")
    assert f.state == "FS2" and "danger right now" in f.replies[-1]
    f = await say(engine, f.session_id, "yes")
    assert "112" in f.replies[0] and f.done


async def test_gate_blocks_unverified_escalation_in_production_mode(store):
    engine = Engine(store, mock_extract, Pack("ng-lagos", allow_unverified=False), "s")
    r = await say(engine, None, "My mother is bleeding right now at Harmattan General Hospital, refused to treat, deposit")
    text = "\n".join(r.replies)
    assert "Section 20" not in text and "still being checked" in text


async def test_self_harm_is_caught_even_if_the_model_misses_it(store):
    async def oblivious(transcript, context=""):
        from app.engine.models import Extraction
        return Extraction(category="other", is_nonsense=True)   # worst case: model sees nothing

    engine = Engine(store, oblivious, Pack("ng-lagos", allow_unverified=True), "s")
    for text in ("I don tire. After wetin dem do my pikin I just wan end my life.", "I wan die"):
        r = await engine.handle_message(None, "web", text) if len(text.split()) > 3 else None
        if r is None:   # short message: greet first, then the message
            g = await engine.handle_message(None, "web", "hi")
            r = await engine.handle_message(g.session_id, "web", text)
        assert r.done and "trained to help" in r.replies[0]
    assert store.reports == {}


def test_safety_net_does_not_fire_on_third_person_or_ordinary_stories():
    from app.engine.models import Extraction
    from app.engine.severity import apply_safety_net
    for text in ("my father wan die for that ward, nobody attend to am",
                 "they left her to die on a bench", "the nurse raised her voice at me"):
        assert apply_safety_net(Extraction(), text).safety_handoff == "none", text
    assert apply_safety_net(Extraction(), "the attendant raped a patient").safety_handoff == "sexual_violence"


def test_summary_scrub_removes_identifiers_the_model_let_through():
    from app.engine.severity import scrub_summary
    story = "My name is Mrs Folake Adeyemi, 08031234567, bed 14. Nurse Bisi insulted me."
    leaked = "Mrs Folake Adeyemi (0803 123 4567) in bed 14 says Nurse Bisi insulted her."
    out = scrub_summary(leaked, story)
    for bad in ("Folake", "Adeyemi", "0803", "bed 14", "Bisi"):
        assert bad not in out, (bad, out)
    assert "insulted her" in out
    clean = "A patient reports that a nurse refused to change her dressing last week."
    assert scrub_summary(clean, story) == clean


def test_pidgin_detected_by_markers_only_where_the_pack_supports_it():
    from app.engine.models import Extraction
    from app.engine.severity import apply_safety_net
    text = "Dem hold my brother for hospital since three days, dem no gree make e comot, e still dey there."
    assert apply_safety_net(Extraction(language="en"), text, ["en", "pcm"]).language == "pcm"
    assert apply_safety_net(Extraction(language="en"), text, ["en"]).language == "en"
    english = "They have held my brother at the hospital for three days and will not let him leave."
    assert apply_safety_net(Extraction(language="en"), english, ["en", "pcm"]).language == "en"


async def test_staff_whistleblower_flow(store):
    from app.engine.models import Extraction

    async def staff(transcript, context=""):
        return Extraction(category="emergency_refused", category_confidence=0.9, subtype="deposit_demanded",
                          reporter_role="staff", is_ongoing=True, critical_condition=True, severity="severe",
                          hospital_name_raw="Iroko District Hospital", department="emergency",
                          incident_timing="ongoing", time_bucket="night", summary_redacted="Staff report.",
                          ack="MODEL TEXT THAT MUST NEVER BE SHOWN")

    engine = Engine(store, staff, Pack("ng-lagos", allow_unverified=True), "s")
    r = await engine.handle_message(None, "web", "I am a nurse, management tells us to collect deposits every night")
    assert r.state == "S2" and "danger right now" in r.replies[0]
    assert "MODEL TEXT" not in " ".join(r.replies) and r.replies[0].startswith("I am sorry this happened")
    r = await engine.handle_message(r.session_id, "web", "no, I am at home")
    text = "\n".join(r.replies)
    assert "Section 20" not in text and "112" not in text            # no emergency steps for someone at home
    assert "courage to speak up" in text and "work phone" in text    # staff wording
    assert "What happened to you" not in text and "receipts" not in text
    report = next(iter(store.reports.values()))
    assert report.reporter_role == "staff" and report.severity == "not_severe" and report.rights_shown == []

    r = await engine.handle_message(None, "web", "I am a nurse, a patient is dying in casualty now and they want deposit")
    r = await engine.handle_message(r.session_id, "web", "yes")
    assert "Section 20" in "\n".join(r.replies)                     # staff who say YES get the escalation


# ---------------------------------------------------------------- fail-safe: the AI is down

async def _broken(transcript, context=""):
    raise RuntimeError("openai is down")


async def _hangs(transcript, context=""):
    import asyncio
    await asyncio.sleep(30)


async def test_emergency_still_gets_escalation_when_the_ai_is_down(store):
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    r = await engine.handle_message(None, "web",
        "My mother is bleeding right now at Harmattan General Hospital, they refused to treat her, pay deposit")
    text = "\n".join(r.replies)
    assert "Section 20" in text and "112" in text and r.ref_code
    report = next(iter(store.reports.values()))
    assert report.credibility == "review" and report.extra == {"degraded_extraction": True}
    assert "AI service could not be reached" in report.summary_redacted


async def test_ai_down_never_skips_the_danger_question(store):
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    # The keyword fallback reads this as clearly past. Normally that skips the question. Not when degraded.
    r = await engine.handle_message(None, "web", "Last month a nurse insulted my wife at Harmattan General Hospital maternity")
    assert r.state == "S2" and "danger right now" in r.replies[0]
    r = await engine.handle_message(r.session_id, "web", "yes")
    assert "112" in "\n".join(r.replies)


async def test_ai_down_never_bounces_the_reporter_as_nonsense(store):
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    g = await engine.handle_message(None, "web", "hi")
    r = await engine.handle_message(g.session_id, "web", "help me abeg")
    assert "did not quite understand" not in " ".join(r.replies) and r.state == "S2"


async def test_slow_ai_times_out_into_the_same_fallback(store):
    engine = Engine(store, _hangs, Pack("ng-lagos", allow_unverified=True), "s", extract_timeout=0.05)
    r = await engine.handle_message(None, "web", "Nobody is attending to my father on the ward, no doctor anywhere at all")
    assert r.state == "S2"


async def test_self_harm_handoff_still_works_when_the_ai_is_down(store):
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    r = await engine.handle_message(None, "web", "After wetin dem do my pikin I just wan end my life")
    assert r.done and "trained to help" in r.replies[0] and store.reports == {}


async def test_degraded_reports_are_not_counted_until_an_analyst_accepts_them(store):
    from app import analyst as A
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    for _ in range(6):
        r = await engine.handle_message(None, "web", "A nurse slapped me last week at Harmattan General Hospital maternity ward")
        await engine.handle_message(r.session_id, "web", "no")
    assert len(store.reports) == 6
    assert A.patterns(list(store.reports.values()), Pack("ng-lagos")) == []


# ---------------------------------------------------------------- tap-to-answer

async def test_closed_questions_come_with_tap_to_answer_options(engine, store):
    r = await say(engine, None, "hi")
    assert r.quick_replies == []                                           # open question: no buttons
    r = await say(engine, r.session_id, "A nurse slapped me and insulted me in front of everybody")
    assert [(q.label, q.value) for q in r.quick_replies] == [("Yes", "yes"), ("No", "no")]   # danger check
    r = await say(engine, r.session_id, "no")
    assert r.state == "B1" and r.quick_replies == []                       # "which hospital?" is open
    r = await say(engine, r.session_id, "Lagoon View General Hospital")
    r = await say(engine, r.session_id, "maternity")
    r = await say(engine, r.session_id, "last week")
    assert r.state == "B5" and [q.value for q in r.quick_replies] == ["yes", "no"]            # opt-in
    code = r.ref_code
    r = await say(engine, r.session_id, "yes")
    assert r.done and r.quick_replies == []
    f = await engine.start_followup(code)
    assert [q.value for q in f.quick_replies] == ["1", "2", "3", "4"]
    assert f.quick_replies[1].label == "Nothing has changed"
    f = await say(engine, f.session_id, "3")
    assert f.state == "FS2" and [q.value for q in f.quick_replies] == ["yes", "no"]


async def test_tap_options_follow_the_reporters_language(engine):
    r = await say(engine, None, "Nurse slap my pikin last week for Harmattan General Hospital children ward, wetin be this wahala")
    code = r.ref_code
    await say(engine, r.session_id, "no")
    f = await engine.start_followup(code)
    assert f.quick_replies[2].label == "E don worse"


async def test_tapped_when_and_department_need_no_ai_call(store):
    calls = 0

    async def counting(transcript, context=""):
        nonlocal calls
        calls += 1
        return await mock_extract(transcript, context)

    engine = Engine(store, counting, Pack("ng-lagos", allow_unverified=True), "s")
    r = await engine.handle_message(None, "web", "A nurse slapped me and insulted me in front of everybody")
    r = await engine.handle_message(r.session_id, "web", "no")
    r = await engine.handle_message(r.session_id, "web", "Lagoon View General Hospital")
    assert [q.label for q in r.quick_replies][:3] == ["Emergency", "Maternity", "Children's ward"]
    before = calls
    r = await engine.handle_message(r.session_id, "web", "tap:maternity")
    assert [q.value for q in r.quick_replies] == ["tap:today", "tap:this_week", "tap:older"]
    r = await engine.handle_message(r.session_id, "web", "tap:older")
    assert calls == before and r.ref_code                                  # two answers, zero AI calls
    report = next(iter(store.reports.values()))
    assert report.department == "maternity" and report.incident_timing == "older"


async def test_typed_answers_still_work_and_junk_taps_are_ignored(engine, store):
    r = await say(engine, None, "A nurse slapped me and insulted me in front of everybody")
    r = await say(engine, r.session_id, "no")
    r = await say(engine, r.session_id, "Lagoon View General Hospital")
    r = await say(engine, r.session_id, "tap:<script>")                    # not an option: ignored, not stored
    r = await say(engine, r.session_id, "last week")                       # typed answer goes through the extractor
    assert r.ref_code
    report = next(iter(store.reports.values()))
    assert report.department == "unknown" and report.incident_timing == "this_week"
