import os

import pytest
from PyQt6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QPushButton

from core import analytics, chart_generator as cg
from tests._data import write_csv
from ui import main_window as mw, theme
from ui.app_settings import AppSettings, SOURCE_DEFAULT, SOURCE_FILES
from ui.drag_drop import KPI_MIME, PANEL_MIME


@pytest.fixture(scope='session')
def app():
    a = QApplication.instance() or QApplication([])
    a.setStyle('Fusion')
    return a


def pump(app, n=6):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def defaults_dir(tmp_path, monkeypatch):
    d = tmp_path / 'Default documents'
    d.mkdir()
    write_csv(d / 'default.csv')
    monkeypatch.setattr(mw, 'DEFAULT_DOCS_DIR', d)
    return d


@pytest.fixture
def make_window(app, tmp_path, defaults_dir):
    created = []

    def factory(settings=None):
        s = settings or AppSettings(str(tmp_path / 'settings.ini'))
        w = mw.MainWindow(s)
        if s.geometry is None:
            w.resize(1300, 800)
        w.show()
        pump(app)
        created.append(w)
        return w

    yield factory
    for w in created:
        w.close()
        w.deleteLater()
    # Delete windows for real, or later theme switches restyle their widgets too.
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    theme.set_mode(QApplication.instance(), 'light')


@pytest.fixture
def window(make_window):
    return make_window()


class TestLayoutBudget:

    def test_window_still_fits_a_1280_pixel_screen(self, window, app):
        # The app is sized for 1280px screens; wider tabs squeeze the sidebar.
        assert window.minimumSizeHint().width() <= 1280
        window.resize(1280, 800)
        pump(app)
        assert window.splitter.sizes()[0] >= 200

    def test_compare_mode_is_no_wider_than_the_original(self, window, app):
        # Measured on the unmodified project: 1174px. The drag handles must not raise it.
        window.dashboard_tab._toggle_multi_mode()
        pump(app)
        assert window.dashboard_tab.minimumSizeHint().width() <= 1174

    def test_new_tabs_do_not_widen_the_window(self, window):
        for tab in (window.employees_tab, window.analytics_tab, window.dashboard_tab):
            assert tab.minimumSizeHint().width() <= 1000


