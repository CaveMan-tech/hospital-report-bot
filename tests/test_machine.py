import pytest

from app.engine.extract import mock_extract
from app.engine.machine import Engine, parse_yes_no
from app.engine.packs import Pack
from app.store.memory import MemoryStore
from tests.helpers import say, unsigned


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def engine(store):
    return Engine(store, mock_extract, Pack("ng-lagos", allow_unverified=True), ref_secret="test-secret")


async def tell(engine, sid, text, **kw):
    return await say(engine, sid, text, finish=False, **kw)


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
    engine = Engine(store, mock_extract, unsigned("ng-lagos"), "s")
    r = await say(engine, None, "My mother is bleeding right now at Harmattan General Hospital, refused to treat, deposit")
    text = "\n".join(r.replies)
    assert "Section 20" not in text and "still being checked" in text


async def test_self_harm_is_caught_even_if_the_model_misses_it(store):
    async def oblivious(transcript, context=""):
        from app.engine.models import Extraction
        return Extraction(category="other", is_nonsense=True)   # worst case: model sees nothing

    engine = Engine(store, oblivious, Pack("ng-lagos", allow_unverified=True), "s")
    for text in ("I don tire. After wetin dem do my pikin I just wan end my life.", "I wan die"):
        r = await say(engine, None, text) if len(text.split()) > 3 else None
        if r is None:   # short message: greet first, then the message
            g = await say(engine, None, "hi")
            r = await say(engine, g.session_id, text)
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
    r = await say(engine, None, "I am a nurse, management tells us to collect deposits every night")
    assert r.state == "S2" and "danger right now" in r.replies[0]
    assert "MODEL TEXT" not in " ".join(r.replies) and r.replies[0].startswith("I am sorry this happened")
    r = await say(engine, r.session_id, "no, I am at home")
    text = "\n".join(r.replies)
    assert "Section 20" not in text and "112" not in text            # no emergency steps for someone at home
    assert "courage to speak up" in text and "work phone" in text    # staff wording
    assert "What happened to you" not in text and "receipts" not in text
    report = next(iter(store.reports.values()))
    assert report.reporter_role == "staff" and report.severity == "not_severe" and report.rights_shown == []

    r = await say(engine, None, "I am a nurse, a patient is dying in casualty now and they want deposit")
    r = await say(engine, r.session_id, "yes")
    assert "Section 20" in "\n".join(r.replies)                     # staff who say YES get the escalation


# ---------------------------------------------------------------- fail-safe: the AI is down

async def _broken(transcript, context=""):
    raise RuntimeError("openai is down")


async def _hangs(transcript, context=""):
    import asyncio
    await asyncio.sleep(30)


async def test_emergency_still_gets_escalation_when_the_ai_is_down(store):
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    r = await say(engine, None, "My mother is bleeding right now at Harmattan General Hospital, they refused to treat her, pay deposit")
    text = "\n".join(r.replies)
    assert "Section 20" in text and "112" in text and r.ref_code
    report = next(iter(store.reports.values()))
    assert report.credibility == "review"
    assert report.extra == {"review_reason": "ai_unavailable", "degraded_extraction": True}
    assert "AI service could not be reached" in report.summary_redacted


async def test_ai_down_never_skips_the_danger_question(store):
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    # The keyword fallback reads this as clearly past. Normally that skips the question. Not when degraded.
    r = await say(engine, None, "Last month a nurse insulted my wife at Harmattan General Hospital maternity")
    assert r.state == "S2" and "danger right now" in r.replies[0]
    r = await say(engine, r.session_id, "yes")
    assert "112" in "\n".join(r.replies)


async def test_ai_down_never_bounces_the_reporter_as_nonsense(store):
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    g = await say(engine, None, "hi")
    r = await say(engine, g.session_id, "help me abeg")
    assert "did not quite understand" not in " ".join(r.replies) and r.state == "S2"


