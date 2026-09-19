import os
import re

os.environ.update(EXTRACT_MODE="mock", STORE="memory", ALLOW_UNVERIFIED="true", DEMO_MODE="true",
                  ANALYST_PASSWORD="pw")

from fastapi.testclient import TestClient

from app import analyst as A
from app.config import get_settings
from app.engine.packs import Pack
from app.main import app
from app.seed import build

get_settings.cache_clear()
AUTH = ("analyst", "pw")


def test_threshold_counts_only_credible_reports_and_hides_small_groups():
    reports, _ = build()
    rows = A.patterns(reports, Pack("ng-lagos"))
    keys = {(p["hospital_id"], p["category"]) for p in rows}
    assert ("h-harmattan", "emergency_refused") in keys
    assert ("h-palmgrove", "abuse") not in keys and ("h-iroko", "abuse") not in keys   # 3 and 4 reports
    top = next(p for p in rows if p["hospital_id"] == "h-harmattan" and p["category"] == "emergency_refused")
    assert top["reports_90d"] == 13 and top["flagged"] == 1                            # 14 seeded, 1 held back
    assert all(p["reports_90d"] >= A.THRESHOLD for p in rows)


def test_excluding_reports_can_drop_a_pattern_below_threshold():
    reports, _ = build()
    for r in [r for r in reports if r.hospital_id == "h-iroko" and r.category == "detention"][:2]:
        r.credibility = "excluded"
    keys = {(p["hospital_id"], p["category"]) for p in A.patterns(reports, Pack("ng-lagos"))}
    assert ("h-iroko", "detention") not in keys


def test_slice_cells_under_threshold_are_masked_and_cannot_be_derived():
    reports, _ = build()
    rs = A.pattern_reports(reports, "h-harmattan", "emergency_refused")
    for cells in A.slices(rs).values():
        shown = [v for _, v in cells]
        if any(v.startswith("fewer") for v in shown):
            # No exact number may sit next to a masked cell, or subtraction reveals it.
            assert all(v.startswith("fewer") or v.endswith("+") for v in shown)
        else:
            assert all(int(v) >= A.THRESHOLD for v in shown)


def test_brief_contains_only_numbers_that_exist_in_the_pattern():
    reports, _ = build()
    pack = Pack("ng-lagos", allow_unverified=True)
    p = A.patterns(reports, pack)[0]
    text = A.brief(p, pack)
    allowed = {str(v) for v in p.values() if isinstance(v, int)} | {str(A.THRESHOLD), str(A.WINDOW_DAYS), "20", "2014"}
    body = re.sub(r"Period:.*", "", text)  # dates are generated, not counted
    assert set(re.findall(r"\b\d+\b", body)) <= allowed
    assert "unverified" in text and "SAMPLE DATA" in text and "not rates" in text


def test_brief_withholds_unverified_law_in_production_mode():
    reports, _ = build()
    pack = Pack("ng-lagos", allow_unverified=False)
    text = A.brief(A.patterns(reports, pack)[0], pack)
    assert "Section 20" not in text and "pending verification" in text


def test_facets_csv_has_no_summaries_codes_or_exact_dates():
    reports, _ = build()
    text = A.facets_csv(reports, Pack("ng-lagos"))
    assert "summary" not in text and "ref_code" not in text and "dedupe" not in text
    assert re.search(r"\d{4}-W\d{2}", text) and not re.search(r"\d{4}-\d{2}-\d{2}", text)
    assert "h-palmgrove" not in text and "Palm Grove" not in text


def test_analyst_pages_need_the_password_and_work():
    with TestClient(app) as c:
        assert c.get("/analyst").status_code == 401
        assert c.get("/analyst", auth=("x", "wrong")).status_code == 401
        page = c.get("/analyst", auth=AUTH)
        assert page.status_code == 200 and "SAMPLE DATA" in page.text and "Harmattan General Hospital" in page.text
        assert "Palm Grove" not in page.text
        detail = c.get("/analyst/pattern/h-harmattan/emergency_refused", auth=AUTH)
        assert detail.status_code == 200 and "fewer than 5" in detail.text
        assert c.get("/analyst/pattern/h-palmgrove/abuse", auth=AUTH).status_code == 404
        assert c.get("/analyst/brief/h-harmattan/emergency_refused.md", auth=AUTH).text.startswith("# 13 unverified")
        assert c.get("/analyst/patterns.csv", auth=AUTH).text.startswith("hospital,category")


