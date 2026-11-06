"""The built-in assistant: answers the common questions from the master sheet with P&O's own scoring, no AI model needed.

Used when no AI service is set up or reachable, and as the fallback when one is busy. Every number comes from agent/facts.py,
the same place the AI tools and the Review screen read from.
"""

from __future__ import annotations

import re

from ..review import fmt as review_fmt
from .facts import KEYS, role_in
from .tools import Toolbox

HELP = ("I answer from the master sheet, with the same scores as the Review screen. For example:\n"
        "- **Tell me about Arslan Arshad** (a person's full sheet)\n- **Bottom 5 department heads on sales**\n"
        "- **How is Fortress doing?**\n- **Compare Fortress and Emporium**\n- **Who has NPS below 40?**\n"
        "- **Which store managers are High performers?**\n- **What is missing in the data?**\n- **How is the score worked out?**")
_DOT = {"good": "🟢", "warn": "🟡", "bad": "🔴", "neutral": "⚪", "none": "⚪", None: "⚪"}
_DEPT_WORDS = [(r"\b(cg|consumer goods?|fmcg|grocery)\b", "Consumer Goods"), (r"\b(ff|fresh food|fresh)\b", "Fresh Food"),
               (r"\b(lhh|light household)\b", "Light Household"), (r"\b(hhh|heavy household)\b", "Heavy Household"),
               (r"\b(textile|txt)\b", "Textile"), (r"\bnon[ -]?food\b", "Non Food")]
_CRIT_WORDS = [("sales", r"sales|budget"), ("productivity", r"productiv"), ("shrink", r"shrink"), ("stock_days", r"stock"),
               ("leavers", r"leaver|turnover|attrition"), ("da", r"\bda\b|disciplin"), ("nps", r"\bnps\b|customer"), ("rating", r"rating")]
_RANK_RX = re.compile(r"\b(top|bottom|best|worst|highest|lowest|weakest|strongest|most|least|rank|ranking|below|above|under|over|less than|more than)\b")
_HEALTH_RX = re.compile(r"missing|not filled|incomplete|complete|data health|gaps? in (the )?data|what('?s| is) left|unrated|no score", re.I)
_HOW_RX = re.compile(r"how (is|are) (the )?scor|criteria|weight|benchmark|how .*(calculated|worked out|measured)", re.I)
_CMP_RX = re.compile(r"\b(compare|comparison|vs|versus|against)\b")
_OVER_RX = re.compile(r"overview|summary|country|overall|how are we|brief|big picture|everyone|all stores|league", re.I)


def _fmtn(v, d=1):
    return "—" if v is None else f"{v:.{d}f}"


def _person_answer(tb: Toolbox, p: dict) -> str:
    d = tb.facts.person(p)
    sc = f"**{d['score_out_of_10']}/10 · {d['category']}**" + (f" · {d['rank_among_same_level']} {p['role'].lower()}s" if d["rank_among_same_level"] else "") \
        if d["score_out_of_10"] is not None else f"**no score yet**: {d['score_note']}"
    out = [f"**{d['name']}** · {d['designation']} · {d['store']} ({d['format']}){(' · ' + d['department']) if d['department'] and d['level'] != 'Store Manager' else ''}",
           "", f"Score {sc} for {d['period']}.", "",
           f"Employee {d['employee_no']} · grade {d['grade'] or '—'} · with the company {d['with_company']} · in this role {d['time_in_role']}"
           + (f" · reports to {d['reports_to']}" if d["reports_to"] else ""), "",
           "| Criterion | Result | Points | Green line | Peers (median) | |", "|---|---|---|---|---|---|"]
    out += [f"| {r['criterion']} | **{r['result']}** | {_fmtn(r['points_out_of_10'])} | {r['green_line']} | {r['peer_median']} | {_DOT[r['status']]} |"
            for r in d["results"]]
    if d["strong_on"]:
        out.append(f"\n**Strong on:** {', '.join(d['strong_on'])}")
    if d["below_benchmark_on"]:
        out.append(f"**Below benchmark on:** {', '.join(d['below_benchmark_on'])}")
    if d["not_filled_yet"]:
        out.append(f"**Not filled yet:** {', '.join(d['not_filled_yet'])}")
    if d["ratings_by_year"]:
        out.append("**Ratings:** " + " · ".join(f"{y}: {v}" for y, v in d["ratings_by_year"].items()) + (f" ({d['rating_trend']})" if d["rating_trend"] else ""))
    if d["own_criteria"]:
        out.append("_Scored on criteria saved for this person (custom)._")
    if d["results"]:
        tb.blocks.append({"type": "chart", "kind": "hbar", "title": f"{d['name']} · points out of 10",
                          "labels": [r["criterion"] for r in d["results"] if r["points_out_of_10"] is not None],
                          "series": [{"name": "Points", "values": [r["points_out_of_10"] for r in d["results"] if r["points_out_of_10"] is not None]}]})
    return "\n".join(out)


