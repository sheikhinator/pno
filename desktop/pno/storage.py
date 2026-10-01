"""Local, transactional SQLite storage for imported PNO snapshots."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from functools import wraps
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _serialized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def _dimension_value(record: dict, key: str) -> str | None:
    value = record.get(key)
    if value is None or not str(value).strip():
        return None
    return str(value).strip().casefold()


def _observation_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        pass
    for fmt in ("%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.strptime(text, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        return None


def _batch_coverage(kind: str, period: str, records: list[dict]) -> dict:
    """Build exact observation keys, retaining uncertain rows for fail-closed checks."""
    keys: set[tuple] = set()
    unknown: set[tuple] = set()
    for record in records:
        scope_values = tuple(
            _dimension_value(record, key) for key in ("store", "department", "section")
        )
        scope = scope_values if any(value is not None for value in scope_values) else None
        employee_id = _dimension_value(record, "employee_id")

        if kind == "attendance":
            identity = employee_id
            observed = _observation_date(record.get("date"))
            needs_scope = True
        elif kind == "roster":
            identity = employee_id
            observed = _observation_date(record.get("date")) or _observation_date(period)
            needs_scope = False
            scope = None
        elif kind in {"sales_mtd", "productivity"}:
            identity = None
            observed = _observation_date(record.get("date")) or _observation_date(period)
            needs_scope = True
        else:
            identity = None
            observed = _observation_date(record.get("date"))
            needs_scope = True

        identity_required = kind in {"attendance", "roster"}
        if observed is not None and (identity is not None or not identity_required):
            if not needs_scope or scope is not None:
                keys.add((scope, identity, observed))
                continue
        unknown.add((scope, identity))

    return {"keys": keys, "unknown": unknown, "complete": bool(records) and not unknown}


def _unknown_matches_key(marker: tuple, key: tuple) -> bool:
    marker_scope, marker_identity = marker
    key_scope, key_identity, _ = key
    return (
        (marker_scope is None or marker_scope == key_scope)
        and (marker_identity is None or marker_identity == key_identity)
    )


def _coverage_overlaps(left: dict, right: dict) -> bool:
    if left["keys"] & right["keys"]:
        return True
    if any(_unknown_matches_key(marker, key) for marker in left["unknown"] for key in right["keys"]):
        return True
    if any(_unknown_matches_key(marker, key) for marker in right["unknown"] for key in left["keys"]):
        return True
    return any(
        (left_scope is None or right_scope is None or left_scope == right_scope)
        and (left_identity is None or right_identity is None or left_identity == right_identity)
        for left_scope, left_identity in left["unknown"]
        for right_scope, right_identity in right["unknown"]
    )


def _safe_replacement_coverage(new: dict, old: dict) -> bool:
    return new["complete"] and old["complete"] and old["keys"].issubset(new["keys"])


class DuplicateImportError(ValueError):
    """Raised when an identical active import is submitted again."""


class ConflictImportError(ValueError):
    """Raised when an active batch already occupies the requested scope."""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        if str(path) == ":memory:":
            raise ValueError("Store requires a file-backed SQLite path.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _lock_for(self.path)
        self._initialize()

    @staticmethod
    def default_path() -> Path:
        override = os.environ.get("PNO_DATA_DIR")
        if override:
            data_dir = Path(override).expanduser()
        elif os.name == "nt":
            data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "PNO"
        elif os.uname().sysname == "Darwin":
            data_dir = Path.home() / "Library/Application Support/PNO"
        else:
            data_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "pno"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "pno.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                period TEXT NOT NULL,
                source TEXT NOT NULL,
                checksum TEXT NOT NULL,
                sheet TEXT NOT NULL,
                created_at TEXT NOT NULL,
                count INTEGER NOT NULL CHECK (count >= 0),
                active INTEGER NOT NULL CHECK (active IN (0, 1))
            );
            CREATE INDEX IF NOT EXISTS imports_active_scope
                ON imports(kind, period, sheet, active);
            CREATE INDEX IF NOT EXISTS imports_checksum
                ON imports(checksum, sheet, kind, period, active);
            CREATE TABLE IF NOT EXISTS imported_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id INTEGER NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE(import_id, ordinal)
            );
            CREATE INDEX IF NOT EXISTS records_batch ON imported_records(import_id, ordinal);
            """
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @_serialized
    def _initialize(self) -> None:
        try:
            connection = self._connect()
            try:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version > SCHEMA_VERSION:
                    raise RuntimeError(
                        f"Database schema version {version} is newer than supported version {SCHEMA_VERSION}."
                    )
                if version == 0:
                    self._create_schema(connection)
                else:
                    tables = {
                        row[0] for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }
                    if not {"imports", "imported_records"}.issubset(tables):
                        raise RuntimeError("The selected database has an unsupported or incomplete schema.")
            finally:
                connection.close()
            self._validate_database(self.path)
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"Could not initialize PNO database {self.path}: {exc}") from exc

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        raise TypeError(f"Record value {type(value).__name__} is not JSON serializable.")

    @_serialized
    def import_records(
        self,
        kind: str,
        period: str,
        records: Iterable[dict],
        source: str,
        checksum: str,
        sheet: str,
        replace: bool = False,
    ) -> int:
        if not all(isinstance(value, str) and value.strip() for value in (kind, period, source, checksum, sheet)):
            raise ValueError("kind, period, source, checksum and sheet must be non-empty strings.")
        materialized = list(records)
        if any(not isinstance(record, dict) for record in materialized):
            raise TypeError("Every imported record must be a dictionary.")
        payloads = [
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=self._json_default)
            for record in materialized
        ]
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                """
                SELECT id FROM imports
                WHERE active=1 AND kind=? AND period=? AND sheet=? AND checksum=?
                LIMIT 1
                """,
                (kind, period, sheet, checksum),
            ).fetchone()
            if duplicate:
                raise DuplicateImportError(
                    f"An identical active {kind} import for {period} on sheet {sheet!r} already exists."
                )
            active_batches = connection.execute(
                """
                SELECT i.id, i.sheet, i.period, r.payload
                FROM imports i
                LEFT JOIN imported_records r ON r.import_id=i.id
                WHERE i.active=1 AND i.kind=?
                ORDER BY i.id, r.ordinal
                """,
                (kind,),
            ).fetchall()
            grouped: dict[int, dict] = {}
            for row in active_batches:
                batch = grouped.setdefault(
                    row["id"],
                    {
                        "id": row["id"],
                        "sheet": row["sheet"],
                        "period": row["period"],
                        "records": [],
                    },
                )
                if row["payload"] is not None:
                    batch["records"].append(json.loads(row["payload"]))
            incoming_coverage = _batch_coverage(kind, period, materialized)
            conflicts = []
            for batch in grouped.values():
                old_coverage = _batch_coverage(kind, batch["period"], batch["records"])
                if _coverage_overlaps(incoming_coverage, old_coverage):
                    conflicts.append((batch, old_coverage))
            if conflicts and not replace:
                raise ConflictImportError(
                    f"An active {kind} import for {period} overlaps this business coverage "
                    f"(source table {conflicts[0][0]['sheet']!r}); confirm a safe correction."
                )
            if conflicts:
                unsafe = [
                    batch["sheet"]
                    for batch, old_coverage in conflicts
                    if not _safe_replacement_coverage(incoming_coverage, old_coverage)
                ]
                if unsafe:
                    raise ConflictImportError(
                        "Cannot safely replace this batch: incoming records do not cover every "
                        "prior observation key or contain an unknown observation date or identity. "
                        "Import the complete prior coverage; the active batch was left unchanged."
                    )
                connection.executemany(
                    "UPDATE imports SET active=0 WHERE id=?",
                    [(batch["id"],) for batch, _ in conflicts],
                )
            cursor = connection.execute(
                """
                INSERT INTO imports(kind, period, source, checksum, sheet, created_at, count, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (kind, period, source, checksum, sheet, created_at, len(payloads)),
            )
            import_id = int(cursor.lastrowid)
            connection.executemany(
                "INSERT INTO imported_records(import_id, ordinal, payload) VALUES (?, ?, ?)",
                [(import_id, index, payload) for index, payload in enumerate(payloads)],
            )
            connection.commit()
            return import_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @_serialized
    def list_imports(self) -> list[dict]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, kind, period, source, checksum, sheet, created_at, count, active
                FROM imports ORDER BY id DESC
                """
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "period": row["period"],
                    "source": row["source"],
                    "checksum": row["checksum"],
                    "sheet": row["sheet"],
                    "created_at": row["created_at"],
                    "count": row["count"],
                    "active": bool(row["active"]),
                }
                for row in rows
            ]
        finally:
            connection.close()

    @staticmethod
    def _date_key(value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            pass
        for fmt in ("%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m"):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.strftime("%Y-%m") if fmt == "%Y-%m" else parsed.date().isoformat()
            except ValueError:
                continue
        return text

    @_serialized
    def records(
        self,
        kind: str | None = None,
        period_from: str | None = None,
        period_to: str | None = None,
        store: str | None = None,
        department: str | None = None,
        section: str | None = None,
        employee: str | None = None,
    ) -> list[dict]:
        clauses = ["i.active=1"]
        parameters: list[Any] = []
        if kind:
            clauses.append("i.kind=?")
            parameters.append(kind)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT r.payload, i.id AS import_id, i.kind, i.period, i.source, i.sheet
                FROM imported_records r
                JOIN imports i ON i.id=r.import_id
                WHERE {' AND '.join(clauses)}
                ORDER BY i.period, i.id, r.ordinal
                """,
                parameters,
            ).fetchall()
            from_key = self._date_key(period_from) if period_from else None
            to_key = self._date_key(period_to) if period_to else None
            if to_key and len(to_key) == 7 and to_key[4] == "-":
                to_key = f"{to_key}-99"
            result: list[dict] = []
            for row in rows:
                record = json.loads(row["payload"])
                record_period = self._date_key(record.get("date")) or self._date_key(row["period"])
                if from_key and (record_period is None or record_period < from_key):
                    continue
                if to_key and (record_period is None or record_period > to_key):
                    continue
                for key, expected in (
                    ("store", store), ("department", department), ("section", section)
                ):
                    if expected is not None and str(record.get(key, "")) != str(expected):
                        break
                else:
                    if employee is not None and str(employee) not in {
                        str(record.get("employee_id", "")),
                        str(record.get("employee_name", "")),
                    }:
                        continue
                    record.update(
                        {
                            "_period": row["period"],
                            "_import_id": row["import_id"],
                            "_kind": row["kind"],
                            "_source": row["source"],
                            "_sheet": row["sheet"],
                        }
                    )
                    result.append(record)
            return result
        finally:
            connection.close()

    def dimensions(self) -> dict[str, list[str]]:
        active_records = self.records()
        output: dict[str, list[str]] = {}
        for dimension in ("store", "department", "section"):
            values = {
                str(record[dimension]).strip()
                for record in active_records
                if record.get(dimension) is not None and str(record[dimension]).strip()
            }
            output[{"store": "stores", "department": "departments", "section": "sections"}[dimension]] = sorted(
                values, key=str.casefold
            )
        return output

    def employees(self, period: str | None = None) -> list[dict]:
        roster = self.records(kind="roster")
        if period is not None:
            as_of = self._date_key(period) or str(period)
            roster = [
                record for record in roster
                if (self._date_key(record.get("_period")) or str(record.get("_period", ""))) <= as_of
            ]
        snapshots: dict[tuple[str, str], list[dict]] = {}
        latest_by_store: dict[str, str] = {}
        for record in roster:
            employee_id = record.get("employee_id")
            if employee_id is None or not str(employee_id).strip():
                continue
            store = str(record.get("store") or "")
            snapshot_period = str(record.get("_period") or "")
            comparison_period = self._date_key(snapshot_period) or snapshot_period
            if store not in latest_by_store or comparison_period > latest_by_store[store]:
                latest_by_store[store] = comparison_period
        for record in roster:
            store = str(record.get("store") or "")
            snapshot_period = str(record.get("_period") or "")
            comparison_period = self._date_key(snapshot_period) or snapshot_period
            if comparison_period != latest_by_store.get(store):
                continue
            employee_id = str(record.get("employee_id") or "").strip()
            if not employee_id:
                continue
            snapshots.setdefault((store, employee_id), record)
        # Employee numbers identify a person across stores. If a number appears
        # in more than one store snapshot, retain the most recent snapshot.
        latest_employees: dict[str, dict] = {}
        for record in snapshots.values():
            employee_id = str(record.get("employee_id") or "").strip()
            existing = latest_employees.get(employee_id)
            current_period = self._date_key(record.get("_period")) or str(record.get("_period", ""))
            existing_period = (
                self._date_key(existing.get("_period")) or str(existing.get("_period", ""))
                if existing else ""
            )
            if existing is None or current_period > existing_period:
                latest_employees[employee_id] = record
        employees = list(latest_employees.values())
        reports: dict[str, list[str]] = {}
        for record in employees:
            manager_id = record.get("manager_id")
            if manager_id is not None and str(manager_id).strip():
                reports.setdefault(str(manager_id).strip(), []).append(str(record.get("employee_id")))
        output: list[dict] = []
        for record in employees:
            copy = dict(record)
            direct_reports = sorted(
                reports.get(
                    str(record.get("employee_id") or "").strip(),
                    [],
                )
            )
            copy["direct_reports"] = direct_reports
            copy["direct_report_count"] = len(direct_reports)
            output.append(copy)
        return sorted(
            output,
            key=lambda record: (
                str(record.get("store") or "").casefold(),
                str(record.get("employee_name") or "").casefold(),
                str(record.get("employee_id") or ""),
            ),
        )

    @staticmethod
    def _backup_database(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(destination)
        try:
            source_connection = sqlite3.connect(source, timeout=30)
            try:
                source_connection.backup(target)
            finally:
                source_connection.close()
        finally:
            target.close()

    @_serialized
    def backup(self, path: str | Path) -> None:
        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() == self.path.resolve():
            raise ValueError("Backup destination must be different from the active database.")
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            self._backup_database(self.path, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _validate_database(path: Path) -> None:
        try:
            connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
            try:
                result = connection.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise ValueError(f"Restore database failed integrity check: {result[0] if result else 'no result'}.")
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if version != SCHEMA_VERSION or not {"imports", "imported_records"}.issubset(tables):
                    raise ValueError("Restore file is not a supported PNO database.")
                if tables - {"imports", "imported_records", "sqlite_sequence"}:
                    raise ValueError("Restore file contains unsupported tables.")
                objects = connection.execute(
                    "SELECT type, name FROM sqlite_master "
                    "WHERE type IN ('trigger', 'view')"
                ).fetchall()
                if objects:
                    raise ValueError("Restore file contains unsupported database objects.")
                expected_columns = {
                    "imports": {
                        "id", "kind", "period", "source", "checksum", "sheet",
                        "created_at", "count", "active",
                    },
                    "imported_records": {"id", "import_id", "ordinal", "payload"},
                }
                for table, expected in expected_columns.items():
                    actual = {
                        row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                    }
                    if actual != expected:
                        raise ValueError(f"Restore file has an incompatible {table} table.")
            finally:
                connection.close()
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"Restore file is not a valid SQLite database: {exc}") from exc

    @_serialized
    def restore(self, path: str | Path) -> None:
        source = Path(path).expanduser()
        if not source.is_file():
            raise FileNotFoundError(f"Restore file not found: {source}")
        self._validate_database(source)
        if source.resolve() == self.path.resolve():
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        preserved_backup = self.path.with_name(f"{self.path.name}.pre-restore-{stamp}.bak")
        if self.path.exists():
            self.backup(preserved_backup)

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".restore", dir=self.path.parent
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            self._backup_database(source, temporary)
            self._validate_database(temporary)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)