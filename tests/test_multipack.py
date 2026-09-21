"""Scaling across geographies: a new country is a new folder, not new code."""

import json
import os
import re
from pathlib import Path

import pytest

os.environ.update(EXTRACT_MODE="mock", STORE="memory", ALLOW_UNVERIFIED="true", DEMO_MODE="true",
                  ANALYST_PASSWORD="pw")

from fastapi.testclient import TestClient

from app import analyst as A
from app.engine.extract import mock_extract
from app.engine.machine import Engine
from app.engine.packs import PACKS_DIR, Pack
from app.main import app
from app.seed import build
from app.store.memory import MemoryStore
from tests.helpers import say

PACK_IDS = sorted(p.name for p in PACKS_DIR.iterdir() if p.is_dir())
AUTH = ("a", "pw")
KE_STORY = ("We are at Mugumo Ridge County Referral Hospital casualty right now, my brother is bleeding "
            "and they refused to treat him until we pay a cash deposit")


def test_both_packs_exist():
    assert {"ng-lagos", "ke-nairobi"} <= set(PACK_IDS)


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_every_pack_has_the_same_message_keys_and_five_hospitals(pack_id):
    reference = set(Pack("ng-lagos").messages)
    pack = Pack(pack_id)
    assert set(pack.messages) == reference
    assert len(pack.hospitals) >= 5 and set(pack.asks) >= {"emergency_refused", "detention", "abuse", "neglect"}
    for lang in pack.languages:                    # default language must always have text
        assert all(m.get("en") for m in pack.messages.values()), lang
    assert set(pack.meta["amount_buckets"]) == {"small", "medium", "large", "very_large"}
    assert set(pack.labels["quick"]) == {"yes", "no", "followup", "when", "department", "danger", "done"} and set(pack.labels["quick"]["followup"]) == {"1", "2", "3", "4"}


RISKY = re.compile(r"[Ss]ection \d|Article \d|Constitution|\b\d{3,4}\b|\{contact:|Council|Act 20|High Court")


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_anything_with_law_numbers_or_contacts_is_gated(pack_id):
    """A message that mentions a law, a phone number, a contact or a regulator must be gated,
    so it can never be sent on a bare `"verified": true`."""
    for key, entry in Pack(pack_id).messages.items():
        texts = " ".join(str(v) for k, v in entry.items() if k in ("en", "pcm") and v)
        if RISKY.search(texts):
            assert entry.get("gated"), f"{pack_id}:{key} has legal/contact content but is not gated"


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_verified_gated_content_always_says_who_when_and_against_what(pack_id):
    """To verify an entry use:  uv run python -m app.verify mark <pack> <file> <id> --by ... --source ...
    Flipping the flag by hand without provenance does NOT count, and this test says so."""
    for row in Pack(pack_id).gated_entries():
        assert not row["claimed_without_provenance"], (
            f"{pack_id}/{row['file']}/{row['id']} says verified but has no verified_by / verified_on / "
            "verified_source. Use `python -m app.verify mark` so the sign-off is recorded.")
        if row["verified"]:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["verified_on"])


