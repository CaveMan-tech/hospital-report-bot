import pytest

from app.engine.packs import Pack, UnverifiedContent
from tests.helpers import unsigned


def test_unverified_message_is_blocked_and_falls_back():
    pack = unsigned("ng-lagos")
    assert pack.messages["A1.emergency_refused"]["verified"] is False
    out = pack.message("A1.emergency_refused", "en")
    assert "Section 20" not in out
    assert out == pack.message("E.unverified_fallback", "en")


def test_unverified_raises_internally():
    pack = unsigned("ng-lagos")
    with pytest.raises(UnverifiedContent):
        pack._message("A1.generic", "en")


def test_unverified_rights_are_not_shown():
    pack = unsigned("ng-lagos")
    assert pack.rights_for("abuse", "en") == []


def test_dev_mode_allows_unverified():
    pack = Pack("ng-lagos", allow_unverified=True)
    assert "Section 20" in pack.message("A1.emergency_refused", "en")
    assert pack.rights_for("abuse", "en")[0][0] == "dignity"


def test_pidgin_falls_back_to_english_when_missing():
    pack = Pack("ng-lagos")
    assert pack.message("B3.abuse", "pcm") == pack.message("B3.abuse", "en")


def test_every_message_with_law_or_numbers_is_gated():
    """Anything that mentions a law, a phone number or a contact must start unverified."""
    import re
    pack = Pack("ng-lagos")
    for key, entry in pack.messages.items():
        if re.search(r"Section \d+|\b\d{3}\b|\{contact:|Council", entry["en"]):
            assert "verified" in entry, key


def test_hospital_matching():
    pack = Pack("ng-lagos")
    assert pack.match_hospital("harmattan general").id == "h-harmattan"
    assert pack.match_hospital("Lagoon Veiw General Hospital").id == "h-lagoonview"
    assert pack.match_hospital("Some Unknown Clinic") is None
    assert pack.match_hospital(None) is None


def test_message_or_none_skips_unverified_instead_of_sending_the_fallback():
    for pack_id in ("ng-lagos", "ke-nairobi"):
        pack = unsigned(pack_id)
        for key in ("S0.privacy.telegram", "T.forgotten", "T.status_usage"):
            assert pack.message_or_none(key, "en") is None
            assert pack.message(key, "en") == pack.message("E.unverified_fallback", "en")   # why it exists


def test_message_or_none_returns_verified_text_and_honours_dev_mode():
    assert "safe place" in Pack("ng-lagos").message_or_none("S0.greeting", "en")
    assert "/forget" in Pack("ng-lagos", allow_unverified=True).message_or_none("S0.privacy.telegram", "en")


def test_message_or_none_still_checks_nested_contacts():
    pack = Pack("ng-lagos", allow_unverified=False)
    pack.messages["X.test"] = {"verified": True, "en": "Call {contact:emergency}"}
    pack.contacts["emergency"] = {**pack.contacts["emergency"], "verified": False}
    assert pack.message_or_none("X.test", "en") is None


def test_content_review_rows_say_what_a_reporter_gets_today():
    pack = unsigned("ng-lagos", allow_unverified=True)      # dev mode must not change the answer
    rows = {(r["file"], r["id"]): r["now"] for r in pack.gated_entries()}
    fallback = pack.messages["E.unverified_fallback"]["en"]
    assert rows[("messages", "A1.emergency_refused")]["kind"] == "fallback"
    assert rows[("messages", "A1.emergency_refused")]["text"] == fallback
    assert rows[("rights", "dignity")] == {"kind": "omitted"}
    emergency = rows[("contacts", "emergency")]
    assert emergency["kind"] == "fallback" and "E.handoff" in emergency["used_in"]
    assert rows[("asks", "abuse")]["kind"] == "brief_placeholder"


def test_a_verified_message_is_still_held_back_by_an_unverified_contact():
    pack = unsigned("ng-lagos")
    signed = {"verified": True, "verified_by": "A", "verified_on": "2026-09-20", "verified_source": "x"}
    pack.messages["E.handoff"] = {**pack.messages["E.handoff"], **signed}
    now = {r["id"]: r["now"] for r in pack.gated_entries() if r["file"] == "messages"}["E.handoff"]
    assert now["kind"] == "fallback" and now["blocked_by"] == ["dsva", "emergency"]
    for cid in ("dsva", "emergency"):
        pack.contacts[cid] = {**pack.contacts[cid], **signed}
    now = {r["id"]: r["now"] for r in pack.gated_entries() if r["file"] == "messages"}["E.handoff"]
    assert now == {"kind": "as_written"}


SIGNED = {"verified": True, "verified_by": "A", "verified_on": "2026-09-20", "verified_source": "checked x"}


def test_a_reference_is_only_offered_once_a_human_has_checked_the_link():
    pack = unsigned("ng-lagos")
    assert pack.references_for("dignity", "en") == []                    # unverified: nothing is sent
    ref = next(r for r in pack.references if r["id"] == "pbor_guide")
    ref.update(SIGNED)
    pack.messages["B2.reference"]["verified"] = True
    (line,) = pack.references_for("dignity", "en")
    assert ref["url"] in line and line.endswith(ref["url"])              # the link is last, so it stays tappable
    assert "not a law" in line and "MB" in line                          # says what it is and what it costs to open
    assert pack.references_for("emergency", "en") == []                  # a different document, still unchecked


def test_every_right_names_a_reference_that_exists_and_every_reference_is_https():
    for pack_id in ("ng-lagos", "ke-nairobi"):
        pack = Pack(pack_id)
        ids = {r["id"] for r in pack.references}
        for right in pack.rights:
            assert set(right.get("references", [])) <= ids, (pack_id, right["id"])
        for ref in pack.references:
            assert ref["url"].startswith("https://"), ref["id"]
        assert any(r["file"] == "references" for r in pack.gated_entries())