class TestUndoRedo:

    def test_starts_with_nothing_to_undo(self, window):
        tab = window.analytics_tab
        assert not tab._undo_btn.isEnabled() and not tab._redo_btn.isEnabled()

    def test_undo_and_redo_series_edits(self, window, app):
        tab = window.analytics_tab
        tab._add_template(next(iter(__import__('ui.series_dialog', fromlist=['x']).TEMPLATES)))
        n = len(tab._active_series())
        assert n > 0 and tab._undo_btn.isEnabled()
        tab._delete_series(0)
        assert len(tab._active_series()) == n - 1
        tab._undo()
        assert len(tab._active_series()) == n
        assert tab._redo_btn.isEnabled()
        tab._undo()
        assert len(tab._active_series()) == 0
        tab._redo()
        tab._redo()
        assert len(tab._active_series()) == n - 1
        assert not tab._redo_btn.isEnabled()

    def test_new_edit_clears_redo(self, window):
        tab = window.analytics_tab
        tab._add_new_chart()
        tab._undo()
        assert tab._redo_btn.isEnabled()
        tab._add_new_chart()
        assert not tab._redo_btn.isEnabled()

    def test_undoing_a_chart_deletion_brings_it_back_and_selects_it(self, window):
        tab = window.analytics_tab
        tab._add_template(next(iter(__import__('ui.series_dialog', fromlist=['x']).TEMPLATES)))
        first_id = tab._charts[0]['id']
        tab._add_new_chart()
        assert len(tab._charts) == 2 and tab._active_idx == 1
        tab._set_active_chart(0)
        tab._delete_chart(0)
        assert [c['id'] for c in tab._charts] != [first_id]
        tab._undo()
        assert len(tab._charts) == 2
        assert tab._charts[tab._active_idx]['id'] == first_id
        assert tab._title_edit.text() == tab._charts[tab._active_idx]['title']

    def test_rename_is_one_step_not_one_per_keystroke(self, window):
        tab = window.analytics_tab
        before = len(tab._history)
        tab._title_edit.setFocus()
        for ch in 'Board pack':
            QTest.keyClick(tab._title_edit, ch)
        assert len(tab._history) == before
        tab._title_edit.editingFinished.emit()
        assert len(tab._history) == before + 1
        tab._undo()
        assert tab._title_edit.text() == 'Chart 1'

    def test_selecting_a_chart_is_not_an_undo_step(self, window):
        tab = window.analytics_tab
        tab._add_new_chart()
        steps = len(tab._history)
        tab._set_active_chart(0)
        tab._set_active_chart(1)
        assert len(tab._history) == steps

    def test_keyboard_shortcuts(self, window, app):
        tab = window.analytics_tab
        window.tab_widget.setCurrentWidget(tab)
        tab._add_new_chart()
        tab.setFocus()
        pump(app)
        QTest.keyClick(tab, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert len(tab._charts) == 1
        QTest.keyClick(tab, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        assert len(tab._charts) == 2

    def test_tooltips_name_the_action(self, window):
        tab = window.analytics_tab
        tab._add_new_chart()
        assert 'New chart' in tab._undo_btn.toolTip()
        tab._undo()
        assert 'New chart' in tab._redo_btn.toolTip()


class _FakeClient:
    def __init__(self, reply):
        self.reply = reply

    def is_available(self):
        return True

    def chat(self, model, messages, json_mode=False, max_tokens=None):
        import json
        return json.dumps(self.reply)


class TestDescribeChart:

    def _dialog(self, window, client=None):
        from ui.chart_prompt_dialog import ChartPromptDialog
        tab = window.analytics_tab
        return ChartPromptDialog(tab._df, client, preview_fn=tab._suggestion_pixmap, parent=window)

    def _generate(self, dlg, text, app):
        dlg._prompt.setPlainText(text)
        dlg._generate()
        dlg._worker.wait(10000)
        pump(app, 10)

    def test_generate_shows_interpretation_and_enables_add(self, window, app):
        dlg = self._dialog(window)
        assert not dlg._generate_btn.isEnabled()
        dlg._prompt.setPlainText('turnover by department')
        assert dlg._generate_btn.isEnabled()
        self._generate(dlg, 'turnover by department', app)
        assert dlg.suggestion() is not None and dlg._add_btn.isEnabled()
        assert 'Department' in dlg._result_detail.text()
        assert not dlg._preview.pixmap().isNull()

    def test_unrecognised_request_shows_message_and_keeps_add_disabled(self, window, app):
        dlg = self._dialog(window)
        self._generate(dlg, 'show me something nice', app)
        assert dlg.suggestion() is None and not dlg._add_btn.isEnabled()
        assert 'measure' in dlg._status.text().lower()

    def test_uses_the_ai_client_when_available(self, window, app):
        spec = {'title': 'AI title', 'series': [{'view': 'snapshot', 'metric': 'Average Salary ($)',
                                                  'group_by': 'Job Role', 'style': 'Horizontal Bar'}]}
        dlg = self._dialog(window, _FakeClient(spec))
        self._generate(dlg, 'whatever', app)
        assert dlg.suggestion().engine == 'ai' and dlg.suggestion().title == 'AI title'
        assert 'AI model' in dlg._engine.text()

    def test_adding_to_current_chart_is_one_undo_step_with_distinct_colours(self, window):
        tab = window.analytics_tab
        existing = cg.suggest_chart('hires last year', tab._df)
        tab._apply_suggestion(existing, 'current')
        steps = len(tab._history)
        more = cg.suggest_chart('departures last year', tab._df)
        tab._apply_suggestion(more, 'current')
        assert len(tab._history) == steps + 1
        colours = [s['color'] for s in tab._active_series()]
        assert len(colours) == len(set(colours)) == 2
        tab._undo()
        assert len(tab._active_series()) == 1

    def test_add_as_new_chart_is_one_undo_step(self, window):
        tab = window.analytics_tab
        steps = len(tab._history)
        tab._apply_suggestion(cg.suggest_chart('hires vs departures', tab._df), 'new')
        assert len(tab._charts) == 2 and tab._charts[1]['title'] == 'Hires vs Departures'
        assert len(tab._charts[1]['series_list']) == 2
        assert len(tab._history) == steps + 1
        tab._undo()
        assert len(tab._charts) == 1

    def test_generated_series_draw_without_error(self, window, app):
        tab = window.analytics_tab
        for text in ['hires by department', 'average salary by job role', 'headcount by status pie chart']:
            tab._apply_suggestion(cg.suggest_chart(text, tab._df), 'new')
            pump(app)
            assert tab._main_widget.figure.axes, text

    def test_describe_with_no_data_is_harmless(self, make_window, defaults_dir):
        for f in defaults_dir.iterdir():
            f.unlink()
        w = make_window()
        assert w._df_full is None


class TestTheme:

    def test_stylesheets_are_translated_and_restored(self, app):
        btn = QPushButton('x')
        original = 'background: white; color: #333; border: 1px solid #E0E0E0;'
        btn.setStyleSheet(original)
        theme.set_mode(app, 'dark')
        try:
            dark = btn.styleSheet()
            assert dark != original and '#1F2633' in dark and 'white' not in dark.split('color:')[0]
            theme.set_mode(app, 'light')
            assert btn.styleSheet() == original
            theme.set_mode(app, 'dark')
            assert btn.styleSheet() == dark
        finally:
            theme.set_mode(app, 'light')

    def test_widgets_created_while_dark_are_translated_too(self, app):
        theme.set_mode(app, 'dark')
        try:
            b = QPushButton('late')
            b.setStyleSheet('QPushButton { background: white; color: #333; }')
            assert 'white' not in b.styleSheet() and '#E6EAF2' in b.styleSheet()
        finally:
            theme.set_mode(app, 'light')

    def test_white_text_on_navy_is_left_alone(self):
        theme._resolved_mode = 'dark'
        try:
            assert theme.adapt_qss('QFrame { background: #1F3864; color: white; }') == \
                'QFrame { background: #1F3864; color: white; }'
        finally:
            theme._resolved_mode = 'light'

    def test_light_mode_changes_nothing(self):
        css = 'QFrame { background: white; color: #333; }'
        assert theme.adapt_qss(css) == css

    def test_palette_and_chart_style_follow_mode(self, app):
        import matplotlib as mpl
        theme.set_mode(app, 'dark')
        try:
            assert app.palette().window().color().value() < 80
            assert mpl.rcParams['figure.facecolor'] == theme.DARK['surface']
            assert theme.chart_color('#1F3864') != '#1F3864'
        finally:
            theme.set_mode(app, 'light')
        assert mpl.rcParams['figure.facecolor'] == 'white'
        assert theme.chart_color('#1F3864') == '#1F3864'

    def test_report_style_is_light_even_while_app_is_dark(self, app):
        import matplotlib as mpl
        from core import report_generator as rg
        theme.set_mode(app, 'dark')
        try:
            with mpl.rc_context(rg.LIGHT_RC):
                assert theme.chart_color('#1F3864') == '#1F3864'
                assert theme.chart_palette() == theme.CHART_COLORS
        finally:
            theme.set_mode(app, 'light')

    def test_window_switch_redraws_everything_and_is_remembered(self, window, app):
        window._set_theme('dark')
        pump(app)
        assert theme.is_dark() and window._settings.theme == 'dark'
        assert window._theme_actions['dark'].isChecked()
        for panel in window.dashboard_tab._chart_panels:
            assert panel.chart.figure.get_facecolor()[:3] != (1.0, 1.0, 1.0)
        window.tab_widget.setCurrentWidget(window.analytics_tab)
        window.analytics_tab._apply_suggestion(cg.suggest_chart('hires', window.analytics_tab._df), 'current')
        pump(app)
        assert window.analytics_tab._main_widget.figure.get_facecolor()[:3] != (1.0, 1.0, 1.0)
        window._toggle_theme()
        assert not theme.is_dark() and window._settings.theme == 'light'

    def test_saved_theme_is_applied_on_start(self, make_window, tmp_path):
        s = AppSettings(str(tmp_path / 'dark.ini'))
        s.theme = 'dark'
        make_window(s)
        assert theme.is_dark()

    def test_follow_system_resolves_without_error(self, window):
        window._set_theme('system')
        assert theme.current_setting() == 'system'


class TestEmployees:

    def test_search_filters_the_list(self, window, app):
        tab = window.employees_tab
        everyone = tab._table.rowCount()
        assert everyone == len(window._df_full)
        tab._search.setText('sales')
        tab._run_search()
        assert 0 < tab._table.rowCount() < everyone
        names = {tab._table.item(r, 1).text() for r in range(tab._table.rowCount())}
        assert 'Sales' in names or any('Sales' in tab._table.item(r, 2).text() for r in range(tab._table.rowCount()))
        tab._search.setText('zzzzzz')
        tab._run_search()
        assert tab._table.rowCount() == 0 and 'No employees' in tab._count.text()

    def test_department_and_status_filters(self, window):
        tab = window.employees_tab
        tab._dept.setCurrentIndex(tab._dept.findData('Sales'))
        tab._status.setCurrentIndex(tab._status.findData('Active'))
        for r in range(tab._table.rowCount()):
            assert tab._table.item(r, 1).text() == 'Sales' and tab._table.item(r, 3).text() == 'Active'

    def test_selecting_a_row_shows_that_persons_profile(self, window):
        from PyQt6.QtWidgets import QLabel
        tab = window.employees_tab
        tab._table.selectRow(0)
        key = tab._table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        name = window._df_full.loc[key, 'Name']
        texts = [l.text() for l in tab._profile.findChildren(QLabel)]
        assert name in texts
        assert any(t.startswith('Compared with') for t in texts)

    def test_show_employee_finds_and_selects_even_with_duplicate_names(self, window):
        tab = window.employees_tab
        df = window._df_full
        dup = df[df['Name'].duplicated(keep=False)]
        key = (dup if len(dup) else df).index[-1]
        assert tab.show_employee(key)
        sel = tab._table.selectionModel().selectedRows()[0].row()
        assert tab._table.item(sel, 0).data(Qt.ItemDataRole.UserRole) == key

    def test_unknown_employee_is_ignored(self, window):
        assert window.employees_tab.show_employee(10 ** 9) is False

    def test_double_click_in_dashboard_table_opens_profile(self, window, app):
        dash = window.dashboard_tab
        table = dash._build_employee_table(window._df_full.head(5))
        table.show()
        got = []
        dash.employee_requested.connect(got.append)
        table.cellDoubleClicked.emit(2, 0)
        assert got == [window._df_full.head(5).index[2]]
        window._show_employee(got[0])
        assert window.tab_widget.currentWidget() is window.employees_tab
        table.deleteLater()

    def test_find_shortcut_action_focuses_search(self, window, app):
        window._find_employee()
        pump(app)
        assert window.tab_widget.currentWidget() is window.employees_tab
        assert window.employees_tab._search.hasFocus()

    def test_new_data_resets_the_tab(self, window):
        tab = window.employees_tab
        tab._table.selectRow(0)
        tab.update_data(None)
        assert tab._table.rowCount() == 0


def _drop(widget, mime_type, payload, pos):
    mime = QMimeData()
    mime.setData(mime_type, payload.encode())
    ev = QDropEvent(QPointF(pos), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier)
    widget.dropEvent(ev)


class TestDragAndDrop:

    def test_dropping_a_kpi_card_reorders_the_row(self, window, app):
        dash = window.dashboard_tab
        before = list(dash._kpi_metrics)
        row = dash._kpi_widget
        last = row._cards()[-1].geometry()
        _drop(row, KPI_MIME, before[0], QPoint(last.right() + 5, 10))
        pump(app)
        assert dash._kpi_metrics == before[1:] + before[:1]
        shown = [c._metric for c in row._cards()]
        assert shown == dash._kpi_metrics

    def test_dropping_at_the_start_moves_a_card_first(self, window, app):
        dash = window.dashboard_tab
        before = list(dash._kpi_metrics)
        _drop(dash._kpi_widget, KPI_MIME, before[-1], QPoint(0, 10))
        pump(app)
        assert dash._kpi_metrics == before[-1:] + before[:-1]

    def test_dropping_a_card_where_it_is_changes_nothing(self, window, app):
        dash = window.dashboard_tab
        before = list(dash._kpi_metrics)
        _drop(dash._kpi_widget, KPI_MIME, before[0], QPoint(0, 10))
        pump(app)
        assert dash._kpi_metrics == before

    def test_unrelated_drops_are_ignored(self, window, app):
        dash = window.dashboard_tab
        before = list(dash._kpi_metrics)
        _drop(dash._kpi_widget, 'text/plain', 'x', QPoint(5, 5))
        pump(app)
        assert dash._kpi_metrics == before

    def test_kpi_click_still_opens_the_breakdown_but_a_drag_does_not(self, window, app, monkeypatch):
        from ui import kpi_card
        card = window.dashboard_tab._kpi_widget._cards()[0]
        clicks = []
        card.clicked.connect(clicks.append)
        QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=QPoint(20, 40))
        assert clicks == [card._metric]

        started = []
        monkeypatch.setattr(kpi_card, 'start_drag', lambda *a, **k: started.append(a[1:]))
        QTest.mousePress(card, Qt.MouseButton.LeftButton, pos=QPoint(20, 40))
        QTest.mouseMove(card, QPoint(120, 60))
        QTest.mouseRelease(card, Qt.MouseButton.LeftButton, pos=QPoint(120, 60))
        assert started and started[0][0] == KPI_MIME
        assert clicks == [card._metric]

    def _two_charts(self, dash, app):
        dash._toggle_multi_mode()
        pump(app)
        assert len(dash._chart_panels) >= 2

    def test_chart_handles_appear_only_with_several_charts(self, window, app):
        dash = window.dashboard_tab
        assert not dash._chart_panels[0]._drag_handle.isVisibleTo(dash)
        self._two_charts(dash, app)
        assert all(p._drag_handle.isVisibleTo(dash) for p in dash._chart_panels)

    def test_dropping_one_chart_on_another_swaps_them(self, window, app):
        dash = window.dashboard_tab
        self._two_charts(dash, app)
        a, b = dash._chart_panels[0], dash._chart_panels[1]
        cfg_a, cfg_b = a.current_config(), b.current_config()
        _drop(b, PANEL_MIME, str(id(a)), QPoint(10, 10))
        pump(app)
        assert dash._chart_panels[0] is b and dash._chart_panels[1] is a
        assert [p.current_config() for p in dash._chart_panels[:2]] == [cfg_b, cfg_a]
        assert a.isVisible() and b.isVisible()

    def test_dropping_a_chart_on_itself_or_a_stranger_does_nothing(self, window, app):
        dash = window.dashboard_tab
        self._two_charts(dash, app)
        order = list(dash._chart_panels)
        _drop(order[0], PANEL_MIME, str(id(order[0])), QPoint(5, 5))
        _drop(order[0], PANEL_MIME, '12345', QPoint(5, 5))
        pump(app)
        assert dash._chart_panels == order

    def test_layout_changes_are_announced(self, window, app):
        dash = window.dashboard_tab
        seen = []
        dash.layout_changed.connect(lambda: seen.append(1))
        dash._on_kpi_removed(dash._kpi_metrics[0])
        dash._toggle_multi_mode()
        assert len(seen) >= 2

    def test_layout_round_trip_and_reset(self, window, app):
        dash = window.dashboard_tab
        dash._toggle_multi_mode()
        dash._on_kpi_removed(dash._kpi_metrics[0])
        state = dash.layout_state()
        dash.reset_layout()
        assert dash._kpi_metrics == analytics.DEFAULT_KPIS and not dash._multi_mode
        assert len(dash._chart_panels) == 1
        dash.restore_layout(state)
        assert dash.layout_state() == state and dash._multi_mode

    def test_restore_ignores_invalid_saved_layout(self, window):
        dash = window.dashboard_tab
        dash.restore_layout({'kpis': ['Nope', 'Total Employees'], 'charts': [{'metric': 'x'}], 'multi_mode': True})
        assert dash._kpi_metrics == ['Total Employees']
        assert len(dash._chart_panels) == 1 and not dash._multi_mode


class TestReportExport:

    def _patch(self, monkeypatch, tmp_path, use_dashboard=True, accept=True, answer='No'):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from ui import report_dialog

        out = str(tmp_path / 'summary')
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: (out, '')))
        monkeypatch.setattr(report_dialog.ReportDialog, 'exec',
                            lambda self: QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected)
        monkeypatch.setattr(report_dialog.ReportDialog, 'use_dashboard_scope', lambda self: use_dashboard)
        asked = []
        monkeypatch.setattr(mw.message_box, 'question',
                            lambda *a, **k: asked.append(a) or QMessageBox.StandardButton.No)
        return out + '.pdf', asked

    def test_exports_a_pdf_for_the_dashboard_view(self, window, tmp_path, monkeypatch):
        path, asked = self._patch(monkeypatch, tmp_path)
        window.tab_widget.setCurrentWidget(window.analytics_tab)
        window.analytics_tab._apply_suggestion(cg.suggest_chart('hires vs departures', window.analytics_tab._df), 'current')
        window._export_report()
        raw = open(path, 'rb').read()
        assert raw.startswith(b'%PDF') and len(raw) > 5000
        assert asked and 'Open it now' in asked[0][2]
        assert window._settings.report_dir == str(tmp_path)

    def test_exports_all_data_scope(self, window, tmp_path, monkeypatch):
        path, _ = self._patch(monkeypatch, tmp_path, use_dashboard=False)
        window._export_report()
        assert os.path.getsize(path) > 5000

    def test_cancelling_the_dialog_writes_nothing(self, window, tmp_path, monkeypatch):
        path, _ = self._patch(monkeypatch, tmp_path, accept=False)
        window._export_report()
        assert not os.path.exists(path)

    def test_no_data_is_handled(self, make_window, defaults_dir, monkeypatch):
        for f in defaults_dir.iterdir():
            f.unlink()
        w = make_window()
        shown = []
        monkeypatch.setattr(mw.message_box, 'information', lambda *a, **k: shown.append(a))
        w._export_report()
        assert shown

    def test_filters_matching_nobody_are_explained(self, window, tmp_path, monkeypatch):
        path, _ = self._patch(monkeypatch, tmp_path)
        shown = []
        monkeypatch.setattr(mw.message_box, 'warning', lambda *a, **k: shown.append(a))
        window.dashboard_tab._df = window._df_full.iloc[0:0]
        window._export_report()
        assert shown and not os.path.exists(path)

    def test_write_failure_is_reported_not_raised(self, window, tmp_path, monkeypatch):
        self._patch(monkeypatch, tmp_path)
        shown = []
        monkeypatch.setattr(mw.message_box, 'critical', lambda *a, **k: shown.append(a))
        monkeypatch.setattr(mw.report_generator, 'generate_report',
                            lambda *a, **k: (_ for _ in ()).throw(PermissionError('file is open')))
        window._export_report()
        assert shown and 'file is open' in shown[0][2]
        assert QApplication.overrideCursor() is None

    def test_dialog_reflects_what_is_available(self, app):
        from ui.report_dialog import ReportDialog
        d = ReportDialog(kpi_count=6, dashboard_chart_count=2, analytics_chart_count=0, dashboard_scope='scope text')
        assert not d._analytics.isEnabled() and not d._analytics.isChecked()
        assert d._kpis.isChecked() and d.use_dashboard_scope()
        opts = d.options()
        assert opts.include_kpis and opts.include_dashboard_charts and not opts.include_analytics_charts
        d._title.setText('  ')
        assert d.options().title == 'HR Workforce Summary'


