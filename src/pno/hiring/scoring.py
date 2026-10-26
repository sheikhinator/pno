"""Score a parsed CV against a vacancy's rubric: 0-100, a band, and the evidence behind every point.

The score only uses work history, skills, education level, leadership and (if the vacancy asks) the city. Age,
gender, marital status, religion and similar details are never read for scoring (they are hidden before parsing).
"""

from __future__ import annotations

import re
from typing import Any

from .cvparse import SKILLS

BANDS = [(75, "strong", "Strong · interview"), (55, "possible", "Possible · phone screen"), (35, "weak", "Weak · hold"),
         (0, "no", "Not suitable")]
LEVEL_NAMES = {0: "no level found", 1: "associate", 2: "team leader / supervisor", 3: "section manager", 4: "department head",
               5: "deputy / assistant store manager", 6: "store manager"}
EDU_NAMES = {0: "not stated", 2: "Matric", 3: "Intermediate", 4: "Bachelor's", 5: "Master's"}


def _quote(text: str, words: list[str], limit: int = 140) -> str:
    low = text.lower()
    for w in words:
        i = low.find(w)
        if i >= 0:
            s = max(0, text.rfind("\n", 0, i) + 1)
            e = text.find("\n", i)
            e = len(text) if e < 0 else e
            q = re.sub(r"\s+", " ", text[s:e]).strip()
            return (q[:limit] + "…") if len(q) > limit else q
    return ""


def band_of(score: float, knocked: bool) -> tuple[str, str]:
    if knocked:
        return "no", "Not suitable"
    for floor, key, label in BANDS:
        if score >= floor:
            return key, label
    return "no", "Not suitable"


def score(cv: dict[str, Any], text: str, rubric: dict[str, Any]) -> dict[str, Any]:
    parts = []
    strengths, gaps = [], []
    total_w = sum(max(0.0, float(c.get("weight") or 0)) for c in rubric.get("criteria", [])) or 1.0
    for c in rubric.get("criteria", []):
        w = max(0.0, float(c.get("weight") or 0))
        if not w:
            continue
        t, target = c["type"], c.get("target") or 0
        val, why, ev = 0.0, "", ""
        if t in ("years_total", "years_retail"):
            have = cv.get(t)
            if have is None:
                why = "no dated work history found"
            else:
                val = min(1.0, have / target) if target else 1.0
                why = f"{have:g} years (asks {target:g})"
                jobs = [j for j in cv.get("jobs", []) if t == "years_total" or j.get("retail")]
                ev = "; ".join(f"{j['start']}→{'now' if j['current'] else j['end']}: {j['title'] or 'role'}" for j in jobs[:3])
        elif t == "level":
            have = cv.get("top_level") or 0
            val = 1.0 if have >= target else 0.6 if have == target - 1 else 0.25 * have / max(target, 1)
            why = f"highest role: {LEVEL_NAMES.get(have, have)} (asks {LEVEL_NAMES.get(target, target)})"
            top = max(cv.get("jobs", []), key=lambda j: j["level"], default=None)
            ev = (top or {}).get("context", "")[:140]
        elif t == "skills":
            items = c.get("items") or []
            found = [s for s in items if s in (cv.get("skills") or {})]
            val = len(found) / len(items) if items else 1.0
            missing = [s for s in items if s not in found]
            why = f"{len(found)} of {len(items)}: " + (", ".join(found) if found else "none found")
            ev = " · ".join(q for q in (_quote(text, SKILLS.get(s, [s.lower()])) for s in found[:3]) if q)
            gaps.extend(f"No sign of {m.lower()}" for m in missing[:3])
        elif t == "education":
            have = cv.get("education_rank") or 0
            val = 1.0 if have >= target else 0.5 if have == target - 1 else 0.0
            why = f"{EDU_NAMES.get(have, have)} (asks {EDU_NAMES.get(target, target)})"
        elif t == "team":
            size = cv.get("team_size")
            if size:
                val = min(1.0, size / target) if target else 1.0
                why = f"led a team of {size} (asks {target})"
                ev = _quote(text, ["team of", "managed", "supervised", "led"])
            else:
                val = 0.5 if (cv.get("top_level") or 0) >= 2 else 0.0
                why = "team size not stated" + (" (has held a lead role)" if val else "")
        elif t == "city":
            items = [x.lower() for x in (c.get("items") or [])]
            city = (cv.get("city") or "").lower()
            val = 1.0 if not items or city in items else (0.4 if not city else 0.0)
            why = f"lives in {cv.get('city') or 'city not stated'}"
        else:
            continue
        parts.append({"key": c["key"], "label": c["label"], "weight": w, "value": round(val, 2), "points": round(100 * w / total_w * val, 1),
                      "max": round(100 * w / total_w, 1), "why": why, "evidence": ev})
        if val >= 0.99:
            strengths.append(f"{c['label']}: {why}")
        elif val < 0.5 and t != "skills":
            gaps.append(f"{c['label']}: {why}")
    total = round(sum(p["points"] for p in parts), 1)
    knock = knockouts(cv, rubric.get("knockouts") or {})
    key, label = band_of(total, bool(knock))
    if cv.get("retailers"):
        strengths.append("Worked at " + ", ".join(cv["retailers"][:4]))
    return {"score": total, "band": key, "band_label": label, "parts": parts, "strengths": strengths[:6], "gaps": gaps[:6],
            "flags": list(cv.get("flags") or []), "knockouts": knock}


def knockouts(cv: dict[str, Any], k: dict[str, Any]) -> list[str]:
    out = []
    if k.get("min_years") and (cv.get("years_total") or 0) < float(k["min_years"]):
        out.append(f"Less than {k['min_years']} years of experience")
    if k.get("cities"):
        allowed = [c.lower() for c in k["cities"]]
        if cv.get("city") and cv["city"].lower() not in allowed:
            out.append(f"Based in {cv['city']}, role needs {', '.join(k['cities'])}")
    for s in k.get("must_skills") or []:
        if s not in (cv.get("skills") or {}):
            out.append(f"No {s.lower()} experience (required)")
    return out
