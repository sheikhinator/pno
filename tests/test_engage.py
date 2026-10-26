"""2.3: engagement surveys, recognition and month close."""

from __future__ import annotations

import base64
import random
import zipfile

import pytest

from pno import engage, importers
from pno.api import Api
from pno.db import Database

from po_fixture import make_po_workbook


def survey_csv(n_a=12, n_b=3, seed=3, enps=True) -> bytes:
    rnd = random.Random(seed)
    head = ["Timestamp", "Store", "Department", "I know what is expected of me", "My manager treats me with respect", "I am paid fairly"]
    if enps:
        head.append("How likely are you to recommend Carrefour (0-10)")
    head.append("Comments")
    lines = [",".join(head)]
    comments = ["Salary is late and too low", "Manager shouts at team", "Need transport at night shift", "", "Good place, want more training", ""]
    for i in range(n_a + n_b):
        store = "HM PK LAH Fortress" if i < n_a else "WTC"
        row = [f"2026-10-0{1 + i % 9}", store, "Fresh Food", str(rnd.choice([4, 5, 5, 3])), str(rnd.choice([2, 4, 5])), str(rnd.choice([1, 2, 3]))]
        if enps:
            row.append(str(rnd.choice([10, 9, 7, 3])))
        row.append('"' + comments[i % len(comments)] + '"')
        lines.append(",".join(row))
    return ("\n".join(lines)).encode()


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "pno.sqlite3")
    a = importers.analyze_path(make_po_workbook(tmp_path / "po.xlsx"))
    importers.commit(db, a, {"*": {"month": "2026-09", "as_of": "2026-09-30"}})
    return Api(db)


def test_parse_classifies_columns(tmp_path):
    p = tmp_path / "s.csv"
    p.write_bytes(survey_csv())
    r = engage.parse(engage._rows_from_file(str(p)))
    assert len(r["questions"]) == 3 and r["has_enps"] and r["has_store"] and r["has_dept"]
    assert len(r["answers"]) == 15 and any(a["comments"] for a in r["answers"])


def test_survey_results_respect_minimum_group(api):
    r = api.dispatch("survey_upload", {"files": [{"name": "Pulse Oct.csv", "b64": base64.b64encode(survey_csv()).decode()}], "wave": "2026-10"})
    assert r["added"] == 1 and r["has_data"] and r["survey"]["n"] == 15
    assert r["enps"] is not None and -100 <= r["enps"] <= 100
    assert all(0 <= q["favourable"] <= 100 and sum(q["dist"]) == q["n"] for q in r["questions"])
    stores = {s["name"]: s for s in r["stores"]}
    assert stores["LAH Fortress"]["hidden"] is False and stores["LAH Fortress"]["n"] == 12
    hidden = [s for s in r["stores"] if s["hidden"]]
    assert hidden and all("favourable" not in s for s in hidden)            # small groups never show scores
    themes = dict(r["themes"])
    assert themes.get("Pay") and themes.get("Manager") and themes.get("Facilities & transport")
    assert r["concerns"][0]["question"].startswith("I am paid")
    r2 = api.dispatch("survey_upload", {"files": [{"name": "Pulse Nov.csv", "b64": base64.b64encode(survey_csv(seed=9)).decode()}], "wave": "2026-11"})
    assert len(r2["trend"]) == 2 and r2["trend"][-1]["wave"] == "2026-11"
    assert len(api.dispatch("survey_delete", {"survey_id": r2["survey"]["id"]})["surveys"]) == 1


def test_bad_survey_file(api):
    r = api.dispatch("survey_upload", {"files": [{"name": "x.csv", "b64": base64.b64encode(b"Name,City\nA,B\nC,D").decode()}]})
    assert r["added"] == 0 and r["failed"]


def test_template_and_export(api, tmp_path):
    t = tmp_path / "t.xlsx"
    api.dispatch("survey_template", {"save_as": str(t), "open_after": False})
    import openpyxl
    ws = openpyxl.load_workbook(t)["Answers"]
    assert ws.max_column == 2 + len(engage.QUESTIONS) + 2
    api.dispatch("survey_upload", {"files": [{"name": "Pulse.csv", "b64": base64.b64encode(survey_csv()).decode()}]})
    for fmt in ("pdf", "docx", "xlsx"):
        out = tmp_path / f"e.{fmt}"
        r = api.dispatch("engagement_export", {"fmt": fmt, "save_as": str(out), "open_after": False})
        assert "error" not in r, r
        assert out.stat().st_size > 1000


def test_stars_and_certificates(api, tmp_path):
    s = api.dispatch("stars", {})
    assert s["stars"] and all(x["award"] and x["name"] for x in s["stars"])
    assert any(x["award"] == "Country champion" for x in s["stars"])
    out = tmp_path / "c.pdf"
    r = api.dispatch("certificates", {"people": s["stars"][:3], "period": "October 2026", "save_as": str(out), "open_after": False})
    assert r["n"] == 3
    from pypdf import PdfReader
    rd = PdfReader(str(out))
    assert len(rd.pages) == 3 and "RECOGNITION" in rd.pages[0].extract_text()


def test_month_close(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    api = Api(Database(tmp_path / "real.sqlite3"))
    api.dispatch("demo", {"on": True})
    month = api.dispatch("init", {})["month"]
    out = tmp_path / "close.zip"
    r = api.dispatch("month_close", {"month": month, "save_as": str(out), "open_after": False})
    assert "error" not in r, r
    names = zipfile.ZipFile(out).namelist()
    assert any(n.startswith("Stores/") for n in names) and "Data health.pdf" in names and any("Director" in n for n in names)
    assert month in api.dispatch("data_health", {"month": month}).get("locked_months", [month])
