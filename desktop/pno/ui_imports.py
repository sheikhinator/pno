"""Workbook selection, safe previews, local column corrections and import history."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .ui_helpers import (
    DataTable,
    FilterBar,
    empty_panel,
)
from .ui_history import ImportHistoryPanel
from .ui_import_commit import save_selected_reports
from .ui_mapping import MappingDialog, coerce_mapped_value, pasted_plan
from .ui_provenance import candidate_key


class ImportsPage(QWidget):
    def __init__(self, store: Any, run_job: Callable, changed: Callable):
        super().__init__()
        self.store = store
        self.run_job = run_job
        self.changed = changed
        self._restore_active = False
        self.plan: Any = None
        self.path: str | None = None
        self.csv_text: str | None = None
        self._scan_token = 0
        self._scanned_kind: str | None = None
        self._scanned_period: str | None = None
        self.mapping_by_sheet: dict[str, dict[str, str]] = {}
        self._reviewed_mappings: set[str] = set()
        self.settings = QSettings("PNO", "WorkforceAnalytics")
        self._build()
        self.reload_history()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)
        intro = empty_panel(
            "Bring your reports in safely",
            "Files are read on this laptop only. Preview every worksheet and its column mappings before saving. "
            "Imports keep a checksum and source worksheet; original workbooks are never copied into the database.",
        )
        root.addWidget(intro)

        controls = QFrame()
        controls.setObjectName("panel")
        control_layout = QVBoxLayout(controls)
        top = QHBoxLayout()
        self.choose_file = QPushButton("Choose Excel / CSV")
        self.choose_file.setObjectName("primaryButton")
        self.paste_button = QPushButton("Paste TSV / CSV")
        self.kind = QComboBox()
        self.kind.addItem("Auto-detect type", None)
        for label, value in (
            ("Roster", "roster"),
            ("Attendance", "attendance"),
            ("Daily sales", "sales_daily"),
            ("Monthly sales (MTD)", "sales_mtd"),
            ("Productivity", "productivity"),
        ):
            self.kind.addItem(label, value)
        self.period = QComboBox()
        self.period.setEditable(True)
        self.period.setPlaceholderText("Report period · YYYY-MM-DD or YYYY-MM")
        self.period.addItems([__import__("datetime").date.today().replace(day=1).isoformat()])
        self.preview_button = QPushButton("Scan & preview")
        self.preview_button.setObjectName("goldButton")
        self.choose_file.clicked.connect(self.select_file)
        self.paste_button.clicked.connect(self.paste_data)
        self.preview_button.clicked.connect(self.scan)
        top.addWidget(self.choose_file)
        top.addWidget(self.paste_button)
        top.addWidget(QLabel("Report type"))
        top.addWidget(self.kind)
        top.addWidget(QLabel("Period"))
        top.addWidget(self.period, 1)
        top.addWidget(self.preview_button)
        control_layout.addLayout(top)
        self.source_label = QLabel("No report selected")
        self.source_label.setObjectName("hint")
        control_layout.addWidget(self.source_label)
        root.addWidget(controls)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QFrame()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Worksheets · select what to import"))
        self.candidates = QListWidget()
        self.candidates.itemSelectionChanged.connect(self.show_candidate)
        self.candidates.itemChanged.connect(self.show_candidate)
        left_layout.addWidget(self.candidates, 1)
        self.map_button = QPushButton("Review column mappings")
        self.map_button.clicked.connect(self.edit_mappings)
        left_layout.addWidget(self.map_button)
        right = QFrame()
        right.setObjectName("panel")
        right_layout = QVBoxLayout(right)
        self.candidate_title = QLabel("Report preview")
        self.candidate_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        right_layout.addWidget(self.candidate_title)
        self.notices = QLabel("Choose a workbook or paste a tabular report, then preview it here.")
        self.notices.setObjectName("hint")
        self.notices.setWordWrap(True)
        right_layout.addWidget(self.notices)
        self.preview = DataTable()
        right_layout.addWidget(self.preview, 1)
        self.save_button = QPushButton("Import selected worksheets")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.import_selected)
        right_layout.addWidget(self.save_button)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        root.addWidget(split, 1)

        self.history_panel = ImportHistoryPanel(self.store)
        root.addWidget(self.history_panel, 1)

    def select_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a report", "", "Reports (*.xlsx *.xlsm *.xls *.csv *.tsv);;All files (*.*)"
        )
        if not path:
            return
        self.path = path
        self.csv_text = None
        self.plan = None
        self._scan_token += 1
        self.source_label.setText(Path(path).name)
        self._reset_preview("Scan the selected report to preview available worksheets.")

    def paste_data(self) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit

        dialog = QDialog(self)
        dialog.setWindowTitle("Paste a delimited report")
        dialog.resize(720, 440)
        layout = QVBoxLayout(dialog)
        label = QLabel("Paste copied spreadsheet cells below. Text stays in memory and a temporary file is not created.")
        label.setWordWrap(True)
        layout.addWidget(label)
        editor = QPlainTextEdit()
        editor.setPlaceholderText("Paste tab-separated or comma-separated rows, including the column headers…")
        layout.addWidget(editor, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text = editor.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "Nothing to preview", "Paste a header row and at least one report row.")
            return
        if self.kind.currentData() is None:
            kind, ok = QInputDialog.getItem(
                self, "Choose report type", "Pasted reports need a type:", ["roster", "attendance", "sales_daily", "sales_mtd", "productivity"], 0, False
            )
            if not ok:
                return
            index = self.kind.findData(kind)
            self.kind.setCurrentIndex(index)
        self.csv_text = text
        self.path = None
        self.plan = None
        self._scan_token += 1
        self.source_label.setText("Pasted report · temporary in-memory text")
        self._reset_preview("Preview the pasted rows, correct their mappings, and then choose Import.")
        self.scan()

    def _period(self) -> str:
        value = self.period.currentText().strip()
        if not value:
            QMessageBox.warning(self, "Period required", "Enter the reporting period (YYYY-MM or YYYY-MM-DD).")
            return ""
        if len(value) == 7:
            value += "-01"
        from datetime import date

        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            QMessageBox.warning(self, "Check the period", "Use YYYY-MM or YYYY-MM-DD for the report period.")
            return ""

    def _reset_preview(self, message: str) -> None:
        self.candidates.clear()
        self.candidate_title.setText("Report preview")
        self.notices.setText(message)
        self.preview.fill([])
        self.save_button.setEnabled(False)

    def scan(self) -> None:
        period = self._period()
        if not period:
            return
        if not self.path and self.csv_text is None:
            QMessageBox.information(self, "Choose a report", "Choose an Excel / CSV report or paste a tabular report first.")
            return
        chosen_kind = self.kind.currentData()
        mappings = self._remembered_mappings()
        path = self.path
        csv_text = self.csv_text
        token = self._scan_token + 1
        self._scan_token = token
        self.save_button.setEnabled(False)

        def work():
            if csv_text is not None:
                return pasted_plan(csv_text, str(chosen_kind), period)
            from .importer import scan_workbook

            return scan_workbook(path, kind=chosen_kind, period=period, mappings=mappings)

        def done(plan: Any) -> None:
            if token != self._scan_token or path != self.path or csv_text != self.csv_text:
                self.notices.setText("This preview was discarded because the selected report changed while it was scanning.")
                return
            self.plan = plan
            self._scanned_kind = chosen_kind
            self._scanned_period = period
            self.mapping_by_sheet = {}
            self.candidates.blockSignals(True)
            self.candidates.clear()
            for candidate in plan.candidates:
                item = QListWidgetItem()
                item.setText(
                    f"{candidate.sheet} · header row {candidate.header_row} · "
                    f"{candidate.kind} · {len(candidate.records):,} rows"
                )
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, candidate)
                self.candidates.addItem(item)
                sheet_map = dict(candidate.column_map or {})
                for header in self._headers(candidate):
                    remembered = self.settings.value(f"mappings/{header}", "")
                    if header not in sheet_map and remembered:
                        sheet_map[header] = str(remembered)
                self.mapping_by_sheet[candidate_key(candidate)] = sheet_map
            self.candidates.blockSignals(False)
            warning_lines = [str(message) for message in getattr(plan, "warnings", [])]
            if warning_lines:
                warning_lines.insert(0, "Workbook notes")
            self.notices.setText(" · ".join(warning_lines) if warning_lines else "Review worksheet type, rows, and any uncertain column mappings.")
            self.save_button.setEnabled(not self._restore_active and bool(plan.candidates))
            if self.candidates.count():
                self.candidates.setCurrentRow(0)
                self.show_candidate()
            else:
                self._reset_preview("No importable worksheets found. Check the header row or choose a report type.")

        self.run_job(work, done, title="Scanning report locally…")

    @staticmethod
    def _headers(candidate: Any) -> list[str]:
        headers = set(getattr(candidate, "column_map", {}).keys())
        for row in candidate.records[:10]:
            if isinstance(row.get("raw"), dict):
                headers.update(row["raw"])
        return sorted(str(header) for header in headers)

    def _selected_candidate(self) -> Any | None:
        selected = self.candidates.selectedItems()
        return selected[0].data(Qt.ItemDataRole.UserRole) if selected else None

    def show_candidate(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        self.candidate_title.setText(
            f"{candidate.sheet} · header row {candidate.header_row} · {candidate.kind} · "
            f"{len(candidate.records):,} rows · {candidate.confidence:.0%} mapping confidence"
        )
        notes = [str(note) for note in candidate.warnings]
        if candidate.kind in ("unknown", "other", ""):
            notes.append("Select a report type before importing this worksheet.")
        if candidate.confidence < 0.65:
            notes.append("Low mapping confidence: verify column mappings before importing.")
        mappings = self.mapping_by_sheet.get(candidate_key(candidate), {})
        if mappings:
            notes.append("Mapped fields: " + ", ".join(mappings.values()))
        self.notices.setText(" · ".join(notes) if notes else "Check the preview and confirm the column mappings look right.")
        preview_records = []
        for record in candidate.records[:100]:
            merged = dict(record.get("raw") or {})
            merged.update({key: value for key, value in record.items() if key != "raw"})
            preview_records.append(merged)
        self.preview.fill(preview_records)

    def edit_mappings(self) -> None:
        candidate = self._selected_candidate()
        if not candidate:
            QMessageBox.information(self, "No worksheet selected", "Run a scan and select a worksheet to edit its mappings.")
            return
        headers = self._headers(candidate)
        if not headers:
            QMessageBox.information(self, "No headers found", "This worksheet has no recognizable column headers.")
            return
        key = candidate_key(candidate)
        before = dict(self.mapping_by_sheet.get(key, {}))
        dialog = MappingDialog(headers, before, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mapping = dialog.mapping
        self.mapping_by_sheet[key] = mapping
        self._reviewed_mappings.add(key)
        for header, field_name in mapping.items():
            self.settings.setValue(f"mappings/{header}", field_name)
        self.settings.sync()
        if self.csv_text is not None:
            # Pasted rows intentionally retain every original value under raw.
            old_fields = set(candidate.column_map.values())
            for record in candidate.records:
                raw = record.get("raw") or {}
                for old_field in old_fields - set(mapping.values()):
                    record.pop(old_field, None)
                for header, key in mapping.items():
                    if header in raw:
                        record[key] = coerce_mapped_value(key, raw[header])
            candidate.column_map = mapping
            self.show_candidate()
            return
        if not self.path:
            return
        path = self.path
        kind = self.kind.currentData()
        period = self._period()
        if not period:
            return
        if period != self._scanned_period or self.kind.currentData() != self._scanned_kind:
            QMessageBox.information(
                self,
                "Preview changed",
                "The selected report type or period differs from the scanned preview. Scan & preview again before importing.",
            )
            return
        self.save_button.setEnabled(False)
        scan_token = self._scan_token
        headers = dict(self._remembered_mappings())
        headers.update(candidate.column_map or {})
        headers.update(mapping)
        old_sheet, old_header = candidate.sheet, candidate.header_row

        def work():
            from .importer import scan_workbook

            return scan_workbook(path, kind=kind, period=period, mappings=headers)

        def done(plan: Any) -> None:
            if scan_token != self._scan_token or path != self.path:
                self.notices.setText("The corrected preview was discarded because the selected report changed while it was scanning.")
                return
            refreshed = next(
                (
                    item for item in plan.candidates
                    if item.sheet == old_sheet and item.header_row == old_header
                ),
                None,
            )
            if refreshed is None:
                QMessageBox.warning(
                    self,
                    "Could not apply mapping",
                    f"The corrected worksheet {old_sheet!r} could not be found after rescanning. "
                    "No corrected data was imported; review the workbook and try again.",
                )
                return
            self.plan = plan
            item = self.candidates.currentItem()
            if item:
                item.setText(
                    f"{refreshed.sheet} · header row {refreshed.header_row} · "
                    f"{refreshed.kind} · {len(refreshed.records):,} rows"
                )
                item.setData(Qt.ItemDataRole.UserRole, refreshed)
            self.save_button.setEnabled(not self._restore_active and bool(plan.candidates))
            self.show_candidate()

        def failed(error: Exception) -> None:
            QMessageBox.critical(self, "Mapping correction failed", str(error))
            self.save_button.setEnabled(False)

        self.run_job(work, done, title="Applying column corrections and rescanning…", on_error=failed)

    def import_selected(self) -> None:
        save_selected_reports(self)

    def _rescan_manual_candidate(self, candidate: Any, kind: str, mapping: dict[str, str]) -> None:
        key = candidate_key(candidate)
        self.mapping_by_sheet[key] = mapping
        self._reviewed_mappings.add(key)
        for header, field_name in mapping.items():
            self.settings.setValue(f"mappings/{header}", field_name)
        self.settings.sync()
        period = self._period()
        if not period:
            return
        source_candidate = candidate
        if self.csv_text is not None:
            source_candidate.kind = kind
            source_candidate.column_map = mapping
            for record in source_candidate.records:
                raw = record.get("raw") or {}
                for header, canonical in mapping.items():
                    if header in raw:
                        record[canonical] = coerce_mapped_value(canonical, raw[header])
            self._scanned_period = period
            self._scanned_kind = self.kind.currentData()
        elif self.path:
            path = self.path
            path_plan = self.plan
            scan_token = self._scan_token
            checksum = path_plan.checksum
            combined = dict(self._remembered_mappings())
            combined.update(candidate.column_map or {})
            combined.update(mapping)
            old_sheet, old_header = candidate.sheet, candidate.header_row
            self.save_button.setEnabled(False)

            def work():
                from .importer import scan_workbook

                return scan_workbook(path, kind=kind, period=period, mappings=combined)

            def done(plan: Any) -> None:
                if scan_token != self._scan_token or path != self.path:
                    self.notices.setText("The corrected preview was discarded because the selected report changed while it was scanning.")
                    return
                refreshed = next(
                    (
                        item for item in plan.candidates
                        if item.sheet == old_sheet and item.header_row == old_header
                    ),
                    None,
                )
                if refreshed is None:
                    QMessageBox.warning(
                        self, "Could not classify worksheet",
                        "The selected worksheet could not be safely rescanned. Nothing was imported.",
                    )
                    return
                path_plan.path = plan.path
                path_plan.checksum = plan.checksum
                path_plan.warnings = plan.warnings
                path_plan.candidates = [
                    refreshed if item.sheet == old_sheet and item.header_row == old_header else item
                    for item in path_plan.candidates
                ]
                self.plan = path_plan
                self._scanned_period = period
                self._scanned_kind = self.kind.currentData()
                row = self.candidates.currentItem()
                if row:
                    row.setText(
                        f"{refreshed.sheet} · header row {refreshed.header_row} · "
                        f"{refreshed.kind} · {len(refreshed.records):,} rows"
                    )
                    row.setData(Qt.ItemDataRole.UserRole, refreshed)
                self.save_button.setEnabled(not self._restore_active and bool(path_plan.candidates))
                self.notices.setText(
                    "Manual type and column corrections are shown. Verify the preview, then select Import again."
                )
                self.show_candidate()

            def failed(error: Exception) -> None:
                QMessageBox.critical(self, "Could not classify worksheet", str(error))
                self.save_button.setEnabled(False)

            self.run_job(work, done, title="Applying report type and rescanning locally…", on_error=failed)
            return
        row = self.candidates.currentItem()
        if row:
            row.setText(
                f"{source_candidate.sheet} · header row {source_candidate.header_row} · "
                f"{kind} · {len(source_candidate.records):,} rows"
            )
        self.notices.setText(
            "Manual type and column corrections are shown. Verify the preview, then select Import again."
        )
        self.show_candidate()

    def _remembered_mappings(self) -> dict[str, str]:
        mappings = {}
        for key in self.settings.allKeys():
            if key.startswith("mappings/"):
                value = self.settings.value(key)
                if value:
                    mappings[key.removeprefix("mappings/")] = str(value)
        return mappings

    def reload_history(self, *_: Any) -> None:
        self.history_panel.reload(*_)

    def refresh(self) -> None:
        self.history_panel.refresh()