async def test_slow_ai_times_out_into_the_same_fallback(store):
    engine = Engine(store, _hangs, Pack("ng-lagos", allow_unverified=True), "s", extract_timeout=0.05)
    r = await say(engine, None, "Nobody is attending to my father on the ward, no doctor anywhere at all")
    assert r.state == "S2"


async def test_self_harm_handoff_still_works_when_the_ai_is_down(store):
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    r = await say(engine, None, "After wetin dem do my pikin I just wan end my life")
    assert r.done and "trained to help" in r.replies[0] and store.reports == {}


async def test_degraded_reports_are_not_counted_until_an_analyst_accepts_them(store):
    from app import analyst as A
    engine = Engine(store, _broken, Pack("ng-lagos", allow_unverified=True), "s")
    for _ in range(6):
        r = await say(engine, None, "A nurse slapped me last week at Harmattan General Hospital maternity ward")
        await say(engine, r.session_id, "no")
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
    r = await say(engine, None, "A nurse slapped me and insulted me in front of everybody")
    r = await say(engine, r.session_id, "no")
    r = await say(engine, r.session_id, "Lagoon View General Hospital")
    assert [q.label for q in r.quick_replies][:3] == ["Emergency", "Maternity", "Children's ward"]
    before = calls
    r = await say(engine, r.session_id, "tap:maternity")
    assert [q.value for q in r.quick_replies] == ["tap:today", "tap:this_week", "tap:older"]
    r = await say(engine, r.session_id, "tap:older")
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


async def test_every_held_report_says_why(engine, store):
    await say(engine, None, "A nurse slapped me last week at Zebra Crossing Hospital maternity ward")
    for _ in range(2):
        await say(engine, None, "A nurse slapped me last week at Harmattan General Hospital maternity ward", dedupe_key="k")
    reasons = sorted(r.extra.get("review_reason", "") for r in store.reports.values())
    assert reasons == ["", "possible_duplicate", "unknown_hospital"]
    assert all((r.credibility == "review") == bool(r.extra.get("review_reason")) for r in store.reports.values())


# ---------------------------------------------------------------- the right help for the situation

async def test_each_kind_of_handoff_gets_the_right_service(store):
    from app.engine.models import Extraction

    def saying(kind):
        async def fn(transcript, context=""):
            return Extraction(category="other", safety_handoff=kind)
        return fn

    pack = Pack("ng-lagos", allow_unverified=True)
    out = {}
    for kind in ("self_harm", "sexual_violence", "other_violence"):
        r = await Engine(store, saying(kind), pack, "s").handle_message(None, "web", "something long enough to be a story")
        out[kind] = r.replies[0]
        assert r.done and "trained to help" in r.replies[0] and "not shared anything" in r.replies[0]
    assert "SURPIN" in out["self_harm"] and "Sexual Violence Agency" not in out["self_harm"]
    assert "Sexual Violence Agency" in out["sexual_violence"] and "Mirabel" in out["sexual_violence"]
    assert "SURPIN" not in out["sexual_violence"]
    assert store.reports == {}


async def test_a_bereaved_family_gets_different_words(store):
    from app.engine.models import Extraction

    async def body(transcript, context=""):
        return Extraction(category="detention", subtype="body_held", is_ongoing=True, category_confidence=0.9,
                          hospital_name_raw="Palm Grove Teaching Hospital", harm_outcome="death")

    r = await Engine(store, body, Pack("ng-lagos", allow_unverified=True), "s").handle_message(
        None, "web", "My father died and they will not release his body until we pay")
    text = "\n".join(r.replies)
    assert "sorry for your loss" in text and "mortuary charges" in text and "discharge" not in text


def test_emergency_message_no_longer_asserts_a_legal_conclusion_or_free_care():
    msg = Pack("ng-lagos", allow_unverified=True).message("A1.emergency_refused")
    assert "against the law" not in msg and "does not say the treatment is free" in msg
    assert "must not refuse a person emergency medical treatment for any reason" in msg
    assert "767 or 112" in msg and "N100,000" not in msg and "imprison" not in msg


