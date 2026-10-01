"""Reusable widgets, filters, tables and charts for the native desktop UI."""

from __future__ import annotations

import json
from typing import Any
import math

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

BRAND_BROWN = "#31261D"
BRAND_GOLD = "#B5975A"
BRAND_WHITE = "#FFFFFF"
MUTED = "#756E68"
CANONICAL_FIELDS = [
    "",
    "store",
    "department",
    "section",
    "employee_id",
    "employee_name",
    "designation",
    "grade",
    "gender",
    "manager_id",
    "manager_name",
    "date",
    "status",
    "in_time",
    "out_time",
    "hours",
    "actual",
    "budget",
    "last_year",
    "oos_value",
    "oos_pct",
    "productivity",
    "productivity_ly",
    "productivity_growth",
]

APP_STYLE = f"""
QWidget {{ background: #F5F3EF; color: #28231F; font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
QMainWindow, QDialog {{ background: #F5F3EF; }}
QLabel#eyebrow {{ color: {BRAND_GOLD}; font-weight: 700; letter-spacing: 1.2px; }}
QLabel#pageTitle {{ color: {BRAND_BROWN}; font-size: 25px; font-weight: 700; }}
QLabel#pageSubtitle {{ color: {MUTED}; font-size: 13px; }}
QFrame#sidebar {{ background: {BRAND_BROWN}; border: none; }}
QFrame#sidebar QLabel {{ background: transparent; color: #F8F6F1; }}
QPushButton#navButton {{ background: transparent; color: #E6DFD3; border: none; text-align: left; padding: 12px 14px; border-radius: 8px; font-weight: 600; }}
QPushButton#navButton:hover {{ background: #493B30; }}
QPushButton#navButton[active="true"] {{ background: #554330; color: #F0D392; border-left: 3px solid {BRAND_GOLD}; }}
QPushButton {{ color: #30271F; background: #ECE6DA; border: 1px solid #DED5C7; border-radius: 8px; padding: 8px 13px; font-weight: 600; }}
QPushButton:hover {{ background: #E0D5C3; }}
QPushButton:disabled {{ color: #9C9489; background: #EFEEEB; }}
QPushButton#primaryButton {{ color: white; background: {BRAND_BROWN}; border-color: {BRAND_BROWN}; }}
QPushButton#primaryButton:hover {{ background: #493B30; }}
QPushButton#goldButton {{ background: {BRAND_GOLD}; border-color: {BRAND_GOLD}; color: #fff; }}
QPushButton#dangerButton {{ color: #8D3329; }}
QLineEdit, QComboBox, QDateEdit, QSpinBox {{ background: white; border: 1px solid #DED8CE; border-radius: 7px; padding: 8px; min-height: 20px; }}
QComboBox QAbstractItemView {{ background: white; selection-background-color: #E8DEC9; }}
QFrame#card, QFrame#panel {{ background: white; border: 1px solid #E7E2D9; border-radius: 13px; }}
QLabel#metricValue {{ color: {BRAND_BROWN}; font-size: 24px; font-weight: 700; }}
QLabel#metricLabel {{ color: {MUTED}; font-size: 11px; font-weight: 700; }}
QLabel#hint {{ color: {MUTED}; }}
QLabel#warning {{ color: #795B1D; background: #F8F0DF; border: 1px solid #EBD9B0; border-radius: 8px; padding: 9px; }}
QLabel#success {{ color: #2C6743; background: #ECF4EC; border: 1px solid #D3E7D3; border-radius: 8px; padding: 9px; }}
QLabel#error {{ color: #8D3329; background: #F9ECE9; border: 1px solid #ECCFCA; border-radius: 8px; padding: 9px; }}
QTableWidget {{ background: white; alternate-background-color: #FAF9F6; border: 1px solid #E7E2D9; border-radius: 9px; gridline-color: #F0EDE8; selection-background-color: #EDE3CF; selection-color: #30271F; }}
QHeaderView::section {{ background: #F3F0EA; color: #685F55; padding: 9px; border: none; border-bottom: 1px solid #E4DDD2; font-weight: 700; }}
QTextEdit, QPlainTextEdit {{ background: white; border: 1px solid #E1DBD1; border-radius: 9px; padding: 8px; }}
QProgressBar {{ background: #EEEAE2; border: none; border-radius: 5px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {BRAND_GOLD}; border-radius: 5px; }}
QScrollArea {{ border: none; }}
"""


