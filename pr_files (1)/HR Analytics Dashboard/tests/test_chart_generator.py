import json

import pytest

from core import analytics, chart_generator as cg
from core.local_llm_client import LocalLLMError
from tests._data import make_df


@pytest.fixture(scope='module')
def df():
    return make_df()


def one(text, df):
    return cg.suggest_chart(text, df)


def test_hires_vs_departures_makes_two_time_series(df):
    r = one('hires vs departures over the last 2 years', df)
    assert [s['metric'] for s in r.series] == ['Hires', 'Departures']
    assert all(s['view_type'] == 'time' for s in r.series)
    assert r.engine == 'keywords'
    assert r.series[0]['color'] != r.series[1]['color']


def test_time_range_phrases(df):
    from core.series_utils import date_range
    for text, months in [('hires last 6 months', 6), ('hires over the past year', 12),
                         ('hires in the last 3 quarters', 9), ('hires last two years', 24)]:
        s = one(text, df).series[0]
        assert (s['start_date'], s['end_date']) == date_range(months, df), text


def test_calendar_year_and_since(df):
    s = one('departures in 2024', df).series[0]
    assert (s['start_date'], s['end_date']) == ('2024-01-01', '2024-12-31')
    assert one('hires since 2023', df).series[0]['start_date'] == '2023-01-01'


def test_all_time_uses_first_hire(df):
    s = one('hires all time', df).series[0]
    assert s['start_date'] == df['Hire_Date'].min().strftime('%Y-%m-%d')


def test_snapshot_group_and_style(df):
    s = one('average salary by job role as horizontal bars', df).series[0]
    assert (s['view_type'], s['metric'], s['group_by'], s['style']) == (
        'snapshot', 'Average Salary ($)', 'Job Role', 'Horizontal Bar')


def test_pie_allowed_for_headcount_but_not_for_averages(df):
    assert one('headcount by status pie chart', df).series[0]['style'] == 'Pie'
    r = one('average salary by department pie chart', df)
    assert r.series[0]['style'] != 'Pie' and any('pie' in n.lower() for n in r.notes)


def test_age_group_is_a_grouping_not_the_age_metric(df):
    s = one('headcount by age group', df).series[0]
    assert s['metric'] == 'Total Employees' and s['group_by'] == 'Age Group'
    assert one('average age by department', df).series[0]['metric'] == 'Average Age'


def test_turnover_is_snapshot_unless_time_is_implied(df):
    assert one('turnover by department', df).series[0]['view_type'] == 'snapshot'
    s = one('turnover trend over the last year', df).series[0]
    assert (s['view_type'], s['metric']) == ('time', 'Turnover Rate per Period (%)')


def test_named_departments_become_one_series_each(df):
    r = one('compare hires in Sales and Engineering last 6 months', df)
    assert [(s['filter_by'], s['filter_val']) for s in r.series] == [('Department', 'Sales'), ('Department', 'Engineering')]


def test_single_named_group_becomes_a_filter(df):
    s = one('monthly departures in HR for 2024', df).series[0]
    assert (s['filter_by'], s['filter_val'], s['granularity']) == ('Department', 'Human Resources', 'Monthly')


def test_time_series_by_group_splits_on_every_group(df):
    r = one('hires by department', df)
    assert {s['filter_val'] for s in r.series} == set(df['Department'].unique())


def test_trend_line_and_granularity(df):
    s = one('weekly hires last 3 months with a trend line', df).series[0]
    assert s['show_trend'] is True and s['granularity'] == 'Weekly'


def test_measures_that_cannot_be_over_time_are_explained(df):
    r = one('average salary over time', df)
    assert r.series[0]['view_type'] == 'snapshot' and r.notes


def test_unrecognised_request_explains_what_to_try(df):
    with pytest.raises(cg.ChartRequestError, match='headcount'):
        one('show me something nice', df)
    with pytest.raises(cg.ChartRequestError):
        one('   ', df)


def test_hires_by_group_is_not_silently_wrong(df):
    assert all(s['view_type'] == 'time' for s in one('hires by sex', df).series)


def test_every_series_has_the_full_shape_the_builder_needs(df):
    required = {'id', 'label', 'view_type', 'metric', 'filter_by', 'filter_val', 'start_date',
                'end_date', 'granularity', 'style', 'show_trend', 'color', 'group_by'}
    for text in ['hires vs departures', 'turnover by department', 'average tenure by sex']:
        for s in one(text, df).series:
            assert required <= set(s)
            if s['view_type'] == 'time':
                assert s['start_date'] < s['end_date'] and s['granularity'] in analytics.GRANULARITIES


