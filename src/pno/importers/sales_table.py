"""Store sales as one flat table: one row per section per store (Department · Section · Code · Store Type · Store
Short Name · Budget · Net Sales …), usually under a 'YTD' or 'MTD' heading, with a subtotal line after each section.

This is the layout the commercial team exports for the year to date. Each row becomes a section line for its store;
section subtotal rows are skipped, and department and store totals are added up from the sections so every screen
(store, department, section) has its numbers.
"""

from __future__ import annotations

import re

from ..reader import Sheet
from ..util import clean_text, is_blank, norm, parse_num
from .base import ParseResult, get

# column titles, matched on the normalised header text (group heading above + column title)
COLS = {
    "store": (r"STORE SHORT NAME", r"STORE NAME", r"^STORE$", r"STORE DESC", r"BRANCH", r"BUSINESS UNIT", r"\bSITE\b", r"LOCATION", r"OUTLET"),
    "section": (r"^SECTION$", r"SECTION NAME", r"SECTION DESC", r"SUB DEPARTMENT", r"SUB DEPT", r"CATEGORY"),
    "code": (r"^CODE$", r"SECTION CODE", r"SEC CODE", r"^SEC$"),
    "dept": (r"^DEPARTMENT$", r"^DEPT$", r"DEPARTMENT NAME", r"DIVISION"),
    "fmt": (r"STORE TYPE", r"FORMAT", r"STORE FORMAT", r"^TYPE$"),
}
VALS = {
    "budget": (r"BUDGET", r"\bBGT\b", r"\bBUD\b", r"TARGET", r"\bPLAN\b"),
    "actual": (r"NET SALES(?! LY)(?! BUDGET)", r"^SALES$", r"ACTUAL", r"\bNS\b", r"REVENUE", r"TURNOVER"),
    "ly": (r"\bLY\b", r"LAST YEAR", r"PREVIOUS YEAR", r"PRIOR YEAR"),
    "growth": (r"GTH", r"GROWTH", r"VS LY"),
    "var_pct": (r"VAR", r"VS BUDGET", r"ACH"),
    "margin": (r"MARGIN", r"\bGM\b", r"NETMRG"),
    "waste": (r"WASTE", r"WASTAGE"),
    "oos": (r"OUT OF STOCK", r"\bOOS\b"),
    "customers": (r"CUSTOMER", r"\bCUST\b", r"FOOTFALL", r"TRANSACTIONS"),
}
PCT = {"growth", "var_pct", "margin", "waste", "oos"}
DEPT_CODE = {"CONSUMER GOODS": "01", "FRESH FOOD": "02", "LIGHT HOUSE HOLD": "03", "LIGHT HOUSEHOLD": "03", "HEAVY HOUSE HOLD": "04",
             "HEAVY HOUSEHOLD": "04", "TEXTILE": "05", "HEALTH & BEAUTY": "06", "HEALTH AND BEAUTY": "06", "H&B": "06", "MYLI": "06"}
DEPT_NAME = {"01": "Consumer Goods", "02": "Fresh Food", "03": "Light House Hold", "04": "Heavy House Hold", "05": "Textile", "06": "Health & Beauty"}


def _find(heads: list[str], pats) -> int | None:
    for p in pats:
        for j, h in enumerate(heads):
            if h and re.search(p, h):
                return j
    return None


def _header(sheet: Sheet) -> tuple[int, list[str], str] | None:
    """The title row (and the group heading above it, e.g. 'YTD' over 'Budget | Net Sales')."""
    rows = sheet.rows
    for i, row in enumerate(rows[:25]):
        h = [norm(c) for c in row]
        if _find(h, COLS["store"]) is None or _find(h, COLS["section"]) is None:
            continue
        above = [norm(c) for c in rows[i - 1]] if i else []
        group, carry = [], ""
        for j in range(len(h)):
            carry = (above[j] if j < len(above) and above[j] else carry) if above else ""
            group.append(carry)
        heads = [f"{g} {x}".strip() if g and x else x for g, x in zip(group, h)]
        if _find(heads, VALS["actual"]) is None:
            continue
        text = " ".join(group + h)
        period = "YTD" if re.search(r"\bYTD\b|YEAR TO DATE", text) else "MTD" if re.search(r"\bMTD\b|MONTH TO DATE", text) else ""
        return i, heads, period
    return None


def score(sheet: Sheet) -> tuple[float, int]:
    hit = _header(sheet)
    return (0.97, hit[0]) if hit else (0.0, -1)


def _value_cols(heads: list[str], period: str) -> dict[str, int]:
    """Which column holds each measure; with both MTD and YTD blocks, the period of the file's heading wins."""
    out = {}
    for f, pats in VALS.items():
        cands = [j for j, h in enumerate(heads) if h and any(re.search(p, h) for p in pats)]
        if f == "actual":
            cands = [j for j in cands if not re.search(r"\bLY\b|LAST YEAR|BUDGET|TARGET|VAR|GTH|GROWTH|%", heads[j])]
        if f == "budget":
            cands = [j for j in cands if not re.search(r"VAR|%|ACH", heads[j])]
        if f == "ly":
            cands = [j for j in cands if not re.search(r"GTH|GROWTH|%|VAR", heads[j])]
        if not cands:
            continue
        pref = [j for j in cands if period and period in heads[j]]
        out[f] = (pref or cands)[0]
    return out


