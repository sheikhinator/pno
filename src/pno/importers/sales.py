"""BO 200-10-05 Country Periodic Store Performance Report ('Store Net Sales' tab): one block per store.

Block: 'Report Name' row (Currency … - MTD / DAY, 'Net Sales of: (Fri) 02-Oct-26'), 'Store Name:' row with the Report
Period, two header rows, then sections followed by their subtotal rows:
    S011…S014 CGD-FMG · S021…S026 CGD-OPSS · Consumer Goods (01) · S050…S057 Fresh Food (02) · z (duplicate, skipped)
    · Food · S080… Heavy House Hold (04) · S030… Light House Hold (03) · S040… Textile (05) · z · Non Food
    · Total Store · X091… Consignment · Total Hypermarket
Department and store figures are taken from the report's own subtotal rows, never re-added.
"""

from __future__ import annotations

import re

from ..reader import Sheet
from ..util import clean_text, is_blank, norm, parse_date, parse_num
from .base import ParseResult, blank_row, get

SUBTOTALS = {
    "CGD FMG": ("subgroup", "SG-FMG", "01"), "CGD OPSS": ("subgroup", "SG-OPSS", "01"),
    "CONSUMER GOODS": ("dept", "D01", "01"), "FRESH FOOD": ("dept", "D02", "02"), "FOOD": ("food", "FOOD", ""),
    "HEAVY HOUSE HOLD": ("dept", "D04", "04"), "HEAVY HOUSEHOLD": ("dept", "D04", "04"),
    "LIGHT HOUSE HOLD": ("dept", "D03", "03"), "LIGHT HOUSEHOLD": ("dept", "D03", "03"),
    "TEXTILE": ("dept", "D05", "05"), "NON FOOD": ("nonfood", "NONFOOD", ""), "TOTAL STORE": ("store", "STORE", ""),
    "CONSIGNMENT": ("consignment", "CONSIGN", ""), "TOTAL HYPERMARKET": ("total", "TOTAL", ""),
    "TOTAL SUPERMARKET": ("total", "TOTAL", ""),
}
FIELDS = {
    "actual": ("NET SALES", "ACTUAL"), "forecast": ("NET SALES", "FORECAST"), "budget": ("NET SALES", "BUDGET"),
    "growth": ("NET SALES", "GTH %"), "var_pct": ("NET SALES", "VAR %"), "weight": ("SECTION WEIGHT", "IN STORE"),
    "customers": ("CUSTOMER", "CUST"), "cust_growth": ("CUSTOMER", "GTH %"), "penetration": ("PENT RATE", ""),
    "items": ("ITEM", "ACTUAL"), "avg_basket": ("AVG BASKET", "ACTUAL"), "asp": ("AVG SELLING PRICE", "ACTUAL"),
    "margin": ("MARGIN %", "NETMRG"), "waste": ("MARGIN %", "WASTE"), "margin_net": ("MARGIN %", "NETMRG WST"),
    "avg_stock": ("AVG STOCK", ""), "oos": ("OUT OF STOCK %", ""),
}
PCT_FIELDS = {"growth", "var_pct", "weight", "cust_growth", "penetration", "margin", "waste", "margin_net", "oos"}


def score(sheet: Sheet) -> tuple[float, int]:
    text = " ".join(norm(c) for r in sheet.rows[:12] for c in r if not is_blank(c))
    if "SECTION CODE NAME" in text and ("STORE NAME" in text or "200 10 05" in text):
        return 0.98, 0
    if "SECTION CODE NAME" in text and "NET SALES" in text:
        return 0.85, 0
    return 0.0, -1


def _header_map(g: list, s: list) -> dict[str, int]:
    out, cur = {}, ""
    for j in range(max(len(g), len(s))):
        gn = norm(get(g, j))
        if gn:
            cur = gn
        sn = norm(get(s, j))
        out.setdefault(f"{cur}|{sn}", j)
        if not sn:
            out.setdefault(f"{cur}|", j)
    cols = {}
    for f, (grp, sub) in FIELDS.items():
        j = out.get(f"{grp}|{sub}")
        if j is None and not sub:
            j = out.get(f"{grp}|")
        if j is not None:
            cols[f] = j
    return cols


