"""The built-in assistant: answers the common questions with PNO's own queries, no AI model needed.

Used when no Groq key / offline model is available, and as the fallback when an AI service is busy.
"""

from __future__ import annotations

import re
from datetime import date

from ..util import MONTHS, norm, parse_date
from .tools import Toolbox

ROLE_WORDS = [("department head", "DH"), ("dept head", "DH"), ("section manager", "SM"), ("supervisor", "SM"),
              ("store manager", "GM"), ("general manager", "GM"), ("gm", "GM"), ("cco", "CCO"), ("cashier", "STAFF"),
              ("managers", "MANAGERS"), ("manager", "MANAGERS"), ("staff", "STAFF"), ("h&b", "HBM")]
LEAVE_TYPES = ["sick", "annual", "casual", "maternity", "paternity", "hajj", "umrah", "compensatory", "unpaid", "emergency", "marriage"]
HELP = ("I can answer from the imported data, for example:\n"
        "- **Who are the top 10 section managers in Lahore?**\n- **Show the bottom 5 store managers**\n"
        "- **How is Lyallpur Galleria doing?**\n- **Who was absent the most this month?**\n"
        "- **Show missing punches at Fortress**\n- **Score of 20064066** or a person's name\n"
        "- **Show the trend for the last months**\n"
        "- **Khadija Ghafoor was on sick leave 12 to 14 September** (I'll prepare it for you to confirm)\n"
        "- **Add 21 March 2027 as Eid holiday**")


_HEALTH_RX = re.compile(r"data (health|ready|quality|complete|check)|is (my|the) data|what('?s| is) missing|missing (data|reports?|files?)|"
                        r"trust (the|these|my) (numbers|data)|data (gaps?|issues?|problems?)|ready to present", re.I)


def _health_answer(tb: Toolbox) -> str:
    r = tb.t_data_health()
    icon = {"ok": "✅", "derived": "🔁", "older": "🟡", "stale": "🟡", "missing": "❌"}
    lines = [f"**Data health for {r['month']}: {r['score']}/100 · {r['verdict']}.**", "",
             "| Report | Status | Period |", "|---|---|---|"]
    lines += [f"| {c['report']} | {icon.get(c['status'], '')} {c['status']} | {c['period'] or '—'} |" for c in r["checklist"]]
    if r["checks"]:
        lines += ["", "### To check"] + [f"- **{c['area']}**: {c['message']}" for c in r["checks"][:8]]
    if r["locked"]:
        lines += ["", "> This month is **locked**: later imports cannot change it."]
    lines += ["", "Open **Data health** in the menu to see every item and fix it."]
    return "\n".join(lines)


_HIRE_RX = re.compile(r"\b(vacanc|candidate|cv|cvs|resume|shortlist|hiring|hire|recruit|interview|talent bank|applicant)", re.I)


def _hire_answer(tb: Toolbox, q: str) -> str:
    stop = {"who", "are", "the", "best", "top", "for", "candidates", "candidate", "cvs", "cv", "role", "vacancy", "shortlist", "should", "we",
            "interview", "which", "show", "me", "hiring", "how", "is", "going", "our", "what", "position", "job"}
    words = " ".join(w for w in re.findall(r"[a-z&]+", q.lower()) if w not in stop)
    r = tb.t_hiring(vacancy=words)
    if "vacancy" in r:
        v = r["vacancy"]
        lines = [f"**{v['title']}{(' · ' + v['store']) if v['store'] else ''}: {v['bands']['strong']} strong and {v['bands']['possible']} possible "
                 f"candidates out of {sum(v['bands'].values())} CVs.**", "", "| # | Candidate | Score | Recommendation | Highest role | Years | Stage |",
                 "|---|---|---|---|---|---|---|"]
        lines += [f"| {i + 1} | {c['name']} | **{c['score']:.0f}** | {c['recommendation']} | {c['highest_role'] or '—'} | {c['years'] or '—'} | {c['stage']} |"
                  for i, c in enumerate(v["candidates"][:10])]
        checks = [f"- **{c['name']}**: {'; '.join(c['checks'])}" for c in v["candidates"][:10] if c["checks"]]
        if checks:
            lines += ["", "### To check in interview"] + checks[:6]
        if v["internal_candidates"]:
            lines += ["", "> **Internal option:** " + ", ".join(f"{p['name']} ({p['role']}, {p['store']})" for p in v["internal_candidates"][:3])]
        return "\n".join(lines)
    a = r["analytics"]
    if not r["open_vacancies"]:
        return "There are no vacancies yet. Open **Hiring** in the menu to create one and drop in CVs."
    lines = [f"**{a['open']} open vacanc{'y' if a['open'] == 1 else 'ies'} · {a['bank']} people in the talent bank.**", "",
             "| Vacancy | Store | CVs | Strong | Days open |", "|---|---|---|---|---|"]
    lines += [f"| {v['title']} | {v['store'] or '—'} | {v['cvs']} | {v['strong']} | {v['days_open'] if v['days_open'] is not None else '—'} |" for v in r["open_vacancies"]]
    lines += ["", f"Time to hire: {a['time_to_hire'] or '—'} days · offer acceptance: {a['offer_acceptance'] if a['offer_acceptance'] is not None else '—'}%.",
              "Ask about one vacancy by name for its ranked shortlist."]
    return "\n".join(lines)


