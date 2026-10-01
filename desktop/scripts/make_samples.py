"""Generate fictional import examples. Never derive fixtures from corporate data."""

from datetime import date
from pathlib import Path
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1] / "samples"


def save(name, sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets:
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 22
    workbook.save(ROOT / name)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    staff_headers = [
        "Business Unit", "Department", "Section", "Employee Number",
        "Employee Name", "Designation", "Grade", "Gender",
        "Reporting Manager", "Reporting Manager Employee Number",
    ]
    staff = [
        ["Training Store A", "", "", "DEMO-GM", "Example General Manager", "Store GM", "DEMO", "", "", ""],
        ["Training Store A", "Fresh Food", "", "DEMO-DH", "Example Department Head", "Department Head", "DEMO", "", "Example General Manager", "DEMO-GM"],
        ["Training Store A", "Fresh Food", "Bakery", "DEMO-SM", "Example Section Manager", "Section Manager", "DEMO", "", "Example Department Head", "DEMO-DH"],
        ["Training Store A", "Fresh Food", "Bakery", "DEMO-001", "Example Associate One", "Associate", "DEMO", "", "Example Section Manager", "DEMO-SM"],
        ["Training Store A", "Fresh Food", "Bakery", "DEMO-002", "Example Associate Two", "Associate", "DEMO", "", "Example Section Manager", "DEMO-SM"],
    ]
    save("fictional-roster.xlsx", [("Roster", [staff_headers, *staff])])
    sales_headers = [
        "Store", "Department", "Section", "Date", "Actual Sales",
        "Budget", "Last Year Sales", "OOS Value", "OOS %",
    ]
    daily = [
        ["Training Store A", "Fresh Food", "Bakery", date(2026, 8, 1), 920, 1000, 880, 20, "2%"],
        ["Training Store A", "Fresh Food", "Bakery", date(2026, 8, 2), 1040, 1000, 910, 10, "1%"],
    ]
    mtd = [["Training Store A", "Fresh Food", "Bakery", date(2026, 8, 31), 30400, 31000, 28500, 320, "1.1%"]]
    save("fictional-sales.xlsx", [
        ("Daily Sales", [["FICTIONAL TRAINING REPORT — NOT COMPANY DATA"], [], sales_headers, *daily]),
        ("MTD Sales", [["FICTIONAL TRAINING REPORT — NOT COMPANY DATA"], [], sales_headers, *mtd]),
        ("Instructions", [["Only the Daily Sales and MTD Sales sheets contain data."]]),
    ])
    attendance_headers = [
        "Store", "Department", "Section", "Employee Number",
        "Employee Name", "Date", "IN", "OUT", "Total WH", "Status",
    ]
    attendance = [
        ["Training Store A", "Fresh Food", "Bakery", "DEMO-001", "Example Associate One", date(2026, 8, 1), "22:00", "06:00", 8, "Present"],
        ["Training Store A", "Fresh Food", "Bakery", "DEMO-001", "Example Associate One", date(2026, 8, 2), "", "", 0, "Absent"],
        ["Training Store A", "Fresh Food", "Bakery", "DEMO-002", "Example Associate Two", date(2026, 8, 1), "", "", 0, "Day OFF"],
        ["Training Store A", "Fresh Food", "Bakery", "DEMO-002", "Example Associate Two", date(2026, 8, 2), "", "", 0, "On Leave"],
    ]
    save("fictional-attendance.xlsx", [("Attendance", [attendance_headers, *attendance])])
    productivity_headers = [
        "Store", "Department", "Section", "Date",
        "Productivity", "Productivity LY", "Productivity Growth %",
    ]
    save("fictional-productivity.xlsx", [("Productivity", [
        productivity_headers,
        ["Training Store A", "Fresh Food", "Bakery", date(2026, 8, 31), 120, 110, "9.1%"],
    ])])
    print(f"Fictional workbooks generated in {ROOT}")


if __name__ == "__main__":
    main()
