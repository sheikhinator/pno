"""The local SQLite database. Every imported row keeps the import it came from, so any import can be undone."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .paths import db_path

SCHEMA_VERSION = 1
APP_ID = 0x504E4F31        # 'PNO1' in the file header: marks databases made by this version of PNO

SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                 -- roster | attendance | productivity | sales | leave | holiday | manual
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    month TEXT,                         -- YYYY-MM the data belongs to (roster: as-of month)
    as_of TEXT,                         -- YYYY-MM-DD the data is valid to
    rows INTEGER NOT NULL DEFAULT 0,
    summary TEXT,
    warnings TEXT,                      -- JSON list
    source TEXT NOT NULL DEFAULT 'file',  -- file | paste | agent | manual
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS imports_kind ON imports(kind, active);

CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,           -- FORMAT|CITY|NAME
    name TEXT NOT NULL,                 -- display name, e.g. 'Lyallpur Galleria'
    format TEXT NOT NULL DEFAULT '',    -- HM | SM | HB | HO | ''
    city TEXT NOT NULL DEFAULT '',      -- LAH | KCH | ISL | FAI | GUJ ...
    code TEXT NOT NULL DEFAULT '',      -- productivity store number, e.g. 663
    is_ho INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS store_aliases (
    alias TEXT PRIMARY KEY,             -- normalised name as written in a report
    raw TEXT NOT NULL,
    store_id INTEGER NOT NULL REFERENCES stores(id),
    confirmed INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS roster (
    import_id INTEGER NOT NULL,
    emp_no TEXT NOT NULL,
    name TEXT NOT NULL,
    store_id INTEGER,
    bu_raw TEXT,
    dept_code TEXT,
    dept_name TEXT,
    section_raw TEXT,
    designation TEXT,
    grade TEXT,
    gender TEXT,
    manager_name TEXT,
    PRIMARY KEY (import_id, emp_no)
);

CREATE TABLE IF NOT EXISTS attendance_all (
    import_id INTEGER NOT NULL,
    emp_no TEXT NOT NULL,
    day TEXT NOT NULL,
    store_id INTEGER,
    t_in TEXT, t_out TEXT,
    minutes INTEGER,
    wh_raw TEXT,
    status TEXT NOT NULL,
    PRIMARY KEY (import_id, emp_no, day)
);
CREATE INDEX IF NOT EXISTS att_all_key ON attendance_all(emp_no, day, import_id);
CREATE TABLE IF NOT EXISTS attendance (       -- the current view: latest active import per person per day
    emp_no TEXT NOT NULL,
    day TEXT NOT NULL,
    store_id INTEGER,
    t_in TEXT, t_out TEXT,
    minutes INTEGER,
    wh_raw TEXT,
    status TEXT NOT NULL,
    import_id INTEGER NOT NULL,
    PRIMARY KEY (emp_no, day)
);
CREATE INDEX IF NOT EXISTS att_day ON attendance(day);
CREATE TABLE IF NOT EXISTS att_people (       -- per person and month: details the attendance file carries
    import_id INTEGER NOT NULL,
    emp_no TEXT NOT NULL,
    month TEXT NOT NULL,
    name TEXT, store_id INTEGER, bu_raw TEXT, section_raw TEXT, designation TEXT, joining_date TEXT,
    sys_absent INTEGER, sys_present INTEGER,
    PRIMARY KEY (import_id, emp_no, month)
);

CREATE TABLE IF NOT EXISTS sales (
    import_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    store_raw TEXT,
    month TEXT NOT NULL,
    period TEXT NOT NULL,               -- MTD | DAY
    as_of TEXT NOT NULL,
    level TEXT NOT NULL,                -- section | subgroup | dept | food | store | consignment | total
    code TEXT NOT NULL,                 -- S011, D01, FOOD, NONFOOD, STORE, ...
    name TEXT,
    dept TEXT,                          -- 01..05 for sections and departments
    actual REAL, budget REAL, growth REAL, ly REAL, var_pct REAL,
    weight REAL, customers REAL, cust_growth REAL, penetration REAL, items REAL,
    avg_basket REAL, asp REAL, margin REAL, waste REAL, margin_net REAL, avg_stock REAL, oos REAL,
    PRIMARY KEY (import_id, store_id, period, as_of, code)
);
CREATE INDEX IF NOT EXISTS sales_key ON sales(store_id, month, period, as_of);

CREATE TABLE IF NOT EXISTS productivity (
    import_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    store_raw TEXT,
    month TEXT NOT NULL,
    row_code TEXT NOT NULL,             -- STORE | CCO | D01 | S054 | S050+S051 | OTHER
    row_name TEXT,
    level TEXT,
    actual REAL, ly REAL, target REAL, forecast REAL,
    PRIMARY KEY (import_id, store_id, row_code)
);
CREATE INDEX IF NOT EXISTS prod_key ON productivity(store_id, month);

CREATE TABLE IF NOT EXISTS leaves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_no TEXT NOT NULL,
    d_from TEXT NOT NULL,
    d_to TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'Leave',
    note TEXT,
    import_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS leaves_emp ON leaves(emp_no, d_from);

CREATE TABLE IF NOT EXISTS holidays (
    day TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    import_id INTEGER
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_no TEXT NOT NULL,
    day TEXT,
    text TEXT NOT NULL,
    import_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ro_uri(path: str | Path) -> str:
    """A read-only SQLite URI that works for any Windows path (spaces, #, %, ?)."""
    return Path(path).resolve().as_uri() + "?mode=ro"


class Database:
    """One connection shared by the app's worker threads, serialised by a lock. WAL keeps reads fast."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.notice = ""          # shown once on the screen (e.g. an older PNO database was set aside)
        self.conn = self._open()
        if self._foreign():
            # A database left by an earlier, different PNO (same folder, other tables). Keep it untouched beside
            # the new one and start fresh, instead of failing on every import.
            self.conn.close()
            moved = self.path.with_name(f"pno-previous-version-{datetime.now():%Y%m%d-%H%M%S}.sqlite3")
            self.path.replace(moved)
            for ext in ("-wal", "-shm"):
                side = Path(str(self.path) + ext)
                if side.exists():
                    side.replace(Path(str(moved) + ext))
            self.notice = (f"A database from an earlier version of PNO was found and kept as '{moved.name}' in "
                           f"{moved.parent}. PNO started with a fresh database: please import your reports again.")
            self.conn = self._open()
        self._add_missing_columns()
        self.conn.executescript(SCHEMA)
        v = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if v > SCHEMA_VERSION:
            raise RuntimeError("This database was made by a newer version of PNO. Please update PNO.")
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.execute(f"PRAGMA application_id = {APP_ID}")
        self.version = 0          # bumped on every write; caches use it

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=OFF")
        return conn

    def _foreign(self) -> bool:
        """True when the file holds tables but was not made by this PNO (and does not look like its schema)."""
        if self.conn.execute("PRAGMA application_id").fetchone()[0] == APP_ID:
            return False
        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables - {"sqlite_sequence"}:
            return False                                   # empty / brand new file
        if "imports" in tables:
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(imports)")}
            if {"file_hash", "kind", "active"} <= cols and "roster" in tables:
                return False                               # this PNO's schema, made before the marker existed
        return True

    def _add_missing_columns(self) -> None:
        """Bring an existing PNO database up to the current tables (new columns are added, nothing is removed)."""
        ref = sqlite3.connect(":memory:")
        try:
            ref.executescript(SCHEMA)
            for (table,) in ref.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                have = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
                if not have:
                    continue                               # a new table: created by the schema below
                for _, name, typ, _nn, default, _pk in ref.execute(f"PRAGMA table_info({table})"):
                    if name not in have:
                        d = f" DEFAULT {default}" if default is not None else ""
                        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}{d}")
        finally:
            ref.close()

    # ---------------------------------------------------------------- basics
    def q(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    def q1(self, sql: str, params: Iterable[Any] = ()):
        with self.lock:
            return self.conn.execute(sql, tuple(params)).fetchone()

    def val(self, sql: str, params: Iterable[Any] = (), default=None):
        r = self.q1(sql, params)
        return default if r is None or r[0] is None else r[0]

    def x(self, sql: str, params: Iterable[Any] = ()):
        with self.lock:
            cur = self.conn.execute(sql, tuple(params))
            self.version += 1
            return cur

    def xmany(self, sql: str, rows: Iterable[Iterable[Any]]):
        with self.lock:
            self.conn.executemany(sql, rows)
            self.version += 1

    def tx(self):
        db = self

        class _Tx:
            def __enter__(self):
                db.lock.acquire()
                db.conn.execute("BEGIN IMMEDIATE")
                return db

            def __exit__(self, et, ev, tb):
                try:
                    if et is None:
                        db.conn.execute("COMMIT")
                    else:
                        db.conn.execute("ROLLBACK")
                finally:
                    db.version += 1
                    db.lock.release()
                return False

        return _Tx()

    # ---------------------------------------------------------------- settings
    def get_setting(self, key: str, default=None):
        r = self.q1("SELECT value FROM settings WHERE key=?", (key,))
        if r is None:
            return default
        try:
            return json.loads(r[0])
        except ValueError:
            return default

    def set_setting(self, key: str, value) -> None:
        self.x("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, json.dumps(value)))

    def log(self, action: str, detail: str = "") -> None:
        self.x("INSERT INTO audit(ts, action, detail) VALUES(?,?,?)", (now(), action, detail))

    # ---------------------------------------------------------------- attendance view
    def rebuild_attendance(self, days: tuple[str, str] | None = None) -> None:
        """Recompute the current attendance from the active imports (latest import wins for each person and day)."""
        where, params = "", []
        if days:
            where, params = "WHERE day BETWEEN ? AND ?", list(days)
        with self.lock:
            self.conn.execute(f"DELETE FROM attendance {where}", params)
            self.conn.execute(f"""
                INSERT INTO attendance(emp_no, day, store_id, t_in, t_out, minutes, wh_raw, status, import_id)
                SELECT a.emp_no, a.day, a.store_id, a.t_in, a.t_out, a.minutes, a.wh_raw, a.status, a.import_id
                FROM attendance_all a
                JOIN (SELECT b.emp_no, b.day, MAX(b.import_id) AS mid FROM attendance_all b
                      JOIN imports i ON i.id=b.import_id AND i.active=1
                      {where.replace('day', 'b.day')} GROUP BY b.emp_no, b.day) last
                  ON last.emp_no=a.emp_no AND last.day=a.day AND last.mid=a.import_id
            """, params)
            self.version += 1

    def backup(self, dest: str | Path) -> None:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            target = sqlite3.connect(str(dest))
            try:
                self.conn.backup(target)
            finally:
                target.close()

    def restore(self, src: str | Path) -> None:
        src = Path(src)
        test = sqlite3.connect(ro_uri(src), uri=True)
        try:
            if test.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("The backup file is damaged.")
            names = {r[0] for r in test.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"imports", "roster", "attendance", "sales"} <= names:
                raise ValueError("This file is not a PNO backup.")
            with self.lock:
                self.backup(self.path.with_name(f"pno-before-restore-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"))
                test.backup(self.conn)
                self.conn.executescript(SCHEMA)
                self.version += 1
        finally:
            test.close()

    def close(self) -> None:
        with self.lock:
            self.conn.close()
