import sqlite3
import threading
import time

import pytest

from pno.storage import ConflictImportError, DuplicateImportError, Store


def test_import_is_atomic_duplicate_conflict_and_replacement_is_audited(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    records = [{"store": "North", "department": "Retail", "date": "2025-01-01", "actual": 0}]

    first_id = store.import_records(
        "sales_daily", "2025-01", records, "daily.csv", "sha-a", "Sales"
    )
    assert first_id > 0
    with pytest.raises(DuplicateImportError):
        store.import_records(
            "sales_daily", "2025-01", records, "daily.csv", "sha-a", "Sales"
        )
    with pytest.raises(ConflictImportError):
        store.import_records(
            "sales_daily", "2025-01", records, "corrected.csv", "sha-b", "Sales"
        )
    assert len(store.list_imports()) == 1

    second_id = store.import_records(
        "sales_daily", "2025-01",
        [{"store": "North", "department": "Retail", "date": "2025-01-01", "actual": 5}],
        "corrected.csv", "sha-b", "Sales", replace=True,
    )
    imports = store.list_imports()
    assert second_id != first_id
    assert [item["active"] for item in imports] == [True, False]
    assert imports[1]["count"] == 1
    assert store.records()[0]["actual"] == 5
    assert store.records()[0]["_import_id"] == second_id


def test_conflicts_use_business_coverage_not_worksheet_name(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    store.import_records(
        "sales_daily", "2025-03",
        [{"store": "StoreA", "department": "Retail", "date": "2025-03-01", "actual": 10}],
        "first.xlsx", "sum-a", "Sheet1",
    )
    store.import_records(
        "sales_daily", "2025-03",
        [{"store": "StoreB", "department": "Retail", "date": "2025-03-01", "actual": 20}],
        "second.xlsx", "sum-b", "Sheet1",
    )

    with pytest.raises(ConflictImportError, match="business coverage"):
        store.import_records(
            "sales_daily", "2025-03",
            [{"store": "StoreA", "department": "Retail", "date": "2025-03-01", "actual": 11}],
            "corrected.xlsx", "sum-c", "ChangedSheet",
        )

    replacement_id = store.import_records(
        "sales_daily", "2025-03",
        [{"store": "StoreA", "department": "Retail", "date": "2025-03-01", "actual": 11}],
        "corrected.xlsx", "sum-c", "ChangedSheet", replace=True,
    )
    active = [item for item in store.list_imports() if item["active"]]
    assert len(active) == 2
    assert {row["store"] for row in store.records()} == {"StoreA", "StoreB"}
    assert {row["actual"] for row in store.records()} == {11, 20}
    assert any(item["id"] == replacement_id for item in active)
    old = next(item for item in store.list_imports() if item["source"] == "first.xlsx")
    assert old["active"] is False
    other_store = next(item for item in store.list_imports() if item["source"] == "second.xlsx")
    assert other_store["active"] is True


def test_same_sheet_candidate_tables_use_distinct_identity_and_scope(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    checksum = "same-workbook-checksum"
    store.import_records(
        "sales_daily", "2025-04",
        [{"store": "StoreA", "department": "Shoes", "date": "2025-04-01", "actual": 10}],
        "report.xlsx", checksum, "Sheet1 [header row 2]",
    )
    store.import_records(
        "sales_daily", "2025-04",
        [{"store": "StoreA", "department": "Apparel", "date": "2025-04-01", "actual": 20}],
        "report.xlsx", checksum, "Sheet1 [header row 12]",
    )

    assert len([item for item in store.list_imports() if item["active"]]) == 2
    assert {row["department"] for row in store.records()} == {"Shoes", "Apparel"}


def test_partial_replacement_of_mixed_store_batch_is_rejected_without_deactivation(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    batch_id = store.import_records(
        "sales_daily", "2025-05",
        [
            {"store": "StoreA", "department": "Retail", "date": "2025-05-01", "actual": 10},
            {"store": "StoreB", "department": "Retail", "date": "2025-05-01", "actual": 20},
        ],
        "combined.xlsx", "combined", "Summary",
    )

    with pytest.raises(ConflictImportError, match="every prior observation key"):
        store.import_records(
            "sales_daily", "2025-05",
            [{"store": "StoreA", "department": "Retail", "date": "2025-05-01", "actual": 11}],
            "store-a.xlsx", "store-a", "DifferentSheet", replace=True,
        )

    assert len(store.list_imports()) == 1
    assert store.list_imports()[0]["id"] == batch_id
    assert store.list_imports()[0]["active"] is True
    assert {row["store"] for row in store.records()} == {"StoreA", "StoreB"}


def test_daily_observation_conflicts_use_actual_date_across_period_labels(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    original_id = store.import_records(
        "sales_daily", "batch-label-a",
        [{"store": "North", "department": "Retail", "date": "2025-01-01", "actual": 10}],
        "first.xlsx", "daily-a", "Daily",
    )

    with pytest.raises(ConflictImportError, match="business coverage"):
        store.import_records(
            "sales_daily", "batch-label-b",
            [{"store": "North", "department": "Retail", "date": "2025-01-01", "actual": 11}],
            "corrected.xlsx", "daily-b", "Changed sheet",
        )

    other_day_id = store.import_records(
        "sales_daily", "batch-label-a",
        [{"store": "North", "department": "Retail", "date": "2025-01-02", "actual": 12}],
        "second-day.xlsx", "daily-c", "Daily",
    )
    assert {record["date"] for record in store.records(kind="sales_daily")} == {
        "2025-01-01", "2025-01-02"
    }
    assert {item["id"] for item in store.list_imports() if item["active"]} == {
        original_id, other_day_id
    }


def test_partial_daily_replacement_preserves_entire_active_batch(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    original_id = store.import_records(
        "sales_daily", "2025-01",
        [
            {"store": "North", "department": "Retail", "date": "2025-01-01", "actual": 10},
            {"store": "North", "department": "Retail", "date": "2025-01-02", "actual": 20},
        ],
        "two-days.xlsx", "two-days", "Daily",
    )

    with pytest.raises(ConflictImportError, match="every prior observation key"):
        store.import_records(
            "sales_daily", "corrected-label",
            [{"store": "North", "department": "Retail", "date": "2025-01-01", "actual": 11}],
            "one-day-correction.xlsx", "one-day", "Correction", replace=True,
        )

    assert [item["id"] for item in store.list_imports() if item["active"]] == [original_id]
    assert {record["actual"] for record in store.records(kind="sales_daily")} == {10, 20}


def test_attendance_conflicts_and_replacement_are_employee_date_specific(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    original_id = store.import_records(
        "attendance", "2025-02",
        [
            {
                "store": "North", "department": "Retail", "section": "Shoes",
                "employee_id": "E1", "date": "2025-02-01", "hours": 8,
            },
            {
                "store": "North", "department": "Retail", "section": "Shoes",
                "employee_id": "E2", "date": "2025-02-01", "hours": 7,
            },
        ],
        "attendance.xlsx", "attendance-a", "Attendance",
    )

    with pytest.raises(ConflictImportError, match="business coverage"):
        store.import_records(
            "attendance", "different-batch-label",
            [{
                "store": "North", "department": "Retail", "section": "Shoes",
                "employee_id": "E1", "date": "2025-02-01", "hours": 9,
            }],
            "e1-correction.xlsx", "attendance-b", "Changed sheet",
        )

    other_employee_id = store.import_records(
        "attendance", "2025-02",
        [{
            "store": "North", "department": "Retail", "section": "Shoes",
            "employee_id": "E3", "date": "2025-02-01", "hours": 6,
        }],
        "e3.xlsx", "attendance-c", "Attendance",
    )

    with pytest.raises(ConflictImportError, match="every prior observation key"):
        store.import_records(
            "attendance", "corrected-label",
            [{
                "store": "North", "department": "Retail", "section": "Shoes",
                "employee_id": "E1", "date": "2025-02-01", "hours": 9,
            }],
            "partial-attendance.xlsx", "attendance-d", "Correction", replace=True,
        )

    assert {item["id"] for item in store.list_imports() if item["active"]} == {
        original_id, other_employee_id
    }
    assert {record["employee_id"] for record in store.records(kind="attendance")} == {
        "E1", "E2", "E3"
    }


def test_unknown_daily_date_fails_closed_for_replacement(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    original_id = store.import_records(
        "sales_daily", "2025-03",
        [{"store": "North", "department": "Retail", "actual": 10}],
        "unknown-date.xlsx", "unknown-a", "Daily",
    )

    with pytest.raises(ConflictImportError, match="unknown observation date or identity"):
        store.import_records(
            "sales_daily", "2025-03",
            [{"store": "North", "department": "Retail", "date": "2025-03-01", "actual": 11}],
            "dated-correction.xlsx", "unknown-b", "Correction", replace=True,
        )

    assert [item["id"] for item in store.list_imports() if item["active"]] == [original_id]
    assert store.records(kind="sales_daily")[0]["actual"] == 10


def test_daily_scope_matches_exact_grain_not_parent_child_hierarchy(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    store.import_records(
        "sales_daily", "2025-04",
        [{
            "store": "North", "department": "Retail", "date": "2025-04-01", "actual": 100,
        }],
        "department-summary.xlsx", "summary-a", "Summary",
    )
    store.import_records(
        "sales_daily", "2025-04",
        [{
            "store": "North", "department": "Retail", "section": "Shoes",
            "date": "2025-04-01", "actual": 40,
        }],
        "section-detail.xlsx", "detail-a", "Detail",
    )

    assert len([item for item in store.list_imports() if item["active"]]) == 2


@pytest.mark.parametrize("kind", ["sales_mtd", "productivity"])
def test_snapshot_metrics_conflict_on_exact_scope_and_actual_date_across_labels(tmp_path, kind):
    store = Store(tmp_path / f"{kind}.sqlite3")
    first_record = {
        "store": "North", "department": "Retail", "date": "2025-06-30", "actual": 10,
    }
    store.import_records(kind, "label-a", [first_record], "first.xlsx", f"{kind}-a", "Summary")

    with pytest.raises(ConflictImportError, match="business coverage"):
        store.import_records(
            kind, "label-b", [dict(first_record, actual=11)],
            "correction.xlsx", f"{kind}-b", "Changed sheet",
        )

    store.import_records(
        kind, "label-b",
        [{
            "store": "North", "department": "Retail", "section": "Shoes",
            "date": "2025-06-30", "actual": 20,
        }],
        "detail.xlsx", f"{kind}-c", "Detail",
    )
    assert len([item for item in store.list_imports() if item["active"]]) == 2


def test_roster_coverage_uses_employee_and_snapshot_date(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    store.import_records(
        "roster", "2025-01",
        [
            {"employee_id": "E1", "store": "North", "employee_name": "One"},
            {"employee_id": "E2", "store": "North", "employee_name": "Two"},
        ],
        "roster.xlsx", "roster-a", "Roster",
    )

    with pytest.raises(ConflictImportError, match="business coverage"):
        store.import_records(
            "roster", "2025-01",
            [{"employee_id": "E1", "store": "North", "employee_name": "Corrected"}],
            "correction.xlsx", "roster-b", "Changed sheet",
        )

    store.import_records(
        "roster", "2025-01",
        [{"employee_id": "E3", "store": "North", "employee_name": "Three"}],
        "additional.xlsx", "roster-c", "Roster",
    )
    store.import_records(
        "roster", "2025-02",
        [{"employee_id": "E1", "store": "North", "employee_name": "One"}],
        "next-snapshot.xlsx", "roster-d", "Roster",
    )
    assert len([item for item in store.list_imports() if item["active"]]) == 3


def test_filters_dimensions_and_date_fallback(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    store.import_records(
        "sales_daily", "2025-02",
        [
            {"store": "North", "department": "Retail", "section": "Shoes", "date": "2025-02-01", "actual": 0},
            {"store": "South", "department": "Service", "section": "Returns", "date": "2025-02-15", "actual": 8},
        ],
        "sales.csv", "sha", "Daily",
    )
    store.import_records(
        "sales_mtd", "2025-02",
        [{"store": "North", "department": "Retail", "actual": 20}],
        "mtd.csv", "sha-mtd", "MTD",
    )

    assert len(store.records(kind="sales_daily", period_from="2025-02-10", period_to="2025-02")) == 1
    assert store.records(store="North", department="Retail", section="Shoes")[0]["actual"] == 0
    assert store.records(employee="missing") == []
    assert store.dimensions() == {
        "stores": ["North", "South"],
        "departments": ["Retail", "Service"],
        "sections": ["Returns", "Shoes"],
    }


def test_roster_as_of_snapshots_and_reports_use_manager_ids(tmp_path):
    store = Store(tmp_path / "pno.sqlite3")
    store.import_records(
        "roster", "2024-01",
        [
            {"store": "North", "employee_id": "001", "employee_name": "Alex Same", "designation": "Manager"},
            {"store": "North", "employee_id": "002", "employee_name": "Alex Same", "manager_id": "001"},
        ],
        "roster-a.csv", "roster-a", "Roster",
    )
    store.import_records(
        "roster", "2025-01",
        [
            {"store": "North", "employee_id": "101", "employee_name": "Alex Same", "designation": "Manager"},
            {"store": "North", "employee_id": "002", "employee_name": "Alex Same", "manager_id": "101"},
        ],
        "roster-b.csv", "roster-b", "Roster",
    )

    historic = store.employees(period="2024-06")
    current = store.employees()
    assert {row["employee_id"] for row in historic} == {"001", "002"}
    old_manager = next(row for row in historic if row["employee_id"] == "001")
    assert old_manager["direct_reports"] == ["002"]
    assert {row["employee_id"] for row in current} == {"101", "002"}
    new_manager = next(row for row in current if row["employee_id"] == "101")
    assert new_manager["direct_reports"] == ["002"]


def test_backup_restore_validates_and_preserves_pre_restore_database(tmp_path):
    database = tmp_path / "pno.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    store = Store(database)
    store.import_records(
        "sales_daily", "2025-01",
        [{"store": "A", "date": "2025-01-01", "actual": 1}], "a.csv", "a", "Sales",
    )
    store.backup(backup)
    store.import_records(
        "sales_daily", "2025-02",
        [{"store": "A", "date": "2025-02-01", "actual": 2}], "b.csv", "b", "Sales",
    )

    store.restore(backup)

    assert [row["period"] for row in store.list_imports()] == ["2025-01"]
    assert len(list(tmp_path.glob("pno.sqlite3.pre-restore-*.bak"))) == 1
    assert store.records()[0]["actual"] == 1

    invalid = tmp_path / "not-a-database.sqlite3"
    invalid.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(ValueError, match="valid SQLite"):
        store.restore(invalid)
    assert [row["period"] for row in store.list_imports()] == ["2025-01"]


def test_database_lock_serializes_restore_against_other_store_instances(tmp_path, monkeypatch):
    database = tmp_path / "pno.sqlite3"
    restore_file = tmp_path / "restore.sqlite3"
    first = Store(database)
    second = Store(database)
    assert first._lock is second._lock
    first.import_records(
        "sales_daily", "2025-01",
        [{"store": "A", "date": "2025-01-01", "actual": 1}], "a", "a", "Sales",
    )
    source = Store(restore_file)
    source.import_records(
        "sales_daily", "2025-02",
        [{"store": "B", "date": "2025-02-01", "actual": 2}], "b", "b", "Sales",
    )

    entered_backup = threading.Event()
    resume_backup = threading.Event()
    import_finished = threading.Event()
    original_backup = Store._backup_database
    first_call = True

    def pause_backup(source_path, destination_path):
        nonlocal first_call
        if first_call:
            first_call = False
            entered_backup.set()
            assert resume_backup.wait(timeout=5)
        return original_backup(source_path, destination_path)

    monkeypatch.setattr(Store, "_backup_database", staticmethod(pause_backup))
    restore_errors = []

    def restore():
        try:
            first.restore(restore_file)
        except Exception as exc:  # surfaced to the test thread
            restore_errors.append(exc)

    restore_thread = threading.Thread(target=restore)
    restore_thread.start()
    assert entered_backup.wait(timeout=5)

    def add_after_restore_lock():
        second.import_records(
            "sales_daily", "2025-03",
            [{"store": "C", "date": "2025-03-01", "actual": 3}], "c", "c", "Sales"
        )
        import_finished.set()

    import_thread = threading.Thread(target=add_after_restore_lock)
    import_thread.start()
    time.sleep(0.05)
    assert not import_finished.is_set()
    resume_backup.set()
    restore_thread.join(timeout=5)
    import_thread.join(timeout=5)

    assert not restore_errors
    assert import_finished.is_set()
    assert {row["_period"] for row in second.records()} == {"2025-02", "2025-03"}