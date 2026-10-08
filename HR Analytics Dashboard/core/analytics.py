# analytics.py
# Computes all HR metrics shown on the dashboard.
# Every function takes a cleaned DataFrame and returns a value ready for display.
# Filtering is applied before these functions are called, so they always
# operate on whatever subset the user has selected.

from __future__ import annotations

import pandas as pd

# ── Constants used by the analytics builder 

TIME_RANGES = {
    'Last 6 Months': 6,
    'Last 1 Year':   12,

    'Last 2 Years':  24,
    'Last 3 Years':  36,
    'All Time':      None,
}

TIME_SERIES_METRICS = [
    'Hires',
    'Departures',
    'Turnover Rate per Period (%)',
    'Attrition (Voluntary Leavers) Rate per Period (%)',
]

SNAPSHOT_METRICS = [
    'Total Employees',
    'Overall Turnover Rate (%)',
    'Attrition (Voluntary Leavers) Rate (%)',
    'Average Salary ($)',
    'Average Tenure (yrs)',
    'Average Age',
    'Average Absenteeism (days)',
    'Average Leave Balance (days)',
]

GROUP_BY_OPTIONS = ['Department', 'Job Role', 'Status', 'Sex', 'Ethnicity', 'Age Group']

_COL_MAP = {
    'Department': 'Department',
    'Job Role':   'Job_Role',
    'Status':     'Status',
    'Sex':        'Sex',
    'Ethnicity':  'Ethnicity',
    'Age Group':  'Age_Group',
}

GRANULARITIES = ['Weekly', 'Monthly', 'Quarterly', 'Yearly']

# Attrition only counts employees who chose to leave (voluntary exits).
# Overall turnover also includes terminations.
ATTRITION_STATUSES = ['Resigned', 'Retired']

_FREQ_MAP = {
    'Weekly':    'W',
    'Monthly':   'ME',
    'Quarterly': 'QE',
    'Yearly':    'YE',
}

# Dashboard customisation constants 

# All KPI metrics available for the cards on the dashboard
KPI_OPTIONS = [
    'Total Employees',
    'Active Employees',
    'Overall Turnover Rate (%)',
    'Attrition (Voluntary Leavers) Rate (%)',
    'Average Tenure (yrs)',
    'Average Salary ($)',
    'Average Age',
    'Average Absenteeism (days)',
    'Average Leave Balance (days)',
    'On Leave Count',
    'Resigned Count',
]

# KPI cards shown by default when the dashboard first loads
DEFAULT_KPIS = [
    'Total Employees',
    'Active Employees',
    'Overall Turnover Rate (%)',
    'Attrition (Voluntary Leavers) Rate (%)',
    'Average Tenure (yrs)',
    'Average Salary ($)',
]

# Plain-English explanation of each metric, shown in tooltips and dialogs so
# users know exactly what a number means and how it's worked out.
METRIC_DESCRIPTIONS = {
    'Total Employees':
        'Number of employees in the selected period (or in each group), including people who have left.',
    'Active Employees':
        'Employees whose status is Active (excludes people on leave and leavers).',
    'On Leave Count':
        'Employees whose status is On Leave.',
    'Resigned Count':
        'Employees whose status is Resigned.',
    'Overall Turnover Rate (%)':
        'Share of employees who have left for any reason (resigned, terminated or retired).',
    'Attrition (Voluntary Leavers) Rate (%)':
        'Share of employees who chose to leave (resigned or retired). Unlike overall turnover, '
        'it does not count terminations.',
    'Average Tenure (yrs)':
        'Average years of service — up to today, or up to their leaving date for people who left.',
    'Average Salary ($)':
        'Average annual salary.',
    'Average Age':
        'Average age in years, from date of birth.',
    'Average Absenteeism (days)':
        'Average number of days absent per employee.',
    'Average Leave Balance (days)':
        'Average number of leave days each employee has remaining.',
    'Hires':
        'Number of people hired in each period (week, month, quarter or year).',
    'Departures':
        'Number of people who left in each period, for any reason.',
    'Turnover Rate per Period (%)':
        'People who left in each period as a share of all employees.',
    'Attrition (Voluntary Leavers) Rate per Period (%)':
        'People who resigned or retired in each period as a share of all employees.',
}