# ---------------------------------------------------------------- an intention is not a report

async def test_saying_you_want_to_report_is_not_a_report(engine, store):
    r = await say(engine, None, "I would like to report an issue.")
    text = " ".join(r.replies)
    assert "sorry this happened" not in text and "danger right now? " not in text   # nothing happened yet
    assert "Tell me what happened" in text and r.state == "S1"
    assert [q.value for q in r.quick_replies] == ["tap:danger"]                     # danger is one tap away
    assert store.reports == {}

    r = await say(engine, r.session_id, "A nurse slapped me last week at Harmattan General Hospital maternity ward")
    assert r.ref_code and len(store.reports) == 1                                   # now there is something to record


async def test_never_stores_a_report_with_nothing_in_it(engine, store):
    r = await say(engine, None, "I would like to report an issue.")
    r = await say(engine, r.session_id, "I want to make a complaint please")
    assert r.state == "S1" and store.reports == {}
    r = await say(engine, r.session_id, "can you help me with something")
    assert r.done and store.reports == {}                                           # politely ends; nothing stored


async def test_danger_button_gives_help_first_and_records_only_once_there_is_a_story(engine, store):
    r = await say(engine, None, "I would like to report an issue.")
    r = await say(engine, r.session_id, "tap:danger")
    text = "\n".join(r.replies)
    assert "767 or 112" in text and "tell me in a few words" in text
    assert r.state == "S1" and store.reports == {} and r.quick_replies == []

    r = await say(engine, r.session_id, "Nobody is attending to my father on the ward at Iroko District Hospital, no doctor anywhere")
    text = "\n".join(r.replies)
    assert text.count("767 or 112") == 0                                            # not repeated: they already have it
    assert "danger right now" not in text and r.ref_code                            # and not asked again
    report = next(iter(store.reports.values()))
    assert report.severity == "severe" and report.escalation_shown and report.category == "neglect"


async def test_the_receipt_only_says_counted_when_it_is(engine, store):
    r = await say(engine, None, "A nurse slapped me last week at London ABC Hospital maternity ward")
    text = "\n".join(r.replies)
    assert "has been counted" not in text and "did not recognise that hospital" in text
    assert next(iter(store.reports.values())).credibility == "review"

    story = "A nurse slapped me last week at Harmattan General Hospital maternity ward"
    first = await say(engine, None, story, dedupe_key="same")
    second = await say(engine, None, story, dedupe_key="same")
    assert "has been counted" in "\n".join(first.replies)
    second_text = "\n".join(second.replies)
    assert "has been counted" not in second_text and "will review your report" in second_text
    assert "duplicate" not in second_text.lower()                                   # do not teach a spammer what tripped


async def test_typing_yes_after_being_offered_the_danger_button_works_like_tapping_it(engine, store):
    r = await say(engine, None, "I would like to report an issue.")
    r = await say(engine, r.session_id, "Yes")
    assert "767 or 112" in "\n".join(r.replies) and "did not quite understand" not in " ".join(r.replies)
    assert store.reports == {}


async def test_the_reporter_can_read_the_source_for_themselves(engine, store):
    r = await say(engine, None, "A nurse slapped me last week at Harmattan General Hospital maternity ward")
    text = "\n".join(r.replies)
    assert "fccpc.gov.ng" in text and text.index("respect and dignity") < text.index("fccpc.gov.ng")


EMERGENCY = ("My brother is bleeding badly now at Harmattan General Hospital and they refuse "
             "to treat him until we pay deposit")


async def test_refused_emergency_gets_the_law_to_show_them_after_the_steps_never_before(engine, store):
    r = await say(engine, None, EMERGENCY)
    law = next(i for i, t in enumerate(r.replies) if "If it helps to show them" in t)
    steps = next(i for i, t in enumerate(r.replies) if "Get care first" in t)
    assert law == steps + 1                                        # what to do comes first, always
    assert "page 17 of the file" in r.replies[law] and r.replies[law].endswith("nig162642.pdf")
    assert sum("http" in t for t in r.replies) == 1                # one link, nothing else to read


