"""Dashboard, sales, attendance, staff hierarchy and score-report pages."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .analysis import analyze, export_report
from .ui_helpers import ChartPanel, DataTable, FilterBar, MetricCards, display_number, empty_panel
from .ui_provenance import split_sheet_identity


METRIC_SPEC = (
    ("Sales", "actual", ""),
    ("Vs budget", "budget_achievement_pct", "%"),
    ("Growth vs LY", "sales_growth_pct", "%"),
    ("OOS", "oos_value", ""),
    ("Attendance", "attendance_rate_pct", "%"),
    ("Productivity", "productivity", ""),
    ("Employees", "employee_count", ""),
    ("Hours", "hours", ""),
)


def report_values(result: dict[str, Any], sales: bool = True) -> list[tuple[str, str, str]]:
    metrics = result.get("metrics") or {}
    keys = METRIC_SPEC if sales else (
        ("Present", "attendance_rate_pct", "%"),
        ("Hours", "hours", ""),
        ("Employees", "employee_count", ""),
        ("Productivity", "productivity", ""),
    )
    entries = []
    for label, key, suffix in keys:
        value = metrics.get(key)
        if value is None:
            note = "Not present in imported data"
        elif key.endswith("_pct"):
            note = "Reported percentage"
        elif key == "budget_achievement_pct":
            note = f"Against budget {display_number(metrics.get('budget'))}"
        elif key == "sales_growth_pct":
            note = f"Last year {display_number(metrics.get('last_year'))}"
        else:
            note = "From imported reports"
        entries.append((label, display_number(value, suffix), note))
    return entries


def _begin_refresh(page: QWidget) -> int:
    token = getattr(page, "_refresh_token", 0) + 1
    page._refresh_token = token
    return token


def _is_latest_refresh(page: QWidget, token: int) -> bool:
    return token == getattr(page, "_refresh_token", 0)


class OverviewPage(QWidget):
    def __init__(self, store: Any, run_job: Callable):
        super().__init__()
        self.store = store
        self.run_job = run_job
        self.last_result: dict[str, Any] | None = None
        self._last_completed_token = 0
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(empty_panel(
            "Workforce & business overview",
            "One offline workspace for sales, attendance, productivity, and team structure. "
            "Metrics appear only when the corresponding reports have been imported.",
        ))
        self.filters_bar = FilterBar(self.store, kind="sales_mtd")
        layout.addWidget(self.filters_bar)
        self.filters_bar.kind.currentIndexChanged.connect(self.refresh)
        for control in (self.filters_bar.period_from, self.filters_bar.period_to):
            control.dateChanged.connect(self.refresh)
        for control in (self.filters_bar.store, self.filters_bar.department, self.filters_bar.section):
            control.currentIndexChanged.connect(self.refresh)
        self.filters_bar.employee.textChanged.connect(self.refresh)
        self.cards = MetricCards()
        layout.addWidget(self.cards)
        self.chart = ChartPanel("Sales against plan")
        layout.addWidget(self.chart, 1)
        self.notice = QLabel("Import a workbook to see your actual business data here.")
        self.notice.setObjectName("hint")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

    def refresh(self) -> None:
        self.filters_bar.refresh_dimensions()
        filters = self.filters_bar.filters()
        token = _begin_refresh(self)

        def work():
            return analyze(self.store, filters)

        def done(result: dict[str, Any]) -> None:
            if not _is_latest_refresh(self, token):
                return
            self._last_completed_token = token
            self.last_result = result
            self.cards.set_entries(report_values(result))
            self.chart.set_data(result.get("trends") or [], mode="grouped")
            self.notice.setText(" · ".join(result.get("warnings") or []) or "Showing metrics supported by active imported reports.")

        self.run_job(work, done, title="Refreshing overview…")


class SalesPage(QWidget):
    def __init__(self, store: Any, run_job: Callable, mode: str = "sales_mtd"):
        super().__init__()
        self.store = store
        self.run_job = run_job
        self.mode = mode
        self.last_result: dict[str, Any] | None = None
        self._build()
        self.filters.kind.setCurrentIndex(self.filters.kind.findData(mode))
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        title = "Daily sales" if self.mode == "sales_daily" else "Monthly sales · MTD"
        layout.addWidget(empty_panel(
            title,
            "Compare actual sales with the available budget and last-year figures. Missing values remain blank; "
            "daily and month-to-date reports are kept as separate data types.",
        ))
        self.filters = FilterBar(self.store, kind=self.mode)
        self.filters.kind.currentIndexChanged.connect(self.refresh)
        self.filters.period_from.dateChanged.connect(self.refresh)
        self.filters.period_to.dateChanged.connect(self.refresh)
        self.filters.store.currentIndexChanged.connect(self.refresh)
        self.filters.department.currentIndexChanged.connect(self.refresh)
        self.filters.section.currentIndexChanged.connect(self.refresh)
        self.filters.employee.textChanged.connect(self.refresh)
        layout.addWidget(self.filters)
        self.cards = MetricCards()
        layout.addWidget(self.cards)
        self.chart = ChartPanel("Sales · actual, budget, last year")
        layout.addWidget(self.chart, 1)
        self.table = DataTable()
        self.table.setMinimumHeight(180)
        layout.addWidget(self.table, 1)
        self.notice = QLabel()
        self.notice.setObjectName("hint")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

    def refresh(self) -> None:
        self.filters.refresh_dimensions()
        filters = self.filters.filters(default_kind=self.mode)
        token = _begin_refresh(self)

        def done(result: dict[str, Any]) -> None:
            if not _is_latest_refresh(self, token):
                return
            self.last_result = result
            self.cards.set_entries(report_values(result))
            self.chart.set_data(result.get("trends") or [], mode="grouped")
            self.table.fill(result.get("rows") or [])
            messages = list(result.get("warnings") or [])
            if not (result.get("rows") or result.get("trends")):
                messages.insert(0, "No active report rows match this selection. Import the corresponding report to begin.")
            self.notice.setText(" · ".join(messages) if messages else "Source details reflect only the active report batches.")

        self.run_job(lambda: analyze(self.store, filters), done, title="Calculating sales report…")


class AttendancePage(QWidget):
    def __init__(self, store: Any, run_job: Callable):
        super().__init__()
        self.store = store
        self.run_job = run_job
        self.last_result: dict[str, Any] | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(empty_panel(
            "Attendance & hours",
            "Review recorded attendance statuses, working hours, and trends. The application preserves the report's "
            "status labels and does not infer attendance from missing entries.",
        ))
        self.filters = FilterBar(self.store, kind="attendance", include_kind=False)
        self.filters.period_from.dateChanged.connect(self.refresh)
        self.filters.period_to.dateChanged.connect(self.refresh)
        self.filters.store.currentIndexChanged.connect(self.refresh)
        self.filters.department.currentIndexChanged.connect(self.refresh)
        self.filters.section.currentIndexChanged.connect(self.refresh)
        self.filters.employee.textChanged.connect(self.refresh)
        layout.addWidget(self.filters)
        self.cards = MetricCards()
        layout.addWidget(self.cards)
        self.chart = ChartPanel("Attendance · recorded trends")
        layout.addWidget(self.chart, 1)
        self.table = DataTable()
        self.table.setMinimumHeight(180)
        layout.addWidget(self.table, 1)
        self.notice = QLabel()
        self.notice.setObjectName("hint")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

    def refresh(self) -> None:
        self.filters.refresh_dimensions()
        filters = self.filters.filters(default_kind="attendance")
        filters["kind"] = "attendance"
        token = _begin_refresh(self)

        def work():
            summary = analyze(self.store, filters)
            rows = self.store.records(
                kind="attendance",
                period_from=filters.get("period_from"),
                period_to=filters.get("period_to"),
                store=filters.get("store"),
                department=filters.get("department"),
                section=filters.get("section"),
                employee=filters.get("employee"),
            )
            by_date: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                day = str(row.get("date") or row.get("_period") or "").strip()
                if day:
                    by_date.setdefault(day[:10], []).append(row)
            trends = []
            for day, day_rows in sorted(by_date.items()):
                # Aggregate only unambiguous employee-detail records. Report-level
                # totals may overlap details and are shown in the source table only.
                detail_rows = [row for row in day_rows if row.get("employee_id") not in (None, "")]
                series_rows = detail_rows if detail_rows else day_rows if len(day_rows) == 1 else []
                hours = []
                identifiers = [str(row.get("employee_id")) for row in detail_rows]
                duplicate_people = bool(identifiers and len(set(identifiers)) != len(identifiers))
                for row in series_rows:
                    try:
                        value = float(row["hours"]) if row.get("hours") is not None else None
                    except (TypeError, ValueError):
                        value = None
                    hours.append(value if value is not None and math.isfinite(value) else None)
                total = (
                    sum(value for value in hours if value is not None)
                    if hours and all(value is not None for value in hours) and not duplicate_people
                    else None
                )
                trends.append({"period": day, "hours": total})
            return summary, rows, trends

        def done(payload: Any) -> None:
            if not _is_latest_refresh(self, token):
                return
            summary, rows, trends = payload
            self.last_result = summary
            self.cards.set_entries(report_values(summary, sales=False))
            self.chart.set_data(trends, ("hours",), mode="line")
            self.table.fill(rows or [])
            warnings = list(summary.get("warnings") or [])
            if not rows:
                warnings.insert(0, "No attendance rows match these filters. Import the attendance report to view them.")
            self.notice.setText(" · ".join(warnings) if warnings else "Attendance statuses and hours are shown only when reported.")

        self.run_job(work, done, title="Refreshing attendance…")


class StaffPage(QWidget):
    def __init__(self, store: Any, run_job: Callable):
        super().__init__()
        self.store = store
        self.run_job = run_job
        self._employees: list[dict[str, Any]] = []
        self.last_result: list[dict[str, Any]] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(empty_panel(
            "Staff & reporting structure",
            "The roster is resolved as of the selected date, using employee and manager identifiers—not display names. "
            "Only roster rows for an imported, active snapshot are shown.",
        ))
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Roster as of"))
        from PySide6.QtWidgets import QDateEdit

        self.as_of = QDateEdit()
        self.as_of.setCalendarPopup(True)
        self.as_of.setDisplayFormat("dd MMM yyyy")
        self.as_of.setDate(__import__("PySide6.QtCore", fromlist=["QDate"]).QDate.currentDate())
        self.as_of.dateChanged.connect(self.refresh)
        bar.addWidget(self.as_of)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search employee, code, manager, department…")
        self.search.textChanged.connect(self._fill_employees)
        bar.addWidget(self.search, 2)
        layout.addLayout(bar)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Employees · select a person to inspect reports"))
        self.employees_table = DataTable()
        self.employees_table.itemSelectionChanged.connect(self._selected_employee)
        left_layout.addWidget(self.employees_table, 1)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        profile_frame = QFrame()
        profile_frame.setObjectName("panel")
        profile_layout = QVBoxLayout(profile_frame)
        profile_layout.setContentsMargins(12, 10, 12, 10)
        self.profile = QLabel("Select an employee to see their recorded manager and direct reports.")
        self.profile.setWordWrap(True)
        self.profile.setTextFormat(Qt.TextFormat.PlainText)
        self.profile.setMinimumHeight(110)
        profile_layout.addWidget(self.profile)
        right_layout.addWidget(profile_frame)
        right_layout.addWidget(QLabel("Direct reports · identifier match"))
        self.reports = DataTable()
        right_layout.addWidget(self.reports, 1)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 1)
        self.notice = QLabel()
        self.notice.setObjectName("hint")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

    def refresh(self) -> None:
        period = self.as_of.date().toString("yyyy-MM-dd")
        token = _begin_refresh(self)

        def done(employees: list[dict[str, Any]]) -> None:
            if not _is_latest_refresh(self, token):
                return
            self._employees = list(employees or [])
            self.last_result = list(self._employees)
            self._fill_employees()
            if not employees:
                self.notice.setText(
                    "No active roster is available as of this date. Import a roster with employee and manager IDs."
                )
            else:
                self.notice.setText(f"Roster snapshot: {len(employees):,} employee(s) as of {period}.")

        self.run_job(lambda: self.store.employees(period=period), done, title="Loading roster snapshot…")

    def _fill_employees(self) -> None:
        query = self.search.text().strip().casefold()
        rows = []
        for employee in self._employees:
            if query and query not in " ".join(str(value) for value in employee.values()).casefold():
                continue
            rows.append(employee)
        columns = [
            ("Code", "employee_id"),
            ("Employee", "employee_name"),
            ("Role", "designation"),
            ("Store", "store"),
            ("Department", "department"),
            ("Manager code", "manager_id"),
        ]
        self.employees_table.fill(rows, columns)
        self.reports.fill([])
        self.profile.setText("Select an employee to see their recorded manager and direct reports.")

    def _selected_employee(self) -> None:
        selected = self.employees_table.selectionModel().selectedRows()
        if not selected:
            return
        index = selected[0].row()
        employee_id = self.employees_table.item(index, 0)
        if employee_id is None:
            return
        code = employee_id.text()
        employee = next((row for row in self._employees if str(row.get("employee_id", "")) == code), None)
        if not employee:
            return
        manager_id = employee.get("manager_id")
        manager = next((row for row in self._employees if manager_id and str(row.get("employee_id", "")) == str(manager_id)), None)
        reports = [row for row in self._employees if row.get("manager_id") not in (None, "") and str(row.get("manager_id")) == code]
        name = employee.get("employee_name") or code
        manager_name = (manager or {}).get("employee_name") or employee.get("manager_name") or "Not recorded"
        self.profile.setText(
            f"{name} · {employee.get('designation') or 'Role not recorded'}\n"
            f"Employee code: {code or 'Not recorded'}\n"
            f"Manager: {manager_name} · {manager_id or 'No manager ID recorded'}\n"
            f"Direct reports by manager ID: {len(reports):,}"
        )
        self.reports.fill(
            reports,
            [("Code", "employee_id"), ("Employee", "employee_name"), ("Role", "designation"),
             ("Department", "department"), ("Store", "store")],
        )


class AnalysisPage(QWidget):
    def __init__(self, store: Any, run_job: Callable):
        super().__init__()
        self.store = store
        self.run_job = run_job
        self.result: dict[str, Any] | None = None
        self.last_result: dict[str, Any] | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(empty_panel(
            "Performance analysis",
            "Transparent analysis of the imported reports and the available score criteria. "
            "A score is provisional unless all approved criteria are known; absent fields are not treated as zero.",
        ))
        self.filters = FilterBar(self.store, kind="sales_mtd")
        self.filters.kind.currentIndexChanged.connect(self.refresh)
        self.filters.period_from.dateChanged.connect(self.refresh)
        self.filters.period_to.dateChanged.connect(self.refresh)
        self.filters.store.currentIndexChanged.connect(self.refresh)
        self.filters.department.currentIndexChanged.connect(self.refresh)
        self.filters.section.currentIndexChanged.connect(self.refresh)
        self.filters.employee.textChanged.connect(self.refresh)
        layout.addWidget(self.filters)
        toolbar = QHBoxLayout()
        self.export_pdf = QPushButton("Export PDF")
        self.export_xlsx = QPushButton("Export Excel")
        self.export_csv = QPushButton("Export CSV")
        self.export_pdf.clicked.connect(lambda: self._export("pdf"))
        self.export_xlsx.clicked.connect(lambda: self._export("xlsx"))
        self.export_csv.clicked.connect(lambda: self._export("csv"))
        toolbar.addWidget(QLabel("Reports use this filter scope:"))
        toolbar.addStretch(1)
        toolbar.addWidget(self.export_pdf)
        toolbar.addWidget(self.export_xlsx)
        toolbar.addWidget(self.export_csv)
        layout.addLayout(toolbar)
        self.cards = MetricCards()
        layout.addWidget(self.cards)
        self.chart = ChartPanel("Performance evidence · actual, budget, last year")
        layout.addWidget(self.chart)
        self.status = QLabel("Select filters to see the calculation evidence.")
        self.status.setObjectName("warning")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.commentary = QLabel()
        self.commentary.setObjectName("panel")
        self.commentary.setWordWrap(True)
        layout.addWidget(self.commentary)
        self.evidence = DataTable()
        self.evidence.setMinimumHeight(140)
        layout.addWidget(self.evidence, 1)
        layout.addWidget(QLabel("Source report batches"))
        self.sources_table = DataTable()
        self.sources_table.setMinimumHeight(120)
        layout.addWidget(self.sources_table, 1)

    def refresh(self) -> None:
        self.filters.refresh_dimensions()
        filters = self.filters.filters()
        token = _begin_refresh(self)

        def done(result: dict[str, Any]) -> None:
            if not _is_latest_refresh(self, token):
                return
            self.result = result
            self.last_result = result
            self.cards.set_entries(report_values(result))
            self.chart.set_data(result.get("trends") or [], mode="grouped")
            score = result.get("score") or {}
            score_name = score.get("status") or score.get("label") or "Provisional"
            warnings = result.get("warnings") or []
            commentary = result.get("commentary") or []
            message = f"Performance assessment: {score_name}. "
            if score.get("score") is not None:
                message += f"Reported score: {score['score']}. "
            message += str(score.get("note") or "Components are evidence only.")
            if warnings:
                message += " Notes: " + " · ".join(str(value) for value in warnings)
            self.status.setText(message)
            self.commentary.setText("\n".join(f"• {line}" for line in commentary) or "No additional commentary for this selection.")
            components = score.get("components") or {}
            evidence = [
                {"metric": key.replace("_", " ").title(), **(value if isinstance(value, dict) else {"value": value})}
                for key, value in components.items()
            ]
            self.evidence.fill(
                evidence,
                [("Metric", "metric"), ("Value", "value"), ("Evidence", "evidence")],
            )
            sources = []
            for source in result.get("sources") or []:
                sheet, header_row = split_sheet_identity(source.get("sheet"))
                sources.append({**source, "source_sheet": sheet, "header_row": header_row})
            self.sources_table.fill(
                sources,
                [("Import ID", "import_id"), ("Type", "kind"), ("Period", "period"),
                 ("Source file", "source"), ("Worksheet", "source_sheet"), ("Header row", "header_row")],
            )

        self.run_job(lambda: analyze(self.store, filters), done, title="Analyzing report evidence…")

    def _export(self, fmt: str) -> None:
        if not self.result:
            QMessageBox.information(self, "Nothing to export", "Run the analysis first.")
            return
        from PySide6.QtWidgets import QFileDialog

        ext, file_filter = {
            "pdf": ("pdf", "PDF report (*.pdf)"),
            "xlsx": ("xlsx", "Excel workbook (*.xlsx)"),
            "csv": ("csv", "CSV report (*.csv)"),
        }[fmt]
        path, _ = QFileDialog.getSaveFileName(self, "Export report", f"PNO-report.{ext}", file_filter)
        if not path:
            return
        from pathlib import Path

        target = Path(path).expanduser()
        if target.suffix.casefold() != f".{ext}":
            target = target.with_suffix(f".{ext}")
        snapshot = deepcopy(self.result)
        for source in snapshot.get("sources") or []:
            sheet, header_row = split_sheet_identity(source.get("sheet"))
            source["sheet"] = sheet
            if header_row is not None:
                source["header_row"] = int(header_row)
        filters = dict(snapshot.get("filters") or {})

        def work() -> str:
            export_report(snapshot, target, format=fmt, filters=filters)
            return str(target)

        def done(saved: str) -> None:
            QMessageBox.information(self, "Export complete", f"Report exported locally:\n{saved}")

        self.run_job(work, done, title=f"Exporting {fmt.upper()} report…")
