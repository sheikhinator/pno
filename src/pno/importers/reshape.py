"""Other ways a table can be laid out, tried when a sheet can't be read as it stands.

  * several tables on one sheet (split at blank rows, or where a title row repeats),
  * stores across the columns ('Section | LAH Fortress | ISB Centaurus | …'): turned into one row per store,
  * turned on its side (titles down the first column): turned the right way up.

Each variant is a new Sheet plus a plain-words note of what was done, so the director sees every change.
"""

from __future__ import annotations

from ..reader import Sheet
from ..util import is_blank, norm

VALUE_TITLE = {"sales": "Net Sales", "productivity": "Productivity Actual", "po_nps": "NPS", "po_shrink": "Shrinkage %",
               "po_da": "Cases", "dataset": "Value"}


def _blank(row) -> bool:
    return all(is_blank(c) for c in row)


def _texty(c) -> bool:
    return isinstance(c, str) and c.strip() != "" and not c.strip().replace(",", "").replace(".", "").replace("%", "").lstrip("-").isdigit()


def split_tables(sheet: Sheet) -> list[Sheet]:
    """Blocks separated by blank rows (2 or more data rows each)."""
    blocks, cur = [], []
    for r in sheet.rows:
        if _blank(r):
            if cur:
                blocks.append(cur)
            cur = []
        else:
            cur.append(r)
    if cur:
        blocks.append(cur)
    blocks = [b for b in blocks if len(b) >= 3]
    if len(blocks) < 2:
        return []
    return [Sheet(name=f"{sheet.name} · table {i}", rows=b, kind=sheet.kind) for i, b in enumerate(blocks, 1)]


def _store_cols(row) -> list[int]:
    from ..po import canon
    out = []
    for j, c in enumerate(row):
        if _texty(c):
            s = canon.store(c)
            if s and canon.store_city(s):
                out.append(j)
    return out


def melt_stores(sheet: Sheet, kind: str = "dataset") -> Sheet | None:
    """Stores across the columns → one row per (row label, store)."""
    for hi, row in enumerate(sheet.rows[:15]):
        cols = _store_cols(row)
        if len(cols) < 3:
            continue
        labels = [j for j in range(min(cols)) if not is_blank(row[j]) or j == 0]
        head = [str(row[j]).strip() if not is_blank(row[j]) else ("Section" if k == 0 else f"Column {j + 1}") for k, j in enumerate(labels)]
        title = next((str(c).strip() for r in sheet.rows[:hi] for c in r if _texty(c)), "")
        value = title if (kind == "dataset" and title) else VALUE_TITLE.get(kind, "Value")
        out = [head + ["Store", value]]
        for r in sheet.rows[hi + 1:]:
            if _blank(r):
                continue
            lab = [r[j] if j < len(r) else None for j in labels]
            if all(is_blank(x) for x in lab) or (isinstance(lab[0], str) and norm(lab[0]).startswith(("TOTAL", "GRAND TOTAL"))):
                continue
            for j in cols:
                v = r[j] if j < len(r) else None
                if not is_blank(v):
                    out.append(lab + [row[j], v])
        if len(out) > 2:
            return Sheet(name=f"{sheet.name} · one row per store", rows=out, kind=sheet.kind)
    return None


def transpose(sheet: Sheet) -> Sheet | None:
    """Titles down the first column and records across: turn it the right way up."""
    rows = [r for r in sheet.rows if not _blank(r)]
    if len(rows) < 3:
        return None
    first = [r[0] if r else None for r in rows]
    top = rows[0]
    if len([c for c in top if not is_blank(c)]) < 3:
        return None
    if sum(_texty(c) for c in first) < 0.7 * len(first) or sum(_texty(c) for c in top[1:]) > 0.5 * max(1, len(top) - 1):
        return None
    w = max(len(r) for r in rows)
    grid = [[(r[j] if j < len(r) else None) for r in rows] for j in range(w)]
    return Sheet(name=f"{sheet.name} · turned", rows=grid, kind=sheet.kind)


def variants(sheet: Sheet, kind: str = "dataset") -> list[tuple[Sheet, str]]:
    out: list[tuple[Sheet, str]] = []
    m = melt_stores(sheet, kind)
    if m is not None:
        out.append((m, "Stores were across the columns; turned into one row per store."))
    for t in split_tables(sheet):
        out.append((t, f"This sheet holds more than one table; read '{t.name.split(' · ')[-1]}' on its own."))
        mt = melt_stores(t, kind)
        if mt is not None:
            out.append((mt, f"'{t.name.split(' · ')[-1]}' had stores across the columns; turned into one row per store."))
    tr = transpose(sheet)
    if tr is not None:
        out.append((tr, "The titles ran down the first column; the table was turned the right way up."))
    return out