async def test_the_law_link_comes_before_the_hospital_question_so_the_question_stays_last(engine, store):
    r = await say(engine, None, "My brother is bleeding badly right now and they refuse to treat him until we pay deposit")
    assert r.state == "A2" and "http" not in r.replies[-1]
    assert any("If it helps to show them" in t for t in r.replies[:-1])


async def test_other_emergencies_get_no_link_and_an_unsigned_pack_sends_none(store):
    engine = Engine(store, mock_extract, Pack("ng-lagos", allow_unverified=True), "s")
    r = await say(engine, None, "They are holding my wife right now at Harmattan General Hospital because of the bill, "
                                "she cannot leave")
    assert "http" not in "\n".join(r.replies)
    engine = Engine(MemoryStore(), mock_extract, unsigned("ng-lagos"), "s")
    assert "http" not in "\n".join((await say(engine, None, EMERGENCY)).replies)


async def test_an_unclear_optin_answer_is_asked_again_once_and_never_recorded_as_no(engine, store):
    r = await say(engine, None, "A nurse slapped me last week at Harmattan General Hospital maternity ward")
    assert r.state == "B5"
    r = await say(engine, r.session_id, "hmm what do you mean")
    assert r.state == "B5" and "check in tomorrow" in r.replies[-1]        # asked again, buttons and all
    assert [q.value for q in r.quick_replies] == ["yes", "no"]
    r = await say(engine, r.session_id, "yes")
    assert r.done and next(iter(store.reports.values())).followup_opt_in is True


async def test_a_second_unclear_optin_answer_ends_without_opting_in(engine, store):
    r = await say(engine, None, "A nurse slapped me last week at Harmattan General Hospital maternity ward")
    r = await say(engine, r.session_id, "hmm")
    r = await say(engine, r.session_id, "hmm")
    assert r.done and "No problem" in r.replies[-1]
    assert next(iter(store.reports.values())).followup_opt_in is False


BURST = ("Also they refused to treat my wife until we paid 50 thousand, she is bleeding on the floor "
         "right now, her name is Ngozi Eze")


def _dump(store):
    import json
    return json.dumps([r.model_dump(mode="json") for r in store.reports.values()])


async def test_more_story_sent_at_the_hospital_question_is_classified_and_never_stored(engine, store):
    r = await say(engine, None, "A nurse insulted me in front of everybody")
    r = await say(engine, r.session_id, "no")
    assert r.state == "B1" and "Which hospital" in r.replies[-1]
    r = await say(engine, r.session_id, BURST)
    assert "112" in "\n".join(r.replies)                        # the emergency was seen, steps were shown
    assert "Which hospital" in r.replies[-1]                    # and the question is asked again
    r = await say(engine, r.session_id, "Harmattan General Hospital")
    report = next(iter(store.reports.values()))
    assert report.category == "emergency_refused" and report.severity == "severe"
    assert report.hospital_id and report.hospital_name_raw is None
    assert "Ngozi" not in _dump(store) and "bleeding on the floor" not in _dump(store)


async def test_more_story_sent_at_the_danger_check_is_read_as_story_not_as_an_unclear_answer(engine, store):
    r = await say(engine, None, "A nurse insulted me in front of everybody")
    assert r.state == "S2"
    r = await say(engine, r.session_id, BURST)
    assert "112" in "\n".join(r.replies) and "Section 20" in "\n".join(r.replies)
    assert "Which hospital" in r.replies[-1]


async def test_a_long_danger_answer_that_starts_with_no_is_still_an_answer(engine):
    r = await say(engine, None, "A nurse insulted me in front of everybody")
    r = await say(engine, r.session_id, "No, nobody is in danger right now, this thing happened to me last week")
    assert r.state == "B1" and "Which hospital" in r.replies[-1]


