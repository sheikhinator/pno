"""Biometric attendance.

Main layout (MTD grid): a title row with the dates ('1-Aug-26') above IN / OUT / Total WH triplets, one row per person,
and the system's own Absent / Present totals at the end. A simple long layout (one row per person per day) also works.

The biometric system has no status column. The status of a day is read from the three cells:
    IN   OUT   Total WH
    time time  9:36      present
    time NM    Absent    missing OUT punch (came to work)
    0/NM time  Absent    missing IN punch (came to work)
    NM   NM    9:19      hours entered by hand, no punches
    time time  Absent    both punches but marked absent (hours worked out from the punches)
    NM   NM    Absent    no punch at all
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from ..reader import Sheet
from ..util import clean_text, emp_code, is_blank, month_of, norm, num, parse_clock, parse_date, parse_duration, span_minutes, title_name
from .base import ParseResult, blank_row, cells, find_col, get, text

EMP = r"EMPLOYEE (NUMBER|NO|CODE|ID)|EMP (NO|NUMBER|CODE|ID)|STAFF (NO|ID)"
STATUS_WORDS = {
    "leave": re.compile(r"LEAVE|\bAL\b|\bSL\b|\bCL\b"),
    "off": re.compile(r"\bOFF\b|WEEKLY OFF|W O|REST"),
    "holiday": re.compile(r"HOLIDAY|\bPH\b|GAZETTED"),
}


def _triplets(h: list[str]) -> list[int]:
    out = []
    for i in range(len(h) - 2):
        if h[i] in ("IN", "TIME IN", "IN TIME", "CHECK IN") and h[i + 1] in ("OUT", "TIME OUT", "OUT TIME", "CHECK OUT") \
                and re.match(r"^(TOTAL )?(WH|WORKING HOURS|HOURS|WORK HOURS|TOTAL)$", h[i + 2]):
            out.append(i)
    return out


def score(sheet: Sheet) -> tuple[float, int]:
    for i, row in enumerate(sheet.rows[:15]):
        h = cells(row)
        if len(_triplets(h)) >= 2 and find_col(h, EMP) is not None:
            return 0.97, i
        if find_col(h, EMP) is not None and find_col(h, r"DATE|ATTENDANCE DATE") is not None and \
                (find_col(h, r"IN|TIME IN|IN TIME|CHECK IN") is not None or find_col(h, r"(TOTAL )?(WH|HOURS)") is not None):
            return 0.8, i
    return 0.0, -1


def classify(t_in_raw, t_out_raw, wh_raw) -> tuple[str, str | None, str | None, int | None]:
    t_in, t_out = parse_clock(t_in_raw), parse_clock(t_out_raw)
    wh_text = norm(wh_raw)
    mins = parse_duration(wh_raw) if not re.search(r"[A-Z]", wh_text) else None
    for status, rx in STATUS_WORDS.items():
        if wh_text and rx.search(wh_text) and "ABSENT" not in wh_text:
            return f"sys_{status}", t_in, t_out, None
    if mins is not None and mins > 0:
        return ("present" if (t_in or t_out) else "manual"), t_in, t_out, mins
    if t_in and t_out:
        return "punched_absent", t_in, t_out, span_minutes(t_in, t_out)
    if t_in:
        return "missing_out", t_in, None, None
    if t_out:
        return "missing_in", None, t_out, None
    return "no_punch", None, None, None


def parse(sheet: Sheet) -> ParseResult:
    conf, hr = score(sheet)
    h = cells(sheet.rows[hr])
    if len(_triplets(h)) >= 2:
        return _parse_grid(sheet, hr)
    return _parse_long(sheet, hr)


def _people_cols(h: list[str], limit: int) -> dict:
    sub = h[:limit]
    return {
        "bu": find_col(sub, r"BUSINESS UNIT( NAME)?|STORE( NAME)?|LOCATION|BRANCH"),
        "section": find_col(sub, r"SECTION( NAME)?"),
        "emp": find_col(sub, EMP),
        "name": find_col(sub, r"EMPLOYEE+ NAME|NAME"),
        "desig": find_col(sub, r"DESIGNATION|JOB TITLE|POSITION"),
        "joining": find_col(sub, r"JOINING DATE|DATE OF JOINING|DOJ"),
    }


def _parse_grid(sheet: Sheet, hr: int) -> ParseResult:
    res = ParseResult(kind="attendance", sheet=sheet.name)
    rows = sheet.rows
    h = cells(rows[hr])
    trip = _triplets(h)
    date_row = rows[hr - 1] if hr > 0 else []
    days: list[date | None] = []
    for c in trip:
        d = None
        for j in (c, c + 1, c + 2):
            d = parse_date(get(date_row, j))
            if d:
                break
        days.append(d)
    # fill gaps (merged or missing headings) from neighbours
    for k in range(len(days)):
        if days[k] is None:
            prev = next((days[j] for j in range(k - 1, -1, -1) if days[j]), None)
            if prev:
                from datetime import timedelta
                days[k] = prev + timedelta(days=k - days.index(prev))
    if not any(days):
        res.warn("The dates above the IN / OUT / Total WH columns could not be read.")
        res.needs = ["month"]
    col = _people_cols(h, trip[0])
    tail = trip[-1] + 3
    c_abs = find_col(h, r"ABSENT|TOTAL ABSENT", start=tail)
    c_pre = find_col(h, r"PRESENT|TOTAL PRESENT", start=tail)
    people = []
    day_rows = []
    activity: Counter = Counter()
    for row in rows[hr + 1:]:
        if blank_row(row):
            continue
        emp = emp_code(get(row, col["emp"]))
        if not emp or not re.search(r"\d", emp):
            continue
        jd = parse_date(get(row, col["joining"])) if col["joining"] is not None else None
        person = {"emp_no": emp, "name": title_name(get(row, col["name"])), "bu": text(row, col["bu"]),
                  "section": text(row, col["section"]), "designation": text(row, col["desig"]),
                  "joining": jd.isoformat() if jd else None,
                  "sys_absent": _int(get(row, c_abs)), "sys_present": _int(get(row, c_pre)), "counted_present": 0}
        for c, d in zip(trip, days):
            if d is None:
                continue
            raw = (get(row, c), get(row, c + 1), get(row, c + 2))
            if all(is_blank(x) for x in raw):
                continue
            status, t_in, t_out, mins = classify(*raw)
            if status != "no_punch":
                activity[d] += 1
            if parse_duration(raw[2]) and not re.search(r"[A-Za-z]", clean_text(raw[2])):
                person["counted_present"] += 1
            day_rows.append({"emp_no": emp, "day": d.isoformat(), "t_in": t_in, "t_out": t_out, "minutes": mins,
                             "wh_raw": clean_text(raw[2])[:20], "status": status})
        people.append(person)
    _finish(res, people, day_rows, activity)
    return res


def _parse_long(sheet: Sheet, hr: int) -> ParseResult:
    res = ParseResult(kind="attendance", sheet=sheet.name)
    h = cells(sheet.rows[hr])
    col = _people_cols(h, len(h))
    c_date = find_col(h, r"DATE|ATTENDANCE DATE|DAY")
    c_in = find_col(h, r"IN|TIME IN|IN TIME|CHECK IN|CLOCK IN")
    c_out = find_col(h, r"OUT|TIME OUT|OUT TIME|CHECK OUT|CLOCK OUT")
    c_wh = find_col(h, r"(TOTAL )?(WH|WORKING HOURS|HOURS|WORK HOURS)")
    c_st = find_col(h, r"STATUS|ATTENDANCE STATUS")
    people: dict[str, dict] = {}
    day_rows = []
    activity: Counter = Counter()
    for row in sheet.rows[hr + 1:]:
        if blank_row(row):
            continue
        emp = emp_code(get(row, col["emp"]))
        d = parse_date(get(row, c_date))
        if not emp or not d:
            continue
        if emp not in people:
            jd = parse_date(get(row, col["joining"])) if col["joining"] is not None else None
            people[emp] = {"emp_no": emp, "name": title_name(get(row, col["name"])), "bu": text(row, col["bu"]),
                           "section": text(row, col["section"]), "designation": text(row, col["desig"]),
                           "joining": jd.isoformat() if jd else None, "sys_absent": None, "sys_present": None,
                           "counted_present": 0}
        wh = get(row, c_wh)
        st = norm(get(row, c_st))
        if c_wh is None and st:
            wh = "Absent" if st.startswith("A") else get(row, c_st)
        status, t_in, t_out, mins = classify(get(row, c_in), get(row, c_out), wh)
        if status == "no_punch" and st in ("P", "PRESENT"):
            status = "manual"
        if status != "no_punch":
            activity[d] += 1
        day_rows.append({"emp_no": emp, "day": d.isoformat(), "t_in": t_in, "t_out": t_out, "minutes": mins,
                         "wh_raw": clean_text(wh)[:20], "status": status})
    _finish(res, list(people.values()), day_rows, activity)
    return res


def _finish(res: ParseResult, people: list[dict], day_rows: list[dict], activity: Counter) -> None:
    if not day_rows:
        res.warn("No attendance days were found.")
        res.summary = "No attendance rows"
        return
    months = Counter(r["day"][:7] for r in day_rows)
    res.month = months.most_common(1)[0][0]
    # MTD files run mid-month show 'Not Marked' for days that have not happened yet: stop at the last day anyone punched
    threshold = max(1, int(len(people) * 0.05))
    active_days = sorted(d for d, n in activity.items() if n >= threshold)
    last = active_days[-1] if active_days else max(date.fromisoformat(r["day"]) for r in day_rows)
    res.as_of = last.isoformat()
    dropped = [r for r in day_rows if r["day"] > res.as_of]
    res.rows = [r for r in day_rows if r["day"] <= res.as_of]
    if dropped:
        res.warn(f"Days after {last:%d %b} have no punches for anyone yet; they are not counted as absences.")
    if len(months) > 1:
        res.warn("The file covers more than one month: " + ", ".join(sorted(months)))
    mism = [p for p in people if p["sys_present"] is not None and p["sys_present"] != p["counted_present"]]
    if mism:
        res.warn(f"For {len(mism)} people the file's own 'Present' total differs from the days with hours.")
    res.extra["people"] = people
    st = Counter(r["status"] for r in res.rows)
    fixes = st["missing_out"] + st["missing_in"] + st["punched_absent"]
    res.summary = (f"{len(people):,} people · {res.month} up to {last:%d %b} · {st['present'] + st['manual']:,} worked days · "
                   f"{fixes:,} punches to fix")
    res.preview = [{"emp_no": p["emp_no"], "name": p["name"], "store": p["bu"], "present": p["counted_present"],
                    "system_absent": p["sys_absent"]} for p in people[:8]]


def _int(v):
    f = num(v)
    return int(f) if f is not None else None


def month_from(res: ParseResult) -> str | None:
    return res.month or (month_of(res.as_of) if res.as_of else None)
