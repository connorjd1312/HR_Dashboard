from __future__ import annotations

import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QMenu, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QComboBox, QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor

from core import analytics
from ui.chart_widget import ChartWithToolbar, draw_pie, make_splitter
from ui.kpi_card import KPICard, AddKPIButton
from ui.chart_panel import ChartPanel

EMPLOYEE_TABLE_COLS = [
    ('Name',          'Name'),
    ('Department',    'Department'),
    ('Job_Role',      'Job Role'),
    ('Status',        'Status'),
    ('Sex',           'Sex'),
    ('Ethnicity',     'Ethnicity'),
    ('Age',           'Age'),
    ('Salary',        'Salary'),
    ('Tenure_Years',  'Tenure (yrs)'),
]

_PIE_COLORS = [
    '#1F3864', '#2E75B6', '#1E8449', '#C0392B',
    '#D4AC0D', '#5B2C6F', '#117A65', '#E67E22',
    '#7F8C8D', '#34495E',
]

# Above this many categories, a horizontal-bar breakdown switches to a tall,
# scrollable canvas so every label stays readable (instead of hiding any in an
# 'Other' bucket).
# Breakdown chart sizing in the KPI drill-down grid. Charts keep a readable
# height and the grid scrolls, instead of squashing every chart onto one screen.
_BREAKDOWN_MIN_H = 300
_BAR_ROW_PX = 24          # height per category for horizontal bar charts
_OVERVIEW_MAX_BARS = 10   # overview grid shows the top N; the focused view shows all

_BTN_PRIMARY = '''
    QPushButton {
        background-color: #1F3864; color: white;
        border-radius: 5px; padding: 6px 14px;
        font-size: 12px; border: none;
    }
    QPushButton:hover  { background-color: #2E75B6; }
    QPushButton:pressed { background-color: #163060; }
'''

_BTN_SECONDARY = '''
    QPushButton {
        background-color: white; color: #444;
        border-radius: 5px; padding: 6px 14px;
        font-size: 12px; border: 1px solid #CCC;
    }
    QPushButton:hover { background-color: #F0F0F0; }
'''

_BTN_DANGER = '''
    QPushButton {
        color: #555; background: #F0F0F0; border: 1px solid #CCC;
        border-radius: 11px; font-size: 11px; font-weight: bold;
    }
    QPushButton:hover { background: #E74C3C; color: white; border-color: #C0392B; }
'''

_COMBO_STYLE = '''
    QComboBox {
        border: 1px solid #CCCCCC; border-radius: 4px;
        padding: 4px 8px; background: white; font-size: 12px; color: #333;
    }
    QComboBox:focus { border-color: #2E75B6; }
    QComboBox::drop-down { border: none; }
'''


