"""2.1: organisation changes, span of control, probation, calibration, data requests, batch export, remembered layouts."""

from __future__ import annotations

import json
import zipfile
from datetime import date, timedelta

import pytest

from pno import importers, org_health
from pno.api import Api, template_key
from pno.db import Database

from po_fixture import make_po_workbook


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "pno.sqlite3")
    a = importers.analyze_path(make_po_workbook(tmp_path / "po.xlsx"))
    out = importers.commit(db, a, {"*": {"month": "2026-09", "as_of": "2026-09-30"}})
    assert all(r["status"] == "ok" for r in out), out
    return Api(db)


def _second_basic_sheet(db, edit):
    old = db.q1("SELECT * FROM imports WHERE kind='roster' ORDER BY id DESC LIMIT 1")
    cols = [k for k in old.keys() if k != "id"]
    new_id = db.x(f"INSERT INTO imports({', '.join(cols)}) SELECT {', '.join(cols)} FROM imports WHERE id=?", (old["id"],)).lastrowid
    db.x("UPDATE imports SET file_name='Basic Sheet Oct.xlsx' WHERE id=?", (new_id,))
    recs = [json.loads(r[0]) for r in db.q("SELECT payload FROM po_records WHERE import_id=? AND kind='po_master'", (old["id"],))]
    rcols = [k for k in db.q1("SELECT * FROM po_records LIMIT 1").keys() if k not in ("id", "import_id", "payload")]
    for rec in edit(recs):
        db.x(f"INSERT INTO po_records(import_id, payload{''.join(', ' + c for c in rcols)}) SELECT ?, ?{''.join(', ' + c for c in rcols)} "
             "FROM po_records WHERE import_id=? AND kind='po_master' LIMIT 1", (new_id, json.dumps(rec), old["id"]))
    return new_id


def test_changes_need_two_basic_sheets(api):
    assert not org_health.changes(api.db)["has_data"]


def test_changes_between_basic_sheets(api):
    def edit(recs):
        gone = recs.pop(0)
        recs[0] = {**recs[0], "store": "KHI Somewhere" if recs[0]["store"] != "KHI Somewhere" else "LAH Fortress"}
        recs[1] = {**recs[1], "designation": "Store Manager"}
        recs[2] = {**recs[2], "manager_name": "Somebody New"}
        recs.append({**gone, "employee_id": "NEW001", "employee_name": "New Joiner"})
        return recs
    _second_basic_sheet(api.db, edit)
    c = org_health.changes(api.db)
    assert c["has_data"]
    assert [j["id"] for j in c["joiners"]] == ["NEW001"]
    assert [l["id"] for l in c["leavers"]] == ["DEMO0001"]
    assert len(c["transfers"]) == 1 and len(c["roles"]) == 1 and c["roles"][0]["promotion"] and c["promotions"] == 1
    assert len(c["managers"]) == 1
    assert len(c["unexplained_leavers"]) <= len(c["leavers"])


def test_span_and_probation(api):
    r = api.dispatch("organisation", {})
    sp = r["span"]
    assert sp["rows"] and sp["managers"] == len(sp["rows"]) and sum(x["direct_reports"] for x in sp["rows"]) <= r["headcount"] + 15
    assert r["probation"]["months"] == 3 and r["probation"]["rows"] == []
    joined = (date.today() - timedelta(days=80)).isoformat()
    api.db.x("UPDATE po_records SET payload=json_set(payload, '$.joining_date', ?) WHERE kind='po_master' AND json_extract(payload, '$.employee_id')='DEMO0002'", (joined,))
    api._cache = {} if hasattr(api, "_cache") else None
    r = api.dispatch("organisation", {"probation_months": 3})
    rows = [x for x in r["probation"]["rows"] if x["joined"] == joined]
    assert rows and rows[0]["days"] <= 30 and api.db.get_setting("probation_months") in (3, "3")


def test_calibration(api):
    ca = api.dispatch("organisation", {})["calibration"]
    assert ca["has_data"] and ca["n"] == 15 and sum(d["count"] for d in ca["distribution"]) == 15
    assert {g["name"] for g in ca["by_gender"]} <= {"Male", "Female"}
    assert all(isinstance(f, str) for f in ca["flags"])


def test_data_request_text(api):
    r = api.dispatch("data_request", {"month": "2026-10", "lang": "en"})
    assert r["missing"] and "please share" in r["text"] and all(m.split(" (")[0] in r["text"] for m in r["missing"])
    ur = api.dispatch("data_request", {"month": "2026-10", "lang": "ur"})
    assert "شکریہ" in ur["text"]


def test_template_key_ignores_month():
    assert template_key("Out of Stock & Stock Days YTDSEP 2026.xlsx") == template_key("Out of Stock & Stock Days YTDOCT.xlsx")
    assert template_key("Turnover Sep.xlsx") == template_key("turnover october.xlsx")


def test_templates_remembered_and_forgotten(api, tmp_path):
    a = importers.analyze_path(make_po_workbook(tmp_path / "po2.xlsx"))
    api._remember_templates([a], [{"results": [{"status": "ok", "import_id": 3, "sheet": "Performance Rating Sep"}]}])
    t = api.dispatch("import_templates", {})["templates"]
    assert any(x["kind"] == "po_rating" and x["kind_label"] for x in t)
    k = next(x["key"] for x in t if x["kind"] == "po_rating")
    assert not any(x["key"] == k for x in api.dispatch("import_templates", {"forget": k})["templates"])


def test_batch_export_one_file_per_store(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    api = Api(Database(tmp_path / "real.sqlite3"))
    api.dispatch("demo", {"on": True})
    out = tmp_path / "stores.zip"
    r = api.dispatch("export_batch", {"pack": "store", "fmt": "pdf", "save_as": str(out), "open_after": False})
    names = zipfile.ZipFile(out).namelist()
    assert names and all(n.endswith(".pdf") for n in names) and len(names) == len(set(names))
    assert r.get("files", len(names)) == len(names)


def test_changes_refuse_different_scopes(api):
    _second_basic_sheet(api.db, lambda recs: [{**r, "employee_id": "X" + r["employee_id"]} for r in recs])
    c = org_health.changes(api.db)
    assert not c["has_data"] and "different people" in c["note"]


def test_assistant_answers_organisation_questions(api):
    from pno.agent import basic
    from pno.agent.tools import Toolbox
    tb = Toolbox(api.agent, "2026-09", {}, False)
    for q in ("Who is ending probation?", "What is our span of control?", "Are ratings fair?", "Who joined this month?"):
        assert basic.answer(tb, q).strip()
