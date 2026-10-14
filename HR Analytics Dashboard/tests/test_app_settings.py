import os

from PyQt6.QtCore import QByteArray

from ui.app_settings import AppSettings, MAX_RECENT, SOURCE_DEFAULT, SOURCE_FILES


def make(tmp_path):
    return AppSettings(str(tmp_path / 's.ini'))


def test_defaults_when_nothing_saved(tmp_path):
    s = make(tmp_path)
    assert s.theme == 'light' and s.geometry is None and s.tab_index == 0
    assert s.sidebar_width is None and s.reopen_last is True
    assert s.last_source is None and s.last_paths == [] and s.recent_files == []
    assert s.dashboard_layout is None


def test_values_survive_a_new_instance(tmp_path):
    s = make(tmp_path)
    s.theme = 'dark'
    s.tab_index = 3
    s.sidebar_width = 275
    s.reopen_last = False
    s.geometry = QByteArray(b'\x01\x02\x03')
    s.dashboard_layout = {'kpis': ['Total Employees'], 'multi_mode': False, 'charts': []}
    s.sync()
    t = make(tmp_path)
    assert (t.theme, t.tab_index, t.sidebar_width, t.reopen_last) == ('dark', 3, 275, False)
    assert bytes(t.geometry) == b'\x01\x02\x03'
    assert t.dashboard_layout['kpis'] == ['Total Employees']


def test_invalid_theme_is_ignored(tmp_path):
    s = make(tmp_path)
    s.theme = 'dark'
    s.theme = 'neon'
    assert s.theme == 'dark'


def test_last_data_roundtrip(tmp_path):
    s = make(tmp_path)
    f1, f2 = str(tmp_path / 'a.csv'), str(tmp_path / 'b.xlsx')
    s.set_last_data(SOURCE_FILES, [f1, f2])
    s.sync()
    t = make(tmp_path)
    assert t.last_source == SOURCE_FILES and t.last_paths == [os.path.abspath(f1), os.path.abspath(f2)]
    t.set_last_data(SOURCE_DEFAULT)
    assert t.last_source == SOURCE_DEFAULT and t.last_paths == []
    t.set_last_data(None)
    assert t.last_source is None


def test_recent_files_are_most_recent_first_unique_and_capped(tmp_path):
    s = make(tmp_path)
    paths = [str(tmp_path / f'f{i}.csv') for i in range(MAX_RECENT + 4)]
    for p in paths:
        s.add_recent([p])
    s.add_recent([paths[5]])
    recent = s.recent_files
    assert recent[0] == os.path.abspath(paths[5])
    assert len(recent) == MAX_RECENT and len(set(recent)) == MAX_RECENT
    s.remove_recent(paths[5])
    assert os.path.abspath(paths[5]) not in s.recent_files
    s.clear_recent()
    assert s.recent_files == []


def test_corrupt_values_fall_back_to_defaults(tmp_path):
    s = make(tmp_path)
    s._s.setValue('data/last_paths', '{not json')
    s._s.setValue('dashboard/layout', '[1, 2]')
    s._s.setValue('window/tab_index', 'abc')
    s._s.setValue('data/last_source', 'bogus')
    s._s.setValue('data/recent_files', '"a string"')
    assert s.last_paths == [] and s.dashboard_layout is None and s.tab_index == 0
    assert s.last_source is None and s.recent_files == []


def test_clear_resets_everything(tmp_path):
    s = make(tmp_path)
    s.theme = 'dark'
    s.set_last_data(SOURCE_FILES, ['x.csv'])
    s.clear()
    assert s.theme == 'light' and s.last_source is None
