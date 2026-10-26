"""Smart import: read any HR or store file, whatever its name or layout.

    profile.py  find the header (under titles, over two rows), profile each column by its values
    schema.py   the fields P&O uses, with the many names HR systems give them, and the report types built from them
    mapper.py   choose the report type, map columns to fields, rewrite into the layout P&O's readers know
    checks.py   discrepancies: duplicates, unknown stores, impossible dates, ratings out of range, people missing
                from the employee master, totals that don't add up
"""

from __future__ import annotations

from typing import Any

from ..importers.base import KIND_LABEL, ParseResult
from ..reader import Sheet
from . import checks, mapper
from .schema import FIELDS, KINDS

SMART_KINDS = {"roster", "po_role", "po_rating", "po_turnover", "leave", "attendance", "po_shift", "po_da", "sales_simple"}
MIN_SCORE = 0.55


def _parse_rewritten(kind: str, sheet: Sheet, file_name: str) -> ParseResult | None:
    from ..importers import PARSERS
    mod = dict(PARSERS).get(kind)
    if mod is None:
        return None
    if mod.score(sheet)[0] <= 0:
        return None
    return mod.parse(sheet, file_name) if kind == "productivity" else mod.parse(sheet)


def read(sheet: Sheet, file_name: str = "", fixed: dict[str, int] | None = None, kind: str | None = None,
         min_score: float = MIN_SCORE) -> tuple[ParseResult | None, list[mapper.Match]]:
    """The best reading of a sheet P&O has no exact reader for. (None, candidates) when nothing fits well enough."""
    cands = mapper.analyse(sheet, file_name, fixed, kind)
    for m in cands:
        if m.score < (0.0 if kind else min_score):
            break
        res = build(m, sheet, file_name)
        if res and res.rows:
            return res, cands
    return None, cands


def build(m: mapper.Match, sheet: Sheet, file_name: str = "") -> ParseResult | None:
    if m.kind in ("po_da", "sales_simple"):
        rows = mapper.build_records(m)
        kind = "sales" if m.kind == "sales_simple" else m.kind
        res = ParseResult(kind=kind, sheet=sheet.name, rows=rows)
        if kind == "sales":
            for r in rows:
                r.update(period="MTD", as_of=None, d_from=None)
            res.summary = f"{len(rows)} stores · sales{' vs budget' if any(r.get('budget') for r in rows) else ''}"
            res.needs = ["month"]
        else:
            res.summary = f"{sum(r['count'] for r in rows)} cases · {len({r['store'] for r in rows})} stores"
        res.preview = rows[:8]
    else:
        res = _parse_rewritten(m.kind, mapper.rewrite(m, sheet), file_name)
        if res is None:
            return None
    res.confidence = round(m.score, 2)
    res.extra = {**res.extra, "smart": True, "mapping": m.describe(), "why": m.why,
                 "columns": [{"index": c.index, "header": c.header, "examples": c.examples[:3]} for c in (m.table.columns if m.table else [])],
                 "table_title": m.table.title if m.table else ""}
    res.warn(f"Read by Smart Import as {KIND_LABEL.get(res.kind, res.kind)} from its columns ({round(100 * m.score)}% sure). "
             "Check the column matches if anything looks wrong.")
    return res


def field_choices() -> list[dict[str, str]]:
    return [{"value": k, "label": v["label"]} for k, v in FIELDS.items()]


def kind_choices() -> list[dict[str, str]]:
    return [{"value": k, "label": v["label"]} for k, v in KINDS.items()]


def summarise(res: ParseResult) -> dict[str, Any]:
    return {"issues": checks.validate(res.kind, res.rows)}
