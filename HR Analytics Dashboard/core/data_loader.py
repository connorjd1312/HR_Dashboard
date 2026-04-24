# data_loader.py
# Responsible for reading CSV and XLSX files into a normalised Pandas DataFrame.
# Handles inconsistent column names by mapping known variants to the standard schema,
# then parses dates and cleans salary formatting before returning to the pipeline.

import pandas as pd
from pathlib import Path

SUPPORTED = {'.csv', '.xlsx'}

# Maps each standard column name to a list of known real-world variants.
# All comparisons are done lowercase so casing in the source file doesn't matter.
COLUMN_MAP = {
    'Name':             ['name', 'employee_name', 'full_name', 'emp_name',
                         'employee name', 'full name'],
    'Date_of_Birth':    ['date_of_birth', 'dob', 'birth_date', 'birthdate',
                         'date of birth'],
    'Department':       ['department', 'dept', 'division', 'team',
                         'business_unit', 'business unit'],
    'Job_Role':         ['job_role', 'role', 'position', 'title', 'job_title',
                         'job title', 'job role'],
    'Hire_Date':        ['hire_date', 'start_date', 'date_hired', 'employment_date',
                         'hire date', 'start date', 'commencement_date',
                         'commencement date'],
    'End_Date':         ['end_date', 'termination_date', 'leave_date',
                         'separation_date', 'end date', 'termination date'],
    'Salary':           ['salary', 'wage', 'annual_salary', 'pay',
                         'compensation', 'annual salary'],
    'Status':           ['status', 'employment_status', 'emp_status',
                         'active_status', 'employment status'],
    'Absenteeism_Days': ['absenteeism_days', 'absence_days', 'days_absent',
                         'absenteeism', 'absent_days', 'absenteeism days'],
    'Leave_Balance':    ['leave_balance', 'annual_leave', 'leave_days',
                         'remaining_leave', 'leave balance', 'leave days remaining'],
}

# The pipeline cannot function without these columns — file is rejected if they're missing
REQUIRED_COLUMNS = {'Name', 'Hire_Date', 'Department'}

# These columns will be converted to datetime after the column mapping step
DATE_COLUMNS = {'Hire_Date', 'Date_of_Birth', 'End_Date'}

# Common date formats found in HR exports, tried in order if auto-inference fails
DATE_FORMATS = [
    '%Y-%m-%d',   # 2024-01-15  (ISO — most common in system exports)
    '%d/%m/%Y',   # 15/01/2024  (NZ/AU/UK style)
    '%m/%d/%Y',   # 01/15/2024  (US style)
    '%d-%m-%Y',   # 15-01-2024
    '%Y/%m/%d',   # 2024/01/15
    '%d %b %Y',   # 15 Jan 2024
    '%B %d, %Y',  # January 15, 2024
]


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename incoming columns to the standard schema using COLUMN_MAP."""

    # Build a flat lookup: lowercase variant → standard name
    lookup = {}
    for standard, variants in COLUMN_MAP.items():
        for variant in variants:
            lookup[variant.lower()] = standard

    # Build the rename mapping for columns that match a known variant
    rename = {}
    for col in df.columns:
        standard = lookup.get(col.strip().lower())
        if standard:
            rename[col] = standard

    df = df.rename(columns=rename)

    # Reject the file early if critical columns couldn't be identified
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Cannot find required columns: {missing}.\n"
            f"Columns detected in file: {list(df.columns)}\n"
            f"Rename your columns to match the expected names and try again."
        )

    return df


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Parse date columns, falling back through explicit formats if auto-inference fails."""
    for col in DATE_COLUMNS:
        if col not in df.columns:
            continue

        # Let pandas attempt automatic inference first — covers most common formats
        parsed = pd.to_datetime(df[col], infer_datetime_format=True, errors='coerce')

        # Where inference produced NaT but the source cell had a value, try explicit formats
        had_values = df[col].notna()
        if parsed[had_values].isna().any():
            for fmt in DATE_FORMATS:
                retry = pd.to_datetime(df[col], format=fmt, errors='coerce')
                parsed = parsed.fillna(retry)
                if not parsed[had_values].isna().any():
                    break  # All previously-failing values are now resolved

        remaining_failures = parsed[had_values].isna().sum()
        if remaining_failures:
            print(f"Warning: {remaining_failures} value(s) in '{col}' could not be parsed as a date and will be treated as missing.")

        df[col] = parsed

    return df


def _clean_salary(df: pd.DataFrame) -> pd.DataFrame:
    """Strip currency symbols, commas, and whitespace from Salary then coerce to float."""
    if 'Salary' not in df.columns:
        return df

    df['Salary'] = (
        df['Salary']
        .astype(str)
        .str.replace(r'[$£€,\s]', '', regex=True)  # remove symbols and commas
        .replace('nan', pd.NA)                       # restore actual NaN from string 'nan'
    )
    df['Salary'] = pd.to_numeric(df['Salary'], errors='coerce')

    return df


def load_file(filepath: str) -> pd.DataFrame:
    """
    Load a CSV or XLSX file into a clean, consistently-named DataFrame.
    Column names are normalised, dates are parsed, and salary is converted to float.
    The returned DataFrame is ready to be passed straight to data_cleaner.clean().
    """
    path = Path(filepath)

    if path.suffix not in SUPPORTED:
        raise ValueError(f"Unsupported file type '{path.suffix}'. Please use .csv or .xlsx.")

    # Load the raw file without date parsing — we handle dates after column normalisation
    if path.suffix == '.csv':
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    df = _normalise_columns(df)
    df = _parse_dates(df)
    df = _clean_salary(df)

    return df
