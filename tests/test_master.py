"""6.0: the master sheet — one upload with everything the Review needs."""
import os

import pytest

from pno import master
from pno.api import Api
from pno.db import Database
from pno.reader import Sheet, from_text

HEAD = ["Sr", "Employee No", "Employee Name", "DOJ", "Grade", "BU", "Section", "Designation", "Sales vs bud.", "Productvity", "Shrink",
        "Stock days", "Leavers", "DA cases", "NPS", "Rating"]
ROWS = [
    ["#VALUE!", "70000001", "Test Store Lead A   ", "6/6/2023", "14", "HM PK FAI Lyallpur Galleria   ", "MGM - Management", "Store Manager", "-37.7%", "▲ 16%", "", "", "7", "3", "62", "0"],
    ["#VALUE!", "70000002", "Test Dept Head B", "8/16/2021", "13", "HM PK LAH Fortress", "CGD - FMCG (Common)", "Department Head", "6.5%", "▲ 8%", "0.02%", "100%", "2", "0", "38", "3"],
    ["1", "70000003", "Test Section C", "5/2/2016", "12", "HM PK LAH Fortress", "FFD - Bakery", "Section Manager", "10.0%", "▼ -6%", "10.50%", "93%", "7", "0", "76", "3"],
    ["2", "70000004", "Test Leader D", "9/13/2023", "1", "HM PK LAH Fortress", "CGD - DPH", "Team Leader", "(15.2%)", "", "-0.01%", "130%", "2", "1", "80", "—"],
    ["3", "70000005", "Test Leader E", "1/3/2024", "12", "SM PK LAH ASKARI 10", "MGM - Management", "Store Manager", "9.9%", "▲ 1%", "", "", "6", "#N/A", "#N/A", "#N/A"],
    ["4", "70000006", "Test Leader F", "3/1/2022", "11", "HM PK LAH Fortress", "FFD - Butchery", "Section Manager", "(10.0%)", "▼ -3%", "0.67%", "129%", "3", "0", "—", "4"],
    ["5", "70000007", "Test SM G", "4/18/2022", "17", "HM PK LAH Fortress", "MGM - Management", "Store Manager", "-4.7%", "▲ 2%", "", "", "24", "2", "57", "0"],
]


def tsv(rows=ROWS):
    return "\n".join("\t".join(r) for r in [HEAD, *rows])


def test_values_read_as_shown():
    r = master.parse(from_text(tsv()).sheets[0])
    assert len(r["rows"]) == 7 and not r["missing_columns"]
    a, b, c, d, e = r["rows"][:5]
    assert a["store"] == "FAI Lyallpur Galleria" and a["level"] == 6 and a["sales"] == -37.7 and a["productivity"] == 16 and a["rating"] is None
    assert d["sales"] == -15.2 and d["productivity"] is None and d["shrink"] == -0.01 and d["stock_days"] == 130 and d["rating"] is None
    assert c["productivity"] == -6 and c["section"] == "Bakery" and c["department"] == "Fresh Food" and c["doj"] == "2016-05-02"
    assert e["store"] == "LAH Askari 10" and e["format"] == "Supermarket" and e["da"] is None and e["nps"] is None


def test_excel_fractions_become_percentages():
    rows = [[*HEAD]] + [["1", "70000001", "X", "", "", "HM PK LAH Fortress", "FFD - Bakery", "Section Manager", -0.152, 0.03, 0.105, 0.93, 1, 0, 50, 3],
                        ["2", "70000002", "Y", "", "", "HM PK LAH Fortress", "FFD - Butchery", "Section Manager", 0.02, -0.06, -0.0001, 1.3, 0, 0, 40, 4]]
    r = master.parse(Sheet("S", rows))
    x, y = r["rows"]
    assert x["sales"] == -15.2 and x["productivity"] == 3 and x["shrink"] == 10.5 and x["stock_days"] == 93
    assert y["shrink"] == -0.01 and y["stock_days"] == 130 and set(r["scaled"]) >= {"Sales vs bud.", "Stock days"}


def test_coverage_lists_what_is_missing():
    cov = master.coverage(master.parse(from_text(tsv()).sheets[0])["rows"])
    m = {x["key"]: x for x in cov["measures"]}
    assert m["rating"]["filled"] == 3 and m["shrink"]["filled"] == 4                               # 0, — and #N/A are not filled
    assert any(g["emp"] == "70000005" and "NPS" in g["missing"] for g in cov["gaps"])


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    return Api(Database(tmp_path / "m.sqlite3"))


def test_upload_check_save_and_periods(api):
    r = api.dispatch("master_read", {"period_type": "ytd", "month": "2026-09", "text": tsv()})
    assert r["status"] in ("good", "warn") and r["label"] == "YTD Jan–Sep 2026" and r["token"]
    api.dispatch("master_save", {"token": r["token"]})
    m = api.dispatch("master_read", {"period_type": "mtd", "month": "2026-10", "text": tsv(ROWS[:5])})
    api.dispatch("master_save", {"token": m["token"]})
    rv = api.dispatch("review", {})
    assert rv["period_label"] == "Oct 2026 (MTD)" and len(rv["people"]) == 5
    api.dispatch("po_view", {"type": "ytd", "to": "2026-09"})
    rv = api.dispatch("review", {})
    assert rv["period_label"] == "YTD Jan–Sep 2026" and len(rv["people"]) == 7
    assert [s["label"] for s in rv["period"]["slots"]] == ["YTD Jan–Sep 2026", "Oct 2026 (MTD)"]
    # a better-filled sheet for the same period replaces the old one
    full = [r_[:15] + ["3"] for r_ in ROWS]
    m2 = api.dispatch("master_read", {"period_type": "ytd", "month": "2026-09", "text": tsv(full)})
    assert any("replaces" in c["text"] for c in m2["checks"])
    api.dispatch("master_save", {"token": m2["token"]})
    api.dispatch("po_view", {"type": "ytd", "to": "2026-09"})
    h = api.dispatch("master_health", {})
    assert next(x for x in h["measures"] if x["key"] == "rating")["pct"] == 100
    lst = api.dispatch("master_list", {})["rows"]
    assert sum(1 for x in lst if x["active"]) == 2 and any(not x["active"] for x in lst)


def test_review_numbers_come_from_the_owners(api):
    r = api.dispatch("master_read", {"period_type": "ytd", "month": "2026-09", "text": tsv()})
    api.dispatch("master_save", {"token": r["token"]})
    s = api.dispatch("review", {"store": "LAH Fortress"})
    tiles = {t["key"]: t["value"] for t in s["tiles"]}
    assert tiles["sales"] == -4.7 and tiles["leavers"] == 24                                   # the store manager's row
    assert tiles["shrink"] is not None                                                          # not on his row: from the departments below
    ff = api.dispatch("review", {"store": "LAH Fortress", "dept": "Fresh Food"})
    assert {g["name"] for g in ff["grid"]} == {"Bakery", "Butchery"} and ff["tiles"]
    cg = api.dispatch("review", {"store": "LAH Fortress", "dept": "Consumer Goods"})
    assert next(t["value"] for t in cg["tiles"] if t["key"] == "sales") == 6.5                 # the department head's row
    p = api.dispatch("review_person", {"key": "70000004"})
    assert p["facts"]["Grade"] == "1" and p["row"]["cells"][0]["value"] == -15.2


def test_bad_sheet_is_refused(api):
    r = api.dispatch("master_read", {"period_type": "ytd", "month": "2026-09", "text": "Name\tScore\nA\t1\n"})
    assert r["status"] == "bad" and not r["token"]
