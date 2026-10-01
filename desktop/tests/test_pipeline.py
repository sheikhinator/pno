"""A fully fictional, file-to-history-to-analysis integration check."""

from pathlib import Path

from pno.analysis import analyze, export_report
from pno.assistant import Assistant
from pno.importer import scan_workbook
from pno.storage import Store
from scripts import make_samples


def test_fictional_workbook_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(make_samples, "ROOT", tmp_path / "samples")
    make_samples.main()
    store_path = tmp_path / "history.sqlite3"
    store = Store(store_path)
    counts = {}
    for filename in sorted(make_samples.ROOT.glob("*.xlsx")):
        plan = scan_workbook(filename, period="2026-08")
        assert plan.candidates, f"No tables detected in {filename.name}"
        for candidate in plan.candidates:
            assert candidate.kind in {
                "roster", "sales_daily", "sales_mtd", "attendance", "productivity"
            }
            period = "2026-08-01" if candidate.kind == "roster" else "2026-08"
            store.import_records(
                candidate.kind, period, candidate.records, str(filename),
                plan.checksum, candidate.sheet,
            )
            counts[candidate.kind] = counts.get(candidate.kind, 0) + len(candidate.records)

    assert counts == {
        "roster": 5, "sales_daily": 2, "sales_mtd": 1,
        "attendance": 4, "productivity": 1,
    }
    # A new Store instance demonstrates that history is not session-only.
    reopened = Store(store_path)
    result = analyze(reopened, {
        "kind": "sales_mtd", "period_from": "2026-08-01",
        "period_to": "2026-08-31", "store": "Training Store A",
    })
    assert result["metrics"]["actual"] == 30400
    assert result["metrics"]["budget"] == 31000
    assert result["metrics"]["attendance_rate_pct"] == 50
    assert len(reopened.employees(period="2026-08-31")) == 5
    manager = analyze(reopened, {
        "employee": "DEMO-SM", "period_from": "2026-08-01",
        "period_to": "2026-08-31", "kind": "sales_mtd",
    })
    assert manager["metrics"]["actual"] == 30400
    assert manager["metrics"]["direct_reports"] == 2
    person = analyze(reopened, {
        "employee": "DEMO-001", "period_from": "2026-08-01",
        "period_to": "2026-08-31", "kind": "sales_mtd",
    })
    assert person["metrics"]["actual"] is None
    answer = Assistant(reopened).ask("Show attendance for employee DEMO-001 in 2026-08")
    assert "DEMO-001" in answer
    assert "50" in answer
    unknown = Assistant(reopened).ask("Show employee DOES-NOT-EXIST in 2026-08")
    assert "30,400" not in unknown
    for fmt in ("pdf", "xlsx", "csv"):
        destination = tmp_path / f"review.{fmt}"
        export_report(result, destination, format=fmt, filters={"store": "Training Store A"})
        assert destination.is_file()
        assert destination.stat().st_size > 100
