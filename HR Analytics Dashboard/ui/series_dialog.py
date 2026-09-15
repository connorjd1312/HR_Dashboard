import uuid

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QButtonGroup, QRadioButton,
    QWidget, QFrame, QCheckBox, QColorDialog, QDateEdit,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor

from core import analytics
from ui import theme

PALETTE = [
    '#1F3864', '#2E75B6', '#1E8449', '#C0392B',
    '#D4AC0D', '#5B2C6F', '#117A65', '#E67E22',
]

_SECTION_STYLE = theme.LABEL_FIELD + ' margin-top: 4px;'
_COMBO_STYLE = theme.COMBO_STYLE
_DATE_EDIT_STYLE = theme.COMBO_STYLE


def _color_btn_style(color: str) -> str:
    # Return stylesheet for the color picker button showing the given hex color.
    return f'''
        QPushButton {{
            background-color: {color};
            border: 2px solid #AAAAAA;
            border-radius: 4px;
            color: white;
            font-size: 11px;
            font-weight: bold;
            padding: 4px 12px;
        }}
        QPushButton:hover {{
            border: 2px solid #555555;
        }}
    '''


# Modal dialog for configuring one chart series.
class SeriesDialog(QDialog):

    def __init__(self, df, existing=None, parent=None):
        super().__init__(parent)
        self._df = df
        self._existing = existing or {}
        self._color = self._existing.get('color', PALETTE[0])
        self._result = None

        self.setWindowTitle('Configure Series')
        self.setMinimumWidth(440)
        self.setMinimumHeight(500)
        self.setModal(True)
        self._build_ui()

        if existing:
            self._populate(existing)

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet('background: white;')

        content = QWidget()
        content.setObjectName('seriesContent')
        content.setStyleSheet('#seriesContent { background: white; }')
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 16, 20, 16)

        # ── Series Label ──────────────────────────────────────────────────
        layout.addWidget(QLabel('Series Label', styleSheet=_SECTION_STYLE))
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText('Leave blank to auto-generate')
        self.label_edit.setStyleSheet(
            'border: 1px solid #CCC; border-radius: 4px; padding: 5px 8px; font-size: 12px;'
        )
        layout.addWidget(self.label_edit)

        layout.addWidget(self._divider())

        # ── View type ─────────────────────────────────────────────────────
        layout.addWidget(QLabel('View Type', styleSheet=_SECTION_STYLE))
        self._view_group = QButtonGroup(self)
        self.time_radio = QRadioButton('Over Time  (track a metric over a date range)')
        self.snap_radio = QRadioButton('Snapshot  (compare groups at the current moment)')
        self.time_radio.setStyleSheet('font-size: 12px; color: #333;')
        self.snap_radio.setStyleSheet('font-size: 12px; color: #333;')
        self.time_radio.setChecked(True)
        self._view_group.addButton(self.time_radio, 0)
        self._view_group.addButton(self.snap_radio, 1)
        layout.addWidget(self.time_radio)
        layout.addWidget(self.snap_radio)
        self.time_radio.toggled.connect(self._on_view_type_toggled)

        layout.addWidget(self._divider())

        # ── Over-time fields ──────────────────────────────────────────────
        self._time_widget = QWidget()
        tw = QVBoxLayout(self._time_widget)
        tw.setContentsMargins(0, 0, 0, 0)
        tw.setSpacing(6)

        tw.addWidget(QLabel('Metric', styleSheet=_SECTION_STYLE))
        self.time_metric_combo = QComboBox()
        self.time_metric_combo.addItems(analytics.TIME_SERIES_METRICS)
        self.time_metric_combo.setStyleSheet(_COMBO_STYLE)
        tw.addWidget(self.time_metric_combo)

        tw.addWidget(QLabel('Filter By', styleSheet=_SECTION_STYLE))
        self.filter_by_combo = QComboBox()
        self.filter_by_combo.addItem('None (show all employees)')
        self.filter_by_combo.addItems(analytics.GROUP_BY_OPTIONS)
        self.filter_by_combo.setStyleSheet(_COMBO_STYLE)
        self.filter_by_combo.currentIndexChanged.connect(self._on_filter_by_changed)
        tw.addWidget(self.filter_by_combo)

        tw.addWidget(QLabel('Filter Value', styleSheet=_SECTION_STYLE))
        self.filter_val_combo = QComboBox()
        self.filter_val_combo.setEnabled(False)
        self.filter_val_combo.setStyleSheet(_COMBO_STYLE)
        tw.addWidget(self.filter_val_combo)

        # ── Date Range ────────────────────────────────────────────────────
        tw.addWidget(QLabel('Date Range', styleSheet=_SECTION_STYLE))
        date_row = QHBoxLayout()
        date_row.setSpacing(8)

        tw.addWidget(QLabel('From', styleSheet='font-size: 11px; color: #666;'))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setStyleSheet(_DATE_EDIT_STYLE)
        default_start = QDate.currentDate().addYears(-2)
        self.start_date_edit.setDate(default_start)
        tw.addWidget(self.start_date_edit)

        tw.addWidget(QLabel('To', styleSheet='font-size: 11px; color: #666;'))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setStyleSheet(_DATE_EDIT_STYLE)
        self.end_date_edit.setDate(QDate.currentDate())
        tw.addWidget(self.end_date_edit)

        # ── Granularity ───────────────────────────────────────────────────
        tw.addWidget(QLabel('Granularity', styleSheet=_SECTION_STYLE))
        self.granularity_combo = QComboBox()
        self.granularity_combo.addItems(analytics.GRANULARITIES)
        self.granularity_combo.setCurrentText('Monthly')
        self.granularity_combo.setStyleSheet(_COMBO_STYLE)
        tw.addWidget(self.granularity_combo)

        tw.addWidget(QLabel('Chart Style', styleSheet=_SECTION_STYLE))
        self.time_style_combo = QComboBox()
        self.time_style_combo.addItems(['Line', 'Bar', 'Area', 'Scatter'])
        self.time_style_combo.setStyleSheet(_COMBO_STYLE)
        tw.addWidget(self.time_style_combo)

        # ── Trend line ────────────────────────────────────────────────────
        self.trend_check = QCheckBox('Show trend line')
        self.trend_check.setStyleSheet('font-size: 12px; color: #333;')
        tw.addWidget(self.trend_check)

        layout.addWidget(self._time_widget)

        # ── Snapshot fields ───────────────────────────────────────────────
        self._snap_widget = QWidget()
        sw = QVBoxLayout(self._snap_widget)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(6)

        sw.addWidget(QLabel('Metric', styleSheet=_SECTION_STYLE))
        self.snap_metric_combo = QComboBox()
        self.snap_metric_combo.addItems(analytics.SNAPSHOT_METRICS)
        self.snap_metric_combo.setStyleSheet(_COMBO_STYLE)
        sw.addWidget(self.snap_metric_combo)

        sw.addWidget(QLabel('Group By', styleSheet=_SECTION_STYLE))
        self.group_by_combo = QComboBox()
        self.group_by_combo.addItems(analytics.GROUP_BY_OPTIONS)
        self.group_by_combo.setStyleSheet(_COMBO_STYLE)
        sw.addWidget(self.group_by_combo)

        sw.addWidget(QLabel('Chart Style', styleSheet=_SECTION_STYLE))
        self.snap_style_combo = QComboBox()
        self.snap_style_combo.addItems(['Vertical Bar', 'Horizontal Bar', 'Scatter', 'Pie'])
        self.snap_style_combo.setStyleSheet(_COMBO_STYLE)
        sw.addWidget(self.snap_style_combo)

        self._snap_widget.hide()
        layout.addWidget(self._snap_widget)

        layout.addWidget(self._divider())

        # ── Color picker ──────────────────────────────────────────────────
        layout.addWidget(QLabel('Color', styleSheet=_SECTION_STYLE))
        self._color_btn = QPushButton('  Choose Color...')
        self._color_btn.setFixedHeight(34)
        self._color_btn.setStyleSheet(_color_btn_style(self._color))
        self._color_btn.clicked.connect(self._open_color_dialog)
        layout.addWidget(self._color_btn)

        layout.addWidget(self._divider())

        # ── Action buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setFixedHeight(36)
        cancel_btn.setStyleSheet(
            'border: 1px solid #CCC; border-radius: 5px; padding: 0 14px; font-size: 12px;'
        )
        cancel_btn.clicked.connect(self.reject)

        confirm_text = 'Save Changes' if self._existing else 'Add to Chart'
        confirm_btn = QPushButton(confirm_text)
        confirm_btn.setFixedHeight(36)
        confirm_btn.setStyleSheet('''
            QPushButton {
                background-color: #1F3864; color: white;
                border-radius: 5px; padding: 0 18px;
                font-size: 13px; border: none;
            }
            QPushButton:hover { background-color: #2E75B6; }
        ''')
        confirm_btn.clicked.connect(self._confirm)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet('color: #E8E8E8;')
        return line

    def _on_view_type_toggled(self, is_time):
        self._time_widget.setVisible(is_time)
        self._snap_widget.setVisible(not is_time)
        self.adjustSize()

    def _on_filter_by_changed(self, index):
        self.filter_val_combo.clear()
        text = self.filter_by_combo.currentText()
        if text == 'None (show all employees)':
            self.filter_val_combo.setEnabled(False)
            return
        self.filter_val_combo.setEnabled(True)
        col_map = {
            'Department': 'Department',
            'Job Role':   'Job_Role',
            'Status':     'Status',
            'Sex':        'Sex',
            'Ethnicity':  'Ethnicity',
            'Age Group':  'Age_Group',
        }
        col = col_map.get(text)
        if col and col in self._df.columns:
            self.filter_val_combo.addItem('All')
            self.filter_val_combo.addItems(sorted(self._df[col].dropna().unique()))

    def _open_color_dialog(self):
        initial = QColor(self._color)
        chosen = QColorDialog.getColor(initial, self, 'Choose Series Color')
        if chosen.isValid():
            self._color = chosen.name()
            self._color_btn.setStyleSheet(_color_btn_style(self._color))

    def _confirm(self):
        if self.time_radio.isChecked():
            view_type = 'time'
            metric = self.time_metric_combo.currentText()
            raw_filter = self.filter_by_combo.currentText()
            filter_by = 'None' if raw_filter.startswith('None') else raw_filter
            filter_val = (
                self.filter_val_combo.currentText()
                if self.filter_val_combo.isEnabled() else 'All'
            )
            # Dates as ISO strings
            qstart = self.start_date_edit.date()
            qend = self.end_date_edit.date()
            start_date = f'{qstart.year():04d}-{qstart.month():02d}-{qstart.day():02d}'
            end_date = f'{qend.year():04d}-{qend.month():02d}-{qend.day():02d}'
            granularity = self.granularity_combo.currentText()
            style = self.time_style_combo.currentText()
            show_trend = self.trend_check.isChecked()
            group_by = None
            auto_label = (
                f'{metric} — {filter_val}' if filter_val != 'All'
                else metric
            ) + f' ({granularity})'
        else:
            view_type = 'snapshot'
            metric = self.snap_metric_combo.currentText()
            filter_by = 'None'
            filter_val = 'All'
            start_date = None
            end_date = None
            granularity = None
            style = self.snap_style_combo.currentText()
            show_trend = False
            group_by = self.group_by_combo.currentText()
            auto_label = f'{metric} by {group_by}'

        label = self.label_edit.text().strip() or auto_label

        self._result = {
            'id':          self._existing.get('id', str(uuid.uuid4())[:8]),
            'label':       label,
            'view_type':   view_type,
            'metric':      metric,
            'filter_by':   filter_by,
            'filter_val':  filter_val,
            'start_date':  start_date,
            'end_date':    end_date,
            'granularity': granularity,
            'style':       style,
            'show_trend':  show_trend,
            'color':       self._color,
            'group_by':    group_by,
        }
        self.accept()

    def result_series(self):
        return self._result

    def _populate(self, s):
        self.label_edit.setText(s.get('label', ''))

        # Color
        self._color = s.get('color', PALETTE[0])
        self._color_btn.setStyleSheet(_color_btn_style(self._color))

        if s.get('view_type') == 'snapshot':
            self.snap_radio.setChecked(True)
            self.snap_metric_combo.setCurrentText(s.get('metric', ''))
            self.group_by_combo.setCurrentText(s.get('group_by', 'Department'))
            self.snap_style_combo.setCurrentText(s.get('style', 'Vertical Bar'))
        else:
            self.time_radio.setChecked(True)
            self.time_metric_combo.setCurrentText(s.get('metric', ''))
            fb = s.get('filter_by', 'None')
            if fb == 'None':
                self.filter_by_combo.setCurrentIndex(0)
            else:
                self.filter_by_combo.setCurrentText(fb)
            self.filter_val_combo.setCurrentText(s.get('filter_val', 'All'))
            self.time_style_combo.setCurrentText(s.get('style', 'Line'))
            self.trend_check.setChecked(s.get('show_trend', False))
            self.granularity_combo.setCurrentText(s.get('granularity', 'Monthly'))

            # Restore dates
            start_str = s.get('start_date')
            end_str = s.get('end_date')
            if start_str:
                try:
                    y, mo, d = [int(x) for x in start_str.split('-')]
                    self.start_date_edit.setDate(QDate(y, mo, d))
                except Exception:
                    pass
            if end_str:
                try:
                    y, mo, d = [int(x) for x in end_str.split('-')]
                    self.end_date_edit.setDate(QDate(y, mo, d))
                except Exception:
                    pass
