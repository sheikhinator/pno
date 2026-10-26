"""Look at a sheet the way a person would: find the header row (even under titles, logos and blank rows, or split over
two rows), then profile every column by what its values look like.

A profile is the evidence the mapper uses: share of values that are numbers, percentages, dates, employee numbers,
person names, store names, section names, job titles, genders, shift codes, ratings 1-5, years, and how many distinct
values there are. Header text alone is never trusted on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from ..po import canon
from ..stores import canon_store
from ..util import clean_text, parse_date

_NUM = re.compile(r"^\(?[-+−]?[\d,]+(\.\d+)?\)?\s*%?$")
_ID = re.compile(r"^[A-Za-z]{0,4}\d{5,10}$")
_NAME = re.compile(r"^[A-Z][A-Za-z.'\-]+(\s+[A-Z][A-Za-z.'\-]*){1,4}$")
_GENDER = {"male", "female", "m", "f", "man", "woman"}
_JOB = re.compile(r"manager|leader|supervisor|associate|cashier|stocker|sales ?person|officer|executive|head|incharge|in-charge|"
                  r"butcher|baker|cook|helper|merchandiser|clerk|controller|coordinator|analyst|assistant|director|chef|"
                  r"specialist|advisor|guard|driver|technician|receiver|picker|packer|operator|attendant|beauty", re.I)
_MONTH = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-']*(\d{2,4})?$", re.I)
_TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?(\s*[ap]m)?$", re.I)


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _txt(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return clean_text(v)


def is_num(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    return bool(_NUM.match(_txt(v).replace(" ", ""))) if _txt(v) else False


def to_num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = _txt(v).replace(",", "").replace("−", "-").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").rstrip("%")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def is_date(v: Any) -> bool:
    if isinstance(v, (date, datetime)):
        return True
    if isinstance(v, (int, float)):
        return False
    s = _txt(v)
    return bool(s) and len(s) <= 30 and parse_date(s) is not None and not _NUM.match(s)


@lru_cache(maxsize=50000)
def _is_store(t: str) -> bool:
    return bool(canon_store(t) or re.match(r"^(HM|SM|HB|H&B|PK)\b", t))


@lru_cache(maxsize=50000)
def _is_section(t: str) -> bool:
    return canon.section(t) in canon.DEPARTMENT_OF


@dataclass
class Column:
    index: int
    header: str
    values: list[Any] = field(default_factory=list)
    n: int = 0                       # non-blank values in the sample
    share: dict[str, float] = field(default_factory=dict)
    distinct: int = 0
    examples: list[str] = field(default_factory=list)
    header_date: date | None = None  # a column headed by a date (wide rosters: one column per day)

    def f(self, key: str) -> float:
        return self.share.get(key, 0.0)


@dataclass
class Table:
    header_row: int
    header_rows: int
    columns: list[Column]
    body: list[list[Any]]
    title: str = ""
    score: float = 0.0


def _valueish(v: Any) -> bool:
    """A cell that looks like data (a number, date, employee number, store or person's name), not a column title."""
    t = _txt(v)
    return bool(t) and (is_num(v) or is_date(v) or bool(_ID.match(t)) or bool(re.match(r"^(HM|SM|HB|H&B)\s+PK\b", t))
                        or bool(_NAME.match(t) and len(t.split()) >= 3))


def _row_text_score(row: list[Any]) -> tuple[float, int]:
    cells = [c for c in row if not _is_blank(c)]
    if len(cells) < 2:
        return 0.0, len(cells)
    texts = [c for c in cells if isinstance(c, str) and not _valueish(c) and len(_txt(c)) <= 60]
    dates = [c for c in cells if is_date(c)]
    if len(dates) >= 5 and len(texts) >= 2:                 # a calendar header: names, then one column per day
        return (len(texts) + len(dates)) / len(cells), len(cells)
    uniq = len({_txt(c).casefold() for c in texts})
    return (len(texts) / len(cells)) * (uniq / max(1, len(texts))), len(cells)


def _data_like(rows: list[list[Any]], width: int) -> float:
    """How much the rows under a candidate header look like records (filled, with numbers / dates / ids)."""
    if not rows:
        return 0.0
    filled = 0
    for r in rows:
        cells = [c for c in r[:width] if not _is_blank(c)]
        if len(cells) >= max(2, width * 0.3):
            filled += 1
    return filled / len(rows)


def find_tables(rows: list[list[Any]], limit: int = 40) -> list[Table]:
    """The best header row (or two-row header) and the records under it."""
    rows = [list(r) for r in rows]
    width = max((len(r) for r in rows[:200]), default=0)
    best: Table | None = None
    for i, row in enumerate(rows[:limit]):
        ts, n = _row_text_score(row)
        if ts < 0.55 or n < 2:
            continue
        below = rows[i + 1:i + 16]
        d = _data_like(below, max(n, 2))
        score = ts * 0.45 + d * 0.45 + min(n, 12) / 12 * 0.1
        if best is None or score > best.score + 1e-9:
            best = Table(header_row=i, header_rows=1, columns=[], body=[], score=score)
    if best is None or best.score < 0.45:
        # no header at all (a plain export): columns are known only by their values
        data = [r for r in rows if sum(1 for c in r if not _is_blank(c)) >= 2]
        if len(data) >= 2 and (best is None or _row_text_score(rows[best.header_row])[0] < 0.9):
            head = [""] * width
            t = Table(header_row=-1, header_rows=0, columns=profile_columns(head, data), body=data, score=0.4)
            if sum(1 for c in t.columns if max(c.share.values(), default=0) >= 0.85) >= 2:
                return [t]
        if best is None:
            return []
    i = best.header_row
    head = [_txt(c) for c in rows[i]] + [""] * (width - len(rows[i]))
    # a group title row above: 'Employee | | Exit | |' over 'Number | Name | Date | Type | Reason'
    if i > 0:
        above = [_txt(c) for c in rows[i - 1]] + [""] * (width - len(rows[i - 1]))
        filled = [a for a in above if a]
        if 1 <= len(filled) < sum(1 for h in head if h) and not any(_valueish(c) for c in rows[i - 1] if not _is_blank(c)) \
                and any(not above[j] for j in range(width) if head[j]):
            carry, merged = "", []
            for j in range(width):
                carry = above[j] or carry
                merged.append(" ".join(x for x in ((carry if head[j] else ""), head[j]) if x).strip())
            head = merged
    # two-row headers: 'Net Sales' over 'Actual | Budget | Gth %'
    nxt = rows[i + 1] if i + 1 < len(rows) else []
    ts2, n2 = _row_text_score(nxt)
    spans = sum(1 for j, c in enumerate(nxt[:width]) if not _is_blank(c) and j < len(head) and not head[j])
    if ts2 >= 0.7 and n2 >= 2 and spans >= 1 and not any(_valueish(c) for c in nxt) and _data_like(rows[i + 2:i + 12], 2) > 0.5:
        sub = [_txt(c) for c in nxt] + [""] * (width - len(nxt))
        carry = ""
        merged = []
        for j in range(width):
            carry = head[j] or carry if head[j] else carry
            top = head[j] or (carry if sub[j] else "")
            merged.append(" ".join(x for x in (top, sub[j]) if x).strip())
        head, best.header_rows = merged, 2
    title = " ".join(_txt(c) for r in rows[:i] for c in r if not _is_blank(c))[:200]
    body = [r for r in rows[i + best.header_rows:] if any(not _is_blank(c) for c in r)]
    best.columns = profile_columns(head, body)
    best.body, best.title = body, title
    return [best]


def profile_columns(head: list[str], body: list[list[Any]], sample: int = 400) -> list[Column]:
    cols = []
    rows = body[:sample]
    for j, h in enumerate(head):
        vals = [r[j] for r in rows if j < len(r) and not _is_blank(r[j])]
        c = Column(index=j, header=h, values=vals, n=len(vals))
        hd = parse_date(h) if h and not is_num(h) else None
        c.header_date = hd
        if not vals:
            cols.append(c)
            continue
        n = len(vals)
        txts = [_txt(v) for v in vals]
        numeric = [to_num(v) for v in vals if is_num(v)]
        sh = {
            "num": len(numeric) / n,
            "pct": sum(1 for t in txts if t.endswith("%")) / n,
            "date": sum(1 for v in vals if is_date(v)) / n,
            "time": sum(1 for t in txts if _TIME.match(t)) / n,
            "id": sum(1 for t in txts if _ID.match(t)) / n,
            "name": sum(1 for t in txts if _NAME.match(t) and not _JOB.search(t) and not canon_store(t)) / n,
            "store": sum(1 for t in txts if _is_store(t)) / n,
            "section": sum(1 for t in txts if _is_section(t)) / n,
            "job": sum(1 for t in txts if _JOB.search(t) and len(t) < 50) / n,
            "gender": sum(1 for t in txts if t.casefold() in _GENDER) / n,
            "shift": sum(1 for t in txts if canon.shift(t) not in ("Other", "Not rostered") and len(t) <= 12) / n,
            "rating": sum(1 for x in numeric if x is not None and 1 <= x <= 5) / n,
            "year": sum(1 for x in numeric if x is not None and float(x).is_integer() and 2000 <= x <= 2100) / n,
            "month": sum(1 for t in txts if _MONTH.match(t)) / n,
            "long_text": sum(1 for t in txts if len(t) > 40) / n,
            "nps": sum(1 for x in numeric if x is not None and -100 <= x <= 100) / n,
            "small_int": sum(1 for x in numeric if x is not None and float(x).is_integer() and 0 <= x <= 1000) / n,
            "money": sum(1 for x in numeric if x is not None and abs(x) >= 1000) / n,
        }
        c.share = sh
        c.distinct = len({t.casefold() for t in txts})
        c.examples = list(dict.fromkeys(txts))[:5]
        cols.append(c)
    return cols
