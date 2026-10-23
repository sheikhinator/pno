"""Read the P&O records saved in PNO's database in the shape the insights engine expects."""

from __future__ import annotations

import json
from typing import Any

from . import canon
from ..period import default_for_kind


class PoStore:
    """Latest active import per P&O kind (each tab is a complete monthly snapshot)."""

    def __init__(self, db: Any):
        self.db = db

    def records(self, kind: str | None = None) -> list[dict]:
        sql = ("SELECT r.kind, r.payload, i.id AS iid, i.month, i.file_name, i.summary, i.kind AS ikind, i.period_type, "
               "i.period_from, i.period_to, i.as_of FROM po_records r "
               "JOIN imports i ON i.id = r.import_id WHERE i.active = 1")
        params: list[Any] = []
        if kind:
            sql += " AND r.kind = ?"
            params.append(kind)
        out = []
        for row in self.db.q(sql + " ORDER BY r.id", params):
            rec = json.loads(row["payload"])
            summary = row["summary"] or ""
            sheet = summary[summary.rfind("[") + 1:-1] if summary.endswith("]") else ""
            ptype = row["period_type"] or default_for_kind(row["kind"] if row["ikind"].startswith("po_") else row["ikind"])
            pto = row["period_to"] or (row["month"] if ptype != "general" else None) or ((row["as_of"] or "")[:7] or None)
            pfrom = row["period_from"] or (pto if ptype == "mtd" else (f"{pto[:4]}-01" if pto else None))
            rec.update(_kind=row["kind"], _period=f"{row['month'] or ''}#{row['iid']:09d}", _source=row["file_name"], _sheet=sheet,
                       _iid=row["iid"], _ptype=ptype, _pfrom=pfrom, _pto=pto)
            out.append(rec)
        return out


# ------------------------------------------------- mirrors of the reports PNO already parses

def sales_records(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        level = r.get("level")
        code = r.get("code") or ""
        if level == "section":
            line, lvl, section = r.get("name") or code, "section", canon.SALES_CODE.get(code[:4], canon.section(f"{code} - {r.get('name')}"))
        elif level == "store":
            line, lvl, section = "Total Store", "total", ""
        elif level == "total":
            line, lvl, section = "Total", "total", ""
        else:
            line, lvl, section = r.get("name") or code, "subtotal", ""
        out.append({
            "store": canon.store(r.get("store_raw")), "store_raw": r.get("store_raw"), "line": line, "code": code,
            "section": section, "level": lvl, "actual": r.get("actual"), "budget": r.get("budget"),
            "growth_pct": r.get("growth"), "last_year": r.get("ly"), "margin_pct": r.get("margin"), "waste_pct": r.get("waste"),
            "margin_after_waste_pct": r.get("margin_net"), "oos_pct": r.get("oos"), "customers": r.get("customers"),
            "customers_growth_pct": r.get("cust_growth"), "basket": r.get("avg_basket"), "asp": r.get("asp"),
            "avg_stock": r.get("avg_stock"), "period_to": r.get("as_of"), "period_from": r.get("d_from"),
            "period": (r.get("period") or "").upper(),
        })
    return out


def productivity_records(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        label = " - ".join(x for x in (str(r.get("row_code") or ""), str(r.get("row_name") or "")) if x)
        section = canon.section(r.get("row_name") or "") if r.get("row_name") else ""
        if section in ("", r.get("row_name")):
            section = canon.section(label)
        if r.get("actual") is None:
            continue
        out.append({"store": canon.store(r.get("store_raw")), "store_raw": r.get("store_raw"), "section": section,
                    "section_raw": label, "productivity": r.get("actual"), "productivity_ly": r.get("ly"),
                    "target": r.get("target"), "forecast": r.get("forecast")})
    return out


def master_records(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "employee_id": r.get("emp_no"), "employee_name": canon.repair_name(r.get("name")),
            "store": canon.store(r.get("bu")), "store_raw": r.get("bu"),
            "department": f"{r.get('dept_code')}:{r.get('dept_name')}" if r.get("dept_code") else (r.get("dept_name") or ""),
            "section": canon.section(r.get("section")), "section_raw": r.get("section") or "",
            "designation": r.get("designation") or "", "grade": (r.get("grade") or "").lstrip("0"),
            "gender": r.get("gender") or "", "manager_name": canon.repair_name(r.get("manager_name")),
            "joining_date": r.get("joining") or r.get("joining_date"),
        })
    by_name: dict[str, list[str]] = {}
    for rec in out:
        by_name.setdefault(canon.name_key(rec["employee_name"]), []).append(rec["employee_id"])
    for rec in out:
        match = by_name.get(canon.name_key(rec["manager_name"]), [])
        rec["manager_id"] = match[0] if len(match) == 1 else ""
    return out
