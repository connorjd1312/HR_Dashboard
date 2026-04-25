# dashboard_tab.py
# The first tab the user sees after loading a file.
# Shows five KPI summary cards across the top and a department bar chart below.
# update_data() is called by the main window whenever the dataset changes
# (on file load or when a filter is applied).

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from PyQt6.QtCore import Qt
from core import analytics
from ui.chart_widget import ChartWithToolbar

# Qt stylesheet applied to each KPI card — dark navy background, white text
CARD_STYLE = '''
    QFrame { background: #1F3864; border-radius: 8px; padding: 12px; }
    QLabel { color: white; font-family: Arial; }
'''


class DashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Horizontal row of KPI cards at the top
        self.kpi_row = QHBoxLayout()
        layout.addLayout(self.kpi_row)

        # Bar chart of employee count per department below the KPI cards
        self.dept_chart = ChartWithToolbar(width=8, height=4)
        layout.addWidget(self.dept_chart)

    def _make_kpi_card(self, label, value):
        """Build a single styled KPI card with a small label and large value."""
        frame = QFrame()
        frame.setStyleSheet(CARD_STYLE)
        vbox = QVBoxLayout(frame)

        lbl = QLabel(label)
        lbl.setStyleSheet('font-size: 11px;')

        val = QLabel(str(value))
        val.setStyleSheet('font-size: 22px; font-weight: bold;')

        vbox.addWidget(lbl)
        vbox.addWidget(val)
        return frame

    def update_data(self, df):
        """Rebuild KPI cards and redraw the department chart with the given DataFrame."""
        self._df = df

        # Remove old KPI cards before adding new ones
        while self.kpi_row.count():
            w = self.kpi_row.takeAt(0).widget()
            if w:
                w.deleteLater()

        # Add one card for each KPI metric
        for label, value in analytics.summary_kpis(df).items():
            self.kpi_row.addWidget(self._make_kpi_card(label, value))

        # Redraw the department bar chart
        ax = self.dept_chart.axes
        self.dept_chart.clear_axes()
        dept_data = analytics.dept_distribution(df)
        ax.bar(dept_data.index, dept_data.values, color='#2E75B6')
        ax.set_title('Employees by Department', fontsize=12, fontweight='bold')
        ax.set_ylabel('Count')
        ax.tick_params(axis='x', rotation=20)
        self.dept_chart.refresh()
