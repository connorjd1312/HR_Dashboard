import copy
import io
import json
import uuid

import numpy as np
import pandas as pd

from PyQt6.QtWidgets import (
    QGridLayout,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QLineEdit, QToolButton,
    QFileDialog, QApplication, QTableWidget, QTableWidgetItem,
    QHeaderView, QToolTip, QCheckBox, QMenu,
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPixmap, QFont, QKeySequence, QShortcut

import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from core import analytics
from core.history import History
from ui import theme
from ui.chart_prompt_dialog import ADD_AS_NEW, ChartPromptDialog
from ui.chart_widget import ChartWithToolbar, make_splitter, set_title_with_period
from ui.series_dialog import PALETTE, TEMPLATES, SeriesDialog, series_from_template

# ── Colour / style constants ──────────────────────────────────────────────────

_NAVY = theme.NAVY
_NAVY_HOVER = theme.BLUE
_NAVY_PRESS = theme.NAVY_PRESS
_GREY_BG = theme.BG
_BORDER = theme.BORDER
_RED = theme.RED
_RED_HOVER = theme.RED_BG

_TOOL_BTN_STYLE = '''
    QPushButton {
        font-size: 12px; background: transparent;
        border: 1px solid #DDD; border-radius: 4px;
        padding: 0 8px; color: #444;
    }
    QPushButton:hover { background: #F0F4FF; border-color: #2E75B6; }
    QPushButton:disabled { color: #BBB; border-color: #EEE; }
    QPushButton::menu-indicator { image: none; }
'''

# Side panel widths — kept narrow enough for the app to fit a 1280px-wide screen
_LEFT_PANEL_WIDTH = 230
_RIGHT_STRIP_WIDTH = 184


# ── _SeriesCard ───────────────────────────────────────────────────────────────

# One row in the series list — coloured dot, label, edit and delete buttons.
class _SeriesCard(QFrame):

    def __init__(self, series, on_edit, on_delete, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f'''
            QFrame {{
                background: white;
                border-radius: 6px;
                border: 1px solid {_BORDER};
            }}
        ''')
        # Grows taller for long names (they wrap) instead of cutting them off
        self.setMinimumHeight(52)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 8, 8)
        row.setSpacing(8)

        dot = QLabel('●')
        dot.setStyleSheet(
            f'color: {series["color"]}; font-size: 18px; border: none; background: transparent;'
        )
        dot.setFixedWidth(22)
        row.addWidget(dot)

        lbl = QLabel(series['label'])
        lbl.setStyleSheet('font-size: 12px; color: #333; border: none; background: transparent;')
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # Long labels wrap (and show in full on hover) instead of pushing the
        # buttons off the side of the panel
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(1)
        lbl.setToolTip(series['label'])
        row.addWidget(lbl, stretch=1)

        edit_btn = QPushButton('Edit')
        edit_btn.setFixedSize(46, 28)
        edit_btn.setStyleSheet('''
            QPushButton {
                font-size: 11px; border: 1px solid #CCC;
                border-radius: 4px; background: white; color: #555;
            }
            QPushButton:hover { background: #F0F0F0; }
        ''')
        edit_btn.clicked.connect(on_edit)
        row.addWidget(edit_btn)

        del_btn = QPushButton('✕')
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(f'''
            QPushButton {{
                font-size: 13px; border: none; border-radius: 4px;
                background: transparent; color: {_RED};
            }}
            QPushButton:hover {{ background: {_RED_HOVER}; }}
        ''')
        del_btn.clicked.connect(on_delete)
        row.addWidget(del_btn)


# ── _ThumbnailCard ────────────────────────────────────────────────────────────

# Clickable chart thumbnail in the right sidebar.
class _ThumbnailCard(QFrame):

    def __init__(self, chart_dict, pixmap, is_active, on_click, on_delete, parent=None):
        super().__init__(parent)
        border_color = _NAVY if is_active else _BORDER
        self.setStyleSheet(f'''
            QFrame {{
                background: white;
                border: 2px solid {border_color};
                border-radius: 6px;
            }}
        ''')
        self.setFixedWidth(168)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        # Image container with delete button overlay
        img_container = QWidget()
        img_container.setFixedSize(160, 104)
        img_container.setStyleSheet('background: transparent; border: none;')

        img_lbl = QLabel(img_container)
        img_lbl.setGeometry(0, 0, 160, 104)
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_lbl.setStyleSheet('border: none; background: #F5F7FA; border-radius: 4px;')
        if pixmap and not pixmap.isNull():
            img_lbl.setPixmap(
                pixmap.scaled(160, 104, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
            )
        else:
            img_lbl.setText('No data')
            img_lbl.setStyleSheet(
                'border: none; background: #F0F0F0; border-radius: 4px;'
                ' color: #999; font-size: 11px;'
            )

        # Delete button overlaid at top-right
        del_btn = QPushButton('✕', img_container)
        del_btn.setGeometry(162, 2, 22, 22)
        del_btn.setStyleSheet('''
            QPushButton {
                background: rgba(200,50,50,0.85); color: white;
                border: none; border-radius: 11px; font-size: 10px; font-weight: bold;
            }
            QPushButton:hover { background: rgba(180,30,30,1); }
        ''')
        del_btn.clicked.connect(on_delete)

        outer.addWidget(img_container)

        title_lbl = QLabel(chart_dict.get('title', 'Untitled'))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f'font-size: 11px; color: {_NAVY}; font-weight: bold; border: none; background: transparent;'
        )
        outer.addWidget(title_lbl)

        self._on_click = on_click

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


# ── AnalyticsTab ──────────────────────────────────────────────────────────────

