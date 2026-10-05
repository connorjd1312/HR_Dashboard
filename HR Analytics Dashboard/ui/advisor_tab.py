# advisor_tab.py
# AI Advisor tab: the AI Workforce Advisor chat (an embedded local LLM — no
# external server or process to install/run). Its own top-level tab next to
# Forecasting, with the conversation in a centred column so it sits where the
# user is looking.

from __future__ import annotations

import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFrame, QScrollArea, QLineEdit, QStackedWidget, QSizePolicy, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, QThread

from core.local_llm_client import LocalLLMClient
from ui import theme
from ui.advisor_worker import AdvisorWorker
from ui.model_download_worker import ModelDownloadWorker

_NAVY = theme.NAVY
_GREY_BG = theme.BG
_BORDER = theme.BORDER
_GREEN = theme.GREEN
_RED = theme.RED
_RED_BG = theme.RED_BG

_BTN_PRIMARY = theme.BTN_PRIMARY
_BTN_SECONDARY = theme.BTN_SECONDARY
_COMBO_STYLE = theme.COMBO_STYLE

_CHIP_STYLE = f'''
    QPushButton {{
        background-color: white; color: {theme.BLUE};
        border-radius: 14px; padding: 6px 14px;
        font-size: {theme.FONT_BODY}px; border: 1px solid {theme.BLUE};
    }}
    QPushButton:hover {{ background-color: #EBF5FB; }}
'''

# Width of the centred conversation column
_COLUMN_MAX_WIDTH = 860
_BUBBLE_MAX_WIDTH = 620

_SUGGESTED_QUESTIONS = [
    "What's our overall turnover rate by department?",
    'Forecast hires for next quarter',
    "What's our average tenure?",
]


class _WarmUpWorker(QThread):
    # Loads the local model in the background so the first question is quick.
    def __init__(self, client: LocalLLMClient, parent=None):
        super().__init__(parent)
        self._client = client

    def run(self):
        try:
            self._client.warm_up()
        except Exception:
            pass  # any real problem is reported when a question is asked


class AdvisorTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._client = LocalLLMClient()
        self._worker: AdvisorWorker | None = None
        self._download_worker: ModelDownloadWorker | None = None
        self._pending_label: QLabel | None = None
        self._warm_up_worker: _WarmUpWorker | None = None

        self._build_ui()
        self._check_connection()

    def _build_ui(self):
        # Centre a fixed-max-width column in the tab, like a chat app.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f'AdvisorTab {{ background-color: {_GREY_BG}; }}')
        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.addStretch(1)
        column = self._build_advisor_page()
        column.setMaximumWidth(_COLUMN_MAX_WIDTH)
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(column, stretch=8)
        outer.addStretch(1)

    def update_data(self, df: pd.DataFrame):
        self._df = df

    def shutdown(self):
        # Called when the app closes: let a background model load finish rather
        # than destroying its thread mid-run (which would crash on exit).
        if self._warm_up_worker is not None:
            self._warm_up_worker.wait()

    # Advisor page


    def _build_advisor_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f'background-color: {_GREY_BG};')
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        title = QLabel('AI Workforce Advisor')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f'font-size: 20px; font-weight: bold; color: {_NAVY}; background: transparent;')
        v.addWidget(title)
        subtitle = QLabel('Ask questions about your workforce data in plain English. '
                          'Answers come from the loaded data and run entirely on this computer.')
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(theme.LABEL_HINT)
        v.addWidget(subtitle)

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

        self._welcome = QLabel('👋  Hi! Ask me about headcount, turnover, attrition, tenure, salaries '
                               'or forecasts — or try one of the suggestions below.')
        self._welcome.setWordWrap(True)
        self._welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome.setStyleSheet('font-size: 13px; color: #777; background: transparent; padding: 20px;')
        self._messages_layout.insertWidget(0, self._welcome)
        self._messages_layout.insertStretch(0)

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
        chips_row.addStretch()
        for question in _SUGGESTED_QUESTIONS:
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
        self._input.setMinimumHeight(40)
        self._input.setStyleSheet(
            'border: 1px solid #CCC; border-radius: 8px; padding: 8px 12px; font-size: 13px; background: white;'
        )
        self._input.returnPressed.connect(self._send)
        input_row.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton('Send')
        self._send_btn.setMinimumHeight(40)
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
            self._model_combo.clear()
            self._model_combo.addItems(models)
            self._model_combo.setEnabled(True)
            self._advisor_stack.setCurrentIndex(1)
            self._start_warm_up()

        self._recheck_btn.setEnabled(True)


    def _start_warm_up(self):
        if self._warm_up_worker is not None:
            if not self._warm_up_worker.isRunning():
                self._status_label.setText('Local model ready')
            return
        self._status_label.setText('Loading the local model in the background…')
        self._warm_up_worker = _WarmUpWorker(self._client, self)
        self._warm_up_worker.finished.connect(
            lambda: self._status_label.setText('Local model ready'))
        self._warm_up_worker.start()

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


    def _add_bubble(self, text: str, is_user: bool, is_error: bool = False) -> QLabel:
        self._welcome.hide()
        row = QHBoxLayout()
        row.setSpacing(0)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(_BUBBLE_MAX_WIDTH)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        label.setStyleSheet(self._bubble_style(is_user, is_error))
        self._fit_bubble(label)

        if is_user:
            row.addStretch()
            row.addWidget(label)
        else:
            row.addWidget(label)
            row.addStretch()

        self._messages_layout.insertLayout(self._messages_layout.count() - 1, row)
        self._scroll_to_bottom()
        return label

    def _fit_bubble(self, label: QLabel):
        # Word-wrapped labels default to a narrow width; size the bubble to its
        # text so short messages stay on one line and long ones use the column.
        lines = label.text().splitlines() or ['']
        text_w = max(label.fontMetrics().horizontalAdvance(line) for line in lines)
        label.setMinimumWidth(min(text_w + 40, _BUBBLE_MAX_WIDTH))

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
            source = debug.get('source')
            if source:
                # Grey 'where this came from' line under the answer
                self._pending_label.setTextFormat(Qt.TextFormat.RichText)
                answer_html = answer.replace('&', '&amp;').replace('<', '&lt;').replace('\n', '<br>')
                self._pending_label.setText(
                    f'{answer_html}<br><span style="color:#888; font-size:11px">{source}</span>')
            else:
                self._pending_label.setText(answer)
            self._fit_bubble(self._pending_label)
        self._scroll_to_bottom()

    def _on_failed(self, message: str):
        if self._pending_label is not None:
            self._pending_label.setText(f"Sorry, I couldn't answer that: {message}")
            self._fit_bubble(self._pending_label)
            self._pending_label.setStyleSheet(self._bubble_style(is_user=False, is_error=True))
        self._scroll_to_bottom()

    def _on_worker_finished(self):
        self._input.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._pending_label = None
        self._worker = None
