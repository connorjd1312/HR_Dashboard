from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
import matplotlib.pyplot as plt

from core import analytics
from ui import theme
from ui.chart_widget import ChartWithToolbar, draw_pie, set_title_with_period

_LABEL_STYLE = theme.LABEL_TAG
_COMBO_STYLE = theme.COMBO_STYLE
_PIE_COLORS = theme.CHART_COLORS


# Chart with metric/dimension/type dropdowns; emits bar_clicked and close_requested.
class ChartPanel(QFrame):

    bar_clicked      = pyqtSignal(str)
    close_requested  = pyqtSignal(object)
    expand_requested = pyqtSignal(object)

    def __init__(
        self,
        parent=None,
        allow_close: bool = False,
        metric: str = 'Employee Count',
        dimension: str = 'Department',
        chart_type: str = 'Auto',
    ):
        super().__init__(parent)
        self._df = None
        self._period_text: str | None = None
        self._allow_close = allow_close
        self._artist_to_label: dict = {}
        # Cache of Auto-resolved chart types keyed by (metric, dimension) so the
        # chart type stays stable when sidebar filters narrow the data — it only
        # re-resolves when the user changes the metric or dimension.
        self._auto_cache: dict[tuple[str, str], str] = {}

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

        # Let the dropdowns shrink when charts sit side by side; the popup
        # list still shows the full names.
        for combo, max_w, stretch in ((self.metric_combo, 280, 3),
                                      (self.dim_combo, 160, 2),
                                      (self.type_combo, 150, 2)):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            combo.setMaximumWidth(max_w)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 24)
            bar.setStretchFactor(combo, stretch)

        bar.addStretch()

        self._expand_btn = QPushButton()
        self._expand_btn.setFixedHeight(24)
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.setStyleSheet('''
            QPushButton {
                color: #1F3864; background: white; border: 1px solid #CCC;
                border-radius: 4px; font-size: 11px; padding: 0 8px;
            }
            QPushButton:hover { background: #F0F4FF; border-color: #2E75B6; }
        ''')
        self._expand_btn.clicked.connect(lambda: self.expand_requested.emit(self))
        bar.addWidget(self._expand_btn)
        self.set_expanded(False)

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

    def set_expanded(self, expanded: bool):
        # Update the enlarge button to match the dashboard's current state.
        if expanded:
            self._expand_btn.setText('⤡ Restore')
            self._expand_btn.setToolTip('Return the chart to its normal size')
        else:
            self._expand_btn.setText('⤢ Enlarge')
            self._expand_btn.setToolTip('Enlarge this chart to fill the dashboard')

    def set_period_text(self, text: str | None):
        # Shown under the chart title; applied on the next redraw.
        self._period_text = text

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
        # cla() does not reset the aspect ratio, so a previous Pie's
        # set_aspect('equal') would squash the next bar/line chart. Force 'auto'
        # back on every redraw; the Pie branch re-sets 'equal' when needed.
        ax.set_aspect('auto')
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

        # Resolve 'Auto' to a concrete type from the data. The dropdown stays
        # on 'Auto' so it keeps adapting when metric/dimension change, but the
        # resolved type is cached per (metric, dimension) so it doesn't flicker
        # as sidebar filters narrow the data.
        auto_label = ''
        if ctype == 'Auto':
            key = (metric, dimension)
            ctype = self._auto_cache.get(key)
            if ctype is None:
                ctype = analytics.recommend_chart_type(metric, dimension, data)
                # Don't cache a default picked from empty/single-row data —
                # let it re-resolve once real data arrives.
                if len(data) > 1:
                    self._auto_cache[key] = ctype
            auto_label = f'Auto chart: {ctype}'

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
            wedges = draw_pie(ax, labels, values, colors, donut=(ctype == 'Donut'))
            for w, lbl in zip(wedges, labels):
                w.set_picker(True)
                self._artist_to_label[w] = lbl
        elif ctype == 'Line':
            ax.plot(labels, values, color='#2E75B6', linewidth=2)
            for lbl, val in zip(labels, values):
                point, = ax.plot([lbl], [val], 'o', color='#1F3864', markersize=8,
                                 picker=True, pickradius=6, zorder=3)
                self._artist_to_label[point] = lbl
            ax.set_ylabel(metric)
            ax.tick_params(axis='x', rotation=20)

        # Auto-picked chart type goes in the subtitle to keep the title short
        # enough for side-by-side charts.
        subtitle = '  ·  '.join(t for t in (self._period_text, auto_label) if t)
        set_title_with_period(ax, f'{metric} by {dimension}', subtitle or None)

        value_of = dict(zip(labels, values))
        self.chart.set_hover_items({
            artist: f'{lbl}: {analytics.format_metric_value(metric, value_of[lbl])}\nClick to drill down'
            for artist, lbl in self._artist_to_label.items()
        })
        self.chart.refresh()

    # ── Click handling ────────────────────────────────────────────────────

    def _on_pick(self, event):
        artist = event.artist
        entry = self._artist_to_label.get(artist)
        if entry is not None:
            self.bar_clicked.emit(str(entry))
