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

FORECAST_METHODS = ['Linear Trend', 'Smoothed Trend', 'Moving Average']

METHOD_DESCRIPTIONS = {
    'Linear Trend':   'Fits a straight line through the last 2 years and extends it forward. '
                      'Good when numbers are steadily rising or falling.',
    'Smoothed Trend': 'Follows the recent trend, giving the latest periods the most weight, and '
                      'adjusts as the trend changes. Good when the direction shifts over time.',
    'Moving Average': 'Projects the average of the most recent periods forward. '
                      'Good when numbers go up and down without a clear direction.',
}

# Smoothed Trend is Holt's exponential smoothing with a damped trend. The smoothing
# weights are picked from these grids to best predict each next period of the history;
# damping eases the trend off over time so a long forecast doesn't run away.
_HOLT_ALPHAS = (0.1, 0.2, 0.3, 0.5, 0.7, 0.9)   # weight on the latest value
_HOLT_BETAS = (0.05, 0.1, 0.2, 0.3)              # weight on the latest change
_HOLT_DAMPING = 0.9

# The likely range covers 80% of outcomes if past forecast errors are a guide
_RANGE_Z = 1.28
RANGE_LABEL = 'Likely range (80%)'

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
    values, _errors = _fit(history.to_numpy(dtype=float), periods, method)

    # Metrics that count events can't go negative
    values = [max(0.0, round(float(v), 2)) for v in values]
    return pd.Series(values, index=future_index, name='Forecast')


def forecast_range(
    history: pd.Series,
    periods: int,
    method: str = 'Linear Trend',
    freq: str = 'ME',
) -> pd.DataFrame:
    # Lower/Upper bounds around forecast_series(), from how far the same method's
    # one-step predictions missed across the history. Widens further ahead.
    forecast = forecast_series(history, periods, method, freq)
    if len(forecast) == 0:
        return pd.DataFrame(columns=['Lower', 'Upper'], dtype=float)

    _values, errors = _fit(history.to_numpy(dtype=float), periods, method)
    spread = float(np.sqrt(np.mean(errors ** 2))) if len(errors) >= 2 else 0.0
    width = _RANGE_Z * spread * np.sqrt(np.arange(1, len(forecast) + 1))
    return pd.DataFrame({
        'Lower': np.maximum(0.0, forecast.to_numpy() - width).round(2),
        'Upper': (forecast.to_numpy() + width).round(2),
    }, index=forecast.index)


def _fit(y: np.ndarray, periods: int, method: str) -> tuple[np.ndarray, np.ndarray]:
    # Returns (future values, in-sample one-step errors) for the chosen method.
    if method == 'Moving Average':
        window = min(3, len(y))
        values = np.full(periods, y[-window:].mean())
        errors = np.array([y[t] - y[max(0, t - window):t].mean() for t in range(1, len(y))])
        return values, errors

    if method == 'Smoothed Trend' and len(y) >= 3:
        best = None
        for alpha in _HOLT_ALPHAS:
            for beta in _HOLT_BETAS:
                level, trend, errors = _holt(y, alpha, beta)
                sse = float(np.sum(errors ** 2))
                if best is None or sse < best[0]:
                    best = (sse, level, trend, errors)
        _sse, level, trend, errors = best
        damp = np.cumsum(_HOLT_DAMPING ** np.arange(1, periods + 1))
        return level + damp * trend, errors

    # Linear Trend — fit a straight line to the historical points (ordinal x)
    # and extrapolate it across the future index. Also the fallback when there
    # are too few points to smooth.
    if len(y) < 2:
        return np.full(periods, y[-1]), np.array([])
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    future_x = np.arange(len(y), len(y) + periods)
    return slope * future_x + intercept, y - (slope * x + intercept)


def _holt(y: np.ndarray, alpha: float, beta: float) -> tuple[float, float, np.ndarray]:
    # Damped Holt smoothing over y; returns the final level and trend plus the
    # error of each one-step-ahead prediction.
    level, trend = y[0], y[1] - y[0]
    errors = []
    for value in y[1:]:
        predicted = level + _HOLT_DAMPING * trend
        errors.append(value - predicted)
        new_level = alpha * value + (1 - alpha) * predicted
        trend = beta * (new_level - level) + (1 - beta) * _HOLT_DAMPING * trend
        level = new_level
    return level, trend, np.array(errors)


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
            {'date': idx.strftime('%Y-%m-%d'), 'value': round(float(val), 1)}
            for idx, val in forecast.items()
        ],
    }
