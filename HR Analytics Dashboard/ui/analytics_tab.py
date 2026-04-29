import io
import json
import uuid

import numpy as np
import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QLineEdit, QToolButton,
    QFileDialog, QApplication, QTableWidget, QTableWidgetItem,
    QHeaderView, QToolTip,
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPixmap, QFont

import matplotlib
matplotlib.use('QtAgg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from core import analytics
from ui.chart_widget import ChartWithToolbar
from ui.series_dialog import SeriesDialog

# ── Colour / style constants ──────────────────────────────────────────────────

_NAVY = '#1F3864'
_NAVY_HOVER = '#2E75B6'
_NAVY_PRESS = '#163060'
_GREY_BG = '#F5F7FA'
_BORDER = '#E0E0E0'
_RED = '#C0392B'
_RED_HOVER = '#FADBD8'


# ── _SeriesCard ───────────────────────────────────────────────────────────────

class _SeriesCard(QFrame):
    """One row in the series list — coloured dot, label, edit and delete buttons."""

    def __init__(self, series, on_edit, on_delete, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f'''
            QFrame {{
                background: white;
                border-radius: 6px;
                border: 1px solid {_BORDER};
            }}
        ''')
        self.setFixedHeight(52)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 8, 0)
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

class _ThumbnailCard(QFrame):
    """A clickable chart thumbnail in the right sidebar."""

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
        self.setFixedWidth(194)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        # Image container with delete button overlay
        img_container = QWidget()
        img_container.setFixedSize(186, 120)
        img_container.setStyleSheet('background: transparent; border: none;')

        img_lbl = QLabel(img_container)
        img_lbl.setGeometry(0, 0, 186, 120)
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_lbl.setStyleSheet('border: none; background: #F5F7FA; border-radius: 4px;')
        if pixmap and not pixmap.isNull():
            img_lbl.setPixmap(
                pixmap.scaled(186, 120, Qt.AspectRatioMode.KeepAspectRatio,
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

class AnalyticsTab(QWidget):
    """Multi-chart analytics builder with series management and thumbnail navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = None
        self._charts = []          # list of {'id', 'title', 'series_list'}
        self._active_idx = -1
        self._left_visible = True
        self._hover_cid = None

        self._build_ui()
        self._add_new_chart()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._left_panel = self._build_left_panel()
        root.addWidget(self._left_panel)

        root.addWidget(self._build_center_panel(), stretch=1)
        root.addWidget(self._build_right_strip())

    # ── Left panel (collapsible) ──────────────────────────────────────────────

    def _build_left_panel(self):
        panel = QWidget()
        panel.setFixedWidth(260)
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
        footer.setFixedHeight(96)
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

        fv.addWidget(add_btn)
        fv.addWidget(clear_btn)
        lv.addWidget(footer)

        return panel

    def _toggle_left_panel(self):
        if self._left_visible:
            self._left_panel.setFixedWidth(0)
            self._collapse_btn.setText('▶')
            self._left_visible = False
        else:
            self._left_panel.setFixedWidth(260)
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
        tb.addWidget(self._title_edit, stretch=1)

        tb.addStretch()

        # Icon buttons
        for icon, tip, slot in [
            ('📋 Copy',  'Copy to clipboard',   self._copy_to_clipboard),
            ('🖼 PNG',   'Export as PNG',        self._export_png),
            ('📄 PDF',   'Export as PDF',        self._export_pdf),
            ('💾 Save',  'Save chart config',    self._save_config),
            ('📂 Load',  'Load chart config',    self._load_config),
        ]:
            btn = QPushButton(icon)
            btn.setToolTip(tip)
            btn.setFixedHeight(32)
            btn.setStyleSheet('''
                QPushButton {
                    font-size: 12px; background: transparent;
                    border: 1px solid #DDD; border-radius: 4px;
                    padding: 0 8px; color: #444;
                }
                QPushButton:hover { background: #F0F4FF; border-color: #2E75B6; }
            ''')
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        cv.addWidget(top_bar)

        # ── Main chart widget ─────────────────────────────────────────────
        self._main_widget = ChartWithToolbar(width=10, height=6)
        self._placeholder = QLabel(
            'Click  "+ Add Series"  to start building your chart.\n\n'
            'Examples:\n'
            '  • Monthly Hires — Last 2 Years\n'
            '  • Compare Turnover Rate across departments\n'
            '  • Overlay multiple series on the same chart'
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet('font-size: 13px; color: #888888; line-height: 1.8;')

        cv.addWidget(self._main_widget, stretch=1)
        cv.addWidget(self._placeholder, stretch=1)
        self._main_widget.hide()

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
        cv.addWidget(self._table_toggle_btn)

        self._table = QTableWidget()
        self._table.setFixedHeight(180)
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
        cv.addWidget(self._table)

        return panel

    # ── Right thumbnail strip ─────────────────────────────────────────────────

    def _build_right_strip(self):
        strip = QWidget()
        strip.setFixedWidth(210)
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
        self._df = df
        if self._active_idx >= 0:
            self._render_active()
            self._update_thumbnails()

    # ── Multi-chart management ────────────────────────────────────────────────

    def _add_new_chart(self):
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
        if self._active_idx >= 0:
            self._charts[self._active_idx]['title'] = text
            self._update_thumbnails()

    # ── Series management ─────────────────────────────────────────────────────

    def _active_series(self):
        if self._active_idx < 0:
            return []
        return self._charts[self._active_idx]['series_list']

    def _add_series(self):
        if self._df is None:
            return
        dlg = SeriesDialog(self._df, parent=self)
        if dlg.exec():
            s = dlg.result_series()
            if s:
                self._active_series().append(s)
                self._rebuild_series_cards()
                self._render_active()
                self._update_thumbnails()

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

    def _delete_series(self, idx):
        series_list = self._active_series()
        series_list.pop(idx)
        self._rebuild_series_cards()
        self._render_active()
        self._update_thumbnails()

    def _clear_series(self):
        if self._active_idx >= 0:
            self._charts[self._active_idx]['series_list'] = []
        self._rebuild_series_cards()
        self._render_active()
        self._update_thumbnails()

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
            return

        self._placeholder.hide()
        self._main_widget.show()

        fig = self._main_widget.figure
        fig.clear()

        self._draw_on_figure(fig, chart, self._df)

        try:
            fig.tight_layout(pad=2.0)
        except Exception:
            pass

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

    def _draw_on_figure(self, fig, chart_dict, df):
        """Draw all series in chart_dict onto fig."""
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
            gs = fig.add_gridspec(2, 1, height_ratios=[1.6, 1], hspace=0.55)
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

            color = s['color']
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
        if len(series_list) == 1:
            ax.set_title(series_list[0]['label'], fontsize=11, fontweight='bold')
            ax.set_ylabel(series_list[0]['metric'], fontsize=9)
        else:
            ax.set_title('Series Comparison', fontsize=11, fontweight='bold')
            ax.legend(fontsize=9, loc='best')

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
            ax.set_title(s['label'], fontsize=11, fontweight='bold')
            return

        style = s.get('style', 'Vertical Bar')
        color = s['color']

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

        ax.set_title(s['label'], fontsize=11, fontweight='bold')
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
            ax.bar(x + offset, vals, width, color=s['color'], label=label, alpha=0.85)

        ax.set_xticks(x)
        ax.set_xticklabels(categories, rotation=20, ha='right', fontsize=9)
        ax.legend(fontsize=9)
        ax.set_title(f'Comparison by {group_by}', fontsize=11, fontweight='bold')
        ax.grid(axis='y', linestyle='--', alpha=0.35)

    # ── Series data helper ────────────────────────────────────────────────────

    def _series_data(self, s, df):
        """Return a pd.Series of data for a series config dict."""
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

    def _chart_to_pixmap(self, chart_dict, w=190, h=120):
        """Render a chart dict to a QPixmap (thumbnail)."""
        series_list = chart_dict.get('series_list', [])
        if not series_list or self._df is None:
            # Grey placeholder
            pix = QPixmap(w, h)
            pix.fill(Qt.GlobalColor.lightGray)
            return pix

        try:
            fig = Figure(figsize=(4, 3), dpi=72)
            self._draw_on_figure(fig, chart_dict, self._df)
            try:
                fig.tight_layout(pad=1.0)
            except Exception:
                pass

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
                    self._charts = loaded
                    self._active_idx = 0
                    self._title_edit.blockSignals(True)
                    self._title_edit.setText(self._charts[0]['title'])
                    self._title_edit.blockSignals(False)
                    self._rebuild_series_cards()
                    self._update_thumbnails()
                    self._render_active()
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, 'Load Failed', str(e))

    # ── Data table ────────────────────────────────────────────────────────────

    def _toggle_table(self):
        self._table_visible = not self._table_visible
        if self._table_visible:
            self._table_toggle_btn.setText('▲ Data Table')
            self._table.show()
            self._update_data_table()
        else:
            self._table_toggle_btn.setText('▼ Data Table')
            self._table.hide()

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
