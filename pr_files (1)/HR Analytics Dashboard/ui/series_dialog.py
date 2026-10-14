# series_dialog.py
# Dialog for adding or editing one chart series in the Analytics tab.
#
# Designed to be quick for non-technical users: pick what kind of chart you want
# in plain language, answer two or three questions (what / who / when), and
# everything else (label, chart style, trend line, granularity, colour) is
# filled in sensibly and tucked away under "More options". Quick-start
# templates add common charts in one click.

from __future__ import annotations

import uuid

import pandas as pd
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QButtonGroup, QWidget, QFrame, QCheckBox,
    QDateEdit, QScrollArea,
)
from PyQt6.QtCore import Qt, QDate

from core import analytics
# Re-exported so existing imports keep working.
from core.series_utils import (
    PALETTE, auto_granularity, auto_label, make_series,
    date_range as _date_range,
)
from ui import theme

_SECTION_STYLE = theme.LABEL_FIELD + ' margin-top: 6px;'
_COMBO_STYLE = theme.COMBO_STYLE

_ALL_EMPLOYEES = 'All employees'
_AUTO_GRANULARITY = 'Automatic'

# Date range presets: label → months back from today (None = all time)
_DATE_PRESETS = [
    ('Last 6 months', 6),
    ('Last 12 months', 12),
    ('Last 2 years', 24),
    ('All time', None),
    ('Custom…', 'custom'),
]

_TIME_STYLES = ['Line', 'Bar', 'Area', 'Scatter']
_SNAP_STYLES = ['Vertical Bar', 'Horizontal Bar', 'Scatter', 'Pie']

# Quick-start templates: name → list of series settings (dates filled in on use)
TEMPLATES = {
    'Hires vs departures (last 12 months)': [
        dict(view_type='time', metric='Hires', months=12, style='Line', color='#1F3864'),
        dict(view_type='time', metric='Departures', months=12, style='Bar', color='#C0392B'),
    ],
    'Turnover by department': [
        dict(view_type='snapshot', metric='Overall Turnover Rate (%)', group_by='Department',
             style='Horizontal Bar', color='#2E75B6'),
    ],
    'Headcount by age group': [
        dict(view_type='snapshot', metric='Total Employees', group_by='Age Group',
             style='Vertical Bar', color='#1E8449'),
    ],
    'Average salary by job role': [
        dict(view_type='snapshot', metric='Average Salary ($)', group_by='Job Role',
             style='Horizontal Bar', color='#5B2C6F'),
    ],
    'Attrition trend (last 2 years)': [
        dict(view_type='time', metric='Attrition (Voluntary Leavers) Rate per Period (%)', months=24,
             style='Line', color='#E67E22', show_trend=True),
    ],
}


def series_from_template(name: str, df) -> list[dict]:
    # Build ready-to-draw series dicts for a quick-start template.
    out = []
    for t in TEMPLATES[name]:
        start = end = gran = None
        if t['view_type'] == 'time':
            start, end = _date_range(t['months'], df)
            gran = auto_granularity(start, end)
        out.append(make_series(
            t['view_type'], t['metric'], style=t['style'], color=t['color'],
            group_by=t.get('group_by'), start_date=start, end_date=end,
            granularity=gran, show_trend=t.get('show_trend', False)))
    return out


def _choice_card_style() -> str:
    return f'''
        QPushButton {{
            text-align: left; padding: 12px 14px;
            background: white; color: {theme.TEXT};
            border: 2px solid {theme.BORDER}; border-radius: 8px;
            font-size: 12px;
        }}
        QPushButton:hover {{ border-color: {theme.BLUE}; background: #F7FAFF; }}
        QPushButton:checked {{ border-color: {theme.BLUE}; background: #EAF1FA; }}
    '''


def _chip_style() -> str:
    return f'''
        QPushButton {{
            background: white; color: {theme.TEXT};
            border: 1px solid {theme.INPUT_BORDER}; border-radius: 13px;
            padding: 4px 11px; font-size: 11px;
        }}
        QPushButton:hover {{ border-color: {theme.BLUE}; }}
        QPushButton:checked {{ background: {theme.BLUE}; color: white; border-color: {theme.BLUE}; }}
    '''


def _template_btn_style() -> str:
    return f'''
        QPushButton {{
            background: #F0F4FF; color: {theme.NAVY};
            border: 1px solid #C9D7F0; border-radius: 6px;
            padding: 6px 10px; font-size: 11px; text-align: left;
        }}
        QPushButton:hover {{ background: #E1EAFB; border-color: {theme.BLUE}; }}
    '''


