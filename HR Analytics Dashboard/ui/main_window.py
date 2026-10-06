# main_window.py
# The top-level application window. Responsible for:
#   - Auto-loading whatever is in the Default Documents folder on startup
#   - A welcome screen with an Open button and drag-and-drop support
#     (shown only when Default Documents is empty/missing)
#   - The menu bar (File → Manage Data, Quit) — Manage Data offers
#     session-only loads or editing the Default Documents folder that
#     auto-loads on startup
#   - Loading multiple files at once, or appending new files to existing data
#   - Layout: filter panel on the left, tabbed dashboard/charts on the right
#   - Re-filtering and refreshing all tabs when the user applies filters

from pathlib import Path

import pandas as pd

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QTabWidget, QFileDialog, QMessageBox, QStatusBar, QDialog,
    QLabel, QPushButton, QStackedWidget, QFrame, QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent

from core.data_loader import load_file
from core import analytics
from core.data_cleaner import clean
from ui.filter_panel import FilterPanel
from ui.dashboard_tab import DashboardTab
from ui.analytics_tab import AnalyticsTab
from ui.data_manager_dialog import DataOptionsDialog, DefaultDocumentsDialog
from ui import message_box, theme
from ui.forecasting_tab import ForecastingTab
from ui.advisor_tab import AdvisorTab
from ui.help_dialog import HelpDialog

SUPPORTED = ('.csv', '.xlsx')

# ui/ -> HR Analytics Dashboard/ -> Default documents
DEFAULT_DOCS_DIR = Path(__file__).resolve().parent.parent / 'Default documents'

_DROP_ZONE_NORMAL = '''
    QFrame {
        border: 2px dashed #2E75B6;
        border-radius: 12px;
        background-color: #EBF5FB;
    }
'''

