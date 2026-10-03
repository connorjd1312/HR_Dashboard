# context_builder.py
# Turns a raw analytics/forecasting result into the small, JSON-safe, aggregated
# summary that gets sent to the local LLM. This is the privacy boundary described
# in the client's Local AI Architecture doc: only aggregated workforce statistics
# are ever handed to the model, never individual employee records.

from __future__ import annotations

import pandas as pd

_MAX_ROWS = 20


class ContextBuilderError(Exception):
    pass


def _round(value):
    if isinstance(value, float):
        return round(value, 2)
    return value


def _serialize(value):
    # Row-level data must never reach the LLM — fail loudly rather than leak it.
    if isinstance(value, pd.DataFrame):
        raise ContextBuilderError(
            'Refusing to build AI context from a DataFrame — only aggregated '
            'results (Series/dict/scalar) may be sent to the local LLM.'
        )

    if isinstance(value, pd.Series):
        items = [
            {'label': str(label), 'value': _round(val)}
            for label, val in value.items()
        ]
        truncated = len(items) > _MAX_ROWS
        return {'series': items[:_MAX_ROWS], 'truncated': truncated}

    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value[:_MAX_ROWS]]

    if isinstance(value, (pd.Timestamp,)):
        return value.strftime('%Y-%m-%d')

    if hasattr(value, 'item'):  # numpy scalar (int64/float64/bool_)
        return _round(value.item())

    return _round(value)


def key_facts(result) -> dict:
    # Facts the LLM would otherwise be tempted to work out itself (and get wrong):
    # highest/lowest group, full ranking, and change from first to last period.
    if not isinstance(result, pd.Series) or result.empty:
        return {}
    values = pd.to_numeric(result, errors='coerce').dropna()
    if values.empty:
        return {}
    facts = {'number_of_groups': int(len(values))}
    if isinstance(values.index, pd.DatetimeIndex):
        first, last = values.iloc[0], values.iloc[-1]
        facts.update({
            'first_period': values.index[0].strftime('%Y-%m-%d'), 'first_value': _round(float(first)),
            'last_period': values.index[-1].strftime('%Y-%m-%d'), 'last_value': _round(float(last)),
            'change_first_to_last': _round(float(last - first)),
            'trend': 'up' if last > first else 'down' if last < first else 'flat',
            'peak_period': values.idxmax().strftime('%Y-%m-%d'), 'peak_value': _round(float(values.max())),
            'lowest_period': values.idxmin().strftime('%Y-%m-%d'), 'lowest_value': _round(float(values.min())),
        })
    else:
        ranked = values.sort_values(ascending=False)
        facts.update({
            'highest': {'label': str(ranked.index[0]), 'value': _round(float(ranked.iloc[0]))},
            'lowest': {'label': str(ranked.index[-1]), 'value': _round(float(ranked.iloc[-1]))},
            'ranking_high_to_low': [str(i) for i in ranked.index[:_MAX_ROWS]],
        })
    return facts


def build_context(question: str, function_name: str, params: dict, result) -> dict:
    # Build the structured payload described in the PDF: department, employee count,
    # turnover rate, average tenure/salary, absenteeism %, forecast period, etc. —
    # whatever the routed analytics function actually returned, aggregated only.
    return {
        'question': question,
        'analysis_type': function_name,
        'parameters': _serialize(params),
        'result': _serialize(result),
        'key_facts': key_facts(result),
    }