_LEARN_RX = re.compile(r"\b(course|training|lesson|learning pack|curriculum)\b", re.I)


def _learn_answer(tb: Toolbox, q: str) -> str:
    ql = q.lower()
    if re.search(r"\b(make|create|build|design|generate|prepare)\b", ql):
        h = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|\s)?(?:hours?|hrs?|h)\b", ql)
        role = next((r for r in ("store manager", "department head", "section manager", "team leader", "supervisor", "associate", "cashier") if r in ql), "")
        topic = re.sub(r"\b(make|create|build|design|generate|prepare|a|an|the|course|training|on|about|for|of|hours?|hrs?|\d+|-|"
                       r"store manager|department head|section manager|team leaders?|supervisors?|associates?|cashiers?|s)\b", " ", ql)
        r = tb.t_learning(make=True, topic=" ".join(topic.split()), role=role, hours=float(h.group(1)) if h else 3)
        lines = [f"**Course ready: {r['title']}.** {r['summary']}.", "", "### Modules"] + [f"{i + 1}. {m}" for i, m in enumerate(r["modules"])]
        lines += [f"> {n}" for n in r["notes"]] + ["", r["where"]]
        return "\n".join(lines)
    r = tb.t_learning()
    if not r["courses"]:
        return "No courses yet. Ask me to make one, e.g. *make a 3-hour course on shrink for team leaders*, or open **Learning Studio**."
    st = r["stats"]
    lines = [f"**{st['courses']} courses · {st['assigned']} assignments · {st['completed']} completed"
             f"{(' · average score ' + str(st['avg_score']) + '%') if st['avg_score'] is not None else ''}.**", "",
             "| Course | For | Hours | Assigned | Done |", "|---|---|---|---|---|"]
    lines += [f"| {c['title']} | {c['audience']} | {c['hours']:g} | {c['assigned']} | {c['completed']} |" for c in r["courses"]]
    return "\n".join(lines)


_STRAT_RX = re.compile(r"flight risk|might leave|likely to leave|at risk of leaving|succession|successor|manpower|understaff|overstaff|"
                        r"approved heads|manning|overdue action|open action|action tracker|\bactions\b", re.I)


