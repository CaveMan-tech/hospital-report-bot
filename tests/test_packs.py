import pytest

from app.engine.packs import Pack, UnverifiedContent


def test_unverified_message_is_blocked_and_falls_back():
    pack = Pack("ng-lagos", allow_unverified=False)
    assert pack.messages["A1.emergency_refused"]["verified"] is False
    out = pack.message("A1.emergency_refused", "en")
    assert "Section 20" not in out
    assert out == pack.message("E.unverified_fallback", "en")


def test_unverified_raises_internally():
    pack = Pack("ng-lagos", allow_unverified=False)
    with pytest.raises(UnverifiedContent):
        pack._message("A1.generic", "en")


def test_unverified_rights_are_not_shown():
    pack = Pack("ng-lagos", allow_unverified=False)
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
