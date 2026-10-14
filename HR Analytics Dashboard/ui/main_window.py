# Main application window

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QTabWidget, QFileDialog, QMessageBox, QStatusBar, QDialog,
    QLabel, QPushButton, QStackedWidget, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QDesktopServices, QDragEnterEvent, QDropEvent, QKeySequence
from PyQt6.QtWidgets import QToolButton

from core.data_loader import load_file
from core import analytics, report_generator
from core.data_cleaner import clean
from core.local_llm_client import LocalLLMClient
from ui.filter_panel import FilterPanel
from ui.dashboard_tab import DashboardTab
from ui.analytics_tab import AnalyticsTab
from ui.data_manager_dialog import DataOptionsDialog, DefaultDocumentsDialog
from ui import message_box, theme
from ui.forecasting_tab import ForecastingTab
from ui.advisor_tab import AdvisorTab
from ui.app_settings import AppSettings, SOURCE_DEFAULT, SOURCE_FILES
from ui.employees_tab import EmployeesTab
from ui.help_dialog import HelpDialog
from ui.report_dialog import ReportDialog

SUPPORTED = ('.csv', '.xlsx')

# Default documents folder
# Sidebar filter keys and display names
_FILTER_LABELS = [
    ('department', 'Department'), ('job_role', 'Job Role'), ('status', 'Status'),
    ('sex', 'Sex'), ('ethnicity', 'Ethnicity'), ('age_group', 'Age Group'),
]

# Filter sidebar width limits
_SIDEBAR_WIDTH = 220
_SIDEBAR_MAX_WIDTH = 400

