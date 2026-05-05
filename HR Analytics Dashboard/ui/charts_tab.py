# charts_tab.py
# The second tab, containing three sub-tabs with different chart types:
#   - Role Distribution: pie chart of employee count per job role
#   - Monthly Hires: line chart of hiring activity over time
#   - Turnover by Dept: horizontal bar chart of turnover rate per department
# update_data() is called by the main window whenever the dataset changes.

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from ui.chart_widget import ChartWithToolbar
from ui.compare_tab import CompareTab
from core import analytics


class ChartsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Sub-tab container for all chart views
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.pie_chart = ChartWithToolbar(width=6, height=4)
        self.line_chart = ChartWithToolbar(width=8, height=4)
        self.turnover_chart = ChartWithToolbar(width=7, height=4)
        self.salary_chart = ChartWithToolbar(width=8, height=4)
        self.absenteeism_chart = ChartWithToolbar(width=8, height=4)
        self.leave_chart = ChartWithToolbar(width=8, height=4)
        self.compare_sub = CompareTab()

        self.tabs.addTab(self.pie_chart, 'Role Distribution')
        self.tabs.addTab(self.line_chart, 'Monthly Hires')
        self.tabs.addTab(self.turnover_chart, 'Turnover by Dept')
        self.tabs.addTab(self.salary_chart, 'Salary by Dept')
        self.tabs.addTab(self.absenteeism_chart, 'Absenteeism by Dept')
        self.tabs.addTab(self.leave_chart, 'Leave Balance by Dept')
        self.tabs.addTab(self.compare_sub, 'Compare Departments')

    def update_data(self, df):
        # Redraw all charts with the given DataFrame.

        # Pie chart; job role distribution
        self.pie_chart.clear_axes()
        roles = analytics.role_distribution(df)
        self.pie_chart.axes.pie(
            roles.values,
            labels=roles.index,
            autopct='%1.1f%%',
            startangle=140,
        )
        self.pie_chart.axes.set_title('Job Role Distribution')
        self.pie_chart.refresh()

        # Line chart; monthly hiring trend
        self.line_chart.clear_axes()
        hires = analytics.monthly_hires(df)
        self.line_chart.axes.plot(
            hires.index, hires.values,
            marker='o',
            color='#1F3864',
        )
        self.line_chart.axes.set_title('Monthly Hires Trend')
        self.line_chart.axes.set_ylabel('Hires')
        self.line_chart.axes.tick_params(axis='x', rotation=30)
        self.line_chart.refresh()

        # Horizontal bar chart: turnover rate by department
        self.turnover_chart.clear_axes()
        to = analytics.turnover_by_dept(df)
        self.turnover_chart.axes.barh(to.index, to.values, color='#C0392B')
        self.turnover_chart.axes.set_title('Turnover Rate by Department (%)')
        self.turnover_chart.axes.set_xlabel('Turnover %')
        self.turnover_chart.refresh()

        # Bar chart: average salary by department 
        self.salary_chart.clear_axes()
        sal = analytics.salary_by_dept(df)
        self.salary_chart.axes.bar(sal.index, sal.values, color='#1E8449')
        self.salary_chart.axes.set_title('Average Salary by Department ($)')
        self.salary_chart.axes.set_ylabel('Avg Salary ($)')
        self.salary_chart.axes.tick_params(axis='x', rotation=20)
        # Format y axis values with commas
        self.salary_chart.axes.yaxis.set_major_formatter(
            lambda x, _: f'${x:,.0f}'
        )
        self.salary_chart.refresh()

        #Bar chart: average absenteeism days by department
        self.absenteeism_chart.clear_axes()
        ab = analytics.avg_absenteeism_by_dept(df)
        if not ab.empty:
            self.absenteeism_chart.axes.bar(ab.index, ab.values, color='#D4AC0D')
            self.absenteeism_chart.axes.set_title('Avg Absenteeism Days by Department')
            self.absenteeism_chart.axes.set_ylabel('Avg Days Absent')
            self.absenteeism_chart.axes.tick_params(axis='x', rotation=20)
        self.absenteeism_chart.refresh()

        # Bar chart: average leave balance by department
        self.leave_chart.clear_axes()
        lb = analytics.leave_balance_by_dept(df)
        if not lb.empty:
            self.leave_chart.axes.bar(lb.index, lb.values, color='#5B2C6F')
            self.leave_chart.axes.set_title('Avg Leave Balance by Department (Days)')
            self.leave_chart.axes.set_ylabel('Avg Leave Balance (Days)')
            self.leave_chart.axes.tick_params(axis='x', rotation=20)
        self.leave_chart.refresh()

        self.compare_sub.update_data(df)
