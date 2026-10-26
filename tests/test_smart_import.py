"""2.5 Smart Import: any layout, any names; discrepancies; column matching; calendar."""

from __future__ import annotations

import base64
from datetime import date, timedelta

import openpyxl
import pytest

from pno import importers
from pno.api import Api
from pno.db import Database

FILES = {
    "Staff list Oct.csv": "MAF Carrefour Pakistan\nStaff list as of 15 Oct 2026\n\nEmp Code,Full Name,Store,Dept,Job Title,DOJ,Line Manager,Sex\n"
                          "20060874,Muhammad Awais Anwar,HM PK FAI Lyallpur Galleria,CGD,Team Leader,13/09/2023,Muhammad Waqas Hameed,Male\n"
                          "20011111,Ali Khan,HM PK LAH Packages Mall,Fresh Food,Section Manager,01/02/2019,Imran Ali,Male\n"
                          "20022222,Sara Ahmed,SM PK LAH DHA 7,Non Food,Cashier,05/06/2024,Ali Khan,Female\n",
    "appraisals.csv": "Staff ID,Name,Year,Final Rating,Location\n20060874,Muhammad Awais Anwar,2025,3,Lyallpur\n20011111,Ali Khan,2025,4.5,Packages Mall\n"
                      "29999999,Someone Else,2025,7,Packages Mall\n",
    "exits.csv": "ID,Employee,Location,Last Working Day,Separation Type,Reason\n20033333,Bilal,HM PK LAH Fortress,12-Aug-2026,Resignation,Better job\n"
                 "20044444,Kamran,HM PK KCH Lucky One,03-Sep-2026,Termination,Absence\n20055555,Usman,Emporium,20-Sep-2026,Resignation,Studies\n",
    "role dates.csv": "Emp #,Name,Branch,Position,In role since\n20060874,Muhammad Awais Anwar,Lyallpur Galleria,Team Leader,1-Mar-24\n20011111,Ali Khan,Packages,Section Manager,10-Jan-22\n",
    "leave oct.csv": "Employee Code,Leave Category,Start,End,Approval\n20060874,Annual Leave,02/10/2026,04/10/2026,Approved\n20011111,Sick Leave,10/10/2026,10/10/2026,Rejected\n"
                     "20022222,Casual,12/10/2026,13/10/2026,Approved\n",
    "Disciplinary cases.csv": "Store,Section,Employee,Date,Violation\nHM PK LAH Fortress,Bakery,Ali,01/09/2026,Late\nHM PK LAH Fortress,Bakery,Bilal,03/09/2026,Absence\n"
                              "Emporium,Butchery,Usman,04/09/2026,Misconduct\n",
    "store sales.csv": "Store,Net Sales,Budget,LY\nHM PK LAH Fortress,774053169,725576093,667287214\nHM PK LAH Packages Mall,540306284,504671006,474346000\nTotal,1314359453,1230247099,1141633214\n",
    "export.csv": "20060874,Muhammad Awais Anwar,HM PK FAI Lyallpur Galleria,Team Leader,13/09/2023\n20011111,Ali Khan,HM PK LAH Packages Mall,Section Manager,01/02/2019\n"
                  "20022222,Sara Ahmed,SM PK LAH DHA 7,Cashier,05/06/2024\n",
}
EXPECT = {"Staff list Oct.csv": "roster", "appraisals.csv": "po_rating", "exits.csv": "po_turnover", "role dates.csv": "po_role", "leave oct.csv": "leave",
          "Disciplinary cases.csv": "po_da", "store sales.csv": "sales", "export.csv": "roster"}


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    return Api(Database(tmp_path / "p.sqlite3"))


def up(api, files, month="2026-09"):
    return api.dispatch("import_upload", {"files": [{"name": n, "b64": base64.b64encode(t.encode()).decode()} for n, t in files.items()], "month": month})


@pytest.mark.parametrize("name", list(FILES))
def test_any_layout_is_recognised(name):
    d = importers.describe(importers.analyze_bytes(FILES[name].encode(), name))
    assert [r["kind"] for r in d["results"]] == [EXPECT[name]], d
    assert d["results"][0]["rows"] >= 2


def test_details_are_read_correctly():
    d = importers.analyze_bytes(FILES["appraisals.csv"].encode(), "appraisals.csv")
    rows = {r["employee_id"]: r for r in d["results"][0].rows}
    assert rows["20011111"]["rating"] == 4.5 and rows["20011111"]["cycle"] == 2025 and rows["20011111"]["store"] == "LAH Packages Mall"
    d = importers.analyze_bytes(FILES["leave oct.csv"].encode(), "leave.csv")
    assert {r["emp_no"] for r in d["results"][0].rows} == {"20060874", "20022222"}          # the rejected request is left out
    d = importers.analyze_bytes(FILES["Disciplinary cases.csv"].encode(), "da.csv")
    cnt = {(r["store"], r["section"]): r["count"] for r in d["results"][0].rows}
    assert cnt[("LAH Fortress", "Bakery")] == 2 and cnt[("LAH Emporium Mall", "Butchery")] == 1
    d = importers.analyze_bytes(FILES["store sales.csv"].encode(), "s.csv")
    assert len(d["results"][0].rows) == 2                                                     # the Total line is not a store


