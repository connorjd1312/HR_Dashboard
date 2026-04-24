# charts_tab.py
# The second tab, containing three sub-tabs with different chart types:
#   - Role Distribution: pie chart of employee count per job role
#   - Monthly Hires: line chart of hiring activity over time
#   - Turnover by Dept: horizontal bar chart of turnover rate per department
# update_data() is called by the main window whenever the dataset changes.

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from ui.chart_widget import ChartWidget
from core import analytics


class ChartsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Sub-tab container for the three chart views
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Each chart lives in its own ChartWidget (Matplotlib canvas)
        self.pie_chart = ChartWidget(width=6, height=4)
        self.line_chart = ChartWidget(width=8, height=4)
        self.turnover_chart = ChartWidget(width=7, height=4)

        self.tabs.addTab(self.pie_chart, 'Role Distribution')
        self.tabs.addTab(self.line_chart, 'Monthly Hires')
        self.tabs.addTab(self.turnover_chart, 'Turnover by Dept')

    def update_data(self, df):
        """Redraw all three charts with the given DataFrame."""

        # --- Pie chart: job role distribution ---
        self.pie_chart.clear_axes()
        roles = analytics.role_distribution(df)
        self.pie_chart.axes.pie(
            roles.values,
            labels=roles.index,
            autopct='%1.1f%%',  # show percentage on each slice
            startangle=140,
        )
        self.pie_chart.axes.set_title('Job Role Distribution')
        self.pie_chart.refresh()

        # --- Line chart: monthly hiring trend ---
        self.line_chart.clear_axes()
        hires = analytics.monthly_hires(df)
        self.line_chart.axes.plot(
            hires.index, hires.values,
            marker='o',       # dot at each data point
            color='#1F3864',
        )
        self.line_chart.axes.set_title('Monthly Hires Trend')
        self.line_chart.axes.set_ylabel('Hires')
        self.line_chart.axes.tick_params(axis='x', rotation=30)
        self.line_chart.refresh()

        # --- Horizontal bar chart: turnover rate by department ---
        self.turnover_chart.clear_axes()
        to = analytics.turnover_by_dept(df)
        self.turnover_chart.axes.barh(to.index, to.values, color='#C0392B')
        self.turnover_chart.axes.set_title('Turnover Rate by Department (%)')
        self.turnover_chart.axes.set_xlabel('Turnover %')
        self.turnover_chart.refresh()
