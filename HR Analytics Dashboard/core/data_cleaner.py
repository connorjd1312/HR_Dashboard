# data_cleaner.py
# Cleans and enriches the normalised DataFrame produced by data_loader.py.
# Handles inconsistent status values, deduplication, missing data, and adds
# computed columns (Age, Tenure_Years, Turnover) used throughout the dashboard.

from __future__ import annotations

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


def _normalise_status(df: pd.DataFrame, note=lambda _msg: None) -> pd.DataFrame:
    # Map status variants to standard labels; unrecognised values become 'Unknown'.
    if 'Status' not in df.columns:
        # Column wasn't in the source file at all — default everyone to Unknown
        df['Status'] = 'Unknown'
        note('The file has no Status column, so every employee is shown with status Unknown.')
        return df

    mapped = df['Status'].astype(str).str.strip().str.lower().map(STATUS_MAP)
    unrecognised = mapped.isna() & df['Status'].notna()
    if unrecognised.any():
        examples = ', '.join(sorted(df.loc[unrecognised, 'Status'].astype(str).unique())[:3])
        note(f'{int(unrecognised.sum())} row(s) have a Status the dashboard doesn\'t recognise '
             f'(e.g. {examples}); they are shown as Unknown.')
    df['Status'] = mapped.fillna('Unknown')   # anything not matched in STATUS_MAP
    return df


_SEX_MAP = {
    'male':            'Male',
    'm':               'Male',
    'man':             'Male',
    'female':          'Female',
    'f':               'Female',
    'woman':           'Female',
    'non-binary':      'Non-binary',
    'nonbinary':       'Non-binary',
    'non binary':      'Non-binary',
    'prefer not to say': 'Prefer not to say',
    'prefer not':      'Prefer not to say',
    'not disclosed':   'Prefer not to say',
}


# Acronyms that Title Casing would otherwise turn into 'Hr', 'It', 'Cmo', etc.
_ACRONYMS = ['HR', 'IT', 'VP', 'AE', 'QA', 'UX', 'UI', 'CEO', 'CFO', 'CTO', 'CMO', 'COO']
_ACRONYM_PATTERN = r'\b(' + '|'.join(a.title() for a in _ACRONYMS) + r')\b'


def _normalise_text_fields(df: pd.DataFrame) -> pd.DataFrame:
    # Strip whitespace, apply Title Casing to text columns, and map Sex to standard labels.
    for col in ['Name', 'Department', 'Job_Role', 'Ethnicity']:
        if col in df.columns:
            # Keep blanks as missing (astype(str) would turn them into the text 'None'/'nan')
            text = df[col].astype(str).str.strip()
            blank = df[col].isna() | text.eq('')
            df[col] = text.str.title().mask(blank)
    # Optional grouping columns: show blanks as their own 'Unknown' group
    for col in ['Job_Role', 'Ethnicity']:
        if col in df.columns:
            df[col] = df[col].fillna('Unknown')
    for col in ['Department', 'Job_Role']:
        if col in df.columns:
            df[col] = df[col].str.replace(_ACRONYM_PATTERN, lambda m: m.group(0).upper(), regex=True)
    if 'Sex' in df.columns:
        df['Sex'] = (
            df['Sex']
            .astype(str)
            .str.strip()
            .str.lower()
            .map(_SEX_MAP)
            .fillna('Unknown')
        )
    return df