# Dashboard tab: customisable KPI cards, charts, and drill-down.
class DashboardTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = None
        self._kpi_metrics: list[str] = list(analytics.DEFAULT_KPIS)
        self._chart_panels: list[ChartPanel] = []
        self._multi_mode: bool = False
        self._expanded_panel: ChartPanel | None = None
        self._period: tuple | None = None  # (start, end) of the hire-date filter

        # Drill-down state
        # KPI mode:   {'mode':'kpi',   'metric':str, 'path':[(dim,val), ...], 'focused_dim':str|None, 'removed_dims':set, 'show_charts':bool, 'show_table':bool}
        # Chart mode: {'mode':'chart', 'metric':str, 'path':[(dim,val), ...], 'override_dim':str|None, 'show_table':bool}
        self._drill_state: dict | None = None
        self._last_pick_click = None  # guards against one click drilling twice

        self._build_ui()

  
    # Build top level layout


    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Time period banner — visible on both the dashboard and drill-down pages
        self._period_label = QLabel()
        self._period_label.setStyleSheet(
            'background: #E8EEF7; color: #1F3864; font-size: 12px; font-family: Arial;'
            'border-radius: 6px; padding: 6px 10px; margin: 8px 8px 0 8px;'
        )
        self._period_label.hide()
        outer.addWidget(self._period_label)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        # Page 0: dashboard
        self._dashboard_page = self._build_dashboard_page()
        self._stack.addWidget(self._dashboard_page)

        # Page 1: drill-down container (rebuilt on entry)
        self._drill_page = QWidget()
        self._drill_layout = QVBoxLayout(self._drill_page)
        self._drill_layout.setContentsMargins(8, 8, 8, 8)
        self._drill_layout.setSpacing(8)
        self._stack.addWidget(self._drill_page)

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)

        #KPI cards row
        self._kpi_widget = QWidget()
        self._kpi_row = QHBoxLayout(self._kpi_widget)
        self._kpi_row.setContentsMargins(0, 0, 0, 0)
        self._kpi_row.setSpacing(8)
        v.addWidget(self._kpi_widget)

        # Toggle row above charts
        self._toggle_widget = QWidget()
        toggle_row = QHBoxLayout(self._toggle_widget)
        toggle_row.setContentsMargins(0, 0, 0, 0)
        self._resize_tip = QLabel('Tip: drag the grey bars between charts to resize them')
        self._resize_tip.setStyleSheet('color: #777; font-size: 11px; background: transparent;')
        self._resize_tip.hide()
        toggle_row.addWidget(self._resize_tip)
        toggle_row.addStretch()

        self._add_chart_btn = QPushButton('+ Add Chart')
        self._add_chart_btn.setStyleSheet(_BTN_SECONDARY)
        self._add_chart_btn.clicked.connect(self._add_chart)
        self._add_chart_btn.hide()
        toggle_row.addWidget(self._add_chart_btn)

        self._multi_toggle_btn = QPushButton('Show 4 Charts')
        self._multi_toggle_btn.setStyleSheet(_BTN_SECONDARY)
        self._multi_toggle_btn.clicked.connect(self._toggle_multi_mode)
        toggle_row.addWidget(self._multi_toggle_btn)

        v.addWidget(self._toggle_widget)

        # Chart area — rebuilt as resizable splitters by _relayout_charts
        self._chart_area = QWidget()
        self._chart_layout = QVBoxLayout(self._chart_area)
        self._chart_layout.setContentsMargins(0, 0, 0, 0)
        self._chart_splitter = None
        v.addWidget(self._chart_area, stretch=1)

        # Initial single chart
        initial = self._make_chart_panel(allow_close=False)
        self._chart_panels = [initial]
        self._relayout_charts()

        return page


    # Public API, called by MainWindow whenever the dataset changes


    def set_period(self, start, end):
        # Hire-date range currently applied; shown in the banner and under chart titles.
        self._period = (start, end)
        for panel in self._chart_panels:
            panel.set_period_text(self._period_subtitle())

    def _period_subtitle(self) -> str | None:
        if not self._period:
            return None
        return f'Hired {analytics.format_period(*self._period)}'

    def _refresh_period_label(self):
        if not self._period or self._df is None:
            self._period_label.hide()
            return
        today = pd.Timestamp.today()
        self._period_label.setText(
            f'<b>Time period:</b> employees hired {analytics.format_period(*self._period)}'
            f'&nbsp;&nbsp;·&nbsp;&nbsp;{len(self._df):,} employees'
            f'&nbsp;&nbsp;·&nbsp;&nbsp;figures as at {analytics.format_date(today)}'
        )
        self._period_label.show()

    def update_data(self, df: pd.DataFrame):
        self._df = df
        self._refresh_period_label()
        self._refresh_kpi_row()
        for panel in self._chart_panels:
            panel.update_data(df)
        # If drill-down view is active, re-render so sidebar filter changes flow through
        if self._stack.currentIndex() == 1 and self._drill_state:
            self._render_drill()


    # KPI row management


    def _refresh_kpi_row(self):
        while self._kpi_row.count():
            item = self._kpi_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for metric in self._kpi_metrics:
            value = analytics.kpi_value(self._df, metric) if self._df is not None else '—'
            card = KPICard(metric, value)
            card.clicked.connect(self._on_kpi_clicked)
            card.remove_clicked.connect(self._on_kpi_removed)
            self._kpi_row.addWidget(card)

        add_btn = AddKPIButton()
        add_btn.clicked.connect(self._on_add_kpi_clicked)
        self._kpi_row.addWidget(add_btn)

    def _on_kpi_clicked(self, metric: str):
        self._drill_state = {
            'mode':         'kpi',
            'metric':       metric,
            'path':         [],      # [(dimension, value), ...] — bars/slices clicked so far
            'focused_dim':  None,
            'removed_dims': set(),
            'show_charts':  True,
            'show_table':   False,   # employee table starts hidden so the charts get the room
            'chart_types':  {},   # {dimension: chart_type}; missing = 'Auto'
        }
        self._render_drill()
        self._stack.setCurrentIndex(1)

    def _on_kpi_removed(self, metric: str):
        self._kpi_metrics = [m for m in self._kpi_metrics if m != metric]
        self._refresh_kpi_row()

    def _on_add_kpi_clicked(self):
        menu = QMenu(self)
        available = [m for m in analytics.KPI_OPTIONS if m not in self._kpi_metrics]
        if not available:
            menu.addAction('All metrics already added').setEnabled(False)
        else:
            for m in available:
                menu.addAction(m, lambda metric=m: self._add_kpi(metric))
        menu.exec(QCursor.pos())

    def _add_kpi(self, metric: str):
        if metric not in self._kpi_metrics:
            self._kpi_metrics.append(metric)
            self._refresh_kpi_row()

  
    # Chart area management 


    def _make_chart_panel(
        self,
        allow_close: bool,
        metric: str = 'Employee Count',
        dimension: str = 'Department',
        chart_type: str = 'Auto',
    ) -> ChartPanel:
        panel = ChartPanel(
            allow_close=allow_close,
            metric=metric,
            dimension=dimension,
            chart_type=chart_type,
        )
        panel.bar_clicked.connect(self._on_chart_bar_clicked)
        panel.expand_requested.connect(self._on_chart_expand)
        panel.set_period_text(self._period_subtitle())
        if allow_close:
            panel.close_requested.connect(self._on_chart_closed)
        if self._df is not None:
            panel.update_data(self._df)
        return panel

    def _relayout_charts(self):
        # Lay charts out two per row inside splitters so the user can drag the
        # dividers to resize them. Panels are detached first so deleting the old
        # splitters doesn't delete them.
        self._set_expanded(None)
        for panel in self._chart_panels:
            panel.setParent(None)
        if self._chart_splitter is not None:
            self._chart_splitter.deleteLater()

        self._chart_splitter = make_splitter(Qt.Orientation.Vertical)
        for start in range(0, len(self._chart_panels), 2):
            row = make_splitter(Qt.Orientation.Horizontal)
            for panel in self._chart_panels[start:start + 2]:
                row.addWidget(panel)
            row.setSizes([1000] * row.count())
            self._chart_splitter.addWidget(row)
        self._chart_splitter.setSizes([1000] * self._chart_splitter.count())
        self._chart_layout.addWidget(self._chart_splitter)

    def _on_chart_expand(self, panel):
        self._set_expanded(None if self._expanded_panel is panel else panel)

    def _set_expanded(self, panel):
        # Enlarge one chart to fill the dashboard (hides KPI cards and the other
        # charts), or restore the normal layout when panel is None.
        self._expanded_panel = panel
        self._kpi_widget.setVisible(panel is None)
        self._toggle_widget.setVisible(panel is None)
        for p in self._chart_panels:
            p.setVisible(panel is None or p is panel)
            p.set_expanded(p is panel)
        if self._chart_splitter is not None:
            for i in range(self._chart_splitter.count()):
                row = self._chart_splitter.widget(i)
                row.setVisible(panel is None or panel.parent() is row)

    def _toggle_multi_mode(self):
        self._multi_mode = not self._multi_mode
        if self._multi_mode:
            self._multi_toggle_btn.setText('Show Single Chart')
            self._add_chart_btn.show()
            self._resize_tip.show()
            self._rebuild_charts(allow_close=True)
        else:
            self._multi_toggle_btn.setText('Show 4 Charts')
            self._add_chart_btn.hide()
            self._resize_tip.hide()
            # Drop everything except the first chart
            for extra in self._chart_panels[1:]:
                extra.deleteLater()
            self._chart_panels = self._chart_panels[:1]
            self._rebuild_charts(allow_close=False)
        self._relayout_charts()

    def _rebuild_charts(self, allow_close: bool):
        # Rebuild panels with a different allow_close flag, preserving configs.
        configs = [p.current_config() for p in self._chart_panels]
        for p in self._chart_panels:
            p.deleteLater()
        self._chart_panels = [
            self._make_chart_panel(
                allow_close=allow_close,
                metric=cfg['metric'],
                dimension=cfg['dimension'],
                chart_type=cfg['chart_type'],
            )
            for cfg in configs
        ]

    def _add_chart(self):
        if len(self._chart_panels) >= 4:
            return
        self._chart_panels.append(self._make_chart_panel(allow_close=True))
        self._relayout_charts()

    def _on_chart_closed(self, panel):
        if panel not in self._chart_panels:
            return
        if len(self._chart_panels) <= 1:
            return  # never let the user close the last chart in multi mode
        self._chart_panels.remove(panel)
        panel.setParent(None)
        panel.deleteLater()
        self._relayout_charts()

 
    # Chart bar click to drill down entry


    def _on_chart_bar_clicked(self, label: str):
        sender = self.sender()
        if not isinstance(sender, ChartPanel):
            return
        cfg = sender.current_config()
        self._drill_state = {
            'mode':          'chart',
            'metric':        cfg['metric'],
            'path':          [(cfg['dimension'], label)],
            'override_dim':  None,
            'show_table':    False,
        }
        self._render_drill()
        self._stack.setCurrentIndex(1)