# Multi-chart analytics builder with series management and thumbnail navigation.
class AnalyticsTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = None          # data the charts are drawn from
        self._full_df = None     # all loaded data
        self._dash_df = None     # the dashboard's filtered employees
        self._dash_scope = ''
        self._charts = []          # list of {'id', 'title', 'series_list'}
        self._active_idx = -1
        self._left_visible = True
        self._focus_mode = False
        self._hover_cid = None
        self._show_period = False
        self._llm_client = None
        self._history = History()

        self._build_ui()
        self._add_new_chart(record=False)
        self._history.reset(self._snapshot())
        self._update_history_buttons()

        # A focused text box keeps its own Ctrl+Z for the text being typed.
        scope = Qt.ShortcutContext.WidgetWithChildrenShortcut
        for keys, slot in (('Ctrl+Z', self._undo), ('Ctrl+Y', self._redo), ('Ctrl+Shift+Z', self._redo)):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(scope)
            sc.activated.connect(slot)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._left_panel = self._build_left_panel()
        root.addWidget(self._left_panel)

        root.addWidget(self._build_center_panel(), stretch=1)
        self._right_strip = self._build_right_strip()
        root.addWidget(self._right_strip)

    # ── Left panel (collapsible) ──────────────────────────────────────────────

    def _build_left_panel(self):
        panel = QWidget()
        panel.setFixedWidth(_LEFT_PANEL_WIDTH)
        panel.setStyleSheet(f'background: {_GREY_BG}; border-right: 1px solid {_BORDER};')
        lv = QVBoxLayout(panel)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f'background-color: {_NAVY};')
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 8, 0)

        title_lbl = QLabel('Analytics Builder')
        title_lbl.setStyleSheet('color: white; font-size: 14px; font-weight: bold;')
        hl.addWidget(title_lbl, stretch=1)

        self._collapse_btn = QPushButton('◀')
        self._collapse_btn.setFixedSize(28, 28)
        self._collapse_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.15); color: white;
                border: none; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.3); }
        ''')
        self._collapse_btn.clicked.connect(self._toggle_left_panel)
        hl.addWidget(self._collapse_btn)

        lv.addWidget(header)

        # Scrollable series card list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet('background: transparent;')

        self._series_container = QWidget()
        self._series_container.setStyleSheet('background: transparent;')
        self._series_layout = QVBoxLayout(self._series_container)
        self._series_layout.setContentsMargins(10, 10, 10, 10)
        self._series_layout.setSpacing(8)
        self._series_layout.addStretch()

        scroll.setWidget(self._series_container)
        lv.addWidget(scroll, stretch=1)

        # Footer buttons
        footer = QWidget()
        footer.setFixedHeight(168)
        footer.setStyleSheet(f'background: {_GREY_BG}; border-top: 1px solid {_BORDER};')
        fv = QVBoxLayout(footer)
        fv.setContentsMargins(10, 10, 10, 12)
        fv.setSpacing(8)

        add_btn = QPushButton('+ Add Series')
        add_btn.setFixedHeight(38)
        add_btn.setStyleSheet(f'''
            QPushButton {{
                background: {_NAVY}; color: white;
                border-radius: 5px; font-size: 13px; border: none;
            }}
            QPushButton:hover   {{ background: {_NAVY_HOVER}; }}
            QPushButton:pressed {{ background: {_NAVY_PRESS}; }}
        ''')
        add_btn.clicked.connect(self._add_series)

        clear_btn = QPushButton('Clear All')
        clear_btn.setFixedHeight(30)
        clear_btn.setStyleSheet(f'''
            QPushButton {{
                background: white; color: {_RED};
                border: 1px solid {_BORDER}; border-radius: 5px; font-size: 12px;
            }}
            QPushButton:hover {{ background: {_RED_HOVER}; }}
        ''')
        clear_btn.clicked.connect(self._clear_series)

        # Kept in this fixed-width panel so the top bar and minimum window width do not grow.
        history_row = QHBoxLayout()
        history_row.setSpacing(6)
        self._undo_btn = QPushButton('Undo')
        self._redo_btn = QPushButton('Redo')
        for btn, slot in ((self._undo_btn, self._undo), (self._redo_btn, self._redo)):
            btn.setFixedHeight(30)
            btn.setStyleSheet(_TOOL_BTN_STYLE)
            btn.clicked.connect(slot)
            history_row.addWidget(btn, stretch=1)
        self._ai_btn = QPushButton('Describe a chart')
        self._ai_btn.setToolTip('Describe a chart in your own words and let the app build it')
        self._ai_btn.setFixedHeight(30)
        self._ai_btn.setStyleSheet(_TOOL_BTN_STYLE)
        self._ai_btn.clicked.connect(self._open_chart_prompt)

        fv.addLayout(history_row)
        fv.addWidget(self._ai_btn)
        fv.addWidget(add_btn)
        fv.addWidget(clear_btn)
        lv.addWidget(footer)

        return panel

    def _toggle_focus_mode(self):
        # Focus mode hides the builder and My Charts panels so the chart fills the tab.
        self._focus_mode = not self._focus_mode
        self._left_panel.setVisible(not self._focus_mode)
        self._right_strip.setVisible(not self._focus_mode)
        self._focus_btn.setText('⤡ Exit Focus' if self._focus_mode else '⤢ Focus')

    def _set_table_section_open(self, is_open: bool):
        # Collapsed: only the toggle button shows. Open: table gets ~a third of the height.
        if is_open:
            self._table_section.setMaximumHeight(16777215)
            total = sum(self._chart_table_split.sizes()) or 600
            self._chart_table_split.setSizes([total * 2 // 3, total // 3])
        else:
            self._table_section.setMaximumHeight(28)

    def _toggle_left_panel(self):
        if self._left_visible:
            self._left_panel.setFixedWidth(0)
            self._collapse_btn.setText('▶')
            self._left_visible = False
        else:
            self._left_panel.setFixedWidth(_LEFT_PANEL_WIDTH)
            self._collapse_btn.setText('◀')
            self._left_visible = True

    # ── Center panel ──────────────────────────────────────────────────────────

    def _build_center_panel(self):
        panel = QWidget()
        panel.setStyleSheet('background: white;')
        cv = QVBoxLayout(panel)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────
        top_bar = QWidget()
        top_bar.setFixedHeight(52)
        top_bar.setStyleSheet(f'background: white; border-bottom: 1px solid {_BORDER};')
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(16, 0, 12, 0)
        tb.setSpacing(8)

        self._title_edit = QLineEdit('Chart 1')
        self._title_edit.setStyleSheet(f'''
            QLineEdit {{
                font-size: 16px; font-weight: bold; color: {_NAVY};
                border: none; background: transparent;
                border-bottom: 2px solid transparent;
            }}
            QLineEdit:focus {{
                border-bottom: 2px solid {_NAVY_HOVER};
                background: #F8FAFF;
            }}
        ''')
        self._title_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._title_edit.textChanged.connect(self._on_title_changed)
        # Long titles: show the start (not the end) when not editing, full title on hover
        self._title_edit.editingFinished.connect(lambda: self._title_edit.setCursorPosition(0))
        # One undo step per finished rename, not per keystroke.
        self._title_edit.editingFinished.connect(lambda: self._commit('Rename chart'))
        tb.addWidget(self._title_edit, stretch=1)

        tb.addStretch()

        # Icon buttons
        export_btn = QPushButton('⬇ Export ▾')
        export_btn.setToolTip('Copy the chart, or save it as an image or PDF')
        export_btn.setFixedHeight(32)
        export_btn.setStyleSheet(_TOOL_BTN_STYLE)
        export_menu = QMenu(export_btn)
        export_menu.addAction('📋  Copy to clipboard', self._copy_to_clipboard)
        export_menu.addAction('🖼  Save as PNG image…', self._export_png)
        export_menu.addAction('📄  Save as PDF…', self._export_pdf)
        export_btn.setMenu(export_menu)
        tb.addWidget(export_btn)

        for icon, tip, slot in [
            ('💾 Save',  'Save this chart setup to a file',   self._save_config),
            ('📂 Load',  'Load a saved chart setup',          self._load_config),
        ]:
            btn = QPushButton(icon)
            btn.setToolTip(tip)
            btn.setFixedHeight(32)
            btn.setStyleSheet(_TOOL_BTN_STYLE)
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        self._use_filters_box = QCheckBox('Dashboard filters')
        self._use_filters_box.setToolTip(
            'Build charts from the employees the Dashboard tab is showing, '
            'instead of all loaded data')
        self._use_filters_box.toggled.connect(self._on_use_filters_toggled)
        tb.addWidget(self._use_filters_box)

        self._focus_btn = QPushButton('⤢ Focus')
        self._focus_btn.setToolTip('Hide the side panels to make the chart bigger')
        self._focus_btn.setFixedHeight(32)
        self._focus_btn.setStyleSheet(f'''
            QPushButton {{
                font-size: 12px; background: {_NAVY}; color: white;
                border: none; border-radius: 4px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {_NAVY_HOVER}; }}
        ''')
        self._focus_btn.clicked.connect(self._toggle_focus_mode)
        tb.addWidget(self._focus_btn)

        cv.addWidget(top_bar)

        # ── Main chart widget ─────────────────────────────────────────────
        self._main_widget = ChartWithToolbar(width=10, height=6)
        self._placeholder = self._build_empty_state()

        chart_area = QWidget()
        ca = QVBoxLayout(chart_area)
        ca.setContentsMargins(0, 0, 0, 0)
        ca.addWidget(self._main_widget, stretch=1)
        ca.addWidget(self._placeholder, stretch=1)
        self._main_widget.hide()

        # Chart and data table share a splitter so the user can drag the
        # divider to give either one more room.
        self._chart_table_split = make_splitter(Qt.Orientation.Vertical)
        self._chart_table_split.addWidget(chart_area)
        cv.addWidget(self._chart_table_split, stretch=1)

        self._table_section = QWidget()
        ts = QVBoxLayout(self._table_section)
        ts.setContentsMargins(0, 0, 0, 0)
        ts.setSpacing(0)

        # ── Data table (collapsible) ──────────────────────────────────────
        self._table_visible = False
        self._table_toggle_btn = QPushButton('▼ Data Table')
        self._table_toggle_btn.setFixedHeight(28)
        self._table_toggle_btn.setStyleSheet(f'''
            QPushButton {{
                background: {_GREY_BG}; border: none;
                border-top: 1px solid {_BORDER}; font-size: 11px;
                color: #555; text-align: left; padding-left: 12px;
            }}
            QPushButton:hover {{ background: #EAECF0; }}
        ''')
        self._table_toggle_btn.clicked.connect(self._toggle_table)
        ts.addWidget(self._table_toggle_btn)

        self._table = QTableWidget()
        self._table.setMinimumHeight(80)
        self._table.setStyleSheet('''
            QTableWidget {
                font-size: 11px; gridline-color: #E8E8E8;
                border: none; border-top: 1px solid #E0E0E0;
            }
            QHeaderView::section {
                background: #F5F7FA; font-weight: bold;
                font-size: 11px; padding: 4px;
                border: none; border-bottom: 1px solid #E0E0E0;
            }
        ''')
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.hide()
        ts.addWidget(self._table, stretch=1)
        self._chart_table_split.addWidget(self._table_section)
        self._set_table_section_open(False)

        return panel

    def _build_empty_state(self) -> QWidget:
        # Shown when the chart has no series: quick-start templates, or build your own.
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch()
        title = QLabel('Start a chart')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {_NAVY};')
        v.addWidget(title)
        hint = QLabel('Pick a common chart below, or click  "+ Add Series"  on the left to build your own.\n'
                      'You can add several series to compare them on one chart.')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet('font-size: 12px; color: #777;')
        v.addWidget(hint)
        v.addSpacing(6)
        ai_row = QHBoxLayout()
        ai_row.addStretch()
        ai_btn = QPushButton('Describe a chart in your own words...')
        ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_btn.setMinimumHeight(40)
        ai_btn.setStyleSheet(f'''
            QPushButton {{
                background: {_NAVY}; color: white; border: none;
                border-radius: 6px; padding: 6px 18px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {_NAVY_HOVER}; }}
        ''')
        ai_btn.clicked.connect(self._open_chart_prompt)
        ai_row.addWidget(ai_btn)
        ai_row.addStretch()
        v.addLayout(ai_row)
        v.addSpacing(6)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, name in enumerate(TEMPLATES):
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(40)
            btn.setStyleSheet(f'''
                QPushButton {{
                    background: #F0F4FF; color: {_NAVY}; border: 1px solid #C9D7F0;
                    border-radius: 6px; padding: 6px 14px; font-size: 12px;
                }}
                QPushButton:hover {{ background: #E1EAFB; border-color: {_NAVY_HOVER}; }}
            ''')
            btn.clicked.connect(lambda _=False, n=name: self._add_template(n))
            grid.addWidget(btn, i // 2, i % 2)
        row = QHBoxLayout()
        row.addStretch()
        row.addLayout(grid)
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        return page

    def _add_template(self, name: str):
        if self._df is None:
            return
        if self._active_idx < 0:
            self._add_new_chart()
        self._add_series_dicts(series_from_template(name, self._df), 'Add chart template')

    def _add_series_dicts(self, series: list, label: str = 'Add series'):
        self._active_series().extend(series)
        self._rebuild_series_cards()
        self._render_active()
        self._update_thumbnails()
        self._commit(label)

    def _next_color(self) -> str:
        # First palette colour not already used on this chart
        used = {s.get('color') for s in self._active_series()}
        return next((c for c in PALETTE if c not in used), PALETTE[len(used) % len(PALETTE)])

    # ── Right thumbnail strip ─────────────────────────────────────────────────

    def _build_right_strip(self):
        strip = QWidget()
        strip.setFixedWidth(_RIGHT_STRIP_WIDTH)
        strip.setStyleSheet(f'background: {_GREY_BG}; border-left: 1px solid {_BORDER};')
        sv = QVBoxLayout(strip)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(f'background: {_NAVY};')
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        hl.addWidget(QLabel(
            'My Charts',
            styleSheet='color: white; font-size: 13px; font-weight: bold;'
        ))
        sv.addWidget(hdr)

        # Scrollable thumbnail area
        self._thumb_scroll = QScrollArea()
        self._thumb_scroll.setWidgetResizable(True)
        self._thumb_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._thumb_scroll.setStyleSheet('background: transparent;')

        self._thumb_container = QWidget()
        self._thumb_container.setStyleSheet('background: transparent;')
        self._thumb_layout = QVBoxLayout(self._thumb_container)
        self._thumb_layout.setContentsMargins(8, 8, 8, 8)
        self._thumb_layout.setSpacing(8)
        self._thumb_layout.addStretch()

        self._thumb_scroll.setWidget(self._thumb_container)
        sv.addWidget(self._thumb_scroll, stretch=1)

        # New chart button
        new_chart_btn = QPushButton('＋ New Chart')
        new_chart_btn.setFixedHeight(38)
        new_chart_btn.setStyleSheet(f'''
            QPushButton {{
                background: {_NAVY}; color: white;
                border: none; font-size: 13px;
            }}
            QPushButton:hover {{ background: {_NAVY_HOVER}; }}
            QPushButton:pressed {{ background: {_NAVY_PRESS}; }}
        ''')
        new_chart_btn.clicked.connect(self._add_new_chart)
        sv.addWidget(new_chart_btn)

        return strip

    # ── Public API ────────────────────────────────────────────────────────────

    def update_data(self, df):
        self._full_df = df
        self._apply_data_source()

    def set_dashboard_filter(self, df, description: str):
        self._dash_df = df
        self._dash_scope = description
        if self._use_filters_box.isChecked():
            self._apply_data_source()

    def _on_use_filters_toggled(self, _checked):
        self._apply_data_source()

    def _apply_data_source(self):
        # Charts use either all loaded data or the dashboard's filtered employees
        use_dash = self._using_dashboard_filters()
        self._df = self._dash_df if use_dash else self._full_df
        self._use_filters_box.setToolTip(
            f'Using the dashboard filters: {self._dash_scope}' if use_dash else
            'Build charts from the employees the Dashboard tab is showing, '
            'instead of all loaded data')
        if self._active_idx >= 0:
            self._render_active()
            self._update_thumbnails()

    # ── Multi-chart management ────────────────────────────────────────────────

    def _add_new_chart(self, record: bool = True):
        chart_num = len(self._charts) + 1
        chart = {
            'id':          str(uuid.uuid4())[:8],
            'title':       f'Chart {chart_num}',
            'series_list': [],
        }
        self._charts.append(chart)
        self._active_idx = len(self._charts) - 1
        self._title_edit.blockSignals(True)
        self._title_edit.setText(chart['title'])
        self._title_edit.blockSignals(False)
        self._rebuild_series_cards()
        self._update_thumbnails()
        self._render_active()
        if record:
            self._commit('New chart')

    def _delete_chart(self, idx):
        if len(self._charts) <= 1:
            # Always keep at least one chart; just clear it
            self._charts[0]['series_list'] = []
            self._charts[0]['title'] = 'Chart 1'
            self._active_idx = 0
            self._title_edit.blockSignals(True)
            self._title_edit.setText('Chart 1')
            self._title_edit.blockSignals(False)
            self._rebuild_series_cards()
            self._update_thumbnails()
            self._render_active()
            self._commit('Clear chart')
            return

        self._charts.pop(idx)
        if self._active_idx >= len(self._charts):
            self._active_idx = len(self._charts) - 1
        elif self._active_idx > idx:
            self._active_idx -= 1

        self._title_edit.blockSignals(True)
        self._title_edit.setText(self._charts[self._active_idx]['title'])
        self._title_edit.blockSignals(False)
        self._rebuild_series_cards()
        self._update_thumbnails()
        self._render_active()
        self._commit('Delete chart')

    def _set_active_chart(self, idx):
        if idx < 0 or idx >= len(self._charts):
            return
        self._active_idx = idx
        self._title_edit.blockSignals(True)
        self._title_edit.setText(self._charts[idx]['title'])
        self._title_edit.blockSignals(False)
        self._rebuild_series_cards()
        self._render_active()
        self._update_thumbnails()

    def _on_title_changed(self, text):
        self._title_edit.setToolTip(text)
        if not self._title_edit.hasFocus():
            self._title_edit.setCursorPosition(0)
        if self._active_idx >= 0:
            self._charts[self._active_idx]['title'] = text
            self._update_thumbnails()

    def _snapshot(self) -> list:
        return copy.deepcopy(self._charts)

    def _commit(self, label: str):
        if self._history.push(self._snapshot(), label):
            self._update_history_buttons()

    def _undo(self):
        state = self._history.undo()
        if state is not None:
            self._restore(state)

    def _redo(self):
        state = self._history.redo()
        if state is not None:
            self._restore(state)

    def _restore(self, charts: list):
        self._active_idx = self._chart_to_show(self._charts, charts)
        self._charts = charts
        self._title_edit.blockSignals(True)
        self._title_edit.setText(self._charts[self._active_idx]['title'])
        self._title_edit.blockSignals(False)
        self._rebuild_series_cards()
        self._render_active()
        self._update_thumbnails()
        self._update_history_buttons()

    def _chart_to_show(self, old: list, new: list) -> int:
        # Jump to the first chart that changed so undoing a deletion shows it again.
        before = {c['id']: c for c in old}
        for i, c in enumerate(new):
            if before.get(c['id']) != c:
                return i
        current = old[self._active_idx]['id'] if 0 <= self._active_idx < len(old) else None
        for i, c in enumerate(new):
            if c['id'] == current:
                return i
        return min(max(self._active_idx, 0), len(new) - 1)

    def _update_history_buttons(self):
        h = self._history
        self._undo_btn.setEnabled(h.can_undo())
        self._redo_btn.setEnabled(h.can_redo())
        self._undo_btn.setToolTip(f'Undo: {h.undo_label()}  (Ctrl+Z)' if h.can_undo() else 'Nothing to undo')
        self._redo_btn.setToolTip(f'Redo: {h.redo_label()}  (Ctrl+Y)' if h.can_redo() else 'Nothing to redo')

    def set_llm_client(self, client):
        self._llm_client = client

    def _open_chart_prompt(self):
        if self._df is None or len(self._df) == 0:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, 'No data', 'Load some employee data first, then describe a chart.')
            return
        dlg = ChartPromptDialog(self._df, self._llm_client, preview_fn=self._suggestion_pixmap, parent=self)
        if dlg.exec() and dlg.suggestion() is not None:
            self._apply_suggestion(dlg.suggestion(), dlg.mode())

    def _suggestion_pixmap(self, suggestion):
        return self._chart_to_pixmap({'series_list': suggestion.series}, 540, 270, figsize=(7.4, 3.8))

    def _apply_suggestion(self, suggestion, mode: str):
        series = suggestion.series
        starts_empty = self._active_idx >= 0 and not self._active_series()
        if mode == ADD_AS_NEW or self._active_idx < 0:
            self._add_new_chart(record=False)
            self._set_active_title(suggestion.title)
        else:
            used = {s.get('color') for s in self._active_series()}
            for s in series:
                s['color'] = next((c for c in PALETTE if c not in used), PALETTE[len(used) % len(PALETTE)])
                used.add(s['color'])
            if starts_empty and self._charts[self._active_idx]['title'].startswith('Chart '):
                self._set_active_title(suggestion.title)
        self._add_series_dicts(series, 'Generate chart')

    def _set_active_title(self, title: str):
        self._charts[self._active_idx]['title'] = title
        self._title_edit.blockSignals(True)
        self._title_edit.setText(title)
        self._title_edit.blockSignals(False)

    def refresh_theme(self):
        self._main_widget.refresh_theme()
        if self._active_idx >= 0:
            self._render_active()
            self._update_thumbnails()

    def report_charts(self) -> list:
        # Each draw function copies its chart so later edits do not change a report in progress.
        if self._df is None:
            return []
        return [(c['title'], (lambda fig, chart=copy.deepcopy(c), df=self._df: self._draw_on_figure(
                    fig, chart, df, show_period=True)))
                for c in self._charts if c['series_list']]

    # ── Series management ─────────────────────────────────────────────────────

    def _active_series(self):
        if self._active_idx < 0:
            return []
        return self._charts[self._active_idx]['series_list']

    def _add_series(self):
        if self._df is None:
            return
        dlg = SeriesDialog(self._df, parent=self, default_color=self._next_color())
        if dlg.exec() and dlg.result_series_list():
            self._add_series_dicts(dlg.result_series_list())

    def _edit_series(self, idx):
        if self._df is None:
            return
        series_list = self._active_series()
        dlg = SeriesDialog(self._df, existing=series_list[idx], parent=self)
        if dlg.exec():
            s = dlg.result_series()
            if s:
                series_list[idx] = s
                self._rebuild_series_cards()
                self._render_active()
                self._update_thumbnails()
                self._commit('Edit series')

    def _delete_series(self, idx):
        series_list = self._active_series()
        series_list.pop(idx)
        self._rebuild_series_cards()
        self._render_active()
        self._update_thumbnails()
        self._commit('Delete series')

    def _clear_series(self):
        if self._active_idx >= 0:
            self._charts[self._active_idx]['series_list'] = []
        self._rebuild_series_cards()
        self._render_active()
        self._update_thumbnails()
        self._commit('Clear series')

    def _rebuild_series_cards(self):
        # Remove all cards (leave the trailing stretch)
        while self._series_layout.count() > 1:
            item = self._series_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, s in enumerate(self._active_series()):
            card = _SeriesCard(
                s,
                on_edit=lambda _=False, i=i: self._edit_series(i),
                on_delete=lambda _=False, i=i: self._delete_series(i),
            )
            self._series_layout.insertWidget(i, card)
            card.show()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_active(self):
        if self._active_idx < 0:
            self._main_widget.hide()
            self._placeholder.show()
            return

        chart = self._charts[self._active_idx]
        if not chart['series_list'] or self._df is None:
            self._main_widget.hide()
            self._placeholder.show()
            self._table.hide()
            if self._table_visible:
                self._table_toggle_btn.setText('▼ Data Table')
                self._table_visible = False
                self._set_table_section_open(False)
            return

        self._placeholder.hide()
        self._main_widget.show()

        fig = self._main_widget.figure
        fig.clear()

        self._draw_on_figure(fig, chart, self._df, show_period=True)

        # 'constrained' keeps re-fitting titles and labels as the chart is resized
        # (splitter / focus mode) and handles the stacked time + snapshot layout,
        # which 'tight' layout can't.
        fig.set_layout_engine('constrained', h_pad=0.12, w_pad=0.1)

        self._main_widget.redraw()

        # Reconnect hover
        canvas = self._main_widget._chart
        if self._hover_cid is not None:
            try:
                canvas.mpl_disconnect(self._hover_cid)
            except Exception:
                pass
        self._hover_cid = canvas.mpl_connect('motion_notify_event', self._on_hover)

        self._update_data_table()

    def _draw_on_figure(self, fig, chart_dict, df, show_period=False):
        # Draw all series in chart_dict onto fig. show_period adds the time
        # period under each chart title (skipped on small thumbnails).
        self._show_period = show_period
        series_list = chart_dict.get('series_list', [])
        if not series_list:
            return

        time_s = [s for s in series_list if s['view_type'] == 'time']
        snap_s = [s for s in series_list if s['view_type'] == 'snapshot']

        if time_s and not snap_s:
            ax = fig.add_subplot(111)
            self._draw_time_series(ax, time_s, df)

        elif snap_s and not time_s:
            self._draw_snapshots(fig, snap_s, df)

        else:
            # Mixed — time on top, snapshot below
            gs = fig.add_gridspec(2, 1, height_ratios=[1.6, 1])
            ax_t = fig.add_subplot(gs[0])
            self._draw_time_series(ax_t, time_s, df)
            ax_s = fig.add_subplot(gs[1])
            if snap_s:
                self._draw_snapshot_single(ax_s, snap_s[0], df)

    # ── Time series rendering ─────────────────────────────────────────────────

    def _draw_time_series(self, ax, series_list, df):
        for s in series_list:
            data = self._series_data(s, df)
            if data is None or data.empty:
                continue

            color = theme.chart_color(s['color'])
            label = s['label']
            style = s.get('style', 'Line')

            if style == 'Bar':
                ax.bar(data.index, data.values, color=color, alpha=0.75, label=label, width=18)
            elif style == 'Area':
                ax.fill_between(data.index, data.values, alpha=0.25, color=color)
                ax.plot(data.index, data.values, color=color, label=label, linewidth=2)
            elif style == 'Scatter':
                ax.scatter(data.index, data.values, color=color, label=label, s=30, zorder=5)
            else:  # Line (default)
                ax.plot(data.index, data.values, color=color, label=label,
                        linewidth=2, marker='o', markersize=4)

            # Trend line
            if s.get('show_trend') and len(data) >= 2:
                try:
                    x_num = np.arange(len(data))
                    coeffs = np.polyfit(x_num, data.values.astype(float), 1)
                    trend = np.polyval(coeffs, x_num)
                    ax.plot(data.index, trend, '--', color=color, alpha=0.5,
                            linewidth=1.5, label=f'{label} (trend)')
                except Exception:
                    pass

        ax.tick_params(axis='x', rotation=30)
        ax.grid(axis='y', linestyle='--', alpha=0.35)
        ax.set_xlabel('Date', fontsize=9)
        title = series_list[0]['label'] if len(series_list) == 1 else 'Series Comparison'
        set_title_with_period(ax, title, self._time_period_text(series_list))
        if len(series_list) == 1:
            ax.set_ylabel(series_list[0]['metric'], fontsize=9)
        else:
            ax.legend(fontsize=9, loc='best')

    def _time_period_text(self, series_list):
        # e.g. '1 Jan 2025 – 30 Jun 2026 · Monthly' across all time series on the chart.
        if not self._show_period:
            return None
        start = min(pd.Timestamp(s['start_date']) for s in series_list)
        end = max(pd.Timestamp(s['end_date']) for s in series_list)
        text = analytics.format_period(start, end)
        grans = {s.get('granularity', 'Monthly') for s in series_list}
        if len(grans) == 1:
            text += f'  ·  {grans.pop()}'
        if self._using_dashboard_filters():
            text += '  ·  dashboard filters applied'
        return text

    def _snapshot_period_text(self):
        if not self._show_period:
            return None
        if self._using_dashboard_filters():
            return f'Dashboard filters: {self._dash_scope}'
        return f'Current snapshot as at {analytics.format_date(pd.Timestamp.today())}'

    def _using_dashboard_filters(self) -> bool:
        return self._use_filters_box.isChecked() and self._dash_df is not None

    # ── Snapshot rendering ────────────────────────────────────────────────────

    def _draw_snapshots(self, fig, series_list, df):
        groups: dict[str, list] = {}
        for s in series_list:
            groups.setdefault(s.get('group_by', 'Department'), []).append(s)

        n = len(groups)
        axes = [fig.add_subplot(1, n, i + 1) for i in range(n)]

        for ax, (group_by, slist) in zip(axes, groups.items()):
            if len(slist) == 1:
                self._draw_snapshot_single(ax, slist[0], df)
            else:
                self._draw_snapshot_grouped(ax, slist, group_by, df)

    def _draw_snapshot_single(self, ax, s, df):
        data = self._series_data(s, df)
        if data is None or data.empty:
            set_title_with_period(ax, s['label'], self._snapshot_period_text())
            return

        style = s.get('style', 'Vertical Bar')
        color = theme.chart_color(s['color'])

        if style == 'Horizontal Bar':
            bars = ax.barh(data.index, data.values, color=color, alpha=0.85)
            ax.bar_label(bars, fmt=self._fmt(s['metric']), padding=3, fontsize=8)
            ax.set_xlabel(s['metric'], fontsize=9)
        elif style == 'Scatter':
            x_pos = np.arange(len(data))
            ax.scatter(x_pos, data.values, color=color, alpha=0.85, s=50, zorder=5)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(data.index, rotation=20, ha='right', fontsize=9)
            ax.set_ylabel(s['metric'], fontsize=9)
        elif style == 'Pie':
            if not data.empty:
                ax.pie(data.values, labels=data.index, autopct='%1.1f%%',
                       startangle=90, textprops={'fontsize': 8})
        else:  # Vertical Bar (default)
            bars = ax.bar(data.index, data.values, color=color, alpha=0.85)
            ax.bar_label(bars, fmt=self._fmt(s['metric']), padding=3, fontsize=8)
            ax.set_ylabel(s['metric'], fontsize=9)
            ax.tick_params(axis='x', rotation=20)

        set_title_with_period(ax, s['label'], self._snapshot_period_text())
        if style not in ('Pie',):
            ax.grid(axis='x' if style == 'Horizontal Bar' else 'y',
                    linestyle='--', alpha=0.35)

    def _draw_snapshot_grouped(self, ax, series_list, group_by, df):
        all_data = {
            s['label']: self._series_data(s, df)
            for s in series_list
        }
        categories = sorted({cat for d in all_data.values() if d is not None for cat in d.index})
        x = np.arange(len(categories))
        n = len(series_list)
        width = 0.75 / n

        for i, s in enumerate(series_list):
            label = s['label']
            data = all_data.get(label)
            if data is None:
                continue
            offset = (i - n / 2 + 0.5) * width
            vals = [float(data.get(cat, 0)) for cat in categories]
            ax.bar(x + offset, vals, width, color=theme.chart_color(s['color']), label=label, alpha=0.85)

        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=20, ha='right', fontsize=9)
        ax.legend(fontsize=9)
        set_title_with_period(ax, f'Comparison by {group_by}', self._snapshot_period_text())
        ax.grid(axis='y', linestyle='--', alpha=0.35)

    # ── Series data helper ────────────────────────────────────────────────────

    def _series_data(self, s, df):
        # Return a pd.Series of data for a series config dict.
        if df is None:
            return None
        try:
            if s['view_type'] == 'time':
                start = pd.Timestamp(s['start_date'])
                end = pd.Timestamp(s['end_date'])
                granularity = s.get('granularity', 'Monthly')
                return analytics.time_series_data(
                    df,
                    s['metric'],
                    s.get('filter_by', 'None'),
                    s.get('filter_val', 'All'),
                    start,
                    end,
                    granularity,
                )
            else:
                return analytics.snapshot_data(
                    df,
                    s['metric'],
                    s.get('group_by', 'Department'),
                )
        except Exception:
            return None

    # ── Thumbnail management ──────────────────────────────────────────────────

    def _chart_to_pixmap(self, chart_dict, w=164, h=104, figsize=(4, 3)):
        # Render a chart dict to a QPixmap for use as a thumbnail.
        series_list = chart_dict.get('series_list', [])
        if not series_list or self._df is None:
            # Grey placeholder
            pix = QPixmap(w, h)
            pix.fill(Qt.GlobalColor.lightGray)
            return pix

        try:
            fig = Figure(figsize=figsize, dpi=72, layout='constrained')
            self._draw_on_figure(fig, chart_dict, self._df)

            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)

            pix = QPixmap()
            pix.loadFromData(buf.read())
            return pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        except Exception:
            pix = QPixmap(w, h)
            pix.fill(Qt.GlobalColor.lightGray)
            return pix

    def _update_thumbnails(self):
        # Clear existing thumbnails (keep the stretch at the end)
        while self._thumb_layout.count() > 1:
            item = self._thumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, chart in enumerate(self._charts):
            pixmap = self._chart_to_pixmap(chart)
            is_active = (i == self._active_idx)
            card = _ThumbnailCard(
                chart,
                pixmap,
                is_active,
                on_click=lambda _=False, idx=i: self._set_active_chart(idx),
                on_delete=lambda _=False, idx=i: self._delete_chart(idx),
            )
            self._thumb_layout.insertWidget(i, card)
            card.show()

    # ── Hover tooltips ────────────────────────────────────────────────────────

    def _on_hover(self, event):
        if not event.inaxes:
            QToolTip.hideText()
            return
        canvas = self._main_widget._chart
        for ax in self._main_widget.figure.axes:
            for line in ax.lines:
                if not line.get_visible():
                    continue
                if line.get_linestyle() == 'None':
                    continue
                try:
                    cont, info = line.contains(event)
                    if cont and len(info.get('ind', [])):
                        i = info['ind'][0]
                        x = line.get_xdata()[i]
                        y = line.get_ydata()[i]
                        x_str = x.strftime('%b %Y') if hasattr(x, 'strftime') else str(x)
                        lbl = line.get_label() or ''
                        text = f'{lbl}\n{x_str}: {y:.2f}'.strip()
                        pos = canvas.mapToGlobal(
                            QPoint(int(event.x), int(canvas.height() - event.y))
                        )
                        QToolTip.showText(pos, text)
                        return
                except Exception:
                    pass
        QToolTip.hideText()

    # ── Export / Clipboard ────────────────────────────────────────────────────

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Chart as PNG', '', 'PNG Image (*.png)'
        )
        if path:
            try:
                self._main_widget.figure.savefig(path, dpi=150, bbox_inches='tight')
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, 'Export Failed', str(e))

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Chart as PDF', '', 'PDF Document (*.pdf)'
        )
        if path:
            try:
                self._main_widget.figure.savefig(path, format='pdf', bbox_inches='tight')
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, 'Export Failed', str(e))

    def _copy_to_clipboard(self):
        try:
            buf = io.BytesIO()
            self._main_widget.figure.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            pix = QPixmap()
            pix.loadFromData(buf.read())
            QApplication.clipboard().setPixmap(pix)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Copy Failed', str(e))

    # ── Save / Load config ────────────────────────────────────────────────────

    def _save_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save Chart Configuration', '', 'JSON File (*.json)'
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(self._charts, f, indent=2)
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, 'Save Failed', str(e))

    def _load_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load Chart Configuration', '', 'JSON File (*.json)'
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if isinstance(loaded, list) and loaded:
                    # Setups saved by older versions may use old metric names
                    for chart in loaded:
                        for series in chart.get('series_list', []):
                            series['metric'] = analytics.canonical_metric(series.get('metric', ''))
                    self._charts = loaded
                    self._active_idx = 0
                    self._title_edit.blockSignals(True)
                    self._title_edit.setText(self._charts[0]['title'])
                    self._title_edit.blockSignals(False)
                    self._rebuild_series_cards()
                    self._update_thumbnails()
                    self._render_active()
                    self._commit('Load chart setup')
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, 'Load Failed', str(e))

    # ── Data table ────────────────────────────────────────────────────────────

    def _toggle_table(self):
        self._table_visible = not self._table_visible
        if self._table_visible:
            self._table_toggle_btn.setText('▲ Data Table')
            self._table.show()
            self._set_table_section_open(True)
            self._update_data_table()
        else:
            self._table_toggle_btn.setText('▼ Data Table')
            self._table.hide()
            self._set_table_section_open(False)

    def _update_data_table(self):
        if not self._table_visible:
            return
        if self._active_idx < 0 or self._df is None:
            self._table.clear()
            return

        chart = self._charts[self._active_idx]
        series_list = chart.get('series_list', [])
        if not series_list:
            self._table.clear()
            return

        time_series = [s for s in series_list if s['view_type'] == 'time']
        snap_series = [s for s in series_list if s['view_type'] == 'snapshot']

        try:
            if time_series:
                frames = {}
                for s in time_series:
                    data = self._series_data(s, self._df)
                    if data is not None and not data.empty:
                        formatted_idx = [
                            idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)
                            for idx in data.index
                        ]
                        frames[s['label']] = pd.Series(data.values, index=formatted_idx)
                if frames:
                    tbl_df = pd.DataFrame(frames)
                    self._fill_table(tbl_df)
                    return

            if snap_series:
                frames = {}
                for s in snap_series:
                    data = self._series_data(s, self._df)
                    if data is not None and not data.empty:
                        frames[s['label']] = data
                if frames:
                    tbl_df = pd.DataFrame(frames)
                    self._fill_table(tbl_df)
        except Exception:
            self._table.clear()

    def _fill_table(self, df: pd.DataFrame):
        self._table.clear()
        self._table.setRowCount(len(df))
        self._table.setColumnCount(len(df.columns))
        self._table.setHorizontalHeaderLabels(list(df.columns))
        self._table.setVerticalHeaderLabels([str(i) for i in df.index])

        for row_i, (idx, row) in enumerate(df.iterrows()):
            for col_i, val in enumerate(row):
                try:
                    text = f'{val:.2f}' if isinstance(val, float) else str(val)
                except Exception:
                    text = str(val)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row_i, col_i, item)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt(metric):
        if 'Salary' in metric:
            return '${:,.0f}'
        if '%' in metric or 'Turnover' in metric:
            return '{:.1f}%'
        return '{:.1f}'
