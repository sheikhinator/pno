from __future__ import annotations

import csv

from pno.analysis import analyze, export_report


class MemoryStore:
    def __init__(self, records=None, employees=None):
        self.data = records or []
        self.roster = employees or []

    def records(
        self,
        kind=None,
        period_from=None,
        period_to=None,
        store=None,
        department=None,
        section=None,
        employee=None,
    ):
        result = []
        for row in self.data:
            if kind and row.get("_kind") != kind:
                continue
            period = str(row.get("date") or row.get("_period") or "")
            if period_from and period[:10] < str(period_from)[:10]:
                continue
            if period_to and period[:10] > str(period_to)[:10]:
                continue
            if store and row.get("store") != store:
                continue
            if department and row.get("department") != department:
                continue
            if section and row.get("section") != section:
                continue
            if employee and row.get("employee_id") != employee:
                continue
            result.append(dict(row))
        return result

    def employees(self, period=None):
        eligible = []
        for person in self.roster:
            snapshot = str(person.get("_period") or "")
            if period and snapshot and snapshot[:10] > str(period)[:10]:
                continue
            eligible.append(dict(person))
        latest = {}
        for person in eligible:
            identity = str(person.get("employee_id") or person.get("employee_code") or person.get("employee_name"))
            prior = latest.get(identity)
            if prior is None or str(person.get("_period") or "") > str(prior.get("_period") or ""):
                latest[identity] = person
        return list(latest.values())


def rec(kind, period, **values):
    return {
        "_kind": kind,
        "_period": period,
        "_import_id": f"{kind}-{period}",
        "_source": "local.xlsx",
        "_sheet": "Sheet1",
        **values,
    }


def test_mtd_uses_latest_monthly_scope_snapshot_and_trends_do_not_sum_snapshots():
    store = MemoryStore([
        rec("sales_mtd", "2025-01-10", store="A", actual=100, budget=200, last_year=80),
        rec("sales_mtd", "2025-01-20", store="A", actual=180, budget=200, last_year=150),
        rec("sales_mtd", "2025-02-08", store="A", actual=90, budget=100, last_year=75),
    ])
    result = analyze(store)
    assert result["metrics"]["actual"] == 270
    assert result["metrics"]["budget"] == 300
    assert [trend["actual"] for trend in result["trends"]] == [180, 90]
    assert len(result["rows"]) == 2
    assert any("latest available snapshot per month" in warning for warning in result["warnings"])


def test_summary_rows_prevent_detail_double_counting():
    store = MemoryStore([
        rec("sales_daily", "2025-03-01", date="2025-03-01", store="A", actual=500, budget=600, last_year=450),
        rec("sales_daily", "2025-03-01", date="2025-03-01", store="A", department="D1", actual=200, budget=300, last_year=180),
        rec("sales_daily", "2025-03-01", date="2025-03-01", store="A", department="D2", actual=300, budget=300, last_year=270),
    ])
    result = analyze(store, {"kind": "sales_daily"})
    assert result["metrics"]["actual"] == 500
    assert len(result["rows"]) == 1
    assert result["trends"][0]["kind"] == "sales_daily"


def test_hierarchy_collapse_is_partitioned_by_daily_observation_date():
    store = MemoryStore([
        rec("sales_daily", "2025-03-01", date="2025-03-01", store="A", actual=100, budget=100, last_year=80),
        rec("sales_daily", "2025-03-02", date="2025-03-02", store="A", department="D1", actual=50, budget=60, last_year=40),
    ])
    result = analyze(store, {"kind": "sales_daily"})
    assert result["metrics"]["actual"] == 150
    assert len(result["rows"]) == 2


def test_distinct_totals_at_same_grain_and_snapshot_are_preserved():
    store = MemoryStore([
        rec("sales_mtd", "2025-03-01", store="A", actual=100, budget=100, last_year=80),
        rec("sales_mtd", "2025-03-05", store="A", actual=100, budget=100, last_year=80),
        rec("sales_mtd", "2025-03-05", store="A", actual=200, budget=200, last_year=160),
    ])
    result = analyze(store)
    assert result["metrics"]["actual"] == 300
    assert len(result["rows"]) == 2


