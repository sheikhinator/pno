"""4.0 Department Review: the one screen the P&O director presents from.

Any slice (country → store → department → section, plus a role filter) gets the same criteria, each coloured against
its benchmark, the next level down as a comparison grid, plain-language strong / weak / focus notes, and a benchmark
table of the people in that slice with every criterion visible and the score as the last column. No ranks, no tiers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import median
from typing import Any

from .po import canon

DEPARTMENTS = ["Consumer Goods", "Fresh Food", "Light Household", "Heavy Household", "Textile", "Non Food", "Health & Beauty"]
SHORT = {"Consumer Goods": "CG", "Fresh Food": "Fresh Food", "Light Household": "LHH", "Heavy Household": "HHH", "Textile": "Textile",
         "Non Food": "Non Food", "Health & Beauty": "H&B"}
ROLES = {"store": ("Store managers", 5, 9), "dept": ("Department heads", 4, 4), "section": ("Section managers", 3, 3), "tl": ("Team leaders", 1, 2)}

# key: label, format, better ("up" | "down" | None), green, amber  (None thresholds = shown without colour)
# 6.0: exactly the measures of the master sheet
CRITERIA: dict[str, dict] = {
    "sales": dict(short="Sales vs bud.", label="Sales vs budget", fmt="pct1s", unit="% vs budget", better="up", green=0, amber=-5),
    "productivity": dict(short="Productivity", label="Productivity vs target", fmt="pct0s", unit="% vs target", better="up", green=0, amber=-10),
    "shrink": dict(short="Shrink", label="Shrinkage vs budget", fmt="pct2s", unit="% vs budget", better="down", green=0, amber=0.5),
    "stock_days": dict(short="Stock days", label="Stock days vs budget", fmt="pct0", unit="% of budget", better="down", green=100, amber=120),
    "leavers": dict(short="Leavers", label="Leavers", fmt="int", unit="", better="down", green=0, amber=2, count=True),
    "da": dict(short="DA cases", label="Disciplinary cases", fmt="int", unit="", better="down", green=0, amber=2, count=True),
    "nps": dict(short="NPS", label="Customer NPS", fmt="int", unit="", better="up", green=50, amber=30),
    "rating": dict(short="Rating", label="Rating", fmt="dec1", unit="/5", better="up", green=4, amber=3),
    "score": dict(short="Score", label="Score", fmt="dec1", unit="/10", better="up", green=7, amber=5),
}
UNIT_KEYS = ["sales", "productivity", "shrink", "stock_days", "leavers", "da", "nps"]
PEOPLE_KEYS = ["sales", "productivity", "shrink", "stock_days", "leavers", "da", "nps", "rating", "score"]
CRITERIA_VERSION = 6


# how much each criterion counts in a person's score (0 = shown but not counted); the director can change all of it
WEIGHTS = {"sales": 25, "productivity": 20, "shrink": 15, "stock_days": 10, "leavers": 10, "da": 5, "nps": 10, "rating": 5}


def upgrade(db) -> None:
    """Criteria from before the master sheet (growth, OOS, waste, attendance, sales as % of budget) don't fit: start fresh once."""
    if (db.get_setting("criteria_version", 0) or 0) < CRITERIA_VERSION:
        db.set_setting("review_criteria", {})
        db.set_setting("review_targets", {})
        db.set_setting("person_criteria", {})
        db.set_setting("criteria_version", CRITERIA_VERSION)


def config(db) -> dict:
    """Per criterion: shown on the Review, its weight in the score, and where green and amber start."""
    t = targets(db)
    saved = db.get_setting("review_criteria", {}) or {}
    out = {}
    for k, c in CRITERIA.items():
        if k == "score":
            continue
        s = saved.get(k, {})
        out[k] = {"show": bool(s.get("show", True)), "weight": float(s.get("weight", WEIGHTS.get(k, 0))), **t[k]}
    return out


