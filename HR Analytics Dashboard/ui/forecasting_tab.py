# forecasting_tab.py
# Forecasting tab: statistical forecast charts (no AI) + the AI Workforce Advisor
# chat (an embedded local LLM — no external server or process to install/run).
# Two sub-tabs inside one top-level tab, mirroring how compare_tab.py is embedded
# inside analytics_tab.py rather than being its own tab.

from __future__ import annotations

from datetime import date

import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QTabWidget, QFrame, QScrollArea, QLineEdit, QStackedWidget,
    QSizePolicy, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer

from core import analytics, forecasting
from core.local_llm_client import LocalLLMClient
from ui.chart_widget import ChartWithToolbar
from ui.advisor_worker import AdvisorWorker
from ui.model_download_worker import ModelDownloadWorker

# Colour / style constants — matches dashboard_tab.py / series_dialog.py

_NAVY = '#1F3864'
_NAVY_HOVER = '#2E75B6'
_NAVY_PRESS = '#163060'
_GREY_BG = '#F5F7FA'
_BORDER = '#E0E0E0'
_GREEN = '#1E8449'
_RED = '#C0392B'
_RED_BG = '#FADBD8'

_BTN_PRIMARY = '''
    QPushButton {
        background-color: #1F3864; color: white;
        border-radius: 5px; padding: 6px 14px;
        font-size: 12px; border: none;
    }
    QPushButton:hover  { background-color: #2E75B6; }
    QPushButton:pressed { background-color: #163060; }
    QPushButton:disabled { background-color: #9AA5B1; }
'''

_BTN_SECONDARY = '''
    QPushButton {
        background-color: white; color: #444;
        border-radius: 5px; padding: 6px 14px;
        font-size: 12px; border: 1px solid #CCC;
    }
    QPushButton:hover { background-color: #F0F0F0; }
    QPushButton:disabled { color: #AAA; }
'''

_CHIP_STYLE = '''
    QPushButton {
        background-color: white; color: #2E75B6;
        border-radius: 12px; padding: 5px 12px;
        font-size: 11px; border: 1px solid #2E75B6;
    }
    QPushButton:hover { background-color: #EBF5FB; }
'''

_COMBO_STYLE = '''
    QComboBox {
        border: 1px solid #CCCCCC; border-radius: 4px;
        padding: 4px 8px; background: white; font-size: 12px; color: #333;
    }
    QComboBox:focus { border-color: #2E75B6; }
    QComboBox::drop-down { border: none; }
'''


class ForecastingTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._client = LocalLLMClient()
        self._worker: AdvisorWorker | None = None
        self._download_worker: ModelDownloadWorker | None = None
        self._pending_label: QLabel | None = None

        self._build_ui()
        self._check_connection()


    # Top-level layout


    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        subtabs = QTabWidget()
        outer.addWidget(subtabs)

        subtabs.addTab(self._build_forecast_page(), 'Forecast Charts')
        subtabs.addTab(self._build_advisor_page(), 'AI Advisor')


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


    # Forecast Charts sub-tab (pure Python, no AI)


    def _build_forecast_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f'background-color: {_GREY_BG};')
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
        controls.addWidget(self.method_combo)

        controls.addWidget(self._tag('Granularity'))
        self.gran_combo = QComboBox()
        self.gran_combo.addItems(analytics.GRANULARITIES)
        self.gran_combo.setCurrentText('Monthly')
        self.gran_combo.setStyleSheet(_COMBO_STYLE)
        self.gran_combo.currentTextChanged.connect(self._redraw_forecast)
        controls.addWidget(self.gran_combo)

        controls.addWidget(self._tag('Periods Ahead'))
        self.periods_spin = QSpinBox()
        self.periods_spin.setRange(1, 24)
        self.periods_spin.setValue(3)
        self.periods_spin.setStyleSheet(_COMBO_STYLE)
        self.periods_spin.valueChanged.connect(self._redraw_forecast)
        controls.addWidget(self.periods_spin)

        controls.addStretch()
        v.addLayout(controls)

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

        df = self._df
        if dept and dept != 'All Departments' and 'Department' in df.columns:
            df = df[df['Department'] == dept]

        freq = analytics._FREQ_MAP.get(granularity, 'ME')
        end = pd.Timestamp(date.today())
        start = end - pd.DateOffset(months=24)
        history = analytics.time_series_data(df, metric, 'None', 'All', start, end, granularity)
        fc = forecasting.forecast_series(history, periods, method, freq)
        summary = forecasting.forecast_summary(history, fc)

        self._forecast_chart.clear_axes()
        ax = self._forecast_chart.axes

        if len(history) == 0:
            ax.text(0.5, 0.5, 'Not enough data to forecast', ha='center', va='center',
                     transform=ax.transAxes, color='#888')
            ax.axis('off')
        else:
            ax.plot(history.index, history.values, color=_NAVY, linewidth=2,
                     marker='o', markersize=3, label='Historical')
            if len(fc):
                bridge_x = [history.index[-1]] + list(fc.index)
                bridge_y = [history.values[-1]] + list(fc.values)
                ax.plot(bridge_x, bridge_y, color=_NAVY_HOVER, linewidth=2, linestyle='--',
                         marker='o', markersize=3, label='Forecast')
            ax.set_title(f'{metric} — {method} Forecast', fontsize=11, color=_NAVY)
            ax.tick_params(axis='x', rotation=30, labelsize=8)
            ax.legend(fontsize=9)

        self._forecast_chart.refresh()

        if summary['last_historical'] is None:
            self._stats_label.setText('Not enough historical data to forecast this metric.')
            self._stats_label.setStyleSheet('font-size: 13px; font-weight: bold; color: #555; background: transparent;')
        else:
            arrow = {'up': '▲', 'down': '▼', 'flat': '→'}.get(summary['direction'], '→')
            color = {'up': _GREEN, 'down': _RED, 'flat': '#555'}.get(summary['direction'], '#555')
            self._stats_label.setText(
                f'{arrow} {summary["percent_change"]:+.1f}% projected over the next '
                f'{periods} period(s) (from {summary["last_historical"]})'
            )
            self._stats_label.setStyleSheet(
                f'font-size: 13px; font-weight: bold; color: {color}; background: transparent;'
            )


    # AI Advisor sub-tab


    def _build_advisor_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f'background-color: {_GREY_BG};')
        v = QVBoxLayout(page)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        # Connection status row
        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self._status_dot = QLabel('●')
        self._status_dot.setStyleSheet('font-size: 14px; background: transparent;')
        status_row.addWidget(self._status_dot)

        self._status_label = QLabel('Checking local model…')
        self._status_label.setStyleSheet('font-size: 12px; color: #555; background: transparent;')
        status_row.addWidget(self._status_label, stretch=1)

        self._model_combo = QComboBox()
        self._model_combo.setStyleSheet(_COMBO_STYLE)
        self._model_combo.setMinimumWidth(160)
        self._model_combo.setEnabled(False)
        status_row.addWidget(self._model_combo)

        self._recheck_btn = QPushButton('Check Again')
        self._recheck_btn.setStyleSheet(_BTN_SECONDARY)
        self._recheck_btn.clicked.connect(self._check_connection)
        status_row.addWidget(self._recheck_btn)

        v.addLayout(status_row)

        # Setup card (shown when the local model isn't downloaded yet) / Chat widget (shown when it is)
        self._advisor_stack = QStackedWidget()
        v.addWidget(self._advisor_stack, stretch=1)

        self._advisor_stack.addWidget(self._build_setup_card())  # index 0
        self._advisor_stack.addWidget(self._build_chat_widget())  # index 1

        return page

    def _build_setup_card(self) -> QWidget:
        card = QFrame()
        card.setStyleSheet(f'QFrame {{ background: white; border: 1px solid {_BORDER}; border-radius: 8px; }}')
        v = QVBoxLayout(card)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(10)
        v.addStretch()

        icon = QLabel('🤖')
        icon.setStyleSheet('font-size: 36px; background: transparent; border: none;')
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(icon)

        title = QLabel('AI Workforce Advisor needs its local model')
        title.setStyleSheet(f'font-size: 15px; font-weight: bold; color: {_NAVY}; background: transparent; border: none;')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        self._setup_message_label = QLabel(self._default_setup_text())
        self._setup_message_label.setWordWrap(True)
        self._setup_message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup_message_label.setStyleSheet('font-size: 12px; color: #555; background: transparent; border: none;')
        v.addWidget(self._setup_message_label)

        self._download_btn = QPushButton('Download Model (~2 GB)')
        self._download_btn.setStyleSheet(_BTN_PRIMARY)
        self._download_btn.clicked.connect(self._start_download)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._download_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self._download_progress = QProgressBar()
        self._download_progress.setRange(0, 100)
        self._download_progress.setVisible(False)
        self._download_progress.setStyleSheet('QProgressBar { border: 1px solid #CCC; border-radius: 4px; text-align: center; } '
                                                f'QProgressBar::chunk {{ background-color: {_NAVY}; }}')
        v.addWidget(self._download_progress)

        v.addStretch()
        return card

    def _default_setup_text(self) -> str:
        return (
            'This feature answers HR questions using a locally hosted AI model that runs '
            'inside this application — no external program to install, no server to start, '
            'and once the one-time download below finishes, no internet connection is needed '
            'to use it.\n\n'
            'Click "Download Model" to fetch it now (a one-time download of a few GB).'
        )

    def _build_chat_widget(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        # Message history
        self._messages_container = QWidget()
        self._messages_container.setStyleSheet(f'background: {_GREY_BG};')
        self._messages_layout = QVBoxLayout(self._messages_container)
        self._messages_layout.setContentsMargins(10, 10, 10, 10)
        self._messages_layout.setSpacing(10)
        self._messages_layout.addStretch()

        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setWidget(self._messages_container)
        self._chat_scroll.setStyleSheet(
            f'QScrollArea {{ border: 1px solid {_BORDER}; border-radius: 6px; }}'
        )
        v.addWidget(self._chat_scroll, stretch=1)

        # Suggested questions
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        for question in [
            "What's our turnover rate by department?",
            'Forecast hires for next quarter',
            "What's our average tenure?",
        ]:
            chip = QPushButton(question)
            chip.setStyleSheet(_CHIP_STYLE)
            chip.clicked.connect(lambda _, q=question: self._send_preset(q))
            chips_row.addWidget(chip)
        chips_row.addStretch()
        v.addLayout(chips_row)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText('Ask a question about your workforce data…')
        self._input.setStyleSheet(
            'border: 1px solid #CCC; border-radius: 6px; padding: 8px 10px; font-size: 12px;'
        )
        self._input.returnPressed.connect(self._send)
        input_row.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton('Send')
        self._send_btn.setStyleSheet(_BTN_PRIMARY)
        self._send_btn.clicked.connect(self._send)
        input_row.addWidget(self._send_btn)

        v.addLayout(input_row)

        return wrap


    # Local model status handling


    def _check_connection(self):
        self._recheck_btn.setEnabled(False)
        models = self._client.list_models()

        if not models:
            self._status_dot.setStyleSheet(f'color: {_RED}; font-size: 14px; background: transparent;')
            self._status_label.setText('Local model not downloaded yet')
            self._model_combo.clear()
            self._model_combo.setEnabled(False)
            if hasattr(self, '_setup_message_label'):
                self._setup_message_label.setText(self._default_setup_text())
            self._advisor_stack.setCurrentIndex(0)
        else:
            self._status_dot.setStyleSheet(f'color: {_GREEN}; font-size: 14px; background: transparent;')
            self._status_label.setText(f'Local model ready · {len(models)} model(s) available')
            self._model_combo.clear()
            self._model_combo.addItems(models)
            self._model_combo.setEnabled(True)
            self._advisor_stack.setCurrentIndex(1)

        self._recheck_btn.setEnabled(True)


    # Model download handling


    def _start_download(self):
        if self._download_worker is not None and self._download_worker.isRunning():
            return

        self._download_btn.setEnabled(False)
        self._recheck_btn.setEnabled(False)
        self._download_progress.setVisible(True)
        self._download_progress.setValue(0)
        self._setup_message_label.setText('Downloading the local model — this can take a while on first run…')

        self._download_worker = ModelDownloadWorker(self._client)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.succeeded.connect(self._on_download_succeeded)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.start()

    def _on_download_progress(self, downloaded: int, total: int):
        if total > 0:
            self._download_progress.setValue(int(downloaded * 100 / total))
        mb_done = downloaded / (1024 * 1024)
        mb_total = total / (1024 * 1024) if total else 0
        self._setup_message_label.setText(
            f'Downloading the local model… {mb_done:.0f} MB'
            + (f' / {mb_total:.0f} MB' if mb_total else '')
        )

    def _on_download_succeeded(self):
        self._download_progress.setValue(100)
        self._check_connection()

    def _on_download_failed(self, message: str):
        self._setup_message_label.setText(f'Download failed: {message}\n\nClick "Download Model" to try again.')

    def _on_download_finished(self):
        self._download_btn.setEnabled(True)
        self._recheck_btn.setEnabled(True)
        self._download_progress.setVisible(False)
        self._download_worker = None


    # Chat message handling


    def _tag(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet('font-size: 12px; color: #555; background: transparent;')
        return lbl

    def _add_bubble(self, text: str, is_user: bool, is_error: bool = False) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(0)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(480)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        label.setStyleSheet(self._bubble_style(is_user, is_error))

        if is_user:
            row.addStretch()
            row.addWidget(label)
        else:
            row.addWidget(label)
            row.addStretch()

        self._messages_layout.insertLayout(self._messages_layout.count() - 1, row)
        self._scroll_to_bottom()
        return label

    def _bubble_style(self, is_user: bool, is_error: bool) -> str:
        if is_error:
            bg, fg, border = _RED_BG, _RED, _RED
        elif is_user:
            bg, fg, border = _NAVY, 'white', _NAVY
        else:
            bg, fg, border = 'white', '#333', _BORDER
        return (
            f'background-color: {bg}; color: {fg}; border: 1px solid {border}; '
            'border-radius: 10px; padding: 10px 14px; font-size: 12px;'
        )

    def _scroll_to_bottom(self):
        QTimer.singleShot(
            0,
            lambda: self._chat_scroll.verticalScrollBar().setValue(
                self._chat_scroll.verticalScrollBar().maximum()
            ),
        )

    def _send_preset(self, question: str):
        self._input.setText(question)
        self._send()

    def _send(self):
        if self._worker is not None and self._worker.isRunning():
            return

        question = self._input.text().strip()
        if not question:
            return

        if self._df is None or len(self._df) == 0:
            self._add_bubble('Load an HR data file first.', is_user=False, is_error=True)
            return

        model = self._model_combo.currentText()
        if not model:
            self._add_bubble('No AI model is available — check the connection above.', is_user=False, is_error=True)
            return

        self._add_bubble(question, is_user=True)
        self._input.clear()
        self._input.setEnabled(False)
        self._send_btn.setEnabled(False)
        self._pending_label = self._add_bubble('Thinking…', is_user=False)

        self._worker = AdvisorWorker(self._client, model, question, self._df)
        self._worker.stage.connect(self._on_stage)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_stage(self, text: str):
        if self._pending_label is not None:
            self._pending_label.setText(text)

    def _on_succeeded(self, answer: str, debug: dict):
        if self._pending_label is not None:
            self._pending_label.setText(answer)
        self._scroll_to_bottom()

    def _on_failed(self, message: str):
        if self._pending_label is not None:
            self._pending_label.setText(f"Sorry, I couldn't answer that: {message}")
            self._pending_label.setStyleSheet(self._bubble_style(is_user=False, is_error=True))
        self._scroll_to_bottom()

    def _on_worker_finished(self):
        self._input.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._pending_label = None
        self._worker = None
