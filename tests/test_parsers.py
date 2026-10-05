"""Every report parser, on the exact layouts of the real BO / HR reports (names and figures here are made up)."""

import pytest

from pno import importers
from pno.importers.attendance import classify

T = "\t"


def tsv(rows):
    return "\n".join(T.join("" if c is None else str(c) for c in r) for r in rows)


# ------------------------------------------------------------------ biometric attendance (MTD grid)
def attendance_text():
    days = ["1-Aug-26", "2-Aug-26", "3-Aug-26", "4-Aug-26"]
    top = ["Biometric Attendance", "", "", "", "", ""]
    for d in days:
        top += [d, "", ""]
    head = ["Business Unit Name", "Section", "Employee No", "Employeee Name", "Designation", "Joining date"] + ["IN", "OUT", "Total WH"] * 4
    a = ["H&B PK KCH Lucky One          ", "OTH - Common                  ", "20000001", "Test Person One              ",
         "Beauty Advisor", "19/12/2025",
         "15:45:24", "01:21:34", "9:36",          # night shift over midnight
         "Not Marked", "Not Marked", "Absent",
         "15:07:25", "Not Marked", "Absent",      # forgot to punch out
         "11:54:35", "21:01:19", "9:06"]
    b = ["HM PK LAH Fortress", "S014 - Grocery", "20000002", "test person two", "Sales Associate", "01/01/2024",
         "Not Marked", "18:00:00", "Absent",      # forgot to punch in
         "09:00:00", "18:30:00", "Absent",        # both punches but the system said absent
         "", "", "Leave",
         "", "", "8:40"]                           # manual hours
    return tsv([top, head, a, b])


def test_attendance_grid_real_layout():
    a = importers.analyze_text(attendance_text(), "Biometric Attendance MTD.xlsx")
    (r,) = a["results"]
    assert r.kind == "attendance" and r.month == "2026-08"
    rows = {(x["emp_no"], x["day"]): x for x in r.rows}
    one = rows[("20000001", "2026-08-01")]
    assert (one["t_in"], one["t_out"], one["minutes"], one["status"]) == ("15:45", "01:21", 576, "present")
    assert rows[("20000001", "2026-08-02")]["status"] == "no_punch"
    assert rows[("20000001", "2026-08-03")]["status"] == "missing_out"
    assert rows[("20000002", "2026-08-01")]["status"] == "missing_in"
    assert rows[("20000002", "2026-08-02")]["status"] == "punched_absent"
    assert rows[("20000002", "2026-08-03")]["status"] == "sys_leave"
    assert rows[("20000002", "2026-08-04")]["status"] == "manual"
    people = {p["emp_no"]: p for p in r.extra.get("people", [])} if r.extra.get("people") else {}
    if people:
        assert people["20000002"]["name"] == "Test Person Two"


@pytest.mark.parametrize("cells, status", [
    (("08:00:00", "17:05:00", "9:05"), "present"),
    (("Not Marked", "Not Marked", "Absent"), "no_punch"),
    (("08:00:00", "Not Marked", "Absent"), "missing_out"),
    (("", "", "Weekly Off"), "sys_off"),
    (("", "", "Public Holiday"), "sys_holiday"),
])
def test_classify(cells, status):
    assert classify(*cells)[0] == status


# ------------------------------------------------------------------ MTD productivity (repeated store blocks)
PROD = tsv([
    ["Store Name", "Dept/Section", "Store Productivity", "Store Productivity LY", "Target Productivity", "Forecasted Productivity ",
     "v/s Target", "v/s LY", "Forecasted v/s Target Productivity"],
    ["651 LAH Fortress", "00 - Overall Store", "128.2", "127.2012931", "124.8", "126.3", "▲ 3%", "▲ 1%", "▲ 1%"],
    ["651 LAH Fortress", "CCO", "183.1", "189.2396639", "182.4", "176.4", "▬ 0%", "▼ -3%", "▼ -3%"],
    ["651 LAH Fortress", "S054 - Bakery/Pastry", "11.5", "10.95267532", "12.3", "12.0", "▼ -6%", "▲ 5%", "▼ -3%"],
    ["651 LAH Fortress", "S050-S051 Deli & Dairy", "27.3", "25.9461509", "26.1", "26.1", "▲ 4%", "▲ 5%", "▬ 0%"],
    ["651 LAH Fortress", "01-CGD", "630.7", "581.9651188", "578.2", "657.7", "▲ 9%", "▲ 8%", "▲ 14%"],
    ["651 LAH Fortress", "S053 - Fishery", "1.3", "1.104855858", "1.7", "", "▼ -25%", "▲ 16%", "▼ -100%"],
    [""] * 9,
    ["Store Name", "Dept/Section", "Store Productivity", "Store Productivity LY", "Target Productivity", "Forecasted Productivity ",
     "v/s Target", "v/s LY", "Forecasted v/s Target Productivity"],
    ["652 LAH High Street Paragon Ci", "00 - Overall Store", "47.8", "45.71211539", "45.7", "51.8", "▲ 5%", "▲ 4%", "▲ 13%"],
    ["652 LAH High Street Paragon Ci", "Other Store Sections", "58.8", "56.95343055", "56.4", "63.7", "▲ 4%", "▲ 3%", "▲ 13%"],
])


