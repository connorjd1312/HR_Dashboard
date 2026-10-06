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
        'Attrition (Voluntary Leavers) Rate (%)',
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
        assert analytics.kpi_value(df, 'Attrition (Voluntary Leavers) Rate (%)') == '37.5%'
        assert analytics.kpi_value(df, 'Overall Turnover Rate (%)') == '50.0%'

    def test_relevant_employees_are_voluntary_leavers(self):
        rows = analytics.kpi_relevant_employees(_staff(), 'Attrition (Voluntary Leavers) Rate (%)')
        assert sorted(rows['Status']) == ['Resigned', 'Resigned', 'Retired']

    def test_breakdown_by_department(self):
        result = analytics.kpi_breakdown(_staff(), 'Attrition (Voluntary Leavers) Rate (%)', 'Department')
        assert result['IT'] == 75.0
        assert result['Sales'] == 0.0

    def test_snapshot_matches_breakdown(self):
        df = _staff()
        snap = analytics.snapshot_data(df, 'Attrition (Voluntary Leavers) Rate (%)', 'Department')
        assert snap.equals(analytics.kpi_breakdown(df, 'Attrition (Voluntary Leavers) Rate (%)', 'Department'))

    def test_dept_comparison(self):
        result = analytics.dept_comparison(_staff(), ['IT', 'Sales'], 'Attrition (Voluntary Leavers) Rate (%)')
        assert result['IT'] == 75.0
        assert result['Sales'] == 0.0

    def test_monthly_series_counts_voluntary_exits_only(self):
        series = analytics.time_series_data(
            _staff(), 'Monthly Attrition (Voluntary Leavers) Rate (%)', 'None', 'All',
            pd.Timestamp('2026-01-01'), pd.Timestamp('2026-03-31'), 'Monthly',
        )
        # Jan: 1 resigned, Feb: 1 resigned + 1 retired, Mar: termination only.
        assert list(series) == [12.5, 25.0, 0.0]


# ── Period formatting ─────────────────────────────────────────────────────

def test_format_period():
    assert analytics.format_period('2015-01-01', '2026-10-09') == '1 Jan 2015 – 9 Oct 2026'


# ── Readable labels ───────────────────────────────────────────────────────

def test_cleaner_keeps_role_acronyms():
    from core import data_cleaner
    df = pd.DataFrame({'Job_Role': ['hr coordinator', 'IT Manager', 'cmo', 'Senior AE'],
                       'Department': ['human resources', 'it', 'marketing', 'sales']})
    out = data_cleaner._normalise_text_fields(df)
    assert list(out['Job_Role']) == ['HR Coordinator', 'IT Manager', 'CMO', 'Senior AE']
    assert out['Department'][1] == 'IT'


def test_age_group_breakdown_in_natural_order():
    df = pd.DataFrame({'Age_Group': ['50–59', 'Under 30', '30–39', '40–49', 'Under 30'],
                       'Status': ['Active'] * 5, 'Turnover': [False] * 5})
    result = analytics.kpi_breakdown(df, 'Total Employees', 'Age Group')
    assert list(result.index) == ['Under 30', '30–39', '40–49', '50–59']


# ── Period filter ─────────────────────────────────────────────────────────

def _period_staff() -> pd.DataFrame:
    df = pd.DataFrame({
        'Name':      ['Long-serving', 'Left 2019', 'Left in period', 'Left after period', 'New hire'],
        'Status':    ['Active', 'Resigned', 'Resigned', 'Resigned', 'Active'],
        'Hire_Date': pd.to_datetime(['2015-03-01', '2016-01-01', '2018-05-01', '2019-06-01', '2025-04-01']),
        'End_Date':  pd.to_datetime([None, '2019-02-01', '2025-06-01', '2026-03-01', None]),
    })
    df['Turnover'] = df['Status'].isin(['Resigned', 'Terminated', 'Retired'])
    df['Tenure_Years'] = 0.0
    return df


def test_employed_during_period_counts_everyone_working_then():
    out = analytics.filter_period(_period_staff(), '2025-01-01', '2025-12-31', analytics.PERIOD_EMPLOYED)
    assert sorted(out['Name']) == ['Left after period', 'Left in period', 'Long-serving', 'New hire']


def test_employed_during_period_treats_later_leavers_as_active():
    out = analytics.filter_period(_period_staff(), '2025-01-01', '2025-12-31').set_index('Name')
    assert out.loc['Left after period', 'Status'] == 'Active'
    assert not out.loc['Left after period', 'Turnover']
    assert out.loc['Left in period', 'Turnover']
    # Turnover for the period: 1 leaver out of 4 employed
    assert analytics.kpi_value(out.reset_index(), 'Overall Turnover Rate (%)') == '25.0%'


def test_hired_during_period_only_counts_new_hires():
    out = analytics.filter_period(_period_staff(), '2025-01-01', '2025-12-31', analytics.PERIOD_HIRED)
    assert list(out['Name']) == ['New hire']


def test_tenure_stops_at_end_date():
    from core import data_cleaner
    df = pd.DataFrame({'Name': ['A'], 'Department': ['Sales'], 'Job_Role': ['Rep'], 'Status': ['Resigned'],
                       'Hire_Date': pd.to_datetime(['2010-01-01']), 'End_Date': pd.to_datetime(['2012-01-01']),
                       'Salary': [50000]})
    out = data_cleaner.clean(df)
    out = out[0] if isinstance(out, tuple) else out
    assert out['Tenure_Years'].iloc[0] == 2.0
