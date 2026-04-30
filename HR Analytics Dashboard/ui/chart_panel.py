from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from matplotlib.patches import Circle
import matplotlib.pyplot as plt

from core import analytics
from ui.chart_widget import ChartWithToolbar

_LABEL_STYLE = 'font-size: 11px; color: #555555; font-family: Arial;'

_COMBO_STYLE = '''
    QComboBox {
        border: 1px solid #CCCCCC; border-radius: 4px;
        padding: 4px 6px; background: white; font-size: 12px; color: #333;
    }
    QComboBox:focus { border-color: #2E75B6; }
    QComboBox::drop-down { border: none; }
'''

_PIE_COLORS = [
    '#1F3864', '#2E75B6', '#1E8449', '#C0392B',
    '#D4AC0D', '#5B2C6F', '#117A65', '#E67E22',
    '#7F8C8D', '#34495E',
]


# Chart with metric/dimension/type dropdowns; emits bar_clicked and close_requested.
class ChartPanel(QFrame):

    bar_clicked     = pyqtSignal(str)
    close_requested = pyqtSignal(object)

    def __init__(
        self,
        parent=None,
        allow_close: bool = False,
        metric: str = 'Employee Count',
        dimension: str = 'Department',
        chart_type: str = 'Vertical Bar',
    ):
        super().__init__(parent)
        self._df = None
        self._allow_close = allow_close
        self._artist_to_label: dict = {}

        self.setObjectName('ChartPanel')
        self.setStyleSheet(
            'QFrame#ChartPanel { background: white; border: 1px solid #E5E7EB; border-radius: 8px; }'
        )

        self._build_ui()
        self.set_config(metric=metric, dimension=dimension, chart_type=chart_type)

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)

        # Toolbar row: dropdowns + optional close button
        bar = QHBoxLayout()
        bar.setSpacing(6)

        bar.addWidget(self._tag('Show'))
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(analytics.SNAPSHOT_METRICS)
        self.metric_combo.setStyleSheet(_COMBO_STYLE)
        self.metric_combo.currentIndexChanged.connect(self._refresh)
        bar.addWidget(self.metric_combo)

        bar.addWidget(self._tag('by'))
        self.dim_combo = QComboBox()
        self.dim_combo.addItems(analytics.GROUP_BY_OPTIONS)
        self.dim_combo.setStyleSheet(_COMBO_STYLE)
        self.dim_combo.currentIndexChanged.connect(self._refresh)
        bar.addWidget(self.dim_combo)

        bar.addWidget(self._tag('as'))
        self.type_combo = QComboBox()
        self.type_combo.addItems(analytics.CHART_TYPES)
        self.type_combo.setStyleSheet(_COMBO_STYLE)
        self.type_combo.currentIndexChanged.connect(self._refresh)
        bar.addWidget(self.type_combo)

        bar.addStretch()

        if self._allow_close:
            close_btn = QPushButton('✕')
            close_btn.setFixedSize(22, 22)
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.setStyleSheet('''
                QPushButton {
                    color: #555; background: #F0F0F0; border: 1px solid #CCC;
                    border-radius: 11px; font-size: 11px; font-weight: bold;
                }
                QPushButton:hover { background: #E74C3C; color: white; border-color: #C0392B; }
            ''')
            close_btn.clicked.connect(lambda: self.close_requested.emit(self))
            bar.addWidget(close_btn)

        v.addLayout(bar)

        # Chart canvas
        self.chart = ChartWithToolbar(width=8, height=4)
        v.addWidget(self.chart, stretch=1)

        # Wire pick events for click-to-drill
        self.chart.figure.canvas.mpl_connect('pick_event', self._on_pick)

    def _tag(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_LABEL_STYLE)
        return lbl

    # ── Public API ────────────────────────────────────────────────────────

    def update_data(self, df):
        self._df = df
        self._refresh()

    def set_config(self, metric: str | None = None, dimension: str | None = None, chart_type: str | None = None):
        # Block signals so we don't trigger refresh three times
        for combo in (self.metric_combo, self.dim_combo, self.type_combo):
            combo.blockSignals(True)
        if metric and metric in analytics.SNAPSHOT_METRICS:
            self.metric_combo.setCurrentText(metric)
        if dimension and dimension in analytics.GROUP_BY_OPTIONS:
            self.dim_combo.setCurrentText(dimension)
        if chart_type and chart_type in analytics.CHART_TYPES:
            self.type_combo.setCurrentText(chart_type)
        for combo in (self.metric_combo, self.dim_combo, self.type_combo):
            combo.blockSignals(False)
        self._refresh()

    def current_config(self) -> dict:
        return {
            'metric':     self.metric_combo.currentText(),
            'dimension':  self.dim_combo.currentText(),
            'chart_type': self.type_combo.currentText(),
        }

    # ── Drawing ───────────────────────────────────────────────────────────

    def _refresh(self):
        if self._df is None:
            return

        metric    = self.metric_combo.currentText()
        dimension = self.dim_combo.currentText()
        ctype     = self.type_combo.currentText()

        ax = self.chart.axes
        self.chart.clear_axes()
        self._artist_to_label = {}

        data = analytics.snapshot_data(self._df, metric, dimension)
        if data.empty:
            ax.text(0.5, 0.5, 'No data for current filters',
                    ha='center', va='center', transform=ax.transAxes,
                    color='#888', fontsize=11)
            ax.axis('off')
            self.chart.refresh()
            return

        labels = [str(x) for x in data.index]
        values = data.values

        if ctype == 'Vertical Bar':
            bars = ax.bar(labels, values, color='#2E75B6', picker=True)
            for bar, lbl in zip(bars, labels):
                self._artist_to_label[bar] = lbl
            ax.set_ylabel(metric)
            ax.tick_params(axis='x', rotation=20)
        elif ctype == 'Horizontal Bar':
            bars = ax.barh(labels, values, color='#2E75B6', picker=True)
            for bar, lbl in zip(bars, labels):
                self._artist_to_label[bar] = lbl
            ax.set_xlabel(metric)
        elif ctype in ('Pie', 'Donut'):
            colors = [_PIE_COLORS[i % len(_PIE_COLORS)] for i in range(len(labels))]
            wedges, _ = ax.pie(values, labels=labels, colors=colors, startangle=90)
            for w, lbl in zip(wedges, labels):
                w.set_picker(True)
                self._artist_to_label[w] = lbl
            if ctype == 'Donut':
                ax.add_artist(Circle((0, 0), 0.55, fc='white'))
            ax.set_aspect('equal')
        elif ctype == 'Line':
            ax.plot(labels, values, color='#2E75B6', linewidth=2)
            sc = ax.scatter(range(len(labels)), values, color='#1F3864',
                            s=70, picker=True, zorder=3)
            self._artist_to_label[sc] = labels  # special: scatter, use event.ind
            ax.set_ylabel(metric)
            ax.tick_params(axis='x', rotation=20)

        ax.set_title(f'{metric} by {dimension}', fontsize=11, fontweight='bold')
        self.chart.refresh()

    # ── Click handling ────────────────────────────────────────────────────

    def _on_pick(self, event):
        artist = event.artist
        entry = self._artist_to_label.get(artist)
        if entry is None:
            return
        if isinstance(entry, list):
            # Scatter on a line chart — use the first picked index
            idx = event.ind[0] if len(event.ind) else 0
            if 0 <= idx < len(entry):
                self.bar_clicked.emit(entry[idx])
        else:
            self.bar_clicked.emit(str(entry))