def test_xlsx_with_titles_and_two_row_header(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leavers Q3"
    ws.append(["MAF Carrefour · People & Organisation"])
    ws.append([])
    ws.append(["Employee", None, "Exit", None, None])
    ws.append(["Number", "Name", "Date", "Type", "Reason"])
    ws.append([20033333, "Bilal Ahmed", date(2026, 8, 12), "Resignation", "Better job"])
    ws.append([20044444, "Kamran Ali", date(2026, 9, 3), "Termination", "Absence"])
    p = tmp_path / "q3.xlsx"
    wb.save(p)
    a = importers.analyze_path(p)
    r = a["results"][0]
    assert r.kind == "po_turnover" and len(r.rows) == 2 and r.rows[0]["date"] == "2026-08-12"


def test_discrepancies_are_reported(api):
    s = up(api, {k: FILES[k] for k in ("Staff list Oct.csv", "appraisals.csv")})
    res = {r["kind"]: r for f in s["files"] for r in f["results"]}
    texts = " ".join(i["text"] for i in res["po_rating"]["issues"])
    assert "outside 0–5" in texts and "not on the employee master" in texts
    future = "Emp Code,Full Name,Store,Job Title,DOJ,Line Manager\n1,Ali Khan,Narnia Mall,Cashier,01/01/2099,X\n2,Sara Khan,Narnia Mall,Cashier,01/01/2020,X\n"
    s = up(api, {"x.csv": future})
    t = " ".join(i["text"] for i in s["files"][0]["results"][0]["issues"])
    assert "future" in t and "not in P&O's store list" in t


def test_remap_and_remembered_columns(api):
    s = up(api, {"appraisals.csv": FILES["appraisals.csv"]})
    f = s["files"][0]
    r = f["results"][0]
    cols = {c["header"]: c["index"] for c in r["columns"]}
    # the user says 'Year' is not the cycle and 'Location' is the store; read it again
    out = api.dispatch("import_remap", {"token": s["token"], "file": f["file"], "sheet": r["sheet"], "kind": "po_rating",
                                        "mapping": {"employee_id": cols["Staff ID"], "employee_name": cols["Name"], "rating": cols["Final Rating"],
                                                    "store": cols["Location"]}})
    assert "error" not in out, out
    r2 = out["file"]["results"][0]
    assert {m["field"] for m in r2["mapping"]} >= {"employee_id", "rating", "store"} and "cycle" not in {m["field"] for m in r2["mapping"]}
    c = api.dispatch("import_commit", {"token": s["token"], "options": {}})
    assert c["done"][0]["results"][0]["status"] == "ok"
    # next month's file with the same titles is set up the same way
    s2 = up(api, {"appraisals Nov.csv": FILES["appraisals.csv"].replace("2025", "2026")})
    r3 = s2["files"][0]["results"][0]
    assert r3.get("remembered") and "cycle" not in {m["field"] for m in r3["mapping"]}


def test_kind_change_and_ai_without_key(api):
    s = up(api, {"exits.csv": FILES["exits.csv"]})
    f = s["files"][0]
    out = api.dispatch("import_remap", {"token": s["token"], "file": f["file"], "sheet": f["results"][0]["sheet"], "kind": "dataset"})
    assert out["file"]["results"][0]["kind"] == "dataset"
    e = api.dispatch("import_ai", {"token": s["token"], "file": f["file"], "sheet": f["results"][0]["sheet"]})
    assert "error" in e


def test_everything_saves_for_the_calendar_month(api):
    s = up(api, FILES, month="2026-09")
    assert all(f["results"] for f in s["files"])
    c = api.dispatch("import_commit", {"token": s["token"], "options": {}})
    st = [x for f in c["done"] for x in f.get("results", [])]
    assert all(x["status"] == "ok" for x in st), st
    cal = api.dispatch("import_calendar", {"year": 2026})
    sep = next(m for m in cal["months"] if m["month"] == "2026-09")
    got = {i["kind"] for i in sep["items"] if i["status"] == "ok"}
    assert {"roster", "po_role", "po_rating", "po_turnover", "po_da", "sales"} <= got
    assert len(cal["months"]) == 12 and cal["guide"]["roster"]
