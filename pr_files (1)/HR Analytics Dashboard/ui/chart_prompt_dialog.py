from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from core import chart_generator
from core.chart_generator import ChartRequestError, ChartSuggestion
from core.local_llm_client import DEFAULT_MODEL
from ui import theme

EXAMPLES = [
    'Hires vs departures over the last 2 years',
    'Turnover rate by department',
    'Average salary by job role as horizontal bars',
    'Headcount by age group as a pie chart',
    'Compare hires in Sales and Engineering this year',
]

ADD_TO_CURRENT = 'current'
ADD_AS_NEW = 'new'

_PRIMARY = f'''
    QPushButton {{ background: {theme.NAVY}; color: white; border: none; border-radius: 4px;
                  padding: 6px 16px; font-size: 12px; font-weight: bold; }}
    QPushButton:hover {{ background: {theme.BLUE}; }}
    QPushButton:disabled {{ background: #9AA5B1; }}
'''
_SECONDARY = '''
    QPushButton { background: white; color: #444; border: 1px solid #CCC; border-radius: 4px;
                  padding: 6px 14px; font-size: 12px; }
    QPushButton:hover { background: #F0F4FF; border-color: #2E75B6; }
    QPushButton:disabled { color: #AAA; }
'''
_CHIP = '''
    QPushButton { background: #F0F4FF; color: #1F3864; border: 1px solid #C9D7F0; border-radius: 11px;
                  padding: 3px 10px; font-size: 11px; }
    QPushButton:hover { background: #E1EAFB; border-color: #2E75B6; }
'''


# Workers still running after their dialog closes are kept here so Qt does not destroy a live thread.
_ORPHANS: set = set()


class _SuggestWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, description, df, client, model, parent=None):
        super().__init__(parent)
        self._args = (description, df, client, model)

    def run(self):
        try:
            self.succeeded.emit(chart_generator.suggest_chart(*self._args))
        except ChartRequestError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f'Something went wrong building that chart: {e}')


