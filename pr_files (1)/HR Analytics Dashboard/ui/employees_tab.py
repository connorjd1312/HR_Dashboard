from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core import analytics, employee_search
from ui import theme

MAX_ROWS = 1000
SEARCH_DELAY_MS = 150

_STATUS_COLOURS = {
    'Active': ('#1E6B3A', '#E9F7EF'),
    'On Leave': ('#7A4B00', '#FFF4E5'),
    'Resigned': ('#555555', '#EAECF0'),
    'Retired': ('#555555', '#EAECF0'),
    'Terminated': ('#C0392B', '#FDECEA'),
}

_CARD = f'''
    QFrame#card {{ background: white; border: 1px solid {theme.BORDER}; border-radius: 8px; }}
'''
_INPUT = f'''
    QLineEdit, QComboBox {{
        background: white; border: 1px solid #CCC; border-radius: 4px;
        padding: 5px 8px; font-size: 12px; color: #333;
    }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {theme.BLUE}; }}
'''


def _money(v) -> str:
    return '-' if v is None else f'${v:,.0f}'


def _date(v) -> str:
    return '-' if v is None else analytics.format_date(v)


def _num(v, unit='', digits=1) -> str:
    return '-' if v is None else f'{v:,.{digits}f}{unit}'


def _avatar(initials: str, size: int = 64) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(theme.NAVY))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.setPen(QColor('white'))
    font = p.font()
    font.setPixelSize(int(size * 0.38))
    font.setBold(True)
    p.setFont(font)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, initials)
    p.end()
    return pix


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName('card')
    frame.setStyleSheet(_CARD)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    return frame, layout


def _card_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f'font-size: 12px; font-weight: bold; color: {theme.NAVY}; '
                      'background: transparent; border: none;')
    return lbl


