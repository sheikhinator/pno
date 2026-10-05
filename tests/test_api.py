"""Every request the screens make, the way the screens make them."""

import base64

import pytest

from pno import engine
from pno.api import Api


def att(mm, emp):
    return mm.people[emp].att


def test_init_and_screens(api):
    init = api.dispatch("init", {})
    assert init["has_data"] and init["month"] == "2026-09"
    assert [m["value"] for m in init["months"]][:2] == ["2026-09", "2026-08"]
    for c in ("roster", "attendance", "productivity", "sales", "leave"):
        assert init["counts"][c] >= 1
    m = "2026-09"
    d = api.dispatch("dashboard", {"month": m, "scope": {}})
    assert "error" not in d
    assert api.dispatch("people", {"month": m})["rows"]
    st = api.dispatch("stores", {"month": m})["rows"]
    assert len(st) >= 12
    assert "error" not in api.dispatch("store", {"store_id": st[0]["store_id"], "month": m})
    assert "error" not in api.dispatch("attendance", {"month": m})
    assert "error" not in api.dispatch("org", {"month": m})
    emp = api.dispatch("people", {"month": m})["rows"][0]["emp"]
    p = api.dispatch("person", {"emp": emp, "month": m})
    assert "error" not in p
    assert len(api.dispatch("compare", {"emps": [emp, emp], "month": m})["people"]) == 2
    s = api.dispatch("search", {"q": "lucky", "month": m})
    assert s["stores"]


def test_unknown_request_is_a_readable_error(api):
    assert "Unknown request" in api.dispatch("drop_tables", {})["error"]
    assert api.dispatch("person", {"emp": "nobody", "month": "2026-09"}).get("error")


@pytest.mark.parametrize("scope", [{"city": "LAH"}, {"format": "SM"}, {"dept": "02"}, {"city": "KCH", "format": "HB"}])
def test_filters_narrow_everything(api, scope):
    m = "2026-09"
    allp = api.dispatch("people", {"month": m})["rows"]
    some = api.dispatch("people", {"month": m, "scope": scope})["rows"]
    assert 0 < len(some) < len(allp)
    d = api.dispatch("dashboard", {"month": m, "scope": scope})
    assert "error" not in d
    stores = api.dispatch("stores", {"month": m, "scope": scope})["rows"]
    if "city" in scope:
        assert all(r.get("city") in (scope["city"], None) or r.get("city_code", scope["city"]) == scope["city"] for r in stores)


def test_people_filters_and_sort(api):
    rows = api.dispatch("people", {"month": "2026-09", "role": "SM", "sort": "score", "desc": True})["rows"]
    assert rows and all(r["role"] == "SM" for r in rows)
    scores = [r["score"] for r in rows if r["score"] is not None]
    assert scores == sorted(scores, reverse=True)
    q = rows[0]["name"].split()[0]
    assert any(q in r["name"] for r in api.dispatch("people", {"month": "2026-09", "q": q})["rows"])


def test_hide_names(api):
    api.dispatch("settings_save", {"hide_names": True})
    rows = api.dispatch("people", {"month": "2026-09"})["rows"]
    assert all(r["name"].startswith("Employee ") for r in rows[:20])
    api.dispatch("settings_save", {"hide_names": False})