class TestPersistence:

    def test_window_tab_sidebar_and_layout_are_restored(self, make_window, tmp_path, app, monkeypatch):
        ini = str(tmp_path / 'p.ini')
        w1 = make_window(AppSettings(ini))
        w1.resize(1350, 820)
        w1.tab_widget.setCurrentWidget(w1.employees_tab)
        w1._sidebar_width = 260
        w1.dashboard_tab._on_kpi_removed(w1.dashboard_tab._kpi_metrics[0])
        w1.dashboard_tab._toggle_multi_mode()
        expected_layout = w1.dashboard_tab.layout_state()
        saved_geometry = bytes(w1.saveGeometry())
        w1.close()
        assert bytes(AppSettings(ini).geometry) == saved_geometry

        # Qt clamps restored geometry to the screen, so compare the saved bytes, not the size.
        handed_back = []
        original = mw.MainWindow.restoreGeometry
        monkeypatch.setattr(mw.MainWindow, 'restoreGeometry',
                            lambda self, g: handed_back.append(bytes(g)) or original(self, g))
        w2 = make_window(AppSettings(ini))
        assert handed_back == [saved_geometry]
        assert w2.tab_widget.currentWidget() is w2.employees_tab
        assert w2._sidebar_width == 260
        assert w2.dashboard_tab.layout_state() == expected_layout

    def test_layout_changes_are_saved_immediately(self, window, tmp_path):
        dash = window.dashboard_tab
        dash._on_kpi_removed(dash._kpi_metrics[0])
        assert window._settings.dashboard_layout['kpis'] == dash._kpi_metrics

    def test_user_opened_files_are_reopened_next_time(self, make_window, tmp_path):
        ini = str(tmp_path / 'f.ini')
        mine = write_csv(tmp_path / 'mine.csv', n=60, seed=5)
        w1 = make_window(AppSettings(ini))
        assert len(w1._df_full) == 240 and w1._settings.last_source == SOURCE_DEFAULT
        w1._load_paths([mine])
        assert w1._settings.last_source == SOURCE_FILES and w1._settings.last_paths == [os.path.abspath(mine)]
        w1.close()
        w2 = make_window(AppSettings(ini))
        assert len(w2._df_full) == 60
        assert 'Reopened' in w2.statusBar().currentMessage()

    def test_appended_files_are_remembered_with_the_originals(self, make_window, tmp_path, defaults_dir):
        ini = str(tmp_path / 'a.ini')
        extra = write_csv(tmp_path / 'extra.csv', n=40, seed=9)
        w1 = make_window(AppSettings(ini))
        w1._load_paths([extra], append=True)
        assert len(w1._settings.last_paths) == 2 and w1._settings.last_source == SOURCE_FILES
        w1.close()
        w2 = make_window(AppSettings(ini))
        assert w2._file_count == 2

    def test_missing_remembered_file_falls_back_to_default_documents(self, make_window, tmp_path):
        ini = str(tmp_path / 'm.ini')
        s = AppSettings(ini)
        s.set_last_data(SOURCE_FILES, [str(tmp_path / 'gone.csv')])
        s.sync()
        w = make_window(AppSettings(ini))
        assert len(w._df_full) == 240

    def test_unreadable_remembered_file_falls_back_without_an_error_box(self, make_window, tmp_path, monkeypatch):
        bad = tmp_path / 'bad.csv'
        bad.write_text('this,is\nnot,hr data')
        ini = str(tmp_path / 'u.ini')
        s = AppSettings(ini)
        s.set_last_data(SOURCE_FILES, [str(bad)])
        s.sync()
        boxes = []
        monkeypatch.setattr(mw.message_box, 'critical', lambda *a, **k: boxes.append(a))
        w = make_window(AppSettings(ini))
        assert len(w._df_full) == 240 and not boxes

    def test_some_missing_files_load_the_rest_and_say_so(self, make_window, tmp_path):
        ini = str(tmp_path / 's.ini')
        mine = write_csv(tmp_path / 'mine.csv', n=30, seed=2)
        s = AppSettings(ini)
        s.set_last_data(SOURCE_FILES, [mine, str(tmp_path / 'gone.csv')])
        s.sync()
        w = make_window(AppSettings(ini))
        assert len(w._df_full) == 30 and 'could not be found' in w.statusBar().currentMessage()

    def test_reopen_can_be_turned_off(self, make_window, tmp_path):
        ini = str(tmp_path / 'o.ini')
        mine = write_csv(tmp_path / 'mine.csv', n=30, seed=2)
        s = AppSettings(ini)
        s.set_last_data(SOURCE_FILES, [mine])
        s.reopen_last = False
        s.sync()
        assert len(make_window(AppSettings(ini))._df_full) == 240

    def test_recent_files_menu_lists_and_reopens(self, make_window, tmp_path, app):
        mine = write_csv(tmp_path / 'recent_me.csv', n=25, seed=4)
        w = make_window()
        w._load_paths([mine])
        w._fill_recent_menu()
        actions = [a for a in w._recent_menu.actions() if a.text() == 'recent_me.csv']
        assert actions
        w._load_paths([write_csv(tmp_path / 'other.csv', n=10)])
        actions[0].trigger()
        assert len(w._df_full) == 25

    def test_missing_recent_file_is_dropped_from_the_list(self, window, tmp_path, monkeypatch):
        window._settings.add_recent([str(tmp_path / 'ghost.csv')])
        warned = []
        monkeypatch.setattr(mw.message_box, 'warning', lambda *a, **k: warned.append(a))
        window._open_recent(str(tmp_path / 'ghost.csv'))
        assert warned and str(tmp_path / 'ghost.csv') not in window._settings.recent_files

    def test_returning_to_the_welcome_page_forgets_the_files(self, window):
        window._reset_to_welcome()
        assert window._settings.last_source is None

    def test_forget_settings_resets_everything(self, window, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox
        window._settings.theme = 'dark'
        monkeypatch.setattr(mw.message_box, 'question', lambda *a, **k: QMessageBox.StandardButton.Yes)
        window._forget_settings()
        assert window._settings.theme == 'light' and window._settings.last_source is None

    def test_corrupt_saved_layout_cannot_stop_startup(self, make_window, tmp_path):
        ini = str(tmp_path / 'c.ini')
        s = AppSettings(ini)
        s._s.setValue('dashboard/layout', '{"kpis": 7, "charts": "x"}')
        s._s.setValue('window/geometry', 'not bytes')
        s.sync()
        w = make_window(AppSettings(ini))
        assert w._df_full is not None and w.dashboard_tab._kpi_metrics == analytics.DEFAULT_KPIS
