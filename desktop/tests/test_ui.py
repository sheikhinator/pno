"""Focused GUI/widget checks; all UI fixtures are synthetic and stay in memory."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Event
import time
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from pno.ui_helpers import ChartCanvas, ChartPanel, DataTable, FilterBar
from pno.ui_mapping import coerce_mapped_value, pasted_plan
from pno.ui_provenance import candidate_key, split_sheet_identity, stored_sheet_identity


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(["pno-ui-tests"])


class EmptyStore:
    """Implements only the read-only interface needed by page construction."""

    def __init__(self, path: Path):
        self.path = path

    def dimensions(self) -> dict[str, list[str]]:
        return {"stores": [], "departments": [], "sections": []}

    def records(self, **_: Any) -> list[dict]:
        return []

    def employees(self, period: str | None = None) -> list[dict]:
        return []

    def list_imports(self) -> list[dict]:
        return []


def test_delimited_paste_preserves_zero_blanks_and_unicode():
    plan = pasted_plan(
        "employee_id\temployee_name\tactual\tstatus\n"
        "00123\tعلی رضا\t0\tAbsent\n"
        "00008\tÉlodie\t\tOn Leave\n",
        "attendance",
        "2025-01-01",
    )
    candidate = plan.candidates[0]
    assert candidate.records[0]["raw"]["employee_name"] == "علی رضا"
    assert candidate.records[0]["raw"]["employee_id"] == "00123"
    assert candidate.records[0]["raw"]["actual"] == "0"
    assert coerce_mapped_value("actual", candidate.records[0]["raw"]["actual"]) == 0
    assert candidate.records[0]["raw"]["status"] == "Absent"
    assert candidate.records[1]["raw"]["employee_id"] == "00008"
    assert candidate.records[1]["raw"]["actual"] is None
    assert candidate.records[1]["raw"]["status"] == "On Leave"
    assert len(plan.checksum) == 64


def test_delimited_paste_requires_unique_header_and_data_row():
    with pytest.raises(ValueError, match="unique"):
        pasted_plan("Sales\tSales\n2\t3\n", "sales_mtd", "2025-01-01")
    with pytest.raises(ValueError, match="header row"):
        pasted_plan("Sales\n", "sales_mtd", "2025-01-01")


def test_table_displays_missing_metrics_as_missing_not_zero(app):
    table = DataTable()
    table.fill([{"actual": 0, "budget": None, "status": "Present"}])
    values = {
        table.horizontalHeaderItem(column).text().casefold(): table.item(0, column).text()
        for column in range(table.columnCount())
    }
    assert values["actual"] == "0"
    assert values["budget"] == "—"
    assert values["status"] == "Present"


def test_chart_and_filter_widgets_have_clear_empty_state(app, tmp_path):
    store = EmptyStore(tmp_path / "local.sqlite3")
    filters = FilterBar(store, kind="sales_daily")
    assert filters.filters()["kind"] == "sales_daily"
    assert filters.filters()["store"] is None
    chart = ChartPanel("Test report")
    assert chart.isVisible() is False
    assert chart._view.text() == "No chart data for this scope yet"


def test_filter_dimension_data_survives_refresh_without_recursive_signals(app):
    class MutableStore(EmptyStore):
        def __init__(self):
            super().__init__(Path("unused.sqlite3"))
            self.values = ["Smoke North", "Smoke South"]

        def dimensions(self) -> dict[str, list[str]]:
            return {"stores": list(self.values), "departments": [], "sections": []}

    store = MutableStore()
    filters = FilterBar(store, include_kind=False)
    events = []
    filters.store.currentIndexChanged.connect(events.append)
    south = filters.store.findText("Smoke South")
    filters.store.setCurrentIndex(south)
    assert filters.filters()["store"] == "Smoke South"
    assert len(events) == 1

    store.values = ["Smoke North"]
    filters.refresh_dimensions()
    assert filters.store.currentData() == ""
    assert filters.filters()["store"] is None
    assert len(events) == 1


def test_overview_refreshes_for_every_filter_change(app, tmp_path):
    class DimensionStore(EmptyStore):
        def dimensions(self) -> dict[str, list[str]]:
            return {
                "stores": ["North"],
                "departments": ["Grocery"],
                "sections": ["Produce"],
            }

    calls = []

    def immediate_runner(operation, on_done, **_options):
        calls.append(1)
        on_done(operation())

    from pno.ui_pages import OverviewPage

    page = OverviewPage(DimensionStore(tmp_path / "local.sqlite3"), immediate_runner)
    start = len(calls)
    page.filters_bar.kind.setCurrentIndex(page.filters_bar.kind.findData("sales_daily"))
    page.filters_bar.period_from.setDate(page.filters_bar.period_from.date().addDays(1))
    page.filters_bar.period_to.setDate(page.filters_bar.period_to.date().addDays(-1))
    page.filters_bar.store.setCurrentIndex(page.filters_bar.store.findData("North"))
    page.filters_bar.department.setCurrentIndex(page.filters_bar.department.findData("Grocery"))
    page.filters_bar.section.setCurrentIndex(page.filters_bar.section.findData("Produce"))
    page.filters_bar.employee.setText("E-1")
    assert len(calls) - start == 7


def test_chart_canvas_paints_numeric_native_chart(app):
    chart = ChartPanel("Native chart")
    chart.set_data(
        [{"period": "2025-01-01", "actual": 12, "budget": 10, "last_year": 8}],
        mode="grouped",
    )
    assert isinstance(chart._view, ChartCanvas)
    chart._view.resize(520, 260)
    pixmap = QPixmap(chart._view.size())
    chart._view.render(pixmap)
    assert not pixmap.isNull()


def test_refresh_results_ignore_older_filter_responses(app, tmp_path):
    class DeferredRunner:
        def __init__(self):
            self.jobs = []

        def __call__(self, operation, on_done, **options):
            self.jobs.append((operation, on_done, options))

    from pno.ui_pages import SalesPage

    class DimensionStore(EmptyStore):
        def dimensions(self) -> dict[str, list[str]]:
            return {"stores": ["North", "South"], "departments": [], "sections": []}

    store = DimensionStore(tmp_path / "local.sqlite3")
    runner = DeferredRunner()
    page = SalesPage(store, runner, "sales_mtd")
    old = {"metrics": {"actual": 11}, "trends": [], "rows": [], "warnings": []}
    latest = {"metrics": {"actual": 22}, "trends": [], "rows": [], "warnings": []}
    initial_token = page._refresh_token
    page.filters.store.setCurrentIndex(page.filters.store.findData("South"))
    new_token = page._refresh_token
    assert new_token > initial_token
    runner.jobs[-1][1](latest)
    runner.jobs[0][1](old)
    assert page.last_result is latest


def test_assistant_return_cannot_queue_concurrent_requests(app, tmp_path):
    class DeferredRunner:
        def __init__(self):
            self.jobs = []

        def __call__(self, operation, on_done, **options):
            self.jobs.append((operation, on_done, options))

    from pno.ui_tools import AssistantPage

    runner = DeferredRunner()
    page = AssistantPage(EmptyStore(tmp_path / "local.sqlite3"), runner)
    page.question.setText("How did sales compare?")
    page.ask()
    page.question.setEnabled(True)  # Simulate a Return signal arriving during an active request.
    page.question.setText("Another question")
    page.ask()
    assert len(runner.jobs) == 1
    assert page._request_active is True
    assert page.send.isEnabled() is False


def test_analysis_export_uses_computed_result_filter_snapshot(app, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    import pno.ui_pages as ui_pages

    class DeferredRunner:
        def __init__(self):
            self.jobs = []

        def __call__(self, operation, on_done, **options):
            self.jobs.append((operation, on_done, options))

    runner = DeferredRunner()
    page = ui_pages.AnalysisPage(EmptyStore(tmp_path / "local.sqlite3"), runner)
    original = {
        "metrics": {"actual": 9},
        "filters": {"kind": "sales_mtd", "store": "Fictional North"},
        "sources": [{"sheet": "Fictional source [PNO header row 8]"}],
        "warnings": [],
        "commentary": [],
    }
    page.result = original
    calls = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(tmp_path / "report"), ""))
    monkeypatch.setattr(
        ui_pages,
        "export_report",
        lambda result, path, **kwargs: calls.append((result, str(path), kwargs)),
    )
    page._export("csv")
    export_work = runner.jobs[-1][0]
    page.result = {"metrics": {"actual": 1000}, "filters": {"store": "Fictional South"}}
    export_work()
    assert calls[0][0]["metrics"]["actual"] == 9
    assert calls[0][0]["sources"] == [
        {"sheet": "Fictional source", "header_row": 8}
    ]
    assert calls[0][1].endswith("report.csv")
    assert calls[0][2]["filters"] == {"kind": "sales_mtd", "store": "Fictional North"}


def test_restore_pauses_ui_writes_and_serializes_inflight_store_mutations(app, tmp_path):
    from pno.ui import MainWindow

    window = MainWindow(EmptyStore(tmp_path / "local.sqlite3"))
    started = Event()
    release = Event()
    first = window.run_job(
        lambda: (started.set(), release.wait(2)),
        lambda _value: None,
        mutating=True,
    )
    assert first
    assert started.wait(2)
    window._pages["imports"].plan = object()
    window._pages["imports"].save_button.setEnabled(True)
    window.set_restore_active(True)
    assert not window._pages["settings"].backup.isEnabled()
    assert not window._pages["imports"].save_button.isEnabled()
    rejected = []
    ran = []
    accepted = window.run_job(
        lambda: ran.append(True),
        lambda _value: None,
        mutating=True,
        on_error=rejected.append,
    )
    assert accepted is False
    assert rejected and "restore" in str(rejected[0]).casefold()
    assert not ran
    release.set()
    window.set_restore_active(False)
    window.close()


def test_source_sheet_identity_preserves_name_and_header_row():
    from types import SimpleNamespace
    from pno.ui_history import ImportHistoryPanel

    first = SimpleNamespace(sheet="Sales report", header_row=3)
    second = SimpleNamespace(sheet="Sales report", header_row=12)
    assert candidate_key(first) != candidate_key(second)
    identity = stored_sheet_identity("Sales report", 12, qualify=True)
    assert split_sheet_identity(identity) == ("Sales report", "12")

    class ProvenanceStore(EmptyStore):
        def list_imports(self) -> list[dict]:
            return [{
                "id": 1,
                "kind": "sales_mtd",
                "period": "2025-01-01",
                "source": "fictional.xlsx",
                "sheet": identity,
                "created_at": "2025-01-01",
                "count": 1,
                "active": True,
            }]

    history = ImportHistoryPanel(ProvenanceStore(Path("unused.sqlite3")))
    columns = {
        history.table.horizontalHeaderItem(i).text(): i
        for i in range(history.table.columnCount())
    }
    assert history.table.item(0, columns["Worksheet"]).text() == "Sales report"
    assert history.table.item(0, columns["Header row"]).text() == "12"

def test_fictional_smoke_seed_drives_filtered_dashboard_and_chart(app, tmp_path):
    from pno.__main__ import _seed_fictional_smoke_records
    from pno.storage import Store
    from pno.ui import MainWindow

    store = Store(tmp_path / "smoke.sqlite3")
    _seed_fictional_smoke_records(store)
    window = MainWindow(store)
    try:
        page = window._pages["dashboard"]

        def wait_for(token: int):
            deadline = time.monotonic() + 8
            while page._last_completed_token < token and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.005)
            assert page._last_completed_token >= token

        wait_for(page._refresh_token)
        assert page.last_result["metrics"]["actual"] == 200
        assert isinstance(page.chart._view, ChartCanvas)
        index = page.filters_bar.store.findData("Fictional Smoke South")
        assert index >= 0
        previous = page._refresh_token
        page.filters_bar.store.setCurrentIndex(index)
        token = page._refresh_token
        assert token > previous
        wait_for(token)
        assert page.filters_bar.filters()["store"] == "Fictional Smoke South"
        assert page.last_result["metrics"]["actual"] == 75
        assert isinstance(page.chart._view, ChartCanvas)
        assert any(row.get("actual") == 75 for row in page.chart._view.rows)
    finally:
        window.close()


def test_packaged_model_discovery_is_local_and_settings_override_wins(monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    import pno.ui_tools as ui_tools

    executable = tmp_path / "PNO.exe"
    bundled = tmp_path / "models" / ui_tools.BUNDLED_MODEL_RELATIVE.name
    bundled.parent.mkdir()
    bundled.write_bytes(b"GGUF local fixture")
    monkeypatch.setattr(ui_tools.sys, "executable", str(executable))
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    assert ui_tools.selected_model_path(settings) == str(bundled)
    override = tmp_path / "chosen.gguf"
    settings.setValue("assistant/model_path", str(override))
    assert ui_tools.selected_model_path(settings) == str(override)
    settings.remove("assistant/model_path")
    assert ui_tools.selected_model_path(settings) == str(bundled)


def test_native_window_has_complete_primary_navigation(app, tmp_path):
    from pno.ui import MainWindow

    window = MainWindow(EmptyStore(tmp_path / "local.sqlite3"))
    expected = {
        "dashboard",
        "sales_daily",
        "sales_mtd",
        "attendance",
        "staff",
        "analysis",
        "assistant",
        "imports",
        "settings",
    }
    assert set(window._pages) == expected
    window.navigate("staff")
    assert window.stack.currentWidget() is window._page_containers["staff"]
    assert window._page_containers["staff"].widget() is window._pages["staff"]
    assert window.page_title.text() == "Staff & hierarchy"
    window.close()
