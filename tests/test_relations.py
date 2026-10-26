"""2.8: employee relations cases, HR letters and exit interviews."""

from __future__ import annotations

from datetime import date

import pytest

from pno import importers
from pno.api import Api
from pno.db import Database

from po_fixture import make_po_workbook


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "pno.sqlite3")
    a = importers.analyze_path(make_po_workbook(tmp_path / "po.xlsx"))
    importers.commit(db, a, {"*": {"month": "2026-09", "as_of": "2026-09-30"}})
    return Api(db)


def _emp(api, q="DEMO0001"):
    return api.dispatch("brain_search", {"q": q})["rows"][0]["emp"]


def test_disciplinary_case_flow_and_ladder(api):
    emp = _emp(api)
    c = api.dispatch("er_open", {"kind": "Disciplinary", "emp": emp, "category": "Lateness", "description": "Late 4 times in September"})
    assert c["stage"] == "Opened" and c["store"] and c["stage_due"] and c["suggest"]["outcome"] == "Counselling"
    c = api.dispatch("er_advance", {"case_id": c["id"]})
    assert c["stage"] == "Show cause issued"
    e = api.dispatch("er_advance", {"case_id": c["id"], "stage": "Closed"})
    assert "outcome" in e["error"]
    c = api.dispatch("er_advance", {"case_id": c["id"], "stage": "Closed", "outcome": "Written warning", "note": "panel decision"})
    assert c["stage"] == "Closed" and c["outcome"] == "Written warning" and len(c["history"]) == 3
    c2 = api.dispatch("er_open", {"kind": "Disciplinary", "emp": emp, "category": "Lateness"})
    assert c2["prior"] and c2["suggest"]["outcome"] == "Final written warning"
    lst = api.dispatch("er_cases", {"status": "all"})
    assert lst["open"] == 1 and lst["closed"] == 1
    # overdue steps show on the Today list
    api.db.x("UPDATE er_cases SET stage_due='2020-01-01' WHERE id=?", (c2["id"],))
    assert any(i["area"] == "Employee relations" for i in api.dispatch("today", {})["items"])


def test_letters(api, tmp_path):
    emp = _emp(api)
    t = api.dispatch("letter_types", {})
    assert {x["kind"] for x in t["types"]} >= {"offer", "show_cause", "warning", "experience", "transfer", "promotion"}
    d = api.dispatch("letter_defaults", {"kind": "experience", "emp": emp})
    assert d["fields"]["position"] and d["name"] and d["ref"].startswith("MAF-PK/P&O/EXPERIENCE/")
    for fmt in ("docx", "pdf"):
        out = tmp_path / f"exp.{fmt}"
        f = dict(d["fields"], from_date=d["fields"]["from_date"] or "01 January 2020")
        r = api.dispatch("letter_make", {"kind": "experience", "emp": emp, "name": d["name"], "fields": f, "fmt": fmt, "save_as": str(out), "open_after": False})
        assert "error" not in r, r
        assert out.stat().st_size > 2000
    bad = api.dispatch("letter_make", {"kind": "warning", "emp": emp, "name": d["name"], "fields": {}, "save_as": str(tmp_path / "w.docx"), "open_after": False})
    assert "Fill in" in bad["error"]
    c = api.dispatch("er_open", {"kind": "Disciplinary", "emp": emp, "category": "Cash shortage", "description": "Till short by PKR 3,000"})
    d = api.dispatch("letter_defaults", {"kind": "show_cause", "emp": emp, "case_id": c["id"]})
    assert "Till short" in d["fields"]["allegation"]
    api.dispatch("letter_make", {"kind": "show_cause", "emp": emp, "name": d["name"], "fields": d["fields"], "case_id": c["id"],
                                 "save_as": str(tmp_path / "sc.docx"), "open_after": False})
    assert api.dispatch("er_case", {"case_id": c["id"]})["letters"]
    refs = [x["ref"] for x in api.dispatch("letter_types", {})["letters"]]
    assert len(refs) == len(set(refs))
    assert any(x["kind"] == "letter" for x in api.dispatch("brain_person", {"emp": emp})["timeline"])


def test_exit_interviews(api):
    emp = _emp(api, "DEMO0002")
    r = api.dispatch("exit_add", {"emp": emp, "leave_date": date.today().isoformat(), "main_reason": "Better pay elsewhere",
                                  "reasons": ["Career growth"], "manager_score": 2, "pay_score": 1, "would_return": True, "recommend": 9, "comments": "Good team"})
    assert r["n"] == 1 and r["rows"][0]["store"] and r["enps"] == 100 and r["would_return"] == 100
    assert dict(r["reasons"])["Better pay elsewhere"] == 1 and r["scores"]["Manager"] == 2
