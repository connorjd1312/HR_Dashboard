# query_router.py
# LLM-based Query Router for the AI Workforce Advisor.
#
# Flow (matches the client's Local AI Architecture doc):
#   1. route_query()   — ask the local LLM to classify the question into one of a
#                          fixed set of Python analytics calls + params (JSON output).
#   2. execute()        — run that call against core/analytics.py or core/forecasting.py
#                          (the "HR Analytics Engine" — all real math happens here).
#   3. context_builder.build_context() turns the result into an aggregated summary.
#   4. explain_result() — a second LLM call that explains the summary in plain English.
#
# The LLM never performs calculations and never sees row-level employee data —
# it only ever classifies the question and later narrates an aggregated result.

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from core import analytics, forecasting
from core.local_llm_client import LocalLLMError

ROUTER_FUNCTIONS = {
    'overall_kpi': 'A single headline number for the whole (filtered) workforce.',
    'breakdown_kpi': 'The same KPI broken down per group (department, job role, status, etc).',
    'department_comparison': 'Compares specific departments against each other on one metric.',
    'time_series_trend': 'A trend of a metric over recent months/quarters.',
    'forecast': 'Projects a metric forward using statistical forecasting.',
    'general_summary': "Whole-dataset headline stats — fallback when nothing else clearly fits.",
}


@dataclass
class RouterResult:
    function: str
    params: dict = field(default_factory=dict)


# Prompt building


def _valid_values(df: pd.DataFrame | None) -> dict:
    if df is None or len(df) == 0:
        return {'departments': [], 'job_roles': []}
    return {
        'departments': sorted(df['Department'].dropna().unique().tolist())
        if 'Department' in df.columns else [],
        'job_roles': sorted(df['Job_Role'].dropna().unique().tolist())
        if 'Job_Role' in df.columns else [],
    }


def build_router_prompt(question: str, df: pd.DataFrame | None) -> list[dict]:
    valid = _valid_values(df)

    system = f"""You are the Query Router for an HR Workforce Advisor. Your only job is to
classify the user's question into exactly one of the following Python functions and
extract its parameters. You do not answer the question yourself and you do not perform
any calculations — a separate analytics engine does that.

Available functions:

1. overall_kpi(metric) — {ROUTER_FUNCTIONS['overall_kpi']}
   metric must be exactly one of: {analytics.KPI_OPTIONS}

2. breakdown_kpi(metric, group_by) — {ROUTER_FUNCTIONS['breakdown_kpi']}
   metric must be exactly one of: {analytics.KPI_OPTIONS}
   group_by must be exactly one of: {analytics.GROUP_BY_OPTIONS}

3. department_comparison(departments, metric) — {ROUTER_FUNCTIONS['department_comparison']}
   departments must be a JSON list drawn only from: {valid['departments']}
   metric must be exactly one of: {analytics.COMPARISON_METRICS}

4. time_series_trend(metric, filter_by, filter_val, granularity, months_back) — {ROUTER_FUNCTIONS['time_series_trend']}
   metric must be exactly one of: {analytics.TIME_SERIES_METRICS}
   filter_by must be "None" or one of: {analytics.GROUP_BY_OPTIONS}
   filter_val must be "All" or a specific value matching filter_by (e.g. a department name)
   granularity must be exactly one of: {analytics.GRANULARITIES}
   months_back is an integer number of months of history to include (default 12)

5. forecast(metric, periods, method) — {ROUTER_FUNCTIONS['forecast']}
   metric must be exactly one of: {forecasting.FORECAST_METRICS}
   periods is an integer number of future periods to project (default 3)
   method must be exactly one of: {forecasting.FORECAST_METHODS}

6. general_summary() — {ROUTER_FUNCTIONS['general_summary']} Takes no parameters.

Known job roles in the current dataset (for context only, not a function parameter): {valid['job_roles']}

Respond with ONLY a JSON object, no other text, of the exact form:
{{"function": "<one of the six names above>", "params": {{...}}}}"""

    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': question},
    ]


# Routing


def route_query(client, model: str, question: str, df: pd.DataFrame | None) -> RouterResult:
    messages = build_router_prompt(question, df)
    try:
        raw = client.chat(model, messages, json_mode=True)
        parsed = json.loads(raw)
        function = parsed.get('function')
        params = parsed.get('params') or {}
    except (LocalLLMError, ValueError, AttributeError, TypeError):
        return RouterResult('general_summary', {})

    if function not in ROUTER_FUNCTIONS or not isinstance(params, dict):
        return RouterResult('general_summary', {})

    return RouterResult(function, _validate_params(function, params, df))


