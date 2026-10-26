"""What P&O knows how to use: the fields (with the many ways HR systems name them) and the report types built from them.

Each field has header synonyms and a value test. A column is matched to a field by both: what it is called and what
is in it, so 'ID', 'Emp Code', 'Staff #' or an unnamed column full of 8-digit numbers all become the employee number.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache

from .profile import Column

F = dict  # field definition


def _hdr(s: str) -> str:
    s = s.casefold().replace("&", " and ").replace("#", " no ")
    s = re.sub(r"[^a-z0-9%]+", " ", s)
    return " ".join(s.split())


FIELDS: dict[str, F] = {
    "employee_id": F(label="Employee number", syn=["employee number", "employee no", "emp no", "emp number", "emp code", "employee code",
                     "employee id", "emp id", "staff id", "staff no", "personnel number", "person number", "subject employee id",
                     "ecode", "e code", "badge no", "id", "code", "number", "emp"],
                     fit=lambda c: c.f("id"), avoid=["manager", "supervisor", "reports to", "cnic", "mobile", "phone"]),
    "manager_id": F(label="Manager's employee number", syn=["manager employee number", "manager id", "manager code", "manager no",
                    "reporting manager id", "line manager id", "supervisor id", "reports to id"], fit=lambda c: c.f("id")),
    "employee_name": F(label="Employee name", syn=["employee name", "name", "full name", "emp name", "subject full name", "staff name",
                       "associate name", "person name", "employee", "employee full name"],
                       fit=lambda c: c.f("name"), avoid=["manager", "supervisor", "father", "store", "business", "section", "department"]),
    "manager_name": F(label="Reporting manager", syn=["reporting manager", "manager", "manager name", "line manager", "reports to",
                      "supervisor", "manager full name", "reporting to", "direct manager"],
                      fit=lambda c: c.f("name"), avoid=["id", "number", "code", "no"]),
    "store": F(label="Store / business unit", syn=["business unit", "store", "store name", "location", "branch", "bu", "outlet", "site",
               "subject division entity", "unit", "store code", "work location", "business unit name"],
               fit=lambda c: c.f("store")),
    "department": F(label="Department", syn=["department", "dept", "department name", "subject department", "division", "family"],
                    fit=lambda c: 0.6 * c.f("section") + (0.3 if 1 < c.distinct <= 25 else 0)),
    "section": F(label="Section", syn=["section", "sect", "section name", "sub department", "sub dept", "category", "area", "team"],
                 fit=lambda c: c.f("section")),
    "designation": F(label="Designation / job title", syn=["designation", "job title", "position", "title", "role", "position title",
                     "subject position title", "job", "job name", "position name"],
                     fit=lambda c: c.f("job"), avoid=["since", "date", "remark"]),
    "grade": F(label="Grade", syn=["grade", "pay grade", "job grade", "band", "level", "subject pay grade", "scale"],
               fit=lambda c: 0.8 if c.n and c.distinct <= 30 and not c.f("name") and not c.f("date") and not c.f("store") else 0.0),
    "gender": F(label="Gender", syn=["gender", "sex"], fit=lambda c: c.f("gender")),
    "joining_date": F(label="Joining date", syn=["joining date", "date of joining", "doj", "hire date", "date joined", "joined",
                      "employment date", "join date", "start date", "service start"], fit=lambda c: c.f("date")),
    "role_since": F(label="In current role since", syn=["on this role", "since when on this role", "in this role since", "role since",
                    "in role since", "date in role", "position start date", "promotion date", "since", "role start date",
                    "current role date"], fit=lambda c: c.f("date")),
    "remarks": F(label="Remarks", syn=["remarks", "remark", "comments", "comment", "notes", "note", "observation"],
                 fit=lambda c: 0.5 + 0.5 * c.f("long_text") if c.n else 0),
    "rating": F(label="Performance rating", syn=["overall performance rating", "performance rating", "rating", "final rating",
                "overall rating", "appraisal rating", "appraisal score", "score", "pms rating", "annual rating"],
                fit=lambda c: c.f("rating") * (1 if c.f("num") > 0.8 else 0.5), avoid=["description", "label", "section", "unadjusted"]),
    "rating_label": F(label="Rating description", syn=["overall performance rating description", "rating description", "rating label",
                      "performance level", "rating band", "rating text", "description"],
                      fit=lambda c: 0.7 if c.n and c.distinct <= 8 and c.f("num") < 0.2 else 0.0),
    "cycle": F(label="Appraisal year / form", syn=["year", "cycle", "appraisal year", "review year", "form template name", "form",
               "review period", "appraisal cycle", "performance year"],
               fit=lambda c: max(c.f("year"), 0.8 if any(re.search(r"20\d\d", e) for e in c.examples) else 0.0)),
    "exit_date": F(label="Leaving date", syn=["requested date", "exit date", "leaving date", "last working day", "lwd", "separation date",
                   "termination date", "resignation date", "date of leaving", "relieving date", "date left", "left on",
                   "end of service date", "effective date"], fit=lambda c: c.f("date")),
    "exit_type": F(label="Exit type", syn=["end of service type", "exit type", "separation type", "leaving type", "termination type",
                   "type of exit", "type of separation", "voluntary involuntary", "exit category"],
                   fit=lambda c: 0.9 if any(re.search(r"resign|terminat|abscond|retire|voluntar|contract", e, re.I) for e in c.examples) else 0.0),
    "reason": F(label="Reason for leaving", syn=["reason", "exit reason", "leaving reason", "reason for leaving", "separation reason",
                "termination reason", "resignation reason"], fit=lambda c: 0.6 if c.n and c.f("num") < 0.2 and not c.f("date") else 0.0),
    "salary_period": F(label="Salary period", syn=["salary period", "payroll period", "pay period", "payroll month"],
                       fit=lambda c: c.f("num") * 0.5),
    "leave_type": F(label="Leave type", syn=["leave type", "absence type", "type of leave", "leave", "leave category", "type"],
                    fit=lambda c: 0.9 if any(re.search(r"annual|sick|casual|maternity|leave|\bal\b|\bsl\b|\bcl\b", e, re.I) for e in c.examples) else 0.0),
    "leave_from": F(label="Leave from", syn=["from", "from date", "leave from", "date from", "start date", "start", "leave start",
                    "begin date", "first day"], fit=lambda c: c.f("date")),
    "leave_to": F(label="Leave to", syn=["to", "to date", "leave to", "date to", "end date", "end", "until", "leave end", "last day"],
                  fit=lambda c: c.f("date")),
    "status": F(label="Status", syn=["status", "approval status", "state", "leave status", "attendance status", "user status"],
                fit=lambda c: 0.6 if c.n and c.distinct <= 10 and c.f("num") < 0.2 else 0.0),
    "date": F(label="Date", syn=["date", "attendance date", "day", "work date", "punch date", "shift date", "case date", "incident date"],
              fit=lambda c: c.f("date")),
    "time_in": F(label="Time in", syn=["in", "time in", "in time", "check in", "clock in", "punch in", "first in", "first punch"],
                 fit=lambda c: c.f("time")),
    "time_out": F(label="Time out", syn=["out", "time out", "out time", "check out", "clock out", "punch out", "last out", "last punch"],
                  fit=lambda c: c.f("time")),
    "hours": F(label="Hours worked", syn=["working hours", "wh", "hours", "total hours", "work hours", "worked hours", "duration"],
               fit=lambda c: max(c.f("time"), c.f("num") * 0.6)),
    "count": F(label="Count / cases", syn=["count", "cases", "number of cases", "no of cases", "count of", "incidents", "total cases",
               "da count", "warnings", "no of da", "occurrences"], fit=lambda c: c.f("small_int") * (1 if c.f("num") > 0.9 else 0.3)),
    "action": F(label="Action taken", syn=["action", "action taken", "da type", "type of action", "penalty", "warning type", "violation",
                "offence", "misconduct", "case type", "category of violation"],
                fit=lambda c: 0.5 if c.n and c.f("num") < 0.2 else 0.0),
    "nps": F(label="NPS", syn=["nps", "net promoter score", "nps score", "customer nps"], fit=lambda c: c.f("nps") * (1 if c.f("num") > 0.8 else 0)),
    "city": F(label="City", syn=["city", "region", "town"], fit=lambda c: 0.0),
    "sales_actual": F(label="Sales (actual)", syn=["net sales", "sales", "actual", "net sales actual", "sales actual", "revenue",
                      "sales mtd", "sales ytd", "actual sales"], fit=lambda c: c.f("money"), avoid=["budget", "target", "ly", "last year", "%"]),
    "sales_budget": F(label="Sales budget", syn=["budget", "net sales budget", "sales budget", "target sales", "plan", "sales target",
                      "budget sales"], fit=lambda c: c.f("money"), avoid=["%", "var"]),
    "sales_ly": F(label="Sales last year", syn=["ly", "last year", "sales ly", "previous year", "ly sales", "prior year"],
                  fit=lambda c: c.f("money"), avoid=["%", "gth", "growth"]),
}

# Report types P&O can build from mapped columns. 'need': every field required (a tuple = any one of them);
# 'want': fields that make the match more certain; 'never': fields that point to another report.
KINDS: dict[str, dict] = {
    "roster": dict(need=["employee_id", "employee_name"], want=["designation", "store", "joining_date", "manager_name", "grade", "gender",
                   "section", "department"], min_want=3, never=["exit_date", "rating", "leave_from", "time_in", "role_since"],
                   label="Employee master (Basic Sheet)"),
    "po_role": dict(need=[("employee_name", "employee_id"), "role_since"], want=["designation", "store", "section", "remarks"], min_want=1,
                    never=["exit_date", "rating", "leave_from"], label="Time in current role"),
    "po_rating": dict(need=[("employee_id", "employee_name"), "rating"], want=["cycle", "rating_label", "designation", "store", "manager_name"],
                      min_want=1, never=["exit_date", "leave_from", "time_in"], label="Performance ratings"),
    "po_turnover": dict(need=[("employee_id", "employee_name"), "exit_date"], want=["exit_type", "reason", "store", "section", "joining_date"], min_want=1,
                        never=["rating", "leave_from", "time_in"], label="Turnover (leavers)"),
    "leave": dict(need=["employee_id", "leave_from"], want=["leave_to", "leave_type", "status", "employee_name"], min_want=1,
                  never=["exit_date", "rating", "time_in"], label="Leave register"),
    "attendance": dict(need=["employee_id", "date", ("time_in", "hours")], want=["time_out", "employee_name", "store", "status"], min_want=0,
                       never=["exit_date", "rating", "leave_from"], label="Biometric attendance"),
    "po_da": dict(need=["store", ("count", "employee_id", "employee_name", "action")], want=["section", "date", "action", "count"], min_want=1,
                  never=["rating", "leave_from", "time_in", "joining_date"], label="Disciplinary actions (DA)", context=r"disciplin|\bda\b|warning|show cause|misconduct|violation|penalt"),
    "sales_simple": dict(need=["store", "sales_actual"], want=["sales_budget", "sales_ly"], min_want=1,
                         never=["employee_id", "employee_name"], label="Store sales (table)"),
}


@lru_cache(maxsize=20000)
def header_score(header: str, field: str) -> float:
    h = _hdr(header)
    if not h:
        return 0.0
    d = FIELDS[field]
    if any(re.search(rf"\b{re.escape(_hdr(a))}\b", h) for a in d.get("avoid", [])):
        return 0.0
    best = 0.0
    ht = set(h.split())
    for syn in d["syn"]:
        s = _hdr(syn)
        if h == s:
            return 1.0
        st = set(s.split())
        if len(s) >= 3 and re.search(rf"\b{re.escape(s)}\b", h):
            best = max(best, 0.82 if len(st) > 1 else (0.72 if len(ht) <= 2 else 0.55))
        overlap = len(ht & st) / max(len(ht | st), 1)
        best = max(best, overlap * 0.8, SequenceMatcher(None, h, s).ratio() * 0.75 if len(h) > 3 else 0)
    return best


def field_score(col: Column, field: str) -> float:
    hs = header_score(col.header, field)
    try:
        fit = float(FIELDS[field]["fit"](col)) if col.n else 0.0
    except Exception:  # noqa: BLE001
        fit = 0.0
    if hs and fit:
        return min(1.0, 0.5 * hs + 0.5 * fit + 0.1)
    if hs >= 0.95:
        return 0.6                               # exact name, values don't confirm (often an empty column)
    if hs:
        return 0.45 * hs
    return 0.55 * fit if fit >= 0.85 else 0.0    # unnamed or oddly named column whose values are unmistakable
