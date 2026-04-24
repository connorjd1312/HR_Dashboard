# test_analytics.py
# Unit tests for the data cleaning and analytics modules.
# Run from the project root with: pytest tests/ -v
# These tests verify that the core logic works correctly in isolation,
# without needing to launch the UI or load a real file.

import pandas as pd
import pytest
from core.data_cleaner import clean
from core import analytics

# Minimal sample dataset used across all tests.
# 'Bob' appears twice to test deduplication.
SAMPLE = pd.DataFrame({
    'Name': ['Alice', 'Bob', 'Bob'],
    'Date_of_Birth': pd.to_datetime(['1990-01-01', '1985-06-15', '1985-06-15']),
    'Hire_Date': pd.to_datetime(['2020-01-01', '2019-03-01', '2019-03-01']),
    'Department': ['HR', 'Engineering', 'Engineering'],
    'Job_Role': ['Analyst', 'Engineer', 'Engineer'],
    'Status': ['Active', 'Resigned', 'Resigned'],
    'Salary': [60000, 80000, 80000],
    'Absenteeism_Days': [3, 5, 5],
    'Leave_Balance': [10, 8, 8],
    'End_Date': pd.to_datetime([None, '2022-01-01', '2022-01-01']),
})


def test_deduplication():
    """The duplicate Bob row should be removed, leaving exactly 2 records."""
    df = clean(SAMPLE)
    assert len(df) == 2


def test_derived_columns():
    """Cleaner must add Age, Tenure_Years, and Turnover columns."""
    df = clean(SAMPLE)
    assert 'Age' in df.columns
    assert 'Tenure_Years' in df.columns
    assert 'Turnover' in df.columns


def test_kpi_structure():
    """summary_kpis must return the expected keys with correct values."""
    df = clean(SAMPLE)
    kpis = analytics.summary_kpis(df)
    assert 'Total Employees' in kpis
    assert kpis['Total Employees'] == 2
    assert kpis['Active Employees'] == 1  # only Alice is Active


def test_turnover_flag():
    """Bob is Resigned, so his Turnover flag must be True."""
    df = clean(SAMPLE)
    assert df.loc[df['Name'] == 'Bob', 'Turnover'].values[0] == True


def test_dept_distribution():
    """Both departments from the sample must appear in the distribution."""
    df = clean(SAMPLE)
    dist = analytics.dept_distribution(df)
    assert 'HR' in dist.index
    assert 'Engineering' in dist.index