def _people_answer(tb: Toolbox, q: str) -> str | None:
    ql = q.lower()
    f = tb.facts
    role = role_in(ql)
    dept = next((d for rx, d in _DEPT_WORDS if re.search(rx, ql)), "")
    sts = f.stores_in_text(q)
    fmt = "Hypermarket" if re.search(r"\bhyper", ql) else "Supermarket" if re.search(r"\bsuper(market)?s?\b", ql) else ""
    cat = next((c for c in ("High", "Good", "Low") if re.search(rf"\b{c.lower()}( performers?)?\b", ql) and "performer" in ql), "")
    crit = next((k for k, rx in _CRIT_WORDS if re.search(rx, ql)), "")
    asc = bool(re.search(r"bottom|worst|lowest|weakest|below|under|less than", ql))
    if crit in ("leavers", "da", "shrink", "stock_days") and re.search(r"most|highest|worst|above|over|more than", ql):
        asc = False
        better_low = True
    else:
        better_low = False
    m = re.search(r"\b(?:top|bottom|best|worst|first|last)\s*(\d{1,2})\b|\b(\d{1,2})\s+(?:best|worst|top|bottom)", ql)
    n = int(next(g for g in m.groups() if g)) if m else 10
    thr = re.search(r"(below|under|less than|above|over|more than)\s*(-?\d+(?:\.\d+)?)", ql)
    bud = re.search(r"\b(below|under|behind|missing|short of|above|over|ahead of|beating)\s+(the\s+)?(sales\s+)?budget", ql)
    if bud and not thr:
        crit = "sales"
        thr = re.match(r"(\w+) (\S+)", ("below 0" if bud.group(1) in ("below", "under", "behind", "missing", "short of") else "above -0.0001"))
    if not (role or dept or sts or fmt or cat or crit or _RANK_RX.search(ql)):
        return None
    r = f.people(store=sts[0] if len(sts) == 1 else "", dept=dept, role=role, fmt=fmt, category=cat, sort=crit or "score",
                 ascending=asc if not better_low else True, limit=100)
    rows = r["people"]
    if thr and crit:
        x = float(thr.group(2))
        below = thr.group(1) in ("below", "under", "less than")
        if bud:
            x = 0.0
        rows = [p for p in rows if p["_values"][crit] is not None and (p["_values"][crit] < x if below else p["_values"][crit] > x)]
    elif _RANK_RX.search(ql) or m:
        rows = rows[:n]
    if not rows:
        return "Nobody matches that in the master sheet for " + f.period_label + "."
    label = f.criteria[crit]["label"] if crit else "Score"
    who = {"store": "store managers", "deputy": "deputy managers", "dept": "department heads and deputy managers", "section": "section managers", "tl": "team leaders"}.get(role, "leaders")
    where = f" in {sts[0]}" if len(sts) == 1 else f" in {dept}" if dept else f" ({fmt.lower()}s)" if fmt else ""
    out = [f"**{len(rows)} {who}{where}**" + (f" · sorted by {label.lower()}" if crit else "") + f" · {f.period_label}", "",
           "| # | Name | Role | Store | Score | Category | " + (label + " |" if crit else "Below benchmark on |"), "|---|---|---|---|---|---|---|"]
    for i, p in enumerate(rows[:40], 1):
        extra = review_fmt(crit, p["_values"][crit]) if crit else ", ".join(f.criteria[k]["label"] for k in KEYS if p["_status"].get(k) == "bad") or "—"
        out.append(f"| {i} | {p['name']} | {p['designation']} | {p['store']} | {_fmtn(p['score'])} | {p['category']} | {extra} |")
    vals = [(p["name"], p["_values"][crit] if crit else p["score"]) for p in rows[:15]]
    vals = [v for v in vals if v[1] is not None]
    if len(vals) >= 3:
        tb.blocks.append({"type": "chart", "kind": "hbar", "title": label, "labels": [v[0] for v in vals], "series": [{"name": label, "values": [v[1] for v in vals]}]})
    return "\n".join(out)