# Earlier versions used different names for some metrics; saved chart setups
# may still contain them.
LEGACY_METRIC_NAMES = {
    'Employee Count': 'Total Employees',
    'Avg Tenure (yrs)': 'Average Tenure (yrs)',
    'Avg Salary ($)': 'Average Salary ($)',
    'Avg Absenteeism Days': 'Average Absenteeism (days)',
    'Avg Leave Balance': 'Average Leave Balance (days)',
    'Hires per Month': 'Hires',
    'Departures per Month': 'Departures',
    'Monthly Turnover Rate (%)': 'Turnover Rate per Period (%)',
    'Monthly Attrition (Voluntary Leavers) Rate (%)': 'Attrition (Voluntary Leavers) Rate per Period (%)',
}


def canonical_metric(metric: str) -> str:
    # Current name for a metric, translating any older name.
    return LEGACY_METRIC_NAMES.get(metric, metric)


def describe_metric(metric: str) -> str:
    return METRIC_DESCRIPTIONS.get(metric, '')


CHART_TYPES = ['Auto', 'Vertical Bar', 'Horizontal Bar', 'Pie', 'Donut', 'Line']

# Metrics whose category values sum to a meaningful whole (so a pie/donut is
# defensible). Average/rate metrics are NOT parts-of-a-whole and must never
# use Pie/Donut — averaging across slices is misleading.
PARTS_OF_WHOLE_METRICS = [
    'Total Employees',
    'Active Employees',
    'On Leave Count',
    'Resigned Count',
]

# Dimensions that have a natural order — never split these into a pie, where
# ordering is lost.
ORDERED_DIMENSIONS = ['Age Group']

# Display order for the Age Group buckets created in data_cleaner.clean()
AGE_GROUP_ORDER = ['Under 30', '30–39', '40–49', '50–59', '60+', 'Unknown']

# Chart-type recommender thresholds (named so they're easy to tune).
_MAX_PIE_CATEGORIES = 5   # pie/donut only when categories ≤ this
_MAX_VERTICAL_BARS  = 6   # above this, switch to horizontal bars for readability

# Order used when cascading drill-downs through dimensions
DRILL_CASCADE = ['Department', 'Job Role', 'Status', 'Sex', 'Ethnicity', 'Age Group']


# How the dashboard's date range selects employees
PERIOD_EMPLOYED = 'Employed during period'
PERIOD_HIRED = 'Hired during period'
PERIOD_MODES = [PERIOD_EMPLOYED, PERIOD_HIRED]

_LEFT_STATUSES = ['Resigned', 'Terminated', 'Retired']


def filter_period(df: pd.DataFrame, start, end, mode: str = PERIOD_EMPLOYED) -> pd.DataFrame:
    # Select the employees the dashboard should count for a date range.
    #
    # 'Employed during period' (default): everyone who worked here at any point in
    # the range — hired on/before the end and not left before the start. Figures
    # are 'as at' the end of the range: anyone who left AFTER it was still
    # employed then, so they count as active, not as a leaver.
    #
    # 'Hired during period': only people whose hire date falls in the range.
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if mode == PERIOD_HIRED:
        return df[(df['Hire_Date'] >= start) & (df['Hire_Date'] <= end)]

    ended = df['End_Date'] if 'End_Date' in df.columns else pd.Series(pd.NaT, index=df.index)
    out = df[(df['Hire_Date'] <= end) & (ended.isna() | (ended >= start))].copy()
    if 'End_Date' not in out.columns:
        return out

    left_later = out['End_Date'] > end
    if left_later.any():
        out.loc[left_later, 'Status'] = 'Active'
        out.loc[left_later, 'Turnover'] = False
        out.loc[left_later, 'End_Date'] = pd.NaT
    if 'Tenure_Years' in out.columns:
        tenure_end = out['End_Date'].fillna(min(end, pd.Timestamp.today().normalize()))
        out['Tenure_Years'] = ((tenure_end - out['Hire_Date']).dt.days / 365).round(1)
    return out


def previous_period(start, end) -> tuple[pd.Timestamp, pd.Timestamp]:
    # The same-length period immediately before [start, end].
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    return start - (end - start) - pd.Timedelta(days=1), start - pd.Timedelta(days=1)


