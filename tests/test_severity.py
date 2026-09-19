from app.engine.models import Extraction
from app.engine.severity import decide


def ex(**kw) -> Extraction:
    return Extraction(**kw)


def test_user_yes_always_wins():
    assert decide(ex(category="abuse", is_ongoing=False, incident_timing="older"), danger_answer=True) == "severe"


def test_emergency_refused_is_severe_unless_clearly_over():
    assert decide(ex(category="emergency_refused", is_ongoing=True)) == "severe"
    assert decide(ex(category="emergency_refused", is_ongoing=None)) == "severe"
    assert decide(ex(category="emergency_refused", is_ongoing=False, incident_timing="older")) == "not_severe"


def test_detention_ongoing_is_severe():
    assert decide(ex(category="detention", is_ongoing=None)) == "severe"


def test_neglect_needs_ongoing_and_critical():
    assert decide(ex(category="neglect", is_ongoing=True, critical_condition=True)) == "severe"
    assert decide(ex(category="neglect", is_ongoing=True, critical_condition=False)) == "ask"


def test_uncertain_always_asks_never_guesses():
    assert decide(ex(category="abuse", severity="uncertain")) == "ask"
    assert decide(ex(category="other", severity="not_severe", incident_timing="today")) == "ask"


def test_ai_severe_alone_is_not_trusted_it_asks():
    assert decide(ex(category="abuse", severity="severe")) == "ask"


def test_clearly_past_skips_the_check():
    assert decide(ex(category="abuse", is_ongoing=False, incident_timing="this_month")) == "not_severe"


def test_user_no_means_not_severe_for_soft_categories():
    assert decide(ex(category="neglect", is_ongoing=True), danger_answer=False) == "not_severe"


def test_staff_whistleblower_is_asked_not_assumed():
    e = ex(category="emergency_refused", is_ongoing=True, reporter_role="staff")
    assert decide(e) == "ask"
    assert decide(e, danger_answer=True) == "severe"
    assert decide(e, danger_answer=False) == "not_severe"   # they said nobody is in danger: believe them
    # "people have died waiting" trips the critical flag; staff are still asked, not assumed
    assert decide(ex(category="emergency_refused", is_ongoing=True, reporter_role="staff",
                     critical_condition=True)) == "ask"
