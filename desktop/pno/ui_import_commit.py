"""Explicit duplicate/correction decisions and per-worksheet bulk-import results."""

from __future__ import annotations

from collections import Counter
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox

from .ui_mapping import MappingDialog
from .ui_provenance import candidate_key, stored_sheet_identity


def save_selected_reports(page: Any) -> None:
    """Validate the scanned selection, request destructive confirmations, then import batches."""
    if page.plan is None:
        return
    period = page._period()
    if not period:
        return
    if period != page._scanned_period or page.kind.currentData() != page._scanned_kind:
        QMessageBox.information(
            page,
            "Preview changed",
            "The selected report type or period differs from the scanned preview. Scan & preview again before importing.",
        )
        return

    selected = []
    for index in range(page.candidates.count()):
        item = page.candidates.item(index)
        if item.checkState() != Qt.CheckState.Checked:
            continue
        candidate = item.data(Qt.ItemDataRole.UserRole)
        if candidate.kind in ("unknown", "other", ""):
            kind, ok = QInputDialog.getItem(
                page,
                "Choose report type",
                f"Type for {candidate.sheet}:",
                ["roster", "attendance", "sales_daily", "sales_mtd", "productivity"],
                0,
                False,
            )
            if not ok:
                return
            mapping = MappingDialog.open_dialog(
                page._headers(candidate),
                page.mapping_by_sheet.get(candidate_key(candidate), {}),
                page,
            )
            if mapping is None or not mapping:
                QMessageBox.warning(
                    page,
                    "Type-specific mapping required",
                    "Map at least one source header, then review the corrected preview before importing.",
                )
                return
            page._rescan_manual_candidate(candidate, kind, mapping)
            return
        selected.append(candidate)
    if not selected:
        QMessageBox.information(page, "Nothing selected", "Tick at least one worksheet to import.")
        return

    try:
        batches = page.store.list_imports()
    except Exception as exc:
        QMessageBox.critical(page, "Could not read import history", str(exc))
        return

    requests, skipped = [], []
    sheet_counts = Counter(candidate.sheet for candidate in page.plan.candidates)
    for candidate in selected:
        identity = stored_sheet_identity(
            candidate.sheet,
            candidate.header_row,
            sheet_counts[candidate.sheet] > 1,
        )
        same = [
            batch for batch in batches
            if batch.get("active")
            and batch.get("kind") == candidate.kind
            and batch.get("period") == period
            and batch.get("sheet") in {candidate.sheet, identity}
        ]
        exact = next(
            (
                batch for batch in same
                if batch.get("checksum") == page.plan.checksum
                and batch.get("sheet") == identity
            ),
            None,
        )
        if exact:
            reply = QMessageBox.question(
                page,
                "Duplicate report detected",
                f"An identical active import already exists for {candidate.sheet!r}, "
                f"header row {candidate.header_row}, and {period}.\n\n"
                "Keep the existing batch and skip this duplicate?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            skipped.append(
                f"{candidate.sheet}, header row {candidate.header_row}: identical active import already exists."
            )
            continue
        replace = False
        if same:
            reply = QMessageBox.question(
                page,
                "Confirm report correction",
                f"An active {candidate.kind.replace('_', ' ')} report already exists for {period} "
                f"on {candidate.sheet}, header row {candidate.header_row}.\n\n"
                "Replace the active report data from this source row? "
                "The earlier batch is retained but will be inactive.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply != QMessageBox.StandardButton.Yes:
                skipped.append(f"{candidate.sheet}, header row {candidate.header_row}: kept the existing report.")
                continue
            replace = True
        requests.append((candidate, replace, identity))
    if not requests:
        message = "No new report was imported."
        if skipped:
            message += "\n\n" + "\n".join(skipped)
        QMessageBox.information(page, "Nothing imported", message)
        return

    corrections = sum(
        candidate_key(candidate) in page._reviewed_mappings
        for candidate, _, _ in requests
    )
    if corrections:
        reply = QMessageBox.question(
            page,
            "Confirm corrected worksheet mappings",
            f"You reviewed column mappings for {corrections} selected worksheet(s). "
            "Import these corrected mappings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

    checksum = page.plan.checksum
    source = str(page.path) if page.path else "Pasted report (memory only)"
    batch_requests = [
        {
            "kind": candidate.kind,
            "period": period,
            "records": candidate.records,
            "source": source,
            "checksum": checksum,
            "sheet": identity,
            "replace": replace,
        }
        for candidate, replace, identity in requests
    ]
    page.save_button.setEnabled(False)

    def work():
        imported, failures = [], []
        for request in batch_requests:
            try:
                batch_id = page.store.import_records(**request)
                imported.append((request["sheet"], batch_id, len(request["records"])))
            except Exception as exc:
                failures.append((request["sheet"], str(exc)))
        return imported, failures, skipped

    def done(result: Any) -> None:
        imported, failures, skipped_rows = result
        page.save_button.setEnabled(
            not getattr(page, "_restore_active", False) and page.plan is not None
        )
        summary = []
        if imported:
            summary.append(
                f"Imported {len(imported)} worksheet(s), "
                f"{sum(item[2] for item in imported):,} rows."
            )
        if skipped_rows:
            summary.append("Skipped:\n" + "\n".join(skipped_rows))
        if failures:
            summary.append(
                "Errors (some selected worksheets were not imported):\n"
                + "\n".join(f"{sheet}: {message}" for sheet, message in failures)
            )
        QMessageBox.information(page, "Import results", "\n\n".join(summary) or "No report data was imported.")
        if imported:
            page.changed()
        page.reload_history()

    page.run_job(work, done, title="Saving selected report worksheets…", mutating=True)
