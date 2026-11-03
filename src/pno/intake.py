"""4.3 Guided intake: one report at a time, from the Data tab checklist.

The director clicks a report that is missing (or one already in), gives a file or pastes cells, and P&O
  1. reads and cleans it (every exact reader, then Smart Import; messy rows, totals and text numbers handled),
  2. makes sure it IS the report that was asked for (re-reading it that way if another type was guessed),
  3. fills what can be worked out (last year from growth, budget from variance, or from data already loaded),
  4. verifies it: rows, stores recognised, sections, the columns that matter for that report, the period,
     and lists everything it changed,
  5. says green / amber / red, and only saves when asked.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .po import canon

# for each report: the columns that must be there, and the ones that make it complete
NEEDS: dict[str, dict[str, Any]] = {
    "sales": {"must": [("actual", "Net sales")], "want": [("budget", "Budget"), (("ly", "growth"), "Last year / growth")], "store": "store_raw",
              "section": "name", "only": lambda r: r.get("level") == "section"},
    "productivity": {"must": [("actual", "Productivity")], "want": [("target", "Target")], "store": "store_raw", "section": "row_name"},
    "po_shrink": {"must": [(("shrink_actual_pct", "stock_days_actual"), "Shrinkage % or stock days")],
                  "want": [("shrink_budget_pct", "Shrinkage budget"), ("stock_days_budget", "Stock days budget")], "store": "store", "section": "section"},
    "po_nps": {"must": [("nps", "NPS score")], "want": [("section", "Section / category"), ("year", "Year")], "city": "city"},
    "po_da": {"must": [("count", "Cases")], "want": [("section", "Section")], "store": "store", "section": "section"},
    "roster": {"must": [("emp_no", "Employee number"), ("name", "Name")], "want": [("designation", "Designation"), ("bu", "Store"),
                                                                                ("joining", "Joining date")], "store": "bu"},
    "po_role": {"must": [(("employee_id", "employee_name"), "Employee")], "want": [("role_since", "In role since"), ("designation", "Designation")]},
    "po_rating": {"must": [(("employee_id", "employee_name"), "Employee"), ("rating", "Rating")], "want": [("cycle", "Year")]},
    "po_turnover": {"must": [(("employee_id", "employee_name"), "Employee"), ("date", "Leaving date")], "want": [("reason", "Reason"), ("store", "Store")],
                    "store": "store"},
    "attendance": {"must": [("emp_no", "Employee number"), ("day", "Date")], "want": [(("t_in", "minutes"), "Punch times / hours")]},
    "leave": {"must": [("emp_no", "Employee number"), ("d_from", "From date")], "want": [("d_to", "To date"), ("type", "Leave type")]},
    "po_shift": {"must": [(("employee_id", "employee_name"), "Employee")], "want": [("date", "Date"), ("shift", "Shift")]},
}


def _has(rows: list[dict], keys) -> float:
    keys = keys if isinstance(keys, tuple) else (keys,)
    if not rows:
        return 0.0
    return sum(1 for r in rows if any(r.get(k) not in (None, "") for k in keys)) / len(rows)


def pick(analyses: list[dict], kind: str) -> tuple[dict, int, bool] | None:
    """The sheet that is the report asked for: one already read that way, else the first that can be read that way."""
    from . import importers
    for a in analyses:
        for i, r in enumerate(a["results"]):
            if r.kind == kind and r.rows:
                return a, i, False
    best = None
    for a in analyses:
        for i, r in enumerate(a["results"]):
            try:
                new = importers.reparse(a, r, kind)
            except ValueError:
                continue
            if new.rows and (best is None or len(new.rows) > len(best[2].rows)):
                best = (a, i, new)
    if best is None:
        # not readable as it stands: stores across the columns, several tables, or turned on its side
        from .importers import reshape
        from .importers.base import ParseResult
        for a in analyses:
            for i, r in enumerate(a["results"]):
                sh = (a.get("sheets") or {}).get(r.sheet)
                for v, note in reshape.variants(sh, kind) if sh is not None else []:
                    a.setdefault("sheets", {})[v.name] = v
                    try:
                        new = importers.reparse(a, ParseResult(kind="dataset", sheet=v.name), kind)
                    except ValueError:
                        continue
                    if new.rows and (best is None or len(new.rows) > len(best[2].rows)):
                        new.warn(note)
                        best = (a, i, new)
    if best:
        a, i, new = best
        a["results"][i] = new
        return a, i, True
    return None


def fill(api, kind: str, rows: list[dict], period: dict) -> list[str]:
    """Work out missing figures. Sales: last year from growth, budget from variance %, and when the file has no budget
    or last year at all, take them from sales already loaded for the same period (store × section)."""
    notes: list[str] = []
    if kind != "sales":
        return notes
    n_ly = n_b = 0
    for r in rows:
        a, g, v = r.get("actual"), r.get("growth"), r.get("var_pct")
        if r.get("ly") in (None, 0) and a and g is not None and g > -99.9:
            r["ly"] = a / (1 + g / 100)
            n_ly += 1
        if r.get("budget") in (None,) and a and v is not None and v > -99.9:
            r["budget"] = a / (1 + v / 100)
            n_b += 1
    if n_ly:
        notes.append(f"Last year worked out from growth % on {n_ly} line{'s' if n_ly != 1 else ''}.")
    if n_b:
        notes.append(f"Budget worked out from variance % on {n_b} line{'s' if n_b != 1 else ''}.")
    need_b = not any(r.get("budget") for r in rows)
    need_ly = not any(r.get("ly") for r in rows)
    if (need_b or need_ly) and period.get("to"):
        have = {}
        for x in api.db.q("""SELECT s.store_raw, s.code, s.budget, s.ly FROM sales s JOIN imports i ON i.id = s.import_id
                              WHERE i.active=1 AND i.period_type=? AND i.period_to=?""", (period.get("type"), period.get("to"))) if _table(api.db, "sales") else []:
            have[(canon.store(x["store_raw"]), x["code"])] = (x["budget"], x["ly"])
        if have:
            got_b = got_ly = 0
            for r in rows:
                b, ly = have.get((canon.store(r.get("store_raw")), r.get("code")), (None, None))
                if need_b and b and not r.get("budget"):
                    r["budget"], got_b = b, got_b + 1
                if need_ly and ly and not r.get("ly"):
                    r["ly"], got_ly = ly, got_ly + 1
                if r.get("actual") is not None and r.get("budget"):
                    r["var_pct"] = round(100 * (r["actual"] / r["budget"] - 1), 1)
                if r.get("actual") is not None and r.get("ly"):
                    r["growth"] = round(100 * (r["actual"] / r["ly"] - 1), 1)
            if got_b:
                notes.append(f"Budget taken from the sales already loaded for this period on {got_b} line{'s' if got_b != 1 else ''}.")
            if got_ly:
                notes.append(f"Last year taken from the sales already loaded for this period on {got_ly} line{'s' if got_ly != 1 else ''}.")
    return notes


def _table(db, name: str) -> bool:
    return bool(db.q1("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)))


def _median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def sanity(kind: str, rows: list[dict]) -> list[tuple[str, str]]:
    """Do the numbers make sense together? Catches budget and last year swapped with sales, % read as fractions,
    the same column read twice."""
    out: list[tuple[str, str]] = []
    pairs = {"sales": [("actual", "budget", "Net sales", "Budget"), ("actual", "ly", "Net sales", "Last year")],
             "productivity": [("actual", "target", "Productivity", "Target")],
             "po_shrink": [("shrink_actual_pct", "shrink_budget_pct", "Shrinkage", "Shrinkage budget")]}.get(kind, [])
    for a, b, la, lb in pairs:
        both = [(r.get(a), r.get(b)) for r in rows if isinstance(r.get(a), (int, float)) and isinstance(r.get(b), (int, float)) and r.get(b)]
        if len(both) < 3:
            continue
        if all(x == y for x, y in both):
            out.append(("warn", f"{la} and {lb} are the same on every row: the same column may have been read twice. Match the columns below."))
            continue
        m = _median([x / y for x, y in both])
        if m is not None and (m > 5 or m < 0.2):
            out.append(("warn", f"{la} is about {m:.1f}× {lb} on a typical row, which is unusual: they may be in different units or swapped. "
                                f"Check the columns below."))
        else:
            out.append(("good", f"{la} and {lb} are in the same range."))
    if kind == "sales":
        neg = sum(1 for r in rows if isinstance(r.get("actual"), (int, float)) and r["actual"] < 0)
        if neg > max(2, 0.2 * len(rows)):
            out.append(("warn", f"Net sales is negative on {neg} rows: is this a variance column instead?"))
    if kind == "po_nps":
        bad = [r.get("nps") for r in rows if isinstance(r.get("nps"), (int, float)) and not -100 <= r["nps"] <= 100]
        if bad:
            out.append(("warn", f"{len(bad)} NPS values are outside −100…100."))
    if kind == "po_shrink":
        big = [r.get("shrink_actual_pct") for r in rows if isinstance(r.get("shrink_actual_pct"), (int, float)) and abs(r["shrink_actual_pct"]) > 25]
        if big:
            out.append(("warn", f"{len(big)} shrinkage figures are above 25%: is a value column read as a percentage?"))
    return out


def verify(kind: str, res, period: dict, fills: list[str], reread: bool, asked_label: str) -> dict:
    """Green / amber / red, with every check in plain words."""
    spec = NEEDS.get(kind, {"must": [], "want": []})
    rows = [r for r in res.rows if spec["only"](r)] or res.rows if spec.get("only") else res.rows
    checks: list[dict] = []
    add = lambda level, text: checks.append({"level": level, "text": text})  # noqa: E731
    if not rows:
        return {"status": "bad", "checks": [{"level": "bad", "text": "No rows could be read."}], "headline": "Nothing could be read from this file."}
    add("good", f"{len(rows):,} row{'s' if len(rows) != 1 else ''} read" + (f" from '{res.sheet}'" if res.sheet else "") + ".")
    if reread:
        add("warn", f"P&O first read this as something else; it was read again as {asked_label} because you asked for that. Check the numbers below.")
    missing_must = []
    for keys, label in spec["must"]:
        share = _has(rows, keys)
        if share >= 0.6:
            add("good", f"{label}: found" + ("" if share > 0.98 else f" on {round(100 * share)}% of rows") + ".")
        else:
            missing_must.append(label)
            add("bad", f"{label}: not found." if share == 0 else f"{label}: only on {round(100 * share)}% of rows.")
    for keys, label in spec["want"]:
        share = _has(rows, keys)
        if share >= 0.6:
            add("good", f"{label}: found.")
        else:
            add("warn", f"{label}: not in this file" + (" (some screens will show '—')." if share == 0 else f" (only {round(100 * share)}% of rows)."))
    if spec.get("store"):
        names = [str(r.get(spec["store"]) or "") for r in rows if r.get(spec["store"])]
        known = {n for n in names if canon.store_city(canon.store(n))}
        unknown = sorted({n for n in names if n not in known})
        if names:
            stores = {canon.store(n) for n in known}
            add("good" if not unknown else "warn", f"{len(stores)} store{'s' if len(stores) != 1 else ''} recognised" +
                (f"; not recognised: {', '.join(unknown[:5])}{'…' if len(unknown) > 5 else ''} (Settings → Stores links them)" if unknown else "."))
    if spec.get("section"):
        secs = Counter(canon.section(str(r.get(spec["section"]) or "")) for r in rows if r.get(spec["section"]))
        if secs:
            add("good", f"{len(secs)} section{'s' if len(secs) != 1 else ''}.")
    if spec.get("city"):
        cities = sorted({r.get("city") for r in rows if r.get("city")})
        fmts = Counter(r.get("format") or "Hypermarket" for r in rows)
        add("good" if cities else "bad", f"Cities: {', '.join(cities) or 'none recognised'} · " + ", ".join(f"{k.lower()} survey" for k in fmts))
    if period.get("type") and period["type"] != "general":
        lab = {"ytd": "Year to date", "mtd": "Month"}.get(period["type"], period["type"])
        add("good", f"Period: {lab} {period.get('from') or ''}{'–' if period.get('from') and period.get('to') != period.get('from') else ''}"
                    f"{period.get('to') if period.get('to') != period.get('from') else ''}.".replace("  ", " "))
    for lvl, text in sanity(kind, rows):
        add(lvl, text)
    for w in res.warnings or []:
        add("info", w)
    for f in fills:
        add("info", f)
    status = "bad" if missing_must else ("warn" if any(c["level"] == "warn" for c in checks) else "good")
    head = {"good": f"This is {asked_label}, and everything needed is there.",
            "warn": f"This is {asked_label}. Some parts are missing or were changed: check the list, then save.",
            "bad": f"This doesn't give {asked_label}: " + ", ".join(missing_must) + " missing."}[status]
    return {"status": status, "checks": checks, "headline": head}


def merge(kind: str, rows: list[dict], extra: list[dict]) -> str:
    """Fill the columns this file lacks from a second file of the same report (matched by store and section,
    or by employee). Returns a plain-words note."""
    spec = NEEDS.get(kind, {})
    st, se = spec.get("store"), spec.get("section")

    def key(r):
        if kind.startswith("po_") and (r.get("employee_id") or r.get("employee_name")) and not st:
            return ("emp", str(r.get("employee_id") or r.get("employee_name")).strip().upper())
        if kind in ("roster", "attendance", "leave"):
            return ("emp", str(r.get("emp_no") or "").strip())
        return (canon.store(r.get(st)) if st else "", (r.get("code") or canon.section(str(r.get(se) or ""))) if se else "", r.get("level", ""))
    have = {}
    for r in extra:
        have.setdefault(key(r), r)
    fields = {f for r in extra for f, v in r.items() if v not in (None, "")}
    missing = {f for f in fields if not any(r.get(f) not in (None, "") for r in rows)}
    n = 0
    for r in rows:
        o = have.get(key(r))
        if not o:
            continue
        hit = False
        for f in missing:
            if o.get(f) not in (None, ""):
                r[f] = o[f]
                hit = True
        n += hit
    if kind == "sales":
        for r in rows:
            a = r.get("actual")
            if a is not None and r.get("budget"):
                r["var_pct"] = round(100 * (a / r["budget"] - 1), 1)
            if a is not None and r.get("ly"):
                r["growth"] = round(100 * (a / r["ly"] - 1), 1)
    from .importers import KIND_LABEL  # noqa: F401
    if not missing:
        return "The second file adds nothing this one doesn't already have."
    names = ", ".join(sorted(missing))
    return f"Added {names} from the second file on {n} of {len(rows)} rows." if n else f"The second file has {names}, but no rows matched (different stores or sections)."


def layout_sig(kind: str, columns: list[dict]) -> str:
    heads = sorted({" ".join(str(c.get("header") or "").upper().split()) for c in columns if c.get("header")})
    return kind + "|" + "|".join(heads)[:600] if heads else ""
