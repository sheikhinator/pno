"""P&O pages: Command Center, Leaders 360°, Turnover, Roster, plus workbook import."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import canon, privacy
from .insights import DEFAULT_WEIGHTS, WEIGHT_LABELS, Insights, Leader, tenure_text
from .po_format import (
    BAD, GOOD, NEUTRAL, SEVERITY_COLOR, STATUS_COLOR, WARN,
    leader_name, leader_profile_html, money, number, pct, pp, score_text, tone,
)
from .ui_helpers import BRAND_BROWN, BRAND_GOLD, MetricCards, empty_panel
from .workbook_pack import PACK_KINDS, import_pack, scan_pack

SETTINGS = ("PNO", "WorkforceAnalytics")


def load_weights() -> dict[str, float]:
    settings = QSettings(*SETTINGS)
    raw = settings.value("po/weights", "")
    try:
        stored = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        stored = {}
    weights = dict(DEFAULT_WEIGHTS)
    weights.update({k: float(v) for k, v in stored.items() if k in DEFAULT_WEIGHTS})
    return weights


def save_weights(weights: dict[str, float]) -> None:
    QSettings(*SETTINGS).setValue("po/weights", json.dumps(weights))


def load_demo_mode() -> bool:
    value = QSettings(*SETTINGS).value("po/demo_mode", False)
    enabled = str(value).lower() in {"true", "1"}
    privacy.set_demo_mode(enabled)
    return enabled


def build_insights(store: Any) -> Insights:
    return Insights(store, weights=load_weights())


# ----------------------------------------------------------- widgets --

def _panel(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 16)
    layout.setSpacing(8)
    heading = QLabel(title)
    heading.setStyleSheet(f"font-size:16px;font-weight:700;color:{BRAND_BROWN}")
    layout.addWidget(heading)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        layout.addWidget(sub)
    return frame, layout


def _item(text: str, sort_value: Any = None, color: str | None = None, bold: bool = False,
          background: str | None = None, align_right: bool = False) -> QTableWidgetItem:
    item = _SortItem(text)
    item.sort_value = sort_value
    if color:
        item.setForeground(QColor(color))
    if background:
        item.setBackground(QColor(background))
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    if align_right:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class _SortItem(QTableWidgetItem):
    sort_value: Any = None

    def __lt__(self, other: QTableWidgetItem) -> bool:  # numeric sort when available
        mine = self.sort_value
        theirs = getattr(other, "sort_value", None)
        if isinstance(mine, (int, float)) and isinstance(theirs, (int, float)):
            return mine < theirs
        if isinstance(mine, (int, float)):
            return False
        if isinstance(theirs, (int, float)):
            return True
        return self.text() < other.text()


class Table(QTableWidget):
    def __init__(self, max_rows: int = 16) -> None:
        super().__init__()
        self.max_rows = max_rows
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)

    def set_rows(self, headers: list[str], rows: list[list[QTableWidgetItem]], sortable: bool = True) -> None:
        self.setSortingEnabled(False)
        self.clear()
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, item in enumerate(row):
                self.setItem(r, c, item)
        self.resizeColumnsToContents()
        self.setSortingEnabled(sortable)
        height = self.horizontalHeader().height() + sum(self.rowHeight(i) for i in range(min(len(rows), self.max_rows))) + 22
        self.setMinimumHeight(min(max(height, 120), 760))


def heat_color(value: float | None, good: float, bad: float, higher_is_better: bool = True) -> str:
    if value is None:
        return "#F4F2EE"
    v, g, b = (value, good, bad) if higher_is_better else (-value, -good, -bad)
    if v >= g:
        return "#CFE6D5"
    if v <= b:
        return "#F3CFCB"
    return "#F7E7C2"


class HBars(QWidget):
    """Horizontal bar list: [(label, value)]."""

    def __init__(self, color: str = BRAND_GOLD) -> None:
        super().__init__()
        self.items: list[tuple[str, float]] = []
        self.color = color
        self.setMinimumHeight(60)

    def set_items(self, items: list[tuple[str, float]]) -> None:
        self.items = items
        self.setMinimumHeight(max(60, 26 * len(items) + 8))
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.items:
            painter.setPen(QColor(NEUTRAL))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data yet")
            return
        top = max(v for _, v in self.items) or 1
        label_w = min(240, int(self.width() * 0.42))
        for i, (label, value) in enumerate(self.items):
            y = 4 + i * 26
            painter.setPen(QColor("#28231F"))
            painter.drawText(QRectF(0, y, label_w - 8, 22), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
            width = max(2.0, (self.width() - label_w - 50) * value / top)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.color))
            painter.drawRoundedRect(QRectF(label_w, y + 4, width, 15), 4, 4)
            painter.setPen(QColor("#28231F"))
            painter.drawText(QRectF(label_w + width + 6, y, 44, 22), Qt.AlignmentFlag.AlignVCenter, number(value, 0))


class VBars(QWidget):
    """Monthly column chart: [(label, value)]."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[tuple[str, float]] = []
        self.setMinimumHeight(200)

    def set_items(self, items: list[tuple[str, float]]) -> None:
        self.items = items
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.items:
            painter.setPen(QColor(NEUTRAL))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data yet")
            return
        top = max(max(v for _, v in self.items), 1)
        n = len(self.items)
        left, bottom = 8, 34
        slot = (self.width() - left * 2) / n
        h = self.height() - bottom - 18
        painter.setPen(QPen(QColor("#E7E2D9")))
        painter.drawLine(left, self.height() - bottom, self.width() - left, self.height() - bottom)
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 2))
        for i, (label, value) in enumerate(self.items):
            x = left + i * slot
            bh = h * value / top
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(BRAND_BROWN if i == n - 1 else BRAND_GOLD))
            painter.drawRoundedRect(QRectF(x + slot * 0.15, self.height() - bottom - bh, slot * 0.7, bh), 3, 3)
            painter.setFont(small)
            painter.setPen(QColor("#28231F"))
            if value:
                painter.drawText(QRectF(x, self.height() - bottom - bh - 16, slot, 14), Qt.AlignmentFlag.AlignCenter, number(value, 0))
            if i % max(1, n // 12) == 0 or i == n - 1:
                painter.setPen(QColor(NEUTRAL))
                painter.drawText(QRectF(x - 10, self.height() - bottom + 4, slot + 20, 28), Qt.AlignmentFlag.AlignHCenter, label)


class TalentGrid(QWidget):
    leader_clicked = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.insights: Insights | None = None
        self.setMinimumHeight(470)
        self._hits: list[tuple[QRectF, str]] = []

    def set_insights(self, insights: Insights) -> None:
        self.insights = insights
        self.update()

    def mousePressEvent(self, event: Any) -> None:
        pos = event.position()
        for rect, key in self._hits:
            if rect.contains(pos):
                self.leader_clicked.emit(key)
                return

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._hits = []
        left, top, bottom = 60, 8, 40
        w = (self.width() - left - 10) / 3
        h = (self.height() - top - bottom) / 3
        fills = {
            (2, 2): "#CFE6D5", (1, 2): "#E1EFE4", (2, 1): "#E1EFE4", (1, 1): "#F4F0E6",
            (0, 2): "#F7E7C2", (2, 0): "#F7E7C2", (0, 1): "#F7E7C2", (1, 0): "#F7E7C2", (0, 0): "#F3CFCB",
        }
        groups: dict[tuple[int, int], list[Leader]] = {}
        if self.insights:
            for leader in self.insights.leaders():
                box = self.insights.talent_box(leader)
                if box:
                    groups.setdefault(box, []).append(leader)
        small = QFont(self.font())
        small.setPointSizeF(max(7.5, small.pointSizeF() - 1.5))
        for col in range(3):
            for row in range(3):
                rect = QRectF(left + col * w + 3, top + (2 - row) * h + 3, w - 6, h - 6)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(fills[(col, row)]))
                painter.drawRoundedRect(rect, 10, 10)
                painter.setPen(QColor(BRAND_BROWN))
                bold = QFont(self.font())
                bold.setBold(True)
                painter.setFont(bold)
                members = groups.get((col, row), [])
                painter.drawText(rect.adjusted(10, 6, -10, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                                 f"{Insights.TALENT_NAMES[(col, row)]}  ({len(members)})")
                painter.setFont(small)
                y = rect.top() + 28
                for leader in sorted(members, key=lambda l: -(l.score or 0)):
                    if y > rect.bottom() - 16:
                        painter.setPen(QColor(NEUTRAL))
                        painter.drawText(QRectF(rect.left() + 10, y, rect.width() - 20, 16), Qt.AlignmentFlag.AlignLeft, "…")
                        break
                    label = f"● {leader_name(leader)} · {leader.store.replace('LAH ', '').replace('KCH ', '').replace('ISL ', '').replace('FAI ', '').replace('GUJ ', '')}"
                    hit = QRectF(rect.left() + 10, y, rect.width() - 20, 16)
                    painter.setPen(QColor("#28231F"))
                    painter.drawText(hit, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
                    self._hits.append((hit, leader.key))
                    y += 17
        painter.setPen(QColor(NEUTRAL))
        painter.setFont(self.font())
        for i, text in enumerate(("Results low", "Results on plan", "Results strong")):
            painter.drawText(QRectF(left + i * w, self.height() - bottom + 6, w, 20), Qt.AlignmentFlag.AlignCenter, text)
        for i, text in enumerate(("Rated ≥4", "Rated 3", "Rated ≤2")):
            painter.drawText(QRectF(0, top + i * h, left - 6, h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)


# ------------------------------------------------------------ base page --

class _PoPage(QWidget):
    title = ""
    intro = ""

    def __init__(self, store: Any, run_job: Callable, navigate: Callable[[str], None] | None = None) -> None:
        super().__init__()
        self.store = store
        self.run_job = run_job
        self.navigate = navigate or (lambda _key: None)
        self.insights: Insights | None = None
        self._refresh_token = 0
        self._last_completed_token = 0
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 22, 24, 22)
        self.layout_.setSpacing(12)
        self.empty = empty_panel(
            "Import the P&O workbook to begin",
            "Go to Imports & history → “Import full P&O workbook”. All tabs (productivity, roster, ratings, sales, "
            "NPS, shrinkage, time in role, DA, turnover, Basic Sheet) are recognised automatically.",
        )
        go = QPushButton("Open workbook import")
        go.setObjectName("primaryButton")
        go.clicked.connect(lambda: self.navigate("imports"))
        self.empty.layout().addWidget(go, 0, Qt.AlignmentFlag.AlignLeft)
        self.layout_.addWidget(self.empty)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        self.layout_.addWidget(self.body, 1)
        self.build()
        self.refresh()

    def build(self) -> None:  # pragma: no cover - overridden
        pass

    def render(self, insights: Insights) -> None:  # pragma: no cover - overridden
        pass

    def refresh(self) -> None:
        load_demo_mode()
        self._refresh_token += 1
        token = self._refresh_token

        def done(insights: Insights) -> None:
            if token != self._refresh_token:
                return
            self._last_completed_token = token
            self.insights = insights
            self.empty.setVisible(insights.empty)
            self.body.setVisible(not insights.empty)
            if not insights.empty:
                self.render(insights)

        self.run_job(lambda: build_insights(self.store), done, title=f"Refreshing {self.title.lower()}…")


# ------------------------------------------------------- command center --

HEAT_METRICS = [
    ("Sales vs budget (%)", "sales_vs_budget", 100, 92, True, "{:.0f}%"),
    ("Sales growth vs LY (%)", "growth", 5, 0, True, "{:+.0f}%"),
    ("Productivity vs target (%)", "productivity_vs_target", 0, -10, True, "{:+.0f}%"),
    ("Shrinkage vs budget (pp)", "shrink_variance", 0, -1, True, "{:+.1f}"),
    ("Stock days vs budget (%)", "stock_days", 105, 130, False, "{:.0f}%"),
    ("Out of stock (%)", "oos", 8, 15, False, "{:.1f}%"),
    ("Net margin (%)", "margin", 5, 0, True, "{:.1f}%"),
]


class CommandCenterPage(_PoPage):
    title = "Command Center"
    export_pack: Callable[[], None] | None = None

    def build(self) -> None:
        hero = QFrame()
        hero.setObjectName("hero")
        hero.setStyleSheet(f"QFrame#hero {{ background:{BRAND_BROWN}; border-radius:14px; }} QFrame#hero QLabel {{ background:transparent; }}")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(22, 18, 22, 18)
        text = QVBoxLayout()
        eyebrow = QLabel("CARREFOUR PAKISTAN · PEOPLE & ORGANISATION")
        eyebrow.setStyleSheet(f"color:{BRAND_GOLD};font-weight:800;letter-spacing:1.5px;font-size:11px")
        self.hero_title = QLabel("Country P&O Command Center")
        self.hero_title.setStyleSheet("color:white;font-size:24px;font-weight:800")
        self.hero_sub = QLabel("")
        self.hero_sub.setStyleSheet("color:#D9CFBF;font-size:12px")
        self.hero_sub.setWordWrap(True)
        text.addWidget(eyebrow)
        text.addWidget(self.hero_title)
        text.addWidget(self.hero_sub)
        hl.addLayout(text, 1)
        buttons = QVBoxLayout()
        self.pack_button = QPushButton("Export board pack (PDF)")
        self.pack_button.setObjectName("goldButton")
        self.excel_button = QPushButton("Export data workbook (Excel)")
        for b in (self.pack_button, self.excel_button):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(b)
        hl.addLayout(buttons)
        self.body_layout.addWidget(hero)
        self.pack_button.clicked.connect(lambda: export_dialog(self, "pdf"))
        self.excel_button.clicked.connect(lambda: export_dialog(self, "xlsx"))

        self.cards = MetricCards()
        self.body_layout.addWidget(self.cards)

        league, ll = _panel("Store league table", "Every store on one line. Click a column to sort. Status combines sales vs budget, productivity vs target and shrinkage.")
        self.league = Table(max_rows=24)
        ll.addWidget(self.league)
        self.body_layout.addWidget(league)

        heat, hlay = _panel("Section heatmap", "Stores × sections. Green = on plan, amber = watch, red = action. Grey = no data in the workbook.")
        row = QHBoxLayout()
        row.addWidget(QLabel("Measure"))
        self.heat_metric = QComboBox()
        for label, *_ in HEAT_METRICS:
            self.heat_metric.addItem(label)
        self.heat_metric.currentIndexChanged.connect(lambda _i: self.insights and self._render_heat(self.insights))
        row.addWidget(self.heat_metric)
        row.addStretch(1)
        hlay.addLayout(row)
        self.heat = Table(max_rows=24)
        hlay.addWidget(self.heat)
        self.body_layout.addWidget(heat)

        alerts, al = _panel("What needs attention", "Automatically generated from every tab and ranked by severity and size.")
        self.alerts = QTextBrowser()
        self.alerts.setMinimumHeight(330)
        self.alerts.setOpenExternalLinks(False)
        al.addWidget(self.alerts)
        self.body_layout.addWidget(alerts)
        self.sources = QLabel()
        self.sources.setObjectName("hint")
        self.sources.setWordWrap(True)
        self.body_layout.addWidget(self.sources)

    def render(self, insights: Insights) -> None:
        h = insights.headline()
        self.hero_sub.setText(
            f"{h['stores']} stores · {h['leaders']} section leaders · data as of {h['as_of']:%d %b %Y}"
            + (" · Presentation mode: names hidden" if privacy.demo_mode() else "")
        )
        self.cards.set_entries([
            ("Sales MTD", money(h["sales"]), f"{pct(h['sales_vs_budget_pct'], digits=1)} of budget"),
            ("Growth vs last year", pct(h["growth_pct"], True), "Country, all stores"),
            ("Productivity vs target", pct(h["productivity_vs_target_pct"], True), "Average across stores (YTD)"),
            ("Stores on track", f"{h['stores_on_track']} / {h['stores']}", f"{h['stores_at_risk']} at risk"),
            ("Section leaders", str(h["leaders"]), f"Avg rating {number(h['avg_rating'], 2)}"),
            ("Leavers · 12 months", number(h["leavers_12m"]), f"{pct(h['voluntary_pct'], digits=0)} voluntary"),
            ("Disciplinary cases", number(h["da_cases"]), "From the DA tab"),
            ("Open alerts", str(len(insights.alerts())), f"{sum(1 for a in insights.alerts() if a['severity'] == 'High')} high priority"),
        ])
        rows = []
        for c in insights.store_scorecard():
            rows.append([
                _item(c["store"], bold=True),
                _item(c["status"], color="white", background=STATUS_COLOR[c["status"]], bold=True),
                _item(money(c["sales"]), c["sales"], align_right=True),
                _item(pct(c["sales_vs_budget_pct"], digits=0), c["sales_vs_budget_pct"], tone(c["sales_vs_budget_pct"], 100, 92), True, align_right=True),
                _item(pct(c["growth_pct"], True), c["growth_pct"], tone(c["growth_pct"], 5, 0), align_right=True),
                _item(pct(c["productivity_vs_target_pct"], True, 0), c["productivity_vs_target_pct"], tone(c["productivity_vs_target_pct"], 0, -10), True, align_right=True),
                _item(pp(c["shrink_variance_avg"]), c["shrink_variance_avg"], tone(c["shrink_variance_avg"], 0, -1), align_right=True),
                _item(pct(c["oos_pct"]), c["oos_pct"], tone(c["oos_pct"], 8, 15, False), align_right=True),
                _item(pct(c["margin_pct"]), c["margin_pct"], align_right=True),
                _item(number(c["nps"], 0), c["nps"], align_right=True),
                _item(number(c["leavers_12m"]), c["leavers_12m"], tone(c["leavers_12m"], 2, 6, False) if c["leavers_12m"] is not None else None, align_right=True),
                _item(number(c["da_cases"]), c["da_cases"], align_right=True),
                _item(score_text(c["avg_leader_score"]), c["avg_leader_score"], tone(c["avg_leader_score"], 70, 45), True, align_right=True),
            ])
        self.league.set_rows(["Store", "Status", "Sales", "vs Budget", "Growth", "Prod. vs target", "Shrink vs bud.",
                              "OOS", "Margin", "NPS", "Leavers 12m", "DA", "Leader index"], rows)
        self._render_heat(insights)
        html = ["<table width='100%' cellspacing='0' cellpadding='6'>"]
        for a in insights.alerts(25):
            color = SEVERITY_COLOR[a["severity"]]
            html.append(
                f"<tr><td width='70'><span style='color:white;background:{color};font-weight:700'>&nbsp;{a['severity']}&nbsp;</span></td>"
                f"<td width='110' style='color:#756E68;font-weight:700'>{a['area']}</td>"
                f"<td width='190'><b>{a['store']}</b></td><td>{_escape(a['message'])}</td></tr>")
        html.append("</table>")
        self.alerts.setHtml("".join(html))
        self.sources.setText("Sources · " + " · ".join(f"{PACK_KINDS[k]}: {v}" for k, v in sorted(insights.sources.items())))

    def _render_heat(self, insights: Insights) -> None:
        label, metric, good, bad, higher, fmt = HEAT_METRICS[self.heat_metric.currentIndex()]
        stores, sections, values = insights.section_matrix(metric)
        rows = []
        for store_name in stores:
            row = [_item(store_name, bold=True)]
            for section in sections:
                v = values.get((store_name, section))
                row.append(_item("" if v is None else fmt.format(v), v, background=heat_color(v, good, bad, higher),
                                 align_right=True))
            rows.append(row)
        short = {"Fruits & Vegetables": "F&V", "Light Household": "LHH", "Heavy Household": "HHH"}
        self.heat.set_rows(["Store"] + [short.get(s, s) for s in sections], rows)


def _escape(text: str) -> str:
    from html import escape
    return escape(text)


# ------------------------------------------------------------- leaders --

class LeadersPage(_PoPage):
    title = "Leaders 360°"

    def build(self) -> None:
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search leader name or employee number…")
        self.search.textChanged.connect(lambda _t: self._fill_list())
        self.store_filter = QComboBox()
        self.store_filter.currentIndexChanged.connect(lambda _i: self._fill_list())
        bar.addWidget(self.search, 2)
        bar.addWidget(self.store_filter, 1)
        self.body_layout.addLayout(bar)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { padding:8px 16px; font-weight:600 } QTabBar::tab:selected { color:#31261D; border-bottom:3px solid #B5975A }")
        # 360
        page = QWidget()
        pl = QHBoxLayout(page)
        pl.setContentsMargins(0, 8, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.table = Table()
        self.table.itemSelectionChanged.connect(self._select)
        split.addWidget(self.table)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.profile = QTextBrowser()
        self.profile.setMinimumWidth(430)
        self.profile.setStyleSheet("QTextBrowser { background:white; border:1px solid #E7E2D9; border-radius:12px; padding:12px }")
        rl.addWidget(self.profile, 1)
        buttons = QHBoxLayout()
        self.one_pager = QPushButton("Export one-pager (PDF)")
        self.one_pager.clicked.connect(self._export_one_pager)
        buttons.addWidget(self.one_pager)
        buttons.addStretch(1)
        rl.addLayout(buttons)
        split.addWidget(right)
        split.setSizes([620, 520])
        pl.addWidget(split)
        page.setMinimumHeight(640)
        self.tabs.addTab(page, "Leader 360°")
        # talent
        talent = QWidget()
        tl = QVBoxLayout(talent)
        hint = QLabel("Appraisal rating (vertical) against the business results of the area each leader runs (horizontal). "
                      "Click a name to open their 360°. Leaders without both a rating and results are not placed.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        tl.addWidget(hint)
        self.grid = TalentGrid()
        self.grid.leader_clicked.connect(self._open_leader)
        tl.addWidget(self.grid, 1)
        self.tabs.addTab(talent, "Talent grid")
        # bench
        bench = QWidget()
        bl = QVBoxLayout(bench)
        hint2 = QLabel("Roles at risk: people not yet in the HR system, acting (DOA) leaders, designation mismatches, new joiners in role, low ratings.")
        hint2.setObjectName("hint")
        hint2.setWordWrap(True)
        bl.addWidget(hint2)
        self.bench = Table()
        self.bench.itemDoubleClicked.connect(lambda item: self._open_leader(self.bench.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)))
        bl.addWidget(self.bench, 1)
        self.tabs.addTab(bench, "Bench strength")
        self.body_layout.addWidget(self.tabs, 1)
        self._pending_key: str | None = None

    def render(self, insights: Insights) -> None:
        current = self.store_filter.currentText()
        self.store_filter.blockSignals(True)
        self.store_filter.clear()
        self.store_filter.addItem("All stores")
        for s in sorted({l.store for l in insights.leaders() if l.store}):
            self.store_filter.addItem(s)
        index = self.store_filter.findText(current)
        self.store_filter.setCurrentIndex(max(0, index))
        self.store_filter.blockSignals(False)
        self._fill_list()
        self.grid.set_insights(insights)
        rows = []
        for f in insights.bench():
            leader = f["leader"]
            first = _item(f["severity"], {"High": 0, "Medium": 1, "Low": 2}[f["severity"]], "white", True, SEVERITY_COLOR[f["severity"]])
            first.setData(Qt.ItemDataRole.UserRole, leader.key)
            rows.append([first, _item(leader_name(leader), bold=True), _item(leader.store), _item(leader.section_text),
                         _item(leader.designation), _item(f["reason"])])
        self.bench.set_rows(["Priority", "Leader", "Store", "Leads", "Designation", "Why flagged"], rows)

    def _fill_list(self) -> None:
        if not self.insights:
            return
        query = self.search.text().strip()
        store_name = self.store_filter.currentText()
        leaders = self.insights.find_leader(query) if query else self.insights.leaders()
        if store_name and store_name != "All stores":
            leaders = [l for l in leaders if l.store == store_name]
        ranks = {l.key: i + 1 for i, l in enumerate(l for l in self.insights.leaders() if l.score is not None)}
        rows = []
        for leader in leaders:
            first = _item(str(ranks.get(leader.key, "—")), ranks.get(leader.key), align_right=True)
            first.setData(Qt.ItemDataRole.UserRole, leader.key)
            rows.append([
                first, _item(leader_name(leader), bold=True), _item(leader.store), _item(leader.section_text),
                _item(leader.designation),
                _item(score_text(leader.score), leader.score, tone(leader.score, 70, 45), True, align_right=True),
                _item("—" if leader.latest_rating is None else f"{leader.latest_rating:g}", leader.latest_rating, align_right=True),
                _item(tenure_text(leader.months_in_role), leader.months_in_role, align_right=True),
            ])
        self.table.set_rows(["#", "Leader", "Store", "Leads", "Role", "Index", "Rating", "In role"], rows)
        if rows:
            target = self._pending_key
            row_index = 0
            if target:
                for r in range(self.table.rowCount()):
                    if self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) == target:
                        row_index = r
            self.table.selectRow(row_index)
            self._pending_key = None
        else:
            self.profile.setHtml("<p style='color:#756E68'>No leader matches this search.</p>")

    def _current(self) -> Leader | None:
        if not self.insights:
            return None
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        key = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return next((l for l in self.insights.leaders() if l.key == key), None)

    def _select(self) -> None:
        leader = self._current()
        if leader and self.insights:
            self.profile.setHtml(leader_profile_html(self.insights, leader))

    def _open_leader(self, key: str) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.store_filter.setCurrentIndex(0)
        self._pending_key = key
        self._fill_list()
        self.tabs.setCurrentIndex(0)

    def _export_one_pager(self) -> None:
        leader = self._current()
        if not leader or not self.insights:
            return
        from .po_reports import export_leader_pdf

        default = f"{leader_name(leader).replace(' ', '_')}_360.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Save leader one-pager", default, "PDF (*.pdf)")
        if not path:
            return
        insights = self.insights
        self.run_job(lambda: export_leader_pdf(insights, leader, path), lambda _r: QMessageBox.information(self, "Saved", f"Saved {path}"),
                     title="Building one-pager…")


# ------------------------------------------------------------ turnover --

class TurnoverPage(_PoPage):
    title = "Turnover"

    def build(self) -> None:
        self.cards = MetricCards()
        self.body_layout.addWidget(self.cards)
        trend, tl = _panel("Leavers per month · last 24 months", "By requested date. The darkest bar is the latest month.")
        self.monthly = VBars()
        tl.addWidget(self.monthly)
        self.body_layout.addWidget(trend)
        row = QHBoxLayout()
        reasons, rl = _panel("Why people leave · last 12 months")
        self.reasons = HBars()
        rl.addWidget(self.reasons)
        stores, sl = _panel("Leavers by store · last 12 months")
        self.stores = HBars(BRAND_BROWN)
        sl.addWidget(self.stores)
        row.addWidget(reasons, 1)
        row.addWidget(stores, 1)
        self.body_layout.addLayout(row)
        hot, hl = _panel("Hotspots · store × section", "Where leavers concentrate in the last 12 months.")
        self.hotspots = Table()
        hl.addWidget(self.hotspots)
        self.body_layout.addWidget(hot)
        recent, rl2 = _panel("Most recent leavers")
        self.recent = Table()
        rl2.addWidget(self.recent)
        self.body_layout.addWidget(recent)
        self.note = QLabel()
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        self.body_layout.addWidget(self.note)

    def render(self, insights: Insights) -> None:
        t = insights.turnover_summary()
        types = dict(t["by_type"])
        self.cards.set_entries([
            ("Leavers · 12 months", str(t["total"]), f"{t['all_time']} on file in total"),
            ("Voluntary", pct(t["voluntary_pct"], digits=0), f"{types.get('Resignation', 0)} resignations"),
            ("Terminations", str(types.get("Termination", 0)), f"{types.get('Absconding', 0)} absconded"),
            ("Top reason", t["by_reason"][0][0] if t["by_reason"] else "—", f"{t['by_reason'][0][1]} leavers" if t["by_reason"] else ""),
        ])
        self.monthly.set_items([(f"{date.fromisoformat(m + '-01'):%b %y}", n) for m, n in t["monthly"]])
        self.reasons.set_items(t["by_reason"][:9])
        self.stores.set_items(t["by_store"][:12])
        self.hotspots.set_rows(["Store", "Section", "Leavers", "Share"], [
            [_item(s, bold=True), _item(sec), _item(str(n), n, tone(n, 3, 6, False), True, align_right=True),
             _item(pct(100 * n / t["total"], digits=0) if t["total"] else "—", n, align_right=True)]
            for s, sec, n in t["hotspots"]])
        recent = sorted((r for r in insights.rows("po_turnover") if r.get("date")), key=lambda r: r["date"], reverse=True)[:25]
        self.recent.set_rows(["Date", "Name", "Store", "Section", "Type", "Reason"], [
            [_item(r["date"], r["date"]), _item(privacy.name(r["employee_name"], r.get("employee_id") or r["employee_name"])),
             _item(r["store"]), _item(r["section"]), _item(r["exit_type"]), _item(r["reason"])] for r in recent])
        self.note.setText("Counts use the requested date. Many records carry salary period 2025-12 regardless of date; "
                          "please confirm with HR operations which date is the official exit date.")


# -------------------------------------------------------------- roster --

SHIFT_STYLE = {
    "Morning": ("M", "#DCEBDF"), "Mid": ("Mid", "#E8E1F2"), "Evening": ("E", "#F7E7C2"),
    "Off": ("Off", "#EEEAE2"), "Leave": ("AL", "#F3CFCB"), "Inventory": ("Inv", "#D6E4F0"),
    "Not rostered": ("", "#FFFFFF"), "Other": ("?", "#FFFFFF"),
}


class RosterPage(_PoPage):
    title = "Roster coverage"

    def build(self) -> None:
        self.cards = MetricCards()
        self.body_layout.addWidget(self.cards)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Store"))
        self.store_box = QComboBox()
        self.store_box.currentIndexChanged.connect(lambda _i: self.insights and self._render_grid(self.insights))
        bar.addWidget(self.store_box)
        legend = QLabel("   ".join(f"<span style='background:{c}'>&nbsp;{code or ' '}&nbsp;</span> {name}"
                                     for name, (code, c) in SHIFT_STYLE.items() if name not in {"Not rostered", "Other"}))
        legend.setTextFormat(Qt.TextFormat.RichText)
        bar.addWidget(legend)
        bar.addStretch(1)
        self.body_layout.addLayout(bar)
        grid, gl = _panel("Shift grid", "Every section leader, every day of the month. Morning till 11, Mid till 2, Evening after 2.")
        self.grid = Table()
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        gl.addWidget(self.grid)
        self.body_layout.addWidget(grid)
        row = QHBoxLayout()
        gaps, gpl = _panel("Coverage gaps", "Days when every rostered leader of a department is off or on leave.")
        self.gaps = Table()
        gpl.addWidget(self.gaps)
        leave, lpl = _panel("Leave this month")
        self.leave = Table()
        lpl.addWidget(self.leave)
        row.addWidget(gaps, 1)
        row.addWidget(leave, 1)
        self.body_layout.addLayout(row)

    def render(self, insights: Insights) -> None:
        r = insights.roster_summary()
        mix = r.get("mix") or {}
        worked = mix.get("Morning", 0) + mix.get("Mid", 0) + mix.get("Evening", 0)
        span = f"{r['days'][0]} – {r['days'][-1]}" if r.get("days") else "—"
        self.cards.set_entries([
            ("Leaders rostered", str(r.get("people", 0)), span),
            ("Morning share", pct(100 * mix.get("Morning", 0) / worked if worked else None, digits=0), "of worked shifts"),
            ("Evening share", pct(100 * mix.get("Evening", 0) / worked if worked else None, digits=0), "of worked shifts"),
            ("Coverage gaps", str(len(r.get("gaps", []))), "department-days with no leader"),
        ])
        current = self.store_box.currentText()
        self.store_box.blockSignals(True)
        self.store_box.clear()
        known = [name for name, *_ in canon._STORES]
        ordered = sorted(r.get("stores", []), key=lambda n: (known.index(n) if n in known else 99, n))
        for s in ordered:
            self.store_box.addItem(s)
        if current:
            self.store_box.setCurrentIndex(max(0, self.store_box.findText(current)))
        self.store_box.blockSignals(False)
        self._render_grid(insights)
        self.gaps.set_rows(["Store", "Department", "Date", "Leaders"], [
            [_item(g["store"], bold=True), _item(g["department"]), _item(g["date"], g["date"]), _item(str(g["leaders"]), g["leaders"])]
            for g in r.get("gaps", [])])
        self.leave.set_rows(["Leader", "Store", "Leave days"], [
            [_item(privacy.name(n, n), bold=True), _item(s), _item(str(d), d, tone(d, 3, 6, False), align_right=True)]
            for n, s, d in r.get("leave", [])])

    def _render_grid(self, insights: Insights) -> None:
        store_name = self.store_box.currentText()
        rows = [x for x in insights.rows("po_shift") if x["store"] == store_name]
        days = sorted({x["date"] for x in rows})
        people: dict[str, dict[str, Any]] = {}
        for x in rows:
            p = people.setdefault(x["employee_id"], {"name": x["employee_name"], "section": x["section"], "designation": x["designation"], "days": {}})
            p["days"][x["date"]] = x["shift"]
        table_rows = []
        for emp, p in sorted(people.items(), key=lambda kv: (canon.department(kv[1]["section"]), kv[1]["section"], kv[1]["name"])):
            row = [_item(privacy.name(p["name"], emp), bold=True), _item(p["section"])]
            for d in days:
                code, color = SHIFT_STYLE.get(p["days"].get(d, "Not rostered"), ("?", "#FFFFFF"))
                cell = _item(code, background=color)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                row.append(cell)
            table_rows.append(row)
        headers = ["Leader", "Section"] + [date.fromisoformat(d).strftime("%d\n%a") for d in days]
        self.grid.set_rows(headers, table_rows, sortable=False)
        for c in range(2, len(headers)):
            self.grid.setColumnWidth(c, 44)
        self.grid.setMinimumHeight(min(60 + 30 * len(table_rows), 620))


# ------------------------------------------------------- workbook import --

class PackImportDialog(QDialog):
    def __init__(self, plan: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import P&O workbook")
        self.setMinimumWidth(720)
        layout = QVBoxLayout(self)
        title = QLabel(f"<b>{Path(plan.path).name}</b> · {len(plan.sheets)} tab(s) recognised")
        layout.addWidget(title)
        self.list = QListWidget()
        for sheet in plan.sheets:
            text = f"{sheet.label}  ·  tab “{sheet.sheet}”  ·  {sheet.summary}"
            if sheet.warnings:
                text += "\n      ⚠ " + "\n      ⚠ ".join(sheet.warnings)
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, sheet.kind)
            self.list.addItem(item)
        for note in plan.skipped:
            item = QListWidgetItem(f"Skipped · {note}")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(item)
        self.list.setMinimumHeight(360)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        row.addWidget(QLabel("Save as month"))
        self.month = QComboBox()
        today = date.today()
        months = []
        for back in range(0, 15):
            y, m = today.year, today.month - back
            while m <= 0:
                m += 12
                y -= 1
            months.append(f"{y}-{m:02d}")
        for m in months:
            self.month.addItem(m)
        self.month.setCurrentIndex(0)
        row.addWidget(self.month)
        hint = QLabel("Importing the same month again replaces it; other months stay in history.")
        hint.setObjectName("hint")
        row.addWidget(hint, 1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import selected tabs")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self) -> list[str]:
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) and item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out


def pack_import_panel(page: QWidget, store: Any, run_job: Callable, changed: Callable[[], None]) -> QFrame:
    frame, layout = _panel(
        "Import full P&O workbook",
        "One click loads every tab: productivity, roster, ratings, store performance, NPS, shrinkage & stock days, "
        "time in role, DA, turnover and the Basic Sheet. Tabs are recognised by their columns, not their names. "
        "Birth dates, phone numbers, e-mails and marital status are never imported.",
    )
    row = QHBoxLayout()
    button = QPushButton("Import full P&O workbook…")
    button.setObjectName("primaryButton")
    status = QLabel("")
    status.setObjectName("hint")
    status.setWordWrap(True)
    row.addWidget(button)
    row.addWidget(status, 1)
    layout.addLayout(row)

    def choose() -> None:
        path, _ = QFileDialog.getOpenFileName(page, "Choose the P&O workbook", "", "Workbooks (*.xlsx *.xlsm *.xls *.csv *.tsv *.txt)")
        if not path:
            return
        status.setText("Reading workbook…")

        def scanned(plan: Any) -> None:
            if not plan.sheets:
                status.setText("No P&O tabs were recognised in this file. " + "; ".join(plan.skipped))
                return
            dialog = PackImportDialog(plan, page)
            if plan.period_hint:
                pass
            if dialog.exec() != QDialog.DialogCode.Accepted:
                status.setText("Import cancelled · nothing was saved.")
                return
            kinds = dialog.selected()
            month = dialog.month.currentText()

            def saved(messages: list[str]) -> None:
                status.setText("\n".join(messages))
                changed()

            run_job(lambda: import_pack(store, plan, month, kinds), saved, title="Saving workbook tabs…", mutating=True)

        run_job(lambda: scan_pack(path), scanned, title="Reading P&O workbook…",
                on_error=lambda exc: status.setText(f"Could not read workbook: {exc}"))

    button.clicked.connect(choose)
    return frame


# ------------------------------------------------------------- settings --

def po_settings_panel(changed: Callable[[], None]) -> QFrame:
    frame, layout = _panel(
        "P&O index weights & presentation mode",
        "Set how much each measure counts in the leader index. Weights are relative (they don't need to add to 100). "
        "Measures a leader has no data for are left out of their index, never treated as zero.",
    )
    grid = QGridLayout()
    weights = load_weights()
    spins: dict[str, QDoubleSpinBox] = {}
    for i, (key, label) in enumerate(WEIGHT_LABELS.items()):
        spin = QDoubleSpinBox()
        spin.setRange(0, 100)
        spin.setDecimals(0)
        spin.setValue(weights[key])
        spins[key] = spin
        grid.addWidget(QLabel(label), i // 3, (i % 3) * 2)
        grid.addWidget(spin, i // 3, (i % 3) * 2 + 1)
    layout.addLayout(grid)
    demo = QCheckBox("Presentation mode — hide employee names and IDs on every page and in exports")
    demo.setChecked(load_demo_mode())
    layout.addWidget(demo)
    row = QHBoxLayout()
    apply = QPushButton("Apply")
    apply.setObjectName("primaryButton")
    reset = QPushButton("Reset weights")
    row.addWidget(apply)
    row.addWidget(reset)
    row.addStretch(1)
    layout.addLayout(row)

    def do_apply() -> None:
        save_weights({k: s.value() for k, s in spins.items()})
        QSettings(*SETTINGS).setValue("po/demo_mode", demo.isChecked())
        privacy.set_demo_mode(demo.isChecked())
        changed()

    def do_reset() -> None:
        for k, s in spins.items():
            s.setValue(DEFAULT_WEIGHTS[k])

    apply.clicked.connect(do_apply)
    reset.clicked.connect(do_reset)
    demo.toggled.connect(lambda _c: do_apply())
    return frame


# -------------------------------------------------------------- exports --

def export_dialog(page: _PoPage, fmt: str) -> None:
    if not page.insights or page.insights.empty:
        return
    from .po_reports import export_board_pack, export_workbook

    stamp = f"{page.insights.as_of:%Y-%m}"
    if fmt == "pdf":
        path, _ = QFileDialog.getSaveFileName(page, "Save board pack", f"PNO_Board_Pack_{stamp}.pdf", "PDF (*.pdf)")
        func = export_board_pack
    else:
        path, _ = QFileDialog.getSaveFileName(page, "Save data workbook", f"PNO_Data_{stamp}.xlsx", "Excel (*.xlsx)")
        func = export_workbook
    if not path:
        return
    insights = page.insights
    page.run_job(lambda: func(insights, path), lambda _r: QMessageBox.information(page, "Export ready", f"Saved {path}"),
                 title="Building export…")
