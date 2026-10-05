"""The scoring rules HR agreed: 9-hour days, one weekly off per week (store) / Sat+Sun (head office), leave and
holidays never count against anyone, and each person is scored only on KPIs they control."""

from datetime import date

import pytest

from pno import engine
from pno.engine import DEFAULT_RULES, attendance_summary, band, curve3

R = dict(DEFAULT_RULES)


def day(status, minutes=None, t_in=None, t_out=None):
    return {"status": status, "minutes": minutes, "t_in": t_in, "t_out": t_out}


def month_days(first: date, last: date, fn):
    out, d = {}, first
    while d <= last:
        v = fn(d)
        if v:
            out[d.isoformat()] = v
        d = date.fromordinal(d.toordinal() + 1)
    return out


def summary(days, start=date(2026, 9, 1), end=date(2026, 9, 30), is_ho=False, holidays=None, leave=None, joining=None):
    return attendance_summary(days, start, end, joining, holidays or {}, leave or {}, is_ho, R)


def test_curve_and_bands():
    assert curve3(80, 80, 100, 115) == 0 and curve3(100, 80, 100, 115) == 7 and curve3(115, 80, 100, 115) == 10
    assert curve3(90, 80, 100, 115) == pytest.approx(3.5)
    assert curve3(200, 80, 100, 115) == 10 and curve3(10, 80, 100, 115) == 0
    assert band(9.2)[0] == "Outstanding" and band(7.5)[0] == "Strong" and band(6)[0] == "Meets expectation"
    assert band(4.1)[0] == "Needs improvement" and band(1)[0] == "Concern" and band(None)[0] == "No score"


def test_store_staff_get_one_off_per_week_even_with_five_in_a_month():
    # Sept 2026 has five Tuesdays; someone off every Tuesday and working 9h every other day is 100% present.
    days = month_days(date(2026, 9, 1), date(2026, 9, 30),
                      lambda d: None if d.weekday() == 1 else day("present", 545, "09:00", "18:05"))
    s = summary(days)
    assert s["off"] == 5 and s["absent"] == 0 and s["presence"] == 100.0 and s["compliance"] == 100.0
    assert s["score"] == 10


def test_second_missing_day_in_a_week_is_absent():
    days = month_days(date(2026, 9, 7), date(2026, 9, 13),
                      lambda d: None if d.weekday() in (0, 1) else day("present", 540, "09:00", "18:00"))
    s = summary(days, date(2026, 9, 7), date(2026, 9, 13))
    assert s["off"] == 1 and s["absent"] == 1 and s["worked"] == 5


def test_head_office_weekends_are_off():
    days = month_days(date(2026, 9, 1), date(2026, 9, 30),
                      lambda d: None if d.weekday() >= 5 else day("present", 540, "09:00", "18:00"))
    s = summary(days, is_ho=True)
    assert s["absent"] == 0 and s["off"] == 8
    # a weekday off is NOT an automatic weekly off at head office
    days.pop("2026-09-02")
    assert summary(days, is_ho=True)["absent"] == 1


def test_leave_and_holidays_never_count_as_absence():
    days = month_days(date(2026, 9, 1), date(2026, 9, 30),
                      lambda d: None if d.day in (3, 4, 5, 14) else day("present", 540, "09:00", "18:00"))
    s = summary(days, holidays={"2026-09-14": "Holiday"}, leave={"2026-09-03": "Annual", "2026-09-04": "Annual",
                                                                 "2026-09-05": "Annual"})
    assert s["absent"] == 0 and s["leave"] == 3 and s["holiday"] == 1


def test_short_hours_and_night_shift():
    days = {"2026-09-01": day("present", 480, "09:00", "17:00"), "2026-09-02": day("present", 560, "15:00", "00:20")}
    s = summary(days, date(2026, 9, 1), date(2026, 9, 2))
    assert s["full_days"] == 1 and s["short_days"] == 1 and s["compliance"] == 50.0 and s["night_days"] == 1
    assert s["avg_minutes"] == 520


