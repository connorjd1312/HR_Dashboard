import matplotlib as mpl
import pandas as pd
import pytest

from core import analytics, report_generator as rg
from tests._data import make_df


@pytest.fixture(scope='module')
def df():
    return make_df()


def _data(df, **kw):
    return rg.ReportData(df=df, scope='All loaded data', history_df=df,
                         kpis=rg.compute_kpis(df, analytics.DEFAULT_KPIS), **kw)


def _pdf_text(path) -> str:
    raw = open(path, 'rb').read()
    return raw.decode('latin-1')


def test_report_is_a_valid_multi_page_pdf(df, tmp_path):
    path = tmp_path / 'r.pdf'
    pages = rg.generate_report(str(path), _data(df, chart_configs=[
        {'metric': 'Total Employees', 'dimension': 'Department', 'chart_type': 'Auto'}]))
    raw = path.read_bytes()
    assert raw.startswith(b'%PDF') and raw.rstrip().endswith(b'%%EOF')
    assert pages >= 2
    assert b'/Count %d' % pages in raw


def test_options_remove_sections(df, tmp_path):
    full, slim = tmp_path / 'full.pdf', tmp_path / 'slim.pdf'
    rg.generate_report(str(full), _data(df))
    n = rg.generate_report(str(slim), _data(df), rg.ReportOptions(
        include_dashboard_charts=False, include_overview_charts=False, include_analytics_charts=False))
    assert n == 1
    assert slim.stat().st_size < full.stat().st_size


def test_title_is_in_pdf_metadata(df, tmp_path):
    path = tmp_path / 'r.pdf'
    rg.generate_report(str(path), _data(df), rg.ReportOptions(title='Q4 Board Pack'))
    assert 'Q4 Board Pack' in _pdf_text(path)


def test_analytics_charts_are_drawn_via_callbacks_and_failures_dont_abort(df, tmp_path):
    calls = []

    def good(fig):
        calls.append('good')
        fig.add_subplot(111).plot([1, 2, 3])

    def bad(fig):
        calls.append('bad')
        raise RuntimeError('boom')

    path = tmp_path / 'r.pdf'
    rg.generate_report(str(path), _data(df, analytics_charts=[('A', good), ('B', bad)]))
    assert calls == ['good', 'bad'] and path.stat().st_size > 1000


def test_report_ignores_the_apps_current_chart_style(df, tmp_path):
    before = dict(mpl.rcParams)
    mpl.rcParams['figure.facecolor'] = '#101010'
    try:
        rg.generate_report(str(tmp_path / 'r.pdf'), _data(df))
        assert mpl.rcParams['figure.facecolor'] == '#101010'
    finally:
        mpl.rcParams.update(before)


def test_small_or_odd_data_still_produces_a_report(df, tmp_path):
    tiny = df.head(3)
    rg.generate_report(str(tmp_path / 'tiny.pdf'), _data(tiny))
    empty_kpis = rg.ReportData(df=tiny, scope='x', kpis=[])
    assert rg.generate_report(str(tmp_path / 'nok.pdf'), empty_kpis) >= 1


def test_kpis_with_previous_period_carry_a_change(df):
    prev = df.head(100)
    kpis = rg.compute_kpis(df, ['Total Employees', 'Average Salary ($)'], prev)
    assert kpis[0].value == f'{len(df):,}'
    assert kpis[0].change and kpis[0].change[1] in ('good', 'bad', 'neutral')
    assert rg.compute_kpis(df, ['Total Employees'])[0].change is None


class TestHighlights:
    def test_content_and_numbers(self, df):
        lines = rg.build_highlights(df, df, pd.Timestamp.today())
        text = ' '.join(lines)
        assert 'largest department' in text and 'hires' in text and 'active' in text
        start = pd.Timestamp.today() - pd.DateOffset(months=12)
        hires = int(((df['Hire_Date'] > start) & (df['Hire_Date'] <= pd.Timestamp.today())).sum())
        assert f'{hires:,} hires' in text

    def test_small_groups_are_not_ranked(self, df):
        tiny = df.groupby('Department').head(3)
        assert not any('Turnover is highest' in l for l in rg.build_highlights(tiny))

    def test_empty(self):
        assert rg.build_highlights(pd.DataFrame()) == []
