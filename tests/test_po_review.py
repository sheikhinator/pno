"""P&O review: the ten-tab workbook through PNO's importer, the API screens, Ask PNO and the export pack."""

from __future__ import annotations

import pytest

from pno import importers
from pno.api import Api
from pno.db import Database
from pno.po import canon
from pno.po.insights import Insights
from pno.po.store import PoStore

from po_fixture import make_po_workbook

PO_KINDS = {"po_rating", "po_role", "po_turnover", "po_da", "po_nps", "po_shrink", "po_shift"}


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "pno.sqlite3")
    book = make_po_workbook(tmp_path / "fictional-po.xlsx")
    analysis = importers.analyze_path(book)
    kinds = {r.kind for r in analysis["results"]}
    assert PO_KINDS | {"sales", "productivity", "roster"} <= kinds, kinds
    out = importers.commit(db, analysis, {"*": {"month": "2026-09", "as_of": "2026-09-30"}})
    assert all(r["status"] == "ok" for r in out), out
    return Api(db)


def test_every_tab_lands_in_the_review(api):
    kinds = {r[0] for r in api.db.q("SELECT DISTINCT kind FROM po_records")}
    assert PO_KINDS | {"po_sales", "po_productivity", "po_master"} <= kinds
    ins = Insights(PoStore(api.db))
    assert ins.headline()["stores"] == 3
    assert ins.headline()["sales"] > 0
    assert any(l.score is not None for l in ins.leaders())


def test_personal_fields_are_never_stored(api):
    blob = " ".join(r[0] for r in api.db.q("SELECT payload FROM po_records")).lower()
    for word in ("birth", "mobile", "marital", "email"):
        assert word not in blob


def test_screens(api):
    review = api.dispatch("po_review", {"metric": "shrink_variance"})
    assert review["has_data"] and review["stores"] and review["heat"]["sections"]
    leaders = api.dispatch("po_leaders", {})
    assert leaders["leaders"] and len(leaders["talent"]) == 9
    first = leaders["leaders"][0]["key"]
    assert "LEADER INDEX /10" in api.dispatch("po_leader", {"key": first})["html"]
    assert api.dispatch("po_turnover", {})["total"] > 0
    shifts = api.dispatch("po_shifts", {})
    assert shifts["grid"] and len(shifts["grid"][0]["days"]) == 31
    w = api.dispatch("po_weights", {"weights": {"sales": 50}})
    assert w["weights"]["sales"] == 50
    assert api.dispatch("po_weights", {"reset": True})["weights"]["sales"] == 30


def test_undo_removes_the_tab(api):
    turnover = api.db.q1("SELECT id FROM imports WHERE kind='po_turnover' AND active=1")[0]
    importers.undo(api.db, turnover)
    assert api.dispatch("po_turnover", {})["has_data"] is False


def test_hide_names_masks_leaders(api):
    api.db.set_setting("hide_names", True)
    names = [l["name"] for l in api.dispatch("po_leaders", {})["leaders"]]
    assert names and all(n.startswith("Leader ") for n in names)


def test_ask_pno_answers_p_and_o_questions(api):
    for q, expect in [("Which roles are at risk?", "Roles at risk"), ("Where is turnover highest?", "Turnover"),
                      ("Compare Fortress and Lucky One", "LAH Fortress"), ("Explain the leader index", "How the leader index works")]:
        r = api.dispatch("agent_ask", {"question": q})
        assert expect in (r.get("answer") or ""), (q, r)


def test_export_pack(api, tmp_path):
    for fmt in ("pdf", "pptx", "xlsx"):
        r = api.dispatch("export", {"pack": "po", "fmt": fmt, "save_as": str(tmp_path / f"po.{fmt}"), "open_after": False})
        assert r.get("ok"), r


def test_name_matching():
    assert canon.section("S050-S051 Deli & Dairy") == "Deli"
    assert canon.section("Comm.FMCG") == "Consumer Goods"
    assert canon.store("STC-Gujranwala") == "GUJ Steel Casting"
    assert canon.store("HB PK KCH H&B PAK KCH LUK (MYLI)") == "KCH Lucky One · Myli"
    assert canon.repair_name("MuhMORmad SMORi HMORza") == "Muhammad Sami Hamza"
