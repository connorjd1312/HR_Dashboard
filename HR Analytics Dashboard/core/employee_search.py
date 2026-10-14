# Names repeat and there is no id column

from __future__ import annotations

import pandas as pd

SEARCH_COLUMNS = ['Name', 'Department', 'Job_Role', 'Status']

# column, label, unit, direction (1 higher is better, -1 lower, 0 neutral)
PEER_METRICS = [
    ('Salary', 'Salary', '$', 0),
    ('Tenure_Years', 'Tenure (yrs)', 'yrs', 0),
    ('Absenteeism_Days', 'Absenteeism (days)', 'days', -1),
    ('Leave_Balance', 'Leave balance (days)', 'days', 0),
]

MIN_PEERS = 3


def _haystack(df: pd.DataFrame) -> pd.Series:
    cols = [c for c in SEARCH_COLUMNS if c in df.columns]
    if not cols:
        return pd.Series('', index=df.index)
    text = df[cols[0]].fillna('').astype(str)
    for col in cols[1:]:
        text = text + ' | ' + df[col].fillna('').astype(str)
    return text.str.lower()


def search_employees(df: pd.DataFrame | None, query: str = '', department: str = 'All',
                     status: str = 'All', limit: int | None = None) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame() if df is None else df.iloc[0:0]

    out = df
    if department and department != 'All' and 'Department' in out.columns:
        out = out[out['Department'] == department]
    if status and status != 'All' and 'Status' in out.columns:
        out = out[out['Status'] == status]

    tokens = query.lower().split()
    if tokens and len(out):
        hay = _haystack(out)
        mask = pd.Series(True, index=out.index)
        for token in tokens:
            mask &= hay.str.contains(token, regex=False)
        out = out[mask]

        if len(out) and 'Name' in out.columns:
            names = out['Name'].fillna('').astype(str).str.lower()
            first = tokens[0]
            rank = pd.Series(2, index=out.index)
            rank[names.str.contains(first, regex=False)] = 1
            rank[names.str.startswith(first)] = 0
            out = (out.assign(_rank=rank, _name=names)
                      .sort_values(['_rank', '_name'], kind='stable')
                      .drop(columns=['_rank', '_name']))
            return out.head(limit) if limit else out

    if 'Name' in out.columns and len(out):
        out = out.sort_values('Name', kind='stable', key=lambda s: s.fillna('').astype(str).str.lower())
    return out.head(limit) if limit else out


def _clean(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, 'item') and not isinstance(value, (pd.Timestamp, str)):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _percentile(series: pd.Series, value: float) -> float:
    s = series.dropna()
    if not len(s):
        return 0.0
    below = float((s < value).sum())
    equal = float((s == value).sum())
    return round((below + 0.5 * equal) / len(s) * 100, 0)


def employee_profile(df: pd.DataFrame, key) -> dict | None:
    if df is None or key not in df.index:
        return None
    row = df.loc[key]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]

    def get(col):
        return _clean(row[col]) if col in row.index else None

    dept, role = get('Department'), get('Job_Role')
    dept_df = df[df['Department'] == dept] if dept is not None and 'Department' in df.columns else df.iloc[0:0]
    role_df = df[df['Job_Role'] == role] if role is not None and 'Job_Role' in df.columns else df.iloc[0:0]

    status = get('Status')
    left = status in ('Resigned', 'Terminated', 'Retired') or get('End_Date') is not None

    peers = []
    for col, label, unit, good in PEER_METRICS:
        value = get(col)
        if value is None or col not in df.columns or len(dept_df) < MIN_PEERS:
            continue
        dept_avg = float(dept_df[col].mean())
        entry = {
            'column': col, 'label': label, 'unit': unit, 'good_direction': good,
            'value': float(value), 'department_avg': dept_avg,
            'difference': float(value) - dept_avg,
            'department_percentile': _percentile(dept_df[col], float(value)),
        }
        if col == 'Salary' and len(role_df) >= MIN_PEERS:
            entry['role_avg'] = float(role_df[col].mean())
            entry['role_count'] = int(len(role_df))
        peers.append(entry)

    return {
        'key': key,
        'name': get('Name'),
        'job_role': role,
        'department': dept,
        'status': status,
        'left_company': bool(left),
        'sex': get('Sex'),
        'ethnicity': get('Ethnicity'),
        'date_of_birth': get('Date_of_Birth'),
        'age': get('Age'),
        'age_group': get('Age_Group'),
        'hire_date': get('Hire_Date'),
        'end_date': get('End_Date'),
        'tenure_years': get('Tenure_Years'),
        'salary': get('Salary'),
        'absenteeism_days': get('Absenteeism_Days'),
        'leave_balance': get('Leave_Balance'),
        'department_size': int(len(dept_df)),
        'role_size': int(len(role_df)),
        'peers': peers,
    }


def initials(name: str | None) -> str:
    parts = [p for p in str(name or '').replace('-', ' ').split() if p]
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()
