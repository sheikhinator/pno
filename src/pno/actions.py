"""Action tracker, manpower planning and the director's "What needs you today" inbox."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from .db import now

STATUSES = ["open", "in progress", "done", "dropped"]


def _j(v, default):
    try:
        return json.loads(v) if v else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------------------------- actions
def add(db, title: str, owner: str = "", store: str = "", area: str = "", due: str | None = None, priority: str = "Medium",
        source: str = "Manual", detail: str = "") -> int:
    if not title.strip():
        raise ValueError("Write what needs to be done.")
    due = due or (date.today() + timedelta(days=14)).isoformat()
    hist = [{"at": now(), "status": "open", "note": f"Created ({source})"}]
    return db.x("""INSERT INTO actions(title, detail, owner, store, area, due, status, priority, source, created_at, updated_at, history)
                   VALUES(?,?,?,?,?,?,'open',?,?,?,?,?)""", (title.strip()[:240], detail[:2000], owner[:80], store[:80], area[:80], due,
                                                            priority if priority in ("High", "Medium", "Low") else "Medium", source[:40], now(), now(),
                                                            json.dumps(hist))).lastrowid


def update(db, action_id: int, **kw) -> dict:
    a = db.q1("SELECT * FROM actions WHERE id=?", (action_id,))
    if not a:
        raise ValueError("Action not found.")
    hist = _j(a["history"], [])
    sets, vals = [], []
    for k in ("title", "detail", "owner", "store", "area", "due", "priority"):
        if kw.get(k) is not None:
            sets.append(f"{k}=?")
            vals.append(str(kw[k])[:2000])
    if kw.get("status") in STATUSES and kw["status"] != a["status"]:
        sets += ["status=?", "done_at=?"]
        vals += [kw["status"], now() if kw["status"] == "done" else None]
        hist.append({"at": now(), "status": kw["status"], "note": kw.get("note") or ""})
    elif kw.get("note"):
        hist.append({"at": now(), "status": a["status"], "note": kw["note"][:500]})
    sets += ["history=?", "updated_at=?"]
    vals += [json.dumps(hist), now()]
    db.x(f"UPDATE actions SET {', '.join(sets)} WHERE id=?", (*vals, action_id))
    return listing(db)


def delete(db, action_id: int) -> dict:
    db.x("DELETE FROM actions WHERE id=?", (action_id,))
    return listing(db)


def listing(db) -> dict:
    today = date.today().isoformat()
    rows = []
    for a in db.q("SELECT * FROM actions ORDER BY status IN ('done','dropped'), due, id DESC"):
        r = dict(a)
        r["history"] = _j(a["history"], [])
        r["overdue"] = r["status"] in ("open", "in progress") and (r["due"] or "9999") < today
        rows.append(r)
    st = Counter(r["status"] for r in rows)
    by_owner = Counter(r["owner"] or "Unassigned" for r in rows if r["status"] in ("open", "in progress"))
    return {"rows": rows, "statuses": STATUSES, "counts": {s: st.get(s, 0) for s in STATUSES},
            "overdue": sum(1 for r in rows if r["overdue"]), "by_owner": by_owner.most_common(10),
            "done_30d": sum(1 for r in rows if r["status"] == "done" and (r["done_at"] or "") >= (date.today() - timedelta(days=30)).isoformat())}


def from_text(text: str) -> list[str]:
    """The numbered / bulleted lines under a 'Recommended actions' heading of an AI answer."""
    lines = text.replace("\r", "").split("\n")
    out, on = [], False
    for ln in lines:
        if re.match(r"^\s*#{1,4}\s*(recommended )?actions?\b", ln, re.I) or re.match(r"^\s*\**(recommended actions|next steps|actions)\**:?\s*$", ln, re.I):
            on = True
            continue
        if on and re.match(r"^\s*#{1,4}\s", ln):
            break
        m = re.match(r"^\s*(?:\d+[.)]|[-*•])\s+(.*)", ln)
        if on and m:
            out.append(re.sub(r"\*\*|__", "", m.group(1)).strip())
    return out[:8]


# ---------------------------------------------------------------------------------------------- manpower
def manning(db, ins) -> dict:
    """Approved heads (entered or imported) against actual heads on the Basic Sheet, plus open vacancies."""
    approved = {(r["store"], r["department"]): r["approved"] for r in db.q("SELECT * FROM manning")}
    actual: dict[tuple[str, str], int] = defaultdict(int)
    for r in ins.rows("po_master"):
        dept = canon_dept(str(r.get("department") or "").split(":")[-1].strip()) or canon_dept(r.get("section"))
        actual[(r.get("store") or "—", dept or "Other")] += 1
    vac: dict[tuple[str, str], int] = defaultdict(int)
    for v in db.q("SELECT store, section, headcount, (SELECT COUNT(*) FROM applications a WHERE a.vacancy_id=v.id AND a.stage='joined') AS joined "
                  "FROM vacancies v WHERE status='open'"):
        vac[(v["store"] or "—", v["section"] or "Any")] += max(0, (v["headcount"] or 1) - (v["joined"] or 0))
    keys = sorted(set(approved) | set(actual))
    rows = []
    for k in keys:
        a, ap = actual.get(k, 0), approved.get(k)
        open_v = sum(n for (s, sec), n in vac.items() if s == k[0] and (sec.lower() in k[1].lower() or k[1].lower() in sec.lower()))
        rows.append({"store": k[0], "department": k[1], "approved": ap, "actual": a, "gap": (a - ap) if ap is not None else None,
                     "open_vacancies": open_v, "fill_pct": round(100 * a / ap, 1) if ap else None})
    by_store: dict[str, dict] = defaultdict(lambda: {"approved": 0, "actual": 0, "has_plan": False})
    for r in rows:
        s = by_store[r["store"]]
        s["actual"] += r["actual"]
        if r["approved"] is not None:
            s["approved"] += r["approved"]
            s["has_plan"] = True
    stores = [{"store": k, **v, "gap": v["actual"] - v["approved"] if v["has_plan"] else None,
               "fill_pct": round(100 * v["actual"] / v["approved"], 1) if v["approved"] else None} for k, v in sorted(by_store.items())]
    tot_ap = sum(s["approved"] for s in stores if s["has_plan"])
    tot_ac = sum(s["actual"] for s in stores if s["has_plan"])
    return {"rows": rows, "stores": stores, "has_plan": bool(approved), "approved": tot_ap, "actual": tot_ac,
            "vacant": sum(max(0, -r["gap"]) for r in rows if r["gap"] is not None),
            "over": sum(max(0, r["gap"]) for r in rows if r["gap"] is not None),
            "open_vacancies": sum(vac.values()), "headcount": sum(actual.values())}


def canon_dept(name: Any) -> str:
    """'CGD-FMCG', 'Market', 'FFD - Bakery', 'Fresh Food' … → the department P&O uses (Consumer Goods, Fresh Food, …)."""
    from .po import canon
    if not name or not str(name).strip():
        return ""
    d = canon.department(canon.section(name))
    return d if d and d != "Overall" else ""


def set_manning(db, rows: list[dict]) -> None:
    for r in rows:
        store, dept = str(r.get("store") or "").strip(), str(r.get("department") or "").strip()
        dept = canon_dept(dept) or dept
        if not store or not dept:
            continue
        if r.get("approved") in (None, ""):
            db.x("DELETE FROM manning WHERE store=? AND department=?", (store, dept))
        else:
            db.x("INSERT INTO manning(store, department, approved, updated_at) VALUES(?,?,?,?) ON CONFLICT(store, department) DO UPDATE SET "
                 "approved=excluded.approved, updated_at=excluded.updated_at", (store, dept, int(float(r["approved"])), now()))


def manning_from_table(db, text: str) -> int:
    """Approved manning pasted from Excel: Store, Department, Approved (header row optional)."""
    n = 0
    rows = []
    for ln in text.replace("\r", "").split("\n"):
        cells = [c.strip() for c in re.split(r"\t|,(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", ln) if c is not None]
        if len(cells) < 3 or not re.fullmatch(r"\d+(\.\d+)?", cells[-1].replace(",", "")):
            continue
        from .po import canon
        rows.append({"store": canon.store(cells[0]), "department": canon_dept(cells[1]) or cells[1], "approved": cells[-1].replace(",", "")})
        n += 1
    set_manning(db, rows)
    return n


# ---------------------------------------------------------------------------------------------- today
def today(api) -> dict:
    """Everything that needs the director, from every module, most urgent first."""
    db = api.db
    items: list[dict] = []
    t = date.today().isoformat()
    for a in db.q("SELECT id, title, owner, due FROM actions WHERE status IN ('open','in progress') AND due < ? ORDER BY due LIMIT 6", (t,)):
        items.append({"level": "bad", "area": "Action overdue", "text": f"{a['title']} · {a['owner'] or 'no owner'} · due {a['due']}", "go": "actions"})
    try:
        from . import datahealth
        from .po.insights import Insights
        from .po.store import PoStore
        ins_latest = Insights(PoStore(db), view={"type": "latest"})
        h = datahealth.report(db, ins_latest)
        missing = [c["name"] for c in h["checklist"] if c["status"] == "missing"]
        if h["score"] < 85:
            items.append({"level": "warn", "area": "Data", "text": f"Data health {h['score']}/100 for {h['month_label']}" +
                          (f": missing {', '.join(missing[:3])}" if missing else ""), "go": "health"})
    except Exception:  # noqa: BLE001 - the inbox never fails because one source does
        pass
    try:
        ins = api._po()
        if not ins.empty:
            for a in [x for x in ins.alerts(40) if x["severity"] == "High"][:4]:
                items.append({"level": "bad", "area": a["area"], "text": f"{a['store']} · {a['message']}", "go": "review"})
            from .po.people_risk import flight_risk
            high = [r for r in flight_risk(ins) if r["band"] == "High"]
            if high:
                items.append({"level": "warn", "area": "Flight risk", "text": f"{len(high)} leader{'s' if len(high) > 1 else ''} at high risk of leaving, "
                              f"e.g. {high[0]['name']} ({high[0]['store']})", "go": "talent", "tab": "risk"})
    except Exception:  # noqa: BLE001
        pass
    for v in db.q("SELECT title, store, created_at FROM vacancies WHERE status='open' ORDER BY created_at LIMIT 3"):
        days = (date.today() - datetime.fromisoformat(v["created_at"][:19]).date()).days if v["created_at"] else 0
        if days >= 30:
            items.append({"level": "warn", "area": "Hiring", "text": f"{v['title']}{(' · ' + v['store']) if v['store'] else ''} open {days} days", "go": "hiring"})
    try:
        od = db.q("SELECT id, kind, name, stage, stage_due FROM er_cases WHERE stage!='Closed' AND stage_due < ? ORDER BY stage_due LIMIT 4", (t,))
        for c in od:
            items.append({"level": "bad", "area": "Employee relations", "text": f"{c['kind']} case · {c['name']}: next step after '{c['stage']}' was due {c['stage_due']}", "go": "relations"})
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import workplace
        bad = [g for g in workplace.goals(db)["rows"] if g["status"] == "open" and g["state"] in ("off track", "missed")]
        if bad:
            items.append({"level": "warn", "area": "Goals", "text": f"{len(bad)} goal{'s' if len(bad) > 1 else ''} off track, e.g. {bad[0]['title']}", "go": "goals"})
        fu = db.q1("SELECT COUNT(*) FROM meetings n JOIN actions a ON a.id=n.action_id WHERE a.status IN ('open','in progress') AND a.due < ?", (t,))[0]
        if fu:
            items.append({"level": "info", "area": "1:1 follow-ups", "text": f"{fu} follow-up{'s' if fu > 1 else ''} from 1:1s past due", "go": "notes"})
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import people_insights
        wk = people_insights.this_week(api)
        ms = [a for a in wk["anniversaries"] if a["milestone"]]
        if ms:
            items.append({"level": "info", "area": "Anniversaries", "text": ", ".join(f"{a['name']} {a['years']} yrs" for a in ms[:3]) +
                          (f" and {len(ms) - 3} more" if len(ms) > 3 else "") + " this week: a note from you goes a long way", "go": "insights"})
        lead = [o for o in wk["off"] if o["level"] >= 3]
        if lead:
            items.append({"level": "info", "area": "Cover", "text": f"{len(lead)} leader{'s' if len(lead) > 1 else ''} on leave this week, e.g. {lead[0]['name']} "
                          f"({lead[0]['store']}, back {lead[0]['to']})", "go": "insights"})
    except Exception:  # noqa: BLE001
        pass
    od = db.q1("SELECT COUNT(*) FROM assignments WHERE status!='completed' AND due IS NOT NULL AND due < ?", (t,))[0]
    if od:
        items.append({"level": "info", "area": "Training", "text": f"{od} training assignment{'s' if od > 1 else ''} past due", "go": "learning"})
    order = {"bad": 0, "warn": 1, "info": 2}
    return {"items": sorted(items, key=lambda i: order[i["level"]])[:10]}
