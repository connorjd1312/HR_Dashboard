# main_window.py
# The top-level application window. Responsible for:
#   - A welcome screen with an Open button and drag-and-drop support
#   - The menu bar (File → Open, Add More Data, Quit)
#   - Loading multiple files at once, or appending new files to existing data
#   - Layout: filter panel on the left, tabbed dashboard/charts on the right
#   - Re-filtering and refreshing all tabs when the user applies filters

import pandas as pd

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QTabWidget, QFileDialog, QMessageBox, QStatusBar,
    QLabel, QPushButton, QStackedWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent

from core.data_loader import load_file
from core.data_cleaner import clean
from ui.filter_panel import FilterPanel
from ui.dashboard_tab import DashboardTab
from ui.charts_tab import ChartsTab

SUPPORTED = ('.csv', '.xlsx')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('HR Employee Analytics Dashboard')
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        # Cleaned combined dataset — updated every time files are loaded or appended
        self._df_full = None

        # Raw (pre-clean) frames kept so we can re-concat + re-clean on each append.
        # This ensures deduplication always runs across the full combined dataset.
        self._raw_frames: list[pd.DataFrame] = []

        # Track how many files are currently loaded for the status bar
        self._file_count = 0

        self._build_ui()
        self._build_menu()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage('Open a CSV or XLSX file to get started  (File → Open HR Data)')

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        h.addWidget(self.splitter)

        # Left side — placeholder until a file is loaded
        self.filter_panel = QWidget()
        self.filter_panel.setFixedWidth(220)
        self.splitter.addWidget(self.filter_panel)

        # Right side — stacked: page 0 = welcome, page 1 = dashboard tabs
        self.stack = QStackedWidget()
        self.splitter.addWidget(self.stack)
        self.splitter.setSizes([220, 1060])

        self.stack.addWidget(self._build_welcome_page())  # index 0

        self.tab_widget = QTabWidget()
        self.dashboard_tab = DashboardTab()
        self.charts_tab = ChartsTab()
        self.tab_widget.addTab(self.dashboard_tab, 'Dashboard')
        self.tab_widget.addTab(self.charts_tab, 'Charts')
        self.stack.addWidget(self.tab_widget)              # index 1

    def _build_welcome_page(self):
        """Landing screen shown before any data is loaded."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel('HR Employee Analytics Dashboard')
        title.setStyleSheet('font-size: 24px; font-weight: bold; color: #1F3864;')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel('Import one or more employee data files to get started')
        subtitle.setStyleSheet('font-size: 14px; color: #555555;')
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn = QPushButton('Open HR Data File(s)')
        btn.setFixedSize(240, 52)
        btn.setStyleSheet('''
            QPushButton {
                background-color: #1F3864; color: white;
                font-size: 14px; border-radius: 6px;
            }
            QPushButton:hover  { background-color: #2E75B6; }
            QPushButton:pressed { background-color: #163060; }
        ''')
        btn.clicked.connect(self._open_files)

        formats = QLabel('Supports .csv and .xlsx — select multiple files at once')
        formats.setStyleSheet('font-size: 11px; color: #888888;')
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)

        dnd = QLabel('You can also drag and drop files directly onto this window')
        dnd.setStyleSheet('font-size: 11px; color: #aaaaaa;')
        dnd.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(subtitle)
        layout.addSpacing(28)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)
        layout.addWidget(formats)
        layout.addSpacing(24)
        layout.addWidget(dnd)
        layout.addStretch()

        return page

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu('File')

        # Open — replaces whatever is currently loaded
        open_action = QAction('Open HR Data...', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self._open_files)
        file_menu.addAction(open_action)

        # Add More Data — appends to the current dataset; disabled until first load
        self._add_action = QAction('Add More Data...', self)
        self._add_action.setShortcut('Ctrl+Shift+O')
        self._add_action.setEnabled(False)   # enabled once data is loaded
        self._add_action.triggered.connect(self._add_files)
        file_menu.addAction(self._add_action)

        file_menu.addSeparator()

        quit_action = QAction('Quit', self)
        quit_action.setShortcut('Ctrl+Q')
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    # ------------------------------------------------------------------ #
    # Core loading logic
    # ------------------------------------------------------------------ #

    def _load_paths(self, paths: list[str], append: bool = False):
        """
        Load one or more files and either replace or append to the current dataset.

        append=False  →  discard existing data, load only the new files
        append=True   →  combine new files with previously loaded data, then re-clean
        """
        try:
            # Load each file individually so we get a clear error message per file
            new_frames = []
            for path in paths:
                new_frames.append(load_file(path))

            if append and self._raw_frames:
                # Merge new raw frames with all previously loaded raw frames,
                # then re-clean the full combined set so dedup runs across everything
                all_raw = self._raw_frames + new_frames
            else:
                all_raw = new_frames

            # Concatenate all raw frames into one DataFrame before cleaning
            combined_raw = pd.concat(all_raw, ignore_index=True)
            self._df_full = clean(combined_raw)

            # Save raw frames so future appends can include them
            self._raw_frames = all_raw
            self._file_count = len(all_raw)

            # Rebuild the filter panel with values from the new combined dataset
            new_fp = FilterPanel(self._df_full)
            new_fp.setFixedWidth(220)
            new_fp.filters_changed.connect(self._apply_filters)
            self.splitter.replaceWidget(0, new_fp)
            self.filter_panel = new_fp

            # Switch from welcome page to dashboard if this is the first load
            if self.stack.currentIndex() == 0:
                self.stack.setCurrentIndex(1)

            # Enable "Add More Data" now that we have a loaded dataset
            self._add_action.setEnabled(True)

            self._refresh_all(self._df_full)

            action = 'Added' if (append and self._file_count > len(paths)) else 'Loaded'
            self.statusBar().showMessage(
                f'{action} {len(paths)} file(s)  —  '
                f'{len(self._df_full)} records from {self._file_count} file(s) total'
            )

        except Exception as e:
            QMessageBox.critical(self, 'Error loading file', str(e))

    def _open_files(self):
        """Open a multi-select file dialog; selected files replace the current dataset."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Open HR Data', '',
            'Data Files (*.csv *.xlsx)',
        )
        if paths:
            self._load_paths(paths, append=False)

    def _add_files(self):
        """Open a multi-select file dialog; selected files are appended to existing data."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Add More HR Data', '',
            'Data Files (*.csv *.xlsx)',
        )
        if paths:
            self._load_paths(paths, append=True)

    # ------------------------------------------------------------------ #
    # Drag-and-drop
    # ------------------------------------------------------------------ #

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept the drag if at least one dragged file is a supported type."""
        if event.mimeData().hasUrls():
            if any(u.toLocalFile().endswith(SUPPORTED) for u in event.mimeData().urls()):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle dropped files — if data is already loaded, ask whether to add or replace."""
        paths = [
            u.toLocalFile() for u in event.mimeData().urls()
            if u.toLocalFile().endswith(SUPPORTED)
        ]
        if not paths:
            return

        if self._df_full is not None:
            # Data already exists — ask the user what they want to do
            msg = QMessageBox(self)
            msg.setWindowTitle('Add or Replace?')
            msg.setText(
                f'You dropped {len(paths)} file(s).\n'
                f'Currently loaded: {self._file_count} file(s), {len(self._df_full)} records.\n\n'
                'What would you like to do?'
            )
            add_btn     = msg.addButton('Add to existing data',  QMessageBox.ButtonRole.AcceptRole)
            replace_btn = msg.addButton('Replace existing data', QMessageBox.ButtonRole.DestructiveRole)
            msg.addButton('Cancel',                              QMessageBox.ButtonRole.RejectRole)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == add_btn:
                self._load_paths(paths, append=True)
            elif clicked == replace_btn:
                self._load_paths(paths, append=False)
            # Cancel → do nothing
        else:
            # No data yet — just load them
            self._load_paths(paths, append=False)

    # ------------------------------------------------------------------ #
    # Filtering and refresh
    # ------------------------------------------------------------------ #

    def _apply_filters(self, f: dict):
        """Filter the full dataset and push the result to both tabs."""
        df = self._df_full.copy()

        if f['department'] != 'All':
            df = df[df['Department'] == f['department']]

        if f['status'] != 'All':
            df = df[df['Status'] == f['status']]

        df = df[
            (df['Hire_Date'].dt.date >= f['date_from']) &
            (df['Hire_Date'].dt.date <= f['date_to'])
        ]

        self._refresh_all(df)
        self.statusBar().showMessage(f'Showing {len(df)} records')

    def _refresh_all(self, df):
        """Push updated data to both tabs so they redraw their charts and KPIs."""
        self.dashboard_tab.update_data(df)
        self.charts_tab.update_data(df)
