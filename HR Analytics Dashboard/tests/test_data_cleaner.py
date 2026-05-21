"""Unit tests for data_cleaner.py"""

import pytest
import pandas as pd
import numpy as np
from datetime import date
from core.data_cleaner import clean


# Test 1: Missing Values
def test_missing_values():
    """Missing values should be filled with defaults (median for Salary, 0 for others)."""
    df = pd.DataFrame({
        'Name': ['Alice', 'Bob'],
        'Hire_Date': pd.to_datetime(['2020-01-01', '2020-01-02']),
        'Department': ['Eng', 'Sales'],
        'Salary': [50000.0, np.nan],
        'Absenteeism_Days': [5.0, np.nan],
        'Leave_Balance': [10.0, np.nan],
    })

    result = clean(df)

    assert result.loc[1, 'Salary'] == 50000.0
    assert result.loc[1, 'Absenteeism_Days'] == 0.0
    assert result.loc[1, 'Leave_Balance'] == 0.0


# Test 2: Duplicates
def test_duplicates():
    """Duplicate rows should be removed."""
    df = pd.DataFrame({
        'Name': ['Alice', 'Bob', 'Alice'],
        'Hire_Date': pd.to_datetime(['2020-01-01', '2020-01-02', '2020-01-01']),
        'Department': ['Eng', 'Sales', 'Eng'],
        'Salary': [50000.0, 60000.0, 50000.0],
    })

    result = clean(df)

    assert len(result) == 2
    assert result['Name'].tolist() == ['Alice', 'Bob']


# Test 3: Date Standardization
def test_dates():
    """Tenure_Years and Age should be computed from dates."""
    today = pd.Timestamp(date.today())

    df = pd.DataFrame({
        'Name': ['Alice'],
        'Hire_Date': [today - pd.Timedelta(days=365)],
        'Department': ['Eng'],
        'Date_of_Birth': [today - pd.Timedelta(days=365*30)],
    })

    result = clean(df)

    assert result.iloc[0]['Tenure_Years'] == pytest.approx(1.0, abs=0.1)
    assert result.iloc[0]['Age'] == 30
    assert result.iloc[0]['Age_Group'] == '30–39'


# Test 4: Status & Turnover
def test_status():
    """Status should be normalized and Turnover flag computed."""
    df = pd.DataFrame({
        'Name': ['Alice', 'Bob', 'Charlie'],
        'Hire_Date': pd.to_datetime(['2020-01-01', '2020-01-02', '2020-01-03']),
        'Department': ['Eng', 'Sales', 'HR'],
        'Status': ['active', 'RESIGNED', 'terminated'],
    })

    result = clean(df)

    assert result.iloc[0]['Status'] == 'Active'
    assert result.iloc[1]['Status'] == 'Resigned'
    assert result.iloc[2]['Status'] == 'Terminated'
    assert result.iloc[0]['Turnover'] == False
    assert result.iloc[1]['Turnover'] == True
    assert result.iloc[2]['Turnover'] == True


# Test 5: Full Cleaning
def test_full_cleaning():
    """Complete cleaning workflow."""
    df = pd.DataFrame({
        'Name': ['alice', 'bob', 'alice'],
        'Hire_Date': pd.to_datetime(['2020-01-01', '2015-01-01', '2020-01-01']),
        'Department': ['engineering', 'sales', 'engineering'],
        'Status': ['active', 'resigned', 'active'],
        'Salary': [50000.0, np.nan, 50000.0],
    })

    result = clean(df)

    assert len(result) == 2
    assert result['Salary'].notna().all()
    assert 'Tenure_Years' in result.columns
    assert 'Turnover' in result.columns
