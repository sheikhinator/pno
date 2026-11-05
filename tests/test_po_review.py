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


def test_undo_removes_the_tab(api):
    turnover = api.db.q1("SELECT id FROM imports WHERE kind='po_turnover' AND active=1")[0]
    importers.undo(api.db, turnover)
    assert api.db.q1("SELECT active FROM imports WHERE id=?", (turnover,))[0] == 0


def test_name_matching():
    assert canon.section("S050-S051 Deli & Dairy") == "Deli"
    assert canon.section("Comm.FMCG") == "Consumer Goods"
    assert canon.store("STC-Gujranwala") == "GUJ Steel Casting"
    assert canon.store("HB PK KCH H&B PAK KCH LUK (MYLI)") == "KCH Lucky One · Myli"
    assert canon.repair_name("MuhMORmad SMORi HMORza") == "Muhammad Sami Hamza"