def test_productivity_real_layout_needs_month_without_date():
    a = importers.analyze_text(PROD, "Productivity.xlsx")
    (r,) = a["results"]
    assert r.kind == "productivity" and len(r.rows) == 8
    assert r.month is None and "month" in r.needs
    codes = {(x["store_raw"], x["row_code"]): x for x in r.rows}
    assert codes[("651 LAH Fortress", "STORE")]["actual"] == 128.2
    assert codes[("651 LAH Fortress", "STORE")]["target"] == 124.8
    assert codes[("651 LAH Fortress", "S053")]["forecast"] is None
    assert ("651 LAH Fortress", "CCO") in codes
    assert any(k[1].startswith("S050") for k in codes)          # Deli & Dairy is one section manager's row


def test_productivity_month_from_file_name():
    a = importers.analyze_text(PROD, "MTD Productivity Sep 2026.xlsx")
    assert a["results"][0].month == "2026-09"


def test_productivity_commit_asks_for_month(empty_db):
    a = importers.analyze_text(PROD, "Productivity.xlsx")
    out = importers.commit(empty_db, a)
    assert out[0]["status"] == "needs_month"
    out = importers.commit(empty_db, a, {"*": {"month": "2026-08"}})
    assert out[0]["status"] == "ok"
    assert empty_db.val("SELECT COUNT(*) FROM productivity") == 8


# ------------------------------------------------------------------ BO 200-10-05 Store Net Sales
def bo_text():
    hdr1 = ["Section Code Name", "Net Sales", "", "", "", "", "", "Section Weight", "", "Customer", "", "Pent. Rate", "Item", "",
            "Avg Basket", "", "Avg Selling Price", "", "Margin %", "", "", "Avg Stock", "Out of Stock %"]
    hdr2 = ["", "Actual", "Forecast", "Budget", "Gth %", "Var FCT %", "Var %", " in Store", "in Cntry", "Cust", "Gth %", "",
            "Actual", "Gth %", "Actual", "Gth %", "Actual", "Gth %", "NetMrg", "Waste ", "NetMrg-Wst", "", ""]

    def row(name, actual, budget, gth, var, waste, oos):
        return [name, actual, "0", budget, gth, "0.0%", var, "24.2%", "5.4%", "2,270", "(5.8%)", "38.6%", "29,330", "(3.8%)",
                "5,676.3", "(10.0%)", "439.3", "(11.8%)", "(8.3%)", waste, "(8.3%)", "41,982,219", oos]
    block = [
        ["Report Name: 200-10-05-Country Periodic Store Performance Report", "", "", "", "", "Currency:  LOCAL CURR - MTD", "", "", "",
         "Net Sales of: (Fri) 02-Oct-26", "", "", "Run By: someone"],
        ["Store Name: HM PK LAH Fortress", "", "", "", "", "Report Period : 01/10/2026 - 02/10/2026", "", "", "",
         "Compare With: (Fri) 03-Oct-25", "", "", "Run Time: 03/10/2026 8:58:47 AM"],
        [""], hdr1, hdr2,
        row("S011 - Beverages", "1,000,000", "800,000", "(15.2%)", "25.0%", "0.0%", "10.6%"),
        row("S014 - Grocery [Dry Food]", "2,000,000", "2,500,000", "9.8%", "(20.0%)", "0.1%", "12.6%"),
        row("CGD-FMG", "3,000,000", "3,300,000", "0.1%", "(9.1%)", "0.1%", "11.6%"),
        row("Consumer Goods", "3,000,000", "3,300,000", "(2.8%)", "(9.1%)", "0.1%", "12.6%"),
        row("S054 - Bakery/Pastry", "471,327", "410,868", "30.8%", "14.7%", "3.2%", "0.0%"),
        row("S050 - Dairy", "100,000", "0", "5.0%", "0.0%", "1.0%", "2.0%"),
        row("Fresh Food", "571,327", "410,868", "5.4%", "39.1%", "2.9%", "1.0%"),
        row("z", "571,327", "410,868", "5.4%", "39.1%", "2.9%", "1.0%"),
        row("Total Store", "3,571,327", "3,710,868", "1.0%", "(3.8%)", "0.5%", "10.0%"),
        row("Total Hypermarket", "3,600,000", "3,710,868", "1.0%", "(3.0%)", "0.5%", "10.0%"),
    ]
    return tsv(block)


