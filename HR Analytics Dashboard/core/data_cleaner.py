# data_cleaner.py
# Cleans and enriches the normalised DataFrame produced by data_loader.py.
# Handles inconsistent status values, deduplication, missing data, and adds
# computed columns (Age, Tenure_Years, Turnover) used throughout the dashboard.

import pandas as pd
from datetime import date

# Maps known status variants to the four standard labels used across the app.
# Keys are lowercase so the comparison is case-insensitive.
STATUS_MAP = {
    'active':       'Active',
    'employed':     'Active',
    'current':      'Active',
    'permanent':    'Active',
    'full-time':    'Active',
    'part-time':    'Active',
    'resigned':     'Resigned',
    'resignation':  'Resigned',
    'quit':         'Resigned',
    'voluntary':    'Resigned',
    'terminated':   'Terminated',
    'termination':  'Terminated',
    'dismissed':    'Terminated',
    'fired':        'Terminated',
    'redundant':    'Terminated',
    'laid off':     'Terminated',
    'retired':      'Retired',
    'retirement':   'Retired',
    'on leave':     'On Leave',
    'leave':        'On Leave',
    'maternity':    'On Leave',
    'paternity':    'On Leave',
    'medical':      'On Leave',
}


def _normalise_status(df: pd.DataFrame) -> pd.DataFrame:
    """Map status variants to standard labels; unrecognised values become 'Unknown'."""
    if 'Status' not in df.columns:
        # Column wasn't in the source file at all — default everyone to Unknown
        df['Status'] = 'Unknown'
        return df

    df['Status'] = (
        df['Status']
        .astype(str)
        .str.strip()
        .str.lower()
        .map(STATUS_MAP)
        .fillna('Unknown')   # anything not matched in STATUS_MAP
    )
    return df


def _normalise_text_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing whitespace and apply consistent Title Casing to text columns."""
    for col in ['Name', 'Department', 'Job_Role']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and enrich the normalised HR DataFrame.
    Returns a new DataFrame — the original is never modified.

    Steps performed:
      1. Normalise text fields and status values
      2. Remove duplicate and incomplete rows
      3. Fill optional missing values with safe defaults
      4. Add computed columns: Age, Tenure_Years, Turnover
      5. Validate data integrity and warn about bad records
    """
    # Always work on a copy so the raw data stays intact for error diagnosis
    df = df.copy()

    # --- 1. Normalise text and status ---
    df = _normalise_text_fields(df)
    df = _normalise_status(df)

    # --- 2. Deduplication and required-field enforcement ---

    before = len(df)
    df.drop_duplicates(inplace=True)
    dupes_removed = before - len(df)
    if dupes_removed:
        print(f"Removed {dupes_removed} duplicate row(s).")

    # Drop rows missing the columns the whole dashboard depends on
    df.dropna(subset=['Name', 'Hire_Date', 'Department'], inplace=True)

    # --- 3. Fill optional missing values with safe defaults ---

    if 'Salary' in df.columns:
        # Median is used instead of mean to avoid distortion from executive-level outliers
        df['Salary'] = df['Salary'].fillna(df['Salary'].median())

    if 'Absenteeism_Days' in df.columns:
        df['Absenteeism_Days'] = df['Absenteeism_Days'].fillna(0)

    if 'Leave_Balance' in df.columns:
        df['Leave_Balance'] = df['Leave_Balance'].fillna(0)

    # --- 4. Derived / computed columns ---

    today = pd.Timestamp(date.today())

    # Age in whole years; will be NaN if Date_of_Birth was missing or unparseable
    if 'Date_of_Birth' in df.columns:
        df['Age'] = ((today - df['Date_of_Birth']).dt.days // 365).astype('Int64')

    # Tenure in decimal years from Hire_Date to today
    df['Tenure_Years'] = ((today - df['Hire_Date']).dt.days / 365).round(1)

    # Turnover flag — True for any status that means the employee has left
    df['Turnover'] = df['Status'].isin(['Resigned', 'Terminated', 'Retired'])

    # --- 5. Validation warnings ---

    # Hire date before date of birth is physically impossible — remove those rows
    if 'Date_of_Birth' in df.columns:
        invalid_dob = df['Hire_Date'] < df['Date_of_Birth']
        if invalid_dob.any():
            print(f"Removed {invalid_dob.sum()} record(s) where Hire_Date is before Date_of_Birth.")
            df = df[~invalid_dob]

    # Negative tenure means the hire date is in the future — warn but keep the row
    future_hires = df['Tenure_Years'] < 0
    if future_hires.any():
        print(f"Warning: {future_hires.sum()} record(s) have a Hire_Date in the future.")

    return df.reset_index(drop=True)
