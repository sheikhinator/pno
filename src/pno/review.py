"""4.0 Department Review: the one screen the P&O director presents from.

Any slice (country → store → department → section, plus a role filter) gets the same criteria, each coloured against
its benchmark, the next level down as a comparison grid, plain-language strong / weak / focus notes, and a benchmark
table of the people in that slice with every criterion visible and the score as the last column. No ranks, no tiers.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from .po import canon

DEPARTMENTS = ["Consumer Goods", "Fresh Food", "Light Household", "Heavy Household", "Textile", "Non Food", "Health & Beauty"]
SHORT = {"Consumer Goods": "CG", "Fresh Food": "Fresh Food", "Light Household": "LHH", "Heavy Household": "HHH", "Textile": "Textile",
         "Non Food": "Non Food", "Health & Beauty": "H&B"}
ROLES = {"store": ("Store managers", 5, 9), "dept": ("Department heads", 4, 4), "section": ("Section managers", 3, 3), "tl": ("Team leaders", 1, 2)}

# key: label, format, better ("up" | "down" | None), green, amber  (None thresholds = shown without colour)
CRITERIA: dict[str, dict] = {
    "sales": dict(short="Sales vs bud.", label="Sales vs budget", fmt="pct0", unit="% of budget", better="up", green=100, amber=95),
    "growth": dict(short="Growth", label="Growth vs LY", fmt="pct1s", unit="", better="up", green=0, amber=-5),
    "productivity": dict(short="Productivity", label="Productivity vs target", fmt="pct1s", unit="", better="up", green=0, amber=-10),
    "shrink": dict(short="Shrink", label="Shrinkage vs budget", fmt="pp2s", unit="pts", better="up", green=0, amber=-0.25),
    "stock_days": dict(short="Stock days", label="Stock days vs budget", fmt="pct0", unit="% of budget", better="down", green=100, amber=120),
    "oos": dict(short="OOS", label="Out of stock", fmt="pct1", unit="", better="down", green=3, amber=6),
    "waste": dict(short="Waste", label="Waste", fmt="pct1", unit="", better="down", green=1, amber=2),
    "attendance": dict(short="Attendance", label="Attendance", fmt="pct1", unit="", better="up", green=95, amber=90),
    "leavers": dict(short="Leavers", label="Leavers (12 m)", fmt="int", unit="", better="down", green=None, amber=None),
    "da": dict(short="DA cases", label="Disciplinary cases", fmt="int", unit="", better="down", green=None, amber=None),
    "nps": dict(short="NPS", label="Customer NPS", fmt="int", unit="", better="up", green=50, amber=30),
    "rating": dict(short="Rating", label="Rating", fmt="dec1", unit="/5", better="up", green=4, amber=3),
    "score": dict(short="Score", label="Score", fmt="dec1", unit="/10", better="up", green=7, amber=5),
}
UNIT_KEYS = ["sales", "growth", "productivity", "shrink", "stock_days", "oos", "waste", "attendance", "leavers", "da", "nps"]
PEOPLE_KEYS = ["sales", "growth", "productivity", "shrink", "stock_days", "oos", "waste", "attendance", "leavers", "da", "nps", "rating", "score"]


def targets(db) -> dict:
    t = {k: {"green": v["green"], "amber": v["amber"]} for k, v in CRITERIA.items()}
    for k, v in (db.get_setting("review_targets", {}) or {}).items():
        if k in t and isinstance(v, dict):
            t[k].update({kk: float(vv) for kk, vv in v.items() if kk in ("green", "amber") and vv is not None})
    return t


def status(key: str, v: float | None, t: dict) -> str:
    if v is None:
        return "none"
    c, g, a = CRITERIA[key], t[key]["green"], t[key]["amber"]
    if g is None:
        return "neutral"
    if c["better"] == "up":
        return "good" if v >= g else "warn" if v >= a else "bad"
    return "good" if v <= g else "warn" if v <= a else "bad"


def members(dept: str | None, section: str | None) -> list[str] | None:
    """The canonical sections in a slice (None = the whole store)."""
    if section:
        return [section]
    if not dept:
        return None
    if dept == "Non Food":
        return ["Light Household", "Heavy Household", "Textile", "Non Food"]
    return [s for s, d in canon.DEPARTMENT_OF.items() if d == dept]


def sections_of(dept: str) -> list[str]:
    if dept == "Non Food":
        return ["Light Household", "Heavy Household", "Textile"]
    return [s for s in canon.SECTION_ORDER if canon.DEPARTMENT_OF.get(s) == dept and s != dept]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


class Review:
    def __init__(self, api):
        self.api = api
        self.ins = api._po()
        self.t = targets(api.db)
        self._att = None

    # ---------------------------------------------------------------------------- attendance from the roster model
    def att(self) -> list[dict]:
        if self._att is None:
            self._att = []
            try:
                from .people_insights import _model, _store_of
                mm = _model(self.api)
                if mm:
                    for p in mm.people.values():
                        if p.att and p.att.get("due"):
                            self._att.append({"emp": str(p.emp), "store": _store_of(p), "section": canon.section(p.section) or p.section,
                                              "worked": p.att["worked"], "due": p.att["due"]})
            except Exception:  # noqa: BLE001
                pass
        return self._att

    def attendance(self, stores: list[str], secs: list[str] | None) -> float | None:
        rows = [r for r in self.att() if r["store"] in stores and (secs is None or r["section"] in secs)]
        due = sum(r["due"] for r in rows)
        return round(100 * sum(r["worked"] for r in rows) / due, 1) if due >= 20 else None

    # ---------------------------------------------------------------------------- one unit = stores × sections
    def unit(self, stores: list[str], dept: str | None, section: str | None) -> dict[str, float | None]:
        ins, secs = self.ins, members(dept, section)
        key = section or dept
        act = bud = ly = 0.0
        has_b = has_ly = False
        w_oos, w_waste, wt = [], [], []
        prod, shr, days, nps = [], [], [], []
        leavers = da = 0
        for st in stores:
            s = ins.sales_total(st) if key is None else ins.sales_section(st, key)
            if s and s.get("actual"):
                a = s["actual"]
                act += a
                if s.get("budget"):
                    bud += s["budget"]
                    has_b = True
                lyv = s.get("last_year")
                if lyv:
                    ly += lyv
                    has_ly = True
                for lst, f in ((w_oos, "oos_pct"), (w_waste, "waste_pct")):
                    if s.get(f) is not None:
                        lst.append((s[f], a))
            p = ins.productivity(st, key or "Overall")
            if p and p.get("vs_target_pct") is not None:
                prod.append(p["vs_target_pct"])
            if key is None:
                rows = [r for r in ins.rows("po_shrink") if r["store"] == st and r["section"] not in ("Consumer Goods", "Fresh Food", "Non Food")]
                shr += [r["shrink_variance_pct"] for r in rows if r.get("shrink_variance_pct") is not None]
                days += [r["stock_days_actual"] / r["stock_days_budget"] for r in rows if r.get("stock_days_budget") and r.get("stock_days_actual") is not None]
            else:
                for sec in (secs or [key]):
                    sh = ins.shrink(st, sec)
                    if sh and not (sh.get("fallback") and sec != key and len(secs or []) > 1):
                        if sh.get("shrink_variance_pct") is not None:
                            shr.append(sh["shrink_variance_pct"])
                        if sh.get("days_ratio"):
                            days.append(sh["days_ratio"])
            lv = ins.leavers(st)
            leavers += sum(1 for r in lv if secs is None or r.get("section") in secs or canon.department(r.get("section", "")) == key)
            da += ins.da_count(st) if secs is None else sum(ins.da_count(st, sc) for sc in secs)
            city = canon.store_city(st)
            if city:
                n = ins.nps(city) if key is None else _mean([(ins.nps(city, sc) or {}).get("nps") for sc in secs])
                if isinstance(n, dict):
                    n = n.get("nps")
                if n is not None:
                    nps.append(n)
        wavg = lambda pairs: (sum(v * w for v, w in pairs) / sum(w for _, w in pairs)) if pairs and sum(w for _, w in pairs) else None  # noqa: E731
        has_turn, has_da = ins.has("po_turnover"), ins.has("po_da")
        return {
            "sales": round(100 * act / bud, 1) if has_b and bud else None,
            "growth": round(100 * (act - ly) / ly, 1) if has_ly and ly else None,
            "productivity": round(_mean(prod), 1) if prod else None,
            "shrink": round(_mean(shr), 2) if shr else None,
            "stock_days": round(100 * _mean(days)) if days else None,
            "oos": round(wavg(w_oos), 1) if w_oos else None,
            "waste": round(wavg(w_waste), 2) if w_waste else None,
            "attendance": self.attendance(stores, secs),
            "leavers": leavers if has_turn else None,
            "da": da if has_da else None,
            "nps": round(_mean(nps)) if nps else None,
        }

    def cells(self, vals: dict, keys: list[str]) -> list[dict]:
        return [{"key": k, "value": vals.get(k), "status": status(k, vals.get(k), self.t)} for k in keys]

    # ---------------------------------------------------------------------------- people
    def leader_row(self, l, secs: list[str] | None) -> dict:
        row = self._leader_row(l)
        # one area (a store, a department or a section): use exactly the numbers the grid shows for it
        top = {"Consumer Goods", "Fresh Food", "Non Food"}
        if l.whole_store or canon.role_rank(l.designation) >= canon.STORE_LEVEL:
            u = self.unit([l.store], None, None)
        elif len(l.sections) == 1:
            sec = l.sections[0]
            u = self.unit([l.store], sec, None) if sec in top else self.unit([l.store], canon.department(sec) or None, sec)
        else:
            u = None
        if u:
            for c in row["cells"]:
                if c["key"] in ("sales", "growth", "productivity", "shrink", "stock_days", "oos", "waste", "nps") and u.get(c["key"]) is not None:
                    c["value"], c["status"] = u[c["key"]], status(c["key"], u[c["key"]], self.t)
            row["measured"] = sum(1 for c in row["cells"] if c["value"] is not None and c["key"] != "score")
        return row

    def _leader_row(self, l) -> dict:
        k = l.kpis or {}
        sp = k.get("sales") or []
        act = sum(s["actual"] or 0 for _, s in sp)
        bud = sum(s["budget"] for _, s in sp if s.get("budget"))
        lyv = [s.get("last_year") for _, s in sp]
        ly = sum(lyv) if sp and all(x for x in lyv) else None
        w = lambda f: (sum((s.get(f) or 0) * (s["actual"] or 0) for _, s in sp if s.get(f) is not None) /  # noqa: E731
                       max(1e-9, sum(s["actual"] or 0 for _, s in sp if s.get(f) is not None))) if any(s.get(f) is not None for _, s in sp) else None
        prod = [p["vs_target_pct"] for _, p in (k.get("productivity") or []) if p.get("vs_target_pct") is not None]
        shr = [s["shrink_variance_pct"] for _, s in (k.get("shrink") or []) if s.get("shrink_variance_pct") is not None]
        days = [s["days_ratio"] for _, s in (k.get("shrink") or []) if s.get("days_ratio")]
        nps = [n["nps"] for _, n in (k.get("nps") or []) if n.get("nps") is not None]
        a = next((r for r in self.att() if r["emp"] == str(l.employee_id)), None)
        vals = {
            "sales": round(100 * act / bud, 1) if bud else None,
            "growth": round(100 * (act - ly) / ly, 1) if ly else None,
            "productivity": round(_mean(prod), 1) if prod else None,
            "shrink": round(_mean(shr), 2) if shr else None,
            "stock_days": round(100 * _mean(days)) if days else None,
            "oos": round(w("oos_pct"), 1) if w("oos_pct") is not None else None,
            "waste": round(w("waste_pct"), 2) if w("waste_pct") is not None else None,
            "attendance": round(100 * a["worked"] / a["due"], 1) if a and a["due"] else None,
            "leavers": k.get("leavers"),
            "da": k.get("da"),
            "nps": round(_mean(nps)) if nps else None,
            "rating": l.latest_rating,
            "score": round(l.score / 10, 1) if l.score is not None else None,
        }
        return {"emp": str(l.employee_id or ""), "key": l.key, "name": l.name, "store": l.store, "role": l.designation,
                "area": l.section_text if hasattr(l, "section_text") else ", ".join(l.sections), "level": canon.role_rank(l.designation),
                "acting": l.acting, "cells": self.cells(vals, PEOPLE_KEYS),
                "measured": sum(1 for kk in PEOPLE_KEYS if vals.get(kk) is not None and kk != "score")}

    def people(self, stores: list[str], dept: str | None, section: str | None, role: str | None) -> list[dict]:
        secs = members(dept, section)
        lo, hi = (ROLES[role][1], ROLES[role][2]) if role in ROLES else (1, 9)
        out = []
        for l in self.ins.leaders():
            if l.store not in stores:
                continue
            r = canon.role_rank(l.designation)
            if not (lo <= r <= hi):
                continue
            if secs is not None:
                if not l.sections or not any(s in secs or canon.department(s) == (section or dept) for s in l.sections):
                    continue
                if r >= canon.STORE_LEVEL and role != "store":
                    continue                                 # store managers run the whole store, not one department
            out.append(self.leader_row(l, secs))
        order = {s: i for i, s in enumerate(stores)}
        out.sort(key=lambda p: (order.get(p["store"], 99), -p["level"], p["area"], p["name"]))
        return out

    # ---------------------------------------------------------------------------- notes
    def notes(self, tiles: list[dict], grid: list[dict], grid_kind: str, people: list[dict]) -> dict:
        lab = lambda k: CRITERIA[k]["label"]  # noqa: E731
        strong, weak, focus = [], [], []
        for c in tiles:
            k, st = c["key"], c["status"]
            spread = [g for g in grid if next((x for x in g["cells"] if x["key"] == k), {}).get("status") in ("good", "bad")]
            good_units = [g["name"] for g in grid if next(x for x in g["cells"] if x["key"] == k)["status"] == "good"]
            bad_units = [g["name"] for g in grid if next(x for x in g["cells"] if x["key"] == k)["status"] == "bad"]
            measured = sum(1 for g in grid if next(x for x in g["cells"] if x["key"] == k)["value"] is not None)
            if st == "good":
                tail = ""
                if measured >= 2 and good_units:
                    tail = f": green in {'all ' + str(measured) if len(good_units) == measured else str(len(good_units)) + ' of ' + str(measured)} {grid_kind}"
                elif measured == 1:
                    tail = " (only one of the " + grid_kind + " has this data)"
                strong.append(f"{lab(k)} {fmt(k, c['value'])}{tail}.")
            elif st == "bad":
                weak.append(f"{lab(k)} {fmt(k, c['value'])} (benchmark {fmt(k, self.t[k]['green'])})" +
                            (f": weakest in {', '.join(bad_units[:3])}" if bad_units else "") + ".")
            elif st == "warn" and bad_units:
                weak.append(f"{lab(k)} {fmt(k, c['value'])}, close to benchmark overall but red in {', '.join(bad_units[:3])}.")
            if bad_units and spread:
                focus.append((len(bad_units) / max(1, len(grid)) + (1 if st == "bad" else 0),
                              f"{lab(k)} in {', '.join(bad_units[:3])}{' and ' + str(len(bad_units) - 3) + ' more' if len(bad_units) > 3 else ''}"))
        for k in ("leavers", "da"):
            vals = [(g["name"], next(x for x in g["cells"] if x["key"] == k)["value"]) for g in grid]
            vals = [(n, v) for n, v in vals if v is not None]
            if len(vals) >= 4:
                med = median(v for _, v in vals)
                hi = [n for n, v in vals if v > max(2, med * 2)]
                if hi:
                    weak.append(f"{lab(k)}: well above the usual level in {', '.join(hi[:3])}.")
                    focus.append((0.8, f"{lab(k)} in {', '.join(hi[:2])}"))
        if people:
            low = [p for p in people if next(c for c in p["cells"] if c["key"] == "attendance")["status"] == "bad"]
            if low:
                weak.append(f"{len(low)} of {len(people)} leaders below the attendance benchmark.")
        focus = [f for _, f in sorted(focus, key=lambda x: -x[0])][:3]
        return {"strong": strong[:5] or ["Nothing clearly above benchmark yet in this view."],
                "weak": weak[:5] or ["Nothing clearly below benchmark in this view."], "focus": focus or ["Keep the current pace: no red areas in this view."]}

    # ---------------------------------------------------------------------------- the screen
    def build(self, store: str | None = None, dept: str | None = None, section: str | None = None, role: str | None = None) -> dict:
        ins = self.ins
        if ins.empty:
            return {"empty": True}
        all_stores = ins.stores(include_myli=True)
        if dept == "Health & Beauty":
            all_stores = [s for s in all_stores if s.endswith("Myli")] or all_stores
        elif dept:
            all_stores = [s for s in all_stores if not s.endswith("Myli")]
        stores = [store] if store else all_stores
        vals = self.unit(stores, dept, section)
        tiles = [{"key": k, "label": CRITERIA[k]["label"], "value": vals[k], "status": status(k, vals[k], self.t)} for k in UNIT_KEYS]
        # next level down
        if not store:
            kind, grid = "stores", [{"name": s, "go": {"store": s}, "cells": self.cells(self.unit([s], dept, section), UNIT_KEYS)} for s in all_stores]
        elif not dept:
            kind, grid = "departments", [{"name": SHORT[d], "go": {"dept": d}, "cells": self.cells(self.unit(stores, d, None), UNIT_KEYS)}
                                         for d in DEPARTMENTS if d not in ("Non Food",) and (d != "Health & Beauty" or store.endswith("Myli"))]
        elif not section and len(sections_of(dept)) > 1:
            kind, grid = "sections", [{"name": s, "go": {"section": s}, "cells": self.cells(self.unit(stores, dept, s), UNIT_KEYS)} for s in sections_of(dept)]
        else:
            kind, grid = "", []
        grid = [g for g in grid if any(c["value"] is not None for c in g["cells"] if c["key"] not in ("leavers", "da"))]
        ppl = self.people(stores, dept, section, role)
        used = [k for k in UNIT_KEYS if vals[k] is not None or any(next(c for c in g["cells"] if c["key"] == k)["value"] is not None for g in grid)]
        pused = [k for k in PEOPLE_KEYS if any(next(c for c in p["cells"] if c["key"] == k)["value"] is not None for p in ppl)]
        label = " · ".join(x for x in [store or "Country", SHORT.get(dept, dept) if dept else "", section or "", ROLES[role][0] if role in ROLES else ""] if x)
        return {"empty": False, "label": label, "as_of": str(ins.as_of), "period": ins.view_label if isinstance(getattr(ins, "view_label", ""), str) else ins.view_label(),
                "filters": {"store": store, "dept": dept, "section": section, "role": role},
                "options": {"stores": ins.stores(include_myli=True), "depts": [[d, SHORT[d]] for d in DEPARTMENTS],
                            "sections": sections_of(dept) if dept else [], "roles": [[k, v[0]] for k, v in ROLES.items()]},
                "criteria": {k: {"label": v["label"], "short": v["short"], "fmt": v["fmt"], "better": v["better"], **self.t[k]} for k, v in CRITERIA.items()},
                "tiles": [t for t in tiles if t["key"] in used], "grid_kind": kind, "grid": grid, "grid_keys": used,
                "people": ppl, "people_keys": pused, "notes": self.notes([t for t in tiles if t["key"] in used], grid, kind, ppl)}


def fmt(key: str, v) -> str:
    if v is None:
        return "—"
    f = CRITERIA[key]["fmt"]
    if f == "pct0":
        return f"{v:.0f}%"
    if f == "pct1":
        return f"{v:.1f}%"
    if f == "pct1s":
        return f"{v:+.1f}%"
    if f == "pp2s":
        return f"{v:+.2f} pts"
    if f == "dec1":
        return f"{v:.1f}"
    return f"{v:.0f}"


def person(api, emp: str = "", key: str = "") -> dict:
    """A leader's data sheet: every criterion against its benchmark, ratings over time, time in role, and direction."""
    rv = Review(api)
    l = next((x for x in rv.ins.leaders() if (emp and str(x.employee_id) == str(emp)) or (key and x.key == key)), None)
    if l is None:
        raise ValueError("This person is not in the current data.")
    row = rv.leader_row(l, None)
    ratings = [{"cycle": r.get("cycle"), "rating": r.get("rating"), "label": r.get("rating_label") or r.get("label")} for r in l.ratings if r.get("rating") is not None]
    trend = None
    if len(ratings) >= 2:
        d = ratings[-1]["rating"] - ratings[-2]["rating"]
        trend = "improving" if d > 0 else "slipping" if d < 0 else "steady"
    comps = [{"key": k, "label": CRITERIA.get(k, {}).get("label", k.replace("_", " ").title()), "value": round(v / 10, 1)} for k, v in (l.components or {}).items()]
    peers = [p for p in rv.people([l.store] if False else rv.ins.stores(include_myli=True), None, None, None) if p["level"] == row["level"]]
    bench = {}
    for c in row["cells"]:
        vs = [next(x for x in p["cells"] if x["key"] == c["key"])["value"] for p in peers]
        vs = [v for v in vs if v is not None]
        bench[c["key"]] = round(median(vs), 1) if len(vs) >= 3 else None
    a = next((r for r in rv.att() if r["emp"] == str(l.employee_id)), None)
    return {"row": row, "criteria": {k: {"label": v["label"], "fmt": v["fmt"], **rv.t[k]} for k, v in CRITERIA.items()}, "peer_median": bench,
            "peers": len(peers), "ratings": ratings, "trend": trend, "components": comps,
            "facts": {"Employee number": l.employee_id, "Store": l.store, "Role": l.designation + (" (acting)" if l.acting else ""),
                      "Area": row["area"], "In role": f"{l.months_in_role} months" if l.months_in_role is not None else "—",
                      "With the company": f"{l.months_service // 12} yrs {l.months_service % 12} m" if l.months_service else "—",
                      "Reports to": l.manager_name or "—", "Attendance days": f"{a['worked']} of {a['due']}" if a else "—"},
            "remarks": l.remarks}
