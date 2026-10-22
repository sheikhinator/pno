"""Formatting shared by the P&O pages, the assistant and the board pack."""

from __future__ import annotations

from html import escape
from typing import Any

from . import privacy
from .insights import WEIGHT_LABELS, Insights, Leader, tenure_text

GOOD = "#2E7D4F"
WARN = "#B7791F"
BAD = "#B23A2E"
NEUTRAL = "#756E68"


def money(value: Any) -> str:
    if value is None:
        return "—"
    v = float(value)
    if abs(v) >= 1e9:
        return f"{v / 1e9:,.2f} bn"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.1f} M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:,.1f} K"
    return f"{v:,.0f}"


def pct(value: Any, signed: bool = False, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value):+.{digits}f}%" if signed else f"{float(value):.{digits}f}%"


def pp(value: Any) -> str:
    return "—" if value is None else f"{float(value):+.1f} pp"


def number(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    v = float(value)
    return f"{v:,.0f}" if v == int(v) else f"{v:,.{digits}f}"


def tone(value: Any, good: float, bad: float, higher_is_better: bool = True) -> str:
    """Traffic-light colour: green at/above `good`, red at/below `bad`."""
    if value is None:
        return NEUTRAL
    v = float(value)
    if not higher_is_better:
        v, good, bad = -v, -good, -bad
    if v >= good:
        return GOOD
    if v <= bad:
        return BAD
    return WARN


STATUS_COLOR = {"On track": GOOD, "Watch": WARN, "At risk": BAD, "No data": NEUTRAL}
SEVERITY_COLOR = {"High": BAD, "Medium": WARN, "Low": NEUTRAL}


def leader_name(leader: Leader) -> str:
    return privacy.name(leader.name, leader.key)


def score_text(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}"


def _change(value: Any) -> str:
    return "—" if value is None else f"{value:+.0f} vs prior year"


def _rating(value: Any) -> str:
    return "Unrated" if value is None else f"{value:g}"


def _chip(text: str, color: str) -> str:
    return (f"<span style='background:{color};color:white;border-radius:6px;padding:2px 7px;"
            f"font-weight:700;font-size:11px'>&nbsp;{escape(text)}&nbsp;</span>")


def leader_profile_html(insights: Insights, leader: Leader) -> str:
    """Rich 360° profile used on the Leaders page and by the assistant."""
    name = escape(leader_name(leader))
    rows: list[str] = []
    rank = None
    scored = [l for l in insights.leaders() if l.score is not None]
    if leader.score is not None:
        rank = 1 + sum(1 for l in scored if l.score > leader.score)
    box = insights.talent_box(leader)
    talent = insights.TALENT_NAMES.get(box) if box else None
    score_color = tone(leader.score, 70, 45)
    head = (
        f"<div style='font-size:20px;font-weight:800;color:#31261D'>{name}</div>"
        f"<div style='color:#756E68;margin-top:2px'>{escape(leader.designation or 'Leader')} · {escape(leader.store or '—')}"
        f" · leads <b>{escape(leader.section_text)}</b></div>"
    )
    score_block = (
        f"<table cellspacing='0' cellpadding='6' style='margin-top:10px'><tr>"
        f"<td style='background:#F6F1E7;border-radius:8px'><div style='font-size:11px;color:#756E68;font-weight:700'>P&amp;O INDEX</div>"
        f"<div style='font-size:26px;font-weight:800;color:{score_color}'>{score_text(leader.score)}</div>"
        f"<div style='font-size:11px;color:#756E68'>{'rank ' + str(rank) + ' of ' + str(len(scored)) if rank else 'needs 3+ measures'}</div></td>"
        f"<td style='background:#F6F1E7'><div style='font-size:11px;color:#756E68;font-weight:700'>RATING</div>"
        f"<div style='font-size:26px;font-weight:800;color:#31261D'>{'—' if leader.latest_rating is None else f'{leader.latest_rating:g}'}</div>"
        f"<div style='font-size:11px;color:#756E68'>{escape(leader.rating_label)}</div></td>"
        f"<td style='background:#F6F1E7'><div style='font-size:11px;color:#756E68;font-weight:700'>IN ROLE</div>"
        f"<div style='font-size:26px;font-weight:800;color:#31261D'>{tenure_text(leader.months_in_role)}</div>"
        f"<div style='font-size:11px;color:#756E68'>service {tenure_text(leader.months_service)}</div></td>"
        f"<td style='background:#F6F1E7'><div style='font-size:11px;color:#756E68;font-weight:700'>TALENT GRID</div>"
        f"<div style='font-size:16px;font-weight:800;color:#31261D'>{escape(talent or '—')}</div>"
        f"<div style='font-size:11px;color:#756E68'>grade {escape(leader.grade or '—')}</div></td>"
        f"</tr></table>"
    )
    k = leader.kpis
    for section, s in k.get("sales", []):
        rows.append(
            f"<tr><td>Sales · {escape(section)}</td><td><b>{money(s['actual'])}</b></td>"
            f"<td style='color:{tone(s['vs_budget_pct'], 100, 92)}'>{pct(s['vs_budget_pct'], digits=0)} of budget</td>"
            f"<td style='color:{tone(s['growth_pct'], 5, 0)}'>{pct(s['growth_pct'], True)} vs LY</td></tr>")
    for section, p in k.get("productivity", []):
        level = f" (at {p['level']} level)" if p.get("fallback") else ""
        rows.append(
            f"<tr><td>Productivity · {escape(section)}{escape(level)}</td><td><b>{number(p['actual'])}</b></td>"
            f"<td style='color:{tone(p['vs_target_pct'], 0, -10)}'>{pct(p['vs_target_pct'], True, 0)} vs target {number(p['target'])}</td>"
            f"<td style='color:{tone(p['vs_ly_pct'], 0, -10)}'>{pct(p['vs_ly_pct'], True, 0)} vs LY</td></tr>")
    for section, sh in k.get("shrink", []):
        rows.append(
            f"<tr><td>Shrinkage · {escape(section)}</td><td><b>{pct(sh['shrink_actual_pct'], digits=2)}</b></td>"
            f"<td style='color:{tone(sh['shrink_variance_pct'], 0, -1)}'>budget {pct(sh['shrink_budget_pct'], digits=2)} ({pp(sh['shrink_variance_pct'])})</td>"
            f"<td style='color:{tone(sh['days_ratio'], 1.0, 1.3, False) if sh.get('days_ratio') else NEUTRAL}'>stock days {number(sh['stock_days_actual'])} vs {number(sh['stock_days_budget'])}</td></tr>")
    for section, n in k.get("nps", []):
        rows.append(
            f"<tr><td>Customer NPS · {escape(section)}</td><td><b>{number(n['nps'], 0)}</b></td>"
            f"<td>{n['year']}</td><td style='color:{tone(n['change'], 0, -10)}'>{_change(n['change'])}</td></tr>")
    people = []
    if k.get("leavers") is not None:
        people.append(f"<b>{k['leavers']}</b> leaver(s) in their section(s) in the last 12 months")
    if k.get("da") is not None:
        people.append(f"<b>{k['da']}</b> disciplinary case(s) recorded for their section(s)")
    if leader.shifts:
        total = sum(leader.shifts.values())
        parts = [f"{leader.shifts[s]} {s.lower()}" for s in ("Morning", "Mid", "Evening", "Off", "Leave") if leader.shifts[s]]
        people.append(f"Roster this month ({total} days): " + ", ".join(parts))
    if leader.manager_name:
        people.append(f"Reports to {escape(privacy.name(leader.manager_name))}")
    ratings = sorted((r for r in leader.ratings), key=lambda r: r.get("cycle") or 0)
    if ratings:
        history = " → ".join(
            f"{r.get('cycle')}: {_rating(r.get('rating'))}" for r in ratings
        )
        people.append(f"Rating history: {history}")
    flags = [f for f in insights.bench() if f["leader"] is leader]
    flag_html = " ".join(_chip(f["reason"], SEVERITY_COLOR[f["severity"]]) for f in flags)
    components = "".join(
        f"<tr><td>{escape(WEIGHT_LABELS[c])}</td><td><b style='color:{tone(v, 70, 45)}'>{v:.0f}</b>/100</td>"
        f"<td style='color:#756E68'>weight {insights.weights.get(c, 0):g}</td></tr>"
        for c, v in leader.components.items()
    )
    html = [
        "<div style='font-family:Segoe UI, sans-serif;color:#28231F'>", head, score_block,
        f"<div style='margin-top:8px'>{flag_html}</div>" if flag_html else "",
        "<h3 style='color:#31261D;margin-bottom:4px'>Business results of their area</h3>",
        ("<table cellpadding='5' style='border-collapse:collapse'>" + "".join(rows) + "</table>") if rows
        else "<p style='color:#756E68'>No section-level business data matched this leader's section yet.</p>",
        "<h3 style='color:#31261D;margin-bottom:4px'>People</h3>",
        "<ul>" + "".join(f"<li>{p}</li>" for p in people) + "</ul>" if people else "<p style='color:#756E68'>No people data yet.</p>",
    ]
    if components:
        html += ["<h3 style='color:#31261D;margin-bottom:4px'>How the index is built</h3>",
                 f"<table cellpadding='4'>{components}</table>",
                 "<p style='color:#756E68;font-size:11px'>Each measure is scaled 0–100 and weighted (Settings). "
                 "Missing measures are left out, never counted as zero. A decision aid, not an automated decision.</p>"]
    if leader.remarks:
        html.append(f"<p style='color:#756E68'><i>HR note: {escape(leader.remarks)}</i></p>")
    html.append("</div>")
    return "".join(html)
