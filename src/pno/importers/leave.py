"""Leave registers in whatever layout the HR system produces: employee number, from / to dates, type and status."""

from __future__ import annotations

import re

from ..reader import Sheet
from ..util import clean_text, emp_code, norm, parse_date
from .base import ParseResult, blank_row, cells, find_col, get

EMP = r"EMPLOYEE (NUMBER|NO|CODE|ID)|EMP (NO|NUMBER|CODE|ID)|STAFF (NO|ID)|PERSONNEL NUMBER"
REJECT = re.compile(r"REJECT|CANCEL|DECLIN|PENDING|WITHDRAW")


def score(sheet: Sheet) -> tuple[float, int]:
    for i, row in enumerate(sheet.rows[:20]):
        h = cells(row)
        if find_col(h, EMP) is None:
            continue
        has_from = find_col(h, r"(LEAVE )?(FROM|START)( DATE)?|DATE FROM|START DATE") is not None
        has_type = find_col(h, r"LEAVE TYPE|TYPE|LEAVE|ABSENCE TYPE") is not None
        if has_from and has_type:
            return 0.9, i
    return 0.0, -1


def parse(sheet: Sheet) -> ParseResult:
    res = ParseResult(kind="leave", sheet=sheet.name)
    _, hr = score(sheet)
    h = cells(sheet.rows[hr])
    col = {
        "emp": find_col(h, EMP),
        "name": find_col(h, r"EMPLOYEE NAME|NAME"),
        "type": find_col(h, r"LEAVE TYPE|ABSENCE TYPE|TYPE|LEAVE"),
        "from": find_col(h, r"(LEAVE )?(FROM|START)( DATE)?|DATE FROM|START DATE"),
        "to": find_col(h, r"(LEAVE )?(TO|END)( DATE)?|DATE TO|END DATE|UNTIL"),
        "status": find_col(h, r"STATUS|APPROVAL STATUS|APPROVAL"),
    }
    skipped = 0
    for row in sheet.rows[hr + 1:]:
        if blank_row(row):
            continue
        emp = emp_code(get(row, col["emp"]))
        d1 = parse_date(get(row, col["from"]))
        d2 = parse_date(get(row, col["to"])) or d1
        if not emp or not d1:
            continue
        if col["status"] is not None and REJECT.search(norm(get(row, col["status"]))):
            skipped += 1
            continue
        if d2 < d1:
            d1, d2 = d2, d1
        res.rows.append({"emp_no": emp, "name": clean_text(get(row, col["name"])), "d_from": d1.isoformat(),
                         "d_to": d2.isoformat(), "type": clean_text(get(row, col["type"])) or "Leave"})
    if skipped:
        res.warn(f"{skipped} rejected / cancelled / pending requests were left out.")
    if res.rows:
        res.month = max(r["d_to"] for r in res.rows)[:7]
    res.summary = f"{len(res.rows):,} approved leave records for {len({r['emp_no'] for r in res.rows}):,} people"
    res.preview = res.rows[:8]
    return res
