"""Employee roster ("Employee basic details"): one row per person with store, department, section and manager."""

from __future__ import annotations

import re

from ..reader import Sheet
from ..util import clean_text, emp_code, parse_date, title_name
from .base import ParseResult, blank_row, cells, find_col, get, text

EMP = r"EMPLOYEE (NUMBER|NO|CODE|ID)|EMP (NO|NUMBER|CODE|ID)|STAFF (NO|ID)|PERSONNEL NUMBER"


def score(sheet: Sheet) -> tuple[float, int]:
    for i, row in enumerate(sheet.rows[:30]):
        h = cells(row)
        if find_col(h, EMP) is not None and find_col(h, r"(REPORTING |LINE )?MANAGER( NAME)?|REPORTS TO") is not None \
                and find_col(h, r"DESIGNATION|JOB TITLE|POSITION") is not None:
            return 0.95, i
    return 0.0, -1


def parse(sheet: Sheet) -> ParseResult:
    res = ParseResult(kind="roster", sheet=sheet.name)
    _, hr = score(sheet)
    h = cells(sheet.rows[hr])
    col = {
        "bu": find_col(h, r"BUSINESS UNIT( NAME)?|STORE( NAME)?|LOCATION|BRANCH"),
        "dept": find_col(h, r"DEPARTMENT( NAME)?|DEPT"),
        "section": find_col(h, r"SECTION( NAME)?|SUB DEPARTMENT"),
        "emp": find_col(h, EMP, exclude=("MANAGER",)),
        "name": find_col(h, r"EMPLOYEE NAME|EMPLOYEEE NAME|NAME|FULL NAME"),
        "desig": find_col(h, r"DESIGNATION|JOB TITLE|POSITION"),
        "grade": find_col(h, r"GRADE|JOB GRADE"),
        "gender": find_col(h, r"GENDER|SEX"),
        "manager_no": find_col(h, r"(REPORTING |LINE )?MANAGER (EMPLOYEE )?(NUMBER|NO|CODE|ID)"),
        "manager": find_col(h, r"(REPORTING |LINE )?MANAGER( NAME)?|REPORTS TO", exclude=("NUMBER", " NO", "CODE", " ID")),
        "joining": find_col(h, r"JOINING DATE|DATE OF JOINING|DOJ|HIRE DATE"),
    }
    seen: set[str] = set()
    dup = 0
    for row in sheet.rows[hr + 1:]:
        if blank_row(row):
            continue
        emp = emp_code(get(row, col["emp"]))
        if not emp or not re.search(r"\d", emp):
            continue
        if emp in seen:
            dup += 1
            continue
        seen.add(emp)
        dept_raw = text(row, col["dept"])
        m = re.match(r"^\s*(\d{1,2})\s*[:\-]\s*(.*)$", dept_raw)
        dept_code, dept_name = (m.group(1).zfill(2), m.group(2).strip()) if m else ("", dept_raw)
        grade = clean_text(get(row, col["grade"]))
        if re.fullmatch(r"\d", grade):
            grade = grade.zfill(2)
        jd = parse_date(get(row, col["joining"])) if col["joining"] is not None else None
        res.rows.append({
            "emp_no": emp, "name": title_name(get(row, col["name"])) or emp, "bu": text(row, col["bu"]),
            "dept_code": dept_code, "dept_name": dept_name, "section": text(row, col["section"]),
            "designation": text(row, col["desig"]), "grade": grade, "gender": text(row, col["gender"]).title(),
            "manager_name": title_name(get(row, col["manager"])), "manager_no": emp_code(get(row, col["manager_no"])),
            "joining": jd.isoformat() if jd else None,
        })
    if dup:
        res.warn(f"{dup} repeated employee numbers were ignored (the first row for each person was kept).")
    if not res.rows:
        res.warn("No employee rows were found under the header.")
    stores = len({r["bu"] for r in res.rows})
    res.summary = f"{len(res.rows):,} employees in {stores} business units"
    res.needs = ["as_of"]
    res.preview = res.rows[:8]
    return res
