"""Data periods: general / MTD / YTD on import, and P&O screens that read the right file for the period chosen."""

from __future__ import annotations

import pytest

from pno import importers, period
from pno.api import Api
from pno.db import Database
from pno.po import canon
from pno.po.insights import Insights
from pno.po.store import PoStore

from po_fixture import make_po_workbook


def test_guess_from_names_rows_and_kind():
    g = period.guess("productivity", [], "YTD Productivity August 2026")
    assert (g["type"], g["from"], g["to"]) == ("ytd", "2026-01", "2026-08") and g["sure"]
    g = period.guess("po_shrink", [], "Out of Stock & Stock Days YTDSEP 2026")
    assert (g["type"], g["to"]) == ("ytd", "2026-09")
    assert period.guess("roster", [], "Basic Sheet")["type"] == "general"
    assert period.guess("po_role", [], "In this role")["type"] == "general"
    g = period.guess("po_turnover", [{"date": "2026-02-03"}, {"date": "2026-09-20"}], "Turnover")
    assert (g["type"], g["from"], g["to"]) == ("ytd", "2026-02", "2026-09")
    g = period.guess("sales", [{"period": "MTD", "as_of": "2026-08-31"}], "Sales", "2026-08", "2026-08-31")
    assert (g["type"], g["from"], g["to"]) == ("mtd", "2026-08", "2026-08")
    g = period.guess("po_da", [], "DA", "2026-10")          # no month anywhere: not sure, lined up later
    assert g["type"] == "ytd" and not g["sure"]


def test_productivity_file_number_is_not_a_year():
    from pno.importers.productivity import month_from_text
    assert month_from_text("01_YTD_Productivity_August") is None
    assert month_from_text("Productivity Aug 26") == "2026-08"


def test_sheets_without_a_month_follow_the_others():
    rs = [{"period": period.guess("po_shrink", [], "Stock Days YTDSEP 2026")},
          {"period": period.guess("po_da", [], "DA", "2026-10")},
          {"period": period.guess("roster", [], "Basic Sheet")}]
    period.line_up(rs)
    assert rs[1]["period"]["to"] == "2026-09" and rs[1]["period"]["from"] == "2026-01"
    assert rs[2]["period"]["type"] == "general"
    lonely = [{"period": period.guess("po_nps", [], "NPS", "2026-10")}]
    period.line_up(lonely, known="2026-07")
    assert lonely[0]["period"]["to"] == "2026-07"


def test_clean_keeps_periods_consistent():
    fb = {"type": "ytd", "from": "2026-01", "to": "2026-09"}
    assert period.clean("general", "2026-01", "2026-09", fb) == ("general", None, None)
    assert period.clean("mtd", "2026-01", "2026-09", fb) == ("mtd", "2026-09", "2026-09")
    assert period.clean("ytd", "2026-09", "2026-04", fb) == ("ytd", "2026-04", "2026-09")
    assert period.clean(None, None, None, fb) == ("ytd", "2026-01", "2026-09")
    assert period.label("ytd", "2026-01", "2026-09") == "YTD Jan–Sep 2026"
    assert period.label("mtd", "2026-08", "2026-08") == "MTD Aug 2026"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "pno.sqlite3")
    book = make_po_workbook(tmp_path / "fictional-po.xlsx")
    a = importers.analyze_path(book)
    opts = {r.sheet: {"period_type": "ytd", "period_from": "2026-01", "period_to": "2026-09"} for r in a["results"]
            if r.kind not in period.GENERAL_KINDS}
    opts["*"] = {"as_of": "2026-09-30"}
    out = importers.commit(db, a, opts)
    assert all(r["status"] == "ok" for r in out), out
    return db


def test_import_stores_the_period(db):
    rows = {r["kind"]: (r["period_type"], r["period_from"], r["period_to"]) for r in db.q("SELECT * FROM imports")}
    assert rows["roster"][0] == "general" and rows["po_role"][0] == "general" and rows["po_rating"][0] == "general"
    assert rows["po_shrink"] == ("ytd", "2026-01", "2026-09")