def _store_answer(tb: Toolbox, st: str) -> str:
    d = tb.facts.store_view(st)
    sm = d["store_manager"]
    out = [f"**{d['store']}** ({d['format']}, {d['city']}) · {d['period']}" + (f" · store manager **{sm['name']}** {_fmtn(sm['score'])}/10 ({sm['category']})" if sm else ""), "",
           "| Criterion | Result |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in d["store_results"].items()]
    if d["strong"]:
        out += ["", "**What's strong**"] + [f"- {x}" for x in d["strong"]]
    if d["weak"]:
        out += ["", "**What's weak**"] + [f"- {x}" for x in d["weak"]]
    if d["focus"]:
        out += ["", "**Focus**"] + [f"{i}. {x}" for i, x in enumerate(d["focus"], 1)]
    out += ["", "| Leader | Role | Score | Below benchmark on |", "|---|---|---|---|"]
    out += [f"| {p['name']} | {p['designation']}{(' · ' + p['department']) if p['department'] and p['department'] != 'Management' else ''} | {_fmtn(p['score'])} ({p['category']}) | {', '.join(p['below_benchmark_on']) or '—'} |"
            for p in d["leaders"]]
    return "\n".join(out)


def _compare_answer(tb: Toolbox, sts: list[str]) -> str:
    views = [tb.facts.store_view(s) for s in sts[:4]]
    keys = list(dict.fromkeys(k for v in views for k in v["store_results"]))
    out = [f"**{' vs '.join(v['store'] for v in views)}** · {tb.facts.period_label}", "", "| | " + " | ".join(v["store"] for v in views) + " |",
           "|---|" + "---|" * len(views)]
    out.append("| Store manager | " + " | ".join(f"{v['store_manager']['name']} ({_fmtn(v['store_manager']['score'])})" if v["store_manager"] else "—" for v in views) + " |")
    out += [f"| {k} | " + " | ".join(v["store_results"].get(k, "—") for v in views) + " |" for k in keys]
    out.append("| Average leader score | " + " | ".join(_fmtn(v["average_leader_score"]) for v in views) + " |")
    return "\n".join(out)


def _health_answer(tb: Toolbox) -> str:
    h = tb.facts.health()
    out = [f"**{h['filled_pct']}% of results are filled** for {h['period']} ({h['people']} leaders).", "", "| Criterion | Filled |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in h["by_criterion"].items()]
    if h["who_is_missing_what"]:
        out += ["", "| Who | Store | Not filled yet |", "|---|---|---|"]
        out += [f"| {g['name']} | {g['store']} | {', '.join(g['missing'])} |" for g in h["who_is_missing_what"][:25]]
    out.append("\nUpload the completed sheet for the same period in **Data → Master sheet**; scores update straight away.")
    return "\n".join(out)


def _how_answer(tb: Toolbox) -> str:
    f = tb.facts
    out = ["**How P&O scores a leader:** each result in the master sheet earns 0–10 points against its benchmark (amber line = 5, green line = 7, "
           "one step past green = 10). The score out of 10 is the weighted average of the points; blanks are left out and at least 3 results "
           "are needed. **High** 7+, **Good** 5–6.9, **Low** below 5.", "", "| Criterion | Weight | Green | Amber | Better |", "|---|---|---|---|---|"]
    from .. import review
    out += [f"| {c['label']} | {c['weight']:g}% | {review.fmt(k, c['green'])} | {review.fmt(k, c['amber'])} | {c['better']} |"
            for k, c in f.criteria.items() if c["on"]]
    out.append("\nChange them in **Settings → Criteria**; every score moves at once.")
    return "\n".join(out)


def _overview_answer(tb: Toolbox) -> str:
    o = tb.facts.overview()
    out = [f"**{o['leaders']} leaders in {o['stores']} stores · average score {_fmtn(o['average_score'])}/10** ({o['period']}): "
           f"{o['high']} High, {o['good']} Good, {o['low']} Low, {o['not_scored']} not scored.", "", "| Country result | |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in o["country_results"].items()]
    out += ["", "**What's strong**"] + [f"- {x}" for x in o["strong"]] + ["", "**What's weak**"] + [f"- {x}" for x in o["weak"]]
    out += ["", "**Focus**"] + [f"{i}. {x}" for i, x in enumerate(o["focus"], 1)]
    lg = tb.facts.league()["stores"]
    tb.blocks.append({"type": "chart", "kind": "hbar", "title": "Store manager score by store", "labels": [s["store"] for s in lg if s["store_manager_score"] is not None],
                      "series": [{"name": "Score", "values": [s["store_manager_score"] for s in lg if s["store_manager_score"] is not None]}]})
    return "\n".join(out)


def _review_answer(tb: Toolbox, q: str) -> str | None:
    from .. import review
    ql = q.lower()
    dept = next((d for rx, d in _DEPT_WORDS if re.search(rx, ql)), None)
    if not dept:
        return None
    sts = tb.facts.stores_in_text(q)
    r = tb.svc.api.api_review(store=sts[0] if sts else None, dept=dept)
    if r.get("empty"):
        return None
    C = r["criteria"]
    out = [f"**{r['label']}** · {tb.facts.period_label}", "", "| Criterion | Result | |", "|---|---|---|"]
    out += [f"| {C[t['key']]['label']} | {review.fmt(t['key'], t['value'])} | {_DOT[t['status']]} |" for t in r["tiles"] if t["value"] is not None]
    out += ["", "**What's strong**"] + [f"- {x}" for x in r["notes"]["strong"]] + ["", "**What's weak**"] + [f"- {x}" for x in r["notes"]["weak"]]
    out += ["", "**Focus**"] + [f"{i}. {x}" for i, x in enumerate(r["notes"]["focus"], 1)]
    return "\n".join(out)


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


_INT_RX = re.compile(r"(who|which|anyone)\b.*\b(replace|ready for|could (be|become|take|fill)|can (be|become|take|fill)|internal candidates?|step up|promot)", re.I)
_ROLE_WORDS = [("store manager", "store_manager"), ("department head", "department_head"), ("dept head", "department_head"),
               ("section manager", "section_manager"), ("team leader", "team_leader")]


def _internal_answer(tb: Toolbox, q: str) -> str | None:
    ql = q.lower()
    role = next((k for w, k in _ROLE_WORDS if w in ql), None)
    if not role:
        return None
    sts = tb.facts.stores_in_text(q) if not tb.facts.empty else []
    store = sts[0] if sts else ""
    dept = next((d for rx, d in _DEPT_WORDS if re.search(rx, ql)), "")
    r = tb.t_internal_candidates(role=role, store=store, department=dept)
    v = r["verdict"]
    lines = [f"**{v['title']}**", "", v["text"], ""] + [f"> {n}" for n in r["notes"]]
    if r["candidates"]:
        lines += ["", "| Candidate | Now | Move | Fit | If they move |", "|---|---|---|---|---|"]
        lines += [f"| {c['name']} | {c['designation']} · {c['store']} | {c['move']} | {c['recommend']:.0f} | {c['backfill']['summary']} ({c['backfill']['risk']} risk) |"
                  for c in r["candidates"]]
    return "\n".join(lines + ["", "Open **Hiring**, create the vacancy and use **Internal talent first** for the full profiles and chains of moves."])




def answer(tb: Toolbox, question: str) -> str:
    q = question.strip()
    ql = q.lower()
    if _HIRE_RX.search(ql) and not _INT_RX.search(ql):
        return _hire_answer(tb, q)
    if _LEARN_RX.search(ql) and not re.search(r"\b(cv|candidate|vacanc)", ql):
        return _learn_answer(tb, q)
    f = tb.facts
    if f.empty:
        return "No master sheet has been uploaded yet. Open **Data → Master sheet**, pick the period and add the file."
    if _INT_RX.search(ql):
        a = _internal_answer(tb, q)
        if a:
            return a
    if _HOW_RX.search(ql):
        return _how_answer(tb)
    p, many = f.find_in_text(q)
    if p and not re.search(r"\b(top|bottom|rank|ranking|list)\b", ql):
        if _HEALTH_RX.search(ql) and p["missing"]:
            return f"**{p['name']}** is missing: {', '.join(p['missing'])}." + ("" if p["score"] is not None else f" With only {p['measured']} of 8 results filled there is no score yet (3 are needed).")
        return _person_answer(tb, p)
    ask = re.search(r"(?:about|who is|tell me about|profile of|sheet (?:for|of)|how is|how's|score of)\s+([a-z][a-z .'-]{1,40}?)(?:\?|$|\s+doing|\s+performing|'s)", ql)
    if not p and not many and ask and not f.stores_in_text(ask.group(1)) and not role_in(ask.group(1)):
        p, many = f.find(ask.group(1).strip())
        if p:
            return _person_answer(tb, p)
    if many and len(many) <= 10 and not role_in(ql) and re.search(r"\b(about|who is|tell me|how is|profile|sheet|doing|performing|score of)\b", ql):
        return "Several people match: " + "; ".join(f"**{x['name']}** ({x['designation']}, {x['store']})" for x in many) + ". Which one?"
    if _HEALTH_RX.search(ql):
        return _health_answer(tb)
    sts = f.stores_in_text(q)
    if len(sts) >= 2 and (_CMP_RX.search(ql) or " and " in ql):
        return _compare_answer(tb, sts)
    ppl = _people_answer(tb, q) if (role_in(ql) or _RANK_RX.search(ql) or re.search(r"\b(who|which|list|show)\b", ql)) else None
    if ppl and not (len(sts) == 1 and not role_in(ql) and not _RANK_RX.search(ql)):
        return ppl
    if len(sts) == 1:
        return _store_answer(tb, sts[0])
    rv = _review_answer(tb, q)
    if rv:
        return rv
    if ppl:
        return ppl
    if _OVER_RX.search(ql) or re.search(r"\bstores?\b", ql):
        return _overview_answer(tb)
    return HELP
