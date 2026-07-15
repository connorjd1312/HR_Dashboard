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
    'Hires per Month',
    'Departures per Month',
    'Monthly Turnover Rate (%)',
]

SNAPSHOT_METRICS = [
    'Employee Count',
    'Turnover Rate (%)',
    'Average Salary ($)',
    'Average Tenure (yrs)',
    'Average Age',
    'Avg Absenteeism Days',
    'Avg Leave Balance',
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
    'Turnover Rate (%)',
    'Avg Tenure (yrs)',
    'Avg Salary ($)',
    'Average Age',
    'Avg Absenteeism Days',
    'Avg Leave Balance',
    'On Leave Count',
    'Resigned Count',
]

# KPI cards shown by default when the dashboard first loads
DEFAULT_KPIS = [
    'Total Employees',
    'Active Employees',
    'Turnover Rate (%)',
    'Avg Tenure (yrs)',
    'Avg Salary ($)',
]

CHART_TYPES = ['Auto', 'Vertical Bar', 'Horizontal Bar', 'Pie', 'Donut', 'Line']

# Metrics whose category values sum to a meaningful whole (so a pie/donut is
# defensible). Average/rate metrics are NOT parts-of-a-whole and must never
# use Pie/Donut — averaging across slices is misleading. Covers both the
# snapshot metric ('Employee Count') and the count-type KPI/drill-down metrics.
PARTS_OF_WHOLE_METRICS = [
    'Employee Count',
    'Total Employees',
    'Active Employees',
    'On Leave Count',
    'Resigned Count',
]

# Dimensions that have a natural order — never split these into a pie, where
# ordering is lost.
ORDERED_DIMENSIONS = ['Age Group']

# Chart-type recommender thresholds (named so they're easy to tune).
_MAX_PIE_CATEGORIES = 5   # pie/donut only when categories ≤ this
_MAX_VERTICAL_BARS  = 6   # above this, switch to horizontal bars for readability

# Order used when cascading drill-downs through dimensions
DRILL_CASCADE = ['Department', 'Job Role', 'Status', 'Sex', 'Ethnicity', 'Age Group']


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
    if metric == 'Turnover Rate (%)':
        return f'{df["Turnover"].mean() * 100:.1f}%'
    if metric == 'Avg Tenure (yrs)':
        v = df['Tenure_Years'].mean()
        return f'{v:.1f}' if pd.notna(v) else '—'
    if metric == 'Avg Salary ($)':
        v = df['Salary'].mean()
        return f'${v:,.0f}' if pd.notna(v) else '—'
    if metric == 'Average Age':
        if 'Age' not in df.columns:
            return '—'
        v = df['Age'].dropna().mean()
        return f'{v:.1f}' if pd.notna(v) else '—'
    if metric == 'Avg Absenteeism Days':
        if 'Absenteeism_Days' not in df.columns:
            return '—'
        return f'{df["Absenteeism_Days"].mean():.1f}'
    if metric == 'Avg Leave Balance':
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
    if metric == 'Turnover Rate (%)':
        return df[df['Turnover'] == True]
    return df


def kpi_breakdown(df: pd.DataFrame, metric: str, group_by: str) -> pd.Series:
    # Return a per-group Series for a KPI metric, used in drill-down breakdown charts.
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
    if metric == 'Turnover Rate (%)':
        return (df.groupby(col)['Turnover'].mean() * 100).round(1).rename('Value')
    if metric == 'Avg Tenure (yrs)':
        return df.groupby(col)['Tenure_Years'].mean().round(1).rename('Value')
    if metric == 'Avg Salary ($)':
        return df.groupby(col)['Salary'].mean().round(0).rename('Value')
    if metric == 'Average Age':
        if 'Age' not in df.columns:
            return pd.Series(dtype=float)
        return df.groupby(col)['Age'].mean().round(1).rename('Value')
    if metric == 'Avg Absenteeism Days':
        if 'Absenteeism_Days' not in df.columns:
            return pd.Series(dtype=float)
        return df.groupby(col)['Absenteeism_Days'].mean().round(1).rename('Value')
    if metric == 'Avg Leave Balance':
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
        'Turnover Rate (%)': turnover_rate,
        'Avg Tenure (yrs)': avg_tenure,
        'Avg Salary ($)': f'{avg_salary:,.0f}',  # formatted with commas, no decimals
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
    'Employee Count',
    'Turnover Rate (%)',
    'Average Salary ($)',
    'Average Tenure (yrs)',
    'Average Age',
    'Avg Absenteeism Days',
    'Avg Leave Balance',
]


def dept_comparison(df: pd.DataFrame, departments: list, metric: str) -> pd.Series:
    # Return a Series of metric values indexed by department for the given selection.
    result = {}
    for dept in departments:
        sub = df[df['Department'] == dept]
        if len(sub) == 0:
            result[dept] = 0.0
            continue
        if metric == 'Employee Count':
            result[dept] = float(len(sub))
        elif metric == 'Turnover Rate (%)':
            result[dept] = round(float(sub['Turnover'].mean() * 100), 1)
        elif metric == 'Average Salary ($)':
            result[dept] = round(float(sub['Salary'].mean()), 0)
        elif metric == 'Average Tenure (yrs)':
            result[dept] = round(float(sub['Tenure_Years'].mean()), 1)
        elif metric == 'Avg Absenteeism Days':
            col = 'Absenteeism_Days'
            result[dept] = round(float(sub[col].mean()), 1) if col in df.columns else 0.0
        elif metric == 'Avg Leave Balance':
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

    if metric == 'Hires per Month':
        mask = df['Hire_Date'] >= start_date
        raw = df[mask].set_index('Hire_Date').resample(freq)['Name'].count()
    elif metric == 'Departures per Month':
        sub = df[df['End_Date'].notna()]
        mask = sub['End_Date'] >= start_date
        raw = sub[mask].set_index('End_Date').resample(freq)['Name'].count()
    elif metric == 'Monthly Turnover Rate (%)':
        total = max(len(df), 1)
        sub = df[df['End_Date'].notna()]
        mask = sub['End_Date'] >= start_date
        counts = sub[mask].set_index('End_Date').resample(freq)['Name'].count()
        raw = (counts / total * 100).round(2)
    else:
        return pd.Series(dtype=float)

    date_range = pd.date_range(start=start_date, end=end_date, freq=freq)
    return raw.reindex(date_range, fill_value=0).rename('Value')


def snapshot_data(df: pd.DataFrame, metric: str, group_by: str) -> pd.Series:
    # Compute a snapshot metric grouped by one dimension.
    col = _COL_MAP.get(group_by, group_by)

    if metric == 'Employee Count':
        return df.groupby(col).size().rename('Value')
    elif metric == 'Turnover Rate (%)':
        return (df.groupby(col)['Turnover'].mean() * 100).round(1).rename('Value')
    elif metric == 'Average Salary ($)':
        return df.groupby(col)['Salary'].mean().round(0).rename('Value')
    elif metric == 'Average Tenure (yrs)':
        return df.groupby(col)['Tenure_Years'].mean().round(1).rename('Value')
    elif metric == 'Avg Absenteeism Days':
        if 'Absenteeism_Days' not in df.columns:
            return pd.Series(dtype=float)
        return df.groupby(col)['Absenteeism_Days'].mean().round(1).rename('Value')
    elif metric == 'Avg Leave Balance':
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
