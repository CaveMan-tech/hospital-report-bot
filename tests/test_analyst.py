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
