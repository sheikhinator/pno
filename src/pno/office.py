"""3.0: the director's office: automatic backups, the HR calendar, the weekly brief, the store-visit checklist, the
glossary behind 'explain this number', and column names P&O teaches Smart Import.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .paths import data_dir

KEEP_BACKUPS = 14


# ------------------------------------------------------------------------------------------- backups
def backup_dir() -> Path:
    d = data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def auto_backup(db, force: bool = False) -> dict | None:
    """One copy a day, kept for two weeks. Runs at start-up; never blocks the app."""
    if getattr(db, "path", None) is None or db.get_setting("auto_backup", True) is False:
        return None
    today = date.today().isoformat()
    if not force and db.get_setting("auto_backup_last", "") == today:
        return None
    dest = backup_dir() / f"P&O auto {datetime.now():%Y-%m-%d %H%M}.sqlite3"
    db.backup(dest)
    db.set_setting("auto_backup_last", today)
    files = sorted(backup_dir().glob("P&O auto *.sqlite3"))
    for old in files[:-KEEP_BACKUPS]:
        try:
            old.unlink()
        except OSError:
            pass
    return {"path": str(dest)}


def backups() -> list[dict]:
    out = []
    for f in sorted(backup_dir().glob("*.sqlite3"), reverse=True):
        st = f.stat()
        out.append({"name": f.name, "path": str(f), "size_kb": round(st.st_size / 1024), "at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")})
    return out


# ------------------------------------------------------------------------------------------- synonyms
def synonyms(db) -> dict:
    from .smart import schema
    extra = db.get_setting("synonyms", {}) or {}
    return {"fields": [{"field": k, "label": v["label"], "builtin": schema._BASE_SYN[k][:12], "extra": extra.get(k, [])} for k, v in schema.FIELDS.items()]}


def save_synonyms(db, field: str, words: list[str]) -> dict:
    from .smart import schema
    if field not in schema.FIELDS:
        raise ValueError("Unknown field.")
    extra = db.get_setting("synonyms", {}) or {}
    clean = sorted({w.strip().casefold() for w in words if w and w.strip()})[:40]
    if clean:
        extra[field] = clean
    else:
        extra.pop(field, None)
    db.set_setting("synonyms", extra)
    schema.set_user_synonyms(extra)
    return synonyms(db)


def load_synonyms(db) -> None:
    from .smart import schema
    schema.set_user_synonyms(db.get_setting("synonyms", {}) or {})


# ------------------------------------------------------------------------------------------- HR calendar
# ------------------------------------------------------------------------------------------- weekly brief
# ------------------------------------------------------------------------------------------- store visit
CHECKLIST = {
    "People & rosters": ["Roster posted and matches the people on the floor", "Breaks staggered, no section left uncovered",
                         "New joiners have a buddy and know their trainer", "Absent people today were followed up"],
    "Leadership": ["Morning briefing held and targets shared", "Section managers know their sales, waste and productivity",
                   "Open actions from the last visit are closed"],
    "Customer & floor": ["Shelves full, price labels right, no gaps in top lines", "Fresh counters staffed at peak hours",
                         "Checkouts open match the queue"],
    "Compliance & wellbeing": ["Uniform and grooming standard", "Attendance punches match the roster (no manual fixes needed)",
                               "Notice board up to date (policies, holidays, recognition)", "Staff room clean; water and rest area OK"],
    "Talk to people": ["Spoke to at least 3 staff members", "Any concern raised is written down with an owner"],
}


# ------------------------------------------------------------------------------------------- explain this number
GLOSSARY: dict[str, dict[str, str]] = {
    "leader index": {"what": "A 0-10 score for each leader, combining sales vs budget, productivity vs target, shrinkage, stock days, "
                     "performance rating, team retention and customer NPS, each weighted (Leaders & talent → Weights).",
                     "source": "Sales, productivity, shrinkage, rating, turnover and NPS sheets", "good": "7+ strong · 5-7 solid · below 5 needs support"},
    "nps": {"what": "Net Promoter Score: % of customers who would recommend us (9-10) minus % who would not (0-6). Ranges -100 to +100.",
            "source": "Customer NPS sheet, by city and category. The hypermarket survey goes to that city's hypermarkets only; supermarkets and Myli need their own survey lines (or a line per store)", "good": "50+ excellent · 30-50 good · below 0 a warning"},
    "sales vs budget": {"what": "Actual net sales as a % of budget for the period selected (100% = on plan).", "source": "Store sales report (BO 200-10-05)",
                        "good": "100% or more of budget is on plan"},
    "productivity": {"what": "Sales per paid hour against the target set for the store or section.", "source": "Section productivity report",
                     "good": "at or above target"},
    "shrinkage": {"what": "Stock lost (damage, expiry, theft, errors) as % of sales, against its budget. Variance = actual − budget.",
                  "source": "Shrinkage & stock days sheet", "good": "variance 0 or positive"},
    "stock days": {"what": "How many days of sales the stock on hand would cover, against budget.", "source": "Shrinkage & stock days sheet",
                   "good": "at or below budget"},
    "turnover": {"what": "Leavers in the last 12 months ÷ current headcount × 100.", "source": "Turnover sheet and Basic Sheet",
                 "good": "lower is better; watch voluntary leavers"},
    "absence": {"what": "Absent days ÷ scheduled days (worked + absent), after leave, holidays and the weekly off are taken out.",
                "source": "Biometric attendance and leave register", "good": "below 3% good · above 5% a concern"},
    "bradford": {"what": "Bradford factor = (number of absence spells)² × total days absent. Many short absences score higher than one long one.",
                 "source": "Biometric attendance", "good": "under 50 normal · 125+ talk · 250+ formal review"},
    "presence": {"what": "Days worked ÷ days due (worked + unexplained absence).", "source": "Biometric attendance", "good": "95%+"},
    "rating": {"what": "The latest performance rating, 1-5, from the performance cycle.", "source": "Performance rating sheet",
               "good": "4-5 strong · 3 solid · 1-2 underperforming"},
    "enps": {"what": "Employee Net Promoter Score: % who would recommend us as an employer (9-10) minus % who would not (0-6).",
             "source": "Engagement surveys and exit interviews", "good": "above 0 positive · 20+ strong"},
    "data health": {"what": "How complete and fresh the imported data is for the month: each expected report present, dated and matched.",
                    "source": "Import history", "good": "85+ reliable"},
}


def explain(term: str) -> dict | None:
    t = (term or "").casefold()
    if "pattern" in t or "bradford" in t:
        return {"term": "bradford", **GLOSSARY["bradford"]}
    for k, v in sorted(GLOSSARY.items(), key=lambda kv: -len(kv[0])):
        if k in t or t in k:
            return {"term": k, **v}
    aliases = {"index": "leader index", "score": "leader index", "leavers": "turnover", "retention": "turnover", "attendance": "presence",
               "sales": "sales vs budget", "shrink": "shrinkage", "pattern absence": "bradford", "women": None}
    for a, k in aliases.items():
        if a in t and k:
            return {"term": k, **GLOSSARY[k]}
    return None