class FakeClient:
    def __init__(self, reply=None, error=None, available=True):
        self.reply, self.error, self.available, self.calls = reply, error, available, []

    def is_available(self):
        return self.available

    def chat(self, model, messages, json_mode=False, max_tokens=None):
        self.calls.append((messages, json_mode, max_tokens))
        if self.error:
            raise self.error
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


GOOD = {'title': 'Sales hires', 'series': [{
    'view': 'time', 'metric': 'Hires', 'filter_by': 'Department', 'filter_val': 'sales',
    'months': 6, 'granularity': 'Weekly', 'style': 'Bar', 'trend': True}]}


def test_ai_spec_is_used_and_validated(df):
    client = FakeClient(GOOD)
    r = cg.suggest_chart('anything', df, client, 'm')
    s = r.series[0]
    assert r.engine == 'ai' and r.title == 'Sales hires'
    assert (s['filter_val'], s['style'], s['granularity'], s['show_trend']) == ('Sales', 'Bar', 'Weekly', True)
    assert client.calls[0][1] is True and client.calls[0][2] == cg.MAX_TOKENS


def test_ai_prompt_contains_valid_names_but_no_employee_rows(df):
    client = FakeClient(GOOD)
    cg.suggest_chart('anything', df, client, 'm')
    prompt = ' '.join(m['content'] for m in client.calls[0][0])
    assert 'Engineering' in prompt and 'Hires' in prompt
    assert df['Name'].iloc[0] not in prompt


def test_ai_hallucinated_group_is_dropped_with_a_note(df):
    bad = json.loads(json.dumps(GOOD))
    bad['series'][0]['filter_val'] = 'Narnia'
    r = cg.suggest_chart('x', df, FakeClient(bad), 'm')
    assert r.series[0]['filter_val'] == 'All' and any('Narnia' in n for n in r.notes)


def test_ai_invalid_values_are_corrected(df):
    spec = {'series': [{'view': 'snapshot', 'metric': 'Average Salary ($)', 'group_by': 'Planet',
                        'style': 'Hologram'}]}
    s = cg.suggest_chart('x', df, FakeClient(spec), 'm').series[0]
    assert s['group_by'] == 'Department' and s['style'] in cg.SNAP_STYLES


def test_ai_wrong_view_for_metric_is_repaired(df):
    spec = {'series': [{'view': 'time', 'metric': 'Overall Turnover Rate (%)'}]}
    assert cg.suggest_chart('x', df, FakeClient(spec), 'm').series[0]['metric'] == 'Turnover Rate per Period (%)'


def test_ai_months_are_clamped_and_series_capped(df):
    spec = {'series': [{'metric': 'Hires', 'months': 99999}] * 20}
    r = cg.suggest_chart('x', df, FakeClient(spec), 'm')
    assert len(r.series) == cg.MAX_SERIES
    from core.series_utils import date_range
    assert r.series[0]['start_date'] == date_range(120, df)[0]


def test_ai_mixed_kinds_keep_the_first_kind(df):
    spec = {'series': [{'metric': 'Hires'}, {'view': 'snapshot', 'metric': 'Total Employees'}]}
    r = cg.suggest_chart('x', df, FakeClient(spec), 'm')
    assert [s['view_type'] for s in r.series] == ['time'] and r.notes


@pytest.mark.parametrize('client', [
    FakeClient('not json at all'),
    FakeClient({'series': 'nope'}),
    FakeClient({'series': [{'metric': 'Happiness'}]}),
    FakeClient(error=LocalLLMError('boom')),
    FakeClient(GOOD, available=False),
])
def test_falls_back_to_keywords_when_ai_is_unusable(df, client):
    r = cg.suggest_chart('turnover by department', df, client, 'm')
    assert r.engine == 'keywords' and r.series[0]['metric'] == 'Overall Turnover Rate (%)'


def test_unavailable_model_is_not_called(df):
    client = FakeClient(GOOD, available=False)
    cg.suggest_chart('hires', df, client, 'm')
    assert client.calls == []


def test_describe_is_readable(df):
    text = one('hires last 6 months with trend line', df).describe()
    assert 'Hires' in text and 'with trend line' in text and 'monthly' in text