#/////////////////////////////////////////////////////////////////////////////////////////////////
# drill down feature will be change in future


    # Drill-down rendering


    def _render_drill(self):
        # Clear current contents
        while self._drill_layout.count():
            item = self._drill_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self._drill_state:
            return

        if self._drill_state['mode'] == 'kpi':
            self._drill_layout.addWidget(self._build_kpi_drill_view())
        else:
            self._drill_layout.addWidget(self._build_chart_drill_view())

    def _build_drill_header(self, title: str, back_label: str = '← Back') -> QWidget:
        header = QFrame()
        header.setStyleSheet('QFrame { background: #F5F7FA; border-radius: 6px; }')
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(8)

        back = QPushButton(back_label)
        back.setStyleSheet(_BTN_SECONDARY)
        back.clicked.connect(self._drill_back)
        h.addWidget(back)

        reset = QPushButton('↻ Reset')
        reset.setStyleSheet(_BTN_SECONDARY)
        reset.clicked.connect(self._exit_drill)
        h.addWidget(reset)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            'font-size: 14px; font-weight: bold; color: #1F3864; padding-left: 12px; background: transparent;'
        )
        h.addWidget(title_lbl)
        h.addStretch()

        return header

    def _drill_back(self):
        if not self._drill_state:
            self._exit_drill()
            return

        if self._drill_state['mode'] == 'kpi':
            # Focused → back to grid; drilled → up one level; top grid → dashboard
            if self._drill_state.get('focused_dim'):
                self._drill_state['focused_dim'] = None
                self._render_drill()
            elif self._drill_state['path']:
                self._drill_state['path'].pop()
                self._render_drill()
            else:
                self._exit_drill()
        else:
            # Chart drill-down: peel one level
            path = self._drill_state['path']
            if len(path) > 1:
                path.pop()
                self._drill_state['override_dim'] = None
                self._render_drill()
            else:
                self._exit_drill()

    def _exit_drill(self):
        self._drill_state = None
        self._stack.setCurrentIndex(0)


    # KPI drill-down view
  

    def _build_kpi_drill_view(self) -> QWidget:
        s = self._drill_state
        metric = s['metric']

        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        path = s['path']

        # Header with breadcrumb of the groups drilled into so far
        title = f'{metric}'
        if path:
            title += '  |  ' + ' › '.join(f'{dim}: {val}' for dim, val in path)
        if s.get('focused_dim'):
            title += f'  ·  by {s["focused_dim"]}'
        v.addWidget(self._build_drill_header(title))

        # Sidebar-filtered df, narrowed to the drilled-into groups
        df = self._df.copy() if self._df is not None else pd.DataFrame()
        for dim, val in path:
            col = analytics._COL_MAP.get(dim, dim)
            if col in df.columns:
                df = df[df[col].astype(str) == str(val)]

        # Dimensions still available to break down by. Once they're all used
        # (or nothing matches), the employee list is the end of the drill-down.
        used = {dim for dim, _ in path}
        remaining = [d for d in analytics.DRILL_CASCADE if d not in used]
        at_bottom = not remaining or len(df) == 0
        show_charts = s['show_charts'] and not at_bottom
        show_table = s['show_table'] or at_bottom

        # Toggle row
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(8)
        toggle_row.addStretch()

        if s.get('focused_dim'):
            show_all_btn = QPushButton('▦ Show All Charts')
            show_all_btn.setStyleSheet(_BTN_SECONDARY)
            show_all_btn.clicked.connect(self._kpi_unfocus)
            toggle_row.addWidget(show_all_btn)

        hint = QLabel('Click a bar or slice to drill into that group'
                      if not at_bottom else 'No more breakdowns — showing the matching employees')
        hint.setStyleSheet('color: #777; font-size: 11px; background: transparent;')
        toggle_row.insertWidget(0, hint)

        if not s.get('focused_dim') and not at_bottom:
            chart_toggle = QPushButton('Hide Charts' if s['show_charts'] else 'Show Charts')
            chart_toggle.setStyleSheet(_BTN_SECONDARY)
            chart_toggle.clicked.connect(self._kpi_toggle_charts)
            toggle_row.addWidget(chart_toggle)

        if not at_bottom:
            table_toggle = QPushButton('Hide Table' if s['show_table'] else 'Show Table')
            table_toggle.setStyleSheet(_BTN_SECONDARY)
            table_toggle.clicked.connect(self._toggle_table)
            toggle_row.addWidget(table_toggle)

        v.addLayout(toggle_row)

        # Charts area
        if show_charts:
            if s.get('focused_dim'):
                focused_scroll = QScrollArea()
                focused_scroll.setWidgetResizable(True)
                focused_scroll.setFrameShape(QFrame.Shape.NoFrame)
                focused_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                focused_scroll.setWidget(self._make_breakdown_chart(metric, s['focused_dim'], df, focused=True))
                v.addWidget(focused_scroll, stretch=2)
            else:
                grid_widget = QWidget()
                grid = QGridLayout(grid_widget)
                grid.setContentsMargins(0, 0, 4, 0)
                grid.setSpacing(8)

                visible_dims = [d for d in remaining if d not in s['removed_dims']]
                for i, dim in enumerate(visible_dims):
                    row, col = divmod(i, 2)
                    grid.addWidget(self._make_breakdown_chart(metric, dim, df, focused=False), row, col)

                if not visible_dims:
                    empty = QLabel('All breakdown charts have been removed. Use ↻ Reset to start over.')
                    empty.setStyleSheet('color: #888; font-style: italic; padding: 20px;')
                    empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    grid.addWidget(empty, 0, 0)

                grid_scroll = QScrollArea()
                grid_scroll.setWidgetResizable(True)
                grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
                grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                grid_scroll.setWidget(grid_widget)
                v.addWidget(grid_scroll, stretch=2)

        # Table — show only employees relevant to this KPI
        if show_table:
            table_df = analytics.kpi_relevant_employees(df, metric)

            count_metrics = {
                'Active Employees':                       'active employees',
                'On Leave Count':                         'employees on leave',
                'Resigned Count':                         'resigned employees',
                'Overall Turnover Rate (%)':              'employees who have left',
                'Attrition (Voluntary Leavers) Rate (%)': 'employees who left voluntarily',
            }
            descriptor = count_metrics.get(metric, 'employees')
            note = QLabel(f'Showing {len(table_df)} {descriptor}')
            note.setStyleSheet('color: #555; font-size: 12px; padding: 4px 2px; background: transparent;')
            v.addWidget(note)
            v.addWidget(self._build_employee_table(table_df), stretch=1)

        return wrap

    def _make_breakdown_chart(self, metric: str, dimension: str, df: pd.DataFrame, focused: bool) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet(
            'QFrame { background: white; border: 1px solid #E5E7EB; border-radius: 8px; }'
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(4)

        # Header row: title + focus + remove
        head = QHBoxLayout()
        head.setSpacing(4)

        title = QLabel(f'by {dimension}')
        title.setStyleSheet(
            'font-size: 12px; font-weight: bold; color: #1F3864; background: transparent; border: none;'
        )
        head.addWidget(title)
        head.addStretch()

        # Per-chart type selector (defaults to 'Auto'). Lets the user override
        # the automatically chosen chart type for this breakdown.
        current_type = self._drill_state.get('chart_types', {}).get(dimension, 'Auto')
        type_combo = QComboBox()
        type_combo.addItems(analytics.CHART_TYPES)
        type_combo.setCurrentText(current_type)
        type_combo.setStyleSheet(_COMBO_STYLE)
        type_combo.setFixedWidth(120)
        type_combo.setToolTip('Chart type for this breakdown')
        type_combo.currentTextChanged.connect(
            lambda t, d=dimension: self._kpi_set_chart_type(d, t)
        )
        head.addWidget(type_combo)

        if not focused:
            focus_btn = QPushButton('🔍')
            focus_btn.setFixedSize(22, 22)
            focus_btn.setToolTip('Focus this chart')
            focus_btn.setStyleSheet(_BTN_DANGER.replace('#E74C3C', '#2E75B6').replace('#C0392B', '#1F3864'))
            focus_btn.clicked.connect(lambda _, d=dimension: self._kpi_focus(d))
            head.addWidget(focus_btn)

            rm_btn = QPushButton('✕')
            rm_btn.setFixedSize(22, 22)
            rm_btn.setToolTip('Remove this chart')
            rm_btn.setStyleSheet(_BTN_DANGER)
            rm_btn.clicked.connect(lambda _, d=dimension: self._kpi_remove_dim(d))
            head.addWidget(rm_btn)

        layout.addLayout(head)

        data = analytics.kpi_breakdown(df, metric, dimension)

        # Resolve the selected type ('Auto' → recommended).
        ctype = current_type
        if ctype == 'Auto':
            ctype = (analytics.recommend_chart_type(metric, dimension, data)
                     if not data.empty else 'Vertical Bar')

        # In the overview grid, long breakdowns (e.g. Job Role) show only the
        # top categories so the chart stays readable; 🔍 focus shows them all.
        hidden = 0
        if (not focused and ctype in ('Horizontal Bar', 'Vertical Bar')
                and dimension not in analytics.ORDERED_DIMENSIONS
                and len(data) > _OVERVIEW_MAX_BARS):
            hidden = len(data) - _OVERVIEW_MAX_BARS
            data = data.sort_values(ascending=False).head(_OVERVIEW_MAX_BARS)
            ctype = 'Horizontal Bar'

        chart = ChartWithToolbar(width=5 if not focused else 9, height=3 if not focused else 5)
        # The zoom/pan toolbar is only worth its space on the focused chart.
        chart.set_toolbar_visible(focused)

        ax = chart.axes
        chart.clear_axes()
        if data.empty:
            ax.text(0.5, 0.5, 'No data', ha='center', va='center',
                    transform=ax.transAxes, color='#888')
            ax.axis('off')
        else:
            # Every bar/slice is clickable to drill one level deeper
            picks = {}
            for artist, label in self._draw_snapshot(ax, data, metric, dimension, ctype):
                artist.set_picker(True)
                picks[artist] = label
            value_of = {str(k): v for k, v in data.items()}
            chart.set_hover_items({
                artist: f'{label}: {analytics.format_metric_value(metric, value_of[label])}\nClick to drill down'
                for artist, label in picks.items()
            })

            def on_pick(event, dim=dimension, picks=picks):
                # One click can pick several overlapping artists — only drill once.
                if event.artist in picks and event.mouseevent is not self._last_pick_click:
                    self._last_pick_click = event.mouseevent
                    self._kpi_drill_into(dim, picks[event.artist])

            chart.figure.canvas.mpl_connect('pick_event', on_pick)
        chart.refresh()

        layout.addWidget(chart, stretch=1)

        if hidden:
            more = QPushButton(f'Showing top {_OVERVIEW_MAX_BARS} of {len(data) + hidden}  —  🔍 see all {dimension.lower()}s')
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            more.setStyleSheet(
                'QPushButton { color: #2E75B6; background: transparent; border: none;'
                ' font-size: 11px; text-align: left; padding: 2px 4px; }'
                'QPushButton:hover { text-decoration: underline; }'
            )
            more.clicked.connect(lambda _, d=dimension: self._kpi_focus(d))
            layout.addWidget(more)

        # Horizontal bars grow taller with more categories (e.g. Job Role) so
        # every label stays readable — nothing is hidden or bucketed. The
        # drill-down page scrolls rather than squashing the chart.
        min_h = 420 if focused else _BREAKDOWN_MIN_H
        if ctype == 'Horizontal Bar':
            min_h = max(min_h, len(data) * _BAR_ROW_PX + 110)
        frame.setMinimumHeight(min_h)

        return frame

    def _draw_snapshot(self, ax, data: pd.Series, metric: str, dimension: str, ctype: str) -> list:
        # Render a snapshot Series onto an axes as the given concrete chart type.
        # Returns (artist, category label) pairs so callers can make them clickable.
        # Bars are sorted largest-first for readability (except ordered
        # dimensions like Age Group, where the natural order is preserved).
        labels = [str(x) for x in data.index]
        values = [float(v) for v in data.values]

        ordered = dimension in analytics.ORDERED_DIMENSIONS
        if ctype in ('Vertical Bar', 'Horizontal Bar', 'Line') and not ordered:
            order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
            labels = [labels[i] for i in order]
            values = [values[i] for i in order]

        if ctype == 'Horizontal Bar':
            # Show every category (no 'Other' bucket); barh stacks bottom-to-top,
            # so reverse to put the largest on top.
            labels, values = labels[::-1], values[::-1]
            artists = ax.barh(labels, values, color='#2E75B6', height=0.7)
            for i, val in enumerate(values):
                ax.text(val, i, f' {self._fmt_val(metric, val)}',
                        va='center', fontsize=8, color='#333')
            ax.set_xlabel(metric, fontsize=9)
            ax.tick_params(axis='y', labelsize=9)
            ax.margins(x=0.15, y=0.02)
            ax.spines[['top', 'right']].set_visible(False)
        elif ctype in ('Pie', 'Donut'):
            colors = [_PIE_COLORS[i % len(_PIE_COLORS)] for i in range(len(labels))]
            artists = draw_pie(ax, labels, values, colors, donut=(ctype == 'Donut'),
                               value_fmt=lambda v: self._fmt_val(metric, v))
        elif ctype == 'Line':
            ax.plot(labels, values, color='#2E75B6', linewidth=2)
            artists = [ax.plot([lbl], [val], 'o', color='#1F3864', markersize=7)[0]
                       for lbl, val in zip(labels, values)]
            ax.set_ylabel(metric, fontsize=9)
            ax.tick_params(axis='x', rotation=20, labelsize=8)
        else:  # Vertical Bar (safe default)
            artists = bars = ax.bar(labels, values, color='#2E75B6', width=0.65)
            ax.bar_label(bars, labels=[self._fmt_val(metric, v) for v in values],
                         padding=2, fontsize=8, color='#333')
            ax.tick_params(axis='x', rotation=20, labelsize=9)
            ax.set_ylabel(metric, fontsize=9)
            ax.margins(y=0.15)
            ax.spines[['top', 'right']].set_visible(False)

        return list(zip(artists, labels))

    def _fmt_val(self, metric: str, val: float) -> str:
        # Compact value label for bar ends.
        if '%' in metric:
            return f'{val:.1f}'
        if '$' in metric or 'Salary' in metric:
            return f'${val:,.0f}'
        if float(val).is_integer():
            return f'{int(val)}'
        return f'{val:.1f}'

    def _kpi_set_chart_type(self, dimension: str, chart_type: str):
        if not self._drill_state:
            return
        self._drill_state.setdefault('chart_types', {})[dimension] = chart_type
        self._render_drill()

    def _kpi_drill_into(self, dimension: str, value: str):
        # Narrow the KPI drill-down to one group and show the remaining breakdowns.
        if not self._drill_state:
            return
        self._drill_state['path'].append((dimension, value))
        self._drill_state['focused_dim'] = None
        self._render_drill()

    def _kpi_focus(self, dimension: str):
        if not self._drill_state:
            return
        self._drill_state['focused_dim'] = dimension
        self._render_drill()

    def _kpi_unfocus(self):
        if not self._drill_state:
            return
        self._drill_state['focused_dim'] = None
        self._render_drill()

    def _kpi_remove_dim(self, dimension: str):
        if not self._drill_state:
            return
        self._drill_state['removed_dims'].add(dimension)
        self._render_drill()

    def _kpi_toggle_charts(self):
        if not self._drill_state:
            return
        self._drill_state['show_charts'] = not self._drill_state['show_charts']
        self._render_drill()

    def _toggle_table(self):
        if not self._drill_state:
            return
        self._drill_state['show_table'] = not self._drill_state['show_table']
        self._render_drill()


    # Chart drill-down view


    def _build_chart_drill_view(self) -> QWidget:
        s = self._drill_state
        metric: str = s['metric']
        path: list[tuple[str, str]] = s['path']

        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        # Breadcrumb title
        crumb = ' › '.join([f'{dim}: {val}' for dim, val in path])
        v.addWidget(self._build_drill_header(f'{metric}  |  {crumb}'))

        # Filter df by the path
        df = self._df.copy() if self._df is not None else pd.DataFrame()
        col_map = analytics._COL_MAP
        for dim, val in path:
            col = col_map.get(dim, dim)
            if col in df.columns:
                df = df[df[col].astype(str) == str(val)]

        # Determine the next dimension to break by
        used_dims = {dim for dim, _ in path}
        remaining = [d for d in analytics.DRILL_CASCADE if d not in used_dims]
        override = s.get('override_dim')
        next_dim = override if (override and override in remaining) else (remaining[0] if remaining else None)

        # Dimension selector row (only shown if there are remaining dims)
        if remaining:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(self._tag('Break down by'))
            dim_combo = QComboBox()
            dim_combo.addItems(remaining)
            if next_dim:
                dim_combo.setCurrentText(next_dim)
            dim_combo.setStyleSheet(_COMBO_STYLE)
            dim_combo.currentTextChanged.connect(self._chart_set_override)
            row.addWidget(dim_combo)
            row.addStretch()

            table_toggle = QPushButton('Hide Table' if s.get('show_table') else 'Show Table')
            table_toggle.setStyleSheet(_BTN_SECONDARY)
            table_toggle.clicked.connect(self._toggle_table)
            row.addWidget(table_toggle)
            v.addLayout(row)

        # Body: chart by next_dim, OR table when no dims remain
        if next_dim is None or len(df) == 0:
            note = QLabel(
                f'Showing {len(df)} employee(s) matching {crumb}.'
                if len(df) else 'No employees match this path with the current filters.'
            )
            note.setStyleSheet('color: #555; font-size: 12px; background: transparent;')
            v.addWidget(note)
            v.addWidget(self._build_employee_table(df), stretch=1)
        else:
            chart_panel = ChartPanel(
                allow_close=False,
                metric=metric,
                dimension=next_dim,
                chart_type='Auto',
            )
            chart_panel.bar_clicked.connect(self._on_drill_chart_bar_clicked)
            chart_panel.set_period_text(self._period_subtitle())
            chart_panel.update_data(df)
            v.addWidget(chart_panel, stretch=2)

            if s.get('show_table'):
                note = QLabel(f'Showing {len(df)} employee(s) matching {crumb}')
                note.setStyleSheet('color: #555; font-size: 12px; padding: 4px 2px; background: transparent;')
                v.addWidget(note)
                v.addWidget(self._build_employee_table(df), stretch=1)

        return wrap

    def _on_drill_chart_bar_clicked(self, label: str):
        sender = self.sender()
        if not isinstance(sender, ChartPanel) or not self._drill_state:
            return
        cfg = sender.current_config()
        self._drill_state['path'].append((cfg['dimension'], label))
        self._drill_state['override_dim'] = None
        self._render_drill()

    def _chart_set_override(self, dimension: str):
        if not self._drill_state:
            return
        self._drill_state['override_dim'] = dimension
        self._render_drill()

    def _tag(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet('font-size: 12px; color: #555; background: transparent;')
        return lbl


#///////////////////////////////////////////////////////////////////////////////////////////
        #drill down feature will be change in future 

    # Employee table builder 


    def _build_employee_table(self, df: pd.DataFrame) -> QTableWidget:
        cols = [(c, label) for c, label in EMPLOYEE_TABLE_COLS if c in df.columns]
        table = QTableWidget(len(df), len(cols))
        table.setHorizontalHeaderLabels([label for _, label in cols])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setStyleSheet('''
            QTableWidget { background: white; alternate-background-color: #F8F9FB; gridline-color: #E5E7EB; }
            QHeaderView::section {
                background: #1F3864; color: white; font-weight: bold;
                padding: 6px; border: none; font-size: 11px;
            }
        ''')

        # Sorting must be off during insert — otherwise the table re-sorts after every
        # setItem() call and rows get scrambled (cells end up in unrelated rows).
        table.setSortingEnabled(False)

        for r, (_, row) in enumerate(df.iterrows()):
            for c, (col, _) in enumerate(cols):
                val = row[col]
                if pd.isna(val):
                    text = '—'
                    sort_val = None
                elif col == 'Salary':
                    text = f'${val:,.0f}'
                    sort_val = float(val)
                elif col == 'Tenure_Years':
                    text = f'{val:.1f}'
                    sort_val = float(val)
                elif col == 'Age':
                    text = f'{int(val)}'
                    sort_val = int(val)
                else:
                    text = str(val)
                    sort_val = None

                item = QTableWidgetItem(text)
                # Use Qt.ItemDataRole.UserRole+1 = EditRole so numeric columns sort numerically
                if sort_val is not None:
                    item.setData(Qt.ItemDataRole.EditRole, sort_val)
                # Right-align numeric columns
                if col in ('Salary', 'Tenure_Years', 'Age'):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(r, c, item)

        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return table
    