def test_a_bare_verified_flag_does_not_unlock_gated_content(tmp_path, monkeypatch):
    import shutil

    from app.engine import packs as P
    shutil.copytree(P.PACKS_DIR / "ng-lagos", tmp_path / "ng-lagos")
    monkeypatch.setattr(P, "PACKS_DIR", tmp_path)
    path = tmp_path / "ng-lagos" / "messages.json"
    cpath = tmp_path / "ng-lagos" / "contacts.json"
    data, contacts = json.loads(path.read_text()), json.loads(cpath.read_text())
    # Whatever has been signed off in packs/, this copy starts from no sign-off at all.
    for entry in (data["A1.emergency_refused"], *contacts):
        entry["verified"] = False
        for field in ("verified_by", "verified_on", "verified_source"):
            entry.pop(field, None)
    cpath.write_text(json.dumps(contacts))

    data["A1.emergency_refused"]["verified"] = True                      # flag flipped by hand
    path.write_text(json.dumps(data))
    assert "Section 20" not in P.Pack("ng-lagos").message("A1.emergency_refused")

    sign_off = {"verified": True, "verified_by": "A. Lawyer", "verified_on": "2026-09-20"}
    data["A1.emergency_refused"].update(sign_off, verified_source="National Health Act 2014 s.20, official gazette")
    path.write_text(json.dumps(data))
    # Still blocked: the message embeds the emergency numbers, and those need their own sign-off.
    assert "Section 20" not in P.Pack("ng-lagos").message("A1.emergency_refused")

    next(c for c in contacts if c["id"] == "emergency").update(sign_off, verified_source="Ministry page; test-called both")
    cpath.write_text(json.dumps(contacts))
    msg = P.Pack("ng-lagos").message("A1.emergency_refused")
    assert "Section 20" in msg and "767 or 112" in msg
    assert "safe place" in P.Pack("ng-lagos").message("S0.greeting")      # plain copy needs no provenance


def test_verify_command_records_provenance_and_can_be_undone(tmp_path, monkeypatch):
    import shutil
    import sys

    from app import verify as V
    from app.engine import packs as P
    shutil.copytree(P.PACKS_DIR / "ke-nairobi", tmp_path / "ke-nairobi")
    monkeypatch.setattr(P, "PACKS_DIR", tmp_path)
    monkeypatch.setattr(V, "PACKS_DIR", tmp_path)

    def run(*argv):
        monkeypatch.setattr(sys, "argv", ["verify", *argv])
        V.main()

    run("mark", "ke-nairobi", "rights", "dignity", "--by", "W. Advocate", "--source", "Health Act 2017 s.5(2), kenyalaw.org")
    row = next(r for r in P.Pack("ke-nairobi").gated_entries() if r["id"] == "dignity")
    assert row["verified"] and row["verified_by"] == "W. Advocate" and row["verified_on"]
    assert P.Pack("ke-nairobi").rights_for("abuse", "en")[0][0] == "dignity"
    run("unmark", "ke-nairobi", "rights", "dignity")
    assert P.Pack("ke-nairobi").rights_for("abuse", "en") == []
    with pytest.raises(SystemExit):                                       # plain copy cannot be "verified"
        run("mark", "ke-nairobi", "messages", "S0.greeting", "--by", "X", "--source", "anything at all")
    with pytest.raises(SystemExit):                                       # a source is mandatory
        run("mark", "ke-nairobi", "rights", "dignity", "--by", "X", "--source", "n/a")


def test_no_country_specific_strings_in_code():
    code = "\n".join(p.read_text() for p in Path("app").rglob("*.py") if p.name not in {"extract.py", "seed.py"})
    for needle in ("National Health Act", "Section 20", "767", "Lagos", "Nairobi", "naira", "KSh"):
        assert needle not in code, needle


def engine(store, allow=True):
    return Engine(store, mock_extract, [Pack("ng-lagos", allow), Pack("ke-nairobi", allow)], "secret")


async def test_kenya_conversation_gets_kenyan_law_and_never_nigerian():
    store = MemoryStore()
    r = await say(engine(store), None, KE_STORY, pack_id="ke-nairobi")
    text = "\n".join(r.replies)
    assert "Article 43(2)" in text and "Health Act 2017" in text and "922" in text
    assert "National Health Act" not in text and "767" not in text and "Section 20" not in text
    assert "Open Ward Kenya" in text
    report = next(iter(store.reports.values()))
    assert report.pack == "ke-nairobi" and report.hospital_id == "h-mugumo-ridge" and report.severity == "severe"


async def test_default_pack_is_unchanged_and_unknown_pack_falls_back():
    store = MemoryStore()
    story = "My mother is bleeding right now at Harmattan General Hospital, refused to treat, pay deposit"
    for pid in (None, "zz-nowhere"):
        r = await say(engine(store), None, story, pack_id=pid)
        assert "Section 20" in "\n".join(r.replies)
    assert {x.pack for x in store.reports.values()} == {"ng-lagos"}


