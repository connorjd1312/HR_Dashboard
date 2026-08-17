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
        'Overall Turnover Rate (%)',
        'Attrition Rate (%)',
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


# ── Attrition rate ────────────────────────────────────────────────────────

def _staff() -> pd.DataFrame:
    # Four leavers (2 resigned, 1 retired, 1 terminated) out of eight staff.
    status = ['Active', 'Active', 'Active', 'On Leave',
              'Resigned', 'Resigned', 'Retired', 'Terminated']
    dept = ['Sales'] * 4 + ['IT'] * 4
    end = [None] * 4 + ['2026-01-15', '2026-02-10', '2026-02-20', '2026-03-05']
    df = pd.DataFrame({
        'Name': [f'E{i}' for i in range(8)],
        'Department': dept,
        'Status': status,
        'End_Date': pd.to_datetime(end),
    })
    df['Turnover'] = df['Status'].isin(['Resigned', 'Terminated', 'Retired'])
    return df


class TestAttritionRate:

    def test_kpi_excludes_terminations(self):
        # 3 voluntary leavers / 8 staff = 37.5%, while overall turnover is 50%.
        df = _staff()
        assert analytics.kpi_value(df, 'Attrition Rate (%)') == '37.5%'
        assert analytics.kpi_value(df, 'Overall Turnover Rate (%)') == '50.0%'

    def test_relevant_employees_are_voluntary_leavers(self):
        rows = analytics.kpi_relevant_employees(_staff(), 'Attrition Rate (%)')
        assert sorted(rows['Status']) == ['Resigned', 'Resigned', 'Retired']

    def test_breakdown_by_department(self):
        result = analytics.kpi_breakdown(_staff(), 'Attrition Rate (%)', 'Department')
        assert result['IT'] == 75.0
        assert result['Sales'] == 0.0

    def test_snapshot_matches_breakdown(self):
        df = _staff()
        snap = analytics.snapshot_data(df, 'Attrition Rate (%)', 'Department')
        assert snap.equals(analytics.kpi_breakdown(df, 'Attrition Rate (%)', 'Department'))

    def test_dept_comparison(self):
        result = analytics.dept_comparison(_staff(), ['IT', 'Sales'], 'Attrition Rate (%)')
        assert result['IT'] == 75.0
        assert result['Sales'] == 0.0

    def test_monthly_series_counts_voluntary_exits_only(self):
        series = analytics.time_series_data(
            _staff(), 'Monthly Attrition Rate (%)', 'None', 'All',
            pd.Timestamp('2026-01-01'), pd.Timestamp('2026-03-31'), 'Monthly',
        )
        # Jan: 1 resigned, Feb: 1 resigned + 1 retired, Mar: termination only.
        assert list(series) == [12.5, 25.0, 0.0]
