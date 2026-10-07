import json

import pandas as pd

from core import analytics, query_router


class _FakeClient:
    # Stands in for LocalLLMClient — records calls, returns a canned response.
    def __init__(self, response: str):
        self._response = response
        self.calls = []

    def chat(self, model, messages, json_mode=False, timeout=60.0):
        self.calls.append({'model': model, 'messages': messages, 'json_mode': json_mode})
        return self._response


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        'Name':         ['A', 'B', 'C', 'D'],
        'Department':   ['Sales', 'Sales', 'Engineering', 'Engineering'],
        'Job_Role':     ['Rep', 'Manager', 'Engineer', 'Engineer'],
        'Status':       ['Active', 'Resigned', 'Active', 'Active'],
        'Turnover':     [False, True, False, False],
        'Tenure_Years': [2.0, 3.5, 1.0, 4.0],
        'Salary':       [60000, 90000, 80000, 85000],
        'Hire_Date':    pd.to_datetime(['2022-01-01', '2020-05-01', '2023-03-01', '2019-07-01']),
        'End_Date':     pd.to_datetime([None, '2023-01-01', None, None]),
    })


# route_query


def test_route_query_valid_json_dispatches_to_named_function():
    df = _sample_df()
    client = _FakeClient(json.dumps({'function': 'overall_kpi', 'params': {'metric': 'Total Employees'}}))

    result = query_router.route_query(client, 'llama3.2', 'How many employees do we have?', df)

    assert result.function == 'overall_kpi'
    assert result.params['metric'] == 'Total Employees'
    assert client.calls[0]['json_mode'] is True


def test_route_query_falls_back_to_general_summary_on_malformed_json():
    df = _sample_df()
    client = _FakeClient('this is not json')

    result = query_router.route_query(client, 'llama3.2', 'asdkjh', df)

    assert result.function == 'general_summary'


def test_route_query_falls_back_on_unknown_function_name():
    df = _sample_df()
    client = _FakeClient(json.dumps({'function': 'delete_all_employees', 'params': {}}))

    result = query_router.route_query(client, 'llama3.2', 'hi', df)

    assert result.function == 'general_summary'


def test_route_query_falls_back_when_params_is_not_a_dict():
    df = _sample_df()
    client = _FakeClient(json.dumps({'function': 'overall_kpi', 'params': 'not a dict'}))

    result = query_router.route_query(client, 'llama3.2', 'hi', df)

    assert result.function == 'general_summary'


# _validate_params


def test_department_comparison_defaults_to_every_department():
    df = _sample_df()
    p = query_router._validate_params('department_comparison', {'metric': 'Total Employees'}, df)
    assert sorted(p['departments']) == ['Engineering', 'Sales']


def test_validate_params_rejects_departments_not_in_dataset():
    df = _sample_df()
    params = query_router._validate_params(
        'department_comparison', {'departments': ['Mars Colony'], 'metric': 'Total Employees'}, df,
    )
    assert set(params['departments']).issubset(set(df['Department'].unique()))
    assert len(params['departments']) > 0


def test_validate_params_clamps_out_of_range_forecast_periods():
    df = _sample_df()
    params = query_router._validate_params(
        'forecast', {'metric': 'Hires', 'periods': 999, 'method': 'Linear Trend'}, df,
    )
    assert params['periods'] == 24


def test_validate_params_defaults_invalid_metric():
    df = _sample_df()
    params = query_router._validate_params('overall_kpi', {'metric': 'Not A Real Metric'}, df)
    assert params['metric'] == 'Total Employees'


# execute


def test_execute_overall_kpi_matches_analytics_directly():
    df = _sample_df()
    result = query_router.execute(query_router.RouterResult('overall_kpi', {'metric': 'Total Employees'}), df)
    assert result == analytics.kpi_value(df, 'Total Employees')


def test_execute_department_comparison_returns_series_indexed_by_department():
    df = _sample_df()
    result = query_router.execute(
        query_router.RouterResult(
            'department_comparison', {'departments': ['Sales', 'Engineering'], 'metric': 'Total Employees'},
        ),
        df,
    )
    assert result['Sales'] == 2.0
    assert result['Engineering'] == 2.0


def test_execute_general_summary_has_expected_keys():
    df = _sample_df()
    result = query_router.execute(query_router.RouterResult('general_summary', {}), df)
    assert set(result.keys()) == {
        'total_employees', 'active_employees', 'turnover_rate', 'attrition_rate',
        'avg_tenure_years', 'avg_salary',
    }


