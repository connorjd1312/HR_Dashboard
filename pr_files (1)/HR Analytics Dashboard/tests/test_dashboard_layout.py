from core import analytics, dashboard_layout as dl


def test_reorder_moves_before_target_position():
    items = ['a', 'b', 'c', 'd']
    assert dl.reorder(items, 'a', 3) == ['b', 'c', 'a', 'd']
    assert dl.reorder(items, 'd', 0) == ['d', 'a', 'b', 'c']
    assert dl.reorder(items, 'b', 4) == ['a', 'c', 'd', 'b']
    assert dl.reorder(items, 'b', 1) == items
    assert dl.reorder(items, 'b', 2) == items
    assert dl.reorder(items, 'zzz', 1) == items


def test_reorder_does_not_mutate_input():
    items = ['a', 'b']
    dl.reorder(items, 'a', 2)
    assert items == ['a', 'b']


def test_swap_and_bounds():
    assert dl.swap([1, 2, 3, 4], 0, 3) == [4, 2, 3, 1]
    assert dl.swap([1, 2], 0, 5) == [1, 2]


def test_insertion_index_counts_cards_left_of_pointer():
    centres = [50, 150, 250]
    assert dl.insertion_index(centres, 10) == 0
    assert dl.insertion_index(centres, 100) == 1
    assert dl.insertion_index(centres, 999) == 3


def test_sanitize_drops_unknown_and_duplicate_kpis_but_keeps_order():
    state = {'kpis': ['Average Salary ($)', 'Nonsense', 'Total Employees', 'Average Salary ($)'], 'charts': []}
    assert dl.sanitize_layout(state)['kpis'] == ['Average Salary ($)', 'Total Employees']


def test_sanitize_translates_legacy_kpi_names():
    assert dl.sanitize_layout({'kpis': ['Avg Salary ($)']})['kpis'] == ['Average Salary ($)']


def test_sanitize_allows_all_cards_removed():
    assert dl.sanitize_layout({'kpis': []})['kpis'] == []


def test_sanitize_charts_validates_and_caps():
    good = {'metric': 'Total Employees', 'dimension': 'Status', 'chart_type': 'Pie'}
    bad_metric = {'metric': 'x', 'dimension': 'Status'}
    bad_type = {'metric': 'Total Employees', 'dimension': 'Department', 'chart_type': 'Radar'}
    out = dl.sanitize_layout({'charts': [good, bad_metric, bad_type] + [good] * 6, 'multi_mode': True})
    assert len(out['charts']) == dl.MAX_CHARTS
    assert out['charts'][1]['chart_type'] == 'Auto'
    assert out['multi_mode'] is True


def test_sanitize_garbage_gives_default():
    for junk in (None, 'x', 5, [], {'kpis': 'no', 'charts': 'no'}):
        out = dl.sanitize_layout(junk)
        assert out['charts'] and out['multi_mode'] is False
    assert dl.sanitize_layout(None)['kpis'] == analytics.DEFAULT_KPIS


def test_multi_mode_needs_charts():
    assert dl.sanitize_layout({'multi_mode': True, 'charts': []})['multi_mode'] is False
