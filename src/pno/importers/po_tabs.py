"""The P&O review workbook tabs PNO did not read before: ratings, time in role, turnover, DA, NPS, shrinkage & stock
days and the monthly shift roster. Each tab is recognised by its columns (never its name)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from ..po import tabs
from ..reader import Sheet
from .base import ParseResult

LABELS = {
    "po_rating": "Performance ratings", "po_role": "Time in current role", "po_turnover": "Turnover (leavers)",
    "po_da": "Disciplinary actions (DA)", "po_nps": "Customer NPS", "po_shrink": "Shrinkage & stock days",
    "po_shift": "Shift roster (M / Mid / E)",
}


def _make(kind: str) -> SimpleNamespace:
    def score(sheet: Sheet) -> tuple[float, int]:
        try:
            return (0.97, 0) if tabs.detect(sheet.rows) == kind else (0.0, -1)
        except Exception:
            return 0.0, -1

    def parse(sheet: Sheet) -> ParseResult:
        parsed = tabs.parse_sheet(sheet.name, sheet.rows, kind)
        res = ParseResult(kind=kind, sheet=sheet.name, rows=parsed.records if parsed else [])
        res.summary = parsed.summary if parsed else ""
        for w in (parsed.warnings if parsed else []):
            res.warn(w)
        res.month = _month(kind, res.rows)
        res.as_of = None
        res.preview = [{k: v for k, v in r.items() if not isinstance(v, (list, dict))} for r in res.rows[:8]]
        return res

    return SimpleNamespace(score=score, parse=parse)


def _month(kind: str, rows: list[dict]) -> str:
    dates = sorted(r.get("date") for r in rows if r.get("date"))
    if kind in ("po_shift", "po_turnover") and dates:
        return dates[-1][:7]
    return date.today().strftime("%Y-%m")


PARSERS = [(kind, _make(kind)) for kind in LABELS]
