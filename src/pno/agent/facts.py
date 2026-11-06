"""6.0: everything Ask P&O AI knows, taken from the master sheet and scored exactly like the Review screen.

One `Facts` per question: every leader in the chosen period with their results, points, score, category, ratings, time in role,
store and manager; store results; how complete the data is. The tools only read from here, so the AI and the screens always agree.
"""

from __future__ import annotations

import re
import statistics
from datetime import date

from .. import master, review
from ..util import norm

KEYS = ["sales", "productivity", "shrink", "stock_days", "leavers", "da", "nps", "rating"]
GROUP = {6: "Store Manager", 5: "Deputy Manager", 4: "Department Head", 3: "Section Manager", 2: "Team Leader", 1: "Staff"}
ROLE_ALIASES = [
    (r"store managers?|\bsms?\b|\bgms?\b|general managers?", "store"),
    (r"deputy (store )?managers?|\bdms?\b|\bdy\.? ?mgrs?\b", "deputy"),
    (r"department heads?|dept\.? heads?|\bdhs?\b|heads? of department", "dept"),
    (r"section managers?", "section"),
    (r"team leaders?|\btls?\b|supervisors?", "tl"),
]
ROLE_LEVELS = {"store": (6, 9), "deputy": (5, 5), "dept": (4, 5), "section": (3, 3), "tl": (2, 2)}


def category(score: float | None) -> str:
    if score is None:
        return "Not scored"
    return "High" if score >= 7 else "Good" if score >= 5 else "Low"


def _months(d: str | None, ref: date) -> int | None:
    if not d:
        return None
    try:
        x = date.fromisoformat(d)
    except ValueError:
        return None
    return max(0, (ref.year - x.year) * 12 + ref.month - x.month)


def _yrs(m: int | None) -> str:
    return "—" if m is None else f"{m // 12} yrs {m % 12} m"


