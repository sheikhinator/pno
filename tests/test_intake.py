"""4.3 guided intake: click a report on the Data checklist, give a file or paste cells, verify, save."""
import base64
import io
import subprocess
import sys
from pathlib import Path

from pno import importers
from pno.api import Api
from pno.db import Database
from pno.importers import reshape
from pno.reader import Sheet, from_text


def _api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    return Api(Database(tmp_path / "p.sqlite3"))


def _sales(tmp_path):
    p = tmp_path / "Sheet1.xlsx"
    subprocess.run([sys.executable, str(Path(__file__).with_name("make_sales_table.py")), str(p)], check=True)
    return p


def test_missing_sales_slot_reads_verifies_and_saves(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    r = api.dispatch("slot_read", {"kind": "sales", "month": "ytd:2026-09", "paths": [str(_sales(tmp_path))]})
    assert r["status"] in ("good", "warn") and r["period"]["type"] == "ytd" and r["period"]["to"] == "2026-09"
    texts = " ".join(c["text"] for c in r["checks"])
    assert "Net sales: found" in texts and "Budget: found" in texts and "stores recognised" in texts
    s = api.dispatch("slot_save", {"token": r["token"], "kind": "sales", "month": "ytd:2026-09"})
    assert s["done"][0]["results"][0]["kind"] == "sales"
    info = api.dispatch("slot_info", {"kind": "sales", "month": "2026-09"})
    assert info["imports"] and info["imports"][0]["rows"] > 100


def test_wrong_report_for_the_slot_is_red(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    r = api.dispatch("slot_read", {"kind": "po_nps", "month": "2026-10", "text": "Employee\tRating\nAli\t4\nSara\t3\nOmar\t5\n"})
    assert r["status"] == "bad"


def test_paste_lined_up_with_spaces():
    wb = from_text("Store Short Name    Section       Budget      Net Sales\n651 LAH Fortress    CGD - Beverages    1,000,000    1,100,000\n"
                   "654 KCH Lucky One    CGD - Beverages    900,000    800,000\n")
    assert wb.sheets[0].rows[0] == ["Store Short Name", "Section", "Budget", "Net Sales"]


def test_stores_across_columns_are_melted():
    sh = Sheet("Prod", [["Section", "LAH Fortress", "KCH Lucky One", "ISL WTC"], ["Beverages", 10, 12, 9], ["Bakery", 7, 8, 6], ["Total", 17, 20, 15]])
    m = reshape.melt_stores(sh, "sales")
    assert m.rows[0] == ["Section", "Store", "Net Sales"] and len(m.rows) == 7


def test_two_tables_on_one_sheet_are_split():
    rows = [["a", "b"], [1, 2], [3, 4], [None, None], ["c", "d"], [5, 6], [7, 8]]
    assert len(reshape.split_tables(Sheet("S", rows))) == 2


def test_sanity_flags_same_column_twice():
    from pno import intake
    rows = [{"actual": 100 + i, "budget": 100 + i} for i in range(5)]
    assert any("same on every row" in t for _, t in intake.sanity("sales", rows))


def test_ask_once_adds_budget_from_second_file(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    a = "Store Short Name\tSection\tCode\tNet Sales\n651 LAH Fortress\tCGD - Beverages\tS011\t1100\n654 KCH Lucky One\tCGD - Beverages\tS011\t800\n656 LAH Packages\tCGD - Beverages\tS011\t700\n"
    b = "Store Short Name\tSection\tCode\tBudget\tNet Sales\n651 LAH Fortress\tCGD - Beverages\tS011\t1000\t1\n654 KCH Lucky One\tCGD - Beverages\tS011\t900\t1\n"
    r = api.dispatch("slot_read", {"kind": "sales", "month": "2026-10", "text": a})
    assert any("Budget: not in this file" in c["text"] for c in r["checks"])
    r2 = api.dispatch("slot_extra", {"token": r["token"], "kind": "sales", "month": "2026-10", "text": b})
    assert any("Added budget" in c["text"] for c in r2["checks"])


def test_pdf_table_is_read(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in [("Store Short Name", "Section", "Code", "Budget", "Net Sales"), ("651 LAH Fortress", "CGD - Beverages", "S011", "1,000", "1,100"),
                 ("654 KCH Lucky One", "CGD - Beverages", "S011", "900", "800"), ("656 LAH Packages", "CGD - Grocery", "S014", "500", "650")]:
        for x, t in zip((40, 170, 290, 350, 430), line):
            c.drawString(x, y, t)
        y -= 18
    c.save()
    a = importers.analyze_bytes(buf.getvalue(), "sales.pdf")
    assert a["results"] and a["results"][0].kind == "sales"


def test_columns_matched_by_hand_are_remembered_for_the_layout(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    t = "Staff\tWhen\tCame\tLeft\nA-101\t2026-10-01\t09:02\t18:10\nA-102\t2026-10-01\t08:55\t17:40\nA-103\t2026-10-01\t10:05\t19:00\n"
    r = api.dispatch("slot_read", {"kind": "attendance", "month": "2026-10", "text": t})
    assert r["status"] == "bad" and r["columns"]
    ai = api.dispatch("slot_ai", {"token": r["token"], "kind": "attendance", "month": "2026-10"})
    assert "ai_note" in ai                                                    # no AI set up: still answers
    r = api.dispatch("slot_fix", {"token": r["token"], "kind": "attendance", "month": "2026-10",
                                  "mapping": {"employee_id": 0, "date": 1, "time_in": 2, "time_out": 3}})
    assert r["status"] == "good"
    again = api.dispatch("slot_read", {"kind": "attendance", "month": "2026-10", "text": t})
    assert again["status"] == "good"


def test_replace_takes_the_place_of_the_old_import(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    f = str(_sales(tmp_path))
    r = api.dispatch("slot_read", {"kind": "sales", "month": "ytd:2026-09", "paths": [f]})
    api.dispatch("slot_save", {"token": r["token"], "kind": "sales", "month": "ytd:2026-09"})
    old = [x["id"] for x in api.dispatch("slot_info", {"kind": "sales", "month": "ytd:2026-09"})["imports"]]
    r = api.dispatch("slot_read", {"kind": "sales", "month": "ytd:2026-09", "paths": [f]})
    api.dispatch("slot_save", {"token": r["token"], "kind": "sales", "month": "ytd:2026-09", "replace": old})
    now_ids = [x["id"] for x in api.dispatch("slot_info", {"kind": "sales", "month": "ytd:2026-09"})["imports"]]
    assert len(now_ids) == 1 and now_ids[0] not in old


def _merged(tmp_path):
    p = tmp_path / "Book2.xlsx"
    subprocess.run([sys.executable, str(Path(__file__).with_name("make_sales_table.py")), str(p), "--merged"], check=True)
    return p


def test_titles_merged_over_two_rows_read_every_section(tmp_path):
    (r,) = importers.analyze_path(_merged(tmp_path))["results"]
    assert r.kind == "sales" and r.confidence >= 0.9
    secs = {x["name"] for x in r.rows if x["level"] == "section"}
    assert len(secs) >= 10 and any(x["level"] == "dept" for x in r.rows) and {x["period"] for x in r.rows} == {"YTD"}


def test_only_store_totals_is_red_when_the_file_has_sections(tmp_path, monkeypatch):
    from pno import intake
    from pno.importers.base import ParseResult
    res = ParseResult(kind="sales", sheet="S", rows=[{"level": "store", "code": "STORE", "name": "Total Store", "store_raw": "LAH Fortress", "actual": 5.0, "budget": 4.0}] * 4)
    v = intake.verify("sales", res, {"type": "ytd", "from": "2026-01", "to": "2026-09"}, [], False, "store sales", True)
    assert v["status"] == "bad" and any("Sections: none read" in c["text"] for c in v["checks"])


def test_smart_sales_keeps_sections_when_matched(tmp_path):
    from pno.reader import from_text
    from pno import smart
    t = "Shop\tCategory\tPlan\tActual sales\n651 LAH Fortress\tCGD - Beverages\t100\t110\n654 KCH Lucky One\tCGD - Beverages\t90\t80\n651 LAH Fortress\tFFD - Bakery\t50\t55\n"
    res, _ = smart.read(from_text(t).sheets[0], "x", kind="sales_simple")
    assert {x["name"] for x in res.rows if x["level"] == "section"} == {"Beverages", "Bakery"}
    assert any(x["level"] == "store" and x["store_raw"] == "LAH Fortress" and x["actual"] == 165 for x in res.rows)


def test_agent_fixes_a_copy_for_review_then_uses_it(tmp_path, monkeypatch):
    from pno.reader import from_text
    from pno.smart import repair
    api = _api(tmp_path, monkeypatch)
    # titles over two rows + grouped section written once + subtotal lines: a layout no reader takes as it is
    t = ("Area\tWhere\tYTD\t\n\t\tBudget\tNet Sales\nCGD - Beverages\t651 LAH Fortress\t100,250,300\t110,400,120\n\t654 KCH Lucky One\t90,120,000\t80,555,210\n"
         "\t\t190,370,300\t190,955,330\nFFD - Bakery\t651 LAH Fortress\t50,300,100\t55,620,900\n\t654 KCH Lucky One\t40,100,500\t45,333,800\n\t\t90,400,600\t100,954,700\n")
    plan = repair.engine_plan(from_text(t).sheets[0], "sales")
    assert [o["op"] for o in plan][:1] == ["header"] and any(o["op"] == "fill_down" for o in plan)
    assert "651" not in repair.ai_prompt(from_text(t).sheets[0], "sales", "store sales", ["store"])      # no cell values to the AI
    r = api.dispatch("slot_read", {"kind": "sales", "month": "ytd:2026-09", "text": t})
    x = api.dispatch("slot_repair", {"token": r["token"], "kind": "sales", "month": "ytd:2026-09", "use_ai": False})
    assert x["steps"] and x["check"]["status"] in ("good", "warn") and x["after"][0][0]
    d = api.dispatch("slot_repair_download", {"token": r["token"]})
    assert d.get("path") or d.get("b64")
    u = api.dispatch("slot_repair_use", {"token": r["token"], "kind": "sales", "month": "ytd:2026-09"})
    assert u["status"] in ("good", "warn") and any("Fixed:" in c["text"] for c in u["checks"])
    s = api.dispatch("slot_save", {"token": r["token"], "kind": "sales", "month": "ytd:2026-09"})
    assert s["done"][0]["results"][0]["status"] == "ok"


def test_running_month_is_not_open_and_general_reports_not_counted(tmp_path, monkeypatch):
    from datetime import date
    api = _api(tmp_path, monkeypatch)
    cal = api.dispatch("import_calendar", {"year": date.today().year})
    cur = date.today().strftime("%Y-%m")
    for m in cal["months"]:
        if m["month"] == cur:
            assert m["running"] and m["future"]
        assert m["total"] == len([i for i in m["items"] if not i["every"]])


def test_ai_plan_is_applied_on_a_copy(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    seen = {}

    def fake(prompt, **kw):
        seen["p"] = prompt
        return ('{"ops": [{"op": "header", "rows": [0, 1], "why": "two title rows"}, {"op": "drop_blank", "columns": [4], "why": "subtotals"}],'
                ' "mapping": {}, "why": "merged titles"}', "groq")
    monkeypatch.setattr(api.agent, "complete", fake)
    r = api.dispatch("slot_read", {"kind": "productivity", "month": "ytd:2026-09", "paths": [str(_merged(tmp_path))]})
    x = api.dispatch("slot_repair", {"token": r["token"], "kind": "sales", "month": "ytd:2026-09", "use_ai": True})
    assert x["engine"] == "groq" and len(x["steps"]) == 2 and "Fortress" not in seen["p"]
    assert x["check"]["status"] in ("good", "warn")
