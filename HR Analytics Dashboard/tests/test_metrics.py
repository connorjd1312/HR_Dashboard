"""Unit tests for age, tenure, and turnover rate calculations"""

import pytest
import pandas as pd
import numpy as np
from datetime import date
from core.data_cleaner import clean


def test_employee_age_calculation():
    """Employee age should be calculated correctly from Date_of_Birth."""
    today = pd.Timestamp(date.today())

    df = pd.DataFrame({
        'Name': ['Alice', 'Bob', 'Charlie'],
        'Hire_Date': pd.to_datetime(['2020-01-01', '2015-01-01', '2018-06-15']),
        'Department': ['Eng', 'Sales', 'HR'],
        'Date_of_Birth': [
            today - pd.Timedelta(days=365*25),  # 25 years old
            today - pd.Timedelta(days=365*40),  # 40 years old
            today - pd.Timedelta(days=365*35 + 100),  # ~35 years old
        ],
    })

    result = clean(df)

    assert result.loc[0, 'Age'] == 25
    assert result.loc[1, 'Age'] == 40
    assert result.loc[2, 'Age'] == 35


def test_employee_tenure_calculation():
    """Employee tenure should be calculated correctly from Hire_Date."""
    today = pd.Timestamp(date.today())

    df = pd.DataFrame({
        'Name': ['Alice', 'Bob', 'Charlie'],
        'Hire_Date': [
            today - pd.Timedelta(days=365*2),    # 2 years
            today - pd.Timedelta(days=365*5 + 100),  # ~5.27 years
            today - pd.Timedelta(days=180),      # ~0.49 years
        ],
        'Department': ['Eng', 'Sales', 'HR'],
    })

    result = clean(df)

    assert result.loc[0, 'Tenure_Years'] == pytest.approx(2.0, abs=0.1)
    assert result.loc[1, 'Tenure_Years'] == pytest.approx(5.3, abs=0.1)
    assert result.loc[2, 'Tenure_Years'] == pytest.approx(0.5, abs=0.1)


def test_turnover_rate_calculation():
    """Turnover rate should be calculated as percentage of employees who left."""
    df = pd.DataFrame({
        'Name': ['Alice', 'Bob', 'Charlie', 'Diana'],
        'Hire_Date': pd.to_datetime(['2020-01-01', '2015-01-01', '2018-06-15', '2019-03-20']),
        'Department': ['Eng', 'Sales', 'HR', 'Eng'],
        'Status': ['Active', 'Resigned', 'Terminated', 'Active'],
    })

    result = clean(df)

    # 2 out of 4 employees have left (Resigned or Terminated) = 50% turnover
    turnover_rate = result['Turnover'].mean() * 100
    assert turnover_rate == 50.0
    assert result.loc[0, 'Turnover'] == False  # Active
    assert result.loc[1, 'Turnover'] == True   # Resigned
    assert result.loc[2, 'Turnover'] == True   # Terminated
    assert result.loc[3, 'Turnover'] == False  # Active


def test_age_group_assignment():
    """Employees should be assigned correct age groups."""
    today = pd.Timestamp(date.today())

    df = pd.DataFrame({
        'Name': ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve'],
        'Hire_Date': pd.to_datetime(['2020-01-01'] * 5),
        'Department': ['Eng'] * 5,
        'Date_of_Birth': [
            today - pd.Timedelta(days=365*25),  # 25 → Under 30
            today - pd.Timedelta(days=365*35),  # 35 → 30–39
            today - pd.Timedelta(days=365*45),  # 45 → 40–49
            today - pd.Timedelta(days=365*55),  # 55 → 50–59
            today - pd.Timedelta(days=365*65),  # 65 → 60+
        ],
    })

    result = clean(df)

    assert result.loc[0, 'Age_Group'] == 'Under 30'
    assert result.loc[1, 'Age_Group'] == '30–39'
    assert result.loc[2, 'Age_Group'] == '40–49'
    assert result.loc[3, 'Age_Group'] == '50–59'
    assert result.loc[4, 'Age_Group'] == '60+'
