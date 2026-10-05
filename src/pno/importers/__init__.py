"""Recognise any of the supported reports in a file, preview it, and save it."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from ..db import Database, now
from ..reader import Workbook, from_text, open_bytes, open_file
from ..stores import StoreResolver
from ..util import month_bounds
from . import attendance, leave, productivity, roster, sales
from .base import KIND_LABEL, ParseResult

PARSERS = [("sales", sales), ("productivity", productivity), ("attendance", attendance), ("roster", roster), ("leave", leave)]


def detect(sheet) -> tuple[str | None, float]:
    best, best_s = None, 0.0
    for kind, mod in PARSERS:
        s, _ = mod.score(sheet)
        if s > best_s:
            best, best_s = kind, s
    return (best, best_s) if best_s >= 0.5 else (None, 0.0)


def analyze_workbook(wb: Workbook, force_kind: str | None = None) -> dict:
    results: list[ParseResult] = []
    skipped: list[str] = []
    for sh in wb.sheets:
        kind, conf = detect(sh)
        if force_kind:
            mod = dict(PARSERS)[force_kind]
            if mod.score(sh)[0] <= 0:
                skipped.append(sh.name)
                continue
            kind = force_kind
        if not kind:
            skipped.append(sh.name)
            continue
        mod = dict(PARSERS)[kind]
        res = mod.parse(sh, wb.name) if kind == "productivity" else mod.parse(sh)
        res.confidence = conf
        if res.rows:
            results.append(res)
        else:
            skipped.append(sh.name)
    return {"file": wb.name, "hash": wb.file_hash, "results": results, "skipped": skipped, "warnings": wb.warnings}


def analyze_path(path: str | Path) -> dict:
    return analyze_workbook(open_file(path))


def analyze_bytes(data: bytes, name: str) -> dict:
    return analyze_workbook(open_bytes(data, name))


def analyze_text(text: str, name: str = "Pasted data") -> dict:
    return analyze_workbook(from_text(text, name))


def describe(analysis: dict) -> dict:
    """What the import screen shows before saving."""
    return {
        "file": analysis["file"], "skipped": analysis["skipped"], "warnings": analysis["warnings"],
        "results": [{"kind": r.kind, "label": KIND_LABEL[r.kind], "sheet": r.sheet, "rows": len(r.rows), "month": r.month,
                     "as_of": r.as_of, "summary": r.summary, "warnings": r.warnings, "needs": r.needs,
                     "confidence": round(r.confidence, 2), "preview": r.preview} for r in analysis["results"]],
    }


def commit(db: Database, analysis: dict, options: dict | None = None, source: str = "file") -> list[dict]:
    """Save every recognised table. options: {sheet: {'month': 'YYYY-MM', 'as_of': 'YYYY-MM-DD', 'replace': bool}}."""
    options = options or {}
    out = []
    for res in analysis["results"]:
        opt = options.get(res.sheet, {}) | options.get("*", {})
        out.append(_commit_one(db, res, analysis, opt, source))
    return out


def _commit_one(db: Database, res: ParseResult, analysis: dict, opt: dict, source: str) -> dict:
    month = opt.get("month") or res.month
    as_of = opt.get("as_of") or res.as_of
    if res.kind == "roster" and not as_of:
        as_of = date.today().isoformat()
    if res.kind == "roster":
        month = as_of[:7]
    if res.kind == "productivity" and not month:
        return {"sheet": res.sheet, "kind": res.kind, "status": "needs_month",
                "message": "Choose the month this productivity report belongs to."}
    if res.kind == "productivity" and not as_of and month:
        as_of = month_bounds(month)[1].isoformat()
    dup = db.q1("SELECT id FROM imports WHERE active=1 AND kind=? AND file_hash=? AND summary LIKE ?",
                (res.kind, analysis["hash"], f"%[{res.sheet}]%"))
    if dup and res.kind in ("roster", "productivity") and not opt.get("replace"):
        # same file again: only meaningful if the user wants another month / as-of date
        prev = db.q1("SELECT month, as_of FROM imports WHERE id=?", (dup[0],))
        if prev["month"] == month and (res.kind != "roster" or prev["as_of"] == as_of):
            return {"sheet": res.sheet, "kind": res.kind, "status": "duplicate", "import_id": dup[0],
                    "message": "This report was already imported."}
    elif dup and not opt.get("replace"):
        return {"sheet": res.sheet, "kind": res.kind, "status": "duplicate", "import_id": dup[0],
                "message": "This report was already imported."}
    resolver = StoreResolver(db, source=res.kind)
    with db.tx():
        cur = db.conn.execute(
            "INSERT INTO imports(kind, file_name, file_hash, month, as_of, rows, summary, warnings, source, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (res.kind, analysis["file"], analysis["hash"], month, as_of, len(res.rows), f"{res.summary} [{res.sheet}]",
             json.dumps(res.warnings), source, now()))
        iid = cur.lastrowid
        if dup and opt.get("replace"):
            db.conn.execute("UPDATE imports SET active=0 WHERE id=?", (dup[0],))
    # store names are resolved outside the transaction (the resolver writes its own rows)
    sid = {}
    for r in res.rows:
        key = r.get("bu") or r.get("store_raw")
        if key and key not in sid:
            sid[key] = resolver.resolve(key)
    try:
        with db.tx():
            c = db.conn
            if res.kind == "roster":
                c.executemany(
                    "INSERT INTO roster(import_id, emp_no, name, store_id, bu_raw, dept_code, dept_name, section_raw, "
                    "designation, grade, gender, manager_name) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(iid, r["emp_no"], r["name"], sid.get(r["bu"]), r["bu"], r["dept_code"], r["dept_name"], r["section"],
                      r["designation"], r["grade"], r["gender"],
                      r["manager_name"] + (f" #{r['manager_no']}" if r.get("manager_no") else "")) for r in res.rows])
            elif res.kind == "attendance":
                people = res.extra.get("people", [])
                c.executemany(
                    "INSERT OR REPLACE INTO att_people(import_id, emp_no, month, name, store_id, bu_raw, section_raw, designation, "
                    "joining_date, sys_absent, sys_present) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    [(iid, p["emp_no"], month, p["name"], sid.get(p["bu"]), p["bu"], p["section"],
                      p["designation"], p["joining"], p["sys_absent"], p["sys_present"]) for p in people])
                store_of = {p["emp_no"]: sid.get(p["bu"]) for p in people}
                c.executemany(
                    "INSERT OR REPLACE INTO attendance_all(import_id, emp_no, day, store_id, t_in, t_out, minutes, wh_raw, status) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    [(iid, r["emp_no"], r["day"], store_of.get(r["emp_no"]), r["t_in"], r["t_out"], r["minutes"], r["wh_raw"],
                      r["status"]) for r in res.rows])
            elif res.kind == "productivity":
                c.executemany(
                    "INSERT OR REPLACE INTO productivity(import_id, store_id, store_raw, month, row_code, row_name, level, actual, ly, "
                    "target, forecast) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    [(iid, sid.get(r["store_raw"]), r["store_raw"], month, r["row_code"], r["row_name"], r["level"], r["actual"], r["ly"],
                      r["target"], r["forecast"]) for r in res.rows if sid.get(r["store_raw"])])
            elif res.kind == "sales":
                c.executemany(
                    "INSERT OR REPLACE INTO sales(import_id, store_id, store_raw, month, period, as_of, level, code, name, dept, actual, "
                    "budget, growth, ly, var_pct, weight, customers, cust_growth, penetration, items, avg_basket, asp, margin, "
                    "waste, margin_net, avg_stock, oos) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(iid, sid.get(r["store_raw"]), r["store_raw"], (r["as_of"] or as_of)[:7], r["period"], r["as_of"] or as_of, r["level"],
                      r["code"], r["name"], r["dept"], r.get("actual"), r.get("budget"), r.get("growth"), r.get("ly"),
                      r.get("var_pct"), r.get("weight"), r.get("customers"), r.get("cust_growth"), r.get("penetration"),
                      r.get("items"), r.get("avg_basket"), r.get("asp"), r.get("margin"), r.get("waste"),
                      r.get("margin_net"), r.get("avg_stock"), r.get("oos"))
                     for r in res.rows if sid.get(r["store_raw"]) and (r["as_of"] or as_of)])
            elif res.kind == "leave":
                c.executemany("INSERT INTO leaves(emp_no, d_from, d_to, type, note, import_id, created_at) VALUES(?,?,?,?,?,?,?)",
                              [(r["emp_no"], r["d_from"], r["d_to"], r["type"], r.get("note"), iid, now()) for r in res.rows])
    except Exception:
        db.x("DELETE FROM imports WHERE id=?", (iid,))
        raise
    if res.kind == "attendance" and res.rows:
        days = sorted(r["day"] for r in res.rows)
        db.rebuild_attendance((days[0], days[-1]))
    if dup and opt.get("replace") and res.kind == "attendance":
        db.rebuild_attendance()
    db.log("import", f"{res.kind} {analysis['file']} [{res.sheet}] -> #{iid}")
    return {"sheet": res.sheet, "kind": res.kind, "status": "ok", "import_id": iid, "rows": len(res.rows),
            "summary": res.summary, "unsure_stores": resolver.unsure}


def undo(db: Database, import_id: int) -> dict:
    row = db.q1("SELECT * FROM imports WHERE id=?", (import_id,))
    if not row:
        raise ValueError("Import not found.")
    db.x("UPDATE imports SET active=0 WHERE id=?", (import_id,))
    if row["kind"] == "attendance":
        r = db.q1("SELECT MIN(day), MAX(day) FROM attendance_all WHERE import_id=?", (import_id,))
        if r and r[0]:
            db.rebuild_attendance((r[0], r[1]))
    db.log("undo", f"{row['kind']} {row['file_name']} #{import_id}")
    return {"ok": True}


def redo(db: Database, import_id: int) -> dict:
    row = db.q1("SELECT * FROM imports WHERE id=?", (import_id,))
    if not row:
        raise ValueError("Import not found.")
    db.x("UPDATE imports SET active=1 WHERE id=?", (import_id,))
    if row["kind"] == "attendance":
        r = db.q1("SELECT MIN(day), MAX(day) FROM attendance_all WHERE import_id=?", (import_id,))
        if r and r[0]:
            db.rebuild_attendance((r[0], r[1]))
    db.log("restore import", f"{row['kind']} {row['file_name']} #{import_id}")
    return {"ok": True}


def as_dict(res: ParseResult) -> dict:
    return asdict(res)
