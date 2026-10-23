"""Any other table: kept as a dataset instead of being skipped.

The header row is found automatically, every column is profiled (number, percent, date, employee number, text) and given
a meaning where one is clear (store, section, employee, actual, budget, target, last year…), from the header words and,
when the header says nothing, from the values themselves (a column full of store names is a store column). The Data
explorer then charts it and writes insights; when an AI is set up it can also label the columns.
"""

from __future__ import annotations

import re
from collections import Counter

from ..po import canon
from ..reader import Sheet
from ..util import clean_text, is_blank, norm, parse_date, parse_num
from .base import ParseResult

ROLE_WORDS: list[tuple[str, str]] = [
    ("employee_id", r"^(EMP(LOYEE)?|STAFF|PERSONNEL|SUBJECT EMPLOYEE)( NO| NUMBER| CODE| ID)$|^EMP NO$|^ID$|^EMPLOYEE ID$"),
    ("employee_name", r"^(EMP(LOYEE)? )?NAME$|FULL NAME|^EMPLOYEE NAME$|SUBJECT FULL NAME"),
    ("manager", r"MANAGER( FULL)? NAME|REPORTING MANAGER|LINE MANAGER|REPORTS TO"),
    ("designation", r"DESIGNATION|POSITION|JOB TITLE|^ROLE$"),
    ("store", r"STORE|BUSINESS UNIT|BRANCH|^LOCATION$|^SITE$|^OUTLET$|^BU$|DIVISION"),
    ("city", r"^CITY$|^REGION$"),
    ("department", r"^DEP(AR)?T(MENT)?( NAME)?$|^DEPT$"),
    ("section", r"SECTION|SUB ?DEPARTMENT|CATEGORY|FAMILY|^SECT$"),
    ("date", r"DATE|^DAY$|^WEEK$|PERIOD$"),
    ("month", r"^MONTH$|^SALARY PERIOD$|^YEAR$"),
    ("budget", r"BUDGET|^BUD\b|PLAN"),
    ("target", r"TARGET|GOAL|^TGT$"),
    ("last_year", r"\bLY\b|LAST YEAR|PREVIOUS YEAR|PRIOR YEAR"),
    ("forecast", r"FORECAST|^FCT$"),
    ("actual", r"ACTUAL|NET SALES|^SALES$|REVENUE|ACHIEVED|^VALUE$|^AMOUNT$"),
    ("count", r"COUNT|^QTY$|QUANTITY|HEADCOUNT|^CASES?$|^UNITS$"),
    ("score", r"SCORE|RATING|^NPS\b|INDEX"),
    ("reason", r"REASON|REMARKS?|COMMENTS?|NOTE"),
    ("type", r"TYPE|STATUS|CATEGORY TYPE"),
]
ROLE_RX = [(role, re.compile(rx)) for role, rx in ROLE_WORDS]
TOTAL_RX = re.compile(r"^(GRAND )?TOTAL\b|^SUB ?TOTAL\b|^Z$")
MEASURE_ROLES = {"actual", "budget", "target", "last_year", "forecast", "count", "score"}


def _is_text(v) -> bool:
    if is_blank(v) or isinstance(v, (int, float)):
        return False
    s = clean_text(v)
    return bool(s) and parse_num(s)[0] is None and parse_date(s) is None


def find_header(rows: list[list]) -> int | None:
    """The row with the most text labels that is followed by data rows."""
    best, best_i = 0.0, None
    for i, row in enumerate(rows[:40]):
        labels = sum(1 for c in row if _is_text(c))
        if labels < 2:
            continue
        below = [r for r in rows[i + 1:i + 6] if any(not is_blank(c) for c in r)]
        if len(below) < 1:
            continue
        width = max(len([c for c in row if not is_blank(c)]), 1)
        filled = sum(min(1.0, sum(1 for c in r if not is_blank(c)) / width) for r in below) / len(below)
        numeric_below = sum(1 for r in below for c in r if parse_num(c)[0] is not None)
        score = labels * (0.5 + filled) + (0.5 if numeric_below else 0)
        if score > best:
            best, best_i = score, i
    return best_i


def _headers(rows: list[list], hi: int) -> list[str]:
    head = rows[hi]
    above = rows[hi - 1] if hi > 0 else []
    names, seen = [], Counter()
    group = ""
    for j in range(max(len(head), 1)):
        g = clean_text(above[j]) if j < len(above) else ""
        if g and not _is_number(g):
            group = g
        h = clean_text(head[j]) if j < len(head) else ""
        if not h:
            h = group or f"Column {j + 1}"
        elif group and norm(h) in ("ACTUAL", "BUDGET", "GTH %", "GROWTH", "TARGET", "LY", "VAR %", "%", "COUNT"):
            h = f"{group} {h}"
        seen[h] += 1
        names.append(h if seen[h] == 1 else f"{h} ({seen[h]})")
    return names


def _is_number(s) -> bool:
    return parse_num(s)[0] is not None


