"""What period a sheet covers: general (true for every period), month to date (MTD) or year to date (YTD).

The default is worked out from the report type, the file and sheet name ("YTD Productivity August", "Stock Days YTDSEP")
and the dates inside the rows; the user can change it on the import screen. A period is stored on the import as
period_type ('general' | 'mtd' | 'ytd'), period_from and period_to (YYYY-MM).
"""

from __future__ import annotations

import re
from datetime import date

TYPES = {"general": "General · applies to every period", "mtd": "Month to date (MTD)", "ytd": "Year to date (YTD)"}
SHORT = {"general": "General", "mtd": "MTD", "ytd": "YTD"}

# Employee master, reporting lines, time in role, rating cycles, leave: true whatever period is being analysed.
GENERAL_KINDS = {"roster", "po_master", "po_role", "po_rating", "leave", "holiday"}
# Rows carry their own date, so any period can be cut from them.
DATED_KINDS = {"po_turnover", "po_shift", "attendance"}
# The P&O workbook tabs are year-to-date unless the name says otherwise.
YTD_KINDS = {"po_nps", "po_shrink", "po_da", "po_turnover"}

_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_MONTH_RX = re.compile(r"(?:(?<=YTD)|(?<=MTD)|(?<![A-Z]))(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|"
                       r"NOVEMBER|DECEMBER|JAN|FEB|MAR|APR|JUN|JUL|AUG|SEPT|SEP|OCT|NOV|DEC)(?![A-Z])")


def month_label(ym: str | None) -> str:
    if not ym:
        return ""
    try:
        y, m = int(ym[:4]), int(ym[5:7])
    except ValueError:
        return ym
    return f"{_MONTHS[m - 1].title()} {y}"


def label(ptype: str | None, pfrom: str | None, pto: str | None) -> str:
    if ptype == "general" or not ptype:
        return "General"
    if ptype == "mtd":
        return f"MTD {month_label(pto)}".strip()
    if pfrom and pto and pfrom != pto:
        same_year = pfrom[:4] == pto[:4]
        start = _MONTHS[int(pfrom[5:7]) - 1].title() + ("" if same_year else f" {pfrom[:4]}")
        return f"YTD {start}–{month_label(pto)}"
    return f"YTD {month_label(pto)}".strip()


def _name_month(text: str, year_hint: int | None) -> str | None:
    up = text.upper().replace("_", " ")
    m = _MONTH_RX.search(up)
    if not m:
        return None
    mon = _MONTHS.index(m.group(1)[:3]) + 1
    y = re.search(r"\b(20\d\d)\b", up)
    year = int(y.group(1)) if y else (year_hint or date.today().year)
    if not y and date(year, mon, 1) > date.today():
        year -= 1
    return f"{year:04d}-{mon:02d}"


def _row_dates(rows: list[dict]) -> list[str]:
    out = []
    for r in rows[:20000]:
        for k in ("date", "day", "as_of", "period_to"):
            v = r.get(k)
            if v and re.match(r"\d{4}-\d\d", str(v)):
                out.append(str(v)[:10])
                break
    return sorted(out)


def guess(kind: str, rows: list[dict], name: str, month: str | None = None, as_of: str | None = None) -> dict:
    """The most likely period of a parsed sheet: {'type', 'from', 'to', 'why', 'sure'}.

    'sure' is False when nothing in the sheet pointed to a month (P&O tabs without dates): the import screen then lines the
    month up with the other sheets of the same import."""
    up = name.upper()
    dates = _row_dates(rows)
    named = _name_month(name, int(dates[-1][:4]) if dates else None)
    if kind in GENERAL_KINDS:
        return {"type": "general", "from": None, "to": None, "why": "Employee and structure data apply to every period.", "sure": True}
    periods = {str(r.get("period") or "").upper() for r in rows[:5000]} - {""}
    if "YTD" in up or periods == {"YTD"}:
        ptype, why = "ytd", "The name says YTD." if "YTD" in up else "The report's rows are year to date."
    elif "MTD" in up or periods == {"MTD"}:
        ptype, why = "mtd", "The name says MTD." if "MTD" in up else "The report's rows are month to date."
    elif dates and dates[0][:7] != dates[-1][:7]:
        ptype, why = "ytd", f"Rows run from {dates[0]} to {dates[-1]}."
    elif dates:
        ptype, why = "mtd", f"All rows fall in {month_label(dates[0][:7])}."
    elif kind in YTD_KINDS or kind == "dataset" and "YEAR" in up:
        ptype, why = "ytd", "P&O workbook tabs are year to date."
    elif kind == "dataset":
        return {"type": "general", "from": None, "to": None, "why": "No period found in the sheet.", "sure": False}
    else:
        ptype, why = "mtd", "Monthly report."
    weak_month = kind.startswith("po_") and not dates            # P&O tab readers fill in today's month
    to = (as_of or "")[:7] or named or (dates[-1][:7] if dates else None) or (None if weak_month else month)
    sure = bool(to)
    if not to:
        to = month or date.today().strftime("%Y-%m")
    if ptype == "mtd":
        frm = to
    elif dates and dates[0][:7] < to:
        frm = dates[0][:7]
    else:
        frm = f"{to[:4]}-01"
    return {"type": ptype, "from": frm, "to": to, "why": why, "sure": sure}


def line_up(results: list[dict], known: str | None = None) -> None:
    """Sheets with no month of their own take the month the other sheets of the same import agree on (or, failing
    that, the latest month already imported)."""
    sure = [r["period"]["to"] for r in results if r["period"].get("sure") and r["period"]["type"] in ("ytd", "mtd") and r["period"]["to"]]
    if not sure and known:
        sure = [known]
    if not sure:
        return
    common = max(set(sure), key=lambda m: (sure.count(m), m))
    for r in results:
        p = r["period"]
        if p.get("sure") or p["type"] not in ("ytd", "mtd"):
            continue
        p["to"], p["lined"] = common, True
        p["from"] = common if p["type"] == "mtd" else f"{common[:4]}-01"
        p["why"] += f" Month taken from the other data ({month_label(common)}); change it if needed."


def clean(ptype: str | None, pfrom: str | None, pto: str | None, fallback: dict) -> tuple[str, str | None, str | None]:
    """The period the user chose, made consistent (from ≤ to, MTD is one month, general has no months)."""
    ptype = ptype if ptype in TYPES else fallback.get("type") or "general"
    if ptype == "general":
        return "general", None, None
    ok = lambda v: v if v and re.fullmatch(r"\d{4}-\d\d", str(v)) else None  # noqa: E731
    pto = ok(pto) or fallback.get("to") or date.today().strftime("%Y-%m")
    if ptype == "mtd":
        return "mtd", pto, pto
    pfrom = ok(pfrom) or (fallback.get("from") if fallback.get("type") == "ytd" else None) or f"{pto[:4]}-01"
    if pfrom > pto:
        pfrom, pto = pto, pfrom
    return "ytd", pfrom, pto


def default_for_kind(kind: str) -> str:
    """For imports saved before periods existed."""
    if kind in GENERAL_KINDS:
        return "general"
    return "ytd" if kind in YTD_KINDS else "mtd"