class Facts:
    def __init__(self, api):
        self.api = api
        self.rv = review.Review(api)
        self.period = self.rv.period
        self.empty = not self.rv.rows
        self.period_label = master.label(self.period["period_type"], self.period["period_from"], self.period["period_to"]) if self.period else ""
        self.periods = [master.label(p["period_type"], p["period_from"], p["period_to"]) for p in master.periods(api.db)]
        ref = date.fromisoformat((self.period["period_to"] if self.period else date.today().strftime("%Y-%m")) + "-28")
        C = review.CRITERIA
        self.criteria = {k: {"label": C[k]["label"], "weight": self.rv.cfg[k]["weight"], "on": self.rv.cfg[k].get("show", True),
                             "green": self.rv.t[k]["green"], "amber": self.rv.t[k]["amber"],
                             "better": "higher" if C[k]["better"] == "up" else "lower"} for k in KEYS}
        sm_of = {r["store"]: r["name"] for r in self.rv.rows if (r["level"] or 0) >= 6}
        dh_of = {(r["store"], r["department"]): r["name"] for r in self.rv.rows if r["level"] == 4}
        self.leaders: list[dict] = []
        for r in self.rv.rows:
            row = self.rv.leader_row(r)
            cells = {c["key"]: c for c in row["cells"]}
            sc = cells["score"]["value"]
            lvl = r["level"] or 1
            mgr = (sm_of.get(r["store"]) if lvl < 6 else None) if lvl >= 4 else (dh_of.get((r["store"], r["department"])) or sm_of.get(r["store"]))
            self.leaders.append({
                "emp": r["emp"], "key": row["key"], "name": r["name"], "designation": r["designation"], "level": lvl,
                "role": GROUP.get(lvl if lvl < 6 else 6, r["designation"]), "store": r["store"] or r["bu"], "format": r.get("format") or "",
                "city": r.get("city") or "", "department": r.get("department") or "", "section": r.get("section_raw") or r.get("section") or "",
                "grade": r.get("grade") or "", "joined": r.get("doj"), "with_company": _yrs(_months(r.get("doj"), ref)),
                "role_since": r.get("role_since"), "in_role": _yrs(_months(r.get("role_since"), ref)),
                "in_role_months": _months(r.get("role_since"), ref),
                "ratings": r.get("ratings") or ({"rating": r["rating"]} if r.get("rating") else {}),
                "values": {k: r.get(k) for k in KEYS},
                "shown": {k: review.fmt(k, r.get(k)) for k in KEYS},
                "status": {k: cells[k]["status"] for k in KEYS if k in cells},
                "points": row.get("points", {}),
                "score": sc, "category": category(sc), "custom_criteria": row.get("custom", False),
                "measured": row.get("measured", 0), "missing": [C[k]["label"] for k in KEYS if r.get(k) is None],
                "manager": mgr,
            })
        # rank within the same level (higher score first); ties share a rank
        for lvl in {p["level"] for p in self.leaders}:
            ps = sorted([p for p in self.leaders if p["level"] == lvl and p["score"] is not None], key=lambda p: -p["score"])
            for p in ps:
                p["rank"] = f"{1 + sum(1 for q in ps if q['score'] > p['score'])} of {len(ps)}"
        self.by_emp = {str(p["emp"]): p for p in self.leaders if p["emp"]}

    # ---------------------------------------------------------------- finding people and stores
    def find(self, who: str) -> tuple[dict | None, list[dict]]:
        w = str(who or "").strip()
        if not w:
            return None, []
        if w in self.by_emp:
            return self.by_emp[w], []
        m = re.search(r"\d{5,}", w)
        if m and m.group(0) in self.by_emp:
            return self.by_emp[m.group(0)], []
        n = norm(w)
        exact = [p for p in self.leaders if norm(p["name"]) == n]
        if len(exact) == 1:
            return exact[0], []
        part = exact or [p for p in self.leaders if n and (n in norm(p["name"]) or norm(p["name"]) in n)]
        if len(part) == 1:
            return part[0], []
        if not part:                                # every word of the question's name appears in theirs (any order, spelling close)
            words = [x for x in n.split() if len(x) > 2]
            part = [p for p in self.leaders if words and all(any(_close(x, y) for y in norm(p["name"]).split()) for x in words)]
            if len(part) == 1:
                return part[0], []
        return None, part[:10]

    def find_in_text(self, text: str) -> tuple[dict | None, list[dict]]:
        """A leader named anywhere in a question ("tell me about arslan", "how is Saad Jilani doing")."""
        t = norm(text)
        m = re.search(r"\b\d{5,}\b", text)
        if m and m.group(0) in self.by_emp:
            return self.by_emp[m.group(0)], []
        full = [p for p in self.leaders if len(p["name"]) > 4 and re.search(rf"\b{re.escape(norm(p['name']))}\b", t)]
        if full:
            longest = max(len(p["name"]) for p in full)
            full = [p for p in full if len(p["name"]) == longest]
            return (full[0], []) if len(full) == 1 else (None, full)
        words = set(t.split())
        stop = {"ALI", "MUHAMMAD", "SYED", "KHAN", "AHMAD", "AHMED", "HUSSAIN", "HASSAN", "SHAH", "MALIK", "THE", "AND"}
        best, hits = 0, []
        for p in self.leaders:
            parts = [x for x in norm(p["name"]).split() if len(x) > 2]
            k = sum(1 for x in parts if x in words)
            distinct = sum(1 for x in parts if x in words and x not in stop)
            if not distinct:
                continue
            if k > best:
                best, hits = k, [p]
            elif k == best:
                hits.append(p)
        if len(hits) == 1:
            return hits[0], []
        return None, hits[:8]

    def stores(self) -> list[str]:
        return self.rv.stores()

    def find_store(self, name: str) -> str | None:
        if not name:
            return None
        n = norm(name)
        sts = self.stores()
        for s in sts:
            if norm(s) == n:
                return s
        hits = [s for s in sts if n in norm(s) or norm(s) in n]
        if len(hits) == 1:
            return hits[0]
        words = [w for w in n.split() if len(w) > 2 and w not in ("LAH", "ISL", "KCH", "FAI", "GUJ", "MALL", "CITY", "STORE", "HM", "SM", "PK")]
        hits = [s for s in sts if words and any(w in norm(s).split() for w in words)]
        return hits[0] if hits else None

    def stores_in_text(self, text: str) -> list[str]:
        t = norm(text)
        out = []
        for s in self.stores():
            words = [w for w in norm(s).split() if len(w) > 2 and w not in ("LAH", "ISL", "KCH", "FAI", "GUJ", "MALL", "CITY", "MARKAZ", "DHA")]
            if norm(s) in t or any(re.search(rf"\b{re.escape(w)}\b", t) for w in words):
                out.append(s)
        return out

    # ---------------------------------------------------------------- views
    def person(self, p: dict) -> dict:
        """Everything about one leader."""
        sheet = review.person(self.api, key=p["key"])
        C = sheet["criteria"]
        peers = [q for q in self.leaders if q["level"] == p["level"] and q["key"] != p["key"]]
        same_store = [q for q in self.leaders if q["store"] == p["store"] and q["key"] != p["key"]]
        res = []
        for k in KEYS:
            if p["values"][k] is None:
                continue
            res.append({"criterion": C[k]["label"], "result": p["shown"][k], "status": p["status"].get(k),
                        "points_out_of_10": p["points"].get(k), "weight_pct": self.criteria[k]["weight"],
                        "green_line": review.fmt(k, C[k]["green"]), "amber_line": review.fmt(k, C[k]["amber"]),
                        "peer_median": review.fmt(k, sheet["peer_median"].get(k))})
        out = {
            "name": p["name"], "employee_no": p["emp"], "designation": p["designation"], "level": p["role"],
            "store": p["store"], "format": p["format"], "city": p["city"], "department": p["department"], "section": p["section"],
            "grade": p["grade"], "joined": p["joined"], "with_company": p["with_company"], "in_current_role_since": p["role_since"],
            "time_in_role": p["in_role"], "reports_to": p["manager"],
            "period": self.period_label,
            "score_out_of_10": p["score"], "category": p["category"], "rank_among_same_level": p.get("rank"),
            "score_note": None if p["score"] is not None else f"Not scored: only {p['measured']} of 8 criteria filled (3 needed).",
            "own_criteria": p["custom_criteria"],
            "results": res, "not_filled_yet": p["missing"],
            "how_the_score_is_made": [{"criterion": c["label"], "points": c["value"], "share_pct": c["share"]} for c in sheet["components"]],
            "ratings_by_year": {x["cycle"]: (x["rating"] if x["rating"] is not None else "Unrated") for x in sheet["ratings"]},
            "rating_trend": sheet["trend"],
            "strong_on": [C[k]["label"] for k in KEYS if p["status"].get(k) == "good"],
            "below_benchmark_on": [C[k]["label"] for k in KEYS if p["status"].get(k) == "bad"],
            "average_score_same_level": _avg([q["score"] for q in peers]),
            "same_store_leaders": [{"name": q["name"], "designation": q["designation"], "score": q["score"]} for q in same_store][:12],
            "history": sheet["history"],
        }
        return out

    def people(self, query: str = "", store: str = "", dept: str = "", section: str = "", role: str = "", fmt: str = "",
               category: str = "", criterion: str = "", sort: str = "score", ascending: bool = False, limit: int = 30) -> dict:
        st = self.find_store(store) if store else None
        if store and not st:
            return {"error": f"No store matches {store}.", "stores": self.stores()}
        lo, hi = ROLE_LEVELS.get(role, (1, 9))
        q = norm(query)
        dk = _dept_key(dept)
        rows = []
        for p in self.leaders:
            if st and p["store"] != st:
                continue
            if role and not (lo <= p["level"] <= hi):
                continue
            if dk and dk not in norm(p["department"]):
                continue
            if section and norm(section) not in norm(p["section"]):
                continue
            if fmt and not norm(p["format"]).startswith(norm(fmt)[:4]):
                continue
            if category and p["category"].lower() != category.lower():
                continue
            if q and q not in norm(p["name"]) and q not in norm(p["designation"]) and q not in str(p["emp"]):
                continue
            rows.append(p)
        key = _crit_key(criterion or sort)
        if key in KEYS:
            better_up = self.criteria[key]["better"] == "higher"
            rows = [p for p in rows if p["values"][key] is not None]
            rows.sort(key=lambda p: p["values"][key], reverse=(better_up != bool(ascending)))
        elif sort == "name":
            rows.sort(key=lambda p: p["name"])
        elif sort == "time_in_role":
            rows.sort(key=lambda p: (p["in_role_months"] is None, p["in_role_months"] or 0), reverse=not ascending)
        else:
            rows.sort(key=lambda p: (p["score"] is None, (p["score"] or 0) * (1 if ascending else -1)))
        n = len(rows)
        lim = max(1, min(int(limit or 30), 100))
        return {"period": self.period_label, "total_matching": n, "sorted_by": self.criteria[key]["label"] if key in KEYS else sort,
                "people": [{"emp": p["emp"], "name": p["name"], "designation": p["designation"], "store": p["store"], "format": p["format"],
                            "department": p["department"], "score": p["score"], "category": p["category"], "rank": p.get("rank"),
                            "time_in_role": p["in_role"], "results": {self.criteria[k]["label"]: p["shown"][k] for k in KEYS if p["values"][k] is not None},
                            "not_filled": p["missing"], "_values": p["values"], "_status": p["status"]} for p in rows[:lim]],
                "average_score": _avg([p["score"] for p in rows])}

    def store_view(self, name: str) -> dict:
        st = self.find_store(name)
        if not st:
            return {"error": f"No store matches {name}.", "stores": self.stores()}
        r = self.api.api_review(store=st)
        C = r["criteria"]
        team = [p for p in self.leaders if p["store"] == st]
        sm = next((p for p in team if p["level"] >= 6), None)
        return {"store": st, "format": team[0]["format"] if team else "", "city": team[0]["city"] if team else "", "period": self.period_label,
                "store_manager": sm and {"name": sm["name"], "score": sm["score"], "category": sm["category"], "time_in_role": sm["in_role"]},
                "store_results": {C[t["key"]]["label"]: f"{review.fmt(t['key'], t['value'])} ({t['status']})" for t in r["tiles"] if t["value"] is not None},
                "strong": r["notes"]["strong"], "weak": r["notes"]["weak"], "focus": r["notes"]["focus"],
                "departments": {g["name"]: {C[c["key"]]["label"]: review.fmt(c["key"], c["value"]) for c in g["cells"] if c["value"] is not None} for g in r["grid"]},
                "leaders": [{"name": p["name"], "designation": p["designation"], "department": p["department"], "score": p["score"],
                             "category": p["category"], "below_benchmark_on": [self.criteria[k]["label"] for k in KEYS if p["status"].get(k) == "bad"],
                             "not_filled": p["missing"]} for p in sorted(team, key=lambda p: -p["level"])],
                "average_leader_score": _avg([p["score"] for p in team])}

    def league(self) -> dict:
        out = []
        for st in self.stores():
            team = [p for p in self.leaders if p["store"] == st]
            sm = next((p for p in team if p["level"] >= 6), None)
            out.append({"store": st, "format": team[0]["format"] if team else "", "store_manager": sm and sm["name"],
                        "store_manager_score": sm and sm["score"],
                        **({self.criteria[k]["label"]: sm["shown"][k] for k in KEYS if k != "rating" and sm["values"][k] is not None} if sm else {}),
                        "leaders": len(team), "average_leader_score": _avg([p["score"] for p in team])})
        return {"period": self.period_label, "stores": out}

    def overview(self) -> dict:
        r = self.api.api_review()
        C = r["criteria"]
        sc = [p["score"] for p in self.leaders if p["score"] is not None]
        by = {}
        for p in self.leaders:
            g = by.setdefault(p["role"], {"people": 0, "scores": []})
            g["people"] += 1
            if p["score"] is not None:
                g["scores"].append(p["score"])
        return {"period": self.period_label, "periods_loaded": self.periods, "leaders": len(self.leaders), "stores": len(self.stores()),
                "country_results": {C[t["key"]]["label"]: f"{review.fmt(t['key'], t['value'])} ({t['status']})" for t in r["tiles"] if t["value"] is not None},
                "strong": r["notes"]["strong"], "weak": r["notes"]["weak"], "focus": r["notes"]["focus"],
                "average_score": _avg(sc), "high": sum(1 for p in self.leaders if p["category"] == "High"),
                "good": sum(1 for p in self.leaders if p["category"] == "Good"), "low": sum(1 for p in self.leaders if p["category"] == "Low"),
                "not_scored": sum(1 for p in self.leaders if p["category"] == "Not scored"),
                "by_level": {k: {"people": v["people"], "average_score": _avg(v["scores"])} for k, v in by.items()}}

    def health(self) -> dict:
        cov = master.coverage(self.rv.rows)
        return {"period": self.period_label, "periods_loaded": self.periods, "people": cov["people"], "filled_pct": cov["filled_pct"],
                "by_criterion": {m["label"]: f"{m['filled']} of {m['of']} ({m['pct']}%)" for m in cov["measures"]},
                "by_store": {s["name"]: f"{s['pct']}%" for s in cov["stores"]},
                "who_is_missing_what": [{"name": g["name"], "store": g["store"], "missing": g["missing"]} for g in cov["gaps"]][:40]}

    def criteria_text(self) -> str:
        parts = []
        for k, c in self.criteria.items():
            if not c["on"]:
                continue
            parts.append(f"{c['label']} {c['weight']:g}% (green {review.fmt(k, c['green'])}, amber {review.fmt(k, c['amber'])}, {c['better']} is better)")
        return "; ".join(parts)


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 1) if xs else None