def parse(sheet: Sheet) -> ParseResult:
    res = ParseResult(kind="sales", sheet=sheet.name)
    hit = _header(sheet)
    if not hit:
        return res
    hi, heads, period = hit
    period = period or ("YTD" if "YTD" in norm(sheet.name) else "MTD" if "MTD" in norm(sheet.name) else "")
    c = {k: _find(heads, p) for k, p in COLS.items()}
    v = _value_cols(heads, period)
    skipped = 0
    totals: dict[tuple, dict] = {}
    for row in sheet.rows[hi + 1:]:
        store_raw = clean_text(get(row, c["store"]))
        section_raw = clean_text(get(row, c["section"]))
        code_raw = clean_text(get(row, c["code"])) if c["code"] is not None else ""
        if not store_raw or not section_raw or re.search(r"^(grand\s*)?total|^sub\s*total", store_raw, re.I):
            skipped += 1                                         # section subtotal / grand total lines
            continue
        if all(is_blank(get(row, j)) for j in v.values()):
            continue
        m = re.match(r"^([SX])\s*(\d{3})", code_raw.upper()) or re.match(r"^([SX])\s*(\d{3})", section_raw.upper())
        code = f"{m.group(1)}{m.group(2)}" if m else ""
        name = re.sub(r"^[A-Z&]{2,4}\s*-\s*", "", section_raw).strip()          # 'CGD - Beverages' → 'Beverages'
        dept_name = norm(clean_text(get(row, c["dept"]))) if c["dept"] is not None else ""
        dept = DEPT_CODE.get(dept_name, "")
        store = re.sub(r"^\d{2,4}\s+", "", store_raw).strip()                    # '651 LAH Fortress' → 'LAH Fortress'
        rec = {"level": "section" if (not code or code.startswith("S")) else "consignment_item", "code": code or f"N:{name}", "name": name,
               "dept": dept, "store_raw": store, "store_type": clean_text(get(row, c["fmt"])) if c["fmt"] is not None else "",
               "period": period or "MTD", "as_of": None, "d_from": None}
        for f, j in v.items():
            x, is_pct = parse_num(get(row, j))
            if x is not None and f in PCT and not is_pct and abs(x) <= 1.5 and not isinstance(get(row, j), str):
                x *= 100                                                          # 0.123 stored as a fraction → 12.3 %
            rec[f] = x
        a, b, g, ly = rec.get("actual"), rec.get("budget"), rec.get("growth"), rec.get("ly")
        if ly is None and a and g is not None and g > -99.9:
            rec["ly"] = ly = a / (1 + g / 100)
        if g is None and a is not None and ly:
            rec["growth"] = round(100 * (a / ly - 1), 1)
        rec["var_pct"] = rec.get("var_pct") if rec.get("var_pct") is not None else (round(100 * (a / b - 1), 1) if a is not None and b else None)
        res.rows.append(rec)
        for key in ((store, "dept", dept), (store, "store", "")):
            if key[1] == "dept" and not dept:
                continue
            t = totals.setdefault(key, {"actual": 0.0, "budget": 0.0, "ly": 0.0, "has_b": False, "ly_ok": True, "n": 0, "w": {}})
            t["actual"] += a or 0
            if b:
                t["budget"] += b
                t["has_b"] = True
            if (a or ly):
                if ly is None:
                    t["ly_ok"] = False
                else:
                    t["ly"] += ly
            for f in ("margin", "waste", "oos"):
                if rec.get(f) is not None and a:
                    s = t["w"].setdefault(f, [0.0, 0.0])
                    s[0] += rec[f] * a
                    s[1] += a
            t["n"] += 1
    for (store, level, dept), t in totals.items():
        a, b, ly = t["actual"], (t["budget"] if t["has_b"] else None), (t["ly"] if t["ly_ok"] and t["ly"] else None)
        rec = {"level": level, "code": f"D{dept}" if level == "dept" else "STORE", "name": DEPT_NAME.get(dept, "Total Store") if level == "dept" else "Total Store",
               "dept": dept, "store_raw": store, "period": period or "MTD", "as_of": None, "d_from": None, "actual": a, "budget": b, "ly": ly,
               "growth": round(100 * (a / ly - 1), 1) if ly else None, "var_pct": round(100 * (a / b - 1), 1) if b else None, "derived": True}
        for f, (num, den) in t["w"].items():
            rec[f] = round(num / den, 2) if den else None
        res.rows.append(rec)
    stores = {r["store_raw"] for r in res.rows}
    secs = {r["name"] for r in res.rows if r["level"] == "section"}
    res.summary = f"{len(stores)} stores · {len(secs)} sections · {period or 'period not stated'}" + (" · budget" if "budget" in v else "") + (" · last year" if "ly" in v or "growth" in v else "")
    if skipped:
        res.warn(f"{skipped} subtotal line{'s' if skipped != 1 else ''} skipped; store and department totals are added up from the sections.")
    missing = [n for f, n in (("budget", "budget"), ("ly", "last year / growth")) if f not in v and not (f == "ly" and "growth" in v)]
    if missing:
        res.warn("No " + " or ".join(missing) + " column: " + ("sales vs budget" if "budget" in missing else "growth") + " can't be shown from this file.")
    res.needs = ["month"]
    res.extra = {**res.extra, "columns_read": {f: heads[j] for f, j in {**c, **v}.items() if j is not None}}
    return res
