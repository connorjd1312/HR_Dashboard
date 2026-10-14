from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QRadioButton, QVBoxLayout,
)

from core.report_generator import ReportOptions
from ui import theme

_PRIMARY = f'''
    QPushButton {{ background: {theme.NAVY}; color: white; border: none; border-radius: 4px;
                  padding: 7px 18px; font-size: 12px; font-weight: bold; }}
    QPushButton:hover {{ background: {theme.BLUE}; }}
'''
_SECONDARY = '''
    QPushButton { background: white; color: #444; border: 1px solid #CCC; border-radius: 4px;
                  padding: 7px 16px; font-size: 12px; }
    QPushButton:hover { background: #F0F4FF; border-color: #2E75B6; }
'''
_HEADING = f'font-size: 12px; font-weight: bold; color: {theme.NAVY};'
_HINT = 'font-size: 11px; color: #777;'

OVERVIEW_CHART_COUNT = 6


class ReportDialog(QDialog):

    def __init__(self, kpi_count: int, dashboard_chart_count: int, analytics_chart_count: int,
                 dashboard_scope: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Export PDF Summary Report')
        self.setMinimumWidth(520)

        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(8)

        head = QLabel('PDF summary report')
        head.setStyleSheet(f'font-size: 16px; font-weight: bold; color: {theme.NAVY};')
        v.addWidget(head)
        intro = QLabel('A printable summary of the key figures, highlights and charts.')
        intro.setStyleSheet(_HINT)
        v.addWidget(intro)

        v.addSpacing(6)
        v.addWidget(self._heading('Title'))
        self._title = QLineEdit('HR Workforce Summary')
        self._title.setStyleSheet('QLineEdit { padding: 6px 8px; border: 1px solid #CCC; border-radius: 4px; '
                                  'background: white; font-size: 12px; }')
        v.addWidget(self._title)

        v.addSpacing(6)
        v.addWidget(self._heading('Employees to include'))
        self._scope_dash = QRadioButton('What the Dashboard is showing now')
        self._scope_dash.setChecked(True)
        v.addWidget(self._scope_dash)
        hint = QLabel(dashboard_scope[:1].upper() + dashboard_scope[1:])
        hint.setWordWrap(True)
        hint.setStyleSheet(_HINT + ' margin-left: 22px;')
        v.addWidget(hint)
        self._scope_all = QRadioButton('All loaded data')
        v.addWidget(self._scope_all)
        group = QButtonGroup(self)
        group.addButton(self._scope_dash)
        group.addButton(self._scope_all)

        v.addSpacing(6)
        v.addWidget(self._heading('Sections'))
        self._kpis = QCheckBox(f'Key figures: the Dashboard KPI cards ({kpi_count})')
        self._dash_charts = QCheckBox(f'Dashboard charts ({dashboard_chart_count})')
        self._overview = QCheckBox(f'Workforce overview charts ({OVERVIEW_CHART_COUNT})')
        self._analytics = QCheckBox(f'Charts from the Analytics tab ({analytics_chart_count})')
        for box, count in ((self._kpis, kpi_count), (self._dash_charts, dashboard_chart_count),
                           (self._overview, 1), (self._analytics, analytics_chart_count)):
            box.setChecked(count > 0)
            box.setEnabled(count > 0)
            v.addWidget(box)
        if analytics_chart_count == 0:
            note = QLabel('Build charts in the Analytics tab and they can be added here.')
            note.setStyleSheet(_HINT + ' margin-left: 22px;')
            v.addWidget(note)
        highlights = QLabel('Highlights (largest department, turnover, hiring trend) are always included.')
        highlights.setStyleSheet(_HINT)
        v.addWidget(highlights)

        v.addSpacing(10)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton('Cancel')
        cancel.setStyleSheet(_SECONDARY)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        export = QPushButton('Choose file and export...')
        export.setStyleSheet(_PRIMARY)
        export.setDefault(True)
        export.clicked.connect(self.accept)
        row.addWidget(export)
        v.addLayout(row)

    @staticmethod
    def _heading(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_HEADING)
        return lbl

    def use_dashboard_scope(self) -> bool:
        return self._scope_dash.isChecked()

    def options(self) -> ReportOptions:
        return ReportOptions(
            title=self._title.text().strip() or 'HR Workforce Summary',
            include_kpis=self._kpis.isChecked(),
            include_dashboard_charts=self._dash_charts.isChecked(),
            include_overview_charts=self._overview.isChecked(),
            include_analytics_charts=self._analytics.isChecked(),
        )