def _swatch_style(color: str) -> str:
    return f'''
        QPushButton {{ background: {color}; border: 2px solid white; border-radius: 13px; }}
        QPushButton:hover {{ border: 2px solid #999; }}
        QPushButton:checked {{ border: 3px solid {theme.HIGHLIGHT}; }}
    '''


# Modal dialog for configuring one chart series.
class SeriesDialog(QDialog):

    def __init__(self, df, existing=None, parent=None, default_color=None):
        super().__init__(parent)
        self._df = df
        self._existing = existing or {}
        self._color = self._existing.get('color', default_color or PALETTE[0])
        self._results: list[dict] = []
        self._custom_dates = False

        self.setWindowTitle('Edit Series' if existing else 'Add a Series')
        self.setMinimumWidth(480)
        self.resize(500, 620)
        self.setModal(True)
        self._build_ui()

        if existing:
            self._populate(existing)
        self._refresh()

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('seriesContent')
        content.setStyleSheet('#seriesContent { background: white; }')
        layout = QVBoxLayout(content)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 16, 20, 16)

        # ── Quick start (new series only) ─────────────────────────────────
        if not self._existing:
            layout.addWidget(QLabel('Quick start — add a common chart in one click', styleSheet=_SECTION_STYLE))
            grid = QGridLayout()
            grid.setSpacing(6)
            for i, name in enumerate(TEMPLATES):
                btn = QPushButton(name)
                btn.setStyleSheet(_template_btn_style())
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _=False, n=name: self._use_template(n))
                grid.addWidget(btn, i // 2, i % 2)
            layout.addLayout(grid)
            layout.addWidget(self._divider())
            layout.addWidget(QLabel('Or build your own', styleSheet=_SECTION_STYLE))

        # ── 1. What kind of chart? ────────────────────────────────────────
        cards = QHBoxLayout()
        cards.setSpacing(8)
        self._kind_group = QButtonGroup(self)
        self.time_card = QPushButton('📈  Change over time\nSee how a number rises or falls')
        self.snap_card = QPushButton('📊  Compare groups\nCompare departments, roles, ages…')
        for i, card in enumerate((self.time_card, self.snap_card)):
            card.setCheckable(True)
            card.setMinimumHeight(58)
            card.setStyleSheet(_choice_card_style())
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            self._kind_group.addButton(card, i)
            cards.addWidget(card)
        self.time_card.setChecked(True)
        self._kind_group.idToggled.connect(lambda *_: self._on_kind_changed())
        layout.addLayout(cards)

        # ── 2a. Over time: What / Who / When ──────────────────────────────
        self._time_widget = QWidget()
        tw = QVBoxLayout(self._time_widget)
        tw.setContentsMargins(0, 0, 0, 0)
        tw.setSpacing(6)

        tw.addWidget(QLabel('What do you want to track?', styleSheet=_SECTION_STYLE))
        self.time_metric_combo = self._metric_combo(analytics.TIME_SERIES_METRICS)
        tw.addWidget(self.time_metric_combo)
        self.time_metric_desc = self._description_label()
        tw.addWidget(self.time_metric_desc)

        tw.addWidget(QLabel('Who?', styleSheet=_SECTION_STYLE))
        self.who_combo = QComboBox()
        self.who_combo.setStyleSheet(_COMBO_STYLE)
        self._fill_who_combo()
        self.who_combo.currentIndexChanged.connect(lambda _: self._refresh())
        tw.addWidget(self.who_combo)

        tw.addWidget(QLabel('When?', styleSheet=_SECTION_STYLE))
        chips = QHBoxLayout()
        chips.setSpacing(5)
        self._preset_group = QButtonGroup(self)
        for i, (name, _months) in enumerate(_DATE_PRESETS):
            chip = QPushButton(name)
            chip.setCheckable(True)
            chip.setStyleSheet(_chip_style())
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            self._preset_group.addButton(chip, i)
            chips.addWidget(chip)
        chips.addStretch()
        self._preset_group.button(1).setChecked(True)   # Last 12 months
        self._preset_group.idToggled.connect(lambda *_: self._on_preset_changed())
        tw.addLayout(chips)

        self._custom_row = QWidget()
        cr = QHBoxLayout(self._custom_row)
        cr.setContentsMargins(0, 2, 0, 0)
        self.start_date_edit = QDateEdit(QDate.currentDate().addYears(-1))
        self.end_date_edit = QDateEdit(QDate.currentDate())
        for label, edit in (('From', self.start_date_edit), ('to', self.end_date_edit)):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat('d MMM yyyy')
            theme.style_date_edit(edit)
            edit.dateChanged.connect(lambda _: self._refresh())
            cr.addWidget(QLabel(label, styleSheet=theme.LABEL_TAG))
            cr.addWidget(edit, stretch=1)
        self._custom_row.hide()
        tw.addWidget(self._custom_row)
        layout.addWidget(self._time_widget)

        # ── 2b. Compare groups: What / Grouped by ─────────────────────────
        self._snap_widget = QWidget()
        sw = QVBoxLayout(self._snap_widget)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(6)
        sw.addWidget(QLabel('What do you want to compare?', styleSheet=_SECTION_STYLE))
        self.snap_metric_combo = self._metric_combo(analytics.SNAPSHOT_METRICS)
        sw.addWidget(self.snap_metric_combo)
        self.snap_metric_desc = self._description_label()
        sw.addWidget(self.snap_metric_desc)
        sw.addWidget(QLabel('Compare by', styleSheet=_SECTION_STYLE))
        self.group_by_combo = QComboBox()
        self.group_by_combo.addItems(analytics.GROUP_BY_OPTIONS)
        self.group_by_combo.setStyleSheet(_COMBO_STYLE)
        self.group_by_combo.currentIndexChanged.connect(lambda _: self._refresh())
        sw.addWidget(self.group_by_combo)
        self._snap_widget.hide()
        layout.addWidget(self._snap_widget)

        # ── More options (collapsed) ──────────────────────────────────────
        self._more_btn = QPushButton('More options ▸')
        self._more_btn.setCheckable(True)
        self._more_btn.setStyleSheet(
            f'QPushButton {{ border: none; color: {theme.BLUE}; font-size: 12px; text-align: left; '
            'padding: 8px 0 2px 0; background: transparent; }'
            'QPushButton:hover { text-decoration: underline; }')
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.toggled.connect(self._toggle_more)
        layout.addWidget(self._more_btn)

        self._more_widget = QWidget()
        mw = QVBoxLayout(self._more_widget)
        mw.setContentsMargins(0, 0, 0, 0)
        mw.setSpacing(6)

        mw.addWidget(QLabel('Name on the chart', styleSheet=_SECTION_STYLE))
        self.label_edit = QLineEdit()
        mw.addWidget(self.label_edit)

        style_row = QHBoxLayout()
        style_col = QVBoxLayout()
        style_col.addWidget(QLabel('Chart style', styleSheet=_SECTION_STYLE))
        self.style_combo = QComboBox()
        self.style_combo.setStyleSheet(_COMBO_STYLE)
        style_col.addWidget(self.style_combo)
        style_row.addLayout(style_col, stretch=1)

        self._gran_col = QWidget()
        gran_col = QVBoxLayout(self._gran_col)
        gran_col.setContentsMargins(0, 0, 0, 0)
        gran_col.addWidget(QLabel('Time step', styleSheet=_SECTION_STYLE))
        self.granularity_combo = QComboBox()
        self.granularity_combo.addItems([_AUTO_GRANULARITY] + analytics.GRANULARITIES)
        self.granularity_combo.setStyleSheet(_COMBO_STYLE)
        self.granularity_combo.currentIndexChanged.connect(lambda _: self._refresh())
        gran_col.addWidget(self.granularity_combo)
        style_row.addWidget(self._gran_col, stretch=1)
        mw.addLayout(style_row)

        self.trend_check = QCheckBox('Show trend line')
        self.trend_check.setStyleSheet('font-size: 12px; color: #333;')
        mw.addWidget(self.trend_check)

        mw.addWidget(QLabel('Colour', styleSheet=_SECTION_STYLE))
        swatches = QHBoxLayout()
        swatches.setSpacing(6)
        self._swatch_group = QButtonGroup(self)
        for i, color in enumerate(PALETTE):
            sw_btn = QPushButton()
            sw_btn.setCheckable(True)
            sw_btn.setFixedSize(26, 26)
            sw_btn.setStyleSheet(_swatch_style(color))
            sw_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            sw_btn.setToolTip(color)
            self._swatch_group.addButton(sw_btn, i)
            swatches.addWidget(sw_btn)
        swatches.addStretch()
        self._swatch_group.idClicked.connect(lambda i: setattr(self, '_color', PALETTE[i]))
        mw.addLayout(swatches)

        self._more_widget.hide()
        layout.addWidget(self._more_widget)
        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        # ── Footer: always visible ────────────────────────────────────────
        footer = QFrame()
        footer.setStyleSheet(f'QFrame {{ background: {theme.BG}; border-top: 1px solid {theme.BORDER}; }}')
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 10, 20, 10)
        self._error_label = QLabel()
        self._error_label.setStyleSheet(f'color: {theme.RED}; font-size: 11px; background: transparent; border: none;')
        self._error_label.setWordWrap(True)
        fl.addWidget(self._error_label, stretch=1)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setStyleSheet(theme.BTN_SECONDARY)
        cancel_btn.clicked.connect(self.reject)
        fl.addWidget(cancel_btn)
        self._confirm_btn = QPushButton('Save Changes' if self._existing else 'Add to Chart')
        self._confirm_btn.setStyleSheet(theme.BTN_PRIMARY)
        self._confirm_btn.setDefault(True)
        self._confirm_btn.clicked.connect(self._confirm)
        fl.addWidget(self._confirm_btn)
        outer.addWidget(footer)

        self._select_swatch(self._color)
        self._fill_style_combo()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _metric_combo(self, metrics) -> QComboBox:
        combo = QComboBox()
        combo.addItems(metrics)
        combo.setStyleSheet(_COMBO_STYLE)
        for i, m in enumerate(metrics):
            combo.setItemData(i, analytics.describe_metric(m), Qt.ItemDataRole.ToolTipRole)
        combo.currentIndexChanged.connect(lambda _: self._refresh())
        return combo

    def _description_label(self) -> QLabel:
        # Grey text under a metric dropdown explaining what the metric means.
        lbl = QLabel()
        lbl.setWordWrap(True)
        lbl.setStyleSheet(theme.LABEL_HINT)
        return lbl

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet('color: #E8E8E8;')
        return line

    def _fill_who_combo(self):
        # One list: 'All employees', then every group grouped by dimension
        # (e.g. 'Department: Sales'). Item data holds (filter_by, filter_val).
        self.who_combo.addItem(_ALL_EMPLOYEES, ('None', 'All'))
        if self._df is None:
            return
        for dim in analytics.GROUP_BY_OPTIONS:
            col = analytics._COL_MAP.get(dim, dim)
            if col not in self._df.columns:
                continue
            values = sorted(str(v) for v in self._df[col].dropna().unique())
            if dim == 'Age Group':
                values = [g for g in analytics.AGE_GROUP_ORDER if g in values]
            self.who_combo.insertSeparator(self.who_combo.count())
            for v in values:
                self.who_combo.addItem(f'{dim}: {v}', (dim, v))

    def _fill_style_combo(self):
        current = self.style_combo.currentText()
        styles = _TIME_STYLES if self._is_time() else _SNAP_STYLES
        self.style_combo.blockSignals(True)
        self.style_combo.clear()
        self.style_combo.addItems(styles)
        if current in styles:
            self.style_combo.setCurrentText(current)
        self.style_combo.blockSignals(False)

    def _select_swatch(self, color: str):
        if color in PALETTE:
            self._swatch_group.button(PALETTE.index(color)).setChecked(True)

    def _is_time(self) -> bool:
        return self.time_card.isChecked()

    # ── Reacting to choices ───────────────────────────────────────────────

    def _on_kind_changed(self):
        is_time = self._is_time()
        self._time_widget.setVisible(is_time)
        self._snap_widget.setVisible(not is_time)
        self._gran_col.setVisible(is_time)
        self.trend_check.setVisible(is_time)
        self._fill_style_combo()
        self._refresh()

    def _on_preset_changed(self):
        custom = _DATE_PRESETS[self._preset_group.checkedId()][1] == 'custom'
        self._custom_row.setVisible(custom)
        self._refresh()

    def _toggle_more(self, shown: bool):
        self._more_widget.setVisible(shown)
        self._more_btn.setText('More options ▾' if shown else 'More options ▸')

    def _dates(self) -> tuple[str, str]:
        preset = _DATE_PRESETS[self._preset_group.checkedId()][1]
        if preset == 'custom':
            return (self.start_date_edit.date().toString('yyyy-MM-dd'),
                    self.end_date_edit.date().toString('yyyy-MM-dd'))
        return _date_range(preset, self._df)

    def _current_series(self) -> dict:
        # The series as currently configured (without label/id).
        if self._is_time():
            filter_by, filter_val = self.who_combo.currentData() or ('None', 'All')
            start, end = self._dates()
            gran = self.granularity_combo.currentText()
            if gran == _AUTO_GRANULARITY:
                gran = auto_granularity(start, end)
            return {
                'view_type': 'time', 'metric': self.time_metric_combo.currentText(),
                'filter_by': filter_by, 'filter_val': filter_val,
                'start_date': start, 'end_date': end, 'granularity': gran,
                'style': self.style_combo.currentText(), 'show_trend': self.trend_check.isChecked(),
                'group_by': None,
            }
        return {
            'view_type': 'snapshot', 'metric': self.snap_metric_combo.currentText(),
            'filter_by': 'None', 'filter_val': 'All', 'start_date': None, 'end_date': None,
            'granularity': None, 'style': self.style_combo.currentText(), 'show_trend': False,
            'group_by': self.group_by_combo.currentText(),
        }

    def _validation_error(self, s: dict) -> str:
        if s['view_type'] == 'time' and pd.Timestamp(s['end_date']) <= pd.Timestamp(s['start_date']):
            return 'The end date must be after the start date.'
        return ''

    def _refresh(self):
        # Keep descriptions, the suggested name and the error message up to date.
        self.time_metric_desc.setText(analytics.describe_metric(self.time_metric_combo.currentText()))
        self.snap_metric_desc.setText(analytics.describe_metric(self.snap_metric_combo.currentText()))
        s = self._current_series()
        self.label_edit.setPlaceholderText(f'Automatic: {auto_label(s)}')
        error = self._validation_error(s)
        self._error_label.setText(error)
        self._confirm_btn.setEnabled(not error)

    # ── Results ───────────────────────────────────────────────────────────

    def _use_template(self, name: str):
        self._results = series_from_template(name, self._df)
        self.accept()

    def _confirm(self):
        s = self._current_series()
        if self._validation_error(s):
            return
        s['label'] = self.label_edit.text().strip() or auto_label(s)
        s['color'] = self._color
        s['id'] = self._existing.get('id', str(uuid.uuid4())[:8])
        self._results = [s]
        self.accept()

    def result_series(self):
        # The configured series (or the first series of a template).
        return self._results[0] if self._results else None

    def result_series_list(self) -> list[dict]:
        # Every series to add — templates can add more than one.
        return list(self._results)

    def _populate(self, s):
        # Fill the dialog from an existing series so it can be edited.
        self._color = s.get('color', PALETTE[0])
        self._select_swatch(self._color)
        if s.get('view_type') == 'snapshot':
            self.snap_card.setChecked(True)
            self.snap_metric_combo.setCurrentText(analytics.canonical_metric(s.get('metric', '')))
            self.group_by_combo.setCurrentText(s.get('group_by') or 'Department')
        else:
            self.time_card.setChecked(True)
            self.time_metric_combo.setCurrentText(analytics.canonical_metric(s.get('metric', '')))
            key = (s.get('filter_by', 'None'), s.get('filter_val', 'All'))
            for i in range(self.who_combo.count()):
                if self.who_combo.itemData(i) == key:
                    self.who_combo.setCurrentIndex(i)
                    break
            # Select the matching preset (e.g. 'Last 12 months'), otherwise show the custom dates
            saved = (s.get('start_date'), s.get('end_date'))
            preset_idx = next((i for i, (_n, months) in enumerate(_DATE_PRESETS)
                               if months != 'custom' and _date_range(months, self._df) == saved),
                              len(_DATE_PRESETS) - 1)
            self._preset_group.button(preset_idx).setChecked(True)
            for edit, iso in ((self.start_date_edit, saved[0]), (self.end_date_edit, saved[1])):
                if iso:
                    edit.setDate(QDate.fromString(iso, 'yyyy-MM-dd'))
            self.granularity_combo.setCurrentText(s.get('granularity') or _AUTO_GRANULARITY)
            self.trend_check.setChecked(bool(s.get('show_trend')))
        self._on_kind_changed()
        self.style_combo.setCurrentText(s.get('style', ''))
        # Keep a custom name; otherwise leave it on 'Automatic'
        if s.get('label') and s.get('label') != auto_label({**self._current_series(), **s}):
            self.label_edit.setText(s['label'])
