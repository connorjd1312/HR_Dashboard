# filter_panel.py
# The sidebar panel that lets the user filter the dataset by department,
# employment status, and hire date range.
# When the user clicks Apply Filters, this widget emits a signal containing
# the selected filter values. The main window listens for that signal and
# re-filters the data before refreshing all charts and KPIs.

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox,
    QDateEdit, QPushButton, QGroupBox,
)
from PyQt6.QtCore import pyqtSignal, QDate


class FilterPanel(QWidget):
    # Signal emitted when Apply Filters is clicked.
    # Carries a dict with keys: department, status, date_from, date_to.
    filters_changed = pyqtSignal(dict)

    def __init__(self, df, parent=None):
        super().__init__(parent)
        self._df = df  # used to populate the department dropdown with real values
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        group = QGroupBox('Filters')
        g_layout = QVBoxLayout(group)

        # Department dropdown — populated from the actual unique values in the dataset
        g_layout.addWidget(QLabel('Department'))
        self.dept_combo = QComboBox()
        self.dept_combo.addItem('All')  # 'All' means no department filter applied
        self.dept_combo.addItems(sorted(self._df['Department'].dropna().unique()))
        g_layout.addWidget(self.dept_combo)

        # Employment status dropdown
        g_layout.addWidget(QLabel('Employment Status'))
        self.status_combo = QComboBox()
        self.status_combo.addItem('All')
        self.status_combo.addItems(['Active', 'Resigned', 'Terminated'])
        g_layout.addWidget(self.status_combo)

        # Hire date range — defaults to the full range expected in sample data
        g_layout.addWidget(QLabel('Hire Date From'))
        self.date_from = QDateEdit(QDate(2015, 1, 1))
        self.date_from.setCalendarPopup(True)  # shows a calendar picker on click
        g_layout.addWidget(self.date_from)

        g_layout.addWidget(QLabel('Hire Date To'))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        g_layout.addWidget(self.date_to)

        # Clicking Apply triggers the signal — charts won't update until this is clicked
        btn = QPushButton('Apply Filters')
        btn.clicked.connect(self._emit)
        g_layout.addWidget(btn)

        layout.addWidget(group)
        layout.addStretch()  # pushes the group box to the top of the panel

    def _emit(self):
        """Collect the current filter values and emit them as a dict."""
        self.filters_changed.emit({
            'department': self.dept_combo.currentText(),
            'status': self.status_combo.currentText(),
            'date_from': self.date_from.date().toPyDate(),
            'date_to': self.date_to.date().toPyDate(),
        })
