"""Data explorer: any imported table, charted and explained automatically.

Picks the best way to read a table (which column to group by, which number to measure), builds the charts and writes
plain-English insights. Everything is computed here; the AI, when available, only adds wording on top.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import Any

MEASURE_PRIORITY = ["actual", "count", "score", "budget", "target", "last_year", "forecast", ""]
GROUP_PRIORITY = ["_store", "store", "_section", "section", "department", "city", "type", "reason", "designation", "employee_name", ""]


def datasets(db) -> list[dict]:
    out = []
    for r in db.q("""SELECT r.payload, i.id, i.file_name, i.rows, i.created_at FROM po_records r JOIN imports i ON i.id=r.import_id
                     WHERE i.active=1 AND r.kind='dataset_meta' ORDER BY i.id DESC"""):
        meta = json.loads(r["payload"])
        out.append({"id": r["id"], "title": meta.get("title") or r["file_name"], "file": r["file_name"], "rows": r["rows"],
                    "columns": len(meta.get("columns", [])), "created": r["created_at"], "ai_title": meta.get("ai_title"),
                    "description": meta.get("ai_description", "")})
    return out


def load(db, import_id: int) -> tuple[dict, list[dict]]:
    meta_row = db.q1("SELECT payload FROM po_records WHERE import_id=? AND kind='dataset_meta'", (import_id,))
    if not meta_row:
        raise ValueError("Dataset not found.")
    meta = json.loads(meta_row[0])
    rows = [json.loads(r[0]) for r in db.q("SELECT payload FROM po_records WHERE import_id=? AND kind='dataset' ORDER BY id", (import_id,))]
    return meta, rows


def _columns(meta: dict, rows: list[dict]) -> list[dict]:
    cols = [dict(c) for c in meta.get("columns", [])]
    for virtual, label in (("_store", "Store (matched)"), ("_section", "Section (matched)")):
        if any(r.get(virtual) for r in rows):
            vals = {r.get(virtual) for r in rows if r.get(virtual)}
            cols.insert(0, {"name": virtual, "label": label, "type": "text", "role": virtual, "distinct": len(vals)})
    for c in cols:
        c.setdefault("label", c["name"])
    return cols


def pick(cols: list[dict], rows: list[dict]) -> tuple[str | None, str | None, str | None]:
    """(group-by column, measure column, date column) that make the clearest first chart."""
    n = len(rows) or 1
    groups = [c for c in cols if c["type"] == "text" and 2 <= c.get("distinct", 0) <= max(40, n // 2 if n < 80 else 40)]
    group = None
    for role in GROUP_PRIORITY:
        hit = next((c for c in groups if c.get("role") == role), None)
        if hit:
            group = hit["name"]
            break
    if group is None and groups:
        group = min(groups, key=lambda c: abs(c.get("distinct", 0) - 10))["name"]
    measures = [c for c in cols if c["type"] in ("number", "percent")]
    measure = None
    for role in MEASURE_PRIORITY:
        hit = next((c for c in measures if c.get("role") == role), None)
        if hit:
            measure = hit["name"]
            break
    date_col = next((c["name"] for c in cols if c["type"] == "date"), None)
    return group, measure, date_col


def _agg(values: list[float], how: str) -> float | None:
    if not values:
        return None
    if how == "avg":
        return sum(values) / len(values)
    if how == "count":
        return float(len(values))
    if how == "max":
        return max(values)
    if how == "min":
        return min(values)
    return sum(values)


def default_agg(col: dict | None) -> str:
    if not col:
        return "count"
    return "avg" if col["type"] == "percent" or col.get("role") in ("score", "target") else "sum"


def view(db, import_id: int, group: str | None = None, measure: str | None = None, agg: str | None = None) -> dict:
    meta, rows = load(db, import_id)
    cols = _columns(meta, rows)
    by_name = {c["name"]: c for c in cols}
    g0, m0, date_col = pick(cols, rows)
    group = None if group == "__none" else (group if group in by_name else g0)
    measure = measure if (measure in by_name or measure == "__count") else m0
    if measure == "__count":
        measure = None
    agg = agg or default_agg(by_name.get(measure))
    if measure is None:
        agg = "count"
    grouped: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        key = str(r.get(group) or "—") if group else "All"
        v = r.get(measure) if measure else 1.0
        if isinstance(v, (int, float)):
            grouped[key].append(float(v))
        elif measure is None:
            grouped[key].append(1.0)
    series = sorted(((k, _agg(v, agg)) for k, v in grouped.items()), key=lambda kv: -(kv[1] or 0))
    trend = []
    if date_col:
        per: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            d = r.get(date_col)
            if not d:
                continue
            key = str(d)[:7] if len({str(x.get(date_col))[:10] for x in rows}) > 62 else str(d)[:10]
            v = r.get(measure) if measure else 1.0
            if isinstance(v, (int, float)):
                per[key].append(float(v))
        trend = sorted((k, _agg(v, agg if measure else "count")) for k, v in per.items())
    numeric = [c for c in cols if c["type"] in ("number", "percent")]
    totals = []
    for c in numeric[:6]:
        vals = [float(r[c["name"]]) for r in rows if isinstance(r.get(c["name"]), (int, float))]
        if vals:
            how = default_agg(c)
            totals.append({"name": c["name"], "value": _agg(vals, how), "agg": how, "type": c["type"]})
    return {
        "id": import_id, "title": meta.get("ai_title") or meta.get("title"), "file": meta.get("file"),
        "description": meta.get("ai_description", ""), "rows": len(rows), "columns": cols, "group": group, "measure": measure,
        "agg": agg, "date": date_col, "series": series[:40], "series_count": len(series), "trend": trend[-60:],
        "totals": totals, "insights": insights(cols, rows, group, measure, agg, series, trend),
        "table": rows[:1000], "warnings": meta.get("warnings", []), "ai_insights": meta.get("ai_insights"),
    }


def _fmt(v: float | None, col: dict | None = None) -> str:
    if v is None:
        return "—"
    if col and col.get("type") == "percent":
        return f"{v:.1f}%"
    if abs(v) >= 1e9:
        return f"{v / 1e9:,.2f} bn"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.1f} M"
    return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.2f}"


def insights(cols: list[dict], rows: list[dict], group: str | None, measure: str | None, agg: str,
             series: list[tuple[str, float | None]], trend: list[tuple[str, float | None]]) -> list[str]:
    by_name = {c["name"]: c for c in cols}
    mcol = by_name.get(measure) if measure else None
    mlabel = (measure or "Rows").lower() if measure else "rows"
    glabel = (by_name.get(group, {}).get("label") or group or "").replace(" (matched)", "").lower()
    plural = (glabel + ("es" if glabel.endswith(("s", "x", "ch")) else "s")) if glabel else "groups"
    out: list[str] = [f"{len(rows):,} rows and {len(cols)} columns."]
    vals = [(k, v) for k, v in series if v is not None]
    if group and len(vals) >= 2:
        top, bottom = vals[0], vals[-1]
        word = {"sum": "total", "avg": "average", "count": "count", "max": "highest", "min": "lowest"}[agg]
        out.append(f"Highest {glabel} by {word} {mlabel}: **{top[0]}** ({_fmt(top[1], mcol)}); lowest: **{bottom[0]}** ({_fmt(bottom[1], mcol)}).")
        total = sum(v for _, v in vals)
        if agg in ("sum", "count") and total > 0 and len(vals) >= 4:
            share = 100 * sum(v for _, v in vals[:3]) / total
            out.append(f"The top 3 {plural} account for **{share:.0f}%** of the {word}.")
        numbers = [v for _, v in vals]
        if len(numbers) >= 5:
            mean, sd = statistics.mean(numbers), statistics.pstdev(numbers)
            outliers = [k for k, v in vals if sd and abs(v - mean) > 2 * sd]
            if outliers:
                out.append(f"Stands out from the rest (more than 2 standard deviations): {', '.join(outliers[:5])}.")
            above = sum(1 for v in numbers if v > mean)
            out.append(f"{above} of {len(numbers)} {plural} are above the average of {_fmt(mean, mcol)}.")
    # actual against a plan column
    actual = next((c for c in cols if c.get("role") == "actual"), None)
    for plan_role, word in (("budget", "budget"), ("target", "target"), ("last_year", "last year")):
        plan = next((c for c in cols if c.get("role") == plan_role), None)
        if actual and plan and actual["type"] == plan["type"] == "number":
            a = sum(float(r[actual["name"]]) for r in rows if isinstance(r.get(actual["name"]), (int, float)) and isinstance(r.get(plan["name"]), (int, float)))
            p = sum(float(r[plan["name"]]) for r in rows if isinstance(r.get(actual["name"]), (int, float)) and isinstance(r.get(plan["name"]), (int, float)))
            if p:
                pct = 100 * a / p
                line = f"Overall {actual['name']} is **{pct:.1f}%** of {word}" if plan_role != "last_year" else \
                    f"Overall {actual['name']} is **{pct - 100:+.1f}%** vs last year"
                if group:
                    per = defaultdict(lambda: [0.0, 0.0])
                    for r in rows:
                        if isinstance(r.get(actual["name"]), (int, float)) and isinstance(r.get(plan["name"]), (int, float)):
                            per[str(r.get(group) or "—")][0] += float(r[actual["name"]])
                            per[str(r.get(group) or "—")][1] += float(r[plan["name"]])
                    ratios = sorted(((k, 100 * x / y) for k, (x, y) in per.items() if y), key=lambda kv: kv[1])
                    if len(ratios) >= 2:
                        line += f"; weakest {glabel}: **{ratios[0][0]}** ({ratios[0][1]:.1f}%), strongest: **{ratios[-1][0]}** ({ratios[-1][1]:.1f}%)"
                    below = sum(1 for _, x in ratios if x < 100)
                    if plan_role != "last_year" and ratios:
                        line += f". {below} of {len(ratios)} are below {word}"
                out.append(line + ".")
    if len(trend) >= 3:
        first, last = trend[0], trend[-1]
        peak = max(trend, key=lambda kv: kv[1] or 0)
        if first[1]:
            change = 100 * ((last[1] or 0) - first[1]) / first[1]
            out.append(f"From {first[0]} to {last[0]} the {mlabel} moved **{change:+.0f}%**; the peak was {peak[0]} ({_fmt(peak[1], mcol)}).")
    missing = [c["name"] for c in cols if c.get("filled") is not None and c["filled"] < 0.8 * len(rows)]
    if missing:
        out.append(f"Columns with many blanks: {', '.join(missing[:5])}.")
    emp = next((c for c in cols if c.get("role") == "employee_id"), None)
    if emp:
        ids = [r.get(emp["name"]) for r in rows if r.get(emp["name"])]
        dup = len(ids) - len(set(ids))
        if dup:
            out.append(f"{dup} repeated {emp['name']} value(s): some people appear more than once.")
    return out


def summary_for_ai(v: dict) -> str:
    """A compact description of a dataset (no raw rows beyond a few) for the AI to write insights from."""
    cols = [{k: c.get(k) for k in ("name", "type", "role", "distinct", "sample")} for c in v["columns"]]
    return json.dumps({"title": v["title"], "rows": v["rows"], "columns": cols, "grouped_by": v["group"], "measure": v["measure"],
                       "aggregation": v["agg"], "groups": v["series"][:25], "trend": v["trend"][-24:], "totals": v["totals"],
                       "computed_insights": v["insights"], "sample_rows": v["table"][:5]}, default=str)[:12000]