def points(key: str, v: float | None, t: dict) -> float | None:
    """A result on a 0-10 scale against its benchmark: amber line = 5, green line = 7, one step (green − amber) past green = 10."""
    if v is None:
        return None
    g, a = t[key]["green"], t[key]["amber"]
    if g is None or a is None:
        return None
    up = CRITERIA[key]["better"] == "up"
    x = v if up else -v
    g, a = (g, a) if up else (-g, -a)
    span = max(abs(g - a), 1e-9)
    if CRITERIA[key].get("count") and x >= g:
        p = 10.0                                         # none at all is the best result possible
    elif x >= g:
        p = 7 + 3 * min(1.0, (x - g) / span)
    elif x >= a:
        p = 5 + 2 * (x - a) / span
    else:
        p = 5 * max(0.0, 1 - (a - x) / (2 * span))
    return round(max(0.0, min(10.0, p)), 2)


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


def _month_end(ym: str) -> str:
    import calendar
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{ym[:7]}-{calendar.monthrange(y, m)[1]:02d}"


class Review:
    def __init__(self, api, cfg: dict | None = None, t: dict | None = None):
        from . import master
        self.api = api
        upgrade(api.db)
        self.period = master.chosen(api.db)
        self.rows = master.rows_for(api.db, self.period)
        self.t = t or targets(api.db)
        self.cfg = cfg or config(api.db)

    # ---------------------------------------------------------------------------- where the numbers come from
    def stores(self) -> list[str]:
        fm = {"Hypermarket": 0, "Supermarket": 1}
        return sorted({r["store"] for r in self.rows if r["store"]}, key=lambda s: (fm.get(canon.store_format(s), 2), s))

    @staticmethod
    def _dept(r) -> str:
        return r["department"] or ""

    def _in(self, r, dept: str | None, section: str | None) -> bool:
        if section:
            return r["section"] == section
        if dept:
            secs = members(dept, None) or []
            return self._dept(r) == dept or r["section"] in secs or (dept == "Non Food" and self._dept(r) in secs)
        return True

    def _owner_value(self, store: str, dept: str | None, section: str | None, f: str):
        """The figure for one store and area, taken from the leader responsible for it: the section's people, the department
        head, the store manager; when that leader has no figure, worked out from the level below."""
        rs = [r for r in self.rows if r["store"] == store]
        count = f in ("leavers", "da")
        if section:
            vals = [r[f] for r in rs if r["section"] == section and r.get(f) is not None]
            if not vals:
                return None
            return max(vals) if count else round(sum(vals) / len(vals), 2)      # the people of one section share its figures
        if dept:
            heads = [r[f] for r in rs if r["level"] == 4 and self._in(r, dept, None) and r.get(f) is not None]
            if heads:
                return sum(heads) if count else round(sum(heads) / len(heads), 2)
            secs = sorted({r["section"] for r in rs if self._in(r, dept, None) and r["level"] < 4})
            vals = [v for v in (self._owner_value(store, None, sc, f) for sc in secs) if v is not None]
            if not vals:
                return None
            return sum(vals) if count else round(sum(vals) / len(vals), 2)
        top = [r[f] for r in rs if r["level"] >= 5 and r.get(f) is not None]
        if top:
            return top[0]
        depts = sorted({self._dept(r) for r in rs if self._dept(r) and self._dept(r) not in ("Management", "Overall", "Services")})
        vals = [v for v in (self._owner_value(store, d, None, f) for d in depts) if v is not None]
        if not vals:
            return None
        return sum(vals) if count else round(sum(vals) / len(vals), 2)

    def unit(self, stores: list[str], dept: str | None, section: str | None) -> dict[str, float | None]:
        out = {}
        for f in UNIT_KEYS:
            vals = [v for v in (self._owner_value(s, dept, section, f) for s in stores) if v is not None]
            if not vals:
                out[f] = None
            elif f in ("leavers", "da"):
                out[f] = int(sum(vals))
            else:
                v = sum(vals) / len(vals)
                out[f] = round(v) if f in ("nps", "stock_days") else round(v, 2 if f == "shrink" else 1)
        return out

    def cells(self, vals: dict, keys: list[str], person: bool = False) -> list[dict]:
        return [{"key": k, "value": vals.get(k),
                 "status": "neutral" if CRITERIA[k].get("count") and not person and vals.get(k) is not None else status(k, vals.get(k), self.t)} for k in keys]

    # ---------------------------------------------------------------------------- people
    def leader_row(self, r: dict, secs=None) -> dict:
        vals = {k: r.get(k) for k in PEOPLE_KEYS if k != "score"}
        area = r["section"] if r["level"] < 5 else "Whole store"
        row = {"emp": r["emp"], "key": r["emp"] or r["name"], "name": r["name"], "store": r["store"] or r["bu"], "role": r["designation"],
               "area": area, "level": r["level"], "acting": False, "grade": r.get("grade"), "doj": r.get("doj"),
               "cells": self.cells(vals, PEOPLE_KEYS, person=True)}
        self.score_row(row)
        row["measured"] = sum(1 for c in row["cells"] if c["value"] is not None and c["key"] != "score")
        return row

    def _custom(self) -> dict:
        if not hasattr(self, "_pc"):
            self._pc = self.api.db.get_setting("person_criteria", {}) or {}
        return self._pc

    @staticmethod
    def _compute(cells: list[dict], cfg: dict, t: dict) -> tuple[float | None, list[dict]]:
        parts = []
        for c in cells:
            if c["key"] == "score" or c["key"] not in cfg:
                continue
            cf = cfg.get(c["key"], {})
            w = cf.get("weight", 0) if cf.get("show", True) else 0      # a criterion switched off doesn't count
            pt = points(c["key"], c["value"], t) if w > 0 else None
            if pt is not None:
                parts.append({"key": c["key"], "label": CRITERIA[c["key"]]["label"], "points": pt, "weight": w})
        total = sum(p["weight"] for p in parts)
        sc = round(sum(p["points"] * p["weight"] for p in parts) / total, 1) if total and len(parts) >= 3 else None
        for p in parts:
            p["share"] = round(100 * p["weight"] / total) if total else 0
        return sc, parts

    def person_setup(self, key: str) -> tuple[dict, dict] | None:
        """The criteria saved for one person (their own weights and lines), merged over the standard ones."""
        own = self._custom().get(str(key)) if key else None
        if not own:
            return None
        cfg = {k: dict(v) for k, v in self.cfg.items()}
        t = {k: dict(v) for k, v in self.t.items()}
        for k, v in own.items():
            if k in cfg:
                cfg[k].update(show=bool(v.get("show", True)), weight=float(v.get("weight") or 0))
                if v.get("green") is not None and v.get("amber") is not None:
                    t[k] = {"green": float(v["green"]), "amber": float(v["amber"])}
        return cfg, t

    def score_row(self, row: dict) -> None:
        """Score = weighted average of each criterion's points (0-10 against its benchmark), using the weights in Settings —
        or the person's own criteria when some were saved for them (marked 'custom')."""
        std, std_parts = self._compute(row["cells"], self.cfg, self.t)
        own = self.person_setup(row.get("key"))
        cfg, t = own if own else (self.cfg, self.t)
        sc, parts = (self._compute(row["cells"], cfg, t) if own else (std, std_parts))
        row["parts"] = parts
        row["custom"] = bool(own)
        if own:
            row["std_score"] = std
            for c in row["cells"]:                      # their own lines colour their results too
                if c["key"] != "score" and c["value"] is not None:
                    c["status"] = status(c["key"], c["value"], t)
        row["points"] = {c["key"]: points(c["key"], c["value"], t) for c in row["cells"]
                         if c["key"] != "score" and c["value"] is not None and points(c["key"], c["value"], t) is not None}
        for c in row["cells"]:
            if c["key"] == "score":
                c["value"], c["status"] = sc, status("score", sc, self.t)

    def people(self, stores: list[str], dept: str | None, section: str | None, role: str | None) -> list[dict]:
        lo, hi = (ROLES[role][1], ROLES[role][2]) if role in ROLES else (1, 9)
        out = []
        for r in self.rows:
            if r["store"] not in stores or not (lo <= (r["level"] or 1) <= hi):
                continue
            if (dept or section) and not self._in(r, dept, section):
                continue
            if (dept or section) and r["level"] >= canon.STORE_LEVEL and role != "store":
                continue                                     # store managers run the whole store, not one department
            out.append(self.leader_row(r))
        order = {s: i for i, s in enumerate(stores)}
        out.sort(key=lambda p: (order.get(p["store"], 99), -p["level"], p["area"], p["name"]))
        return out

    def sections_of(self, dept: str) -> list[str]:
        secs = members(dept, None) or []
        have = {r["section"] for r in self.rows if r["section"] and (r["section"] in secs or self._dept(r) == dept) and r["section"] != dept}
        return sorted(have)

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
            unrated = [p for p in people if next(c for c in p["cells"] if c["key"] == "rating")["value"] is None]
            if unrated and len(unrated) < len(people):
                focus.append((0.1, f"Ratings still to fill for {len(unrated)} of {len(people)} leaders"))
        focus = [f for _, f in sorted(focus, key=lambda x: -x[0])][:3]
        return {"strong": strong[:5] or ["Nothing clearly above benchmark yet in this view."],
                "weak": weak[:5] or ["Nothing clearly below benchmark in this view."], "focus": focus or ["Keep the current pace: no red areas in this view."]}

    # ---------------------------------------------------------------------------- the screen
    def build(self, store: str | None = None, dept: str | None = None, section: str | None = None, role: str | None = None) -> dict:
        from . import master
        if not self.rows:
            return {"empty": True}
        all_stores = self.stores()
        stores = [store] if store else all_stores
        vals = self.unit(stores, dept, section)
        shown = [k for k in UNIT_KEYS if self.cfg[k]["show"]]
        tiles = [{"key": k, "label": CRITERIA[k]["label"], "value": vals[k],
                  "status": "neutral" if CRITERIA[k].get("count") and vals[k] is not None else status(k, vals[k], self.t)} for k in shown]
        present = [d for d in DEPARTMENTS if any(self._in(r, d, None) for r in self.rows if r["store"] in stores)]
        if not store:
            kind, grid = "stores", [{"name": s, "go": {"store": s}, "cells": self.cells(self.unit([s], dept, section), UNIT_KEYS)} for s in all_stores]
        elif not dept:
            kind, grid = "departments", [{"name": SHORT[d], "go": {"dept": d}, "cells": self.cells(self.unit(stores, d, None), UNIT_KEYS)}
                                         for d in present if d != "Non Food"]
        elif not section and len(self.sections_of(dept)) > 1:
            kind, grid = "sections", [{"name": s, "go": {"section": s}, "cells": self.cells(self.unit(stores, dept, s), UNIT_KEYS)}
                                      for s in self.sections_of(dept)]
        else:
            kind, grid = "", []
        grid = [g for g in grid if any(c["value"] is not None for c in g["cells"] if c["key"] not in ("leavers", "da"))]
        ppl = self.people(stores, dept, section, role)
        used = [k for k in shown if vals[k] is not None or any(next(c for c in g["cells"] if c["key"] == k)["value"] is not None for g in grid)]
        pused = [k for k in PEOPLE_KEYS if (k == "score" or self.cfg[k]["show"]) and any(next(c for c in p["cells"] if c["key"] == k)["value"] is not None for p in ppl)]
        label = " · ".join(x for x in [store or "Country", SHORT.get(dept, dept) if dept else "", section or "", ROLES[role][0] if role in ROLES else ""] if x)
        plab = master.label(self.period["period_type"], self.period["period_from"], self.period["period_to"]) if self.period else ""
        return {"empty": False, "label": label, "as_of": _month_end(self.period["period_to"]) if self.period else "", "period_label": plab,
                "filters": {"store": store, "dept": dept, "section": section, "role": role},
                "options": {"stores": all_stores, "depts": [[d, SHORT[d]] for d in DEPARTMENTS if d in present or d == dept],
                            "sections": self.sections_of(dept) if dept else [], "roles": [[k, v[0]] for k, v in ROLES.items()],
                            "section_groups": [[SHORT[d], d, self.sections_of(d)] for d in DEPARTMENTS if d != "Non Food" and self.sections_of(d)]},
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
    if f == "pct2s":
        return f"{v:+.2f}%"
    if f == "pct0s":
        return f"{v:+.0f}%"
    if f == "dec1":
        return f"{v:.1f}"
    return f"{v:.0f}"


def person(api, emp: str = "", key: str = "") -> dict:
    """A leader's data sheet: every criterion against its benchmark and against peers at the same level."""
    from . import master
    rv = Review(api)
    r = next((x for x in rv.rows if (emp and str(x["emp"]) == str(emp)) or (key and (x["emp"] or x["name"]) == key)), None)
    if r is None:
        raise ValueError("This person is not in the current data.")
    row = rv.leader_row(r)
    comps = [{"key": x["key"], "label": x["label"], "value": x["points"], "weight": x["weight"], "share": x["share"]} for x in row.get("parts", [])]
    peers = [p for p in rv.people(rv.stores(), None, None, None) if p["level"] == row["level"]]
    bench = {}
    for c in row["cells"]:
        vs = [next(x for x in p["cells"] if x["key"] == c["key"])["value"] for p in peers]
        vs = [v for v in vs if v is not None]
        bench[c["key"]] = round(median(vs), 1) if len(vs) >= 3 else None
    own = rv.person_setup(row.get("key"))
    eff_cfg, eff_t = own if own else (rv.cfg, rv.t)
    months = None
    if r.get("doj"):
        try:
            d = date.fromisoformat(r["doj"])
            ref = date.fromisoformat((rv.period["period_to"] if rv.period else date.today().strftime("%Y-%m")) + "-28")
            months = max(0, (ref.year - d.year) * 12 + ref.month - d.month)
        except ValueError:
            pass
    plab = master.label(rv.period["period_type"], rv.period["period_from"], rv.period["period_to"]) if rv.period else ""
    history = []
    for p in master.periods(api.db):
        if p["id"] == (rv.period or {}).get("id"):
            continue
        x = next((y for y in master.rows_for(api.db, p) if y["emp"] == r["emp"]), None)
        if x:
            h = rv.leader_row(x)
            history.append({"period": master.label(p["period_type"], p["period_from"], p["period_to"]),
                            "score": next(c["value"] for c in h["cells"] if c["key"] == "score"), "rating": x.get("rating")})
    return {"row": row, "criteria": {k: {"label": v["label"], "fmt": v["fmt"], "better": v["better"], "count": bool(v.get("count")), **eff_t[k]}
                                     for k, v in CRITERIA.items()}, "peer_median": bench, "custom": bool(own),
            "standard": {k: {"weight": v["weight"], "show": v["show"], "green": rv.t[k]["green"], "amber": rv.t[k]["amber"]} for k, v in rv.cfg.items()},
            "peers": len(peers), "ratings": _ratings(r, plab), "trend": _trend(r),
            "components": comps, "history": history,
            "peer_scores": [next((x["value"] for x in p["cells"] if x["key"] == "score"), None) for p in peers if p.get("key") != row.get("key")],
            "weights": {k: {"weight": v["weight"], "show": v["show"]} for k, v in eff_cfg.items()},
            "facts": {"Employee number": r["emp"], "Store": r["store"] or r["bu"], "Role": r["designation"], "Section": r["section_raw"] or r["section"],
                      "Grade": r.get("grade") or "—", "Joined": r.get("doj") or "—",
                      "With the company": f"{months // 12} yrs {months % 12} m" if months is not None else "—",
                      "In current role since": _since(r.get("role_since"), rv.period), "Period": plab},
            "remarks": "", "record": None}


def _ratings(r: dict, plab: str) -> list[dict]:
    yrs = r.get("ratings") or {}
    if yrs:
        return [{"cycle": y, "rating": v, "label": "" if v is not None else "Unrated"} for y, v in sorted(yrs.items())]
    return [{"cycle": plab, "rating": r["rating"], "label": ""}] if r.get("rating") else []


def _trend(r: dict) -> str | None:
    vals = [v for _, v in sorted((r.get("ratings") or {}).items()) if v is not None]
    if len(vals) < 2:
        return None
    return "improving" if vals[-1] > vals[0] else "slipping" if vals[-1] < vals[0] else "steady"


def _since(d: str | None, period: dict | None) -> str:
    if not d:
        return "—"
    try:
        x = date.fromisoformat(d)
        ref = date.fromisoformat(((period or {}).get("period_to") or date.today().strftime("%Y-%m")) + "-28")
        m = max(0, (ref.year - x.year) * 12 + ref.month - x.month)
        return f"{x:%b %Y} ({m // 12} yrs {m % 12} m)"
    except ValueError:
        return d


def _record(api, emp: str) -> dict | None:
    """Everything else P&O holds on the person: every fact with its source, the timeline, attendance, corrections, team."""
    if not emp:
        return None
    try:
        pg = api._brain().person_page(emp)
    except Exception:  # noqa: BLE001
        return None
    keep = ("facts", "timeline", "attendance", "corrections", "insights", "reports", "team", "sources", "left", "manager", "department",
            "service_months", "in_role_months")
    return {k: pg.get(k) for k in keep}