def test_bo_sales_real_layout():
    a = importers.analyze_text(bo_text(), "200-10-05 Country Performance.xlsx")
    (r,) = a["results"]
    assert r.kind == "sales" and r.as_of == "2026-10-02" and r.month == "2026-10"
    by = {x["code"]: x for x in r.rows}
    assert by["S011"]["actual"] == 1_000_000 and by["S011"]["budget"] == 800_000
    assert by["S011"]["growth"] == -15.2 and by["S011"]["oos"] == 10.6
    assert by["S011"]["dept"] == "01" and by["S054"]["dept"] == "02"
    assert by["D01"]["level"] == "dept" and by["D02"]["level"] == "dept"
    assert by["STORE"]["actual"] == 3_571_327          # the report's own Total Store row, not a re-sum
    assert by["S050"]["var_pct"] is None              # no budget → no variance (never a fake 0%)
    assert all(x["period"] == "MTD" for x in r.rows)
    assert not any(x["name"].lower() == "z" for x in r.rows)
    assert by["S011"]["ly"] == pytest.approx(1_000_000 / (1 - 0.152), rel=1e-3)


# ------------------------------------------------------------------ roster and leave
def test_roster_and_leave_demo(demo):
    a = importers.analyze_bytes(demo.files["Employee Basic Details.xlsx"], "Employee Basic Details.xlsx")
    (r,) = a["results"]
    assert r.kind == "roster" and len(r.rows) == len(demo.people)
    assert "as_of" in r.needs
    first = r.rows[0]
    assert first["dept_code"] == "99" and first["dept_name"] == "Services"
    lv = importers.analyze_bytes(demo.files["Leave Register Aug 2026.xlsx"], "Leave Register Aug 2026.xlsx")
    (lr,) = lv["results"]
    assert lr.kind == "leave" and lr.warnings          # rejected requests are left out and reported


def test_roster_text_with_duplicates():
    text = tsv([
        ["Business Unit", "Department", "Section", "Employee Number", "Employee Name", "Designation ", "Grade", "Gender",
         "Reporting Manager "],
        ["HM PK LAH Fortress", "02:Fresh Food", "S054 - Bakery", "20000010", "AMNA TEST", "Section Manager", "9", "Female", "Boss Person"],
        ["HM PK LAH Fortress", "02:Fresh Food", "S054 - Bakery", "20000010", "AMNA TEST", "Section Manager", "9", "Female", "Boss Person"],
    ])
    (r,) = importers.analyze_text(text, "roster.csv")["results"]
    assert len(r.rows) == 1 and r.rows[0]["name"] == "Amna Test" and r.rows[0]["grade"] == "09"


def test_every_demo_file_is_recognised(demo):
    kinds = {}
    for name, data in demo.files.items():
        a = importers.analyze_bytes(data, name)
        assert a["results"], name
        kinds.setdefault(a["results"][0].kind, 0)
        kinds[a["results"][0].kind] += 1
    assert kinds == {"roster": 1, "leave": 2, "attendance": 2, "productivity": 2, "sales": 2}


def test_unknown_file_is_skipped_not_guessed():
    a = importers.analyze_text("fruit,price\napple,3\npear,4\n", "fruit.csv")
    assert a["results"] == [] and a["skipped"]


# ------------------------------------------------------------------ commit, duplicates, undo / redo
def test_commit_duplicate_undo_redo(empty_db):
    text = attendance_text()
    a = importers.analyze_text(text, "att.xlsx")
    (first,) = importers.commit(empty_db, a)
    assert first["status"] == "ok"
    assert importers.commit(empty_db, importers.analyze_text(text, "att.xlsx"))[0]["status"] == "duplicate"
    n = empty_db.val("SELECT COUNT(*) FROM attendance")
    assert n == 8
    importers.undo(empty_db, first["import_id"])
    assert empty_db.val("SELECT COUNT(*) FROM attendance") == 0
    importers.redo(empty_db, first["import_id"])
    assert empty_db.val("SELECT COUNT(*) FROM attendance") == 8


def test_newer_attendance_file_wins_per_day(empty_db):
    importers.commit(empty_db, importers.analyze_text(attendance_text(), "att.xlsx"))
    newer = attendance_text().replace("Not Marked\tNot Marked\tAbsent\t15:07:25", "09:00:00\t18:10:00\t9:10\t15:07:25", 1)
    importers.commit(empty_db, importers.analyze_text(newer, "att2.xlsx"))
    row = empty_db.q1("SELECT status, minutes FROM attendance WHERE emp_no='20000001' AND day='2026-08-02'")
    assert (row["status"], row["minutes"]) == ("present", 550)
    assert empty_db.val("SELECT COUNT(*) FROM attendance") == 8
