"""Periods nobody sent a file for, worked out from the files that were sent (additive measures only)."""

from __future__ import annotations

from pno.po import derive
from pno.po.insights import Insights


def imp(iid, t, f, to, rows):
    return {"iid": iid, "type": t, "from": f, "to": to, "rows": rows}


def sale(store, actual, budget, ly, margin=20.0):
    return {"store": store, "line": "Total Store", "code": "", "section": "", "level": "total", "actual": actual,
            "budget": budget, "last_year": ly, "margin_pct": margin, "customers": 10}


def test_mtd_from_two_ytds():
    ytd_sep = imp(2, "ytd", "2026-01", "2026-09", [sale("A", 900, 1000, 800), sale("B", 50, 40, 30)])
    ytd_aug = imp(1, "ytd", "2026-01", "2026-08", [sale("A", 800, 880, 720)])
    rows, how = derive.derive("po_sales", [ytd_sep, ytd_aug], "2026-09", "2026-09")
    a = next(r for r in rows if r["store"] == "A")
    assert (a["actual"], a["budget"], a["last_year"]) == (100, 120, 80)
    assert round(a["growth_pct"], 1) == 25.0 and a["margin_pct"] is None          # ratios are never subtracted
    assert next(r for r in rows if r["store"] == "B")["actual"] == 50               # new in the period: kept whole
    assert "YTD to Sep 2026" in how and a["_derived"] == how


def test_ytd_from_monthly_files_and_partial_ytd():
    months = [imp(i, "mtd", m, m, [{"store": "A", "section": "Bakery", "section_raw": "Bakery", "count": i}])
              for i, m in enumerate(["2026-01", "2026-02", "2026-03"], start=1)]
    rows, how = derive.derive("po_da", months, "2026-01", "2026-03")
    assert rows[0]["count"] == 6 and "sum of 3 monthly files" in how
    assert derive.derive("po_da", months[:2], "2026-01", "2026-03") is None          # a month missing: no guess
    full = imp(9, "ytd", "2026-01", "2026-09", [{"store": "A", "section": "Bakery", "section_raw": "Bakery", "count": 10}])
    q1 = imp(8, "ytd", "2026-01", "2026-03", [{"store": "A", "section": "Bakery", "section_raw": "Bakery", "count": 4}])
    rows, _ = derive.derive("po_da", [full, q1], "2026-04", "2026-09")
    assert rows[0]["count"] == 6


def test_ratios_are_not_derived():
    assert derive.derive("po_shrink", [imp(1, "ytd", "2026-01", "2026-09", [{"x": 1}])], "2026-09", "2026-09") is None
    assert not derive.can_derive("po_nps") and not derive.can_derive("po_productivity")


class _Store:
    def __init__(self, rows):
        self._rows = rows

    def records(self):
        return self._rows


def _rec(kind, iid, t, f, to, **kw):
    return {"_kind": kind, "_iid": iid, "_ptype": t, "_pfrom": f, "_pto": to, "_source": "f", "_sheet": "s", **kw}


def test_screen_uses_worked_out_month():
    recs = [_rec("po_da", 1, "ytd", "2026-01", "2026-08", store="A", section="Bakery", section_raw="Bakery", count=3),
            _rec("po_da", 2, "ytd", "2026-01", "2026-09", store="A", section="Bakery", section_raw="Bakery", count=5)]
    ins = Insights(_Store(recs), view={"type": "mtd", "to": "2026-09"})
    assert ins.rows("po_da")[0]["count"] == 2
    cov = next(c for c in ins.coverage if c["kind"] == "po_da")
    assert cov["derived"] and "YTD to Sep 2026" in cov["how"] and not ins.notes
    ytd = Insights(_Store(recs), view={"type": "ytd", "from": "2026-01", "to": "2026-09"})
    assert ytd.rows("po_da")[0]["count"] == 5 and not ytd.notes