def kpi_number(df: pd.DataFrame, metric: str) -> float | None:
    # Numeric value of a KPI card (kpi_value without the formatting).
    text = kpi_value(df, metric)
    if text in (None, '—'):
        return None
    try:
        return float(text.replace('$', '').replace('%', '').replace(',', ''))
    except ValueError:
        return None


# Which way is good news for each KPI: +1 higher is better, -1 lower is better.
# Anything not listed (headcount, salary, age, leave) is shown in neutral grey.
_KPI_GOOD_DIRECTION = {
    'Overall Turnover Rate (%)': -1,
    'Attrition (Voluntary Leavers) Rate (%)': -1,
    'Resigned Count': -1,
    'Average Absenteeism (days)': -1,
    'Average Tenure (yrs)': +1,
}


def kpi_change(metric: str, current: float | None, previous: float | None) -> tuple[str, str] | None:
    # ('▲ 3.2 pts', 'good' | 'bad' | 'neutral') comparing a KPI with the previous period.
    if current is None or previous is None:
        return None
    diff = current - previous
    if abs(diff) < 0.05:
        return '→ no change', 'neutral'
    arrow = '▲' if diff > 0 else '▼'
    if '%' in metric:
        amount = f'{abs(diff):.1f} pts'
    elif '$' in metric:
        amount = f'${abs(diff):,.0f}'
    elif float(abs(diff)).is_integer():
        amount = f'{abs(diff):,.0f}'
    else:
        amount = f'{abs(diff):.1f}'
    good = _KPI_GOOD_DIRECTION.get(metric)
    tone = 'neutral' if good is None else ('good' if diff * good > 0 else 'bad')
    return f'{arrow} {amount}', tone


def format_date(d) -> str:
    # Human-readable date, e.g. '9 Oct 2026'.
    d = pd.Timestamp(d)
    return f'{d.day} {d:%b %Y}'


def format_period(start, end) -> str:
    # Human-readable date range, e.g. '1 Jan 2015 – 9 Oct 2026'.
    return f'{format_date(start)} – {format_date(end)}'


def format_metric_value(metric: str, val: float) -> str:
    # Compact display value for chart labels, e.g. '23.2%', '$86,754', '27'.
    if '%' in metric:
        return f'{val:.1f}%'
    if '$' in metric or 'Salary' in metric:
        return f'${val:,.0f}'
    if float(val).is_integer():
        return f'{int(val):,}'
    return f'{val:.1f}'


def _attrition_flag(df: pd.DataFrame) -> pd.Series:
    # True for employees who left voluntarily (resigned or retired).
    return df['Status'].isin(ATTRITION_STATUSES)


def kpi_value(df: pd.DataFrame, metric: str) -> str:
    # Return formatted display string for a KPI on a dashboard card.
    if df is None or len(df) == 0:
        return '—'

    if metric == 'Total Employees':
        return f'{len(df):,}'
    if metric == 'Active Employees':
        return f'{int((df["Status"] == "Active").sum()):,}'
    if metric == 'On Leave Count':
        return f'{int((df["Status"] == "On Leave").sum()):,}'
    if metric == 'Resigned Count':
        return f'{int((df["Status"] == "Resigned").sum()):,}'
    if metric == 'Overall Turnover Rate (%)':
        return f'{df["Turnover"].mean() * 100:.1f}%'
    if metric == 'Attrition (Voluntary Leavers) Rate (%)':
        return f'{_attrition_flag(df).mean() * 100:.1f}%'
    if metric == 'Average Tenure (yrs)':
        v = df['Tenure_Years'].mean()
        return f'{v:.1f}' if pd.notna(v) else '—'
    if metric == 'Average Salary ($)':
        v = df['Salary'].mean()
        return f'${v:,.0f}' if pd.notna(v) else '—'
    if metric == 'Average Age':
        if 'Age' not in df.columns:
            return '—'
        v = df['Age'].dropna().mean()
        return f'{v:.1f}' if pd.notna(v) else '—'
    if metric == 'Average Absenteeism (days)':
        if 'Absenteeism_Days' not in df.columns:
            return '—'
        return f'{df["Absenteeism_Days"].mean():.1f}'
    if metric == 'Average Leave Balance (days)':
        if 'Leave_Balance' not in df.columns:
            return '—'
        return f'{df["Leave_Balance"].mean():.1f}'
    return '—'


