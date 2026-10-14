# Forecasting tab with statistical forecast charts

from __future__ import annotations

from datetime import date

import pandas as pd

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox
from PyQt6.QtCore import Qt

from core import analytics, forecasting
from ui import theme
from ui.chart_widget import ChartWithToolbar, set_title_with_period

# Colour / style constants, matches dashboard_tab.py / series_dialog.py

_NAVY = theme.NAVY
_NAVY_HOVER = theme.BLUE
_GREY_BG = theme.BG
_GREEN = theme.GREEN
_RED = theme.RED

_COMBO_STYLE = theme.COMBO_STYLE


# Word used for one forecast step at each granularity
_PERIOD_UNITS = {'Weekly': 'week', 'Monthly': 'month', 'Quarterly': 'quarter', 'Yearly': 'year'}

# How much past data the chart shows; None = all the data
_HISTORY_OPTIONS = {'All Data': None, 'Last 5 Years': 60, 'Last 2 Years': 24, 'Last 1 Year': 12}
_FIT_MONTHS = 24  # the forecast is fitted to this much recent history
_MIN_FIT_POINTS = 4


class ForecastingTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._build_ui()


    # Top-level layout


    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_forecast_page())


    # Public API, called by MainWindow whenever the dataset changes


    def update_data(self, df: pd.DataFrame):
        self._df = df

        current = self.dept_combo.currentText()
        self.dept_combo.blockSignals(True)
        self.dept_combo.clear()
        self.dept_combo.addItem('All Departments')
        if df is not None and 'Department' in df.columns:
            self.dept_combo.addItems(sorted(df['Department'].dropna().unique().tolist()))
        idx = self.dept_combo.findText(current)
        self.dept_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.dept_combo.blockSignals(False)

        self._redraw_forecast()


    # Forecast chart page (pure Python, no AI)


    def _build_forecast_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f'QWidget {{ background-color: {_GREY_BG}; }}' + theme.TOOLTIP_QSS)
        v = QVBoxLayout(page)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        controls.addWidget(self._tag('Metric'))
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(forecasting.FORECAST_METRICS)
        self.metric_combo.setStyleSheet(_COMBO_STYLE)
        self.metric_combo.currentTextChanged.connect(self._redraw_forecast)
        self.metric_combo.currentTextChanged.connect(
            lambda m: self.metric_combo.setToolTip(analytics.describe_metric(m)))
        controls.addWidget(self.metric_combo)

        controls.addWidget(self._tag('Department'))
        self.dept_combo = QComboBox()
        self.dept_combo.addItem('All Departments')
        self.dept_combo.setStyleSheet(_COMBO_STYLE)
        self.dept_combo.currentTextChanged.connect(self._redraw_forecast)
        controls.addWidget(self.dept_combo)

        controls.addWidget(self._tag('Method'))
        self.method_combo = QComboBox()
        self.method_combo.addItems(forecasting.FORECAST_METHODS)
        self.method_combo.setStyleSheet(_COMBO_STYLE)
        self.method_combo.currentTextChanged.connect(self._redraw_forecast)
        for i, m in enumerate(forecasting.FORECAST_METHODS):
            self.method_combo.setItemData(i, forecasting.METHOD_DESCRIPTIONS[m], Qt.ItemDataRole.ToolTipRole)
        controls.addWidget(self.method_combo)

        controls.addWidget(self._tag('Granularity'))
        self.gran_combo = QComboBox()
        self.gran_combo.addItems(analytics.GRANULARITIES)
        self.gran_combo.setCurrentText('Monthly')
        self.gran_combo.setStyleSheet(_COMBO_STYLE)
        self.gran_combo.currentTextChanged.connect(self._redraw_forecast)
        controls.addWidget(self.gran_combo)

        controls.addWidget(self._tag('History'))
        self.history_combo = QComboBox()
        self.history_combo.addItems(_HISTORY_OPTIONS.keys())
        self.history_combo.setStyleSheet(_COMBO_STYLE)
        self.history_combo.setToolTip('How much past data to show. The forecast is always based on the last 2 years.')
        self.history_combo.currentTextChanged.connect(self._redraw_forecast)
        controls.addWidget(self.history_combo)

        self._ahead_label = self._tag('Months Ahead')
        controls.addWidget(self._ahead_label)
        self.periods_spin = QSpinBox()
        self.periods_spin.setRange(1, 24)
        self.periods_spin.setValue(3)
        self.periods_spin.setMinimumHeight(28)
        self.periods_spin.valueChanged.connect(self._redraw_forecast)
        controls.addWidget(self.periods_spin)

        # Let the dropdowns shrink on narrower windows
        for combo in (self.metric_combo, self.dept_combo, self.method_combo, self.gran_combo,
                      self.history_combo):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(6)
            combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 24)

        controls.addStretch()
        v.addLayout(controls)

        # Explains the chosen method in plain English
        self._method_hint = QLabel()
        self._method_hint.setWordWrap(True)
        self._method_hint.setStyleSheet(theme.LABEL_HINT)
        v.addWidget(self._method_hint)

        self._stats_label = QLabel('Load data to see a forecast.')
        self._stats_label.setStyleSheet(
            f'font-size: 13px; font-weight: bold; color: {_NAVY}; background: transparent;'
        )
        v.addWidget(self._stats_label)

        self._forecast_chart = ChartWithToolbar(width=9, height=5)
        v.addWidget(self._forecast_chart, stretch=1)

        return page

    def _redraw_forecast(self, *_args):
        if self._df is None or len(self._df) == 0:
            return

        metric = self.metric_combo.currentText()
        method = self.method_combo.currentText()
        granularity = self.gran_combo.currentText()
        periods = self.periods_spin.value()
        dept = self.dept_combo.currentText()

        unit = _PERIOD_UNITS.get(granularity, 'period')
        self._ahead_label.setText(f'{unit.title()}s Ahead')
        self._method_hint.setText(f'{method}: {forecasting.METHOD_DESCRIPTIONS.get(method, "")}')

        df = self._df
        if dept and dept != 'All Departments' and 'Department' in df.columns:
            df = df[df['Department'] == dept]

        freq = analytics._FREQ_MAP.get(granularity, 'ME')
        end = pd.Timestamp(date.today())
        months_back = _HISTORY_OPTIONS.get(self.history_combo.currentText())
        if months_back is None:
            start = self._earliest_date(end)
        else:
            start = end - pd.DateOffset(months=months_back)
        history = analytics.time_series_data(df, metric, 'None', 'All', start, end, granularity)
        # Fit the forecast to the most recent 2 years
        full = history
        if months_back is not None:
            full = analytics.time_series_data(df, metric, 'None', 'All',
                                              self._earliest_date(end), end, granularity)
        recent = full[full.index > end - pd.DateOffset(months=_FIT_MONTHS)]
        recent = full.tail(max(len(recent), _MIN_FIT_POINTS))
        fc = forecasting.forecast_series(recent, periods, method, freq)
        fc_range = forecasting.forecast_range(recent, periods, method, freq)
        summary = forecasting.forecast_summary(recent, fc)

        self._forecast_chart.clear_axes()
        ax = self._forecast_chart.axes

        if len(history) == 0:
            ax.text(0.5, 0.5, 'Not enough data to forecast', ha='center', va='center',
                     transform=ax.transAxes, color=theme.chart_muted())
            ax.axis('off')
        else:
            ax.plot(history.index, history.values, color=theme.chart_color(_NAVY), linewidth=2,
                     marker='o', markersize=3, label='Historical')
            if len(fc):
                bridge_x = [history.index[-1]] + list(fc.index)
                bridge_y = [history.values[-1]] + list(fc.values)
                # Shaded likely range, starting from the last real value
                ax.fill_between(bridge_x,
                                [history.values[-1]] + list(fc_range['Lower']),
                                [history.values[-1]] + list(fc_range['Upper']),
                                color=_NAVY_HOVER, alpha=0.15, linewidth=0,
                                label=forecasting.RANGE_LABEL)
                ax.plot(bridge_x, bridge_y, color=_NAVY_HOVER, linewidth=2, linestyle='--',
                         marker='o', markersize=3, label='Forecast')
            period = f'History: {analytics.format_period(history.index[0], history.index[-1])}'
            if len(fc):
                period += f'   ·   Forecast to {analytics.format_date(fc.index[-1])}'
            set_title_with_period(ax, f'{metric} - {method} Forecast', period, color=theme.heading_colour())
            ax.tick_params(axis='x', rotation=30, labelsize=8)
            ax.legend(fontsize=9)

        self._forecast_chart.refresh()

        if summary['last_historical'] is None:
            self._stats_label.setText('Not enough historical data to forecast this metric.')
            self._stats_label.setStyleSheet('font-size: 13px; font-weight: bold; color: #555; background: transparent;')
        else:
            arrow = {'up': '▲', 'down': '▼', 'flat': '→'}.get(summary['direction'], '→')
            color = {'up': _GREEN, 'down': _RED, 'flat': '#555'}.get(summary['direction'], '#555')
            # Plain-English summary
            latest = summary['last_historical']
            end_value = summary['forecast_points'][-1]['value'] if summary['forecast_points'] else latest
            if summary['direction'] == 'flat':
                trend = 'stay about the same'
            elif latest == 0:
                # A % change from zero is meaningless, describe the actual change instead
                trend = f'{"rise" if end_value > latest else "fall"} from 0 to {end_value:.1f}'
            else:
                trend = f'{"rise" if summary["direction"] == "up" else "fall"} {abs(summary["percent_change"]):.1f}%'
            self._stats_label.setText(
                f'{arrow} {metric} {"are" if metric in ("Hires", "Departures") else "is"} expected to {trend} over the next {periods} '
                f'{unit}{"s" if periods != 1 else ""}'
                f'  (latest: {latest:.1f} → forecast: {end_value:.1f},'
                f' likely {fc_range["Lower"].iloc[-1]:.1f}–{fc_range["Upper"].iloc[-1]:.1f})'
            )
            self._stats_label.setStyleSheet(
                f'font-size: 13px; font-weight: bold; color: {color}; background: transparent;'
            )

    def _earliest_date(self, end: pd.Timestamp) -> pd.Timestamp:
        # Earliest hire or leave date in the data
        dates = [self._df[c].min() for c in ('Hire_Date', 'End_Date') if c in self._df.columns]
        dates = [d for d in dates if pd.notna(d)]
        return min(dates) if dates else end - pd.DateOffset(months=24)

    def refresh_theme(self):
        self._forecast_chart.refresh_theme()
        self._redraw_forecast()

    def _tag(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet('font-size: 12px; color: #555; background: transparent;')
        return lbl