def test_execute_forecast_returns_summary_dict():
    df = _sample_df()
    result = query_router.execute(
        query_router.RouterResult('forecast', {'metric': 'Hires', 'periods': 2, 'method': 'Linear Trend'}),
        df,
    )
    assert 'direction' in result
    assert 'forecast_points' in result
    assert len(result['forecast_points']) == 2


# explain_result


def test_explain_result_sends_context_as_user_message_without_json_mode():
    client = _FakeClient('Here is your answer.')

    answer = query_router.explain_result(client, 'llama3.2', 'What is turnover?', {'question': 'x', 'result': 1})

    assert answer == 'Here is your answer.'
    call = client.calls[0]
    assert call['json_mode'] is False
    assert call['messages'][0]['role'] == 'system'
    assert json.loads(call['messages'][1]['content']) == {'question': 'x', 'result': 1}


# Keeping answers to the data

def test_route_query_accepts_unsupported_and_executes_to_nothing():
    client = _FakeClient(json.dumps({'function': 'unsupported', 'params': {'reason': 'pay rise what-if'}}))
    result = query_router.route_query(client, 'model', 'What if we raised pay 10%?', _sample_df())
    assert result.function == 'unsupported'
    assert query_router.execute(result, _sample_df()) is None


def test_unsupported_question_gets_direct_answer_without_llm():
    route = query_router.RouterResult('unsupported', {'reason': 'pay rise what-if'})
    answer = query_router.direct_answer(route, None)
    assert 'only answer from the figures' in answer
    assert 'pay rise what-if' in answer


def test_single_kpi_answered_exactly_from_dashboard_value():
    df = _sample_df()
    route = query_router.RouterResult('overall_kpi', {'metric': 'Overall Turnover Rate (%)'})
    value = query_router.execute(route, df)
    answer = query_router.direct_answer(route, value)
    assert answer.startswith(f'Overall Turnover Rate (%): {analytics.kpi_value(df, "Overall Turnover Rate (%)")}.')


def test_breakdowns_still_go_to_llm_with_precomputed_key_facts():
    from core import context_builder
    df = _sample_df()
    route = query_router.RouterResult('breakdown_kpi', {'metric': 'Average Salary ($)', 'group_by': 'Department'})
    result = query_router.execute(route, df)
    assert query_router.direct_answer(route, result) is None
    facts = context_builder.build_context('q', route.function, route.params, result)['key_facts']
    assert facts['highest']['label'] == 'Engineering'
    assert facts['lowest']['label'] == 'Sales'


def test_time_series_key_facts_include_change():
    from core import context_builder
    s = pd.Series([5, 8, 3], index=pd.to_datetime(['2026-07-31', '2026-08-31', '2026-09-30']))
    facts = context_builder.key_facts(s)
    assert facts['change_first_to_last'] == -2
    assert facts['trend'] == 'down'
    assert facts['peak_period'] == '2026-08-31'


def test_explain_prompt_forbids_own_calculations():
    assert 'Do NOT calculate' in query_router._EXPLAIN_SYSTEM_PROMPT


def test_source_note_names_the_dashboard_figure():
    route = query_router.RouterResult('breakdown_kpi', {'metric': 'Average Salary ($)', 'group_by': 'Department'})
    assert query_router.source_note(route) == 'Source: Average Salary ($) by Department'


# Following the dashboard filters

def test_trends_use_full_history_even_when_filtered():
    df = _sample_df()
    filtered = df[df['Department'] == 'Sales']
    route = query_router.RouterResult('time_series_trend', {
        'metric': 'Hires', 'filter_by': 'None', 'filter_val': 'All',
        'granularity': 'Yearly', 'months_back': 120})
    full = query_router.execute(route, df)
    assert query_router.execute(route, filtered, history_df=df).equals(full)


def test_kpis_use_the_filtered_employees():
    df = _sample_df()
    filtered = df[df['Department'] == 'Sales']
    route = query_router.RouterResult('overall_kpi', {'metric': 'Total Employees'})
    assert query_router.execute(route, filtered, history_df=df) == '2'


def test_source_note_describes_dashboard_scope():
    df = _sample_df()
    route = query_router.RouterResult('overall_kpi', {'metric': 'Total Employees'})
    note = query_router.source_note(route, df, scope='Department: Sales')
    assert note.endswith('4 employees matching the dashboard (Department: Sales)')