def test_views_pick_the_right_file_and_keep_general_data(db, tmp_path):
    api = Api(db)
    # a second, month-only shrinkage file for August
    book = make_po_workbook(tmp_path / "aug.xlsx")
    a = importers.analyze_path(book)
    shrink = next(r for r in a["results"] if r.kind == "po_shrink")
    a["results"], a["hash"] = [shrink], "august-file"
    out = importers.commit(db, a, {shrink.sheet: {"period_type": "mtd", "period_to": "2026-08"}})
    assert out[0]["status"] == "ok" and out[0]["period"] == "MTD Aug 2026"

    ytd = Insights(PoStore(db), view={"type": "ytd", "from": "2026-01", "to": "2026-09"})
    assert ytd.periods["po_shrink"] == "YTD Jan–Sep 2026"
    assert ytd.has("po_role") and ytd.has("po_master")            # general data counts for every period
    assert any(l.score is not None for l in ytd.leaders())

    mtd = Insights(PoStore(db), view={"type": "mtd", "to": "2026-08"})
    assert mtd.periods["po_shrink"] == "MTD Aug 2026"
    assert mtd.has("po_role")
    assert any("no MTD data" in n for n in mtd.notes)               # tabs that only have YTD say so

    p = api.dispatch("po_view", {"type": "mtd", "to": "2026-08"})
    assert p["label"] == "MTD Aug 2026" and p["view"]["type"] == "mtd"
    r = api.dispatch("po_review", {})
    assert r["has_data"] and r["period"]["label"] == "MTD Aug 2026"
    assert {c["type"] for c in r["period"]["coverage"]} >= {"general", "mtd", "ytd"}
    api.dispatch("po_view", {"type": "latest"})
    assert api.dispatch("po_period", {})["view"]["type"] == "latest"


def test_turnover_is_cut_to_the_period(db):
    full = Insights(PoStore(db))
    dates = sorted(r["date"] for r in full.rows("po_turnover") if r.get("date"))
    month = dates[-1][:7]
    one = Insights(PoStore(db), view={"type": "mtd", "to": month})
    assert one.rows("po_turnover") and all(r["date"][:7] == month for r in one.rows("po_turnover") if r.get("date"))
    assert one.leaver_window == f"MTD {period.month_label(month)}"
    assert len(one.turnover_summary()["monthly"]) > 1               # trend still shows the months around it
    empty = Insights(PoStore(db), view={"type": "mtd", "to": "2001-01"})
    assert not empty.rows("po_turnover")


def test_people_are_placed_from_remarks_and_other_tabs():
    assert canon.working_role("Working as Team Leader DPH but in system he is sales person", "Sales Person") == "Team Leader"
    assert canon.working_role("Leading HHH Since 02-Jun-25", "Stocker") == "Team Leader"
    assert canon.working_role("Working as Section Manager (New Joiner Not in system yet)", "#N/A") == "Section Manager"
    assert canon.working_role("Leading Bakery & Deli", "Section Manager") == ""
    assert canon.store("DHA11") == "LAH DHA Rahbar"
    assert canon.is_leader("Deputy Store Manager") and canon.role_rank("Store Manager") >= canon.STORE_LEVEL


def test_data_health_checklist_checks_and_locks(db, tmp_path):
    api = Api(db)
    r = api.dispatch("data_health", {"month": "2026-09"})
    assert "error" not in r, r
    status = {c["kind"]: c["status"] for c in r["checklist"]}
    assert status["roster"] == "ok" and status["po_shrink"] == "ok" and status["po_turnover"] in ("ok", "missing")
    assert 0 <= r["score"] <= 100 and r["verdict"] and r["measures"]
    assert all(c["level"] in ("bad", "warn", "info") for c in r["checks"])
    # lock September: a new YTD Sep file is refused, a general file still goes in
    r = api.dispatch("lock_month", {"month": "2026-09", "locked": True})
    assert r["locked"] and "2026-09" in r["locked_months"]
    book = make_po_workbook(tmp_path / "again.xlsx")
    a = importers.analyze_path(book)
    a["hash"] = "another-file"
    da = next(x for x in a["results"] if x.kind == "po_da")
    a["results"] = [da]
    out = importers.commit(db, a, {da.sheet: {"period_type": "ytd", "period_to": "2026-09"}})
    assert out[0]["status"] == "locked" and "locked" in out[0]["message"]
    api.dispatch("lock_month", {"month": "2026-09", "locked": False})
    out = importers.commit(db, a, {da.sheet: {"period_type": "ytd", "period_to": "2026-09"}})
    assert out[0]["status"] == "ok"
    conflicts = [c for c in api.dispatch("data_health", {"month": "2026-09"})["checks"] if c["area"] == "Files"]
    assert conflicts and "different" in conflicts[0]["message"]


def test_annualised_turnover(db):
    full = Insights(PoStore(db))
    month = max(r["date"] for r in full.rows("po_turnover") if r.get("date"))[:7]
    t = Insights(PoStore(db), view={"type": "mtd", "to": month}).turnover_summary()
    assert t["window_months"] == 1 and t["annualised"] == t["total"] * 12


def test_ai_answers_data_health(db):
    api = Api(db)
    r = api.dispatch("agent_ask", {"question": "Is my data ready for September?", "month": "2026-09"})
    assert "Data health" in r["answer"] and "/100" in r["answer"]
