import csv

import pytest

from pno.importer import scan_workbook


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(rows)
    return path


def test_roster_header_mapping_and_provenance(tmp_path):
    path = write_csv(
        tmp_path / "roster.csv",
        [
            [
                "Business Unit", "Department", "Section", "Employee Number",
                "Employee Name", "Designation", "Grade", "Gender",
                "Reporting Manager", "Reporting Manager Employee Number",
                "Custom Flag",
            ],
            [
                "North", "Operations", "Floor", "E-001", "Avery Example",
                "Supervisor", "G5", "F", "Morgan Example", "M-01", "kept",
            ],
        ],
    )

    plan = scan_workbook(path, period="2025-01")

    assert len(plan.candidates) == 1
    candidate = plan.candidates[0]
    assert candidate.kind == "roster"
    assert candidate.header_row == 1
    record = candidate.records[0]
    assert record["store"] == "North"
    assert record["employee_id"] == "E-001"
    assert record["manager_id"] == "M-01"
    assert record["manager_name"] == "Morgan Example"
    assert record["raw"]["Custom Flag"] == "kept"
    assert record["_provenance"]["row"] == 2
    assert len(plan.checksum) == 64


def test_body_values_that_look_like_aliases_do_not_become_new_headers(tmp_path):
    path = write_csv(
        tmp_path / "three_people.csv",
        [
            [
                "Employee Number", "Employee Name", "Department", "Designation",
                "Grade", "Gender", "Reporting Manager",
                "Reporting Manager Employee Number",
            ],
            ["E-01", "Avery Example", "Sales", "Store Manager", "G5", "F", "Morgan", "M-01"],
            ["E-02", "Casey Example", "Operations", "Store Manager", "G4", "F", "Morgan", "M-01"],
            ["E-03", "Jordan Example", "Service", "Store Manager", "G3", "M", "Taylor", "M-02"],
        ],
    )

    plan = scan_workbook(path)

    assert len(plan.candidates) == 1
    candidate = plan.candidates[0]
    assert candidate.kind == "roster"
    assert candidate.header_row == 1
    assert [record["employee_id"] for record in candidate.records] == ["E-01", "E-02", "E-03"]
    assert [record["department"] for record in candidate.records] == ["Sales", "Operations", "Service"]


def test_daily_sales_header_row_and_actual_last_year_values_are_not_shifted(tmp_path):
    path = write_csv(
        tmp_path / "fictional_sales.csv",
        [
            ["FICTIONAL TRAINING REPORT"],
            [],
            [
                "Store", "Department", "Section", "Date", "Actual Sales",
                "Budget", "Last Year Sales", "OOS Value", "OOS %",
            ],
            ["Training Store A", "Fresh Food", "Bakery", "2026-08-01", 920, 1000, 880, 20, "2%"],
            ["Training Store A", "Fresh Food", "Bakery", "2026-08-02", 1040, 1000, 910, 10, "1%"],
        ],
    )

    plan = scan_workbook(path)

    assert len(plan.candidates) == 1
    candidate = plan.candidates[0]
    assert candidate.header_row == 3
    assert candidate.kind == "sales_daily"
    assert len(candidate.records) == 2
    assert candidate.records[1]["actual"] == 1040
    assert candidate.records[1]["last_year"] == 910


def test_wide_attendance_keeps_statuses_zero_and_overnight_times(tmp_path):
    path = tmp_path / "attendance.tsv"
    path.write_text(
        "Employee Number\tEmployee Name\tDepartment\t1 IN\t1 OUT\t1 Total WH\t"
        "2 IN\t2 OUT\t2 Total WH\t2 Status\n"
        "E-10\tCasey Example\tRetail\t21:00\t05:00\t0\t\t\t\tWO\n",
        encoding="utf-8",
    )

    candidate = scan_workbook(path, period="2025-02").candidates[0]

    assert candidate.kind == "attendance"
    assert len(candidate.records) == 2
    first, second = candidate.records
    assert first["date"] == "2025-02-01"
    assert first["in_time"] == "21:00"
    assert first["out_time"] == "05:00"
    assert first["hours"] == 0
    assert "overnight" in " ".join(candidate.warnings).lower()
    assert second["date"] == "2025-02-02"
    assert second["status"] == "WO"
    assert "status" not in first


def test_status_only_month_grid_preserves_distinct_tokens(tmp_path):
    path = write_csv(
        tmp_path / "statuses.csv",
        [
            ["Employee Number", "Employee Name", "1", "2", "3"],
            ["E-11", "Taylor Example", "P", "A", "PH"],
        ],
    )

    candidate = scan_workbook(path, period="2025-04").candidates[0]

    assert candidate.kind == "attendance"
    assert [record["status"] for record in candidate.records] == ["P", "A", "PH"]
    assert [record["date"] for record in candidate.records] == [
        "2025-04-01", "2025-04-02", "2025-04-03"
    ]