def _close(a: str, b: str) -> bool:
    if a == b or (len(a) > 3 and (b.startswith(a) or a.startswith(b))):
        return True
    if len(a) > 4 and len(b) > 4:
        import difflib
        return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8
    return False


_DEPTS = [("CONSUMER GOODS", r"\bCG\b|CONSUMER|FMCG|GROCERY"), ("FRESH FOOD", r"\bFF\b|FRESH|\bFOOD\b"),
          ("HEAVY HOUSEHOLD", r"\bHHH\b|HEAVY"), ("LIGHT HOUSEHOLD", r"\bLHH\b|LIGHT"), ("NON FOOD", r"NON ?FOOD|\bNF\b"),
          ("TEXTILE", r"TEXTILE|\bTXT\b"), ("SERVICES", r"SERVICE"), ("MANAGEMENT", r"MANAGEMENT")]


def _dept_key(d: str) -> str:
    if not d:
        return ""
    n = norm(d)
    return next((k for k, rx in _DEPTS if re.search(rx, n)), n)


_CRIT = [("sales", r"SALES|BUDGET"), ("productivity", r"PRODUCTIV"), ("shrink", r"SHRINK"), ("stock_days", r"STOCK"),
         ("leavers", r"LEAVER|TURNOVER|ATTRITION"), ("da", r"\bDA\b|DISCIPLIN"), ("nps", r"NPS|CUSTOMER"), ("rating", r"RATING")]


def _crit_key(s: str) -> str:
    n = norm(s or "")
    return next((k for k, rx in _CRIT if re.search(rx, n)), s or "")


def role_in(text: str) -> str:
    t = text.lower()
    return next((k for rx, k in ROLE_ALIASES if re.search(rx, t)), "")