def test_full_loop_report_in_pattern_moves():
    with TestClient(app) as c:
        def count():
            rows = c.get("/analyst/patterns.csv", auth=AUTH).text.splitlines()
            return int(next(r for r in rows if r.startswith("Lagoon View General Hospital,abuse")).split(",")[2])
        before = count()
        c.post("/api/chat", json={"text": "A nurse slapped me last week at Lagoon View General Hospital maternity ward"})
        assert count() == before + 1


def test_content_review_page_lists_everything_to_verify():
    with TestClient(app) as c:
        assert c.get("/analyst/content").status_code == 401
        page = c.get("/analyst/content?pack=ke-nairobi", auth=AUTH).text
        assert "0 of" in page and "Article 43(2)" in page and "new.kenyalaw.org" in page
        assert "app.verify mark ke-nairobi" in page and "ALLOW_UNVERIFIED is ON" in page
        assert "A1.emergency_refused" in c.get("/analyst/content", auth=AUTH).text


def _all_patterns():
    for pid in ("ng-lagos", "ke-nairobi"):
        pack = Pack(pid, allow_unverified=True)
        reports, _ = build(pack)
        for pat in A.patterns(reports, pack):
            yield pack, pat, A.pattern_reports(reports, pat["hospital_id"], pat["category"])


def test_every_thread_post_fits_and_uses_only_numbers_from_the_pattern():
    for pack, pat, rs in _all_patterns():
        posts = A.thread(pat, rs, pack)
        assert 5 <= len(posts) <= 8 and all(len(p) <= 280 for p in posts), [len(p) for p in posts]
        assert [p.split(" ")[0] for p in posts] == [f"{i}/{len(posts)}" for i in range(1, len(posts) + 1)]
        assert "unverified" in posts[0] and "SAMPLE DATA" in posts[0] and pack.meta["target"]["x_handle"] in posts[0]
        assert "not rates" in posts[-1] and pack.org_name in posts[-1]
        allowed = {str(v) for v in pat.values() if isinstance(v, int) and not isinstance(v, bool)}
        body = " ".join(posts[:2]).replace(pat["hospital"], "")   # "Level 5 Hospital" is a name, not a statistic
        numbers = set(re.findall(r"(?<![/\d])\b\d+\b(?!/)", body)) - {str(A.WINDOW_DAYS)}
        assert numbers <= allowed, (numbers, allowed)


def test_thread_withholds_unverified_law_in_production_mode():
    pack = Pack("ke-nairobi", allow_unverified=False)
    reports, _ = build(pack)
    pat = A.patterns(reports, pack)[0]
    text = " ".join(A.thread(pat, A.pattern_reports(reports, pat["hospital_id"], pat["category"]), pack))
    assert "Article 43" not in text and "pending verification" in text


def test_dominant_facts_are_only_stated_when_safe_and_true():
    from app.engine.models import Report
    def r(dept, time):
        return Report(ref_code_hmac="x", category="neglect", severity="not_severe", department=dept, time_bucket=time)
    many = [r("ward", "night")] * 6 + [r("emergency", "day")] * 2
    assert A._dominant(many, "time_bucket", A._TIME_WORDS) == "at night"
    few = [r("ward", "night")] * 4 + [r("emergency", "day")] * 1          # majority, but under the threshold
    assert A._dominant(few, "time_bucket", A._TIME_WORDS) is None
    split = [r("ward", "night")] * 5 + [r("ward", "day")] * 6               # over threshold, but not most
    assert A._dominant(split, "time_bucket", A._TIME_WORDS) == "during the day"
    assert A._dominant([r("unknown", "unknown")] * 9, "department", A._DEPT_WORDS) is None


def test_card_is_safe_svg_with_the_count_and_the_sample_mark():
    for pack, pat, _ in _all_patterns():
        svg = A.card_svg(pat, pack)
        assert svg.startswith("<svg") and f">{pat['reports_90d']}</text>" in svg
        assert "SAMPLE DATA" in svg and "unverified" in svg and "<script" not in svg
    evil = dict(pat, hospital='<script>alert(1)</script> & Sons')
    assert "<script>" not in A.card_svg(evil, pack) and "&lt;script&gt;" in A.card_svg(evil, pack)


def test_trend_words_and_small_halves_stay_hidden():
    from datetime import UTC, datetime, timedelta

    from app.engine.models import Report
    now = datetime.now(UTC)
    def at(days):
        return Report(ref_code_hmac="x", category="abuse", severity="not_severe", created_at=now - timedelta(days=days))
    rising = [at(5)] * 8 + [at(60)] * 2
    assert A.trend(rising)["word"] == "rising" and A.trend(rising)["recent"] is None     # earlier half is under 5
    both = [at(5)] * 9 + [at(60)] * 5
    assert A.trend(both) == {"word": "rising", "recent": 9, "earlier": 5}
    assert A.trend([at(5)] * 5 + [at(60)] * 5)["word"] == "steady"
    assert sum(A.weekly_counts(both)) == 14 and len(A.weekly_counts(both)) == 13