async def test_more_story_in_the_emergency_branch_does_not_repeat_the_steps_or_store_the_text(engine, store):
    r = await say(engine, None, "My mother is bleeding right now and they refused to treat her until we pay deposit")
    assert r.state == "A2" and "112" in "\n".join(r.replies)
    r = await say(engine, r.session_id, "The doctor on duty walked past us three times and the cashier "
                                        "said no deposit no treatment, my name is Ngozi Eze")
    assert r.state == "A2" and "112" not in "\n".join(r.replies) and "Which hospital" in r.replies[-1]
    r = await say(engine, r.session_id, "Harmattan General Hospital")
    assert next(iter(store.reports.values())).severity == "severe" and "Ngozi" not in _dump(store)


async def test_a_short_unknown_hospital_name_is_still_kept_for_review(engine, store):
    r = await say(engine, None, "A nurse insulted me in front of everybody last week at the maternity ward")
    assert "Which hospital" in r.replies[-1]
    r = await say(engine, r.session_id, "Saint Nowhere Clinic")
    for _ in range(3):
        if store.reports:
            break
        r = await say(engine, r.session_id, "last week")
    assert next(iter(store.reports.values())).hospital_name_raw == "Saint Nowhere Clinic"


# ---------------------------------------------------------------- "have you finished?"

FIRST = "A nurse insulted me in front of everybody last week at Harmattan General Hospital maternity ward"


async def test_nothing_is_recorded_until_the_person_says_they_have_finished(engine, store):
    r = await tell(engine, None, FIRST)
    assert r.state == "M1" and not r.ref_code and store.reports == {}
    assert "anything else" in r.replies[-1].lower() and [q.value for q in r.quick_replies] == ["tap:done"]
    assert "recorded" not in "\n".join(r.replies[:-1]).lower()            # no receipt, no rights yet
    r = await tell(engine, r.session_id, "tap:done")
    assert r.state == "B5" and r.ref_code and len(store.reports) == 1
    text = "\n".join(r.replies)
    assert "dignity" in text and "Your report is recorded" in text       # help and receipt come now


async def test_they_can_add_as_many_messages_as_they_like_before_finishing(engine, store):
    r = await tell(engine, None, FIRST)
    r = await tell(engine, r.session_id, "She also slapped my sister")
    assert r.state == "M1" and "added" in r.replies[-1] and store.reports == {}
    r = await tell(engine, r.session_id, "And she pushed her against the wall")
    assert r.state == "M1" and store.reports == {}
    r = await tell(engine, r.session_id, "done")
    assert r.ref_code and len(store.reports) == 1
    report = next(iter(store.reports.values()))
    assert report.hospital_id and report.department == "maternity"      # what they already told us is kept


async def test_typed_ways_of_saying_finished(engine, store):
    for word in ("DONE", "that is all", "No", "nothing else", "I don finish"):
        r = await tell(engine, None, FIRST)
        r = await tell(engine, r.session_id, word)
        assert r.ref_code, word


async def test_a_long_message_starting_with_no_is_more_story_not_finished(engine, store):
    r = await tell(engine, None, FIRST)
    r = await tell(engine, r.session_id, "No one came to help us and the matron just stood there watching it all")
    assert r.state == "M1" and store.reports == {}


async def test_an_emergency_revealed_while_adding_detail_gets_the_steps_at_once(engine, store):
    r = await tell(engine, None, "A nurse insulted me in front of everybody at Harmattan General Hospital maternity")
    r = await tell(engine, r.session_id, "no")
    while r.state == "B1":
        r = await tell(engine, r.session_id, "tap:today")
    assert r.state == "M1"
    r = await tell(engine, r.session_id, BURST)
    text = "\n".join(r.replies)
    assert "112" in text and "Section 20" in text and r.state == "M1" and store.reports == {}
    r = await tell(engine, r.session_id, "tap:done")
    report = next(iter(store.reports.values()))
    assert report.category == "emergency_refused" and report.severity == "severe"
    assert "Ngozi" not in _dump(store)


