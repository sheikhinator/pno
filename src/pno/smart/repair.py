"""Fix a messy sheet before it is read: the AI (or P&O's own engine) plans the edits, P&O makes them on a COPY.

Privacy: the AI is never sent cell values. It gets the column titles and the *shape* of each cell
('999 AAA Aaaaaaa', '9,999,999', blank), and replies with a plan in a small fixed vocabulary. P&O applies the
plan itself, on this computer, to a copy of the sheet, and shows the director the before / after for review.

Edits ("ops"):
  header      {"rows": [0, 1]}                  titles spread over these rows (merged cells, a group heading) → one title row
  drop_blank  {"columns": [4]}                  drop rows where all these columns are blank (subtotal / spacer lines)
  drop_match  {"column": 4, "pattern": "total"} drop rows whose cell matches (case-insensitive regex)
  fill_down   {"columns": [0]}                  repeat a grouped label down the blank cells below it
  strip       {"column": 4, "pattern": "^\\d+\\s+"}  remove a pattern from a column's text (store numbers, prefixes)
  rename      {"column": 6, "title": "Net Sales"} give a column a clear title
  scale       {"column": 7, "factor": 100}       multiply a column (fractions → %)
  drop_columns {"columns": [8, 9]}
  unpivot     {"keep": [0], "name": "Store", "value": "Net Sales"}  columns after 'keep' are stores → one row per store
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..reader import Sheet
from ..util import is_blank

OPS = ("header", "drop_blank", "drop_match", "fill_down", "strip", "rename", "scale", "drop_columns", "unpivot")
LIMIT = 60000


def shape(v: Any) -> str:
    """A cell's shape without its content: letters → a/A, digits → 9."""
    if is_blank(v):
        return "·"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "num" if abs(v) < 1e15 else "bignum"
    s = str(v).strip()[:28]
    return re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", re.sub(r"\d", "9", s)))


def _texty(v) -> bool:
    return isinstance(v, str) and bool(re.search(r"[A-Za-z]", v)) and not re.fullmatch(r"[\d,.\s%()-]+", v)


def _numy(v) -> bool:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return True
    return isinstance(v, str) and bool(re.fullmatch(r"\s*\(?-?[\d,]+(\.\d+)?\)?%?\s*", v))


def _width(rows) -> int:
    return max((len(r) for r in rows[:200]), default=0)


def _pad(rows) -> list[list]:
    w = _width(rows)
    return [list(r) + [None] * (w - len(r)) for r in rows]


# ------------------------------------------------------------------ the engine's own plan (no AI needed)
def header_band(rows: list[list]) -> tuple[int, int] | None:
    """(first, last) rows of the titles when they run over more than one row."""
    for i in range(min(20, len(rows) - 2)):
        r0, r1 = rows[i], rows[i + 1]
        t0 = [j for j, c in enumerate(r0) if _texty(c)]
        t1 = [j for j, c in enumerate(r1) if _texty(c)]
        if len(t0) < 1 or len(t1) < 1 or len(t0) + len(t1) < 3:
            continue
        if any(_numy(c) for c in r0 if not is_blank(c)) or any(_numy(c) for c in r1 if not is_blank(c)):
            continue
        # the next row is data (some numbers) and the two title rows fill different columns
        nxt = rows[i + 2]
        if sum(_numy(c) for c in nxt) < 1:
            continue
        if set(t1) - set(t0) and (set(t0) - set(t1) or len(t0) < len(t1)):
            return i, i + 1
    return None


def engine_plan(sheet: Sheet, kind: str | None = None) -> list[dict]:
    rows = _pad([r for r in sheet.rows])
    plan: list[dict] = []
    band = header_band(rows)
    hi = band[1] if band else next((i for i, r in enumerate(rows[:25]) if sum(_texty(c) for c in r) >= 3), 0)
    if band:
        plan.append({"op": "header", "rows": [band[0], band[1]], "why": "The titles run over two rows (merged cells): combined into one."})
    body = rows[hi + 1:]
    if not body:
        return plan
    w = len(rows[0]) if rows else 0
    n = len(body)
    filled = {j: [r[j] for r in body if not is_blank(r[j])] for j in range(w)}
    textual = [j for j in range(w) if filled[j] and sum(_texty(v) for v in filled[j]) >= 0.8 * len(filled[j])]
    title = lambda j: str(rows[hi][j] or (rows[band[0]][j] if band else "") or f"column {j + 1}")  # noqa: E731
    # grouped labels: a text column written once at the start of each group (fill down before looking for subtotals)
    grouped = [j for j in textual if 0.04 * n < len(filled[j]) < 0.6 * n and not is_blank(body[0][j])
               and len(set(map(str, filled[j]))) >= 0.8 * len(filled[j])]
    for j in grouped:
        plan.append({"op": "fill_down", "columns": [j], "why": f"'{title(j)}' is written once per group: repeated down."})
    # subtotal lines: rows with numbers whose key text columns are blank while most rows have them
    key = [j for j in textual if j not in grouped and len(filled[j]) >= 0.6 * n]
    holes = [j for j in key if len(filled[j]) < n]
    if holes:
        sub = [r for r in body if all(is_blank(r[j]) for j in holes) and any(_numy(c) for c in r)]
        if 0 < len(sub) <= 0.35 * n:
            plan.append({"op": "drop_blank", "columns": holes, "why": f"{len(sub)} subtotal line{'s' if len(sub) != 1 else ''} (no {', '.join(title(j) for j in holes[:2])}) removed."})
    text_cols = textual
    tot = [j for j in text_cols if any(re.match(r"^\s*(grand\s*)?total\b", str(r[j] or ""), re.I) for r in body)]
    for j in tot[:1]:
        plan.append({"op": "drop_match", "column": j, "pattern": r"^\s*(grand\s*)?total\b", "why": "Total lines removed (P&O adds totals up itself)."})
    return plan