def test_month_name_day_headers_keep_their_month_and_warn_on_period_mismatch(tmp_path):
    path = write_csv(
        tmp_path / "named_month.csv",
        [
            ["Employee Number", "Employee Name", "1-Jan IN", "1-Jan OUT", "1-Jan Total WH"],
            ["E-12", "Riley Example", "09:00", "17:00", "8"],
        ],
    )

    candidate = scan_workbook(path, period="2025-02").candidates[0]

    assert candidate.records[0]["date"] == "2025-01-01"
    assert any("differs from selected period" in warning for warning in candidate.warnings)


def test_impossible_and_unresolved_month_name_dates_are_not_silently_replaced(tmp_path):
    impossible = write_csv(
        tmp_path / "impossible.csv",
        [
            ["Employee Number", "Employee Name", "31-Feb Status"],
            ["E-13", "Sam Example", "A"],
        ],
    )
    impossible_candidate = scan_workbook(impossible, period="2025-02").candidates[0]
    assert impossible_candidate.records == []
    assert any("Impossible attendance date" in warning for warning in impossible_candidate.warnings)

    unresolved = write_csv(
        tmp_path / "unresolved.csv",
        [
            ["Employee Number", "Employee Name", "1-Jan Status"],
            ["E-14", "Lee Example", "PH"],
        ],
    )
    unresolved_candidate = scan_workbook(unresolved).candidates[0]
    assert unresolved_candidate.records[0]["date"] is None
    assert unresolved_candidate.records[0]["status"] == "PH"
    assert any("Unresolved attendance date" in warning for warning in unresolved_candidate.warnings)


def test_unknown_file_can_be_manually_classified_and_mapping_overrides_win(tmp_path):
    path = write_csv(
        tmp_path / "custom.csv",
        [["Identifier", "Value"], ["row-1", "0"]],
    )
    # A generic schema is deliberately not inferred as a production kind.
    plan = scan_workbook(path)
    assert plan.candidates[0].kind == "unknown"
    assert "Identifier" in plan.candidates[0].records[0]["raw"]

    manual = scan_workbook(
        path,
        kind="sales_daily",
        mappings={"Identifier": "store", "Value": "actual"},
    )
    record = manual.candidates[0].records[0]
    assert manual.candidates[0].kind == "sales_daily"
    assert record["store"] == "row-1"
    assert record["actual"] == 0


def test_multiple_tables_and_summary_exclusion_keeps_department_aggregate(tmp_path):
    path = write_csv(
        tmp_path / "reports.csv",
        [
            ["Department", "Actual Sales", "Budget"],
            ["Shoes", "120", "100"],
            ["TOTAL", "120", "100"],
            ["Grand Total", "120", "100"],
            [],
            ["Department", "Actual Sales", "Budget"],
            ["Apparel", "80", "90"],
        ],
    )
    plan = scan_workbook(path)

    assert len(plan.candidates) == 2
    assert [row["department"] for row in plan.candidates[0].records] == ["Shoes", "TOTAL"]
    assert [row["department"] for row in plan.candidates[1].records] == ["Apparel"]
    assert any("summary row" in warning for warning in plan.candidates[0].warnings)


def test_xlsx_merged_attendance_headers_and_percentage_points(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "monthly.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Attendance"
    sheet.append(["Employee Number", "Employee Name", "Department", "OOS %", 1, None, None])
    sheet.merge_cells(start_row=1, start_column=5, end_row=1, end_column=7)
    sheet.append([None, None, None, None, "IN", "OUT", "Total WH"])
    sheet.append(["E-20", "Jordan Example", "Service", 0.05, "09:00", "17:00", 0])
    sheet["D3"].number_format = "0.00%"
    workbook.save(path)
    workbook.close()

    candidate = scan_workbook(path, period="2025-03").candidates[0]
    assert candidate.kind == "attendance"
    record = candidate.records[0]
    assert record["date"] == "2025-03-01"
    assert record["hours"] == 0
    assert record["oos_pct"] == 5.0


def test_formula_without_cached_value_is_warned(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "formula.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Department", "Actual Sales", "Budget"])
    sheet.append(["Retail", "=1+2", 100])
    workbook.save(path)
    workbook.close()

    candidate = scan_workbook(path).candidates[0]
    assert candidate.records[0].get("actual") is None
    assert any("Formula cache missing" in warning for warning in candidate.warnings)