async def test_the_emergency_branch_also_waits_for_finished_but_never_delays_the_steps(engine, store):
    r = await tell(engine, None, "My mother is bleeding right now at Harmattan General Hospital emergency and "
                                "they refused to treat her until we pay deposit")
    assert "112" in "\n".join(r.replies) and r.state == "M1" and store.reports == {}
    r = await tell(engine, r.session_id, "tap:done")
    assert r.ref_code and next(iter(store.reports.values())).severity == "severe"


async def test_a_crisis_disclosed_while_adding_detail_is_handed_off_and_nothing_is_stored(engine, store):
    r = await tell(engine, None, FIRST)
    r = await tell(engine, r.session_id, "I am so tired of everything, I want to die")
    assert r.done and store.reports == {}


async def test_until_the_wording_is_signed_off_the_step_is_skipped_not_replaced_by_the_fallback(store):
    engine = Engine(store, mock_extract, unsigned("ng-lagos", False), ref_secret="test-secret")
    r = await say(engine, None, FIRST, finish=False)
    assert r.state == "B5" and r.ref_code and len(store.reports) == 1


# ------------------------------------------- emergencies are recorded if the person goes quiet

EMERGENCY = ("My mother is bleeding right now at Harmattan General Hospital emergency and they refused "
             "to treat her until we pay deposit")


def _quick_engine(store, after=0.0):
    return Engine(store, mock_extract, Pack("ng-lagos", allow_unverified=True), "s", auto_record_after=after)


async def test_an_emergency_is_recorded_by_itself_when_the_person_goes_quiet(store):
    engine = _quick_engine(store)
    r = await tell(engine, None, EMERGENCY)
    assert r.state == "M1" and r.auto_record_after == 0.0 and store.reports == {}
    auto = await engine.auto_record(r.session_id)
    assert auto.ref_code and auto.state == "B5" and "Your report is recorded" in "\n".join(auto.replies)
    assert [q.value for q in auto.quick_replies] == ["yes", "no"]          # the rest of the flow carries on
    assert next(iter(store.reports.values())).severity == "severe"
    assert await engine.auto_record(r.session_id) is None                  # once only


async def test_only_emergencies_are_recorded_without_being_told(store):
    engine = _quick_engine(store)
    r = await tell(engine, None, FIRST)
    assert r.state == "M1" and r.auto_record_after is None
    assert await engine.auto_record(r.session_id) is None and store.reports == {}


async def test_the_wait_starts_again_whenever_they_add_something(store):
    engine = _quick_engine(store, after=60)
    r = await tell(engine, None, EMERGENCY)
    assert await engine.auto_record(r.session_id) is None and store.reports == {}   # not quiet for long enough
    assert await engine.auto_record("no-such-session") is None


async def test_someone_in_an_emergency_is_told_up_front_that_they_can_go(store):
    engine = _quick_engine(store, after=120)
    r = await tell(engine, None, EMERGENCY)
    assert "If you need to go, go" in r.replies[-1] and "two minutes" in r.replies[-1]
    assert "only recorded when you tell me" not in r.replies[-1]          # that would not be true for them
    r = await tell(engine, None, FIRST)
    assert "only recorded when you tell me" in r.replies[-1] and "two minutes" not in r.replies[-1]


async def test_the_emergency_prompt_falls_back_to_the_plain_one_until_it_is_signed_off(store):
    pack = Pack("ng-lagos", allow_unverified=False)
    pack.messages["M1.more.severe"]["verified"] = False
    engine = Engine(store, mock_extract, pack, "s")
    r = await tell(engine, None, EMERGENCY)
    assert r.state == "M1" and "only recorded when you tell me" in r.replies[-1]
