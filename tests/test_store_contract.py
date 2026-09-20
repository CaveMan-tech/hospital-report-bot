"""The same behaviour is required of every Store implementation.

The Postgres half runs when TEST_DATABASE_URL is set, e.g.
    TEST_DATABASE_URL=postgresql://localhost/hospital_bot_test uv run pytest
"""

import os
from datetime import UTC, datetime, timedelta

import pytest

from app.engine.extract import mock_extract
from app.engine.machine import Engine
from app.engine.models import AuditEntry, Followup, Report, Session
from app.engine.packs import Pack
from app.store.memory import MemoryStore
from tests.helpers import say

PG = os.environ.get("TEST_DATABASE_URL")
STORES = ["memory", pytest.param("postgres", marks=pytest.mark.skipif(not PG, reason="TEST_DATABASE_URL not set"))]


@pytest.fixture(params=STORES)
async def store(request):
    if request.param == "memory":
        yield MemoryStore()
        return
    from app.store.postgres import PostgresStore

    s = await PostgresStore.connect(PG)
    await s.pool.execute("truncate analyst_actions, followups, sessions, reports cascade")
    yield s
    await s.close()


def a_report(**kw) -> Report:
    base = {"ref_code_hmac": os.urandom(8).hex(), "category": "abuse", "severity": "not_severe",
            "hospital_id": "h-harmattan", "subtype": "verbal", "secondary_categories": ["neglect"],
            "rights_shown": ["dignity"], "extra": {"note": "x"}, "summary_redacted": "A summary."}
    return Report(**{**base, **kw})


async def test_report_roundtrip_preserves_every_field(store):
    r = a_report(money_demanded=True, is_ongoing=None,
                 followup_due_at=datetime.now(UTC).replace(microsecond=0) + timedelta(days=1))
    await store.create_report(r)
    assert await store.get_report(r.id) == r
    assert await store.get_report_by_ref(r.ref_code_hmac) == r
    assert await store.get_report_by_ref("nope") is None


async def test_save_report_updates_in_place(store):
    r = a_report()
    await store.create_report(r)
    r.status, r.credibility, r.followup_opt_in = "unchanged", "excluded", True
    await store.save_report(r)
    got = await store.get_report(r.id)
    assert (got.status, got.credibility, got.followup_opt_in) == ("unchanged", "excluded", True)
    assert len(await store.list_reports()) == 1


async def test_session_roundtrip_and_context_json(store):
    s = Session(context={"lang": "pcm", "transcript": [{"role": "user", "text": "wetin dey"}], "asked": ["hospital"]})
    await store.create_session(s)
    got = await store.get_session(s.id)
    assert got.context == s.context and got.state == "S1"
    got.state, got.context = "B5", {"lang": "pcm"}
    await store.save_session(got)
    assert (await store.get_session(s.id)).context == {"lang": "pcm"}


async def test_junk_ids_return_none_not_errors(store):
    assert await store.get_session("not-a-uuid") is None
    assert await store.get_report("not-a-uuid") is None
    assert await store.get_session("00000000-0000-0000-0000-000000000000") is None


async def test_expired_sessions_are_purged(store):
    old = Session(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    live = Session()
    await store.create_session(old)
    await store.create_session(live)
    assert await store.purge_expired_sessions() == 1
    assert await store.get_session(old.id) is None and await store.get_session(live.id) is not None


async def test_duplicate_detection_window_and_null_hospital(store):
    await store.create_report(a_report(dedupe_key="k", hospital_id="h-iroko"))
    await store.create_report(a_report(dedupe_key="k", hospital_id=None))
    await store.create_report(a_report(dedupe_key="old", created_at=datetime.now(UTC) - timedelta(hours=30)))
    assert await store.find_recent_duplicate("k", "h-iroko", "abuse") is True
    assert await store.find_recent_duplicate("k", None, "abuse") is True
    assert await store.find_recent_duplicate("k", "h-iroko", "neglect") is False
    assert await store.find_recent_duplicate("k", "h-sunbird", "abuse") is False
    assert await store.find_recent_duplicate("old", "h-harmattan", "abuse") is False


async def test_followups_and_cascade(store):
    r = a_report()
    await store.create_report(r)
    await store.add_followup(Followup(report_id=r.id, status="worse"))


async def test_full_conversation_runs_on_this_store(store):
    engine = Engine(store, mock_extract, Pack("ng-lagos", allow_unverified=True), "secret")
    r = await say(engine, None, "A nurse slapped me last week at Harmattan General Hospital maternity ward",
                  dedupe_key="d1")
    assert r.ref_code and r.state == "B5"
    r2 = await engine.handle_message(r.session_id, "web", "yes")
    assert r2.done
    reports = await store.list_reports()
    assert len(reports) == 1 and reports[0].followup_opt_in and reports[0].hospital_id == "h-harmattan"
    # Privacy promises hold on a real database too.
    session = await store.get_session(r.session_id)
    assert "transcript" not in session.context and "slapped" not in session.model_dump_json()
    f = await engine.start_followup(r.ref_code)
    await engine.handle_message(f.session_id, "web", "2")
    assert (await store.list_reports())[0].status == "unchanged"


async def test_delete_session_and_audit_log(store):
    s = Session(context={"transcript": [{"role": "user", "text": "secret story"}]})
    await store.create_session(s)
    await store.delete_session(s.id)
    await store.delete_session(s.id)                       # idempotent
    await store.delete_session("not-a-uuid")               # junk never raises
    assert await store.get_session(s.id) is None

    r = a_report()
    await store.create_report(r)
    await store.add_audit(AuditEntry(actor="Ngozi", action="exclude", report_id=r.id, before="ok", after="excluded"))
    await store.add_audit(AuditEntry(actor="Tunde", action="accept", report_id=r.id, before="review", after="ok",
                                     detail="hospital set to X"))
    log = await store.list_audit()
    assert [e.actor for e in log] == ["Tunde", "Ngozi"] and log[0].detail == "hospital set to X"
    assert len(await store.list_audit(limit=1)) == 1
