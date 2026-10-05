"""Reading the values that MAF reports throw at us: numbers in brackets, arrows, times, durations and dates."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta
from typing import Any

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTHS["sept"] = 9


def is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def clean_text(v: Any) -> str:
    """Visible text of a cell: trimmed, single-spaced, no invisible characters."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).replace(" ", " ").replace("​", "")
    return re.sub(r"\s+", " ", s).strip()


def norm(v: Any) -> str:
    """Comparison key: upper case, accents removed, punctuation reduced to single spaces."""
    s = unicodedata.normalize("NFKD", clean_text(v)).encode("ascii", "ignore").decode()
    s = s.upper().replace("&", " AND ")
    return re.sub(r"[^A-Z0-9%]+", " ", s).strip()


def title_name(v: Any) -> str:
    """'kashan rehman' -> 'Kashan Rehman'; keeps already mixed-case names as they are."""
    s = clean_text(v)
    if s and (s.islower() or s.isupper()):
        s = " ".join(w[:1].upper() + w[1:].lower() for w in s.split(" "))
    return s


def emp_code(v: Any) -> str:
    """Employee numbers arrive as 20064066, 20064066.0 or ' 20064066 '."""
    s = clean_text(v)
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return s


# ------------------------------------------------------------------------------------------------ numbers
_NUM = re.compile(r"[-+]?\d[\d,]*\.?\d*|[-+]?\.\d+")


def parse_num(v: Any) -> tuple[float | None, bool]:
    """Returns (value, written_as_percent). Handles 1,234  (15.2%)  -195  '▲ 3%'  '▼ -6%'  '▬ 0%'  1,725.3%."""
    if v is None or isinstance(v, bool):
        return None, False
    if isinstance(v, (int, float)):
        f = float(v)
        return (f if f == f and abs(f) != float("inf") else None), False
    s = clean_text(v)
    if not s or s in {"-", "--", "—", "N/A", "NA", "#N/A", "#DIV/0!", "#VALUE!", "#REF!"}:
        return None, False
    down = "▼" in s or "↓" in s
    neg = s.startswith("(") and s.endswith(")") or bool(re.match(r"^\(\s*[\d.,]+\s*%?\s*\)$", s))
    pct = "%" in s
    m = _NUM.search(s.replace(" ", ""))
    if not m:
        return None, False
    try:
        f = float(m.group(0).replace(",", ""))
    except ValueError:
        return None, False
    if neg and f > 0:
        f = -f
    if down and f > 0:
        f = -f
    return f, pct


def num(v: Any) -> float | None:
    return parse_num(v)[0]


# ------------------------------------------------------------------------------------------------ times
def parse_clock(v: Any) -> str | None:
    """A punch time ('15:45:24', a time object, an Excel fraction) as 'HH:MM'; 'Not Marked', 0 and blanks are None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, datetime):
        return v.strftime("%H:%M")
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, timedelta):
        mins = int(v.total_seconds() // 60) % 1440
        return f"{mins // 60:02d}:{mins % 60:02d}"
    if isinstance(v, (int, float)):
        if 0 < v < 1:
            mins = int(round(v * 1440)) % 1440
            return f"{mins // 60:02d}:{mins % 60:02d}"
        return None
    s = clean_text(v)
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?$", s, re.I)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    ap = (m.group(4) or "").upper()
    if ap == "PM" and h < 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def parse_duration(v: Any) -> int | None:
    """Worked hours ('9:36', '10:31', 9.5, a time or timedelta cell) as minutes. 'Absent' and blanks are None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, timedelta):
        return int(round(v.total_seconds() / 60))
    if isinstance(v, time):
        return v.hour * 60 + v.minute
    if isinstance(v, datetime):          # Excel durations above 24h become dates in 1900
        base = datetime(1899, 12, 30)
        return int(round((v - base).total_seconds() / 60)) if v.year < 1901 else v.hour * 60 + v.minute
    if isinstance(v, (int, float)):
        if v <= 0:
            return 0 if v == 0 else None
        if v < 1.5:                       # fraction of a day
            return int(round(v * 1440))
        if v <= 24:                       # decimal hours
            return int(round(v * 60))
        return None
    s = clean_text(v)
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    try:
        f = float(s)
    except ValueError:
        return None
    return parse_duration(f)


def span_minutes(t_in: str | None, t_out: str | None) -> int | None:
    """Minutes between two punches; an OUT before the IN is an overnight shift."""
    if not t_in or not t_out:
        return None
    a = int(t_in[:2]) * 60 + int(t_in[3:5])
    b = int(t_out[:2]) * 60 + int(t_out[3:5])
    d = b - a
    if d < 0:
        d += 1440
    return d


def fmt_minutes(m: int | None) -> str:
    if m is None:
        return "—"
    return f"{m // 60}:{m % 60:02d}"


# ------------------------------------------------------------------------------------------------ dates
def parse_date(v: Any, dayfirst: bool = True) -> date | None:
    """'1-Aug-26', '19/12/2025', '2026-08-01', '(Fri) 02-Oct-26', Excel dates and serial numbers."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):
        if 20000 < v < 80000:
            return (datetime(1899, 12, 30) + timedelta(days=int(v))).date()
        return None
    s = clean_text(v)
    s = re.sub(r"^\(\w+\)\s*", "", s)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})[-/ .]([A-Za-z]{3,9})[-/ .,]*(\d{2,4})", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        mon = MONTHS[m.group(2)[:3].lower()]
        y = int(m.group(3))
        return _mk(y + 2000 if y < 100 else y, mon, int(m.group(1)))
    m = re.search(r"([A-Za-z]{3,9})[ -](\d{1,2}),?[ -](\d{4})", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        return _mk(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        d, mo = (a, b) if dayfirst else (b, a)
        if mo > 12 and d <= 12:
            d, mo = mo, d
        return _mk(y, mo, d)
    return None


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def month_of(d: date | str) -> str:
    if isinstance(d, str):
        return d[:7]
    return f"{d.year:04d}-{d.month:02d}"


def month_bounds(month: str) -> tuple[date, date]:
    y, m = int(month[:4]), int(month[5:7])
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    return start, end


def prev_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y - (m == 1):04d}-{(m - 2) % 12 + 1:02d}"


def month_label(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return date(y, m, 1).strftime("%B %Y")
