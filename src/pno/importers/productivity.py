"""MTD productivity: one block per store, each with its own header row (Store Name | Dept/Section | Store Productivity …).

Rows mix levels: '00 - Overall Store' (store), 'CCO', '01-CGD' (department), 'S054 - Bakery/Pastry' (section),
'S050-S051 Deli & Dairy' (two sections), 'Other Store Sections' (supermarkets). The ▲/▼ comparison columns are
recomputed from the numbers, and a blank forecast is 'no forecast' (never the report's -100%).
"""

from __future__ import annotations

import re

from ..reader import Sheet
from ..util import clean_text, norm, num, parse_date
from .base import ParseResult, blank_row, cells, find_col, get

MONTHS = "JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC"


def score(sheet: Sheet) -> tuple[float, int]:
    for i, row in enumerate(sheet.rows[:20]):
        h = cells(row)
        if find_col(h, r"STORE PRODUCTIVITY") is not None and find_col(h, r"TARGET PRODUCTIVITY") is not None:
            return 0.96, i
    return 0.0, -1


def row_code(label: str) -> tuple[str, str] | None:
    n = norm(label)
    if not n:
        return None
    if re.match(r"^0+ OVERALL", n) or n in ("OVERALL STORE", "TOTAL STORE", "STORE TOTAL"):
        return "STORE", "store"
    if n.startswith("CCO") or "CENTRAL CASHIER" in n:
        return "CCO", "cco"
    if n.startswith("OTHER STORE SECTION"):
        return "OTHER", "other"
    m = re.match(r"^S(\d{3})\s*S(\d{3})\b", n)
    if m:
        return f"S{m.group(1)}+S{m.group(2)}", "section"
    m = re.match(r"^S(\d{3})\b", n)
    if m:
        return f"S{m.group(1)}", "section"
    m = re.match(r"^(\d{2})\s+[A-Z]", n)
    if m and m.group(1) != "00":
        return f"D{m.group(1)}", "dept"
    return None


def parse(sheet: Sheet, file_name: str = "") -> ParseResult:
    res = ParseResult(kind="productivity", sheet=sheet.name)
    col = None
    store = ""
    unknown: set[str] = set()
    for row in sheet.rows:
        if blank_row(row):
            continue
        h = cells(row)
        if find_col(h, r"STORE PRODUCTIVITY") is not None and find_col(h, r"TARGET PRODUCTIVITY") is not None:
            col = {
                "store": find_col(h, r"STORE NAME|STORE"),
                "row": find_col(h, r"DEPT SECTION|DEPARTMENT SECTION|SECTION|DEPT"),
                "actual": find_col(h, r"STORE PRODUCTIVITY|PRODUCTIVITY|ACTUAL PRODUCTIVITY"),
                "ly": find_col(h, r"STORE PRODUCTIVITY LY|PRODUCTIVITY LY|LY"),
                "target": find_col(h, r"TARGET PRODUCTIVITY|TARGET"),
                "forecast": find_col(h, r"FORECASTED PRODUCTIVITY|FORECAST PRODUCTIVITY|FORECAST"),
            }
            continue
        if col is None:
            continue
        store = clean_text(get(row, col["store"])) or store
        label = clean_text(get(row, col["row"]))
        rc = row_code(label)
        if rc is None:
            if label:
                unknown.add(label)
            continue
        actual, target = num(get(row, col["actual"])), num(get(row, col["target"]))
        if actual is None and target is None:
            continue
        res.rows.append({"store_raw": store, "row_code": rc[0], "level": rc[1], "row_name": label, "actual": actual,
                         "ly": num(get(row, col["ly"])), "target": target, "forecast": num(get(row, col["forecast"]))})
    if unknown:
        res.warn("Rows not recognised (kept out): " + ", ".join(sorted(unknown)[:6]))
    res.month = month_from_text(f"{file_name} {sheet.name}")
    if not res.month:
        res.needs = ["month"]
        res.warn("This report has no date inside it. Choose the month it belongs to.")
    stores = len({r["store_raw"] for r in res.rows})
    res.summary = f"{len(res.rows):,} rows for {stores} stores"
    res.preview = res.rows[:8]
    return res


def month_from_text(s: str) -> str | None:
    n = norm(s)
    m = re.search(rf"\b({MONTHS})[A-Z]*\s*(20\d{{2}}|\d{{2}})\b", n)
    if m:
        d = parse_date(f"1-{m.group(1)}-{m.group(2)}")
        return f"{d.year:04d}-{d.month:02d}" if d else None
    m = re.search(r"\b(20\d{2})\s(\d{2})\b", n)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}-{m.group(2)}"
    return None
