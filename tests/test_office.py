"""3.0: backups, synonyms, HR calendar, weekly brief, store visits, glossary, Smart Import for NPS / productivity / shrinkage, NPS in the leader index."""
import os
from pno import importers, office
from pno.api import Api, load_demo
from pno.db import Database
from pno.smart import schema


def _api(tmp_path, monkeypatch):
    monkeypatch.setenv("PNO_HOME", str(tmp_path / "home"))
    db = Database(tmp_path / "p.sqlite3"); load_demo(db); a = Api(db); a.dispatch("init", {})
    return a


def test_office(tmp_path, monkeypatch):
    a = _api(tmp_path, monkeypatch)
    assert office.auto_backup(a.db) and office.auto_backup(a.db) is None          # once a day
    assert len(a.dispatch("backups", {})["rows"]) == 1
    c = a.dispatch("hr_calendar", {"month": "2026-10"})
    assert len(c["days"]) == 31 and c["counts"].get("anniversary")
    b = a.dispatch("weekly_brief", {})
    assert b["sections"] and "% of budget" in b["text"]
    for fmt in ("pdf", "docx"):
        p = str(tmp_path / f"brief.{fmt}")
        assert a.dispatch("weekly_brief_export", {"fmt": fmt, "save_as": p, "open_after": False})["ok"] and os.path.getsize(p) > 1000
    st = a.dispatch("visit_template", {"store": ""})["stores"][0]
    r = a.dispatch("visit_save", {"store": st, "answers": {"x": "ok", "y": "issue"}, "actions": ["Fix it", ""]})
    assert r["score"] == 50 and r["actions"] == 1
    assert a.dispatch("explain", {"term": "Pattern absence"})["term"] == "bradford"
    assert a.dispatch("explain", {"term": "Leader index"})["term"] == "leader index"


def test_synonyms(tmp_path, monkeypatch):
    a = _api(tmp_path, monkeypatch)
    assert schema.header_score("Mulazim Code", "employee_id") < 0.9
    a.dispatch("synonyms_save", {"field": "employee_id", "words": ["Mulazim Code"]})
    assert schema.header_score("Mulazim Code", "employee_id") == 1.0
    a.dispatch("synonyms_save", {"field": "employee_id", "words": []})
    assert schema.header_score("Mulazim Code", "employee_id") < 0.9


def test_smart_new_kinds(tmp_path):
    files = {"cx.csv": "Region,Category,Score,Year\nLahore,Bakery,45,2026\nLahore,Butchery,38,2026\nKarachi,Bakery,52,2026\n",
             "prod.csv": "Branch,Dept,Sales per hour,Target SPH\nLAH Fortress,Bakery,5200,5000\nKCH Lucky One,Total Store,4100,4500\nISL WTC,Bakery,5000,5200\n",
             "shr.csv": "Store,Section,Shrinkage %,Shrink Budget,Stock Days,Stock Days Budget\nLAH Fortress,Bakery,-0.8,-0.5,12,10\nISL WTC,Deli,-0.3,-0.4,9,10\n"}
    want = {"cx.csv": "po_nps", "prod.csv": "productivity", "shr.csv": "po_shrink"}
    for n, t in files.items():
        p = tmp_path / n; p.write_text(t)
        res = importers.analyze_path(p)["results"]
        assert res and res[0].kind == want[n], (n, [r.kind for r in res])
    shr = importers.analyze_path(tmp_path / "shr.csv")["results"][0].rows[0]
    assert shr["shrink_variance_pct"] == -0.3


def test_nps_in_leader_index(tmp_path, monkeypatch):
    a = _api(tmp_path, monkeypatch)
    ins = a._po()
    scored = [l for l in ins.leaders() if "nps" in l.components]
    assert scored and all(0 <= l.components["nps"] <= 100 for l in scored)
    assert a.dispatch("po_weights", {})["weights"]["nps"] == 10
