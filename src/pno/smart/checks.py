"""Discrepancies found while reading a file, explained in plain words before anything is saved."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta
from typing import Any

from ..po import canon
from ..stores import canon_store

ID_KEYS = ("employee_id", "emp_no")
NAME_KEYS = ("employee_name", "name")
STORE_KEYS = ("store_raw", "bu", "store")
DATE_KEYS = {"joining_date": "joining date", "joining": "joining date", "role_since": "in-role date", "date": "date",
             "d_from": "leave start", "day": "attendance day"}


def _first(r: dict, keys: tuple) -> Any:
    for k in keys:
        if r.get(k) not in (None, ""):
            return r[k]
    return None


def _issue(level: str, text: str, examples: list | None = None) -> dict:
    return {"level": level, "text": text, "examples": [str(e) for e in (examples or [])][:6]}


def validate(kind: str, rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    if not rows:
        return [_issue("bad", "No rows could be read.")]
    n = len(rows)
    ids = [str(_first(r, ID_KEYS)) for r in rows if _first(r, ID_KEYS)]
    per_person_kinds = {"roster", "po_role", "po_master"}
    if kind in per_person_kinds:
        dup = [k for k, v in Counter(ids).items() if v > 1]
        if dup:
            out.append(_issue("warn", f"{len(dup)} employee number(s) appear more than once; the first row is used.", dup))
        missing = n - len(ids)
        if missing and kind != "po_role":
            out.append(_issue("warn", f"{missing} row(s) have no employee number and were left out or can't be linked."))
    if kind == "po_rating":
        dup = [k for k, v in Counter((str(r.get("employee_id")), r.get("cycle")) for r in rows).items() if v > 1]
        if dup:
            out.append(_issue("info", f"{len(dup)} person-year(s) have more than one rating form (e.g. a role change); the latest is used.",
                              [f"{a} · {b}" for a, b in dup]))
        bad = [r for r in rows if r.get("rating") is not None and not (0 <= r["rating"] <= 5)]
        if bad:
            out.append(_issue("bad", f"{len(bad)} rating(s) are outside 0–5.", [f"{r.get('employee_name')}: {r['rating']}" for r in bad]))
        unrated = sum(1 for r in rows if r.get("rating") is None)
        if unrated:
            out.append(_issue("info", f"{unrated} form(s) have no rating yet and are left out of averages."))
    # stores
    raw = [str(_first(r, STORE_KEYS)) for r in rows if _first(r, STORE_KEYS)]
    if raw:
        unknown = sorted({s for s in raw if not canon_store(s) and not re.search(r"head office|\bho\b|office|corporate|warehouse|dc\b", s, re.I)})
        if unknown:
            out.append(_issue("warn", f"{len(unknown)} store name(s) are not in P&O's store list. They are kept as new stores; "
                                      "confirm them in Settings → Stores if they are spellings of an existing store.", unknown))
    elif kind in ("roster", "po_role", "po_turnover", "po_rating", "po_da"):
        out.append(_issue("info", "No store column: results can't be split by store."))
    # dates
    today = date.today()
    for key, label in DATE_KEYS.items():
        vals = [r.get(key) for r in rows if r.get(key)]
        if not vals:
            continue
        future = [v for v in vals if str(v)[:10] > (today + timedelta(days=62)).isoformat()]
        old = [v for v in vals if str(v)[:4] < "1980"]
        if future:
            out.append(_issue("warn", f"{len(future)} {label}(s) are in the future.", future))
        if old:
            out.append(_issue("warn", f"{len(old)} {label}(s) are before 1980: probably a wrong date format.", old))
    # sections
    secs = [r.get("section_raw") or r.get("section") for r in rows if (r.get("section_raw") or r.get("section"))]
    if secs:
        unknown = sorted({s for s in secs if canon.section(s) not in canon.DEPARTMENT_OF and not re.search(r"store|overall|all|admin|hr|cash|cco|security|maint", str(s), re.I)})
        if len(unknown) > 0 and len(unknown) <= 40:
            out.append(_issue("info", f"{len(unknown)} section name(s) are not standard Carrefour sections; they are kept as written.", unknown))
    if kind == "sales":
        nob = sum(1 for r in rows if r.get("level") in ("store", "total") and not r.get("budget"))
        if nob:
            out.append(_issue("info", f"{nob} store total(s) have no budget: '% of budget' can't be shown for them."))
        neg = [r for r in rows if (r.get("actual") or 0) < 0]
        if neg:
            out.append(_issue("warn", f"{len(neg)} line(s) have negative sales.", [f"{r.get('store_raw')} {r.get('name')}" for r in neg]))
    if kind == "po_turnover":
        nodate = sum(1 for r in rows if not r.get("date"))
        if nodate:
            out.append(_issue("warn", f"{nodate} leaver(s) have no leaving date and are left out of monthly counts."))
    return out


def cross(db, results: list) -> list[dict]:
    """People in ratings / roles / leavers / leave who are not on any employee master P&O has."""
    master: set[str] = set()
    for r in results:
        if r.kind == "roster":
            master |= {str(x.get("emp_no")) for x in r.rows}
    try:
        for (e,) in db.q("SELECT DISTINCT emp_no FROM roster r JOIN imports i ON i.id=r.import_id WHERE i.active=1"):
            master.add(str(e))
        import json
        for (p,) in db.q("SELECT payload FROM po_records r JOIN imports i ON i.id=r.import_id WHERE i.active=1 AND r.kind='po_master'"):
            e = json.loads(p).get("employee_id")
            if e:
                master.add(str(e))
    except Exception:  # noqa: BLE001
        pass
    if not master:
        return []
    out = []
    for r in results:
        if r.kind not in ("po_rating", "po_role", "leave"):
            continue
        ids = {str(_first(x, ID_KEYS)) for x in r.rows if _first(x, ID_KEYS)}
        missing = sorted(ids - master)
        if missing and len(missing) < len(ids):
            out.append({"sheet": r.sheet, **_issue("info", f"{len(missing)} of {len(ids)} people in '{r.sheet}' are not on the employee master "
                                                           "(left, transferred or not yet in the Basic Sheet).", missing)})
    return out
