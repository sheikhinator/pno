"""Any table becomes a dataset; store names in either word order; store leads without the Store Manager title."""

from __future__ import annotations

import pytest

from pno import engine, importers
from pno.api import Api
from pno.db import Database
from pno.stores import parse_name

KPI = """Weekly store KPI report
Week 41
Store\tDepartment\tFootfall\tConversion %\tSales Actual\tSales Budget
HM PK LAH Fortress\tFresh Food\t12,450\t38.2%\t21,500,000\t20,000,000
HM PK LAH Fortress\tNon Food\t8,100\t21.0%\t9,800,000\t11,000,000
HM PK KCH Lucky One\tFresh Food\t10,200\t35.1%\t18,000,000\t19,500,000
PK HM GUJ Steel Casting\tFresh Food\t4,100\t30.0%\t5,100,000\t5,600,000
Grand Total\t\t34,850\t\t54,400,000\t56,100,000"""

ROSTER = """Employee Number\tBusiness Unit\tDepartment\tSection\tEmployee Name\tDesignation\tGrade\tGender\tReporting Manager
60000001\tPK HM GUJ Steel Casting\t99:Services\tMGM - Management\tTariq Saeed\tStore Manager\t16\tMale\tCountry Director
60000002\tPK HM GUJ Steel Casting\t02:Market\tFFD - Bakery\tBahadur Ali\tSection Manager\t8\tMale\tTariq Saeed
60000003\tSM PK LAH ASKARI 10\t01:CGD-FMCG\tCGD - FMCG (Common)\tImran Khan\tDeputy Manager\t13\tMale\tCountry Director
60000004\tSM PK LAH ASKARI 10\t01:CGD-FMCG\tCGD - Grocery\tAli Raza\tTeam Leader\t9\tMale\tImran Khan"""


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    return Api(Database(tmp_path / "pno.sqlite3"))


def test_store_word_order():
    a, b = parse_name("PK HM GUJ Steel Casting"), parse_name("HM PK GUJ Steel Casting")
    assert (a.format, a.city, a.tokens) == (b.format, b.city, b.tokens) == ("HM", "GUJ", ["STEEL", "CASTING"])
    assert a.name == "Steel Casting"


def test_store_leads_are_found(api):
    importers.commit(api.db, importers.analyze_text(ROSTER, "pasted"), {"*": {"as_of": "2026-10-20"}}, source="paste")
    mm = engine.model(api.db, "2026-10")
    roles = {p.name: (p.role, p.store, p.store_format) for p in mm.people.values()}
    assert roles["Tariq Saeed"] == ("GM", "Steel Casting", "HM")
    assert roles["Imran Khan"][0] == "GM"            # supermarket Deputy Manager runs the store
    assert roles["Bahadur Ali"][0] == "SM"


def test_old_store_links_are_repaired(api):
    sid = api.db.x("INSERT INTO stores(key,name,format,city,code,is_ho) VALUES('||GUJ STEEL CASTING','HM GUJ Steel Casting','','','',0)").lastrowid
    api.db.x("INSERT INTO store_aliases(alias,raw,store_id,confirmed,source) VALUES('PK HM GUJ STEEL CASTING','PK HM GUJ Steel Casting',?,1,'roster')", (sid,))
    api.dispatch("init", {})
    row = api.db.q1("SELECT s.name, s.format, s.city FROM store_aliases a JOIN stores s ON s.id=a.store_id")
    assert tuple(row) == ("Steel Casting", "HM", "GUJ")


def test_any_table_becomes_an_explained_dataset(api):
    a = importers.analyze_text(KPI, "Weekly store KPI")
    assert [r.kind for r in a["results"]] == ["dataset"]
    res = importers.commit(api.db, a, {"*": {"month": "2026-10"}})
    assert res[0]["status"] == "ok"
    sets = api.dispatch("datasets", {})["datasets"]
    v = api.dispatch("dataset", {"import_id": sets[0]["id"]})
    roles = {c["name"]: c["role"] for c in v["columns"]}
    assert roles["Store"] == "store" and roles["Sales Actual"] == "actual" and roles["Sales Budget"] == "budget"
    assert v["group"] == "_store" and v["measure"] == "Sales Actual"
    assert {k for k, _ in v["series"]} == {"LAH Fortress", "KCH Lucky One", "GUJ Steel Casting"}
    assert v["rows"] == 4                            # the Grand Total row is not counted twice
    text = " ".join(v["insights"])
    assert "of budget" in text and "GUJ Steel Casting" in text
    by_dept = api.dispatch("dataset", {"import_id": sets[0]["id"], "group": "Department", "measure": "Conversion %"})
    assert by_dept["agg"] == "avg" and dict(by_dept["series"])["Fresh Food"] == pytest.approx(34.43, abs=0.01)
    ai = api.dispatch("dataset_ai", {"import_id": sets[0]["id"]})
    assert ai["engine"] == "basic" and ai["insights"]
    r = api.dispatch("agent_ask", {"question": "What does the weekly store KPI show?"})
    assert "Weekly store KPI" in r["answer"]