def test_mtd_older_summary_is_retained_instead_of_summing_newer_partial_detail():
    store = MemoryStore([
        rec("sales_mtd", "2025-03-01", store="A", actual=100, budget=100, last_year=80),
        rec("sales_mtd", "2025-03-02", store="A", department="D1", actual=50, budget=60, last_year=40),
    ])
    result = analyze(store)
    assert result["metrics"]["actual"] == 100
    assert [trend["actual"] for trend in result["trends"]] == [100]
    assert len(result["rows"]) == 1
    assert any("older covering summary was retained" in warning for warning in result["warnings"])


def test_mtd_newer_covering_store_snapshot_replaces_older_department_snapshot():
    store = MemoryStore([
        rec("sales_mtd", "2025-08-10", store="A", department="D1", actual=100, budget=120, last_year=80),
        rec("sales_mtd", "2025-08-20", store="A", actual=200, budget=220, last_year=180),
    ])
    result = analyze(store)
    assert result["metrics"]["actual"] == 200
    assert [trend["actual"] for trend in result["trends"]] == [200]
    assert len(result["rows"]) == 1
    assert not any("coverage cannot be verified" in warning for warning in result["warnings"])


def test_country_scope_filters_and_country_summary_prevents_store_overlap():
    store = MemoryStore([
        rec("sales_mtd", "2025-03-01", country="Exampleland", actual=100, budget=120, last_year=80),
        rec("sales_mtd", "2025-03-01", country="Exampleland", store="North", actual=60, budget=70, last_year=50),
        rec("sales_mtd", "2025-03-01", country="Exampleland", store="South", actual=40, budget=50, last_year=30),
        rec("sales_mtd", "2025-03-01", country="Elsewhere", store="West", actual=999, budget=1000, last_year=900),
    ])
    result = analyze(store, {"country": "Exampleland"})
    assert result["metrics"]["actual"] == 100
    assert len(result["rows"]) == 1


def test_attendance_exclusions_denominator_and_no_shift_assumption():
    records = [
        rec("attendance", "2025-04-01", date="2025-04-01", store="A", employee_id="1", status="Present", hours=8),
        rec("attendance", "2025-04-01", date="2025-04-01", store="A", employee_id="2", status="Absent"),
        rec("attendance", "2025-04-01", date="2025-04-01", store="A", employee_id="3", status="Approved Leave"),
        rec("attendance", "2025-04-01", date="2025-04-01", store="A", employee_id="4", status="Day Off"),
        rec("attendance", "2025-04-01", date="2025-04-01", store="A", employee_id="5", status="Not Marked"),
    ]
    result = analyze(MemoryStore(records), {"kind": "sales_daily"})
    assert result["metrics"]["attendance_rate_pct"] == 50
    assert result["metrics"]["actual"] is None
    assert any("excludes 3" in warning for warning in result["warnings"])
    assert any("No scheduled-shift assumption" in warning for warning in result["warnings"])


def test_attendance_absent_ab_and_duplicates_or_unknown_statuses_are_warned():
    records = [
        rec("attendance", "2025-04-02", date="2025-04-02", store="A", employee_id="1", status="P"),
        rec("attendance", "2025-04-02", date="2025-04-02", store="A", employee_id="2", status="AB"),
        rec("attendance", "2025-04-02", date="2025-04-02", store="A", employee_id="3", status="mystery"),
        rec("attendance", "2025-04-02", date="2025-04-02", store="A", employee_id="4", status="P"),
        rec("attendance", "2025-04-02", date="2025-04-02", store="A", employee_id="4", status="P"),
    ]
    result = analyze(MemoryStore(records), {"kind": "sales_daily"})
    assert result["metrics"]["attendance_rate_pct"] == 50
    assert any("unknown or partial-day status" in warning for warning in result["warnings"])
    assert any("duplicate employee/date groups" in warning for warning in result["warnings"])


