# analytics.py
# Computes all HR metrics shown on the dashboard.
# Every function takes a cleaned DataFrame and returns a value ready for display.
# Filtering is applied before these functions are called, so they always
# operate on whatever subset the user has selected.

import pandas as pd


def summary_kpis(df: pd.DataFrame) -> dict:
    """Return the five headline KPI values shown as cards on the Dashboard tab."""
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
    """Return employee count per department, used for the bar chart on the Dashboard tab."""
    return df['Department'].value_counts()


def role_distribution(df: pd.DataFrame) -> pd.Series:
    """Return employee count per job role, used for the pie chart on the Charts tab."""
    return df['Job_Role'].value_counts()


def monthly_hires(df: pd.DataFrame) -> pd.Series:
    """
    Return the number of employees hired per month, used for the line chart on the Charts tab.
    Resamples by month-end ('ME') so gaps with zero hires are included.
    """
    return (
        df.set_index('Hire_Date')
        .resample('ME')['Name']
        .count()
        .rename('Hires')
    )


def turnover_by_dept(df: pd.DataFrame) -> pd.Series:
    """
    Return the turnover rate (%) for each department, used for the horizontal bar chart.
    Calculated as the proportion of employees in each department who have left.
    """
    return (
        df.groupby('Department')['Turnover']
        .mean()       # gives proportion who left (0.0 – 1.0)
        .mul(100)     # convert to percentage
        .round(1)
    )
