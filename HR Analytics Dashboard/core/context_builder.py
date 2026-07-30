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


def build_context(question: str, function_name: str, params: dict, result) -> dict:
    # Build the structured payload described in the PDF: department, employee count,
    # turnover rate, average tenure/salary, absenteeism %, forecast period, etc. —
    # whatever the routed analytics function actually returned, aggregated only.
    return {
        'question': question,
        'analysis_type': function_name,
        'parameters': _serialize(params),
        'result': _serialize(result),
    }