def parse(sheet: Sheet) -> ParseResult:
    res = ParseResult(kind="sales", sheet=sheet.name)
    rows = sheet.rows
    blocks = 0
    period, as_of, d_from = "MTD", None, None
    store = ""
    cols: dict[str, int] = {}
    pending: list[dict] = []
    raw_rows: list[tuple[dict, list]] = []
    i = 0
    while i < len(rows):
        row = rows[i]
        joined = " ".join(clean_text(c) for c in row if not is_blank(c))
        nj = norm(joined)
        if "REPORT NAME" in nj or "CURRENCY" in nj and "NET SALES OF" in nj:
            m = re.search(r"CURR(?:ENCY)?\s*-\s*(MTD|DAY|DAILY|YTD|WTD)", nj)
            if m:
                period = {"DAILY": "DAY"}.get(m.group(1), m.group(1))
            m = re.search(r"Net Sales of:\s*(\(\w+\)\s*)?([0-9A-Za-z/\- ]+?)(\s{2,}|Run|$)", joined)
            if m:
                as_of = parse_date(m.group(2))
            i += 1
            continue
        if nj.startswith("STORE NAME"):
            m = re.search(r"Store Name\s*:\s*(.+?)(?:\s{2,}|Report Period|$)", joined, re.I)
            store = clean_text(get(row, 0)).split(":", 1)[-1].strip() if not m else m.group(1).strip()
            store = clean_text(store.split("Report Period")[0])
            m = re.search(r"Report Period\s*:\s*([0-9/\-.]+)\s*-\s*([0-9/\-.]+)", joined, re.I)
            if m:
                d_from = parse_date(m.group(1))
                d_to = parse_date(m.group(2))
                as_of = as_of or d_to
            blocks += 1
            pending = []
            i += 1
            continue
        if norm(get(row, 0)) == "SECTION CODE NAME":
            cols = _header_map(row, rows[i + 1] if i + 1 < len(rows) else [])
            i += 2
            continue
        if blank_row(row) or not cols or not store:
            i += 1
            continue
        label = clean_text(get(row, 0))
        nl = norm(label)
        rec = None
        m = re.match(r"^([SX])(\d{3})\s*-?\s*(.*)$", label)
        if m:
            code = f"{m.group(1)}{m.group(2)}"
            rec = {"level": "section" if m.group(1) == "S" else "consignment_item", "code": code,
                   "name": m.group(3).strip(), "dept": ""}
            if m.group(1) == "S":
                pending.append(rec)
        elif nl in ("Z",):
            rec = None                                     # duplicate subtotal printed by the report: skipped
        elif nl in SUBTOTALS:
            level, code, dept = SUBTOTALS[nl]
            rec = {"level": level, "code": code, "name": label, "dept": dept}
            if level == "dept":
                for p in pending:
                    p["dept"] = dept
                pending = []
        elif nl:
            res.warn(f"Unrecognised row kept out: '{label}'")
        if rec:
            rec.update(store_raw=store, period=period, as_of=as_of.isoformat() if as_of else None,
                       d_from=d_from.isoformat() if d_from else None)
            raw_rows.append((rec, row))
        i += 1
    scale = _pct_scale(raw_rows, cols)
    for rec, row in raw_rows:
        for f, j in cols.items():
            v, is_pct = parse_num(get(row, j))
            if v is not None and f in PCT_FIELDS and not is_pct and not isinstance(get(row, j), str):
                v *= scale
            rec[f] = v
        a, g = rec.get("actual"), rec.get("growth")
        rec["ly"] = a / (1 + g / 100) if a and g is not None and g > -99.9 else None
        if rec.get("budget") in (0, None):
            rec["var_pct"] = None                          # 'Var % 0.0%' with no budget means 'no budget'
        res.rows.append(rec)
    dates = sorted({r["as_of"] for r in res.rows if r["as_of"]})
    if dates:
        res.as_of = dates[-1]
        res.month = dates[-1][:7]
    else:
        res.needs = ["as_of"]
        res.warn("The 'Net Sales of' date could not be read.")
    periods = sorted({r["period"] for r in res.rows})
    res.summary = f"{blocks} stores · {' / '.join(periods) or 'MTD'} as of {res.as_of or '?'} · {len(res.rows):,} rows"
    res.preview = [{"store": r["store_raw"], "row": r["name"], "actual": r.get("actual"), "budget": r.get("budget")}
                   for r in res.rows if r["level"] == "store"][:8]
    return res


def _pct_scale(raw_rows, cols) -> float:
    """Percentages typed as text ('(15.2%)') are already points; numeric cells from a %-formatted workbook are fractions.
    Decide from the rows where Var % can be checked against actual ÷ budget."""
    j = cols.get("var_pct")
    ja, jb = cols.get("actual"), cols.get("budget")
    if j is None or ja is None or jb is None:
        return 1.0
    frac = points = 0
    for _, row in raw_rows:
        v = get(row, j)
        if isinstance(v, str) or v is None:
            continue
        a, b = parse_num(get(row, ja))[0], parse_num(get(row, jb))[0]
        if not a or not b:
            continue
        r = a / b - 1
        if abs(v - r) < abs(v - 100 * r):
            frac += 1
        else:
            points += 1
    return 100.0 if frac > points else 1.0
