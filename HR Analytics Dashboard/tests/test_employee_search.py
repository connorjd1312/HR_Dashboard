import pandas as pd
import pytest

from core import employee_search as es


@pytest.fixture
def df():
    rows = [
        ('Nathan Robinson', 'Engineering', 'Senior Engineer', 'Active', 100000, 4.0, 3, 10),
        ('Natalie Nash', 'Sales', 'Sales Manager', 'Active', 90000, 2.0, 5, 12),
        ('Ann Nathan', 'Sales', 'Sales Rep', 'Resigned', 50000, 1.0, 9, 4),
        ('Bob Stone', 'Sales', 'Sales Rep', 'Active', 60000, 3.0, 1, 20),
        ('Cara Lee', 'Sales', 'Sales Rep', 'Active', 70000, 5.0, 2, 8),
        ('Dan Poe', 'Engineering', 'Senior Engineer', 'Terminated', 80000, 6.0, 0, 5),
        ('Eve Ray', 'Engineering', 'Junior Engineer', 'Active', 55000, 1.5, 4, 9),
        ('Solo Person', 'Legal', 'Counsel', 'Active', 120000, 7.0, 2, 15),
    ]
    out = pd.DataFrame(rows, columns=['Name', 'Department', 'Job_Role', 'Status', 'Salary',
                                      'Tenure_Years', 'Absenteeism_Days', 'Leave_Balance'])
    out['Hire_Date'] = pd.Timestamp('2020-01-01')
    out['End_Date'] = pd.NaT
    out.loc[out['Status'].isin(['Resigned', 'Terminated']), 'End_Date'] = pd.Timestamp('2024-01-01')
    return out


def test_empty_query_returns_everyone_sorted_by_name(df):
    r = es.search_employees(df)
    assert len(r) == len(df)
    assert r['Name'].iloc[0] == 'Ann Nathan'


def test_search_is_case_insensitive_and_all_words_must_match(df):
    assert set(es.search_employees(df, 'NATHAN')['Name']) == {'Nathan Robinson', 'Ann Nathan'}
    assert list(es.search_employees(df, 'nathan eng')['Name']) == ['Nathan Robinson']
    assert len(es.search_employees(df, 'nathan zzz')) == 0


def test_names_starting_with_the_search_rank_first(df):
    assert list(es.search_employees(df, 'nat')['Name']) == [
        'Natalie Nash', 'Nathan Robinson', 'Ann Nathan', 'Dan Poe']


def test_search_matches_department_role_and_status(df):
    assert len(es.search_employees(df, 'sales rep')) == 3
    assert list(es.search_employees(df, 'resigned')['Name']) == ['Ann Nathan']
    assert len(es.search_employees(df, 'legal')) == 1


def test_filters_combine_with_search(df):
    r = es.search_employees(df, 'rep', department='Sales', status='Active')
    assert set(r['Name']) == {'Bob Stone', 'Cara Lee'}


def test_limit_and_empty_inputs(df):
    assert len(es.search_employees(df, limit=2)) == 2
    assert len(es.search_employees(None)) == 0
    assert len(es.search_employees(df.iloc[0:0], 'x')) == 0


def test_special_characters_are_literal(df):
    assert len(es.search_employees(df, '(.*')) == 0


def test_profile_basics_and_missing_key(df):
    p = es.employee_profile(df, 0)
    assert p['name'] == 'Nathan Robinson' and p['department'] == 'Engineering'
    assert p['left_company'] is False and p['end_date'] is None
    assert es.employee_profile(df, 999) is None
    assert es.employee_profile(None, 0) is None


def test_profile_flags_leavers(df):
    assert es.employee_profile(df, 2)['left_company'] is True


def test_profile_salary_comparison_against_department(df):
    p = es.employee_profile(df, 0)
    salary = next(x for x in p['peers'] if x['column'] == 'Salary')
    assert salary['department_avg'] == pytest.approx(235000 / 3)
    assert salary['difference'] == pytest.approx(100000 - 235000 / 3)
    assert salary['department_percentile'] == pytest.approx((2 + 0.5) / 3 * 100, abs=1)
    assert 'role_avg' not in salary


def test_role_comparison_only_with_enough_peers(df):
    sales_rep = es.employee_profile(df, 2)
    assert next(x for x in sales_rep['peers'] if x['column'] == 'Salary')['role_avg'] == pytest.approx(60000)


def test_no_peer_comparison_for_tiny_departments(df):
    assert es.employee_profile(df, 7)['peers'] == []


def test_profile_tolerates_missing_values(df):
    df.loc[0, 'Salary'] = float('nan')
    p = es.employee_profile(df, 0)
    assert p['salary'] is None
    assert all(x['column'] != 'Salary' for x in p['peers'])


def test_initials():
    assert es.initials('Nathan Robinson') == 'NR'
    assert es.initials('Cher') == 'C'
    assert es.initials('Mary-Jane van Dyke') == 'MD'
    assert es.initials(None) == '?' and es.initials('') == '?'