def _validate_params(function: str, params: dict, df: pd.DataFrame | None) -> dict:
    # Never trust the LLM's params outright — clamp/replace anything invalid with a
    # sane default instead of letting a bad value reach the analytics engine.
    valid = _valid_values(df)
    p = dict(params)

    if function == 'overall_kpi':
        if p.get('metric') not in analytics.KPI_OPTIONS:
            p['metric'] = 'Total Employees'

    elif function == 'breakdown_kpi':
        if p.get('metric') not in analytics.KPI_OPTIONS:
            p['metric'] = 'Total Employees'
        if p.get('group_by') not in analytics.GROUP_BY_OPTIONS:
            p['group_by'] = 'Department'

    elif function == 'department_comparison':
        depts = p.get('departments')
        depts = [d for d in depts if d in valid['departments']] if isinstance(depts, list) else []
        p['departments'] = depts or valid['departments'][:5]
        if p.get('metric') not in analytics.COMPARISON_METRICS:
            p['metric'] = 'Employee Count'

    elif function == 'time_series_trend':
        if p.get('metric') not in analytics.TIME_SERIES_METRICS:
            p['metric'] = analytics.TIME_SERIES_METRICS[0]
        if p.get('filter_by') not in (['None'] + analytics.GROUP_BY_OPTIONS):
            p['filter_by'] = 'None'
        if not isinstance(p.get('filter_val'), str):
            p['filter_val'] = 'All'
        if p.get('granularity') not in analytics.GRANULARITIES:
            p['granularity'] = 'Monthly'
        p['months_back'] = _clamp_int(p.get('months_back'), default=12, lo=1, hi=60)

    elif function == 'forecast':
        if p.get('metric') not in forecasting.FORECAST_METRICS:
            p['metric'] = forecasting.FORECAST_METRICS[0]
        p['periods'] = _clamp_int(p.get('periods'), default=3, lo=1, hi=24)
        if p.get('method') not in forecasting.FORECAST_METHODS:
            p['method'] = 'Linear Trend'

    return p


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


# Execution — this is the "HR Analytics Engine" step; all real math happens here.


def execute(result: RouterResult, df: pd.DataFrame):
    fn, p = result.function, result.params

    if fn == 'overall_kpi':
        return analytics.kpi_value(df, p['metric'])

    if fn == 'breakdown_kpi':
        return analytics.kpi_breakdown(df, p['metric'], p['group_by'])

    if fn == 'department_comparison':
        return analytics.dept_comparison(df, p['departments'], p['metric'])

    if fn == 'time_series_trend':
        start, end = _resolve_time_range(p.get('months_back', 12))
        return analytics.time_series_data(
            df, p['metric'], p.get('filter_by', 'None'), p.get('filter_val', 'All'),
            start, end, p.get('granularity', 'Monthly'),
        )

    if fn == 'forecast':
        start, end = _resolve_time_range(12)
        history = analytics.time_series_data(
            df, p['metric'], 'None', 'All', start, end, 'Monthly',
        )
        fc = forecasting.forecast_series(
            history, p.get('periods', 3), p.get('method', 'Linear Trend'), 'ME',
        )
        return forecasting.forecast_summary(history, fc)

    return _general_summary(df)


def _resolve_time_range(months_back: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    end = pd.Timestamp(date.today())
    start = end - pd.DateOffset(months=months_back)
    return start, end


def _general_summary(df: pd.DataFrame) -> dict:
    if df is None or len(df) == 0:
        return {'note': 'No data is currently loaded.'}
    return {
        'total_employees': analytics.kpi_value(df, 'Total Employees'),
        'active_employees': analytics.kpi_value(df, 'Active Employees'),
        'turnover_rate': analytics.kpi_value(df, 'Overall Turnover Rate (%)'),
        'avg_tenure_years': analytics.kpi_value(df, 'Avg Tenure (yrs)'),
        'avg_salary': analytics.kpi_value(df, 'Avg Salary ($)'),
    }


# Explanation — second LLM call, narrates the aggregated context only.


_EXPLAIN_SYSTEM_PROMPT = (
    "You are the AI Workforce Advisor for an HR analytics dashboard. "
    "You are given a JSON object containing the user's question and the ONLY "
    "workforce data you are permitted to reference — it was already computed and "
    "aggregated by the HR Analytics Engine. "
    "Answer the question in clear, plain English (2-5 sentences unless the question "
    "calls for a short list). Use only the numbers provided in the JSON — never invent, "
    "estimate, or assume figures that aren't there. If the data doesn't actually answer "
    "the question, say so plainly. You may add one brief, sensible HR observation or "
    "recommendation, grounded strictly in the given numbers."
)


def explain_result(client, model: str, question: str, context: dict) -> str:
    messages = [
        {'role': 'system', 'content': _EXPLAIN_SYSTEM_PROMPT},
        {'role': 'user', 'content': json.dumps(context)},
    ]
    return client.chat(model, messages, json_mode=False)