def test_upload_analyze_commit_undo_redo(api, demo, empty_db):
    a = Api(empty_db)
    files = [{"name": n, "b64": base64.b64encode(b).decode()} for n, b in demo.files.items() if "Sep" in n or "Employee" in n
             or "30-Sep" in n]
    sess = a.dispatch("import_upload", {"files": files})
    assert not sess["errors"] and len(sess["files"]) == len(files)
    out = a.dispatch("import_commit", {"token": sess["token"],
                                       "options": {"Employee Basic Details.xlsx": {"*": {"as_of": "2026-09-30"}}}})
    statuses = [r["status"] for f in out["done"] for r in f["results"]]
    assert statuses and set(statuses) == {"ok"}
    assert a.dispatch("init", {})["has_data"]
    imps = a.dispatch("imports", {})["rows"]
    att_imp = next(r for r in imps if r["kind"] == "attendance")
    a.dispatch("import_undo", {"import_id": att_imp["id"]})
    assert empty_db.val("SELECT COUNT(*) FROM attendance") == 0
    a.dispatch("import_redo", {"import_id": att_imp["id"]})
    assert empty_db.val("SELECT COUNT(*) FROM attendance") > 1000
    with pytest.raises(Exception):
        raise RuntimeError(a.dispatch("import_commit", {"token": sess["token"]})["error"])   # expired preview


def test_import_analyze_paths_and_bad_file(api, tmp_path, demo):
    good = tmp_path / "MTD Productivity Sep 2026.xlsx"
    good.write_bytes(demo.files["MTD Productivity Sep 2026.xlsx"])
    bad = tmp_path / "missing.xlsx"
    r = api.dispatch("import_analyze", {"paths": [str(good), str(bad)]})
    assert len(r["files"]) == 1 and len(r["errors"]) == 1
    assert r["files"][0]["results"][0]["kind"] == "productivity"


def test_leave_changes_absence_and_can_be_deleted(api, db):
    mm = engine.model(db, "2026-09")
    p = next(p for p in mm.people.values() if p.att and p.att["absent"] > 0 and p.att["calendar"])
    absent_day = next(c["day"] for c in p.att["calendar"] if c["kind"] == "absent")
    before = p.att["absent"]
    r = api.dispatch("leave_add", {"emp": p.emp, "d_from": absent_day, "type": "Sick Leave"})
    assert r["ok"]
    after = engine.model(db, "2026-09").people[p.emp].att
    assert after["absent"] == before - 1 and after["leave"] >= 1
    rows = api.dispatch("leaves", {"month": "2026-09", "emp": p.emp})["rows"]
    lid = next(x["id"] for x in rows if x["d_from"] == absent_day)
    api.dispatch("leave_delete", {"leave_id": lid})
    assert engine.model(db, "2026-09").people[p.emp].att["absent"] == before
    assert "not in the imported data" in api.dispatch("leave_add", {"emp": "999", "d_from": "2026-09-01"})["error"]


def test_holiday_add_delete_and_defaults(api, db):
    mm = engine.model(db, "2026-09")
    p = next(p for p in mm.people.values() if p.att and any(c["kind"] == "absent" for c in p.att["calendar"]))
    day = next(c["day"] for c in p.att["calendar"] if c["kind"] == "absent")
    api.dispatch("holiday_add", {"day": day, "name": "Test Holiday"})
    assert engine.model(db, "2026-09").people[p.emp].att["absent"] == p.att["absent"] - 1
    assert any(h["day"] == day for h in api.dispatch("holidays", {"year": 2026})["rows"])
    api.dispatch("holiday_delete", {"day": day})
    assert api.dispatch("holiday_add", {"day": "not a date", "name": "x"}).get("error")
    assert api.dispatch("holidays_defaults", {"year": 2027})["added"] >= 1


def test_settings_save_validate_reset(api, db):
    s = api.dispatch("settings", {})
    assert s["weights"]["GM"] and s["rules"]["full_day_minutes"] == 540
    assert "error" in api.dispatch("settings_save", {"weights": {"SM": {"sales": 0}}})
    api.dispatch("settings_save", {"rules": {"full_day_minutes": 480, "bogus": 1}})
    s = api.dispatch("settings", {})
    assert s["rules"]["full_day_minutes"] == 480 and "bogus" not in s["rules"]
    api.dispatch("settings_reset", {})
    assert api.dispatch("settings", {})["rules"]["full_day_minutes"] == 540