def profile(names: list[str], data: list[list]) -> list[dict]:
    cols = []
    for j, name in enumerate(names):
        vals = [r[j] if j < len(r) else None for r in data]
        filled = [v for v in vals if not is_blank(v)]
        nums = [parse_num(v) for v in filled]
        n_num = sum(1 for v, _ in nums if v is not None)
        n_pct = sum(1 for v, p in nums if v is not None and p)
        n_date = sum(1 for v in filled if not isinstance(v, (int, float)) and parse_date(v) is not None)
        texts = [clean_text(v) for v in filled]
        distinct = len(set(texts))
        if not filled:
            kind = "empty"
        elif n_date >= 0.8 * len(filled):
            kind = "date"
        elif n_num >= 0.8 * len(filled):
            ids = all(re.fullmatch(r"\d{5,9}(\.0)?", t.replace(",", "")) for t in texts[:200]) and not any("," in t for t in texts[:50])
            id_header = re.search(r"\b(NO|NUMBER|ID|CODE|EMP|EMPLOYEE|STAFF)\b", norm(name))
            measure_header = any(rx.search(norm(name)) for role, rx in ROLE_RX if role in MEASURE_ROLES)
            is_id = ids and distinct >= 0.9 * len(filled) and (id_header or not measure_header) and not measure_header
            kind = "id" if is_id else ("percent" if n_pct >= 0.5 * n_num else "number")
        else:
            kind = "text"
        role = _role(name, kind, texts)
        cols.append({"name": name, "type": kind, "role": role, "filled": len(filled), "distinct": distinct,
                     "sample": texts[:3]})
    return cols


def _role(name: str, kind: str, texts: list[str]) -> str:
    n = norm(name)
    for role, rx in ROLE_RX:
        if rx.search(n):
            if role in MEASURE_ROLES and kind not in ("number", "percent"):
                continue
            if role in ("store", "section", "department", "employee_name", "designation", "manager", "city") and kind != "text":
                continue
            return role
    if kind == "text" and texts:
        sample = texts[:60]
        known = {s[0] for s in canon._STORES}
        if sum(1 for t in sample if canon.store(t).replace(" · Myli", "") in known) >= 0.6 * len(sample):
            return "store"
        if sum(1 for t in sample if canon.section(t) in canon.DEPARTMENT_OF) >= 0.7 * len(sample):
            return "section"
    if kind == "id":
        return "employee_id"
    if kind == "date":
        return "date"
    return ""


def score(sheet: Sheet) -> tuple[float, int]:
    hi = find_header(sheet.rows)
    if hi is None:
        return 0.0, -1
    data = [r for r in sheet.rows[hi + 1:] if any(not is_blank(c) for c in r)]
    return (0.3, hi) if len(data) >= 1 else (0.0, -1)


def parse(sheet: Sheet) -> ParseResult:
    res = ParseResult(kind="dataset", sheet=sheet.name)
    hi = find_header(sheet.rows)
    if hi is None:
        return res
    names = _headers(sheet.rows, hi)
    raw = [r for r in sheet.rows[hi + 1:] if any(not is_blank(c) for c in r)]
    cols = profile(names, raw)
    keep = [j for j, c in enumerate(cols) if c["type"] != "empty"]
    first_text = next((j for j in keep if cols[j]["type"] == "text"), None)
    totals = repeats = dupes = 0
    rows = []
    header_key = [norm(c) for c in sheet.rows[hi]]
    seen_rows: set = set()
    for r in raw:
        if first_text is not None and first_text < len(r) and TOTAL_RX.search(norm(r[first_text])):
            totals += 1
            continue
        if [norm(c) for c in r][:len(header_key)] == header_key[:len(r)] or \
                sum(1 for a, b in zip([norm(c) for c in r], header_key) if a and a == b) >= max(2, len([h for h in header_key if h]) * 0.6):
            repeats += 1                          # the header printed again (one block per store): not data
            continue
        sig = tuple(clean_text(c) for c in r)
        if sig in seen_rows:
            dupes += 1
            continue
        seen_rows.add(sig)
        rec = {}
        for j in keep:
            v = r[j] if j < len(r) else None
            c = cols[j]
            if c["type"] in ("number", "percent"):
                rec[c["name"]] = parse_num(v)[0]
            elif c["type"] == "date":
                d = parse_date(v)
                rec[c["name"]] = d.isoformat() if d else clean_text(v) or None
            else:
                rec[c["name"]] = clean_text(v) or None
        store_col = next((cols[j]["name"] for j in keep if cols[j]["role"] == "store"), None)
        section_col = next((cols[j]["name"] for j in keep if cols[j]["role"] == "section"), None)
        if store_col and rec.get(store_col):
            rec["_store"] = canon.store(rec[store_col])
        if section_col and rec.get(section_col):
            rec["_section"] = canon.section(rec[section_col])
        rows.append(rec)
    res.rows = rows
    cols = [cols[j] for j in keep]
    res.extra = {"columns": cols, "title": sheet.name, "header_row": hi + 1}
    if totals:
        res.warn(f"{totals} total / subtotal row(s) were left out so nothing is counted twice.")
    if repeats:
        res.warn(f"{repeats} repeated header row(s) were removed.")
    if dupes:
        res.warn(f"{dupes} exact duplicate row(s) were removed.")
    roles = [c["role"] for c in cols if c["role"]]
    measures = [c["name"] for c in cols if c["type"] in ("number", "percent")]
    res.summary = (f"{len(rows):,} rows · {len(cols)} columns" + (f" · understood: {', '.join(sorted(set(roles)))}" if roles else "")
                   + (f" · {len(measures)} numeric" if measures else ""))
    res.warn("Not one of P&O's standard reports: kept under Other data with charts and insights.")
    res.preview = rows[:8]
    return res
