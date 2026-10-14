from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal

from core import analytics
from ui import theme
from ui.chart_widget import ChartWithToolbar, draw_pie, set_title_with_period
from ui.drag_drop import DragHandle, PANEL_MIME, mime_payload, start_drag

_LABEL_STYLE = theme.LABEL_TAG
_COMBO_STYLE = theme.COMBO_STYLE


_PANEL_STYLE = 'QFrame#ChartPanel { background: white; border: 1px solid #E5E7EB; border-radius: 8px; }'
_PANEL_DROP_STYLE = 'QFrame#ChartPanel { background: white; border: 2px dashed #F5A623; border-radius: 8px; }'


# Chart with metric/dimension/type dropdowns
class ChartPanel(QFrame):

    bar_clicked = pyqtSignal(str)
    close_requested = pyqtSignal(object)
    expand_requested = pyqtSignal(object)
    config_changed = pyqtSignal()
    swap_requested = pyqtSignal(str, object)

    def __init__(
        self,
        parent=None,
        allow_close: bool = False,
        metric: str = 'Total Employees',
        dimension: str = 'Department',
        chart_type: str = 'Auto',
    ):
        super().__init__(parent)
        self._df = None
        self._period_text: str | None = None
        self._allow_close = allow_close
        self._artist_to_label: dict = {}
        # Remembers the Auto chart type for each metric and dimension
        self._auto_cache: dict[tuple[str, str], str] = {}

        self.setObjectName('ChartPanel')
        self.setStyleSheet(_PANEL_STYLE)
        self.setAcceptDrops(True)

        self._build_ui()
        self.set_config(metric=metric, dimension=dimension, chart_type=chart_type)

    # UI construction

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)

        # Toolbar row: dropdowns + optional close button
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self._drag_handle = DragHandle(tooltip='Drag onto another chart to swap their positions')
        self._drag_handle.drag_requested.connect(self._begin_drag)
        self._drag_handle.hide()
        bar.addWidget(self._drag_handle)

        bar.addWidget(self._tag('Show'))
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(analytics.SNAPSHOT_METRICS)
        self.metric_combo.setStyleSheet(_COMBO_STYLE)
        self.metric_combo.currentIndexChanged.connect(self._refresh)
        self.metric_combo.currentIndexChanged.connect(lambda _i: self.config_changed.emit())
        self.metric_combo.currentTextChanged.connect(
            lambda m: self.metric_combo.setToolTip(analytics.describe_metric(m)))
        for i, m in enumerate(analytics.SNAPSHOT_METRICS):
            self.metric_combo.setItemData(i, analytics.describe_metric(m), Qt.ItemDataRole.ToolTipRole)
        bar.addWidget(self.metric_combo)

        bar.addWidget(self._tag('by'))
        self.dim_combo = QComboBox()
        self.dim_combo.addItems(analytics.GROUP_BY_OPTIONS)
        self.dim_combo.setStyleSheet(_COMBO_STYLE)
        self.dim_combo.currentIndexChanged.connect(self._refresh)
        self.dim_combo.currentIndexChanged.connect(lambda _i: self.config_changed.emit())
        self.dim_combo.setToolTip('How to split the employees into groups')
        bar.addWidget(self.dim_combo)

        bar.addWidget(self._tag('as'))
        self.type_combo = QComboBox()
        self.type_combo.addItems(analytics.CHART_TYPES)
        self.type_combo.setStyleSheet(_COMBO_STYLE)
        self.type_combo.currentIndexChanged.connect(self._refresh)
        self.type_combo.currentIndexChanged.connect(lambda _i: self.config_changed.emit())
        self.type_combo.setToolTip('Chart type. "Auto" picks the clearest type for the data.')
        bar.addWidget(self.type_combo)

        # Let dropdowns shrink when charts sit side by side
        for combo, max_w, stretch in ((self.metric_combo, 280, 3),
                                      (self.dim_combo, 160, 2),
                                      (self.type_combo, 150, 2)):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(7)  # keeps compare mode no wider with the drag handle
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
        self.chart.hide_coordinates()
        v.addWidget(self.chart, stretch=1)

        # Wire pick events for click-to-drill
        self.chart.figure.canvas.mpl_connect('pick_event', self._on_pick)

    def _tag(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_LABEL_STYLE)
        return lbl

    # Public API

    def update_data(self, df):
        self._df = df
        self._refresh()

    def set_draggable(self, draggable: bool):
        self._drag_handle.setVisible(draggable)

    def refresh_theme(self):
        self.chart.refresh_theme()
        self._refresh()

    def _begin_drag(self):
        start_drag(self, PANEL_MIME, str(id(self)))

    def _set_drop_highlight(self, on: bool):
        self.setStyleSheet(_PANEL_DROP_STYLE if on else _PANEL_STYLE)

    def _is_foreign_panel(self, mime) -> bool:
        source = mime_payload(mime, PANEL_MIME)
        return source is not None and source != str(id(self))

    def dragEnterEvent(self, event):
        if self._is_foreign_panel(event.mimeData()):
            self._set_drop_highlight(True)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._is_foreign_panel(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_drop_highlight(False)

    def dropEvent(self, event):
        self._set_drop_highlight(False)
        if self._is_foreign_panel(event.mimeData()):
            event.acceptProposedAction()
            self.swap_requested.emit(mime_payload(event.mimeData(), PANEL_MIME), self)

    def set_expanded(self, expanded: bool):
        # Update the enlarge button to match the dashboard's current state
        if expanded:
            self._expand_btn.setText('⤡ Restore')
            self._expand_btn.setToolTip('Return the chart to its normal size')
        else:
            self._expand_btn.setText('⤢ Enlarge')
            self._expand_btn.setToolTip('Enlarge this chart to fill the dashboard')

    def set_period_text(self, text: str | None):
        # Shown under the chart title; applied on the next redraw
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
            'metric': self.metric_combo.currentText(),
            'dimension': self.dim_combo.currentText(),
            'chart_type': self.type_combo.currentText(),
        }

    # Drawing

    def _refresh(self):
        if self._df is None:
            return

        metric = self.metric_combo.currentText()
        dimension = self.dim_combo.currentText()
        ctype = self.type_combo.currentText()

        ax = self.chart.axes
        self.chart.clear_axes()
        # Reset the aspect ratio so a pie does not squash other charts
        ax.set_aspect('auto')
        self._artist_to_label = {}

        data = analytics.snapshot_data(self._df, metric, dimension)
        if data.empty:
            ax.text(0.5, 0.5, 'No data for current filters',
                    ha='center', va='center', transform=ax.transAxes,
                    color=theme.chart_muted(), fontsize=11)
            ax.axis('off')
            self.chart.refresh()
            return

        labels = [str(x) for x in data.index]
        values = [float(v) for v in data.values]

        # Pick a concrete chart type for Auto and remember it
        auto_label = ''
        if ctype == 'Auto':
            key = (metric, dimension)
            ctype = self._auto_cache.get(key)
            if ctype is None:
                ctype = analytics.recommend_chart_type(metric, dimension, data)
                # Do not remember a default chosen from empty data
                if len(data) > 1:
                    self._auto_cache[key] = ctype
            auto_label = f'Auto chart: {ctype}'

        # Largest first, except ordered groups like Age Group
        if ctype in ('Vertical Bar', 'Horizontal Bar', 'Line') and dimension not in analytics.ORDERED_DIMENSIONS:
            order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
            labels = [labels[i] for i in order]
            values = [values[i] for i in order]
        value_text = [analytics.format_metric_value(metric, v) for v in values]

        if ctype == 'Vertical Bar':
            bars = ax.bar(labels, values, color='#2E75B6', picker=True)
            for bar, lbl in zip(bars, labels):
                self._artist_to_label[bar] = lbl
            ax.bar_label(bars, labels=value_text, padding=2, fontsize=8, color=theme.chart_text())
            ax.margins(y=0.12)
            ax.set_ylabel(metric)
            ax.tick_params(axis='x', rotation=20)
        elif ctype == 'Horizontal Bar':
            # barh draws bottom-up, so reverse to put the largest at the top
            bars = ax.barh(labels[::-1], values[::-1], color='#2E75B6', picker=True)
            for bar, lbl in zip(bars, labels[::-1]):
                self._artist_to_label[bar] = lbl
            ax.bar_label(bars, labels=value_text[::-1], padding=3, fontsize=8, color=theme.chart_text())
            ax.margins(x=0.12)
            ax.set_xlabel(metric)
        elif ctype in ('Pie', 'Donut'):
            palette = theme.chart_palette()
            colors = [palette[i % len(palette)] for i in range(len(labels))]
            wedges = draw_pie(ax, labels, values, colors, donut=(ctype == 'Donut'))
            for w, lbl in zip(wedges, labels):
                w.set_picker(True)
                self._artist_to_label[w] = lbl
        elif ctype == 'Line':
            ax.plot(labels, values, color=theme.chart_color(theme.BLUE), linewidth=2)
            for lbl, val in zip(labels, values):
                point, = ax.plot([lbl], [val], 'o', color=theme.chart_color(theme.NAVY), markersize=8,
                                 picker=True, pickradius=6, zorder=3)
                self._artist_to_label[point] = lbl
            ax.set_ylabel(metric)
            ax.tick_params(axis='x', rotation=20)

        # Put the Auto chart type in the subtitle
        subtitle = '  ·  '.join(t for t in (self._period_text, auto_label) if t)
        set_title_with_period(ax, f'{metric} by {dimension}', subtitle or None)

        self.chart.set_hover_items(self._artist_to_label)
        self.chart.refresh()

    # Click handling

    def _on_pick(self, event):
        artist = event.artist
        entry = self._artist_to_label.get(artist)
        if entry is not None:
            self.bar_clicked.emit(str(entry))