def test_store_alias_split_and_merge_back(api, db):
    lst = api.dispatch("store_list", {})
    alias = next(a for a in lst["aliases"] if a["raw"].startswith("HB PK KCH"))        # the BO name of an H&B store
    home = alias["store_id"]
    n_home = db.val("SELECT COUNT(*) FROM sales WHERE store_id=?", (home,))
    r = api.dispatch("store_new", {"alias": alias["alias"]})                          # split it into its own store
    assert db.val("SELECT COUNT(*) FROM sales WHERE store_id=?", (r["store_id"],)) == n_home
    assert db.val("SELECT COUNT(*) FROM sales WHERE store_id=?", (home,)) == 0
    assert api.dispatch("store_alias_set", {"alias": alias["alias"], "store_id": home})["ok"]   # and merge it back
    assert db.val("SELECT COUNT(*) FROM sales WHERE store_id=?", (home,)) == n_home
    assert not db.q1("SELECT 1 FROM stores WHERE id=?", (r["store_id"],))           # the empty store is removed
    api.dispatch("store_update", {"store_id": home, "name": "Renamed Store"})
    assert db.val("SELECT name FROM stores WHERE id=?", (home,)) == "Renamed Store"


def test_store_alias_clash_is_refused_and_nothing_changes(api, db):
    lst = api.dispatch("store_list", {})
    alias = next(a for a in lst["aliases"] if a["raw"].startswith("HB PK KCH"))
    other = next(s for s in lst["stores"] if s["id"] != alias["store_id"] and s["format"] == "HB")
    r = api.dispatch("store_alias_set", {"alias": alias["alias"], "store_id": other["id"]})
    assert "two different stores" in r["error"]
    assert db.val("SELECT store_id FROM store_aliases WHERE alias=?", (alias["alias"],)) == alias["store_id"]


def test_section_map_and_manager_override(api, db):
    rows = api.dispatch("section_map", {})["rows"]
    assert rows
    key = rows[0]["key"]
    api.dispatch("section_map_set", {"key": key, "codes": ["S011"]})
    assert next(r for r in api.dispatch("section_map", {})["rows"] if r["key"] == key)["overridden"]
    api.dispatch("section_map_set", {"key": key, "reset": True})
    mm = engine.model(db, "2026-09")
    staff = next(p for p in mm.people.values() if p.role == "STAFF")
    boss = next(p for p in mm.people.values() if p.role == "GM")
    api.dispatch("manager_set", {"emp": staff.emp, "manager_emp": boss.emp})
    assert engine.model(db, "2026-09").people[staff.emp].manager_emp == boss.emp


def test_notes(api, db):
    emp = next(iter(engine.model(db, "2026-09").people))
    r = api.dispatch("note_add", {"emp": emp, "text": "Discussed punctuality"})
    assert r["ok"]
    p = api.dispatch("person", {"emp": emp, "month": "2026-09"})
    assert any("punctuality" in n["text"] for n in p.get("notes", []))
    api.dispatch("note_delete", {"note_id": p["notes"][0]["id"]})


def test_backup_restore(api, db, tmp_path):
    class H:
        def save_path(self, name, filt=""):
            d = tmp_path / "HR #1 100% backups"           # the kind of folder names people really use
            return str(d / name)

        def pick_files(self, kind="reports"):
            return []

        def open_path(self, p):
            pass
    api.host = H()
    r = api.dispatch("backup", {})
    assert r["ok"]
    n = db.val("SELECT COUNT(*) FROM roster")
    db.x("DELETE FROM roster")
    api.dispatch("restore", {"path": r["path"]})
    assert db.val("SELECT COUNT(*) FROM roster") == n


def test_demo_switch(api):
    r = api.dispatch("demo", {"on": True})
    assert r["demo"] and r["has_data"]
    r = api.dispatch("demo", {"on": False})
    assert not r["demo"]


def test_audit_log(api):
    api.dispatch("holiday_add", {"day": "2026-12-31", "name": "Audit"})
    assert any(r["action"] == "holiday" for r in api.dispatch("audit", {})["rows"])