class ChartPromptDialog(QDialog):

    def __init__(self, df, client=None, preview_fn=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Describe a chart')
        self.setMinimumWidth(620)
        self._df = df
        self._client = client
        self._preview_fn = preview_fn
        self._worker: _SuggestWorker | None = None
        self._suggestion: ChartSuggestion | None = None
        self._mode = ADD_TO_CURRENT

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        title = QLabel('Describe the chart you want')
        title.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {theme.NAVY};')
        root.addWidget(title)
        hint = QLabel('Say what to measure, how to split it and over what period. '
                      'You\'ll see how it was understood before anything is added.')
        hint.setWordWrap(True)
        hint.setStyleSheet('font-size: 12px; color: #666;')
        root.addWidget(hint)

        self._prompt = QPlainTextEdit()
        self._prompt.setPlaceholderText('e.g. "Compare turnover by department as horizontal bars"')
        self._prompt.setFixedHeight(66)
        self._prompt.textChanged.connect(self._on_text_changed)
        root.addWidget(self._prompt)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        chip_box = QWidget()
        chip_layout = QVBoxLayout(chip_box)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setSpacing(5)
        row = None
        for i, text in enumerate(EXAMPLES):
            if i % 2 == 0:
                row = QHBoxLayout()
                row.setSpacing(6)
                chip_layout.addLayout(row)
            chip = QPushButton(text)
            chip.setStyleSheet(_CHIP)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, t=text: self._use_example(t))
            row.addWidget(chip)
        for r in range(chip_layout.count()):
            chip_layout.itemAt(r).layout().addStretch()
        root.addWidget(chip_box)

        gen_row = QHBoxLayout()
        self._status = QLabel('')
        self._status.setStyleSheet('font-size: 12px; color: #666;')
        gen_row.addWidget(self._status, stretch=1)
        self._generate_btn = QPushButton('Generate')
        self._generate_btn.setStyleSheet(_PRIMARY)
        self._generate_btn.setEnabled(False)
        self._generate_btn.clicked.connect(self._generate)
        gen_row.addWidget(self._generate_btn)
        root.addLayout(gen_row)
        QShortcut(QKeySequence('Ctrl+Return'), self, activated=self._generate)

        self._result = QFrame()
        self._result.setStyleSheet(f'QFrame#result {{ background: #F5F7FA; border: 1px solid {theme.BORDER}; '
                                   'border-radius: 6px; }')
        self._result.setObjectName('result')
        rv = QVBoxLayout(self._result)
        rv.setContentsMargins(14, 12, 14, 12)
        rv.setSpacing(6)
        self._result_title = QLabel()
        self._result_title.setStyleSheet(f'font-size: 13px; font-weight: bold; color: {theme.NAVY}; '
                                         'background: transparent; border: none;')
        self._result_title.setWordWrap(True)
        rv.addWidget(self._result_title)
        self._result_detail = QLabel()
        self._result_detail.setWordWrap(True)
        self._result_detail.setStyleSheet('font-size: 12px; color: #444; background: transparent; border: none;')
        rv.addWidget(self._result_detail)
        self._result_notes = QLabel()
        self._result_notes.setWordWrap(True)
        self._result_notes.setStyleSheet('font-size: 11px; color: #7A4B00; background: transparent; border: none;')
        rv.addWidget(self._result_notes)
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet('background: white; border: 1px solid #E0E0E0; border-radius: 4px;')
        rv.addWidget(self._preview)
        self._engine = QLabel()
        self._engine.setStyleSheet('font-size: 11px; color: #888; background: transparent; border: none;')
        self._engine.setWordWrap(True)
        rv.addWidget(self._engine)
        self._result.hide()
        root.addWidget(self._result)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton('Cancel')
        cancel.setStyleSheet(_SECONDARY)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self._new_btn = QPushButton('Add as new chart')
        self._new_btn.setStyleSheet(_SECONDARY)
        self._new_btn.clicked.connect(lambda: self._accept(ADD_AS_NEW))
        buttons.addWidget(self._new_btn)
        self._add_btn = QPushButton('Add to this chart')
        self._add_btn.setStyleSheet(_PRIMARY)
        self._add_btn.clicked.connect(lambda: self._accept(ADD_TO_CURRENT))
        buttons.addWidget(self._add_btn)
        self._set_confirm_enabled(False)
        root.addLayout(buttons)

    def suggestion(self) -> ChartSuggestion | None:
        return self._suggestion

    def mode(self) -> str:
        return self._mode

    def _use_example(self, text: str):
        self._prompt.setPlainText(text)
        self._generate()

    def _on_text_changed(self):
        busy = self._worker is not None and self._worker.isRunning()
        self._generate_btn.setEnabled(bool(self._prompt.toPlainText().strip()) and not busy)

    def _set_confirm_enabled(self, enabled: bool):
        self._add_btn.setEnabled(enabled)
        self._new_btn.setEnabled(enabled)

    def _generate(self):
        text = self._prompt.toPlainText().strip()
        if not text or (self._worker is not None and self._worker.isRunning()):
            return
        self._suggestion = None
        self._set_confirm_enabled(False)
        self._generate_btn.setEnabled(False)
        using_ai = self._client is not None and self._client.is_available()
        self._status.setText('Asking the local AI model...' if using_ai else 'Working out the chart...')
        self._status.setStyleSheet('font-size: 12px; color: #666;')
        self._worker = _SuggestWorker(text, self._df, self._client, DEFAULT_MODEL)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_success(self, suggestion: ChartSuggestion):
        self._suggestion = suggestion
        self._status.setText('')
        self._result_title.setText(suggestion.title)
        self._result_detail.setText('Understood as:\n' + suggestion.describe())
        self._result_notes.setText('\n'.join('- ' + n for n in suggestion.notes))
        self._result_notes.setVisible(bool(suggestion.notes))

        pix = self._preview_fn(suggestion) if self._preview_fn else None
        self._preview.setVisible(pix is not None and not pix.isNull())
        if pix is not None:
            self._preview.setPixmap(pix)
            self._preview.setFixedSize(pix.size())

        if suggestion.engine == 'ai':
            self._engine.setText('Interpreted by the local AI model. Check the preview before adding.')
        elif self._client is not None and self._client.is_available():
            self._engine.setText('Interpreted with keyword matching.')
        else:
            self._engine.setText('Interpreted with keyword matching. Download the AI model on the AI Advisor '
                                 'tab to understand more flexible wording.')
        self._result.show()
        self._set_confirm_enabled(True)
        self._on_text_changed()
        self.adjustSize()

    def _on_failure(self, message: str):
        self._result.hide()
        self._status.setText(message)
        self._status.setStyleSheet('font-size: 12px; color: #C0392B;')
        self._status.setWordWrap(True)
        self._on_text_changed()

    def _accept(self, mode: str):
        if self._suggestion is None:
            return
        self._mode = mode
        self.accept()

    def done(self, result):
        worker = self._worker
        if worker is not None and worker.isRunning():
            for signal in (worker.succeeded, worker.failed):
                try:
                    signal.disconnect()
                except TypeError:
                    pass
            _ORPHANS.add(worker)
            worker.finished.connect(lambda w=worker: _ORPHANS.discard(w))
        super().done(result)