def test_unknown_denominators_are_unavailable_and_oos_is_not_aggregated():
    store = MemoryStore([
        rec("sales_daily", "2025-05-01", date="2025-05-01", store="A", department="D1", actual=10, budget=None, last_year=5, oos_pct=4),
        rec("sales_daily", "2025-05-01", date="2025-05-01", store="A", department="D2", actual=20, budget=30, last_year=10, oos_pct=6),
    ])
    result = analyze(store, {"kind": "sales_daily"})
    assert result["metrics"]["actual"] == 30
    assert result["metrics"]["budget"] is None
    assert result["metrics"]["budget_achievement_pct"] is None
    assert result["metrics"]["oos_pct"] is None
    assert any("weighting denominator" in warning for warning in result["warnings"])


def test_manager_scope_comes_from_as_of_roster_and_ordinary_employee_has_no_sales():
    roster = [
        {"employee_id": "GM1", "employee_name": "Store Lead", "designation": "GM", "store": "A"},
        {"employee_id": "DH1", "employee_name": "Dept Lead", "designation": "DH", "store": "A", "department": "D1"},
        {"employee_id": "SM1", "employee_name": "Section Lead", "designation": "SM", "store": "A", "department": "D1", "section": "S1"},
        {"employee_id": "E1", "employee_name": "Staff", "designation": "Associate", "store": "A", "department": "D1", "section": "S1"},
        {"employee_id": "E2", "manager_id": "DH1", "store": "A", "department": "D1"},
    ]
    sales = [
        rec("sales_mtd", "2025-06-01", store="A", department="D1", section="S1", actual=10, budget=20, last_year=8),
        rec("sales_mtd", "2025-06-01", store="A", department="D2", section="S2", actual=50, budget=60, last_year=40),
    ]
    gm = analyze(MemoryStore(sales, roster), {"employee": "GM1"})
    dh = analyze(MemoryStore(sales, roster), {"employee": "DH1"})
    ordinary = analyze(MemoryStore(sales, roster), {"employee": "E1"})
    assert gm["metrics"]["actual"] == 60
    assert dh["metrics"]["actual"] == 10
    assert dh["metrics"]["direct_reports"] == 1
    assert ordinary["metrics"]["actual"] is None
    assert any("GM, DH, or SM responsibility" in warning for warning in ordinary["warnings"])
    mismatch = analyze(MemoryStore(sales, roster), {"employee": "DH1", "department": "D2"})
    assert mismatch["metrics"]["actual"] is None
    assert any("outside" in warning for warning in mismatch["warnings"])


def test_manager_scope_fails_closed_when_required_assignment_is_missing():
    roster = [
        {"employee_id": "GM1", "employee_name": "Store Lead", "designation": "GM", "store": ""},
    ]
    sales = [
        rec("sales_mtd", "2025-06-01", store="A", actual=100, budget=100, last_year=80),
        rec("sales_mtd", "2025-06-01", store="B", actual=200, budget=200, last_year=150),
    ]
    result = analyze(MemoryStore(sales, roster), {"employee": "GM1"})
    assert result["metrics"]["actual"] is None
    assert result["rows"] == []
    assert any("has no store" in warning and "fails closed" in warning for warning in result["warnings"])


def test_manager_assignment_is_resolved_as_of_each_daily_observation():
    roster = [
        {"employee_id": "GM1", "designation": "GM", "store": "A", "_period": "2025-01-01"},
        {"employee_id": "GM1", "designation": "GM", "store": "B", "_period": "2025-01-10"},
    ]
    sales = [
        rec("sales_daily", "2025-01-05", date="2025-01-05", store="A", actual=10, budget=10, last_year=8),
        rec("sales_daily", "2025-01-05", date="2025-01-05", store="B", actual=100, budget=100, last_year=80),
        rec("sales_daily", "2025-01-15", date="2025-01-15", store="A", actual=200, budget=200, last_year=160),
        rec("sales_daily", "2025-01-15", date="2025-01-15", store="B", actual=20, budget=20, last_year=16),
    ]
    result = analyze(
        MemoryStore(sales, roster),
        {"kind": "sales_daily", "employee": "GM1", "period_from": "2025-01-01", "period_to": "2025-01-31"},
    )
    assert result["metrics"]["actual"] == 30
    assert {row["store"] for row in result["rows"]} == {"A", "B"}


