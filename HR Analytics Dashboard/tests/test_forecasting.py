import pandas as pd

from core import forecasting


def _rising_series() -> pd.Series:
    idx = pd.date_range('2024-01-31', periods=6, freq='ME')
    return pd.Series([10, 12, 14, 16, 18, 20], index=idx)


def test_forecast_series_linear_trend_continues_upward():
    history = _rising_series()
    fc = forecasting.forecast_series(history, periods=3, method='Linear Trend', freq='ME')

    assert len(fc) == 3
    assert (fc.index > history.index[-1]).all()
    assert fc.iloc[0] > history.iloc[-1]
    assert fc.is_monotonic_increasing


def test_forecast_series_moving_average_uses_trailing_window_mean():
    history = _rising_series()
    fc = forecasting.forecast_series(history, periods=2, method='Moving Average', freq='ME')

    expected = round(history.tail(3).mean(), 2)
    assert list(fc.values) == [expected, expected]


def test_forecast_series_empty_history_returns_empty_series():
    result = forecasting.forecast_series(pd.Series(dtype=float), periods=3, method='Linear Trend', freq='ME')
    assert result.empty


def test_forecast_series_zero_periods_returns_empty_series():
    result = forecasting.forecast_series(_rising_series(), periods=0, method='Linear Trend', freq='ME')
    assert result.empty


def test_forecast_series_never_goes_negative():
    idx = pd.date_range('2024-01-31', periods=4, freq='ME')
    declining = pd.Series([10, 5, 0, -5], index=idx)
    fc = forecasting.forecast_series(declining, periods=3, method='Linear Trend', freq='ME')
    assert (fc >= 0).all()


def test_forecast_summary_reports_upward_direction_and_change():
    history = _rising_series()
    fc = forecasting.forecast_series(history, periods=2, method='Linear Trend', freq='ME')
    summary = forecasting.forecast_summary(history, fc)

    assert summary['direction'] == 'up'
    assert summary['percent_change'] > 0
    assert summary['last_historical'] == 20
    assert len(summary['forecast_points']) == 2
    assert summary['forecast_points'][0]['value'] == float(fc.iloc[0])


def test_forecast_summary_empty_inputs_reports_flat():
    summary = forecasting.forecast_summary(pd.Series(dtype=float), pd.Series(dtype=float))
    assert summary['direction'] == 'flat'
    assert summary['percent_change'] == 0.0
    assert summary['forecast_points'] == []