def _strategy_answer(tb: Toolbox, q: str) -> str:
    r = tb.t_people_strategy()
    ql = q.lower()
    lines = []
    if re.search(r"action", ql):
        a = r["actions"]
        lines += [f"**{a['open'] + a['in_progress']} open actions, {a['overdue']} overdue.**", ""]
        lines += [f"- **{x['title']}** · {x['owner'] or 'no owner'} · due {x['due']}" for x in a["overdue_list"]] or ["Nothing overdue."]
        return "\n".join(lines + ["", "Open **Actions** in the menu to update them."])
    if re.search(r"manpower|staff|manning|heads", ql):
        m = r["manpower"]
        if not m["has_plan"]:
            return (f"**{m['headcount']} people on the Basic Sheet.** No approved manning has been entered yet: open **Manpower** and paste "
                    "Store · Department · Approved heads from Excel to see vacancies and over-staffing.")
        return (f"**{m['headcount']} people against {m['approved']} approved heads (stores with a plan): {m['vacant']} vacant positions, "
                f"{m['over']} above plan, {m['open_vacancies']} open vacancies in Hiring.** Open **Manpower** for the store and department detail.")
    if re.search(r"success", ql):
        gaps = r.get("succession_gaps", [])
        lines += [f"**{len(gaps)} leadership roles with no successor or no one in the role.**", "", "| Store | Role | Status |", "|---|---|---|"]
        lines += [f"| {g['store']} | {g['role']} | {g['status']} |" for g in gaps]
        if r.get("ready_now"):
            lines += ["", "### Ready now"] + [f"- {x['store']} · {x['role']}: **{x['successor']}**" for x in r["ready_now"]]
        return "\n".join(lines)
    risk = r.get("flight_risk", [])
    if not risk:
        return "Import the P&O workbook (Time in role, ratings, turnover) to see flight risk."
    lines += [f"**{sum(1 for x in risk if x['band'] == 'High')} leaders at high and {sum(1 for x in risk if x['band'] == 'Medium')} at medium risk of leaving.**", "",
              "| Leader | Store | Risk | Why |", "|---|---|---|---|"]
    lines += [f"| {x['name']} | {x['store']} | **{x['score']}** {x['band']} | {'; '.join(x['reasons'][:3])} |" for x in risk[:10]]
    lines += ["", "> **Next step:** hold a stay conversation with the top names this week (Flight risk → + Action)."]
    return "\n".join(lines)