def test_punch_problems_count_as_worked_but_flagged():
    days = {"2026-09-01": day("missing_out", None, "09:00"), "2026-09-02": day("punched_absent", 540, "09:00", "18:00"),
            "2026-09-03": day("no_punch")}
    s = summary(days, date(2026, 9, 1), date(2026, 9, 3))
    assert s["worked"] == 2 and s["fixes"] == 2 and s["off"] == 1 and s["absent"] == 0


def test_joiner_mid_month_only_counts_from_joining():
    days = month_days(date(2026, 9, 20), date(2026, 9, 30), lambda d: day("present", 540, "09:00", "18:00"))
    s = summary(days, joining="2026-09-20")
    assert s["days"] == 11 and s["absent"] == 0


def test_long_absence_streak_skips_offs():
    days = month_days(date(2026, 9, 1), date(2026, 9, 30), lambda d: day("present", 540) if d.day < 10 else None)
    s = summary(days)
    assert s["longest_absence"] >= 7


# ------------------------------------------------------------------ the month model on the demo data
@pytest.fixture
def mm(db):
    return engine.model(db, "2026-09")


def test_roles_and_domains(mm):
    roles = {p.role for p in mm.people.values()}
    assert {"GM", "DH", "SM", "HBM", "CCO", "STAFF"} <= roles
    gm = [p for p in mm.people.values() if p.role == "GM"]
    assert gm and all(p.domain.get("level") == "store" for p in gm)
    for p in mm.people.values():
        if p.role == "SM" and p.domain.get("level") == "section":
            assert p.domain.get("codes"), p.name


def test_scores_are_0_to_10_and_use_only_controllable_kpis(mm):
    scored = [p for p in mm.people.values() if p.score is not None]
    assert len(scored) > 0.8 * len(mm.people)
    for p in scored:
        assert 0 <= p.score <= 10
        assert p.coverage * 100 >= DEFAULT_RULES["min_coverage"]
        keys = {c["key"] for c in p.components}
        assert keys == set(engine.DEFAULT_WEIGHTS[p.role])
    for p in mm.people.values():
        if p.role == "CCO":
            assert not {"sales", "oos", "waste"} & {c["key"] for c in p.components}


def test_score_is_weighted_average_of_available_components(mm):
    p = next(p for p in mm.people.values() if p.role == "SM" and p.score is not None)
    av = [c for c in p.components if c["available"]]
    expect = sum(c["weight"] * c["score"] for c in av) / sum(c["weight"] for c in av)
    assert p.score == pytest.approx(expect, abs=0.06)


def test_gm_is_judged_on_total_store(mm, db):
    gm = next(p for p in mm.people.values() if p.role == "GM" and p.kpis.get("sales") is not None)
    row = db.q1("""SELECT s.actual, s.budget FROM sales s JOIN imports i ON i.id=s.import_id AND i.active=1
                   WHERE s.store_id=? AND s.level='store' AND s.month='2026-09' ORDER BY s.as_of DESC LIMIT 1""", (gm.store_id,))
    assert gm.kpis["sales"] == pytest.approx(row["actual"] / row["budget"] * 100, abs=0.1)


def test_fresh_department_head_gets_productivity(mm):
    fresh = [p for p in mm.people.values() if p.role == "DH" and p.domain.get("dept") == "02"]
    assert fresh and any(p.kpis.get("prod") is not None for p in fresh)


def test_previous_month_is_available(db):
    assert engine.months_available(db) == ["2026-08", "2026-09"]
    aug = engine.model(db, "2026-08")
    assert aug.complete and len(aug.people) > 400


def test_weights_from_settings_change_scores(db):
    before = {e: p.score for e, p in engine.model(db, "2026-09").people.items()}
    db.set_setting("weights", {"SM": {"sales": 100}})
    after = engine.model(db, "2026-09")
    p = next(p for p in after.people.values() if p.role == "SM" and p.kpis.get("sales") is not None and p.score is not None)
    assert [c["key"] for c in p.components] == ["sales"]
    assert p.score != before[p.emp] or p.score == p.components[0]["score"]


def test_model_is_cached_until_data_changes(db):
    a = engine.model(db, "2026-09")
    assert engine.model(db, "2026-09") is a
    db.x("INSERT INTO holidays(day, name) VALUES('2026-09-15','Test')")
    assert engine.model(db, "2026-09") is not a
