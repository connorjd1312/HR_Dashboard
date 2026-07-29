# data_manager_dialog.py
# Dialogs behind the "Manage Data" entry point:
#   - DataOptionsDialog: small chooser shown first — load files for this
#     session only, or manage the Default Documents folder that auto-loads
#     on startup.
#   - DefaultDocumentsDialog: add/remove files from the Default Documents
#     folder itself.
#
# Every color here is set explicitly (never left to the OS/Qt palette) —
# these dialogs previously inherited system theme colors for text, which
# produced unreadable white-on-white buttons on some machines.

import shutil
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView, QMessageBox,
    QFileDialog, QFrame, QWidget,
)

from ui import message_box

SUPPORTED = ('.csv', '.xlsx')

_NAVY = '#1F3864'
_BLUE = '#2E75B6'
_GREEN = '#1E8449'
_RED = '#C0392B'
_BG = '#F5F7FA'

_HEADER_STYLE = f'background-color: {_NAVY};'
_HEADER_TITLE_STYLE = (
    'font-size: 15px; font-weight: bold; color: white; '
    'font-family: Arial; background: transparent;'
)

_PRIMARY_BTN = f'''
    QPushButton {{
        background-color: {_NAVY}; color: white;
        border-radius: 6px; padding: 9px 16px;
        font-size: 12px; font-weight: bold; border: none;
    }}
    QPushButton:hover  {{ background-color: {_BLUE}; }}
    QPushButton:pressed {{ background-color: #163060; }}
    QPushButton:disabled {{ background-color: #B7C2D6; color: #EEEEEE; }}
'''

_DANGER_BTN = f'''
    QPushButton {{
        background-color: white; color: {_RED};
        border: 1px solid {_RED}; border-radius: 6px;
        padding: 8px 16px; font-size: 12px; font-weight: bold;
    }}
    QPushButton:hover  {{ background-color: #FDECEA; }}
    QPushButton:pressed {{ background-color: #FADBD8; }}
    QPushButton:disabled {{ color: #C9A6A1; border-color: #E6C6C2; background-color: white; }}
'''

_TEXT_BTN = '''
    QPushButton {
        border: none; color: #666666;
        padding: 8px 16px; font-size: 12px; background: transparent;
    }
    QPushButton:hover { color: #333333; text-decoration: underline; }
'''


def _format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB'):
        if size < 1024 or unit == 'MB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} MB'


class _ClickableCard(QFrame):
    # A large, hoverable option card — icon + title + description — used
    # in DataOptionsDialog so the two choices read as distinct actions
    # rather than easy-to-miss buttons.
    clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, description: str, accent: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._accent = accent
        self._apply_style(hover=False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet('font-size: 26px; background: transparent; border: none;')
        layout.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f'font-size: 13px; font-weight: bold; color: {_NAVY}; '
            'background: transparent; border: none;'
        )
        text_col.addWidget(title_label)

        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            'font-size: 11px; color: #666666; background: transparent; border: none;'
        )
        text_col.addWidget(desc_label)

        layout.addLayout(text_col, stretch=1)

        arrow = QLabel('›')
        arrow.setStyleSheet(
            f'font-size: 20px; font-weight: bold; color: {accent}; '
            'background: transparent; border: none;'
        )
        layout.addWidget(arrow)

    def _apply_style(self, hover: bool):
        bg = '#F7FAFD' if hover else 'white'
        self.setStyleSheet(f'''
            QFrame {{
                background-color: {bg};
                border: 1px solid {"#B7D3EA" if hover else "#E0E0E0"};
                border-left: 4px solid {self._accent};
                border-radius: 8px;
            }}
        ''')

    def enterEvent(self, event):
        self._apply_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(hover=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class DataOptionsDialog(QDialog):
    # Entry-point chooser. Caller reads .choice after exec() — 'load', 'manage', or None.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Manage Data')
        self.setFixedWidth(420)
        self.setStyleSheet(f'QDialog {{ background-color: {_BG}; }}')
        self.choice = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(_HEADER_STYLE)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)
        title = QLabel('Manage Data')
        title.setStyleSheet(_HEADER_TITLE_STYLE)
        h_layout.addWidget(title)
        outer.addWidget(header)

        body = QWidget()
        body.setStyleSheet('background-color: transparent;')
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        subtitle = QLabel('Choose how you’d like to update your data.')
        subtitle.setStyleSheet(
            'font-size: 12px; color: #555555; background: transparent; border: none;'
        )
        layout.addWidget(subtitle)

        load_card = _ClickableCard(
            '\U0001F4C4', 'Load New Files (This Session)',
            'Open CSV/XLSX files for right now only — the Default\n'
            'Documents folder is left untouched.',
            _BLUE,
        )
        load_card.clicked.connect(lambda: self._pick('load'))
        layout.addWidget(load_card)

        manage_card = _ClickableCard(
            '\U0001F5C2', 'Manage Default Documents',
            'Add or remove the files that load automatically\n'
            'every time the app starts.',
            _GREEN,
        )
        manage_card.clicked.connect(lambda: self._pick('manage'))
        layout.addWidget(manage_card)

        layout.addSpacing(4)

        cancel_btn = QPushButton('Cancel')
        cancel_btn.setStyleSheet(_TEXT_BTN)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

        outer.addWidget(body)

    def _pick(self, choice):
        self.choice = choice
        self.accept()


