"""Cell values and file reading: the small things every parser depends on."""

from datetime import date, datetime, time, timedelta

import openpyxl
import pytest

from pno import reader
from pno.util import (clean_text, emp_code, fmt_minutes, month_bounds, month_label, norm, parse_clock, parse_date,
                      parse_duration, parse_num, prev_month, span_minutes, title_name)


@pytest.mark.parametrize("raw, value, pct", [
    ("12,885,231", 12885231, False),
    ("(15.2%)", -15.2, True),
    ("370.3%", 370.3, True),
    ("▲ 3%", 3, True),
    ("▼ -6%", -6, True),
    ("▼ 6%", -6, True),
    ("▬ 0%", 0, True),
    ("1,725.3%", 1725.3, True),
    ("-195", -195, False),
    ("5,676.3", 5676.3, False),
    (42, 42, False),
    ("#DIV/0!", None, False),
    ("-", None, False),
    ("", None, False),
    (None, None, False),
])
def test_parse_num(raw, value, pct):
    v, p = parse_num(raw)
    assert v == value
    if value is not None:
        assert p == pct


@pytest.mark.parametrize("raw, out", [
    ("15:45:24", "15:45"), ("01:21:34", "01:21"), ("9:05 PM", "21:05"), ("12:10 AM", "00:10"),
    (time(8, 2), "08:02"), (0.5, "12:00"), ("Not Marked", None), ("Absent", None), (None, None), (0, None),
])
def test_parse_clock(raw, out):
    assert parse_clock(raw) == out


@pytest.mark.parametrize("raw, mins", [
    ("9:36", 576), ("10:31", 631), ("8:53", 533), (9.5, 570), (0.375, 540), (timedelta(hours=9, minutes=6), 546),
    (time(9, 9), 549), ("Absent", None), ("", None), (None, None),
])
def test_parse_duration(raw, mins):
    assert parse_duration(raw) == mins


def test_span_overnight():
    assert span_minutes("15:45", "01:21") == 576
    assert span_minutes("09:00", "18:00") == 540
    assert span_minutes(None, "18:00") is None
    assert fmt_minutes(576) == "9:36" and fmt_minutes(None) == "—"


@pytest.mark.parametrize("raw, d", [
    ("1-Aug-26", date(2026, 8, 1)), ("19/12/2025", date(2025, 12, 19)), ("2026-08-01", date(2026, 8, 1)),
    ("(Fri) 02-Oct-26", date(2026, 10, 2)), ("Sep 30, 2026", date(2026, 9, 30)), (46000, date(2025, 12, 9)),
    (datetime(2026, 9, 1, 10), date(2026, 9, 1)), ("12/25/2026", date(2026, 12, 25)), ("hello", None), ("31/02/2026", None),
])
def test_parse_date(raw, d):
    assert parse_date(raw) == d


def test_text_helpers():
    assert clean_text("  H&B PK KCH Lucky One          ") == "H&B PK KCH Lucky One"
    assert norm("Deli & Dairy") == "DELI AND DAIRY"
    assert title_name("kashan rehman") == "Kashan Rehman"
    assert title_name("McArthur Khan") == "McArthur Khan"
    assert emp_code(20064066.0) == "20064066" and emp_code(" 20064066 ") == "20064066"


def test_months():
    assert month_bounds("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert month_bounds("2026-12")[1] == date(2026, 12, 31)
    assert prev_month("2026-01") == "2025-12" and prev_month("2026-09") == "2026-08"
    assert "Sept" in month_label("2026-09") or "September" in month_label("2026-09")


def test_reader_csv_encodings():
    text = "Employee No,Name\n1001,Áli Khan\n1002,Sara\n"
    for data in (text.encode("utf-8"), b"\xef\xbb\xbf" + text.encode("utf-8"), text.encode("utf-16"),
                 text.encode("cp1252")):
        wb = reader.open_bytes(data, "x.csv")
        assert wb.sheets[0].rows[0] == ["Employee No", "Name"]
        assert wb.sheets[0].rows[1][1] == "Áli Khan"


def test_reader_delimiters():
    for d in ("\t", ";", "|"):
        wb = reader.open_bytes(f"a{d}b{d}c\n1{d}2{d}3\n4{d}5{d}6\n".encode(), "x.txt")
        assert wb.sheets[0].rows[2] == ["4", "5", "6"]


def test_reader_html_xls():
    html = b"<html><body><table><tr><td>Store</td><td>Sales</td></tr><tr><td>A</td><td>1,000</td></tr></table></body></html>"
    wb = reader.open_bytes(html, "report.xls")
    assert wb.sheets[0].rows == [["Store", "Sales"], ["A", "1,000"]]


def test_reader_xlsx_hidden_and_blank_sheets(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Employee No", "Name"])
    ws.append([1001, "Ali"])
    wb.create_sheet("Empty")
    p = tmp_path / "x.xlsx"
    wb.save(p)
    out = reader.open_file(p)
    assert [s.name for s in out.sheets] == ["Data"]
    assert out.sheets[0].rows[1][0] in (1001, 1001.0)


def test_reader_garbage_is_not_a_crash():
    wb = reader.open_bytes(b"PK\x03\x04 this is not really a zip", "broken.xlsx")
    assert wb.sheets == [] and wb.warnings
