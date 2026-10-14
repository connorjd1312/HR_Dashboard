import numpy as np
import pandas as pd

from core.data_cleaner import clean


def make_raw(n=240, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    depts = ['Sales', 'Engineering', 'Human Resources', 'Customer Support']
    roles = {'Sales': ['Sales Manager', 'Sales Rep'], 'Engineering': ['Senior Engineer', 'Junior Engineer'],
             'Human Resources': ['HR Partner', 'Recruiter'], 'Customer Support': ['Support Agent', 'Team Lead']}
    today = pd.Timestamp.today().normalize()
    rows = []
    for i in range(n):
        d = depts[i % len(depts)]
        hire = today - pd.Timedelta(days=int(rng.integers(30, 2200)))
        left = rng.random() < 0.3
        end = hire + pd.Timedelta(days=int(rng.integers(60, 900))) if left else pd.NaT
        if left and end > today:
            end, left = pd.NaT, False
        rows.append({
            'Name': f'Person{i} Test{i % 7}', 'Date_of_Birth': today - pd.Timedelta(days=int(rng.integers(8000, 20000))),
            'Department': d, 'Job_Role': roles[d][i % 2], 'Hire_Date': hire, 'End_Date': end,
            'Salary': float(rng.integers(40, 150) * 1000), 'Status': 'Resigned' if left else 'Active',
            'Absenteeism_Days': int(rng.integers(0, 15)), 'Leave_Balance': float(rng.integers(0, 25)),
            'Sex': 'Male' if i % 2 else 'Female', 'Ethnicity': ['Asian', 'Maori', 'European'][i % 3],
        })
    return pd.DataFrame(rows)


def make_df(n=240, seed=1) -> pd.DataFrame:
    return clean(make_raw(n, seed))


def write_csv(path, n=240, seed=1) -> str:
    make_raw(n, seed).to_csv(path, index=False)
    return str(path)
