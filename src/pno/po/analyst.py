"""P&O analyst: answers plain-English questions from the imported workbook.

The engine does the arithmetic; this module only decides which calculation a
question needs and phrases the result. It never invents a number: if the data
is not in the workbook, it says so.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from . import canon, privacy
from .insights import WEIGHT_LABELS, Insights, Leader, tenure_text
from .format import BAD, GOOD, WARN, leader_name, leader_profile_html, money, number, pct, pp, score_text, tone

METRICS: list[tuple[str, tuple[str, ...], str, bool]] = [
    # key, trigger words, label, higher-is-better
    ("sales_vs_budget_pct", ("budget", "plan", "target sales", "achievement"), "Sales vs budget", True),
    ("growth_pct", ("growth", "last year", "ly", "grow"), "Sales growth vs LY", True),
    ("productivity_vs_target_pct", ("productivity", "productive", "sph"), "Productivity vs target", True),
    ("shrink_variance_avg", ("shrink", "wastage", "loss"), "Shrinkage vs budget", True),
    ("oos_pct", ("oos", "out of stock", "availability"), "Out of stock", False),
    ("margin_pct", ("margin", "profit"), "Net margin", True),
    ("leavers_12m", ("turnover", "leaver", "attrition", "resign", "left"), "Leavers", False),
    ("da_cases", ("disciplin", " da ", "warning"), "Disciplinary cases", False),
    ("nps", ("nps", "customer score", "satisfaction"), "NPS", True),
    ("sales", ("sales", "revenue", "turnover in pkr"), "Sales", True),
    ("avg_leader_score", ("index", "score", "people"), "Average leader index", True),
]

SUGGESTIONS = [
    "Brief me for the Country review",
    "Which stores need attention?",
    "Rank stores by productivity vs target",
    "Who are the top 5 section leaders?",
    "Who are the weakest leaders in Lucky One?",
    "Compare Fortress and Emporium",
    "Brief me on Packages Mall",
    "Where is turnover highest?",
    "Which roles are at risk?",
    "Explain the leader index",
]


def _h(title: str) -> str:
    return f"<div style='font-size:15px;font-weight:800;color:#31261D;margin:2px 0 6px'>{escape(title)}</div>"


def _li(items: list[str]) -> str:
    return "<ul style='margin-top:2px'>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def _c(value_text: str, color: str) -> str:
    return f"<b style='color:{color}'>{value_text}</b>"


class PoAnalyst:
    def __init__(self, insights: Insights):
        self.i = insights
        self.blocks: list[dict] = []          # KPI cards and charts shown with the answer

    def _kpis(self, items: list[tuple[str, str, str, str]]) -> None:
        self.blocks.append({"type": "kpis", "items": [{"label": l, "value": v, "sub": s, "tone": t} for l, v, s, t in items]})

    def _chart(self, kind: str, title: str, labels: list, values: list, name: str = "", fmt: str = "num", ref=None, tone: str = "") -> None:
        pairs = [(str(l), float(v)) for l, v in zip(labels, values) if v is not None]
        if len(pairs) >= 2:
            self.blocks.append({"type": "chart", "kind": kind, "title": title, "labels": [p[0] for p in pairs][:25],
                                "series": [{"name": name, "values": [round(p[1], 2) for p in pairs][:25]}], "fmt": fmt, "ref": ref, "tone": tone})

    # ---------------------------------------------------------- routing --

    def answer(self, question: str) -> str | None:
        self.blocks = []
        if self.i.empty:
            return None
        q = f" {question.casefold().strip()} "
        if re.search(r"\bh\s*&\s*b\b|\bhb\b|myli|health\s*(and|&)\s*beauty", q) and not any(s.endswith("· Myli") for s in self.i.stores()):
            return None                              # H&B (Myli) stores are only in the sales report: answered from there
        stores = self._stores_in(q)
        leader = self._leader_in(question)
        wants_rank = bool(re.search(r"\b(top|best|bottom|worst|weakest|strongest|lowest|highest|rank|ranking|league|most|least)\b", q))
        about_leaders = bool(re.search(r"\b(leader|leaders|manager|managers|people|team lead|section manager|who)\b", q))

        if re.search(r"explain|how .*(index|score)|what is the (index|score)|methodology", q):
            return self.explain_index()
        if leader and not wants_rank and not (stores and not re.search(r"about|brief|who is|profile|how is", q)):
            return self.leader_brief(leader)
        if re.search(r"\b(compare|vs|versus|against)\b", q) and len(stores) >= 2:
            return self.compare(stores[:3])
        if re.search(r"bench|succession|roles?\b.*\bat risk|acting|\bdoa\b|not in system|new in role", q):
            return self.bench()
        if re.search(r"\bnps\b|net promoter|customer score|promoter|detractor|satisfaction", q):
            return self.nps(stores[0] if stores else None)
        if re.search(r"talent|9.?box|nine.?box|stars?\b|high potential", q):
            return self.talent()
        if re.search(r"roster|shift|leave|day off|coverage|evening|morning", q) and not wants_rank:
            return self.roster(stores[0] if stores else None)
        if re.search(r"turnover|leaver|attrition|resign|left the company|exit", q) and not (wants_rank and "store" in q):
            return self.turnover(stores[0] if stores else None)
        if wants_rank and about_leaders and not re.search(r"\bstores?\b", q):
            return self.rank_leaders(q, stores[0] if stores else None)
        if wants_rank:
            return self.rank_stores(q)
        if re.search(r"attention|alert|risk|problem|issue|priorit|worry|concern|red flag", q):
            return self.alerts(stores[0] if stores else None)
        if stores:
            return self.store_brief(stores[0])
        if re.search(r"brief|summary|overview|review|how are we|how is the country|headline|meeting", q):
            return self.country_brief()
        return None

    def _stores_in(self, q: str) -> list[str]:
        found = []
        for name in self.i.stores():
            canonical = canon.store(q)
            if canonical == name and name not in found:
                found.append(name)
        # several stores mentioned: scan word by word windows
        tokens = re.findall(r"[a-z0-9&]+", q)
        for size in (3, 2, 1):
            for start in range(len(tokens) - size + 1):
                chunk = " ".join(tokens[start:start + size])
                name = canon.store(chunk)
                if name in self.i.stores() and name not in found:
                    found.append(name)
        return found

    def _leader_in(self, question: str) -> Leader | None:
        tokens = re.findall(r"[A-Za-z0-9]+", question)
        stop = {"tell", "me", "about", "who", "is", "how", "the", "brief", "for", "my", "meeting", "with", "prepare", "doing",
                "of", "in", "and", "store", "section", "leader", "profile", "show", "give", "what", "on", "a", "an", "performance",
                "muhammad", "syed", "ali", "khan", "ahmed", "ahmad", "mohammad", "hafiz", "rana", "abdul", "malik"}
        names = [t for t in tokens if t.casefold() not in stop and (len(t) > 2 or (t.isdigit() and len(t) == 2))]
        if not names:
            return None
        best: tuple[int, Leader] | None = None
        for leader in self.i.leaders():
            key = canon.name_key(leader.name).split()
            hits = sum(1 for n in names if n.casefold() in key)
            if hits and (best is None or hits > best[0]):
                best = (hits, leader)
        if best and best[0] >= 1:
            # require the match to be specific: unique best, or two-word match
            ties = [l for l in self.i.leaders() if sum(1 for n in names if n.casefold() in canon.name_key(l.name).split()) == best[0]]
            if len(ties) == 1 or best[0] >= 2:
                return best[1]
        return None

    # --------------------------------------------------------- answers --

    def country_brief(self) -> str:
        h = self.i.headline()
        cards = self.i.store_scorecard()
        ranked = sorted((c for c in cards if c.get("sales_vs_budget_pct") is not None), key=lambda c: -c["sales_vs_budget_pct"])
        leaders = [l for l in self.i.leaders() if l.score is not None]
        lines = [
            f"Country sales are {_c(money(h['sales']), '#31261D')}, {_c(pct(h['sales_vs_budget_pct']), tone(h['sales_vs_budget_pct'], 100, 92))} of budget "
            f"and {_c(pct(h['growth_pct'], True), tone(h['growth_pct'], 5, 0))} versus last year.",
            f"Productivity is {_c(pct(h['productivity_vs_target_pct'], True), tone(h['productivity_vs_target_pct'], 0, -10))} against target on average across {h['stores']} stores.",
            f"{h['stores_on_track']} of {h['stores']} stores are on track; {h['stores_at_risk']} at risk.",
        ]
        if ranked:
            lines.append(f"Best against budget: <b>{escape(ranked[0]['store'])}</b> ({pct(ranked[0]['sales_vs_budget_pct'], digits=0)}). "
                         f"Furthest behind: <b>{escape(ranked[-1]['store'])}</b> ({pct(ranked[-1]['sales_vs_budget_pct'], digits=0)}).")
        if h["leavers_12m"] is not None:
            lines.append(f"{h['leavers_12m']} people left ({self.i.leaver_window}) ({pct(h['voluntary_pct'], digits=0)} voluntary); {number(h['da_cases'])} disciplinary cases are on record.")
        if leaders:
            lines.append(f"Strongest leader on the leader index: <b>{escape(leader_name(leaders[0]))}</b> ({escape(leaders[0].store)}, {escape(leaders[0].section_text)}, {score_text(leaders[0].score)}).")
        alerts = self.i.alerts(4)
        lvl = lambda v, g, b: "good" if v is not None and v >= g else ("bad" if v is not None and v <= b else "warn")  # noqa: E731
        self._kpis([("Sales MTD", money(h["sales"]), f"{pct(h['sales_vs_budget_pct'])} of budget", lvl(h["sales_vs_budget_pct"], 100, 92)),
                    ("Growth vs LY", pct(h["growth_pct"], True), "all stores", lvl(h["growth_pct"], 5, 0)),
                    ("Productivity vs target", pct(h["productivity_vs_target_pct"], True), "average", lvl(h["productivity_vs_target_pct"], 0, -10)),
                    ("Stores on track", f"{h['stores_on_track']}/{h['stores']}", f"{h['stores_at_risk']} at risk", "good" if not h["stores_at_risk"] else "warn"),
                    ("Leavers", number(h["leavers_12m"]), f"{pct(h['voluntary_pct'], digits=0)} voluntary", "")])
        self._chart("hbar", "Sales vs budget by store (%)", [c["store"] for c in ranked], [c["sales_vs_budget_pct"] for c in ranked], "% of budget", "pct0", 100)
        out = _h(f"Country brief · data as of {h['as_of']:%d %b %Y}") + _li(lines)
        if alerts:
            out += _h("Top priorities") + _li([f"<b>{escape(a['store'])}</b> · {escape(a['message'])}" for a in alerts])
        return out

    def store_brief(self, store_name: str) -> str:
        card = next((c for c in self.i.store_scorecard() if c["store"] == store_name), None)
        if not card:
            return _h(store_name) + "<p>No workbook data for this store.</p>"
        lines = [
            f"Status: {_c(card['status'], {'On track': GOOD, 'Watch': WARN, 'At risk': BAD}.get(card['status'], '#756E68'))}",
            f"Sales {money(card['sales'])} · {_c(pct(card['sales_vs_budget_pct'], digits=0), tone(card['sales_vs_budget_pct'], 100, 92))} of budget · "
            f"{_c(pct(card['growth_pct'], True), tone(card['growth_pct'], 5, 0))} vs LY · margin {pct(card['margin_pct'])} · OOS {pct(card['oos_pct'])}",
            f"Productivity {number(card['productivity'])} vs target {number(card['productivity_target'])} "
            f"({_c(pct(card['productivity_vs_target_pct'], True, 0), tone(card['productivity_vs_target_pct'], 0, -10))})",
            f"Shrinkage: average {pp(card['shrink_variance_avg'])} vs budget" + (f"; worst section {escape(card['shrink_worst_section'])} ({pp(card['shrink_worst_variance'])})" if card.get("shrink_worst_section") else ""),
            f"People: {card['leaders']} leaders · avg rating {number(card['avg_rating'], 2)} · {number(card['leavers_12m'])} leavers ({self.i.leaver_window}) · {number(card['da_cases'])} DA cases",
        ]
        if card.get("nps") is not None:
            lines.append(f"Customer NPS ({escape(card['city'])}): {number(card['nps'], 0)}")
        leaders = sorted((l for l in self.i.leaders() if l.store == store_name and l.score is not None), key=lambda l: -l.score)
        self._kpis([("Sales vs budget", pct(card["sales_vs_budget_pct"], digits=0), money(card["sales"]), "good" if (card["sales_vs_budget_pct"] or 0) >= 100 else "bad"),
                    ("Growth vs LY", pct(card["growth_pct"], True), "", "good" if (card["growth_pct"] or 0) >= 0 else "bad"),
                    ("Productivity vs target", pct(card["productivity_vs_target_pct"], True, 0), number(card["productivity"]), "good" if (card["productivity_vs_target_pct"] or 0) >= 0 else "bad"),
                    ("Status", card["status"], f"{card['leaders']} leaders", {"On track": "good", "Watch": "warn", "At risk": "bad"}.get(card["status"], ""))])
        if leaders:
            self._chart("hbar", f"{store_name} · leader index (out of 10)", [leader_name(l) for l in leaders[:15]], [l.score / 10 for l in leaders[:15]], "Index", "score")
        out = _h(f"{store_name} · store brief") + _li(lines)
        if leaders:
            out += _h("Leaders by leader index") + _li([
                f"{escape(leader_name(l))} — {escape(l.section_text)} · {_c(score_text(l.score), tone(l.score, 70, 45))}" for l in leaders[:6]])
            if len(leaders) > 6:
                out += f"<p style='color:#756E68'>Lowest: {escape(leader_name(leaders[-1]))} ({escape(leaders[-1].section_text)}, {score_text(leaders[-1].score)}).</p>"
        alerts = [a for a in self.i.alerts() if a["store"] == store_name][:5]
        if alerts:
            out += _h("Needs attention") + _li([escape(a["message"]) for a in alerts])
        return out

    def leader_brief(self, leader: Leader) -> str:
        return leader_profile_html(self.i, leader)

    def compare(self, stores: list[str]) -> str:
        cards = {c["store"]: c for c in self.i.store_scorecard()}
        rows = [
            ("Status", "status", None), ("Sales", "sales", money), ("vs budget", "sales_vs_budget_pct", lambda v: pct(v, digits=0)),
            ("Growth vs LY", "growth_pct", lambda v: pct(v, True)), ("Productivity vs target", "productivity_vs_target_pct", lambda v: pct(v, True, 0)),
            ("Shrinkage vs budget", "shrink_variance_avg", pp), ("Out of stock", "oos_pct", pct), ("Margin", "margin_pct", pct),
            ("Leavers", "leavers_12m", number), ("DA cases", "da_cases", number), ("Avg rating", "avg_rating", lambda v: number(v, 2)),
            ("Leader index", "avg_leader_score", score_text),
        ]
        metrics = [("vs budget %", "sales_vs_budget_pct"), ("Growth %", "growth_pct"), ("Prod. vs target %", "productivity_vs_target_pct"), ("OOS %", "oos_pct")]
        self.blocks.append({"type": "chart", "kind": "bar", "title": " vs ".join(stores), "labels": [m for m, _ in metrics], "fmt": "num",
                            "series": [{"name": st, "values": [round(cards.get(st, {}).get(k) or 0, 1) for _, k in metrics]} for st in stores]})
        head = "<tr><th align='left'></th>" + "".join(f"<th align='left'>{escape(s)}</th>" for s in stores) + "</tr>"
        body = ""
        for label, key, fmt in rows:
            body += f"<tr><td style='color:#756E68'>{label}</td>" + "".join(
                f"<td><b>{escape(str(cards.get(s, {}).get(key) or '—')) if fmt is None else (fmt(cards.get(s, {}).get(key)) if cards.get(s, {}).get(key) is not None else '—')}</b></td>"
                for s in stores) + "</tr>"
        return _h(" vs ".join(stores)) + f"<table cellpadding='5'>{head}{body}</table>"

    def _metric(self, q: str) -> tuple[str, str, bool]:
        for key, words, label, higher in METRICS:
            if any(w in q for w in words):
                return key, label, higher
        return "sales_vs_budget_pct", "Sales vs budget", True

    @staticmethod
    def _direction(q: str, higher_is_better: bool) -> tuple[bool, str]:
        """(descending?, title suffix) from the wording of the question."""
        if re.search(r"\b(highest|most|largest|biggest|maximum)\b", q):
            return True, " (highest first)"
        if re.search(r"\b(lowest|least|fewest|smallest|minimum)\b", q):
            return False, " (lowest first)"
        if re.search(r"\b(worst|weakest|bottom|poorest)\b", q):
            return (not higher_is_better), " (weakest first)"
        return higher_is_better, ""

    def rank_stores(self, q: str) -> str:
        key, label, higher = self._metric(q)
        cards = [c for c in self.i.store_scorecard() if c.get(key) is not None]
        descending, suffix = self._direction(q, higher)
        cards.sort(key=lambda c: c[key], reverse=descending)
        n = self._count(q, len(cards))
        fmt = {"sales": money, "leavers_12m": number, "da_cases": number, "nps": lambda v: number(v, 0),
               "avg_leader_score": score_text, "shrink_variance_avg": pp}.get(key, lambda v: pct(v, key.endswith("growth_pct") or "vs_target" in key))
        items = [f"<b>{escape(c['store'])}</b> — {fmt(c[key])}" for c in cards[:n]]
        title = f"Stores by {label.lower()}{suffix}"
        self._chart("hbar", title, [c["store"] for c in cards[:n]], [c[key] / (10 if key == "avg_leader_score" else 1) for c in cards[:n]], label,
                    "pct" if key.endswith("pct") else "num", 100 if key == "sales_vs_budget_pct" else None, "signed" if key in ("growth_pct", "productivity_vs_target_pct", "shrink_variance_avg") else "")
        return _h(title) + "<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"

    def rank_leaders(self, q: str, store_name: str | None) -> str:
        leaders = [l for l in self.i.leaders() if l.score is not None and (store_name is None or l.store == store_name)]
        for section in canon.SECTION_ORDER:
            if section.casefold() in q or (section == "Fruits & Vegetables" and re.search(r"f&v|fruit", q)):
                leaders = [l for l in leaders if section in l.sections]
                break
        weakest = bool(re.search(r"\b(worst|weakest|bottom|lowest|least)\b", q))
        leaders.sort(key=lambda l: l.score, reverse=not weakest)
        n = self._count(q, len(leaders))
        scope = f" in {store_name}" if store_name else ""
        if not leaders:
            return _h("Leaders") + "<p>No scored leaders match that question.</p>"
        items = []
        for l in leaders[:n]:
            strongest = max(l.components.items(), key=lambda kv: kv[1]) if l.components else None
            weakest_c = min(l.components.items(), key=lambda kv: kv[1]) if l.components else None
            note = ""
            if strongest and weakest_c:
                note = f" · strongest: {WEIGHT_LABELS[strongest[0]].lower()}, weakest: {WEIGHT_LABELS[weakest_c[0]].lower()}"
            items.append(f"<b>{escape(leader_name(l))}</b> ({escape(l.store)}, {escape(l.section_text)}) — index "
                         f"{_c(score_text(l.score), tone(l.score, 70, 45))}{note}")
        title = ("Weakest" if weakest else "Top") + f" {min(n, len(leaders))} leaders{scope} by leader index"
        self._chart("hbar", title + " (out of 10)", [leader_name(l) for l in leaders[:n]], [l.score / 10 for l in leaders[:n]], "Index", "score")
        return _h(title) + "<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"

    @staticmethod
    def _count(q: str, maximum: int) -> int:
        m = re.search(r"\b(\d{1,2})\b", q)
        words = {"three": 3, "five": 5, "ten": 10}
        for w, v in words.items():
            if w in q:
                return min(v, maximum)
        if m:
            return min(int(m.group(1)), maximum)
        if re.search(r"\b(top|bottom|best|worst|weakest|strongest)\b", q) and "rank" not in q:
            return min(5, maximum)
        return maximum

    def alerts(self, store_name: str | None) -> str:
        alerts = [a for a in self.i.alerts() if store_name is None or a["store"] == store_name][:12]
        if not alerts:
            return _h("Nothing flagged") + "<p>No alert rules were triggered for this scope.</p>"
        per: dict = {}
        for a in [x for x in self.i.alerts() if store_name is None or x["store"] == store_name]:
            per[a["store"]] = per.get(a["store"], 0) + (3 if a["severity"] == "High" else 1)
        top = sorted(per.items(), key=lambda kv: -kv[1])[:12]
        self._chart("hbar", "Attention points by store (high = 3, other = 1)", [k for k, _ in top], [v for _, v in top], "Points", "int")
        items = [f"<span style='color:{ {'High': BAD, 'Medium': WARN}.get(a['severity'], '#756E68') }'><b>{a['severity']}</b></span> · "
                 f"{escape(a['area'])} · <b>{escape(a['store'])}</b> — {escape(a['message'])}" for a in alerts]
        return _h("What needs attention" + (f" in {store_name}" if store_name else "")) + _li(items)

    def turnover(self, store_name: str | None) -> str:
        t = self.i.turnover_summary()
        if not self.i.has("po_turnover"):
            return _h("Turnover") + "<p>The turnover tab has not been imported.</p>"
        if store_name:
            rows = self.i.leavers(store_name)
            reasons: dict[str, int] = {}
            for r in rows:
                reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
            items = [f"{len(rows)} leavers ({self.i.leaver_window})"] + [f"{escape(k)}: {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:5]]
            return _h(f"Turnover · {store_name}") + _li(items)
        self._kpis([("Leavers 12m", str(t["total"]), f"{t['all_time']} on file", "warn"), ("Voluntary", pct(t["voluntary_pct"], digits=0), "resignations", ""),
                    ("Top hotspot", t["hotspots"][0][0] if t["hotspots"] else "—", f"{t['hotspots'][0][1]}: {t['hotspots'][0][2]}" if t["hotspots"] else "", "bad")])
        self._chart("donut", f"Why people leave ({self.i.leaver_window})", [r for r, _ in t["by_reason"][:7]], [n for _, n in t["by_reason"][:7]], "leavers", "int")
        self._chart("hbar", f"Leavers by store ({self.i.leaver_window})", [s_ for s_, _ in t["by_store"][:12]], [n for _, n in t["by_store"][:12]], "Leavers", "int")
        lines = [
            f"<b>{t['total']}</b> leavers ({self.i.leaver_window}, {pct(t['voluntary_pct'], digits=0)} voluntary).",
            "Top reasons: " + ", ".join(f"{escape(r)} ({n})" for r, n in t["by_reason"][:4]),
            "Hotspots: " + "; ".join(f"<b>{escape(s)}</b> {escape(sec)} ({n})" for s, sec, n in t["hotspots"][:4]),
        ]
        return _h("Turnover") + _li(lines)

    def roster(self, store_name: str | None) -> str:
        r = self.i.roster_summary()
        if not r.get("days"):
            return _h("Roster") + "<p>The roster tab has not been imported.</p>"
        gaps = [g for g in r["gaps"] if store_name is None or g["store"] == store_name]
        leave = [x for x in r["leave"] if store_name is None or x[1] == store_name]
        people = len({x["employee_id"] for x in self.i.rows("po_shift") if store_name is None or x["store"] == store_name})
        lines = [f"{people} leaders rostered from {r['days'][0]} to {r['days'][-1]}."]
        if gaps:
            lines.append(f"{len(gaps)} department-day(s) with every leader off: " + "; ".join(f"{escape(g['store'])} {escape(g['department'])} on {g['date']}" for g in gaps[:5]))
        else:
            lines.append("No department is left without a leader on any day.")
        if leave:
            lines.append("Most leave: " + ", ".join(f"{escape(privacy.name(n, n))} ({escape(s)}, {d} days)" for n, s, d in leave[:4]))
        return _h("Roster coverage" + (f" · {store_name}" if store_name else "")) + _li(lines)

    def bench(self) -> str:
        flags = self.i.bench()
        if not flags:
            return _h("Bench strength") + "<p>No roles are flagged.</p>"
        items = [f"<b>{escape(leader_name(f['leader']))}</b> ({escape(f['leader'].store or 'store not set yet')}, {escape(f['leader'].section_text)}) — {escape(f['reason'])}" for f in flags[:12]]
        return _h(f"Roles at risk · {len(flags)} flag(s)") + _li(items)

    def talent(self) -> str:
        groups: dict[str, list[Leader]] = {}
        for l in self.i.leaders():
            box = self.i.talent_box(l)
            if box:
                groups.setdefault(self.i.TALENT_NAMES[box], []).append(l)
        if not groups:
            return _h("Talent grid") + "<p>Leaders need both an appraisal rating and section results to be placed. Import the Performance Rating tab with full data.</p>"
        items = [f"<b>{escape(name)}</b>: " + ", ".join(escape(leader_name(l)) for l in members[:6]) + (" …" if len(members) > 6 else "")
                 for name, members in sorted(groups.items(), key=lambda kv: -len(kv[1]))]
        order = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        self._chart("donut", "Leaders on the talent grid", [k for k, _ in order], [len(v) for _, v in order], "leaders", "int")
        return _h("Talent grid · rating vs results") + _li(items)

    def nps(self, store_name: str | None) -> str:
        rows = [r for r in self.i.rows("po_nps") if r.get("nps") is not None and r.get("year")]
        if not rows:
            return _h("Customer NPS") + "<p>The NPS sheet has not been imported.</p>"
        city = canon.store_city(store_name) if store_name else ""
        if city:
            rows = [r for r in rows if r["city"] == city] or rows
        latest = max(r["year"] for r in rows)
        now_ = [r for r in rows if r["year"] == latest]
        before = {(r["city"], r["category"]): r["nps"] for r in rows if r["year"] == latest - 1}
        avg = sum(r["nps"] for r in now_) / len(now_)
        ranked = sorted(now_, key=lambda r: -r["nps"])
        moves = sorted(((r["nps"] - before[(r["city"], r["category"])], r) for r in now_ if (r["city"], r["category"]) in before), key=lambda t: t[0])
        self._kpis([(f"Average NPS {latest}", f"{avg:+.0f}", city or "all cities", "good" if avg >= 50 else "warn" if avg >= 20 else "bad"),
                    ("Best", ranked[0]["category"][:28], f"{ranked[0]['nps']:+.0f}", "good"), ("Weakest", ranked[-1]["category"][:28], f"{ranked[-1]['nps']:+.0f}", "bad")])
        self._chart("hbar", f"NPS by category · {latest}", [r["category"][:40] for r in ranked], [r["nps"] for r in ranked], "NPS", "int", None, "signed")
        lines = [f"Average NPS {latest}{' in ' + escape(city) if city else ''}: <b>{avg:+.0f}</b> across {len(now_)} categories.",
                 "Best: " + ", ".join(f"<b>{escape(r['category'][:40])}</b> ({r['nps']:+.0f})" for r in ranked[:3]),
                 "Weakest: " + ", ".join(f"<b>{escape(r['category'][:40])}</b> ({r['nps']:+.0f})" for r in ranked[-3:][::-1])]
        if moves:
            lines.append(f"Biggest drop vs {latest - 1}: <b>{escape(moves[0][1]['category'][:40])}</b> ({moves[0][0]:+.0f}); "
                         f"biggest gain: <b>{escape(moves[-1][1]['category'][:40])}</b> ({moves[-1][0]:+.0f}).")
        return _h("Customer NPS") + _li(lines)

    def explain_index(self) -> str:
        weights = self.i.weights
        total = sum(weights.values()) or 1
        items = [f"<b>{escape(WEIGHT_LABELS[k])}</b> — weight {v:g} ({100 * v / total:.0f}%)" for k, v in weights.items()]
        return (_h("How the leader index works") + _li(items) +
                "<p>Each measure is taken from the section(s) the leader runs, scored 0–10 "
                "(e.g. sales 80% of budget = 0, 120% = 10; productivity 80% of target = 0, 120% = 10; shrinkage on budget = 10, "
                "5 pp worse = 0; stock days on budget = 10, 50% over = 0; rating 1–5 → 0–10; 0 leavers = 10, 10+ = 0). "
                "A leader needs at least 3 measures to get an index. Missing data is excluded, never counted as zero. "
                "Weights can be changed in Settings.</p>")


def answer(store: Any, question: str, weights: dict[str, float] | None = None) -> str | None:
    insights = Insights(store, weights=weights)
    return PoAnalyst(insights).answer(question)


def to_markdown(html_text: str) -> str:
    """The analyst's HTML as the chat's markdown: headings and bold kept, lists as bullets."""
    import html as _html
    t = html_text

    def table(match: "re.Match") -> str:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", match.group(0), re.S)
        lines = []
        for i, row in enumerate(rows):
            cells = [re.sub(r"<[^>]+>", "", c).strip() or " " for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
            lines.append("| " + " | ".join(cells) + " |")
            if i == 0:
                lines.append("|" + "---|" * len(cells))
        return "\n" + "\n".join(lines) + "\n"

    t = re.sub(r"<table[^>]*>.*?</table>", table, t, flags=re.S)
    t = re.sub(r"<div style='font-size:15px[^>]*>(.*?)</div>", r"\n**\1**\n", t)
    t = re.sub(r"<div style='font-size:20px[^>]*>(.*?)</div>", r"**\1**\n", t)
    t = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n**\1**\n", t)
    t = re.sub(r"<(b|strong)[^>]*>(.*?)</\1>", r"**\2**", t)
    t = re.sub(r"<li>", "\n- ", t)
    t = re.sub(r"</tr>", "\n", t)
    t = re.sub(r"</t[dh]>", "  ", t)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</ul>|</ol>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\*\*\s*\*\*", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


PO_WORDS = re.compile(r"turnover|leaver|attrition|resign|rating|appraisal|talent|9.?box|bench|succession|acting|\bdoa\b|"
                      r"in role|time in role|tenure|shrink|stock days|\bnps\b|disciplin|\bda\b|roster coverage|shift|p ?& ?o|"
                      r"\bindex\b|\bleaders?\b|brief|compare|attention|heatmap|league|how is .* doing|how are", re.IGNORECASE)