def qdate_iso(widget: QDateEdit) -> str | None:
    value = widget.date()
    if value == widget.minimumDate():
        return None
    return value.toString("yyyy-MM-dd") if value.isValid() else None


class FilterBar(QFrame):
    """Consistent report scope controls; unset dates mean the complete available range."""

    def __init__(
        self,
        store: Any,
        kind: str = "sales_mtd",
        include_kind: bool = True,
        all_dates: bool = False,
    ):
        super().__init__()
        self.setObjectName("panel")
        self._store = store
        outer = QVBoxLayout(self)
        outer.setContentsMargins(13, 9, 13, 9)
        row = QHBoxLayout()
        row.setSpacing(8)
        scope_row = QHBoxLayout()
        scope_row.setSpacing(8)

        self.kind = QComboBox()
        self.kind.addItem("Monthly sales", "sales_mtd")
        self.kind.addItem("Daily sales", "sales_daily")
        self.kind.addItem("Attendance", "attendance")
        self.kind.addItem("Productivity", "productivity")
        index = self.kind.findData(kind)
        self.kind.setCurrentIndex(max(index, 0))
        self.kind.setVisible(include_kind)
        if include_kind:
            row.addWidget(self.kind)

        self.period_from = QDateEdit()
        self.period_to = QDateEdit()
        minimum = QDate(1752, 9, 14) if all_dates else QDate(2000, 1, 1)
        for control, offset in ((self.period_from, -89), (self.period_to, 0)):
            control.setCalendarPopup(True)
            control.setDisplayFormat("dd MMM yyyy")
            control.setSpecialValueText("Any date")
            control.setMinimumDate(minimum)
            control.setDate(minimum if all_dates and control is self.period_from else QDate.currentDate().addDays(offset))
        row.addWidget(QLabel("From"))
        row.addWidget(self.period_from, 1)
        row.addWidget(QLabel("To"))
        row.addWidget(self.period_to, 1)
        row.addStretch(1)

        dimensions: dict[str, list[str]] = {}
        try:
            dimensions = store.dimensions()
        except Exception:
            pass
        self.store = self._dimension_box("All stores", dimensions.get("stores", []))
        self.department = self._dimension_box("All departments", dimensions.get("departments", []))
        self.section = self._dimension_box("All sections", dimensions.get("sections", []))
        scope_row.addWidget(self.store, 1)
        scope_row.addWidget(self.department, 1)
        scope_row.addWidget(self.section, 1)
        self.employee = QLineEdit()
        self.employee.setPlaceholderText("Employee name / code")
        scope_row.addWidget(self.employee, 2)
        outer.addLayout(row)
        outer.addLayout(scope_row)

    @staticmethod
    def _dimension_box(label: str, values: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItem(label, "")
        for value in values:
            if value is not None:
                text = str(value)
                combo.addItem(text, text)
        combo.setMinimumWidth(110)
        return combo

    def filters(self, default_kind: str | None = None) -> dict[str, Any]:
        return {
            "kind": str(self.kind.currentData() or default_kind or "sales_mtd"),
            "period_from": qdate_iso(self.period_from),
            "period_to": qdate_iso(self.period_to),
            "store": self.store.currentData() or None,
            "department": self.department.currentData() or None,
            "section": self.section.currentData() or None,
            "employee": self.employee.text().strip() or None,
        }

    def refresh_dimensions(self) -> None:
        try:
            dimensions = self._store.dimensions()
        except Exception:
            return
        for control, key, title in (
            (self.store, "stores", "All stores"),
            (self.department, "departments", "All departments"),
            (self.section, "sections", "All sections"),
        ):
            previous = control.currentData()
            was_blocked = control.blockSignals(True)
            try:
                control.clear()
                control.addItem(title, "")
                for value in dimensions.get(key, []):
                    if value is not None:
                        text = str(value)
                        control.addItem(text, text)
                index = control.findData(previous)
                control.setCurrentIndex(index if index >= 0 else 0)
            finally:
                control.blockSignals(was_blocked)


class MetricCards(QWidget):
    def __init__(self, entries: list[tuple[str, str, str]] | None = None):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.set_entries(entries or [])

    def set_entries(self, entries: list[tuple[str, str, str]]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, (label, value, note) in enumerate(entries):
            card = QFrame()
            card.setObjectName("card")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(15, 12, 15, 12)
            caption = QLabel(label.upper())
            caption.setObjectName("metricLabel")
            amount = QLabel(value)
            amount.setObjectName("metricValue")
            amount.setWordWrap(True)
            sub = QLabel(note)
            sub.setObjectName("hint")
            sub.setWordWrap(True)
            layout.addWidget(caption)
            layout.addWidget(amount)
            layout.addWidget(sub)
            self.grid.addWidget(card, index // 4, index % 4)


class DataTable(QTableWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)

    def fill(self, rows: list[dict[str, Any]], columns: list[tuple[str, str]] | None = None, cap: int = 5000) -> None:
        rows = rows[:cap]
        if columns is None:
            keys: list[str] = []
            for row in rows[:25]:
                for key in row:
                    if not key.startswith("_") and key != "raw" and key not in keys:
                        keys.append(key)
            columns = [(key.replace("_", " ").title(), key) for key in keys[:14]]
        self.setSortingEnabled(False)
        self.clear()
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels([label for label, _ in columns])
        self.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, (_, key) in enumerate(columns):
                value = row.get(key)
                if value is None:
                    text = "—"
                elif isinstance(value, (dict, list)):
                    text = json.dumps(value, ensure_ascii=False, default=str)
                else:
                    text = str(value)
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, value if isinstance(value, (int, float)) else None)
                self.setItem(i, j, item)
        self.resizeColumnsToContents()
        self.setSortingEnabled(True)


class ChartPanel(QFrame):
    """Small native chart painted with QtWidgets/QPainter (no Qt Charts module)."""

    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("panel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        heading = QLabel(title)
        heading.setStyleSheet(f"font-weight: 700; color: {BRAND_BROWN}; font-size: 15px;")
        self._layout.addWidget(heading)
        self._view: QWidget | None = None
        self.set_data([])

    def set_data(self, trends: list[dict[str, Any]], series_names: tuple[str, ...] = ("actual", "budget", "last_year"), mode: str = "line") -> None:
        if self._view:
            self._layout.removeWidget(self._view)
            self._view.deleteLater()
        valid_rows = [row for row in trends if any(self._clean(row.get(key)) is not None for key in series_names)]
        if not valid_rows:
            label = QLabel("No chart data for this scope yet")
            if trends:
                label.setText("No numeric values are available in this report scope")
            label.setObjectName("hint")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(205)
            self._view = label
            self._layout.addWidget(label)
            return
        view = ChartCanvas(valid_rows, series_names, mode)
        view.setMinimumHeight(245)
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view = view
        self._layout.addWidget(view)

    @staticmethod
    def _clean(value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
            return number if number == number and abs(number) != float("inf") else None
        except (TypeError, ValueError):
            return None

class ChartCanvas(QWidget):
    """Legible grouped-bar/line chart with absent cells kept as visual gaps."""

    PALETTE = ("#31261D", "#B5975A", "#9F968A", "#63796C", "#906C6C")

    def __init__(self, rows: list[dict[str, Any]], names: tuple[str, ...], mode: str):
        super().__init__()
        self.rows = rows
        self.names = names
        self.mode = "line" if mode == "line" else "grouped"
        self.setMinimumHeight(230)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    @staticmethod
    def _format(value: float) -> str:
        magnitude = abs(value)
        if magnitude >= 1_000_000:
            return f"{value / 1_000_000:.1f}m"
        if magnitude >= 10_000:
            return f"{value / 1_000:.0f}k"
        if magnitude >= 1_000:
            return f"{value / 1_000:.1f}k"
        if magnitude >= 100:
            return f"{value:,.0f}"
        if magnitude >= 10:
            return f"{value:,.1f}"
        return f"{value:,.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _category(row: dict[str, Any], index: int) -> str:
        value = str(row.get("period", row.get("date", index + 1))).replace("T00:00:00", "")
        if len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
            try:
                from datetime import date
                parsed = date.fromisoformat(value[:10])
                return parsed.strftime("%b %d")
            except ValueError:
                pass
        return value[:14]

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        width, height = self.width(), self.height()
        left, right, top, bottom = 62, 16, 22, 64
        graph = self.rect().adjusted(left, top, -right, -bottom)
        if graph.width() <= 0 or graph.height() <= 0:
            return
        values = [
            ChartPanel._clean(row.get(key))
            for row in self.rows for key in self.names
        ]
        numbers = [value for value in values if value is not None]
        if not numbers:
            painter.end()
            return
        minimum, maximum = min(numbers), max(numbers)
        if self.mode == "grouped":
            minimum = min(0.0, minimum)
        padding = (maximum - minimum) * 0.12 or max(abs(maximum) * 0.12, 1.0)
        if self.mode == "line":
            minimum -= padding
        maximum += padding
        if maximum <= minimum:
            maximum = minimum + 1.0
        y_at = lambda value: graph.bottom() - (value - minimum) / (maximum - minimum) * graph.height()
        painter.setFont(self.font())
        fm = QFontMetrics(painter.font())
        painter.setPen(QPen(QColor("#EBE7E0"), 1))
        for tick in range(5):
            ratio = tick / 4
            value = minimum + (maximum - minimum) * ratio
            y = round(graph.bottom() - ratio * graph.height())
            painter.drawLine(graph.left(), y, graph.right(), y)
            painter.setPen(QColor("#756E68"))
            painter.drawText(0, y - 8, left - 10, 18, Qt.AlignmentFlag.AlignRight, self._format(value))
            painter.setPen(QPen(QColor("#EBE7E0"), 1))
        categories = [self._category(row, i) for i, row in enumerate(self.rows)]
        slot = graph.width() / max(1, len(self.rows))
        visible_limit = 10
        skip = max(1, math.ceil(len(categories) / visible_limit))
        painter.setPen(QPen(QColor("#756E68"), 1))
        for index, category in enumerate(categories):
            if index % skip:
                continue
            center = graph.left() + (index + 0.5) * slot
            shown = category
            max_chars = max(5, int(slot / max(fm.averageCharWidth(), 1)))
            if len(shown) > max_chars:
                shown = shown[: max(2, max_chars - 1)] + "…"
            painter.drawText(
                int(center - slot), graph.bottom() + 10, int(slot * 2),
                fm.height() + 4, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, shown,
            )

        active_series = [
            key for key in self.names
            if any(ChartPanel._clean(row.get(key)) is not None for row in self.rows)
        ]
        if self.mode == "grouped":
            inner_width = slot * 0.78 / max(1, len(active_series))
            for series_index, key in enumerate(active_series):
                color = QColor(self.PALETTE[series_index % len(self.PALETTE)])
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                for index, row in enumerate(self.rows):
                    value = ChartPanel._clean(row.get(key))
                    if value is None:
                        continue
                    center = graph.left() + (index + 0.5) * slot
                    x = center - inner_width * len(active_series) / 2 + series_index * inner_width
                    zero = y_at(0.0)
                    y = y_at(value)
                    rect_top = min(y, zero)
                    rect_height = max(1, abs(zero - y))
                    painter.drawRoundedRect(int(x), int(rect_top), max(1, int(inner_width - 2)), int(rect_height), 2, 2)
        else:
            for series_index, key in enumerate(active_series):
                color = QColor(self.PALETTE[series_index % len(self.PALETTE)])
                pen = QPen(color, 2)
                painter.setPen(pen)
                prior: tuple[float, float] | None = None
                for index, row in enumerate(self.rows):
                    value = ChartPanel._clean(row.get(key))
                    if value is None:
                        prior = None
                        continue
                    point = (
                        graph.left() + (index + 0.5) * slot,
                        y_at(value),
                    )
                    if prior:
                        painter.drawLine(int(prior[0]), int(prior[1]), int(point[0]), int(point[1]))
                    painter.setBrush(color)
                    painter.drawEllipse(int(point[0] - 3), int(point[1] - 3), 6, 6)
                    prior = point

        legend_y = height - 24
        painter.setFont(self.font())
        legend_width = max(110, graph.width() // max(1, len(active_series)))
        for index, key in enumerate(active_series):
            x = graph.left() + index * legend_width
            color = QColor(self.PALETTE[index % len(self.PALETTE)])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(x, legend_y + 2, 11, 11, 3, 3)
            painter.setPen(QColor("#574E46"))
            label = key.replace("_", " ").title()
            painter.drawText(x + 17, legend_y, legend_width - 20, 18, Qt.AlignmentFlag.AlignLeft, label)


def display_number(value: Any, suffix: str = "", precision: int = 1) -> str:
    if value is None or value == "":
        return "—"
    try:
        number = float(value)
        if number == int(number):
            return f"{number:,.0f}{suffix}"
        return f"{number:,.{precision}f}{suffix}"
    except (TypeError, ValueError):
        return f"{value}{suffix}"


def empty_panel(title: str, message: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    heading = QLabel(title)
    heading.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {BRAND_BROWN};")
    body = QLabel(message)
    body.setObjectName("hint")
    body.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(body)
    return frame