def clean(df: pd.DataFrame, report: list | None = None) -> pd.DataFrame:
    # Clean and enrich the HR DataFrame — normalise text/status, deduplicate, fill missing
    # values, add Age/Tenure_Years/Turnover columns, and check for invalid records.
    # Anything that was fixed, skipped or looks wrong is described in plain English
    # and appended to `report` (shown to the user after loading).
    note = report.append if report is not None else (lambda _msg: None)

    # Always work on a copy so the raw data stays intact for error diagnosis
    df = df.copy()

    # 1. Normalise text and status 
    df = _normalise_text_fields(df)
    df = _normalise_status(df, note)

    # 2. Deduplication and required field enforcement

    before = len(df)
    df.drop_duplicates(inplace=True)
    dupes_removed = before - len(df)
    if dupes_removed:
        note(f'{dupes_removed} duplicate row(s) were removed.')

    # Drop rows missing the columns the whole dashboard depends on
    before = len(df)
    df.dropna(subset=['Name', 'Hire_Date', 'Department'], inplace=True)
    if before - len(df):
        note(f'{before - len(df)} row(s) were skipped because the Name, Hire Date or '
             'Department was missing or unreadable.')

    # 3. Fill optional missing values with safe defaults

    if 'Salary' in df.columns:
        # Median is used instead of mean to avoid distortion from executive-level outliers
        missing = int(df['Salary'].isna().sum())
        if missing:
            note(f'{missing} row(s) had no salary; the median salary '
                 f'(${df["Salary"].median():,.0f}) was used instead.')
        df['Salary'] = df['Salary'].fillna(df['Salary'].median())

    if 'Absenteeism_Days' in df.columns:
        df['Absenteeism_Days'] = df['Absenteeism_Days'].fillna(0)

    if 'Leave_Balance' in df.columns:
        df['Leave_Balance'] = df['Leave_Balance'].fillna(0)

    # 4. Derived / computed columns

    today = pd.Timestamp(date.today())

    # Age in whole years; will be NaN if Date_of_Birth was missing or unparseable
    if 'Date_of_Birth' in df.columns:
        df['Age'] = ((today - df['Date_of_Birth']).dt.days // 365).astype('Int64')
        bins   = [-1, 29, 39, 49, 59, 200]
        labels = ['Under 30', '30–39', '40–49', '50–59', '60+']
        df['Age_Group'] = pd.cut(df['Age'], bins=bins, labels=labels).astype(str).replace('nan', 'Unknown')
        no_dob = int(df['Date_of_Birth'].isna().sum())
        if no_dob:
            note(f'{no_dob} row(s) have no valid date of birth, so their age is shown as Unknown.')

    # Tenure in decimal years from Hire_Date to their End_Date (or today if still employed)
    tenure_end = df['End_Date'].fillna(today) if 'End_Date' in df.columns else today
    df['Tenure_Years'] = ((tenure_end - df['Hire_Date']).dt.days / 365).round(1)

    # Turnover flag — True for any status that means the employee has left
    df['Turnover'] = df['Status'].isin(['Resigned', 'Terminated', 'Retired'])

    # 5. Validation warnings

    # Hire date before date of birth is physically impossible, remove those rows
    if 'Date_of_Birth' in df.columns:
        invalid_dob = df['Hire_Date'] < df['Date_of_Birth']
        if invalid_dob.any():
            note(f'{int(invalid_dob.sum())} row(s) were removed because the Hire Date is '
                 'before the Date of Birth.')
            df = df[~invalid_dob]

    # Hire date in the future — warn but keep the row
    future_hires = df['Hire_Date'] > today
    if future_hires.any():
        note(f'{int(future_hires.sum())} row(s) have a Hire Date in the future.')

    if 'End_Date' in df.columns:
        # End date before hire date — warn but keep the row
        backwards = df['End_Date'] < df['Hire_Date']
        if backwards.any():
            note(f'{int(backwards.sum())} row(s) have an End Date before their Hire Date.')

        # Leavers with no end date can't appear in departure trends or forecasts
        no_end = df['Turnover'] & df['End_Date'].isna()
        if no_end.any():
            note(f'{int(no_end.sum())} leaver(s) have no End Date, so they are left out of '
                 'departure trends and forecasts.')

        # Still marked Active but with an end date
        active_ended = (df['Status'] == 'Active') & df['End_Date'].notna()
        if active_ended.any():
            note(f'{int(active_ended.sum())} employee(s) are marked Active but have an End Date.')

    return df.reset_index(drop=True)