def test_ready_to_post_section_on_the_pattern_page():
    with TestClient(app) as c:
        page = c.get("/analyst/pattern/h-harmattan/emergency_refused", auth=AUTH).text
        assert "Ready to post" in page and "x.com/intent/tweet" in page and "nothing here is written by AI" in page
        assert "Last 13 weeks" in c.get("/analyst", auth=AUTH).text
        card = c.get("/analyst/card/h-harmattan/emergency_refused.svg", auth=AUTH)
        assert card.status_code == 200 and card.headers["content-type"].startswith("image/svg+xml")
        assert c.get("/analyst/card/h-harmattan/emergency_refused.svg").status_code == 401
        assert c.get("/analyst/card/h-palmgrove/abuse.svg", auth=AUTH).status_code == 404


def test_review_queue_resolves_an_unknown_hospital_and_logs_the_decision():
    with TestClient(app) as c:
        assert c.get("/analyst/review").status_code == 401
        def count():
            rows = c.get("/analyst/patterns.csv", auth=AUTH).text.splitlines()
            return int(next(r for r in rows if r.startswith("Lagoon View General Hospital,abuse")).split(",")[2])
        before = count()
        c.post("/api/chat", json={"text": "A nurse slapped me last week at Island Peoples Hospital maternity ward"})
        assert count() == before                                          # held, not counted

        page = c.get("/analyst/review", auth=AUTH).text
        assert "Hospital name not recognised" in page and "Island Peoples Hospital" in page and "Decision log" in page
        store = c.app.state.engine.store
        held = next(r for r in store.reports.values() if r.hospital_name_raw and "Island Peoples" in r.hospital_name_raw)

        # Cannot be counted without saying which hospital it is, or with a hospital from another country.
        assert c.post(f"/analyst/reports/{held.id}/accept", auth=AUTH, follow_redirects=False).status_code == 400
        assert c.post(f"/analyst/reports/{held.id}/accept", auth=AUTH, data={"hospital_id": "h-mugumo-ridge"},
                      follow_redirects=False).status_code == 400
        r = c.post(f"/analyst/reports/{held.id}/accept", auth=("Ngozi", "pw"), data={"hospital_id": "h-lagoonview"},
                   follow_redirects=False)
        assert r.status_code == 303 and count() == before + 1
        fixed = store.reports[held.id]
        assert fixed.hospital_id == "h-lagoonview" and fixed.hospital_name_raw is None and fixed.credibility == "ok"

        log = store.audit[-1]
        assert (log.actor, log.action, log.before, log.after) == ("Ngozi", "accept", "review", "ok")
        assert "Lagoon View General Hospital" in log.detail
        assert "Ngozi" in c.get("/analyst/review", auth=AUTH).text


def test_excluding_a_report_is_always_logged():
    with TestClient(app) as c:
        store = c.app.state.engine.store
        target = next(r for r in store.reports.values() if r.hospital_id == "h-iroko" and r.category == "detention")
        n = len(store.audit)
        c.post(f"/analyst/reports/{target.id}/exclude", auth=("Tunde", "pw"), follow_redirects=False)
        assert len(store.audit) == n + 1 and store.audit[-1].actor == "Tunde" and store.audit[-1].after == "excluded"


def test_kenyan_held_reports_do_not_show_in_the_lagos_queue():
    with TestClient(app) as c:
        c.post("/api/chat", json={"pack": "ke-nairobi",
                                  "text": "A nurse insulted my wife last week at Some Unknown Kenyan Hospital maternity"})
        assert "Some Unknown Kenyan" not in c.get("/analyst/review", auth=AUTH).text
        assert "Some Unknown Kenyan" in c.get("/analyst/review?pack=ke-nairobi", auth=AUTH).text


def test_long_posts_are_split_on_sentences_and_never_overflow():
    long = "We ask for this. " + "A very long requirement that goes on and on " * 12 + "and ends. Then a short one."
    parts = A._split_post(long)
    assert len(parts) > 1 and all(len(p) <= A.POST_LIMIT for p in parts)
    assert " ".join(parts).split() == long.split()                    # nothing lost, nothing added
    assert A._split_post("Short.") == ["Short."]