def test_score_is_provisional_and_never_authoritative():
    result = analyze(MemoryStore())
    assert result["score"]["status"] == "PROVISIONAL"
    assert result["score"]["score"] is None
    assert result["score"]["authoritative"] is False
    assert all(value is None for value in result["metrics"].values())


def test_csv_export_includes_filters_warnings_provenance_and_trends(tmp_path):
    result = analyze(MemoryStore([
        rec("sales_daily", "2025-07-02", date="2025-07-02", store="A", actual=5, budget=10, last_year=4),
    ]), {"kind": "sales_daily", "store": "A"})
    path = export_report(result, tmp_path / "report.csv", "csv", {"store": "A"})
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    flattened = "\n".join(",".join(row) for row in rows)
    assert "Filters" in flattened
    assert "Warning" in flattened
    assert "local.xlsx" in flattened
    assert "trend_period" in flattened


def test_xlsx_and_pdf_exports_are_written_when_export_libraries_are_available(tmp_path):
    import pytest

    openpyxl = pytest.importorskip("openpyxl")
    reportlab = pytest.importorskip("reportlab")
    result = analyze(MemoryStore([
        rec("sales_daily", "2025-07-02", date="2025-07-02", store="A", actual=5, budget=10, last_year=4),
    ]), {"kind": "sales_daily", "store": "A"})
    workbook_path = export_report(result, tmp_path / "report.xlsx", "xlsx", {"store": "A"})
    workbook = openpyxl.load_workbook(workbook_path, read_only=True)
    overview = list(workbook["Overview"].values)
    workbook.close()
    overview_text = "\n".join(str(value) for row in overview for value in row)
    assert "Filters" in overview_text
    assert "Warning" in overview_text
    assert "2025-07-02" in overview_text
    assert "local.xlsx" in overview_text

    pdf_path = export_report(result, tmp_path / "report.pdf", "pdf", {"store": "A"})
    assert pdf_path.is_file() and pdf_path.stat().st_size > 0


def test_xlsx_sources_and_other_strings_are_literal_not_formulas(tmp_path):
    import pytest

    openpyxl = pytest.importorskip("openpyxl")
    result = analyze(MemoryStore([
        rec(
            "sales_daily",
            "2025-07-02",
            date="2025-07-02",
            store="A",
            actual=5,
            budget=10,
            last_year=4,
            _source="=1+1",
            _sheet="@SUM(1,1)",
        ),
    ]), {"kind": "sales_daily"})
    path = export_report(result, tmp_path / "literal.xlsx", "xlsx")
    workbook = openpyxl.load_workbook(path, data_only=False)
    sources = workbook["Sources"]
    source_column = [cell.value for cell in sources[1]].index("source") + 1
    sheet_column = [cell.value for cell in sources[1]].index("sheet") + 1
    assert sources.cell(2, source_column).value == "=1+1"
    assert sources.cell(2, source_column).data_type == "s"
    assert sources.cell(2, sheet_column).value == "@SUM(1,1)"
    assert sources.cell(2, sheet_column).data_type == "s"
    workbook.close()


def test_csv_formula_leading_report_strings_are_neutralized(tmp_path):
    unsafe = {
        "metrics": {},
        "commentary": ["=1+1"],
        "warnings": ["+SUM(1,1)"],
        "sources": [],
    }
    path = export_report(unsafe, tmp_path / "unsafe.csv", "csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert ["Commentary 1", "'=1+1"] in rows
    assert ["Warning 1", "'+SUM(1,1)"] in rows