# ------------------------------------------------------------------ the AI's plan
def ai_prompt(sheet: Sheet, kind: str, label: str, fields: list[str]) -> str:
    rows = _pad(sheet.rows[:18])
    band = header_band(_pad(sheet.rows[:40]))
    first = next((i for i, r in enumerate(rows) if sum(_texty(c) for c in r) >= 3), 0)
    last_title = max(band[1] if band else first, first)       # only title rows are shown as text; nothing below them
    lines = []
    for i, r in enumerate(rows):
        cells = [str(c).strip()[:30] if (i <= last_title and _texty(c) and not any(_numy(x) for x in r if not is_blank(x))) else shape(c) for c in r]
        lines.append(f"row {i}: " + " | ".join(cells))
    n = len(sheet.rows)
    return (f"A spreadsheet that should be '{label}' has {n} rows and {_width(sheet.rows)} columns. Title rows are shown as text; every other cell "
            f"only as its shape (A/a = letters, 9 = digit, num = number, · = blank):\n" + "\n".join(lines) +
            f"\n\nIt will be read by a parser that needs one title row and then one record per row, with these fields: {', '.join(fields)}.\n"
            "Plan the edits that make it so, using ONLY these ops (row and column numbers start at 0, as shown):\n"
            "header{rows}, drop_blank{columns}, drop_match{column,pattern}, fill_down{columns}, strip{column,pattern}, rename{column,title}, "
            "scale{column,factor}, drop_columns{columns}, unpivot{keep,name,value}.\n"
            'Reply with JSON only: {"ops": [{"op": "...", ..., "why": "<short reason>"}], "mapping": {"<field>": <column number after the edits>}, '
            '"why": "<one sentence>"}. Use as few ops as needed; an empty list is fine if the sheet is already clean.')


def parse_plan(text: str, width: int) -> tuple[list[dict], dict, str]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("The AI's plan could not be read.")
    ans = json.loads(m.group(0))
    ops = []
    for o in ans.get("ops") or []:
        if not isinstance(o, dict) or o.get("op") not in OPS:
            continue
        ok = all(isinstance(c, int) and 0 <= c < max(width, 1) * 4 for c in (o.get("columns") or []) + ([o["column"]] if "column" in o else []))
        if o["op"] == "header" and not (isinstance(o.get("rows"), list) and all(isinstance(x, int) and 0 <= x < 40 for x in o["rows"])):
            ok = False
        if o.get("pattern") is not None:
            try:
                re.compile(str(o["pattern"]))
            except re.error:
                ok = False
        if ok:
            ops.append(o)
    mapping = {f: int(j) for f, j in (ans.get("mapping") or {}).items() if str(j).lstrip("-").isdigit()}
    return ops, mapping, str(ans.get("why") or "")


