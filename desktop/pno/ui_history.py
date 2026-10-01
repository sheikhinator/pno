"""Searchable local import-batch history with period and report-scope filters."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from .ui_helpers import DataTable, FilterBar
from .ui_provenance import split_sheet_identity


class ImportHistoryPanel(QWidget):
    """Queryable metadata history; detail-scope filters hide inactive batches."""

    def __init__(self, store: Any):
        super().__init__()
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        heading = QLabel("Import history")
        heading.setStyleSheet("font-size: 17px; font-weight: 700;")
        root.addWidget(heading)
        self.filters = FilterBar(self.store, include_kind=False, all_dates=True)
        root.addWidget(self.filters)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search type, period, workbook, or worksheet")
        self.notice = QLabel()
        self.notice.setObjectName("hint")
        query = QHBoxLayout()
        query.addWidget(self.search, 2)
        query.addWidget(self.notice, 1)
        root.addLayout(query)
        self.table = DataTable()
        root.addWidget(self.table, 1)
        self.filters.period_from.dateChanged.connect(self.reload)
        self.filters.period_to.dateChanged.connect(self.reload)
        for control in (self.filters.store, self.filters.department, self.filters.section):
            control.currentIndexChanged.connect(self.reload)
        self.filters.employee.textChanged.connect(self.reload)
        self.search.textChanged.connect(self.reload)
        self.reload()

    def reload(self, *_: Any) -> None:
        try:
            batches = self.store.list_imports()
        except Exception as exc:
            self.notice.setText(f"Could not read history: {exc}")
            self.table.fill([])
            return
        filters = self.filters.filters()
        scoped = any(filters.get(key) for key in ("store", "department", "section", "employee"))
        matching_ids: set[int] | None = None
        if scoped:
            try:
                rows = self.store.records(
                    period_from=filters.get("period_from"),
                    period_to=filters.get("period_to"),
                    store=filters.get("store"),
                    department=filters.get("department"),
                    section=filters.get("section"),
                    employee=filters.get("employee"),
                )
                matching_ids = {
                    int(row["_import_id"]) for row in rows if row.get("_import_id") is not None
                }
            except Exception as exc:
                self.notice.setText(f"Could not filter import history: {exc}")
                return
        query = self.search.text().strip().casefold()
        results = []
        for batch in batches:
            period = str(batch.get("period", ""))
            if filters["period_from"] and period and period < filters["period_from"]:
                continue
            if filters["period_to"] and period and period > filters["period_to"]:
                continue
            if matching_ids is not None and (
                not batch.get("active") or int(batch.get("id", -1)) not in matching_ids
            ):
                continue
            source_sheet, header_row = split_sheet_identity(batch.get("sheet"))
            batch = {
                **batch,
                "source_sheet": source_sheet,
                "header_row": header_row,
            }
            haystack = " ".join(
                str(batch.get(key, ""))
                for key in ("kind", "period", "source", "source_sheet", "header_row")
            ).casefold()
            if query and query not in haystack:
                continue
            results.append(batch)
        self.table.fill(
            results,
            [
                ("State", "active"),
                ("Type", "kind"),
                ("Period", "period"),
                ("Source file", "source"),
                ("Worksheet", "source_sheet"),
                ("Header row", "header_row"),
                ("Rows", "count"),
                ("Imported", "created_at"),
            ],
        )
        note = " · dimension filters show active batches only" if scoped else " · includes superseded reports"
        self.notice.setText(f"{len(results):,} batch(es){note}")

    def refresh(self) -> None:
        self.filters.refresh_dimensions()
        self.reload()