# In the packaged .exe, bundled files are unpacked to sys._MEIPASS instead
_APP_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
DEFAULT_DOCS_DIR = _APP_DIR / 'Default documents'

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
    def __init__(self, settings: AppSettings | None = None):
        super().__init__()
        self._settings = settings or AppSettings()
        theme.apply_app_theme(QApplication.instance(), self._settings.theme)
        self.setWindowTitle('HR Employee Analytics Dashboard')
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        # Cleaned combined dataset
        self._df_full = None

        # Raw frames kept so appends can be cleaned together
        self._raw_frames: list[pd.DataFrame] = []

        # Track how many files are currently loaded for the status bar
        self._file_count = 0

        self._loaded_paths: list[str] = []
        self._loaded_source = SOURCE_DEFAULT

        self._dash_scope_text = ''
        self._dash_history_df = None

        self.llm_client = LocalLLMClient()

        self._build_ui()
        self._build_menu()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage('Open a CSV or XLSX file to get started  (File → Manage Data)')

        self._restore_window()
        self._load_startup_data()
        self._restore_tab()
        # Save layout changes only after the saved layout has been applied
        self.dashboard_tab.layout_changed.connect(self._save_dashboard_layout)
        self._watch_system_theme()


    # UI construction


    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        h.addWidget(self.splitter)

        # Left side placeholder until a file is loaded; hidden on welcome screen
        self.filter_panel = QWidget()
        self.splitter.addWidget(self.filter_panel)
        self.filter_panel.hide()

        # Right side stacked: page 0 = welcome, page 1 = dashboard tabs
        self.stack = QStackedWidget()
        self.splitter.addWidget(self.stack)
        # Extra window width goes to the charts, not the sidebar
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.splitterMoved.connect(self._remember_sidebar_width)
        self._sidebar_width = _SIDEBAR_WIDTH

        self.stack.addWidget(self._build_welcome_page())  # index 0

        self.tab_widget = QTabWidget()
        self.dashboard_tab = DashboardTab()
        self.employees_tab = EmployeesTab()
        self.analytics_tab = AnalyticsTab()
        self.forecasting_tab = ForecastingTab()
        self.advisor_tab = AdvisorTab(client=self.llm_client)
        self.analytics_tab.set_llm_client(self.llm_client)
        self.dashboard_tab.clear_filter_requested.connect(self._on_clear_filter)
        self.dashboard_tab.employee_requested.connect(self._show_employee)
        self.tab_widget.addTab(self.dashboard_tab, 'Dashboard')
        self.tab_widget.addTab(self.employees_tab, 'Employees')
        self.tab_widget.addTab(self.analytics_tab, 'Analytics')
        self.tab_widget.addTab(self.forecasting_tab, 'Forecasting')
        self.tab_widget.addTab(self.advisor_tab, 'AI Advisor')
        self.stack.addWidget(self.tab_widget)  # index 1
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _build_welcome_page(self):
        # Build the landing screen shown before any data is loaded
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

        # Manage Data, session-only loads, or edit the Default Documents folder
        self._manage_data_action = QAction('Manage Data...', self)
        self._manage_data_action.setShortcut('Ctrl+M')
        self._manage_data_action.triggered.connect(self._open_data_options)
        file_menu.addAction(self._manage_data_action)

        self._recent_menu = file_menu.addMenu('Open Recent')
        self._recent_menu.aboutToShow.connect(self._fill_recent_menu)

        self._reopen_action = QAction('Reopen last files on startup', self)
        self._reopen_action.setCheckable(True)
        self._reopen_action.setChecked(self._settings.reopen_last)
        self._reopen_action.setToolTip('Start with the files you were using last time, '
                                       'instead of always loading the Default documents folder')
        self._reopen_action.toggled.connect(lambda on: setattr(self._settings, 'reopen_last', on))
        file_menu.addAction(self._reopen_action)

        file_menu.addSeparator()

        self._report_action = QAction('Export PDF Summary Report...', self)
        self._report_action.setShortcut('Ctrl+P')
        self._report_action.triggered.connect(self._export_report)
        file_menu.addAction(self._report_action)

        file_menu.addSeparator()

        quit_action = QAction('Quit', self)
        quit_action.setShortcut('Ctrl+Q')
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menu.addMenu('View')
        theme_menu = view_menu.addMenu('Theme')
        self._theme_actions = {}
        group = QActionGroup(self)
        for mode, label in (('light', 'Light'), ('dark', 'Dark'), ('system', 'Follow system')):
            action = QAction(label, self, checkable=True)
            action.setChecked(mode == theme.current_setting())
            action.triggered.connect(lambda _checked=False, m=mode: self._set_theme(m))
            group.addAction(action)
            theme_menu.addAction(action)
            self._theme_actions[mode] = action
        toggle = QAction('Toggle Dark Mode', self)
        toggle.setShortcut('Ctrl+Shift+D')
        toggle.triggered.connect(self._toggle_theme)
        view_menu.addAction(toggle)

        view_menu.addSeparator()
        find_action = QAction('Find Employee...', self)
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self._find_employee)
        view_menu.addAction(find_action)
        reset_layout = QAction('Reset Dashboard Layout', self)
        reset_layout.triggered.connect(self.dashboard_tab.reset_layout)
        view_menu.addAction(reset_layout)
        forget = QAction('Forget Saved Settings...', self)
        forget.triggered.connect(self._forget_settings)
        view_menu.addAction(forget)

        help_menu = menu.addMenu('Help')
        guide_action = QAction('Quick Guide', self)
        guide_action.setShortcut('F1')
        guide_action.triggered.connect(lambda: HelpDialog(self).exec())
        help_menu.addAction(guide_action)

        self._theme_button = QToolButton()
        self._theme_button.setAutoRaise(True)
        self._theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_button.clicked.connect(self._toggle_theme)
        menu.setCornerWidget(self._theme_button, Qt.Corner.TopRightCorner)
        self._update_theme_button()

    def _set_theme(self, mode: str):
        self._settings.theme = mode
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.setUpdatesEnabled(False)
        try:
            theme.set_mode(QApplication.instance(), mode)
            for m, action in self._theme_actions.items():
                action.setChecked(m == mode)
            self._update_theme_button()
            self.dashboard_tab.refresh_theme()
            self.analytics_tab.refresh_theme()
            self.forecasting_tab.refresh_theme()
        finally:
            self.setUpdatesEnabled(True)
            QApplication.restoreOverrideCursor()

    def _toggle_theme(self):
        self._set_theme('light' if theme.is_dark() else 'dark')

    def _update_theme_button(self):
        dark = theme.is_dark()
        self._theme_button.setText('Light' if dark else 'Dark')
        self._theme_button.setToolTip('Switch to light mode' if dark else 'Switch to dark mode')

    def _watch_system_theme(self):
        try:
            QApplication.instance().styleHints().colorSchemeChanged.connect(self._on_system_theme_changed)
        except AttributeError:
            pass

    def _on_system_theme_changed(self, *_args):
        if theme.current_setting() == 'system':
            self._set_theme('system')

    def _restore_window(self):
        geometry = self._settings.geometry
        if geometry is not None:
            self.restoreGeometry(geometry)
        width = self._settings.sidebar_width
        if width:
            self._sidebar_width = max(150, min(width, _SIDEBAR_MAX_WIDTH))
        saved = self._settings.dashboard_layout
        if saved is not None:
            self.dashboard_tab.restore_layout(saved)

    def _restore_tab(self):
        if self._df_full is not None and self._settings.tab_index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(self._settings.tab_index)

    def _save_dashboard_layout(self):
        self._settings.dashboard_layout = self.dashboard_tab.layout_state()

    def _save_window(self):
        self._settings.geometry = self.saveGeometry()
        self._settings.tab_index = self.tab_widget.currentIndex()
        # Only sample the splitter width while visible
        if self.filter_panel.isVisible():
            self._remember_sidebar_width()
        self._settings.sidebar_width = self._sidebar_width
        self._save_dashboard_layout()
        self._settings.sync()

    def _forget_settings(self):
        reply = message_box.question(
            self, 'Forget saved settings?',
            'This clears the remembered theme, window size, dashboard layout, recent files and '
            'last-used data. They go back to their defaults next time you start the app.')
        if reply == QMessageBox.StandardButton.Yes:
            self._settings.clear()
            self._reopen_action.setChecked(True)
            self.statusBar().showMessage('Saved settings cleared')

    def _find_employee(self):
        if self._df_full is None:
            return
        self.tab_widget.setCurrentWidget(self.employees_tab)
        self.employees_tab.focus_search()

    def _show_employee(self, key):
        if self.employees_tab.show_employee(key):
            self.tab_widget.setCurrentWidget(self.employees_tab)


    # Core loading logic


    def _load_paths(self, paths: list[str], append: bool = False, source: str = SOURCE_FILES,
                    quiet: bool = False) -> bool:
        # Replace (append=False) or merge (append=True) data
        try:
            # Load each file individually so we get a clear error message per file
            new_frames = []
            for path in paths:
                new_frames.append(load_file(path))

            if append and self._raw_frames:
                # Merge with earlier raw frames and clean them together
                all_raw = self._raw_frames + new_frames
            else:
                all_raw = new_frames

            # Concatenate all raw frames into one DataFrame before cleaning
            combined_raw = pd.concat(all_raw, ignore_index=True)
            data_report: list[str] = []
            self._df_full = clean(combined_raw, data_report)

            # Save raw frames so future appends can include them
            self._raw_frames = all_raw
            self._file_count = len(all_raw)

            # Rebuild the filter panel with values from the new combined dataset
            new_fp = FilterPanel(self._df_full)
            new_fp.filters_changed.connect(self._apply_filters)
            new_fp.setMaximumWidth(_SIDEBAR_MAX_WIDTH)
            self.splitter.replaceWidget(0, new_fp)
            self.filter_panel = new_fp
            self._show_sidebar()

            # Switch from welcome page to dashboard if this is the first load
            if self.stack.currentIndex() == 0:
                self.stack.setCurrentIndex(1)

            # Analytics and Forecasting use the full dataset
            self.analytics_tab.update_data(self._df_full)
            self.employees_tab.update_data(self._df_full)
            self.forecasting_tab.update_data(self._df_full)
            self.advisor_tab.update_data(self._df_full)
            self.filter_panel.emit_filters()
            self.dashboard_tab.show_data_check(len(combined_raw), len(self._df_full), data_report)

            action = 'Added' if (append and self._file_count > len(paths)) else 'Loaded'
            self.statusBar().showMessage(
                f'{action} {len(paths)} file(s), '
                f'{len(self._df_full)} records from {self._file_count} file(s) total'
            )
            self._remember_loaded(paths, append, source)
            return True

        except Exception as e:
            if not quiet:
                message_box.critical(self, 'Error loading file', str(e))
            return False

    def _remember_loaded(self, paths: list[str], append: bool, source: str):
        if append and self._loaded_paths:
            self._loaded_paths = self._loaded_paths + [p for p in paths if p not in self._loaded_paths]
            self._loaded_source = SOURCE_FILES
        else:
            self._loaded_paths = list(paths)
            self._loaded_source = source
        self._settings.set_last_data(self._loaded_source, self._loaded_paths)
        if source == SOURCE_FILES:
            self._settings.add_recent(paths)

    def _open_files(self):
        # Open a file dialog; selected files replace the current dataset
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

    def _load_startup_data(self):
        s = self._settings
        if s.reopen_last and s.last_source == SOURCE_FILES and s.last_paths:
            existing = [p for p in s.last_paths if os.path.isfile(p)]
            missing = len(s.last_paths) - len(existing)
            if existing and self._load_paths(existing, append=False, source=SOURCE_FILES, quiet=True):
                note = f'  ({missing} earlier file(s) could not be found)' if missing else ''
                self.statusBar().showMessage(
                    f'Reopened your last session: {len(self._df_full)} records from '
                    f'{len(existing)} file(s){note}')
                return
            self.statusBar().showMessage('Your last files could not be reopened; loading the default documents')
        self._load_default_documents()

    def _load_default_documents(self):
        # Auto-load the Default Documents folder on startup
        paths = self._default_document_paths()
        if not paths:
            return

        if self._load_paths(paths, append=False, source=SOURCE_DEFAULT):
            self.statusBar().showMessage(
                f'Loaded {len(paths)} default document(s): '
                f'{len(self._df_full)} records from "Default documents"'
            )

    def _fill_recent_menu(self):
        self._recent_menu.clear()
        recent = self._settings.recent_files
        if not recent:
            self._recent_menu.addAction('No recent files').setEnabled(False)
            return
        for path in recent:
            action = self._recent_menu.addAction(f'{Path(path).name}')
            action.setToolTip(path)
            action.setStatusTip(path)
            action.triggered.connect(lambda _c=False, p=path: self._open_recent(p))
        self._recent_menu.addSeparator()
        self._recent_menu.addAction('Clear list', self._settings.clear_recent)

    def _open_recent(self, path: str):
        if not os.path.isfile(path):
            self._settings.remove_recent(path)
            message_box.warning(self, 'File not found', f'{path}\n\ncould not be found, so it was removed from the list.')
            return
        self._load_paths([path], append=False)

    def _reset_to_welcome(self):
        # Clear all loaded data and return to the welcome/upload screen
        self._df_full = None
        self._raw_frames = []
        self._file_count = 0
        self._loaded_paths = []
        self._settings.set_last_data(None)
        self.employees_tab.update_data(None)
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
            self._load_paths(paths, append=False, source=SOURCE_DEFAULT)


    # Drag-and-drop


    def closeEvent(self, event):
        self._save_window()
        self.advisor_tab.shutdown()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        # Accept drag if at least one dragged file is a supported type
        if event.mimeData().hasUrls():
            if any(u.toLocalFile().endswith(SUPPORTED) for u in event.mimeData().urls()):
                event.acceptProposedAction()
                if self.stack.currentIndex() == 0 and hasattr(self, '_drop_zone'):
                    self._drop_zone.setStyleSheet(_DROP_ZONE_ACTIVE)

    def dragLeaveEvent(self, event):
        # Reset drop zone highlight when the drag leaves the window
        if hasattr(self, '_drop_zone'):
            self._drop_zone.setStyleSheet(_DROP_ZONE_NORMAL)

    def dropEvent(self, event: QDropEvent):
        # Handle dropped files, if data is loaded, ask whether to add or replace
        if hasattr(self, '_drop_zone'):
            self._drop_zone.setStyleSheet(_DROP_ZONE_NORMAL)
        paths = [
            u.toLocalFile() for u in event.mimeData().urls()
            if u.toLocalFile().endswith(SUPPORTED)
        ]
        if not paths:
            return

        if self._df_full is not None:
            # Data already exists, ask the user what they want to do
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
            # No data yet, just load them
            self._load_paths(paths, append=False)

    def _export_report(self):
        if self._df_full is None:
            message_box.information(self, 'No data', 'Load some employee data first, then export a report.')
            return
        dash_df, prev_df, prev_label, kpi_metrics, chart_configs = self.dashboard_tab.report_inputs()
        analytics_charts = self.analytics_tab.report_charts()

        dlg = ReportDialog(len(kpi_metrics), len(chart_configs), len(analytics_charts),
                           self._dash_scope_text or 'All loaded data', self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        options = dlg.options()
        use_dashboard = dlg.use_dashboard_scope()

        if use_dashboard and (dash_df is None or len(dash_df) == 0):
            message_box.warning(self, 'Nothing to report',
                                'No employees match the current dashboard filters, so there is nothing to summarise. '
                                'Change the filters, or choose "All loaded data".')
            return

        suggested = f'HR_Summary_{date.today().isoformat()}.pdf'
        start_dir = self._settings.report_dir or str(Path.home())
        path, _ = QFileDialog.getSaveFileName(self, 'Save PDF Report', str(Path(start_dir) / suggested),
                                              'PDF files (*.pdf)')
        if not path:
            return
        if not path.lower().endswith('.pdf'):
            path += '.pdf'

        if use_dashboard:
            data = report_generator.ReportData(
                df=dash_df, scope=self._dash_scope_text, history_df=self._dash_history_df,
                kpis=report_generator.compute_kpis(dash_df, kpi_metrics, prev_df),
                previous_label=prev_label, chart_configs=chart_configs, analytics_charts=analytics_charts)
        else:
            data = report_generator.ReportData(
                df=self._df_full, scope=f'All loaded data, {self._file_count} file(s)',
                history_df=self._df_full,
                kpis=report_generator.compute_kpis(self._df_full, kpi_metrics),
                chart_configs=chart_configs, analytics_charts=analytics_charts)

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage('Creating the PDF report...')
        QApplication.processEvents()
        try:
            pages = report_generator.generate_report(path, data, options)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.statusBar().showMessage('The report could not be created')
            message_box.critical(self, 'Report failed',
                                 f'The report could not be created:\n{e}\n\n'
                                 'If the file is open in another program, close it and try again.')
            return
        QApplication.restoreOverrideCursor()
        self._settings.report_dir = os.path.dirname(path)
        self.statusBar().showMessage(f'Saved a {pages}-page report to {path}')
        reply = message_box.question(self, 'Report saved',
                                     f'The {pages}-page report was saved to:\n{path}\n\nOpen it now?')
        if reply == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))


    # Filtering and refresh


    def _apply_filters(self, f: dict):
        # Filter the data and update the dashboard
        base = self._apply_group_filters(self._df_full.copy(), f)
        mode = f.get('period_mode', analytics.PERIOD_EMPLOYED)
        df = analytics.filter_period(base, f['date_from'], f['date_to'], mode)

        # Same filters for the previous period
        prev_start, prev_end = analytics.previous_period(f['date_from'], f['date_to'])
        previous, previous_label = None, ''
        if prev_start >= self._df_full['Hire_Date'].min():
            previous = analytics.filter_period(base, prev_start, prev_end, mode)
            previous_label = analytics.format_period(prev_start, prev_end)

        self._dash_history_df = base
        self._set_period(f['date_from'], f['date_to'], mode)
        self.dashboard_tab.update_data(df, previous, previous_label)
        self._after_filters_applied(f, df, mode)

    @staticmethod
    def _apply_group_filters(df, f: dict):
        # Department / role / status / sex / ethnicity / age group filters
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
        return df

    def _after_filters_applied(self, f: dict, df, mode: str):
        # Advisor and Analytics can use the dashboard's data
        self.dashboard_tab.set_active_filters([
            (key, f'{label}: {f[key]}') for key, label in _FILTER_LABELS if f.get(key) not in (None, 'All')
        ])
        description = self._describe_filters(f, mode)
        self._dash_scope_text = description
        self.advisor_tab.set_dashboard_filter(df, description)
        self.analytics_tab.set_dashboard_filter(df, description)
        self.statusBar().showMessage(f'Showing {len(df)} records')

    @staticmethod
    def _describe_filters(f: dict, mode: str) -> str:
        # e.g. 'employed 1 Jan 2025 – 9 Oct 2026 · Department: Sales'
        verb = 'hired' if mode == analytics.PERIOD_HIRED else 'employed'
        parts = [f"{verb} {analytics.format_period(f['date_from'], f['date_to'])}"]
        for key, label in _FILTER_LABELS:
            if f.get(key) and f[key] != 'All':
                parts.append(f'{label}: {f[key]}')
        return ' · '.join(parts)

    def _on_clear_filter(self, key: str):
        # A filter chip's ✕ (or 'Clear all') on the dashboard
        if not isinstance(self.filter_panel, FilterPanel):
            return
        if key == '*':
            for k, _label in _FILTER_LABELS:
                self.filter_panel._combos()[k].setCurrentIndex(0)
            self.filter_panel.emit_filters()
        else:
            self.filter_panel.clear_filter(key)

    def _set_period(self, date_from, date_to, mode):
        # Show the date range on the dashboard
        start = max(pd.Timestamp(date_from), self._df_full['Hire_Date'].min())
        self.dashboard_tab.set_period(start, pd.Timestamp(date_to), mode)

    def _on_tab_changed(self, index):
        # Show the sidebar only on the Dashboard tab
        if self._df_full is None:
            return
        if index == 0:  # Dashboard
            self._show_sidebar()
        else:
            self.filter_panel.hide()

    def _show_sidebar(self):
        # Show the filter sidebar at the width the user last dragged it to
        self.filter_panel.show()
        total = max(self.splitter.width(), self._sidebar_width + 1)
        self.splitter.setSizes([self._sidebar_width, total - self._sidebar_width])

    def _remember_sidebar_width(self, *_args):
        width = self.splitter.sizes()[0]
        if width > 0:  # 0 = dragged closed; reopen at the last real width
            self._sidebar_width = width