def answer(tb: Toolbox, question: str) -> str:
    q = question.strip()
    ql = q.lower()
    if _STRAT_RX.search(ql):
        return _strategy_answer(tb, q)
    if _LEARN_RX.search(ql) and not re.search(r"\b(cv|candidate|vacanc)", ql):
        return _learn_answer(tb, q)
    if _HEALTH_RX.search(ql):
        return _health_answer(tb)
    if _HIRE_RX.search(ql):
        return _hire_answer(tb, q)
    mm = tb._mm()
    if not mm.people and not getattr(mm, "sales", {}):
        return _dataset_answer(tb, q) or _po_answer(tb, q) or "There is no data yet. Import the roster, attendance, productivity and BO sales reports first (Import screen)."
    store = _find_store(tb, mm, ql)
    city = _find_city(ql)
    person, _ = _find_person_in_text(tb, mm, q)
    ds = _dataset_answer(tb, q)
    if ds:
        return ds
    if re.search(r"\bstores?\b", ql) and re.search(r"\b(rank|top|bottom|best|worst|weakest|highest|lowest|compare|vs|versus|below|above|need|attention)\b", ql) \
            and re.search(r"sales|budget|growth|productiv|shrink|stock|oos|out of stock|margin|turnover|leaver|nps|attention|risk|index|\bvs\b|compare", ql):
        po = _po_answer(tb, q)
        if po:
            return po
    if not person:                                   # P&O review topics (leaders, turnover, ratings, shrinkage, roster…)
        po = _po_answer(tb, q, only_if_topic=True)
        if po:
            return po

    # --- data entry: leave and holidays
    if "holiday" in ql and re.search(r"\badd\b|\bmark\b|\bset\b|\bis\b|\bas\b", ql):
        d = _first_date(q, mm.month)
        if d:
            m = re.search(r"\bas\s+(?:an?\s+)?(.+?)\s*holiday", q, re.I) or re.search(r"holiday\s+(?:for|of)\s+(.+)$", q, re.I)
            name = (m.group(1).strip().title() if m else "Gazetted holiday")
            tb.t_propose_holiday(d.isoformat(), name)
            return f"I've prepared **{name}** on **{d:%A %d %B %Y}** as a gazetted holiday. Click **Confirm** to save it."
    if re.search(r"\bleave\b|\bleaves\b|\boff sick\b", ql) and person and re.search(r"\d", ql):
        span = _date_range(q, mm.month)
        if span:
            typ = next((t.title() + " Leave" for t in LEAVE_TYPES if t in ql), "Leave")
            tb.t_propose_leave([{"who": person.emp, "from": span[0].isoformat(), "to": span[1].isoformat(), "type": typ}])
            days = (span[1] - span[0]).days + 1
            return (f"I've prepared **{typ}** for **{person.name}** ({person.emp}) from **{span[0]:%d %b %Y}** to "
                    f"**{span[1]:%d %b %Y}** ({days} day{'s' if days != 1 else ''}). Click **Confirm** to save it; those days will then "
                    "count as leave, not absence.")

    # --- one person
    if person and not re.search(r"\btop\b|\bbottom\b|\bbest\b|\bworst\b|\branking\b", ql):
        d = tb.t_person(person.emp)
        lines = [f"**{d['name']}** · {d['designation']} · {d['store']} ({d['role']})", ""]
        if d["score"] is not None:
            lines.append(f"Score **{d['score']}/10** · {d['band']}" + (" · provisional" if d["provisional"] else "") +
                         f" · measured on {d['measured_on']}")
        else:
            lines.append({"new_joiner": "New joiner: not scored yet.", "not_enough_data": "Not enough data for a score yet."}.get(d["status"], ""))
        rows = [{"Part": c["label"], "Weight": c["weight"], "Result": c["display"] or "No data (left out)",
                 "Score": c["score"] if c["score"] is not None else "—"} for c in d["components"]]
        tb.blocks.append({"type": "table", "title": "How the score is made", "columns": ["Part", "Weight", "Result", "Score"], "rows": rows})
        a = d["attendance"]
        if a.get("worked") is not None:
            lines.append(f"Attendance: {a['worked']} days worked, **{a['absent']} unexplained absences**, {a['leave']} leave, "
                         f"{a['off']} weekly offs, {a['fixes']} punches to fix; {a['compliance'] or 0:.0f}% of days were full 9 hours.")
        if d["context_not_scored"]:
            lines.append("Context (not scored): " + "; ".join(d["context_not_scored"]))
        return "\n".join(x for x in lines if x is not None)

    scope_args = {"store": store["name"] if store else None, "city": city}
    n = _number(ql, 10)

    # --- rankings
    if re.search(r"\btop\b|\bbest\b|\bhighest\b|\bbottom\b|\bworst\b|\blowest\b|\bweakest\b|\brank", ql) and not re.search(r"\bstores?\b(?!\s+manager)", ql):
        role = next((r for w, r in ROLE_WORDS if w in ql), "")
        asc = bool(re.search(r"bottom|worst|lowest|weakest", ql))
        sort = "attendance" if "attendance" in ql else "score"
        res = tb.t_find_people(role=role, sort=sort, ascending=asc, limit=n, **{k: v for k, v in scope_args.items() if v})
        rows = [{"#": i + 1, "Name": r["name"], "Role": r["role_label"], "Store": r["store"],
                 "Score": r["score"] if r["score"] is not None else "—", "Attendance": r["attendance"] if r["attendance"] is not None else "—"}
                for i, r in enumerate(res["people"])]
        tb.blocks.append({"type": "table", "title": "Ranking", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
        if rows:
            tb.blocks.append({"type": "chart", "kind": "hbar", "title": "Score", "labels": [r["Name"] for r in rows],
                              "series": [{"name": "Score", "values": [r["Score"] if r["Score"] != "—" else None for r in rows]}]})
        who = {"GM": "store managers", "DH": "department heads", "SM": "section managers", "CCO": "CCO managers",
               "STAFF": "staff", "MANAGERS": "managers", "HBM": "H&B store leads"}.get(role, "people")
        from ..stores import CITIES
        where = f" in {store['name']}" if store else (f" in {CITIES.get(city, city)}" if city else "")
        return f"{'Bottom' if asc else 'Top'} {len(rows)} {who}{where} by {sort} ({res['total_matching']} in total)."

    # --- attendance
    if re.search(r"absen|attendance|present", ql):
        d = tb.t_attendance(**{k: v for k, v in scope_args.items() if v})
        t = d["totals"]
        res = tb.t_find_people(sort="absent", limit=n, **{k: v for k, v in scope_args.items() if v})
        rows = [{"Name": r["name"], "Store": r["store"], "Absent days": r["absent"], "Presence %": r["presence"]}
                for r in res["people"] if r.get("absent")]
        if rows:
            tb.blocks.append({"type": "table", "title": "Most unexplained absences", "columns": list(rows[0].keys()), "rows": rows})
        return (f"**Real absence {t['absence_pct'] or 0:.1f}%** in {d['month']} (up to {d['up_to']}); the biometric system shows "
                f"{t['system_absence_pct'] or 0:.1f}% because it also counts weekly offs, leave and missing punches.\n"
                f"- {t['fixes']} missing punches to fix\n- {t['long_absence']} people absent 7+ days in a row\n"
                f"- {t['compliance_pct'] or 0:.0f}% of worked days were full 9 hours")

    if re.search(r"punch|missing in|missing out|fix", ql):
        d = tb.t_attendance(**{k: v for k, v in scope_args.items() if v})
        rows = [{"Store": f["store"], "Name": f["name"], "Date": f["day"], "Problem": f["kind"].replace("_", " "),
                 "IN": f["t_in"] or "—", "OUT": f["t_out"] or "—"} for f in d["punches_to_fix_sample"]]
        if rows:
            tb.blocks.append({"type": "table", "title": "Punches to fix (first 15)", "columns": list(rows[0].keys()), "rows": rows})
        return f"There are **{d['totals']['fixes']} missing punches** to fix. The full list is on the Attendance screen and in the Attendance Exceptions export."

    # --- trends
    if re.search(r"trend|history|last \d+ months|over time|month on month|previous month", ql):
        d = tb.t_trend(**{k: v for k, v in scope_args.items() if v})
        ms = d["months"]
        tb.blocks.append({"type": "chart", "kind": "line", "title": "Average score", "labels": [m["month"] for m in ms],
                          "series": [{"name": "Average score", "values": [m["avg_score"] for m in ms]}]})
        tb.blocks.append({"type": "chart", "kind": "line", "title": "Real absence %", "labels": [m["month"] for m in ms],
                          "series": [{"name": "Real absence %", "values": [m["real_absence_pct"] for m in ms]}]})
        from ..stores import CITIES
        return "Month-by-month trend for " + (store["name"] if store else CITIES.get(city, city) if city else "the whole country") + ":"

    # --- a store
    if store and not re.search(r"\bstores\b", ql):
        d = tb.t_store(store["name"])
        t = d["total"] or {}
        rows = [{"Section": f"{s['code']} {s['name']}", "Manager": ", ".join(s["managers"]) or "—",
                 "vs budget %": round(s["sales_pct"]) if s["sales_pct"] is not None else "—",
                 "Productivity %": round(s["prod_pct"]) if s["prod_pct"] is not None else "—"} for s in d["sections"]]
        if rows:
            tb.blocks.append({"type": "table", "title": "Sections", "columns": list(rows[0].keys()), "rows": rows})
        gm = d["gm"]
        return (f"**{d['store']}** ({d['format']}, {d['city']}): store score **{(d['store_score'] or 0):.1f}/10**" +
                (f", GM {gm['name']} **{gm['score']}/10**" if gm and gm["score"] is not None else "") +
                (f". Sales **{t['sales_pct']:.0f}% of budget**, {t['growth']:+.1f}% vs last year" if t.get("sales_pct") is not None else "") +
                f". Real absence {d['attendance']['absence_pct'] or 0:.1f}%, {d['attendance']['fixes']} punches to fix.")

    # --- stores league / overview
    if re.search(r"\bstores?\b|league|compare|overview|summary|how are we|how is|doing", ql) or city:
        d = tb.t_overview(**{k: v for k, v in scope_args.items() if v})
        rows = [{"Store": f"{r['store']} · {r['format']}" if r["format"] else r["store"], "Format": r["format"], "Score": round(r["score"], 1) if r["score"] is not None else "—",
                 "Sales vs budget %": round(r["sales_pct"]) if r["sales_pct"] is not None else "—",
                 "Real absence %": round(r["absence_pct"], 1) if r["absence_pct"] is not None else "—"} for r in d["store_league"]]
        if rows:
            tb.blocks.append({"type": "table", "title": "Store league", "columns": list(rows[0].keys()), "rows": rows})
            tb.blocks.append({"type": "chart", "kind": "hbar", "title": "Average score by store", "labels": [r["Store"] for r in rows],
                              "series": [{"name": "Score", "values": [r["Score"] if r["Score"] != "—" else None for r in rows]}]})
        cards = "; ".join(f"{k}: {_fmt(v)}" for c in d["cards"] for k, v in c.items() if k not in ("change_vs_last_month", "note"))
        return f"**{d['scope']} · {d['month']}** (data up to {d['data_up_to']}). {cards}." + (
            "\n\n" + "\n".join("- " + a for a in d["alerts"]) if d["alerts"] else "")
    return _po_answer(tb, q) or HELP


def _dataset_answer(tb: Toolbox, question: str) -> str | None:
    """A question naming one of the other imported tables: its computed insights."""
    try:
        from ..po import explorer
        q = norm(question)
        for d in explorer.datasets(tb.db):
            names = [norm(x) for x in (d.get("ai_title"), d["title"], d["file"].rsplit(".", 1)[0]) if x]
            if any(n and len(n) >= 4 and n in q for n in names):
                v = explorer.view(tb.db, d["id"])
                return f"**{v['title']}** ({v['rows']:,} rows)\n\n" + "\n".join(f"- {i}" for i in v["insights"]) + \
                    "\n\nOpen **Other data** to regroup it or chart another column."
    except Exception:
        return None
    return None


def _po_answer(tb: Toolbox, question: str, only_if_topic: bool = False) -> str | None:
    """Questions about the P&O review workbook (leaders, turnover, ratings, shrinkage, roster…)."""
    try:
        from ..po.analyst import PO_WORDS, PoAnalyst, to_markdown
        if only_if_topic and not PO_WORDS.search(question):
            return None
        ins = tb.svc.api._po()
        if ins.empty:
            return None
        an = PoAnalyst(ins)
        html = an.answer(question)
        if html:
            tb.blocks.extend(an.blocks[:3])
        return to_markdown(html) if html else None
    except Exception:
        return None


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.1f}"
    return "—" if v is None else str(v)


def _number(ql: str, default: int) -> int:
    m = re.search(r"\b(?:top|bottom|best|worst|first|last)?\s*(\d{1,3})\b", ql)
    try:
        n = int(m.group(1)) if m else default
    except ValueError:
        n = default
    return max(1, min(n, 50)) if n < 1000 else default


def _find_store(tb, mm, ql: str):
    best = None
    for s in mm.stores.values():
        n = s["name"].lower()
        if len(n) >= 3 and re.search(rf"\b{re.escape(n)}\b", ql):
            if not best or len(n) > len(best["name"]):
                best = s
    return best


def _find_city(ql: str):
    from ..stores import CITIES
    for code, name in CITIES.items():
        if re.search(rf"\b{name.lower()}\b", ql) or re.search(rf"\b{code.lower()}\b", ql):
            return code
    return None


def _find_person_in_text(tb, mm, q: str):
    m = re.search(r"\b\d{7,9}\b", q)
    if m and m.group(0) in mm.people:
        return mm.people[m.group(0)], []
    nq = " " + norm(q) + " "
    hits = [p for p in mm.people.values() if len(p.name) > 4 and f" {norm(p.name)} " in nq]
    if hits:
        hits.sort(key=lambda p: -len(p.name))
        same = [p for p in hits if norm(p.name) == norm(hits[0].name)]
        return (hits[0], []) if len(same) == 1 else (None, same)
    return None, []


def _first_date(q: str, month: str) -> date | None:
    m = re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", q)
    if m:
        return parse_date(m.group(0))
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\.?,?\s*(\d{4})?", q)
    if m and m.group(2)[:3].lower() in MONTHS:
        y = int(m.group(3)) if m.group(3) else int(month[:4])
        return parse_date(f"{m.group(1)}-{m.group(2)[:3]}-{y}")
    return None


def _date_range(q: str, month: str) -> tuple[date, date] | None:
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|till|until|-|–|and)\s*(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\.?,?\s*(\d{4})?", q)
    if m and m.group(3)[:3].lower() in MONTHS:
        y = int(m.group(4)) if m.group(4) else int(month[:4])
        a = parse_date(f"{m.group(1)}-{m.group(3)[:3]}-{y}")
        b = parse_date(f"{m.group(2)}-{m.group(3)[:3]}-{y}")
        if a and b:
            return (a, b) if a <= b else (b, a)
    m = re.search(r"from\s+(.+?)\s+(?:to|till|until)\s+(.+?)(?:$|\.|,)", q)
    if m:
        a, b = _first_date(m.group(1), month), _first_date(m.group(2), month)
        if a and b:
            return (a, b) if a <= b else (b, a)
    d = _first_date(q, month)
    return (d, d) if d else None
