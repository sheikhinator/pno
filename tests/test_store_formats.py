"""2.4 fix: H&B (Myli) stores must never be merged into the hypermarket of the same name."""

from __future__ import annotations

from pno.api import Api
from pno.db import Database
from pno.stores import StoreResolver, repair_formats


def test_hb_store_is_separate_even_after_productivity(tmp_path):
    db = Database(tmp_path / "p.sqlite3")
    r = StoreResolver(db, "test")
    prod = r.resolve("656 LAH Packages")                      # productivity: no format
    hm = r.resolve("HM PK LAH Packages Mall")
    hb = r.resolve("H&B PK LAH Packages Mall")
    myli = r.resolve("HB PK LAH H&B PAK LAH EMP (MYLI)")
    emp = r.resolve("HM PK LAH Emporium Mall")
    assert prod == hm and hb != hm and myli != emp
    assert db.q1("SELECT format FROM stores WHERE id=?", (hb,))[0] == "HB"
    assert db.q1("SELECT name FROM stores WHERE id=?", (myli,))[0] == "Emporium Mall"


def test_known_store_spellings_are_one_store(tmp_path):
    db = Database(tmp_path / "p.sqlite3")
    r = StoreResolver(db, "test")
    assert r.resolve("661 ISL D12 (P06)") == r.resolve("SM PK ISL DIZ MARKAZ") == r.resolve("SM PK ISL D12 (P06)")
    assert r.resolve("PK HM GUJ Steel Casting") == r.resolve("STC-Gujranwala") == r.resolve("657 GUJ Steel Casting")
    assert r.resolve("652 LAH High Street Paragon Ci") == r.resolve("SM PK LAH PARAGON")
    assert r.resolve("660 LAH Askari 10") != r.resolve("660 LAH Emporium Mall")


def test_repair_splits_old_merged_stores(tmp_path):
    db = Database(tmp_path / "p.sqlite3")
    sid = db.x("INSERT INTO stores(key, name, format, city, code, is_ho) VALUES('|LAH|PACKAGES','Packages Mall','HM','LAH','656',0)").lastrowid
    for alias, raw in (("656 LAH PACKAGES", "656 LAH Packages"), ("HM PK LAH PACKAGES MALL", "HM PK LAH Packages Mall"),
                       ("H AND B PK LAH PACKAGES MALL", "H&B PK LAH Packages Mall")):
        db.x("INSERT INTO store_aliases(alias, raw, store_id, confirmed, source) VALUES(?,?,?,1,'x')", (alias, raw, sid))
    fixed = repair_formats(db)
    assert fixed
    hb = db.q1("SELECT store_id FROM store_aliases WHERE alias='H AND B PK LAH PACKAGES MALL'")[0]
    assert hb != sid and db.q1("SELECT format FROM stores WHERE id=?", (hb,))[0] == "HB"
    assert db.q1("SELECT key FROM stores WHERE id=?", (sid,))[0] == "HM|LAH|PACKAGES"
    # Api start-up runs the repair once and tells the user to re-import sales
    db.set_setting("repair_stores_v2", None)
    api = Api(db)
    assert api.dispatch("init", {}).get("notice") is not None
