"""Opening databases left by other versions of PNO."""

import sqlite3

from pno import importers
from pno.api import Api
from pno.db import APP_ID, Database

# The tables the earlier (Replit) PNO created in the same %LOCALAPPDATA%\PNO\pno.sqlite3
OLD_APP_SCHEMA = """
CREATE TABLE imports (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, period TEXT NOT NULL, source TEXT NOT NULL,
    checksum TEXT NOT NULL, sheet TEXT NOT NULL, created_at TEXT NOT NULL, count INTEGER NOT NULL, active INTEGER NOT NULL);
CREATE INDEX imports_active_scope ON imports(kind, period, sheet, active);
CREATE TABLE imported_records (id INTEGER PRIMARY KEY AUTOINCREMENT, import_id INTEGER NOT NULL, ordinal INTEGER NOT NULL,
    payload TEXT NOT NULL, UNIQUE(import_id, ordinal));
INSERT INTO imports(kind, period, source, checksum, sheet, created_at, count, active)
    VALUES('attendance', '2026-08', 'old.xlsx', 'abc', 'Sheet1', '2026-09-01', 1, 1);
PRAGMA user_version = 1;
"""


def test_old_app_database_is_kept_aside_and_imports_work(tmp_path, demo):
    path = tmp_path / "pno.sqlite3"
    old = sqlite3.connect(path)
    old.executescript(OLD_APP_SCHEMA)
    old.close()

    db = Database(path)
    assert "earlier version of PNO" in db.notice
    kept = list(tmp_path.glob("pno-previous-version-*.sqlite3"))
    assert len(kept) == 1
    k = sqlite3.connect(kept[0])
    assert k.execute("SELECT checksum FROM imports").fetchone()[0] == "abc"      # old data untouched
    k.close()

    a = importers.analyze_bytes(demo.files["Biometric Attendance MTD Sep 2026.xlsx"], "August BioMetric Attendance.xlsx")
    assert importers.commit(db, a)[0]["status"] == "ok"
    api = Api(db)
    init = api.dispatch("init", {})
    assert "earlier version" in init["notice"] and api.dispatch("init", {})["notice"] == ""   # shown once
    db.close()

    again = Database(path)                       # now ours: opened as is, nothing moved
    assert again.notice == "" and again.val("SELECT COUNT(*) FROM attendance") > 0
    assert again.val("PRAGMA application_id") == APP_ID
    assert len(list(tmp_path.glob("pno-previous-version-*.sqlite3"))) == 1
    again.close()


def test_own_database_without_marker_gets_missing_columns(tmp_path):
    path = tmp_path / "pno.sqlite3"
    db = Database(path)
    db.x("INSERT INTO holidays(day, name) VALUES('2026-09-01','x')")
    db.conn.execute("PRAGMA application_id = 0")
    db.conn.execute("ALTER TABLE sales DROP COLUMN store_raw")     # as if made before that column existed
    db.close()
    db = Database(path)
    assert db.notice == ""
    assert "store_raw" in {r[1] for r in db.q("PRAGMA table_info(sales)")}
    assert db.val("SELECT name FROM holidays") == "x"
    db.close()


def test_new_empty_file(tmp_path):
    db = Database(tmp_path / "new.sqlite3")
    assert db.notice == "" and db.val("PRAGMA application_id") == APP_ID
    db.close()
