"""Small local-only helpers for pasted reports and correcting workbook headers."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .ui_helpers import CANONICAL_FIELDS


@dataclass
class PastedPlan:
    path: str
    checksum: str
    candidates: list[Any]
    warnings: list[str] = field(default_factory=list)


@dataclass
class PastedCandidate:
    kind: str
    sheet: str
    header_row: int
    records: list[dict[str, Any]]
    warnings: list[str]
    confidence: float
    column_map: dict[str, str]


def coerce_mapped_value(field_name: str, value: Any) -> Any:
    """Only numeric metrics are converted; codes such as 00123 stay strings."""
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    if not trimmed:
        return None
    numeric_fields = {
        "actual",
        "budget",
        "last_year",
        "oos_value",
        "oos_pct",
        "hours",
        "productivity",
        "productivity_ly",
        "productivity_growth",
    }
    if field_name not in numeric_fields:
        return trimmed
    cleaned = trimmed.replace(",", "").replace("%", "").strip()
    try:
        number = float(cleaned)
    except ValueError:
        return trimmed
    return int(number) if number.is_integer() else number


def pasted_plan(text: str, kind: str, period: str) -> PastedPlan:
    sample = text[:8192]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters="\t,;").delimiter
    except csv.Error:
        delimiter = "\t" if "\t" in sample else ","
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    if len(rows) < 2 or not any(cell.strip() for cell in rows[0]):
        raise ValueError("Paste at least a header row and one data row.")
    headers = [cell.strip() for cell in rows[0]]
    if len(set(headers)) != len(headers):
        raise ValueError("Column headers must be unique. Rename duplicate columns before pasting.")
    records = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        padded = row[: len(headers)] + [""] * max(0, len(headers) - len(row))
        records.append({"raw": {header: padded[index].strip() or None for index, header in enumerate(headers)}})
    return PastedPlan(
        path="Pasted report (temporary)",
        checksum=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        candidates=[
            PastedCandidate(
                kind=kind,
                sheet="Pasted data",
                header_row=1,
                records=records,
                warnings=["Pasted rows are previewed locally. Verify column mappings before importing."],
                confidence=0.35,
                column_map={},
            )
        ],
        warnings=["Tab-delimited text detected." if delimiter == "\t" else "Delimited text detected."],
    )


class MappingDialog(QDialog):
    """A compact, explicit per-header canonical mapping editor."""

    def __init__(self, headers: list[str], mapping: dict[str, str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Review column mappings")
        self.setMinimumSize(590, 440)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Mapped fields affect how rows are interpreted. Unmapped columns stay in their original form; "
            "no missing metrics are created."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QTableWidget(len(headers), 2)
        self.table.setHorizontalHeaderLabels(["Workbook column", "Interpret as"])
        self.table.verticalHeader().hide()
        for row, header in enumerate(headers):
            item = QTableWidgetItem(header)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
            combo = QComboBox()
            combo.addItems(CANONICAL_FIELDS)
            current = mapping.get(header, "")
            index = combo.findText(current)
            combo.setCurrentIndex(index if index >= 0 else 0)
            self.table.setCellWidget(row, 1, combo)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        apply = QPushButton("Apply mappings")
        apply.setObjectName("primaryButton")
        cancel.clicked.connect(self.reject)
        apply.clicked.connect(self._accept_mapping)
        buttons.addWidget(cancel)
        buttons.addWidget(apply)
        layout.addLayout(buttons)

    def _accept_mapping(self) -> None:
        self.mapping = {}
        for row in range(self.table.rowCount()):
            header = self.table.item(row, 0).text()
            field_name = self.table.cellWidget(row, 1).currentText()
            if field_name:
                self.mapping[header] = field_name
        self.accept()

    @staticmethod
    def open_dialog(headers: list[str], mapping: dict[str, str], parent: QWidget) -> dict[str, str] | None:
        dialog = MappingDialog(headers, mapping, parent)
        return dialog.mapping if dialog.exec() == QDialog.DialogCode.Accepted else None