# ------------------------------------------------------------------ making the edits, on a copy
def _apply_one(rows: list[list], o: dict, hi: int) -> tuple[list[list], int, str]:
    op = o["op"]
    w = len(rows[0]) if rows else 0
    if op == "header":
        rr = sorted({x for x in o["rows"] if x < len(rows)})
        if len(rr) < 2:
            return rows, hi, ""
        out_h, carry = [], [""] * len(rr)
        for j in range(w):
            parts = []
            for k, ri in enumerate(rr):
                v = rows[ri][j]
                below = [rows[x][j] for x in rr[k + 1:]]
                if not is_blank(v):
                    carry[k] = str(v).strip()
                    parts.append(carry[k])
                elif k < len(rr) - 1 and carry[k] and any(not is_blank(b) for b in below) and j and not is_blank(rows[rr[-1]][j - 1]):
                    parts.append(carry[k])                       # a group heading spread over the columns to its right
                else:
                    carry[k] = ""
            out_h.append(" ".join(dict.fromkeys(parts)) or None)
        keep = [r for i, r in enumerate(rows) if i not in rr[1:]]
        keep[rr[0]] = out_h
        return keep, rr[0], f"Titles in rows {', '.join(str(x + 1) for x in rr)} combined into one row."
    body_start = hi + 1
    head, body = rows[:body_start], rows[body_start:]
    if op == "drop_blank":
        cols = [c for c in o["columns"] if c < w]
        new = [r for r in body if not all(is_blank(r[c]) for c in cols)]
        return head + new, hi, f"{len(body) - len(new)} rows without {', '.join(str(head[-1][c] or f'column {c + 1}') for c in cols[:2])} removed."
    if op == "drop_match":
        c, pat = o["column"], re.compile(str(o["pattern"]), re.I)
        if c >= w:
            return rows, hi, ""
        new = [r for r in body if not pat.search(str(r[c] or ""))]
        return head + new, hi, f"{len(body) - len(new)} rows matching '{o['pattern']}' in {head[-1][c] or f'column {c + 1}'} removed."
    if op == "fill_down":
        n = 0
        for c in [c for c in o["columns"] if c < w]:
            last = None
            for r in body:
                if is_blank(r[c]) and last is not None and any(not is_blank(x) for x in r):
                    r[c] = last
                    n += 1
                elif not is_blank(r[c]):
                    last = r[c]
        return rows, hi, f"{n} blank cells filled with the label above."
    if op == "strip":
        c, pat = o["column"], re.compile(str(o["pattern"]))
        if c >= w:
            return rows, hi, ""
        n = 0
        for r in body:
            if isinstance(r[c], str):
                new = pat.sub("", r[c]).strip()
                n += new != r[c]
                r[c] = new
        return rows, hi, f"Text '{o['pattern']}' removed from {n} cells of {head[-1][c] or f'column {c + 1}'}."
    if op == "rename":
        c = o["column"]
        if c >= w:
            return rows, hi, ""
        old = head[-1][c]
        head[-1][c] = str(o["title"])[:60]
        return rows, hi, f"Column '{old or f'{c + 1}'}' titled '{head[-1][c]}'."
    if op == "scale":
        c, f = o["column"], float(o.get("factor") or 1)
        if c >= w:
            return rows, hi, ""
        n = 0
        for r in body:
            v = r[c]
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                r[c] = v * f
                n += 1
        return rows, hi, f"{head[-1][c] or f'Column {c + 1}'} multiplied by {f:g} on {n} rows."
    if op == "drop_columns":
        cols = set(c for c in o["columns"] if c < w)
        names = [str(head[-1][c] or f"column {c + 1}") for c in sorted(cols)]
        return [[v for j, v in enumerate(r) if j not in cols] for r in rows], hi, f"Columns removed: {', '.join(names)}."
    if op == "unpivot":
        keep = [c for c in o.get("keep", []) if c < w]
        others = [j for j in range(w) if j not in keep and not is_blank(head[-1][j])]
        out = [[head[-1][c] for c in keep] + [o.get("name") or "Store", o.get("value") or "Value"]]
        for r in body:
            for j in others:
                if not is_blank(r[j]):
                    out.append([r[c] for c in keep] + [head[-1][j], r[j]])
        return head[:-1] + out, hi, f"{len(others)} columns turned into one row each ({len(out) - 1} rows)."
    return rows, hi, ""


def apply(sheet: Sheet, ops: list[dict]) -> tuple[Sheet, list[dict]]:
    rows = _pad([list(r) for r in sheet.rows[:LIMIT]])
    hi = next((i for i, r in enumerate(rows[:25]) if sum(_texty(c) for c in r) >= 2), 0)
    log = []
    for o in ops:
        try:
            rows, hi, what = _apply_one(rows, o, hi)
        except Exception as e:  # noqa: BLE001 - one bad step never loses the sheet
            what = f"Skipped a step ({o.get('op')}): {e}"
        if what:
            log.append({"op": o["op"], "what": what, "why": o.get("why", "")})
        if o["op"] == "header":
            hi = min(o["rows"])
    return Sheet(name=f"{sheet.name} · fixed", rows=rows, hidden=sheet.hidden, kind=sheet.kind), log


def preview(sheet: Sheet, n: int = 10) -> list[list[str]]:
    out = []
    for r in sheet.rows[:n]:
        out.append(["" if is_blank(c) else (f"{c:,.0f}" if isinstance(c, float) and abs(c) >= 1000 else str(c))[:40] for c in r[:12]])
    return out


def to_xlsx(sheet: Sheet) -> bytes:
    import io

    import xlsxwriter
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet((sheet.name or "Fixed")[:31].replace("/", "-").replace(":", "-"))
    for i, r in enumerate(sheet.rows):
        for j, v in enumerate(r):
            if not is_blank(v):
                ws.write(i, j, v)
    wb.close()
    return buf.getvalue()