class _ProfilePanel(QScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f'QScrollArea {{ background: {theme.BG}; }}')
        self._show_message('Select an employee to see their profile.')

    def _show_message(self, text: str):
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f'font-size: 14px; color: #888; background: {theme.BG};')
        self.setWidget(lbl)

    def clear(self, message: str = 'Select an employee to see their profile.'):
        self._show_message(message)

    def show_profile(self, p: dict):
        body = QWidget()
        body.setStyleSheet(f'background: {theme.BG};')
        v = QVBoxLayout(body)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(12)
        v.addWidget(self._header(p))
        v.addWidget(self._details(p))
        v.addWidget(self._comparison(p))
        v.addStretch()
        self.setWidget(body)

    def _header(self, p: dict) -> QFrame:
        frame, lay = _card()
        row = QHBoxLayout()
        row.setSpacing(16)
        avatar = QLabel()
        avatar.setPixmap(_avatar(employee_search.initials(p['name'])))
        avatar.setFixedSize(QSize(64, 64))
        avatar.setStyleSheet('background: transparent; border: none;')
        row.addWidget(avatar)

        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(p['name'] or 'Unknown')
        name.setStyleSheet(f'font-size: 22px; font-weight: bold; color: {theme.NAVY}; '
                           'background: transparent; border: none;')
        name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.addWidget(name)
        role = QLabel(', '.join(x for x in (p['job_role'], p['department']) if x) or '-')
        role.setStyleSheet('font-size: 13px; color: #555; background: transparent; border: none;')
        text.addWidget(role)
        row.addLayout(text, stretch=1)

        status = p['status'] or 'Unknown'
        fg, bg = _STATUS_COLOURS.get(status, ('#555555', '#EAECF0'))
        pill = QLabel(status)
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setStyleSheet(f'font-size: 12px; font-weight: bold; color: {fg}; background: {bg}; '
                           'border-radius: 11px; padding: 3px 14px; border: none;')
        row.addWidget(pill, alignment=Qt.AlignmentFlag.AlignTop)
        lay.addLayout(row)
        return frame

    def _details(self, p: dict) -> QFrame:
        frame, lay = _card()
        lay.addWidget(_card_title('Details'))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)

        end = p['end_date']
        tenure_note = 'until leaving' if p['left_company'] else 'so far'
        facts = [
            ('Hired', _date(p['hire_date'])),
            ('Left' if p['left_company'] else 'Employment', _date(end) if end is not None else 'Still employed'),
            ('Tenure', f"{_num(p['tenure_years'])} years {tenure_note}" if p['tenure_years'] is not None else '-'),
            ('Salary', _money(p['salary'])),
            ('Age', (f"{p['age']:.0f}" + (f"  ({p['age_group']})" if p['age_group'] else ''))
             if p['age'] is not None else '-'),
            ('Date of birth', _date(p['date_of_birth'])),
            ('Sex', p['sex'] or '-'),
            ('Ethnicity', p['ethnicity'] or '-'),
            ('Absenteeism', _num(p['absenteeism_days'], ' days', 0)),
            ('Leave balance', _num(p['leave_balance'], ' days')),
        ]
        for i, (label, value) in enumerate(facts):
            cell = QVBoxLayout()
            cell.setSpacing(1)
            k = QLabel(label.upper())
            k.setStyleSheet('font-size: 10px; color: #888; font-weight: bold; letter-spacing: 1px; '
                            'background: transparent; border: none;')
            val = QLabel(value)
            val.setStyleSheet('font-size: 13px; color: #333; background: transparent; border: none;')
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cell.addWidget(k)
            cell.addWidget(val)
            holder = QWidget()
            holder.setLayout(cell)
            grid.addWidget(holder, i // 3, i % 3)
        lay.addLayout(grid)
        return frame

    def _comparison(self, p: dict) -> QFrame:
        frame, lay = _card()
        dept = p['department'] or 'their department'
        lay.addWidget(_card_title(f'Compared with {dept}'))
        if not p['peers']:
            note = QLabel('Not enough people in this department to make a comparison.')
            note.setStyleSheet('font-size: 12px; color: #888; background: transparent; border: none;')
            lay.addWidget(note)
            return frame

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        for col, head in enumerate(('', 'This person', 'Department average', 'Difference', 'Rank in department')):
            h = QLabel(head)
            h.setStyleSheet('font-size: 10px; color: #888; font-weight: bold; background: transparent; border: none;')
            grid.addWidget(h, 0, col)

        for r, m in enumerate(p['peers'], start=1):
            fmt = _money if m['unit'] == '$' else _num
            diff = m['difference']
            sign = '+' if diff > 0 else '-' if diff < 0 else ''
            diff_text = f"{sign}{_money(abs(diff)) if m['unit'] == '$' else _num(abs(diff))}"
            if diff == 0:
                colour = '#888'
            elif m['good_direction'] == 0:
                colour = '#555555'
            else:
                colour = '#1E8449' if (diff > 0) == (m['good_direction'] > 0) else '#C0392B'
            cells = [
                (m['label'], 'font-size: 12px; color: #333; font-weight: bold;'),
                (fmt(m['value']), 'font-size: 12px; color: #333;'),
                (fmt(m['department_avg']), 'font-size: 12px; color: #555;'),
                (diff_text, f'font-size: 12px; font-weight: bold; color: {colour};'),
                (f"higher than {m['department_percentile']:.0f}% of colleagues", 'font-size: 11px; color: #777;'),
            ]
            for c, (text, style) in enumerate(cells):
                lbl = QLabel(text)
                lbl.setStyleSheet(style + ' background: transparent; border: none;')
                grid.addWidget(lbl, r, c)
        lay.addLayout(grid)

        salary = next((m for m in p['peers'] if m['column'] == 'Salary'), None)
        if salary and 'role_avg' in salary:
            role = QLabel(f"Average salary for {p['job_role']} ({salary['role_count']:,} people): "
                          f"{_money(salary['role_avg'])}")
            role.setStyleSheet('font-size: 12px; color: #555; background: transparent; border: none;')
            lay.addWidget(role)

        foot = QLabel(f"Based on {p['department_size']:,} people in this department, including former employees.")
        foot.setStyleSheet('font-size: 11px; color: #888; background: transparent; border: none;')
        lay.addWidget(foot)
        return frame


class EmployeesTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._selected_key = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SEARCH_DELAY_MS)
        self._timer.timeout.connect(self._run_search)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)

        split.addWidget(self._build_left())
        self._profile = _ProfilePanel()
        split.addWidget(self._profile)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([460, 700])

    def _build_left(self) -> QWidget:
        left = QWidget()
        left.setMinimumWidth(380)
        left.setStyleSheet(f'background: {theme.BG};')
        v = QVBoxLayout(left)
        v.setContentsMargins(16, 16, 12, 12)
        v.setSpacing(8)

        title = QLabel('Find an employee')
        title.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {theme.NAVY};')
        v.addWidget(title)

        self._search = QLineEdit()
        self._search.setPlaceholderText('Search by name, department, job role or status...')
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(_INPUT)
        self._search.textChanged.connect(lambda _t: self._timer.start())
        self._search.returnPressed.connect(self._select_first)
        v.addWidget(self._search)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self._dept = QComboBox()
        self._status = QComboBox()
        for combo in (self._dept, self._status):
            combo.setStyleSheet(_INPUT)
            combo.currentIndexChanged.connect(lambda _i: self._run_search())
            filters.addWidget(combo, stretch=1)
        v.addLayout(filters)

        self._count = QLabel('')
        self._count.setStyleSheet('font-size: 11px; color: #777;')
        v.addWidget(self._count)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(['Name', 'Department', 'Job role', 'Status'])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().hide()
        self._table.verticalHeader().setDefaultSectionSize(30)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setStyleSheet(f'''
            QTableWidget {{ background: white; alternate-background-color: #F8F9FB;
                           border: 1px solid {theme.BORDER}; border-radius: 6px; font-size: 12px; }}
            QTableWidget::item:selected {{ background: {theme.BLUE}; color: white; }}
            QHeaderView::section {{ background: {theme.NAVY}; color: white; font-weight: bold;
                                   font-size: 11px; padding: 6px; border: none; }}
        ''')
        self._table.itemSelectionChanged.connect(self._on_selection)
        v.addWidget(self._table, stretch=1)
        return left

    def update_data(self, df: pd.DataFrame | None):
        self._df = df
        self._selected_key = None
        self._profile.clear()
        for combo, col in ((self._dept, 'Department'), (self._status, 'Status')):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem('All departments' if col == 'Department' else 'All statuses', 'All')
            if df is not None and col in df.columns:
                for value in sorted(df[col].dropna().unique().tolist()):
                    combo.addItem(str(value), str(value))
            combo.blockSignals(False)
        self._run_search()

    def focus_search(self):
        self._search.setFocus()
        self._search.selectAll()

    def show_employee(self, key) -> bool:
        if self._df is None or key not in self._df.index:
            return False
        name = self._df.loc[key, 'Name']
        self._dept.setCurrentIndex(0)
        self._status.setCurrentIndex(0)
        self._search.setText(str(name))
        self._run_search()
        for row in range(self._table.rowCount()):
            if self._table.item(row, 0).data(Qt.ItemDataRole.UserRole) == key:
                self._table.selectRow(row)
                self._table.scrollToItem(self._table.item(row, 0))
                return True
        return False

    def _run_search(self):
        self._timer.stop()
        if self._df is None or len(self._df) == 0:
            self._fill([], 0)
            self._count.setText('Load employee data to search it.')
            return
        results = employee_search.search_employees(
            self._df, self._search.text(), self._dept.currentData() or 'All',
            self._status.currentData() or 'All')
        total = len(results)
        self._fill(results.head(MAX_ROWS), total)

    def _fill(self, results, total: int):
        keep = self._selected_key
        table = self._table
        table.blockSignals(True)
        table.setSortingEnabled(False)
        table.setRowCount(0)
        rows = []
        if len(results):
            for key, r in results.iterrows():
                rows.append((key, r.get('Name'), r.get('Department'), r.get('Job_Role'), r.get('Status')))
        table.setRowCount(len(rows))
        for i, (key, *cells) in enumerate(rows):
            for c, value in enumerate(cells):
                item = QTableWidgetItem('' if value is None or (isinstance(value, float) and pd.isna(value)) else str(value))
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, key)
                table.setItem(i, c, item)
        # Keep best-match order until the user clicks a column header.
        table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        table.setSortingEnabled(True)
        table.blockSignals(False)

        if self._df is not None and len(self._df):
            if total == 0:
                self._count.setText('No employees match.')
            elif total > MAX_ROWS:
                self._count.setText(f'{total:,} employees match, showing the first {MAX_ROWS:,}. Type more to narrow.')
            else:
                self._count.setText(f'{total:,} employee{"s" if total != 1 else ""}')

        for row in range(table.rowCount()):
            if keep is not None and table.item(row, 0).data(Qt.ItemDataRole.UserRole) == keep:
                table.blockSignals(True)
                table.selectRow(row)
                table.blockSignals(False)
                return
        if keep is not None:
            self._selected_key = None
            self._profile.clear()

    def _select_first(self):
        if self._table.rowCount():
            self._table.selectRow(0)

    def _on_selection(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        key = self._table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        self._selected_key = key
        profile = employee_search.employee_profile(self._df, key)
        if profile is None:
            self._profile.clear('That employee is no longer in the loaded data.')
        else:
            self._profile.show_profile(profile)
