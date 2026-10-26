"""Work out a period nobody sent a file for, from the files that were sent.

Only measures that add up can be derived: sales, budget, last year, customers, disciplinary cases. Then
    MTD Sep = YTD Sep − YTD Aug          (two year-to-date files of the same year)
    YTD Jan–Sep = MTD Jan + … + MTD Sep  (every month present)
    YTD Apr–Sep = YTD Jan–Sep − YTD Jan–Mar
Percentages and ratios (productivity, shrinkage %, NPS, margin %) are never subtracted or summed: they are worked out
again from the derived parts where possible (growth vs last year) and otherwise left empty, so a wrong number is never
shown. Every derived row says how it was made.
"""

from __future__ import annotations

from typing import Any

# kind -> (row identity fields, additive fields, ratios re-computed from the parts)
ADDITIVE: dict[str, dict[str, Any]] = {
    "po_sales": {"key": ("store", "line", "code", "section", "level"),
                 "sum": ("actual", "budget", "last_year", "customers"),
                 "blank": ("margin_pct", "waste_pct", "margin_after_waste_pct", "oos_pct", "basket", "asp", "avg_stock",
                           "customers_growth_pct")},
    "po_da": {"key": ("store", "section", "section_raw"), "sum": ("count",), "blank": ()},
}


def month_add(ym: str, n: int) -> str:
    y, m = divmod(int(ym[:4]) * 12 + int(ym[5:7]) - 1 + n, 12)
    return f"{y:04d}-{m + 1:02d}"


def months(a: str, b: str) -> list[str]:
    out, m = [], a
    while m <= b:
        out.append(m)
        m = month_add(m, 1)
    return out


def can_derive(kind: str) -> bool:
    return kind in ADDITIVE


def _key(spec: dict, r: dict) -> tuple:
    return tuple(str(r.get(k) or "") for k in spec["key"])


def _finish(kind: str, rows: list[dict], how: str, vf: str, vt: str) -> list[dict]:
    spec = ADDITIVE[kind]
    for r in rows:
        for f in spec["blank"]:
            r[f] = None
        if kind == "po_sales":
            a, ly = r.get("actual"), r.get("last_year")
            r["growth_pct"] = (100.0 * (a / ly - 1)) if isinstance(a, (int, float)) and isinstance(ly, (int, float)) and ly else None
            r["period_from"], r["period_to"] = f"{vf}-01", f"{vt}-28"
            r["period"] = "MTD" if vf == vt else "YTD"
        r["_derived"] = how
    return rows


def subtract(kind: str, later: list[dict], earlier: list[dict], how: str, vf: str, vt: str) -> list[dict]:
    """Rows of `later` minus the same rows of `earlier` (rows only in `later` are new in the period and kept whole)."""
    spec = ADDITIVE[kind]
    before = {_key(spec, r): r for r in earlier}
    out = []
    for r in later:
        b = before.get(_key(spec, r))
        n = dict(r)
        for f in spec["sum"]:
            x, y = r.get(f), (b or {}).get(f)
            if isinstance(x, (int, float)):
                n[f] = x - y if isinstance(y, (int, float)) else (x if b is None else None)
            else:
                n[f] = None
        out.append(n)
    return _finish(kind, out, how, vf, vt)


def add_up(kind: str, parts: list[list[dict]], how: str, vf: str, vt: str) -> list[dict]:
    """Rows of several months added together by identity."""
    spec = ADDITIVE[kind]
    acc: dict[tuple, dict] = {}
    for rows in parts:
        for r in rows:
            k = _key(spec, r)
            if k not in acc:
                acc[k] = dict(r)
                continue
            for f in spec["sum"]:
                x, y = acc[k].get(f), r.get(f)
                acc[k][f] = (x or 0) + (y or 0) if isinstance(x, (int, float)) or isinstance(y, (int, float)) else None
    return _finish(kind, list(acc.values()), how, vf, vt)


def derive(kind: str, imports: list[dict], vf: str, vt: str) -> tuple[list[dict], str] | None:
    """Rows for the window vf..vt worked out from the imports (each {'type','from','to','rows','iid'}), or None."""
    if kind not in ADDITIVE:
        return None
    timed = [i for i in imports if i["type"] in ("mtd", "ytd") and i["from"] and i["to"]]

    def latest(pred):
        hits = [i for i in timed if pred(i)]
        return max(hits, key=lambda i: i["iid"]) if hits else None

    def lab(ym: str) -> str:
        from .insights import _ml
        return _ml(ym)

    # 1. cumulative to vt minus cumulative to the month before vf (same start)
    for later in sorted((i for i in timed if i["to"] == vt and i["from"] <= vf), key=lambda i: -i["iid"]):
        if later["from"] == vf:
            break                      # already exactly the window: not a derivation
        earlier = latest(lambda i: i["from"] == later["from"] and i["to"] == month_add(vf, -1))
        if earlier:
            how = (f"{'YTD' if later['type'] == 'ytd' else 'Total'} to {lab(vt)} − {'YTD' if earlier['type'] == 'ytd' else 'total'} "
                   f"to {lab(earlier['to'])}")
            return subtract(kind, [dict(r) for r in later["rows"]], earlier["rows"], how, vf, vt), how
    # 2. every month present as its own MTD file
    per_month = [latest(lambda i, m=m: i["type"] == "mtd" and i["from"] == m and i["to"] == m) for m in months(vf, vt)]
    if len(per_month) > 1 and all(per_month):
        how = f"sum of {len(per_month)} monthly files ({lab(vf)}–{lab(vt)})"
        return add_up(kind, [i["rows"] for i in per_month], how, vf, vt), how
    return None