_DROP_ZONE_ACTIVE = '''
    QFrame {
        border: 2px dashed #1F3864;
        border-radius: 12px;
        background-color: #D6EAF8;
    }
'''


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Shared fonts, colours and chart style for the whole app
        theme.apply_app_theme(QApplication.instance())
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
        self.statusBar().showMessage('Open a CSV or XLSX file to get started  (File → Manage Data)')

        self._load_default_documents()

   
    # UI construction


    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        h.addWidget(self.splitter)

        # Left side placeholder until a file is loaded; hidden on welcome screen
        self.filter_panel = QWidget()
        self.filter_panel.setFixedWidth(220)
        self.splitter.addWidget(self.filter_panel)
        self.filter_panel.hide()

        # Right side stacked: page 0 = welcome, page 1 = dashboard tabs
        self.stack = QStackedWidget()
        self.splitter.addWidget(self.stack)
        self.splitter.setSizes([220, 1060])

        self.stack.addWidget(self._build_welcome_page())  # index 0

        self.tab_widget = QTabWidget()
        self.dashboard_tab = DashboardTab()
        self.analytics_tab = AnalyticsTab()
        self.forecasting_tab = ForecastingTab()
        self.advisor_tab = AdvisorTab()
        self.tab_widget.addTab(self.dashboard_tab, 'Dashboard')
        self.tab_widget.addTab(self.analytics_tab, 'Analytics')
        self.tab_widget.addTab(self.forecasting_tab, 'Forecasting')
        self.tab_widget.addTab(self.advisor_tab, 'AI Advisor')
        self.stack.addWidget(self.tab_widget)              # index 1
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _build_welcome_page(self):
        # Build the landing screen shown before any data is loaded.
        page = QWidget()
        page.setStyleSheet('background-color: #F5F7FA;')
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # header bar
        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet('background-color: #1F3864;')
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(32, 0, 32, 0)
        app_title = QLabel('HR Employee Analytics Dashboard')
        app_title.setStyleSheet(
            'font-size: 22px; font-weight: bold; color: white;'
        )
        app_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_layout.addWidget(app_title)
        outer.addWidget(header)

        # Upload section
        outer.addStretch()

        subtitle = QLabel('Import your employee data file to get started')
        subtitle.setStyleSheet(
            'font-size: 14px; color: #555555; background: transparent;'
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(subtitle)
        outer.addSpacing(20)

        btn = QPushButton('Open HR Data File(s)')
        btn.setFixedSize(240, 52)
        btn.setStyleSheet('''
            QPushButton {
                background-color: #1F3864; color: white;
                font-size: 14px; border-radius: 6px; border: none;
            }
            QPushButton:hover  { background-color: #2E75B6; }
            QPushButton:pressed { background-color: #163060; }
        ''')
        btn.clicked.connect(self._open_files)
        outer.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        outer.addSpacing(16)

        # Visible drag-and-drop zone
        self._drop_zone = QFrame()
        self._drop_zone.setFixedSize(400, 130)
        self._drop_zone.setStyleSheet(_DROP_ZONE_NORMAL)
        dz_layout = QVBoxLayout(self._drop_zone)
        dz_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz_layout.setSpacing(4)

        dz_icon = QLabel('📂')
        dz_icon.setStyleSheet('font-size: 32px; border: none; background: transparent;')
        dz_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        dz_main = QLabel('Drag & drop your HR file here')
        dz_main.setStyleSheet(
            'font-size: 13px; font-weight: bold; color: #2E75B6;'
            ' border: none; background: transparent;'
        )
        dz_main.setAlignment(Qt.AlignmentFlag.AlignCenter)

        dz_hint = QLabel('.csv and .xlsx  ·  multiple files supported')
        dz_hint.setStyleSheet(
            'font-size: 11px; color: #888888; border: none; background: transparent;'
        )
        dz_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        dz_layout.addWidget(dz_icon)
        dz_layout.addWidget(dz_main)
        dz_layout.addWidget(dz_hint)
        outer.addWidget(self._drop_zone, alignment=Qt.AlignmentFlag.AlignCenter)

        outer.addStretch()

        # Feature preview cards
        cards_container = QWidget()
        cards_container.setStyleSheet('background-color: #F5F7FA;')
        cards_layout = QHBoxLayout(cards_container)
        cards_layout.setContentsMargins(40, 0, 40, 40)
        cards_layout.setSpacing(16)

        for card_title, colour, description in [
            (
                'KPI Overview', '#1F3864',
                'Track total headcount, active employees,\n'
                'overall turnover rate, average tenure and salary.',
            ),
            (
                'Visual Charts', '#2E75B6',
                'Explore hiring trends, role distribution,\n'
                'turnover, salary, and leave analytics.',
            ),
            (
                'Filter & Explore', '#1E8449',
                'Slice data by department, job role,\n'
                'employment status and hire date range.',
            ),
        ]:
            card = QFrame()
            card.setStyleSheet(f'''
                QFrame {{
                    background-color: white;
                    border-radius: 8px;
                    border-top: 1px solid #E0E0E0;
                    border-right: 1px solid #E0E0E0;
                    border-bottom: 1px solid #E0E0E0;
                    border-left: 5px solid {colour};
                }}
            ''')
            card.setFixedHeight(100)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(6)

            ct = QLabel(card_title)
            ct.setStyleSheet(
                f'font-size: 13px; font-weight: bold; color: {colour};'
                ' border: none; background: transparent;'
            )

            cd = QLabel(description)
            cd.setStyleSheet(
                'font-size: 11px; color: #555555; border: none; background: transparent;'
            )

            cl.addWidget(ct)
            cl.addWidget(cd)
            cards_layout.addWidget(card)

        outer.addWidget(cards_container)

        return page

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu('File')

        # Manage Data — session-only loads, or edit the Default Documents folder
        self._manage_data_action = QAction('Manage Data...', self)
        self._manage_data_action.setShortcut('Ctrl+M')
        self._manage_data_action.triggered.connect(self._open_data_options)
        file_menu.addAction(self._manage_data_action)

        file_menu.addSeparator()

        quit_action = QAction('Quit', self)
        quit_action.setShortcut('Ctrl+Q')
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menu.addMenu('Help')
        guide_action = QAction('Quick Guide', self)
        guide_action.setShortcut('F1')
        guide_action.triggered.connect(lambda: HelpDialog(self).exec())
        help_menu.addAction(guide_action)


    # Core loading logic


    def _load_paths(self, paths: list[str], append: bool = False):
        # Load files and either replace (append=False) or merge (append=True) with existing data.
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
            self.filter_panel.show()
            self.splitter.setSizes([220, 1060])

            # Switch from welcome page to dashboard if this is the first load
            if self.stack.currentIndex() == 0:
                self.stack.setCurrentIndex(1)

            # Analytics and Forecasting use the full dataset; the dashboard
            # starts with the sidebar's default filters applied.
            self.analytics_tab.update_data(self._df_full)
            self.forecasting_tab.update_data(self._df_full)
            self.advisor_tab.update_data(self._df_full)
            self.filter_panel.emit_filters()

            action = 'Added' if (append and self._file_count > len(paths)) else 'Loaded'
            self.statusBar().showMessage(
                f'{action} {len(paths)} file(s)  —  '
                f'{len(self._df_full)} records from {self._file_count} file(s) total'
            )

        except Exception as e:
            message_box.critical(self, 'Error loading file', str(e))

    def _open_files(self):
        # Open a file dialog; selected files replace the current dataset.
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Open HR Data', str(Path.home()),
            'Data Files (*.csv *.xlsx)',
        )
        if paths:
            self._load_paths(paths, append=False)

    def _default_document_paths(self) -> list[str]:
        if not DEFAULT_DOCS_DIR.is_dir():
            return []
        return sorted(
            str(p) for p in DEFAULT_DOCS_DIR.iterdir()
            if p.suffix.lower() in SUPPORTED
        )

    def _load_default_documents(self):
        # Auto-load whatever is in the Default Documents folder on startup.
        # Leaves the welcome/upload screen showing if it's missing or empty.
        paths = self._default_document_paths()
        if not paths:
            return

        self._load_paths(paths, append=False)
        self.statusBar().showMessage(
            f'Loaded {len(paths)} default document(s)  —  '
            f'{len(self._df_full)} records from "Default documents"'
        )

    def _reset_to_welcome(self):
        # Clear all loaded data and return to the welcome/upload screen.
        self._df_full = None
        self._raw_frames = []
        self._file_count = 0
        self.filter_panel.hide()
        self.splitter.setSizes([0, 1280])
        self.stack.setCurrentIndex(0)
        self.statusBar().showMessage('Open a CSV or XLSX file to get started  (File → Manage Data)')


    # Manage Data entry point


    def _open_data_options(self):
        dlg = DataOptionsDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if dlg.choice == 'load':
            self._open_files()
        elif dlg.choice == 'manage':
            self._manage_default_documents()

    def _manage_default_documents(self):
        dlg = DefaultDocumentsDialog(DEFAULT_DOCS_DIR, self)
        dlg.exec()
        if not dlg.changed:
            return

        paths = self._default_document_paths()
        if not paths:
            message_box.information(
                self, 'Default Documents cleared',
                'The Default Documents folder is now empty. Returning to the upload screen.',
            )
            self._reset_to_welcome()
            return

        reply = message_box.question(
            self, 'Reload dashboard?',
            'The Default Documents folder has changed.\n'
            'Reload the dashboard with the updated files now?',
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._load_paths(paths, append=False)


    # Drag-and-drop


    def closeEvent(self, event):
        self.advisor_tab.shutdown()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        # Accept drag if at least one dragged file is a supported type.
        if event.mimeData().hasUrls():
            if any(u.toLocalFile().endswith(SUPPORTED) for u in event.mimeData().urls()):
                event.acceptProposedAction()
                if self.stack.currentIndex() == 0 and hasattr(self, '_drop_zone'):
                    self._drop_zone.setStyleSheet(_DROP_ZONE_ACTIVE)

    def dragLeaveEvent(self, event):
        # Reset drop zone highlight when the drag leaves the window.
        if hasattr(self, '_drop_zone'):
            self._drop_zone.setStyleSheet(_DROP_ZONE_NORMAL)

    def dropEvent(self, event: QDropEvent):
        # Handle dropped files — if data is loaded, ask whether to add or replace.
        if hasattr(self, '_drop_zone'):
            self._drop_zone.setStyleSheet(_DROP_ZONE_NORMAL)
        paths = [
            u.toLocalFile() for u in event.mimeData().urls()
            if u.toLocalFile().endswith(SUPPORTED)
        ]
        if not paths:
            return

        if self._df_full is not None:
            # Data already exists — ask the user what they want to do
            clicked = message_box.custom(
                self, 'Add or Replace?',
                f'You dropped {len(paths)} file(s).\n'
                f'Currently loaded: {self._file_count} file(s), {len(self._df_full)} records.\n\n'
                'What would you like to do?',
                [
                    ('Add to existing data', QMessageBox.ButtonRole.AcceptRole),
                    ('Replace existing data', QMessageBox.ButtonRole.DestructiveRole),
                    ('Cancel', QMessageBox.ButtonRole.RejectRole),
                ],
            )
            if clicked == 'Add to existing data':
                self._load_paths(paths, append=True)
            elif clicked == 'Replace existing data':
                self._load_paths(paths, append=False)
            # Cancel (or closed) → do nothing
        else:
            # No data yet — just load them
            self._load_paths(paths, append=False)


    # Filtering and refresh


    def _apply_filters(self, f: dict):
        # Filter the full dataset and push the result to the dashboard. Analytics
        # and Forecasting have their own filtering, so they keep the full dataset.
        df = self._df_full.copy()

        if f['department'] != 'All':
            df = df[df['Department'] == f['department']]

        if f['job_role'] != 'All':
            df = df[df['Job_Role'] == f['job_role']]

        if f['status'] != 'All':
            df = df[df['Status'] == f['status']]

        if f.get('sex') and f['sex'] != 'All' and 'Sex' in df.columns:
            df = df[df['Sex'] == f['sex']]

        if f.get('ethnicity') and f['ethnicity'] != 'All' and 'Ethnicity' in df.columns:
            df = df[df['Ethnicity'] == f['ethnicity']]

        if f.get('age_group') and f['age_group'] != 'All' and 'Age_Group' in df.columns:
            df = df[df['Age_Group'] == f['age_group']]

        mode = f.get('period_mode', analytics.PERIOD_EMPLOYED)
        df = analytics.filter_period(df, f['date_from'], f['date_to'], mode)

        self._set_period(f['date_from'], f['date_to'], mode)
        self.dashboard_tab.update_data(df)
        # Advisor and Analytics can optionally use exactly what the dashboard shows
        description = self._describe_filters(f, mode)
        self.advisor_tab.set_dashboard_filter(df, description)
        self.analytics_tab.set_dashboard_filter(df, description)
        self.statusBar().showMessage(f'Showing {len(df)} records')

    @staticmethod
    def _describe_filters(f: dict, mode: str) -> str:
        # e.g. 'employed 1 Jan 2025 – 9 Oct 2026 · Department: Sales'
        verb = 'hired' if mode == analytics.PERIOD_HIRED else 'employed'
        parts = [f"{verb} {analytics.format_period(f['date_from'], f['date_to'])}"]
        for key, label in [('department', 'Department'), ('job_role', 'Job Role'),
                           ('status', 'Status'), ('sex', 'Sex'),
                           ('ethnicity', 'Ethnicity'), ('age_group', 'Age Group')]:
            if f.get(key) and f[key] != 'All':
                parts.append(f'{label}: {f[key]}')
        return ' · '.join(parts)

    def _set_period(self, date_from, date_to, mode):
        # Show the date range on the dashboard. The start is clamped to the
        # earliest hire in the data so the banner never claims a range we don't have.
        start = max(pd.Timestamp(date_from), self._df_full['Hire_Date'].min())
        self.dashboard_tab.set_period(start, pd.Timestamp(date_to), mode)

    def _on_tab_changed(self, index):
        # Show sidebar on Dashboard tab, hide it on Analytics/Forecasting tabs —
        # both have their own independent filtering (department dropdown, AI Advisor
        # reasons over the currently loaded dataset).
        if self._df_full is None:
            return
        if index == 0:  # Dashboard
            self.filter_panel.show()
            self.splitter.setSizes([220, 1060])
        else:
            self.filter_panel.hide()
            self.splitter.setSizes([0, 1280])
