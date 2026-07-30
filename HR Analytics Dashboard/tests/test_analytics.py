from __future__ import annotations

import pandas as pd
import pytest

from core import analytics


def _series(categories: int) -> pd.Series:
    # Build a snapshot-style Series with the requested number of categories.
    idx = [f'Cat{i}' for i in range(categories)]
    return pd.Series(range(1, categories + 1), index=idx, name='Value')


# ── recommend_chart_type ──────────────────────────────────────────────────

class TestRecommendChartType:

    def test_always_returns_a_valid_concrete_type(self):
        # Sweep metrics, dimensions and category counts; result is always a
        # real chart type and never 'Auto'.
        for metric in analytics.SNAPSHOT_METRICS:
            for dim in analytics.GROUP_BY_OPTIONS:
                for n in (0, 1, 3, 8):
                    ctype = analytics.recommend_chart_type(metric, dim, _series(n))
                    assert ctype in analytics.CHART_TYPES
                    assert ctype != 'Auto'

    def test_employee_count_few_categories_is_pie(self):
        # Parts-of-a-whole count with a small number of categories → Pie.
        ctype = analytics.recommend_chart_type('Employee Count', 'Status', _series(3))
        assert ctype == 'Pie'

    @pytest.mark.parametrize('metric', [
        'Total Employees', 'Active Employees', 'On Leave Count', 'Resigned Count',
    ])
    def test_kpi_count_metrics_are_parts_of_whole(self, metric):
        # Count-type KPI/drill-down metrics behave like Employee Count: Pie when
        # there are few categories.
        assert analytics.recommend_chart_type(metric, 'Status', _series(3)) == 'Pie'

    def test_employee_count_many_categories_is_not_pie(self):
        # Too many slices to read as a pie → falls back to a bar.
        ctype = analytics.recommend_chart_type('Employee Count', 'Job Role', _series(8))
        assert ctype in ('Vertical Bar', 'Horizontal Bar')
        assert ctype not in ('Pie', 'Donut')

    @pytest.mark.parametrize('metric', [
        'Turnover Rate (%)',
        'Average Salary ($)',
        'Average Tenure (yrs)',
        'Average Age',
        'Avg Absenteeism Days',
        'Avg Leave Balance',
    ])
    def test_average_and_rate_metrics_never_pie(self, metric):
        # Averages/rates don't sum to a whole — Pie/Donut must never be chosen,
        # regardless of how few categories there are.
        for n in (2, 3, 4, 5):
            ctype = analytics.recommend_chart_type(metric, 'Status', _series(n))
            assert ctype not in ('Pie', 'Donut')

    def test_few_categories_is_vertical_bar(self):
        ctype = analytics.recommend_chart_type('Average Salary ($)', 'Department', _series(4))
        assert ctype == 'Vertical Bar'

    def test_many_categories_is_horizontal_bar(self):
        ctype = analytics.recommend_chart_type('Average Salary ($)', 'Job Role', _series(10))
        assert ctype == 'Horizontal Bar'

    def test_ordered_dimension_never_pie(self):
        # Age Group is ordered; even as a count it should stay a bar to preserve
        # the natural ordering of the buckets.
        ctype = analytics.recommend_chart_type('Employee Count', 'Age Group', _series(4))
        assert ctype == 'Vertical Bar'

    def test_empty_series_safe_default(self):
        ctype = analytics.recommend_chart_type('Employee Count', 'Status', _series(0))
        assert ctype == 'Vertical Bar'

    def test_single_category_safe_default(self):
        ctype = analytics.recommend_chart_type('Employee Count', 'Status', _series(1))
        assert ctype == 'Vertical Bar'

    def test_none_data_does_not_raise(self):
        ctype = analytics.recommend_chart_type('Employee Count', 'Status', None)
        assert ctype == 'Vertical Bar'