def kpi_relevant_employees(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    # Return employees contributing to this KPI; count metrics filter to matching rows only.
    if df is None or len(df) == 0:
        return df

    if metric == 'Active Employees':
        return df[df['Status'] == 'Active']
    if metric == 'On Leave Count':
        return df[df['Status'] == 'On Leave']
    if metric == 'Resigned Count':
        return df[df['Status'] == 'Resigned']
    if metric == 'Overall Turnover Rate (%)':
        return df[df['Turnover'] == True]
    if metric == 'Attrition (Voluntary Leavers) Rate (%)':
        return df[_attrition_flag(df)]
    return df


def _in_natural_order(result: pd.Series, group_by: str) -> pd.Series:
    # groupby sorts alphabetically ('30–39' before 'Under 30'); put age buckets
    # back in youngest-to-oldest order.
    if group_by != 'Age Group' or result.empty:
        return result
    order = [g for g in AGE_GROUP_ORDER if g in result.index]
    order += [g for g in result.index if g not in order]
    return result.reindex(order)


def kpi_breakdown(df: pd.DataFrame, metric: str, group_by: str) -> pd.Series:
    # Return a per-group Series for a KPI metric, used in drill-down breakdown charts.
    return _in_natural_order(_kpi_breakdown(df, metric, group_by), group_by)


def _kpi_breakdown(df: pd.DataFrame, metric: str, group_by: str) -> pd.Series:
    col = _COL_MAP.get(group_by, group_by)
    if df is None or col not in df.columns or len(df) == 0:
        return pd.Series(dtype=float)

    if metric == 'Total Employees':
        return df.groupby(col).size().rename('Value')
    if metric == 'Active Employees':
        return df.groupby(col).apply(
            lambda g: int((g['Status'] == 'Active').sum())
        ).rename('Value')
    if metric == 'On Leave Count':
        return df.groupby(col).apply(
            lambda g: int((g['Status'] == 'On Leave').sum())
        ).rename('Value')
    if metric == 'Resigned Count':
        return df.groupby(col).apply(
            lambda g: int((g['Status'] == 'Resigned').sum())
        ).rename('Value')
    if metric == 'Overall Turnover Rate (%)':
        return (df.groupby(col)['Turnover'].mean() * 100).round(1).rename('Value')
    if metric == 'Attrition (Voluntary Leavers) Rate (%)':
        return (_attrition_flag(df).groupby(df[col]).mean() * 100).round(1).rename('Value')
    if metric == 'Average Tenure (yrs)':
        return df.groupby(col)['Tenure_Years'].mean().round(1).rename('Value')
    if metric == 'Average Salary ($)':
        return df.groupby(col)['Salary'].mean().round(0).rename('Value')
    if metric == 'Average Age':
        if 'Age' not in df.columns:
            return pd.Series(dtype=float)
        return df.groupby(col)['Age'].mean().round(1).rename('Value')
    if metric == 'Average Absenteeism (days)':
        if 'Absenteeism_Days' not in df.columns:
            return pd.Series(dtype=float)
        return df.groupby(col)['Absenteeism_Days'].mean().round(1).rename('Value')
    if metric == 'Average Leave Balance (days)':
        if 'Leave_Balance' not in df.columns:
            return pd.Series(dtype=float)
        return df.groupby(col)['Leave_Balance'].mean().round(1).rename('Value')
    return pd.Series(dtype=float)


def summary_kpis(df: pd.DataFrame) -> dict:
    # Return the five headline KPI values shown as cards on the Dashboard tab.
    total = len(df)
    active = int((df['Status'] == 'Active').sum())

    # Turnover rate = number of employees who left / total employees * 100
    turnover_rate = round(df['Turnover'].sum() / total * 100, 1) if total else 0.0

    avg_tenure = round(df['Tenure_Years'].mean(), 1)
    avg_salary = df['Salary'].mean()

    return {
        'Total Employees': total,
        'Active Employees': active,
        'Overall Turnover Rate (%)': turnover_rate,
        'Average Tenure (yrs)': avg_tenure,
        'Average Salary ($)': f'{avg_salary:,.0f}',  # formatted with commas, no decimals
    }


def dept_distribution(df: pd.DataFrame) -> pd.Series:
    # Return employee count per department, used for the bar chart on the Dashboard tab.
    return df['Department'].value_counts()


def role_distribution(df: pd.DataFrame) -> pd.Series:
    # Return employee count per job role, used for the pie chart on the Charts tab.
    return df['Job_Role'].value_counts()


def monthly_hires(df: pd.DataFrame) -> pd.Series:
    # Return hires per month (resampled to month-end so zero-hire gaps are included).
    return (
        df.set_index('Hire_Date')
        .resample('ME')['Name']
        .count()
        .rename('Hires')
    )


def turnover_by_dept(df: pd.DataFrame) -> pd.Series:
    # Return turnover rate (%) per department — proportion of employees who have left.
    return (
        df.groupby('Department')['Turnover']
        .mean()       # gives proportion who left (0.0 – 1.0)
        .mul(100)     # convert to percentage
        .round(1)
    )


COMPARISON_METRICS = [
    'Total Employees',
    'Overall Turnover Rate (%)',
    'Attrition (Voluntary Leavers) Rate (%)',
    'Average Salary ($)',
    'Average Tenure (yrs)',
    'Average Age',
    'Average Absenteeism (days)',
    'Average Leave Balance (days)',
]


def dept_comparison(df: pd.DataFrame, departments: list, metric: str) -> pd.Series:
    # Return a Series of metric values indexed by department for the given selection.
    result = {}
    for dept in departments:
        sub = df[df['Department'] == dept]
        if len(sub) == 0:
            result[dept] = 0.0
            continue
        if metric == 'Total Employees':
            result[dept] = float(len(sub))
        elif metric == 'Overall Turnover Rate (%)':
            result[dept] = round(float(sub['Turnover'].mean() * 100), 1)
        elif metric == 'Attrition (Voluntary Leavers) Rate (%)':
            result[dept] = round(float(_attrition_flag(sub).mean() * 100), 1)
        elif metric == 'Average Salary ($)':
            result[dept] = round(float(sub['Salary'].mean()), 0)
        elif metric == 'Average Tenure (yrs)':
            result[dept] = round(float(sub['Tenure_Years'].mean()), 1)
        elif metric == 'Average Absenteeism (days)':
            col = 'Absenteeism_Days'
            result[dept] = round(float(sub[col].mean()), 1) if col in df.columns else 0.0
        elif metric == 'Average Leave Balance (days)':
            col = 'Leave_Balance'
            result[dept] = round(float(sub[col].mean()), 1) if col in df.columns else 0.0
        elif metric == 'Average Age':
            col = 'Age'
            result[dept] = round(float(sub[col].mean()), 1) if col in df.columns else 0.0
        else:
            result[dept] = 0.0
    return pd.Series(result)


def salary_by_dept(df: pd.DataFrame) -> pd.Series:
    # Return average salary per department, used for the salary bar chart.
    return df.groupby('Department')['Salary'].mean().round(0)


def avg_absenteeism_by_dept(df: pd.DataFrame) -> pd.Series:
    # Return average absenteeism days per department.
    if 'Absenteeism_Days' not in df.columns:
        return pd.Series(dtype=float)
    return df.groupby('Department')['Absenteeism_Days'].mean().round(1)


def leave_balance_by_dept(df: pd.DataFrame) -> pd.Series:
    # Return average leave balance days per department.
    if 'Leave_Balance' not in df.columns:
        return pd.Series(dtype=float)
    return df.groupby('Department')['Leave_Balance'].mean().round(1)


# Analytics builder functions 

def time_series_data(
    df: pd.DataFrame,
    metric: str,
    filter_by: str,
    filter_val: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    granularity: str = 'Monthly',
) -> pd.Series:
    # Compute a time series for one metric over the given date range and granularity.
    if filter_by and filter_by != 'None' and filter_val and filter_val != 'All':
        col = _COL_MAP.get(filter_by, filter_by)
        df = df[df[col] == filter_val]

    freq = _FREQ_MAP.get(granularity, 'ME')

    if metric == 'Hires':
        mask = df['Hire_Date'] >= start_date
        raw = df[mask].set_index('Hire_Date').resample(freq)['Name'].count()
    elif metric == 'Departures':
        sub = df[df['End_Date'].notna()]
        mask = sub['End_Date'] >= start_date
        raw = sub[mask].set_index('End_Date').resample(freq)['Name'].count()
    elif metric == 'Turnover Rate per Period (%)':
        total = max(len(df), 1)
        sub = df[df['End_Date'].notna()]
        mask = sub['End_Date'] >= start_date
        counts = sub[mask].set_index('End_Date').resample(freq)['Name'].count()
        raw = (counts / total * 100).round(2)
    elif metric == 'Attrition (Voluntary Leavers) Rate per Period (%)':
        total = max(len(df), 1)
        sub = df[df['End_Date'].notna() & _attrition_flag(df)]
        mask = sub['End_Date'] >= start_date
        counts = sub[mask].set_index('End_Date').resample(freq)['Name'].count()
        raw = (counts / total * 100).round(2)
    else:
        return pd.Series(dtype=float)

    date_range = pd.date_range(start=start_date, end=end_date, freq=freq)
    return raw.reindex(date_range, fill_value=0).rename('Value')


def snapshot_data(df: pd.DataFrame, metric: str, group_by: str) -> pd.Series:
    # Compute a snapshot metric grouped by one dimension.
    return _in_natural_order(_snapshot_data(df, metric, group_by), group_by)


def _snapshot_data(df: pd.DataFrame, metric: str, group_by: str) -> pd.Series:
    col = _COL_MAP.get(group_by, group_by)

    if metric == 'Total Employees':
        return df.groupby(col).size().rename('Value')
    elif metric == 'Overall Turnover Rate (%)':
        return (df.groupby(col)['Turnover'].mean() * 100).round(1).rename('Value')
    elif metric == 'Attrition (Voluntary Leavers) Rate (%)':
        return (_attrition_flag(df).groupby(df[col]).mean() * 100).round(1).rename('Value')
    elif metric == 'Average Salary ($)':
        return df.groupby(col)['Salary'].mean().round(0).rename('Value')
    elif metric == 'Average Tenure (yrs)':
        return df.groupby(col)['Tenure_Years'].mean().round(1).rename('Value')
    elif metric == 'Average Absenteeism (days)':
        if 'Absenteeism_Days' not in df.columns:
            return pd.Series(dtype=float)
        return df.groupby(col)['Absenteeism_Days'].mean().round(1).rename('Value')
    elif metric == 'Average Leave Balance (days)':
        if 'Leave_Balance' not in df.columns:
            return pd.Series(dtype=float)
        return df.groupby(col)['Leave_Balance'].mean().round(1).rename('Value')
    elif metric == 'Average Age':
        if 'Age' not in df.columns:
            return pd.Series(dtype=float)
        return df.groupby(col)['Age'].mean().round(1).rename('Value')
    return pd.Series(dtype=float)


def recommend_chart_type(metric: str, group_by: str, data: pd.Series) -> str:
    # Pick the best concrete chart type for a snapshot Series.
    # Always returns a value in CHART_TYPES and never 'Auto'.
    #
    # Signals: metric type (parts-of-whole vs average/rate), dimension
    # (ordered vs categorical), category count, and data shape.
    n = 0 if data is None else len(data)

    # Empty / single category — nothing to compare, use the safe default.
    if n <= 1:
        return 'Vertical Bar'

    # Ordered buckets (e.g. Age Group) must keep their order → vertical bars.
    if group_by in ORDERED_DIMENSIONS:
        return 'Vertical Bar' if n <= _MAX_VERTICAL_BARS else 'Horizontal Bar'

    # Parts-of-a-whole counts with few categories read well as a pie.
    if metric in PARTS_OF_WHOLE_METRICS and n <= _MAX_PIE_CATEGORIES:
        return 'Pie'

    # Everything else is a bar; orientation depends on how many categories
    # there are (many long labels are more readable horizontally).
    return 'Vertical Bar' if n <= _MAX_VERTICAL_BARS else 'Horizontal Bar'
