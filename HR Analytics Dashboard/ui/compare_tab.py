import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QListWidget, QListWidgetItem, QPushButton, QGroupBox, QFrame,
)
from PyQt6.QtCore import Qt

from core import analytics
from ui.chart_widget import ChartWithToolbar

DEPT_COLOURS = [
    '#1F3864', '#2E75B6', '#1E8449', '#C0392B',
    '#D4AC0D', '#5B2C6F', '#117A65', '#E67E22',
]

CHART_TYPES = ['Vertical Bar', 'Horizontal Bar', 'Radar']


class CompareTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Controls row ──────────────────────────────────────────────────
        controls = QWidget()
        controls.setStyleSheet('background-color: #F5F7FA;')
        controls.setFixedHeight(160)
        row = QHBoxLayout(controls)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(12)

        # Department checklist
        dept_group = QGroupBox('Select Departments')
        dept_inner = QVBoxLayout(dept_group)
        dept_inner.setSpacing(4)

        self.dept_list = QListWidget()
        self.dept_list.setFixedHeight(90)
        self.dept_list.itemChanged.connect(self._draw)
        dept_inner.addWidget(self.dept_list)

        btn_row = QHBoxLayout()
        all_btn = QPushButton('All')
        all_btn.setFixedHeight(24)
        all_btn.clicked.connect(self._select_all)
        none_btn = QPushButton('None')
        none_btn.setFixedHeight(24)
        none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        dept_inner.addLayout(btn_row)
        row.addWidget(dept_group, stretch=3)

        # Metric selector
        metric_group = QGroupBox('Metric')
        metric_inner = QVBoxLayout(metric_group)
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(analytics.COMPARISON_METRICS)
        self.metric_combo.currentIndexChanged.connect(self._draw)
        metric_inner.addWidget(self.metric_combo)
        metric_inner.addStretch()
        row.addWidget(metric_group, stretch=2)

        # Chart type selector
        chart_group = QGroupBox('Display As')
        chart_inner = QVBoxLayout(chart_group)
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItems(CHART_TYPES)
        self.chart_type_combo.currentIndexChanged.connect(self._draw)
        chart_inner.addWidget(self.chart_type_combo)
        chart_inner.addStretch()
        row.addWidget(chart_group, stretch=2)

        layout.addWidget(controls)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet('color: #E0E0E0;')
        layout.addWidget(line)

        # ── Chart area ────────────────────────────────────────────────────
        self.chart = ChartWithToolbar(width=9, height=5)
        layout.addWidget(self.chart)

        # Placeholder message shown before data loads
        self._placeholder = QLabel('Load a data file to use department comparison.')
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet('font-size: 13px; color: #888888;')
        layout.addWidget(self._placeholder)
        self.chart.hide()

    # ── Public API ────────────────────────────────────────────────────────

    def update_data(self, df):
        self._df = df
        self._placeholder.hide()
        self.chart.show()

        # Block signals while rebuilding the list so _draw isn't called per item
        self.dept_list.blockSignals(True)
        self.dept_list.clear()
        for dept in sorted(df['Department'].dropna().unique()):
            item = QListWidgetItem(dept)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.dept_list.addItem(item)
        self.dept_list.blockSignals(False)

        self._draw()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _checked_departments(self):
        result = []
        for i in range(self.dept_list.count()):
            item = self.dept_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return result

    def _select_all(self):
        self.dept_list.blockSignals(True)
        for i in range(self.dept_list.count()):
            self.dept_list.item(i).setCheckState(Qt.CheckState.Checked)
        self.dept_list.blockSignals(False)
        self._draw()

    def _select_none(self):
        self.dept_list.blockSignals(True)
        for i in range(self.dept_list.count()):
            self.dept_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.dept_list.blockSignals(False)
        self._draw()

    def _draw(self):
        if self._df is None:
            return

        departments = self._checked_departments()
        if not departments:
            self.chart.reset_axes()
            self.chart.axes.text(
                0.5, 0.5, 'Select at least one department to compare.',
                ha='center', va='center', transform=self.chart.axes.transAxes,
                fontsize=12, color='#888888',
            )
            self.chart.refresh()
            return

        metric = self.metric_combo.currentText()
        chart_type = self.chart_type_combo.currentText()
        data = analytics.dept_comparison(self._df, departments, metric)

        is_radar = chart_type == 'Radar'
        self.chart.reset_axes(polar=is_radar)
        ax = self.chart.axes
        colours = [DEPT_COLOURS[i % len(DEPT_COLOURS)] for i in range(len(data))]

        if chart_type == 'Vertical Bar':
            bars = ax.bar(data.index, data.values, color=colours)
            ax.bar_label(bars, fmt=self._label_fmt(metric), padding=3, fontsize=9)
            ax.set_ylabel(metric)
            ax.tick_params(axis='x', rotation=20)
            ax.set_title(f'{metric} by Department')

        elif chart_type == 'Horizontal Bar':
            bars = ax.barh(data.index, data.values, color=colours)
            ax.bar_label(bars, fmt=self._label_fmt(metric), padding=3, fontsize=9)
            ax.set_xlabel(metric)
            ax.set_title(f'{metric} by Department')

        elif chart_type == 'Radar':
            self._draw_radar(ax, data, metric)

        self.chart.refresh()

    def _draw_radar(self, ax, data, metric):
        labels = list(data.index)
        values = list(data.values)
        n = len(labels)

        if n < 3:
            ax.set_visible(False)
            # fall back to text — reset to standard axes first
            self.chart.reset_axes(polar=False)
            self.chart.axes.text(
                0.5, 0.5, 'Select at least 3 departments for a radar chart.',
                ha='center', va='center', transform=self.chart.axes.transAxes,
                fontsize=12, color='#888888',
            )
            return

        angles = [2 * np.pi * i / n for i in range(n)] + [0]
        values_closed = values + [values[0]]

        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=9)

        # Scale y-axis from 0 with a small top margin
        max_val = max(values) if max(values) > 0 else 1
        ax.set_ylim(0, max_val * 1.2)
        ax.set_yticklabels([])  # hide radial labels to reduce clutter

        ax.plot(angles, values_closed, 'o-', linewidth=2, color='#1F3864')
        ax.fill(angles, values_closed, alpha=0.25, color='#2E75B6')
        ax.set_title(f'{metric} — Radar View', pad=20)

    @staticmethod
    def _label_fmt(metric):
        if metric == 'Average Salary ($)':
            return '${:,.0f}'
        if metric == 'Overall Turnover Rate (%)':
            return '{:.1f}%'
        return '{:.1f}'