async def test_pack_is_fixed_for_the_life_of_a_conversation():
    store = MemoryStore()
    e = engine(store)
    r = await e.handle_message(None, "web", "hi", pack_id="ke-nairobi")
    r = await e.handle_message(r.session_id, "web", KE_STORY, pack_id="ng-lagos")   # ignored mid-conversation
    assert "Article 43(2)" in "\n".join(r.replies)


async def test_pidgin_is_not_assumed_outside_nigeria():
    store = MemoryStore()
    r = await engine(store).handle_message(
        None, "web", "Nurse dey shout for my pikin for ward, wetin be this wahala, dem no send us", pack_id="ke-nairobi")
    assert "Anybody dey for danger" not in r.replies[0] and "danger right now" in r.replies[0]


async def test_kenya_gate_blocks_unverified_law_in_production_mode():
    store = MemoryStore()
    r = await engine(store, allow=False).handle_message(None, "web", KE_STORY, pack_id="ke-nairobi")
    text = "\n".join(r.replies)
    assert "Article 43" not in text and "922" not in text and "still being checked" in text


async def test_followup_and_lookup_use_the_reports_own_pack():
    store = MemoryStore()
    e = engine(store)
    r = await say(e, None, "A nurse insulted my wife last week at Twiga Hill Sub-County Hospital maternity",
                  pack_id="ke-nairobi")
    assert "Twiga Hill Sub-County Hospital" in await e.lookup(r.ref_code)
    f = await e.start_followup(r.ref_code)
    assert "Twiga Hill" in f.replies[0] and (await store.get_session(f.session_id)).pack == "ke-nairobi"


def test_patterns_never_mix_countries():
    ng, _ = build(Pack("ng-lagos"))
    ke, _ = build(Pack("ke-nairobi"))
    rows = A.patterns(ng + ke, Pack("ke-nairobi"))
    assert rows and all(r["hospital_id"].startswith("h-") and "Harmattan" not in r["hospital"] for r in rows)
    assert {r["hospital"] for r in rows} <= {h.name for h in Pack("ke-nairobi").hospitals}
    brief = A.brief(rows[0], Pack("ke-nairobi", allow_unverified=True))
    assert "Open Ward Kenya" in brief and "National Health Act" not in brief


def test_pack_switch_over_http():
    with TestClient(app) as c:
        page = c.get("/?pack=ke-nairobi").text
        assert 'window.PACK = "ke-nairobi"' in page and "Open Ward Kenya" in page and "<details>" in page and "Switch to Nigeria (Lagos)" in page
        r = c.post("/api/chat", json={"text": KE_STORY, "pack": "ke-nairobi"}).json()
        assert "Article 43(2)" in "\n".join(r["replies"])
        ke = c.get("/analyst?pack=ke-nairobi", auth=AUTH).text
        assert "Mugumo Ridge" in ke and "Harmattan" not in ke and "Kenya (Nairobi)" in ke
        ng = c.get("/analyst", auth=AUTH).text
        assert "Harmattan" in ng and "Mugumo" not in ng
        assert c.get("/analyst/pattern/h-mugumo-ridge/emergency_refused", auth=AUTH).status_code == 200
        assert "Mugumo Ridge" in c.get("/analyst/patterns.csv?pack=ke-nairobi", auth=AUTH).text
        total = sum(len(c.get(p).content) for p in ("/?pack=ke-nairobi", "/static/app.css", "/static/chat.js"))
        assert total < 10_000


def test_switching_pack_on_the_web_page_starts_a_fresh_conversation():
    """The page keeps the conversation in sessionStorage, which survives navigation in the tab.
    Without this, opening /?pack=ke-nairobi mid-conversation carried on in Nigerian content."""
    with TestClient(app) as c:
        js = c.get("/static/chat.js").text
        assert "S.get('pack') !== window.PACK" in js and "S.set('sid', null)" in js
