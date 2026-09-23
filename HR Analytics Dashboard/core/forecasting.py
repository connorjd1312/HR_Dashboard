# forecasting.py
# Statistical (non-AI) time-series forecasting used by the Forecasting tab.
# Extends a historical metric series (built by analytics.time_series_data) forward
# by N periods. Pure pandas/numpy — no LLM involvement, matching the client's
# "HR Analytics Engine handles all calculations" architecture.

from __future__ import annotations

import numpy as np
import pandas as pd

from core import analytics

FORECAST_METRICS = list(analytics.TIME_SERIES_METRICS)

FORECAST_METHODS = ['Linear Trend', 'Moving Average']

METHOD_DESCRIPTIONS = {
    'Linear Trend':   'Fits a straight line through the last 2 years and extends it forward. '
                      'Good when numbers are steadily rising or falling.',
    'Moving Average': 'Projects the average of the most recent periods forward. '
                      'Good when numbers go up and down without a clear direction.',
}

METHOD_DESCRIPTIONS = {
    'Linear Trend':   'Fits a straight line through the last 2 years and extends it forward. '
                      'Good when numbers are steadily rising or falling.',
    'Moving Average': 'Projects the average of the most recent periods forward. '
                      'Good when numbers go up and down without a clear direction.',
}

_FREQ_MAP = analytics._FREQ_MAP


def forecast_series(
    history: pd.Series,
    periods: int,
    method: str = 'Linear Trend',
    freq: str = 'ME',
) -> pd.Series:
    # Extrapolate `periods` future points past the last date in `history`.
    if history is None or len(history) == 0 or periods <= 0:
        return pd.Series(dtype=float)

    future_index = pd.date_range(
        start=history.index[-1], periods=periods + 1, freq=freq,
    )[1:]

    if method == 'Moving Average':
        window = min(3, len(history))
        avg = history.tail(window).mean()
        values = [avg] * periods
    else:
        # Linear Trend — fit a straight line to the historical points (ordinal x)
        # and extrapolate it across the future index.
        if len(history) < 2:
            values = [float(history.iloc[-1])] * periods
        else:
            x = np.arange(len(history))
            y = history.to_numpy(dtype=float)
            slope, intercept = np.polyfit(x, y, 1)
            future_x = np.arange(len(history), len(history) + periods)
            values = (slope * future_x + intercept).tolist()

    # Metrics that count events can't go negative
    values = [max(0.0, round(v, 2)) for v in values]
    return pd.Series(values, index=future_index, name='Forecast')


def forecast_summary(history: pd.Series, forecast: pd.Series) -> dict:
    # Direction/percent-change summary shared by the chart panel and the AI context builder,
    # so both surfaces always agree on the same numbers.
    if history is None or len(history) == 0 or forecast is None or len(forecast) == 0:
        return {
            'direction': 'flat',
            'percent_change': 0.0,
            'last_historical': None,
            'forecast_points': [],
        }

    last_historical = float(history.iloc[-1])
    forecast_end = float(forecast.iloc[-1])

    if last_historical == 0:
        percent_change = 0.0 if forecast_end == 0 else 100.0
    else:
        percent_change = round((forecast_end - last_historical) / abs(last_historical) * 100, 1)

    if percent_change > 1:
        direction = 'up'
    elif percent_change < -1:
        direction = 'down'
    else:
        direction = 'flat'

    return {
        'direction': direction,
        'percent_change': percent_change,
        'last_historical': round(last_historical, 2),
        'forecast_points': [
            {'date': idx.strftime('%Y-%m-%d'), 'value': round(float(val), 2)}
            for idx, val in forecast.items()
        ],
    }
