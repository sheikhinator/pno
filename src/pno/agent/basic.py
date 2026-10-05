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


def answer(tb: Toolbox, question: str) -> str:
    q = question.strip()
    ql = q.lower()
    mm = tb._mm()
    if not mm.people and not getattr(mm, "sales", {}):
        return "There is no data yet. Import the roster, attendance, productivity and BO sales reports first (Import screen)."
    store = _find_store(tb, mm, ql)
    city = _find_city(ql)
    person, _ = _find_person_in_text(tb, mm, q)

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
    return HELP


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