class DefaultDocumentsDialog(QDialog):
    # Add/remove files in the Default Documents folder.
    # Exposes .changed so the caller knows whether to reload the dashboard afterward.

    def __init__(self, folder: Path, parent=None):
        super().__init__(parent)
        self._folder = folder
        self.changed = False

        self.setWindowTitle('Manage Default Documents')
        self.setMinimumSize(480, 420)
        self.setStyleSheet(f'QDialog {{ background-color: {_BG}; }}')

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(_HEADER_STYLE)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)
        title = QLabel('Manage Default Documents')
        title.setStyleSheet(_HEADER_TITLE_STYLE)
        h_layout.addWidget(title)
        outer.addWidget(header)

        body = QVBoxLayout()
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(10)

        info = QLabel('These files load automatically every time the app starts.')
        info.setStyleSheet(
            'font-size: 12px; color: #555555; background: transparent; border: none;'
        )
        body.addWidget(info)

        path_label = QLabel(str(folder))
        path_label.setWordWrap(True)
        path_label.setStyleSheet('''
            font-family: Consolas, monospace; font-size: 10px; color: #444444;
            background-color: #ECEFF3; border: 1px solid #DCE1E8;
            border-radius: 4px; padding: 5px 8px;
        ''')
        body.addWidget(path_label)

        # White card containing the file list (or an empty-state message)
        card = QFrame()
        card.setStyleSheet('''
            QFrame {
                background-color: white;
                border: 1px solid #E0E0E0;
                border-radius: 8px;
            }
        ''')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(1, 1, 1, 1)
        card_layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setStyleSheet(f'''
            QListWidget {{
                background-color: white; color: #333333;
                border: none; border-radius: 8px;
                font-size: 12px; padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 10px; border-radius: 4px; color: #333333;
            }}
            QListWidget::item:selected {{
                background-color: {_BLUE}; color: white;
            }}
            QListWidget::item:hover:!selected {{
                background-color: #F0F5FA;
            }}
        ''')
        self._list.itemSelectionChanged.connect(self._update_remove_state)
        card_layout.addWidget(self._list)

        self._empty_label = QLabel(
            'No default documents yet.\nClick "Add File(s)..." below to add some.'
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            'font-size: 12px; color: #999999; background: white; '
            'border: none; padding: 30px;'
        )
        card_layout.addWidget(self._empty_label)

        body.addWidget(card, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        add_btn = QPushButton('+  Add File(s)...')
        add_btn.setStyleSheet(_PRIMARY_BTN)
        add_btn.clicked.connect(self._add_files)

        self._remove_btn = QPushButton('Remove Selected')
        self._remove_btn.setStyleSheet(_DANGER_BTN)
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._remove_selected)

        btn_row.addWidget(add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        body.addLayout(btn_row)

        outer.addLayout(body)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet('color: #E0E0E0; background-color: #E0E0E0; max-height: 1px;')
        outer.addWidget(divider)

        bottom = QWidget()
        bottom.setStyleSheet('background-color: transparent;')
        bottom_row = QHBoxLayout(bottom)
        bottom_row.setContentsMargins(20, 12, 20, 16)
        bottom_row.addStretch()
        done_btn = QPushButton('Done')
        done_btn.setStyleSheet(_PRIMARY_BTN)
        done_btn.setFixedWidth(90)
        done_btn.clicked.connect(self.accept)
        bottom_row.addWidget(done_btn)
        outer.addWidget(bottom)

        self._refresh_list()

    def _update_remove_state(self):
        self._remove_btn.setEnabled(bool(self._list.selectedItems()))

    def _refresh_list(self):
        self._list.clear()
        self._folder.mkdir(parents=True, exist_ok=True)

        files = sorted(
            f for f in self._folder.iterdir() if f.suffix.lower() in SUPPORTED
        )
        for f in files:
            try:
                size_str = _format_size(f.stat().st_size)
            except OSError:
                size_str = '–'
            item = QListWidgetItem(f'\U0001F4C4  {f.name}      ({size_str})')
            item.setData(Qt.ItemDataRole.UserRole, f.name)
            self._list.addItem(item)

        is_empty = self._list.count() == 0
        self._list.setVisible(not is_empty)
        self._empty_label.setVisible(is_empty)
        self._update_remove_state()

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Add Default Document(s)', str(Path.home()),
            'Data Files (*.csv *.xlsx)',
        )
        if not paths:
            return

        self._folder.mkdir(parents=True, exist_ok=True)
        for src in paths:
            src_path = Path(src)
            dest = self._folder / src_path.name

            if dest.exists() and dest.resolve() != src_path.resolve():
                reply = message_box.question(
                    self, 'File already exists',
                    f"'{dest.name}' already exists in Default Documents.\nOverwrite it?",
                )
                if reply != QMessageBox.StandardButton.Yes:
                    continue

            if dest.resolve() != src_path.resolve():
                shutil.copy(src_path, dest)
            self.changed = True

        self._refresh_list()

    def _remove_selected(self):
        items = self._list.selectedItems()
        if not items:
            return

        names = ', '.join(i.data(Qt.ItemDataRole.UserRole) for i in items)
        reply = message_box.question(
            self, 'Remove file(s)',
            f'Delete the following from Default Documents?\n\n{names}',
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for item in items:
            path = self._folder / item.data(Qt.ItemDataRole.UserRole)
            try:
                path.unlink(missing_ok=True)
            except OSError as e:
                message_box.warning(self, 'Error removing file', str(e))

        self.changed = True
        self._refresh_list()
