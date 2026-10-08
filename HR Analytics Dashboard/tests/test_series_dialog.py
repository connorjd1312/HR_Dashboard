import pandas as pd

from ui import series_dialog


def _df():
    return pd.DataFrame({'Hire_Date': pd.to_datetime(['2018-01-04', '2024-06-01'])})


def test_auto_granularity_matches_range_length():
    assert series_dialog.auto_granularity('2026-07-01', '2026-09-30') == 'Weekly'
    assert series_dialog.auto_granularity('2025-10-01', '2026-10-01') == 'Monthly'
    assert series_dialog.auto_granularity('2018-01-01', '2026-10-01') == 'Quarterly'


def test_auto_label_is_readable():
    time = {'view_type': 'time', 'metric': 'Hires', 'filter_val': 'Sales', 'granularity': 'Monthly'}
    assert series_dialog.auto_label(time) == 'Hires · Sales'
    snap = {'view_type': 'snapshot', 'metric': 'Total Employees', 'group_by': 'Department'}
    assert series_dialog.auto_label(snap) == 'Total Employees by Department'


def test_templates_build_complete_series():
    required = {'id', 'label', 'view_type', 'metric', 'filter_by', 'filter_val', 'start_date',
                'end_date', 'granularity', 'style', 'show_trend', 'color', 'group_by'}
    for name in series_dialog.TEMPLATES:
        for s in series_dialog.series_from_template(name, _df()):
            assert required <= set(s)
            if s['view_type'] == 'time':
                assert s['start_date'] < s['end_date']


def test_hires_vs_departures_template_adds_two_series():
    series = series_dialog.series_from_template('Hires vs departures (last 12 months)', _df())
    assert [s['metric'] for s in series] == ['Hires', 'Departures']
