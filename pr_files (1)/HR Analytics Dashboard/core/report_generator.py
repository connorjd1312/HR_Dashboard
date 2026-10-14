from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

import matplotlib as mpl
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch, Rectangle

from core import analytics

# Same palette as ui/theme.py; core must not import ui.
NAVY, BLUE, GREEN, RED = '#1F3864', '#2E75B6', '#1E8449', '#C0392B'
TEXT, MUTED, BORDER = '#333333', '#666666', '#D8DCE3'
CHART_COLORS = ['#1F3864', '#2E75B6', '#1E8449', '#C0392B', '#D4AC0D',
                '#5B2C6F', '#117A65', '#E67E22', '#7F8C8D', '#34495E']

PAGE_W, PAGE_H = 8.27, 11.69
MARGIN_X = 0.06
CONTENT_TOP = 0.925
CONTENT_BOTTOM = 0.055
MAX_BARS = 10

LIGHT_RC = {
    'figure.facecolor': 'white', 'axes.facecolor': 'white', 'savefig.facecolor': 'white',
    'text.color': TEXT, 'axes.labelcolor': '#444444', 'axes.edgecolor': '#999999',
    'axes.titlecolor': TEXT, 'axes.titleweight': 'bold', 'axes.titlesize': 10,
    'axes.labelsize': 8, 'xtick.color': '#444444', 'ytick.color': '#444444',
    'xtick.labelsize': 7.5, 'ytick.labelsize': 7.5, 'legend.fontsize': 7.5, 'legend.frameon': False,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.prop_cycle': mpl.cycler(color=CHART_COLORS), 'grid.color': '#DDDDDD',
    'font.family': 'sans-serif', 'font.sans-serif': ['Segoe UI', 'Arial', 'DejaVu Sans'],
    'font.size': 8, 'pdf.fonttype': 42,
}


@dataclass
class KpiEntry:
    metric: str
    value: str
    change: tuple[str, str] | None = None


def compute_kpis(df: pd.DataFrame, metrics: list[str], previous: pd.DataFrame | None = None) -> list[KpiEntry]:
    out = []
    for m in metrics:
        change = None
        if previous is not None and len(previous):
            change = analytics.kpi_change(m, analytics.kpi_number(df, m), analytics.kpi_number(previous, m))
        out.append(KpiEntry(m, analytics.kpi_value(df, m), change))
    return out


@dataclass
class ReportOptions:
    title: str = 'HR Workforce Summary'
    include_kpis: bool = True
    include_dashboard_charts: bool = True
    include_overview_charts: bool = True
    include_analytics_charts: bool = True


@dataclass
class ReportData:
    df: pd.DataFrame
    scope: str
    kpis: list[KpiEntry] = field(default_factory=list)
    chart_configs: list[dict] = field(default_factory=list)
    history_df: pd.DataFrame | None = None
    previous_label: str = ''
    analytics_charts: list[tuple[str, Callable[[Figure], None]]] = field(default_factory=list)


def build_highlights(df: pd.DataFrame, history_df: pd.DataFrame | None = None,
                     today: pd.Timestamp | None = None) -> list[str]:
    out: list[str] = []
    if df is None or len(df) == 0:
        return out
    today = pd.Timestamp(today or date.today())
    total = len(df)

    if 'Department' in df.columns and df['Department'].nunique() > 1:
        sizes = df['Department'].value_counts()
        out.append(f'{sizes.index[0]} is the largest department with {sizes.iloc[0]:,} employees '
                   f'({sizes.iloc[0] / total:.0%} of the workforce); {sizes.index[-1]} is the smallest '
                   f'with {sizes.iloc[-1]:,}.')

        # Rates for tiny groups swing wildly, so only compare departments with at least 10 people.
        big = [d for d, n in sizes.items() if n >= 10]
        if len(big) >= 2:
            turn = (df[df['Department'].isin(big)].groupby('Department')['Turnover'].mean() * 100).sort_values()
            out.append(f'Turnover is highest in {turn.index[-1]} ({turn.iloc[-1]:.1f}%) and lowest in '
                       f'{turn.index[0]} ({turn.iloc[0]:.1f}%).')
            sal = df[df['Department'].isin(big)].groupby('Department')['Salary'].mean().sort_values()
            out.append(f'Average salary is highest in {sal.index[-1]} (${sal.iloc[-1]:,.0f}) and lowest in '
                       f'{sal.index[0]} (${sal.iloc[0]:,.0f}).')

    hist = history_df if history_df is not None else df
    if 'Hire_Date' in hist.columns:
        start = today - pd.DateOffset(months=12)
        hires = int(((hist['Hire_Date'] > start) & (hist['Hire_Date'] <= today)).sum())
        departures = 0
        if 'End_Date' in hist.columns:
            departures = int(((hist['End_Date'] > start) & (hist['End_Date'] <= today)).sum())
        net = hires - departures
        direction = 'grew' if net > 0 else 'shrank' if net < 0 else 'was unchanged'
        out.append(f'In the last 12 months there were {hires:,} hires and {departures:,} departures, so '
                   f'headcount {direction}' + (f' by {abs(net):,}.' if net else '.'))

    active = int((df['Status'] == 'Active').sum())
    on_leave = int((df['Status'] == 'On Leave').sum())
    out.append(f'{active:,} of {total:,} employees ({active / total:.0%}) are currently active'
               + (f' and {on_leave:,} are on leave.' if on_leave else '.'))
    return out


def _t(text: str) -> str:
    # $...$ is maths text in matplotlib, so escape the dollar sign.
    return text.replace('$', r'\$')


def _fmt(metric: str, v: float) -> str:
    return analytics.format_metric_value(metric, v)


def draw_snapshot(ax, df: pd.DataFrame, metric: str, dimension: str, chart_type: str = 'Auto') -> None:
    data = analytics.snapshot_data(df, metric, dimension)
    if data is None or data.empty:
        ax.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax.transAxes, color='#888')
        ax.axis('off')
        ax.set_title(_t(f'{metric} by {dimension}'))
        return
    ctype = analytics.recommend_chart_type(metric, dimension, data) if chart_type == 'Auto' else chart_type
    title = f'{metric} by {dimension}'
    ordered = dimension in analytics.ORDERED_DIMENSIONS
    if ctype in ('Pie', 'Donut') and (metric not in analytics.PARTS_OF_WHOLE_METRICS or ordered):
        ctype = 'Vertical Bar'

    labels = [str(i) for i in data.index]
    values = [float(v) for v in data.values]
    if not ordered and ctype != 'Pie' and ctype != 'Donut':
        order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
        labels, values = [labels[i] for i in order], [values[i] for i in order]
    if not ordered and ctype in ('Vertical Bar', 'Horizontal Bar') and len(values) > MAX_BARS:
        title += f'  (top {MAX_BARS} of {len(values)})'
        labels, values = labels[:MAX_BARS], values[:MAX_BARS]
        ctype = 'Horizontal Bar'
    text = [_fmt(metric, v) for v in values]

    if ctype == 'Horizontal Bar':
        bars = ax.barh(labels[::-1], values[::-1], color=BLUE, height=0.7)
        ax.bar_label(bars, labels=[_t(x) for x in text[::-1]], padding=3, fontsize=7)
        ax.margins(x=0.18)
    elif ctype in ('Pie', 'Donut'):
        total = sum(values) or 1.0
        wedges, _labels, _pcts = ax.pie(
            values, colors=CHART_COLORS[:len(values)] * (len(values) // len(CHART_COLORS) + 1),
            startangle=90, counterclock=False, autopct=lambda p: f'{p:.0f}%' if p >= 6 else '',
            pctdistance=0.75 if ctype == 'Donut' else 0.65,
            textprops={'fontsize': 7, 'color': 'white', 'fontweight': 'bold'},
            wedgeprops={'linewidth': 1, 'edgecolor': 'white'})
        ax.legend(wedges, [_t(f'{l}  {_fmt(metric, v)} ({v / total:.0%})') for l, v in zip(labels, values)],
                  loc='center left', bbox_to_anchor=(1.0, 0.5), fontsize=7)
        ax.set_aspect('equal')
    elif ctype == 'Line':
        ax.plot(labels, values, color=BLUE, linewidth=2, marker='o', markersize=4)
        ax.tick_params(axis='x', rotation=25)
    else:
        bars = ax.bar(labels, values, color=BLUE, width=0.65)
        ax.bar_label(bars, labels=[_t(x) for x in text], padding=2, fontsize=7)
        ax.margins(y=0.15)
        ax.tick_params(axis='x', rotation=25)
    ax.set_title(_t(title))


def draw_hires_departures(ax, history_df: pd.DataFrame, today: pd.Timestamp | None = None) -> None:
    end = pd.Timestamp(today or date.today())
    start = end - pd.DateOffset(months=12)
    hires = analytics.time_series_data(history_df, 'Hires', 'None', 'All', start, end, 'Monthly')
    leavers = analytics.time_series_data(history_df, 'Departures', 'None', 'All', start, end, 'Monthly')
    ax.plot(hires.index, hires.values, color=NAVY, linewidth=2, marker='o', markersize=3.5, label='Hires')
    ax.plot(leavers.index, leavers.values, color=RED, linewidth=2, marker='o', markersize=3.5, label='Departures')
    ax.set_title('Hires vs departures, last 12 months')
    ax.tick_params(axis='x', rotation=30)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.legend(loc='best')


def _fit_to_cell(sub, pad_px: float = 6.0, passes: int = 4) -> None:
    # Tight layout for one chart's sub-figure. A page-level layout engine would stretch
    # every chart over the whole page.
    axes = [a for a in sub.axes if a.get_visible()]
    if not axes:
        return
    renderer = sub.canvas.get_renderer()
    cell = sub.bbox
    w, h = cell.width, cell.height
    for _ in range(passes):
        boxes = [a.get_tightbbox(renderer) for a in axes]
        boxes = [b for b in boxes if b is not None and b.width > 0]
        if not boxes:
            return
        x0, y0 = min(b.x0 for b in boxes), min(b.y0 for b in boxes)
        x1, y1 = max(b.x1 for b in boxes), max(b.y1 for b in boxes)
        dl, db = (cell.x0 + pad_px - x0) / w, (cell.y0 + pad_px - y0) / h
        dr, dt = (x1 - (cell.x1 - pad_px)) / w, (y1 - (cell.y1 - pad_px)) / h
        if max(abs(dl), abs(dr), abs(db), abs(dt)) < 0.004:
            return
        pos = [a.get_position() for a in axes]
        ax0, ay0 = min(p.x0 for p in pos), min(p.y0 for p in pos)
        ax1, ay1 = max(p.x1 for p in pos), max(p.y1 for p in pos)
        nx0, ny0, nx1, ny1 = ax0 + dl, ay0 + db, ax1 - dr, ay1 - dt
        if nx1 - nx0 < 0.2 or ny1 - ny0 < 0.2:
            return
        sx, sy = (nx1 - nx0) / (ax1 - ax0), (ny1 - ny0) / (ay1 - ay0)
        for a, p in zip(axes, pos):
            a.set_position([nx0 + (p.x0 - ax0) * sx, ny0 + (p.y0 - ay0) * sy, p.width * sx, p.height * sy])


class _Pager:

    def __init__(self, pdf: PdfPages, title: str, generated: str):
        self.pdf, self.title, self.generated = pdf, title, generated
        self.page_no = 0
        self.fig: Figure | None = None
        self.y = 0.0
        self._new_page()

    def _new_page(self):
        if self.fig is not None:
            self._finish_page()
        self.page_no += 1
        self.fig = Figure(figsize=(PAGE_W, PAGE_H))
        FigureCanvasAgg(self.fig)  # needed to measure text
        if self.page_no == 1:
            self.y = 0.93
        else:
            f = self.fig
            f.add_artist(Rectangle((0, 0.965), 1, 0.035, transform=f.transFigure, color=NAVY, zorder=0))
            f.text(MARGIN_X, 0.9825, self.title, color='white', fontsize=9, fontweight='bold', va='center')
            self.y = 0.94

    def _finish_page(self):
        f = self.fig
        f.add_artist(Rectangle((MARGIN_X, 0.04), 1 - 2 * MARGIN_X, 0.0007, transform=f.transFigure, color=BORDER))
        f.text(MARGIN_X, 0.025, f'Generated {self.generated}', fontsize=7, color=MUTED, va='center')
        f.text(1 - MARGIN_X, 0.025, f'Page {self.page_no}', fontsize=7, color=MUTED, va='center', ha='right')
        self.pdf.savefig(f)
        self.fig = None

    def ensure(self, height: float):
        if self.y - height < CONTENT_BOTTOM + 0.01:
            self._new_page()

    def first_page_header(self, subtitle: str):
        f = self.fig
        f.add_artist(Rectangle((0, 0.93), 1, 0.07, transform=f.transFigure, color=NAVY, zorder=0))
        f.text(MARGIN_X, 0.972, self.title, color='white', fontsize=19, fontweight='bold', va='center')
        f.text(MARGIN_X, 0.945, 'Prepared from the HR Employee Analytics Dashboard', color='#C9D3E3', fontsize=8, va='center')
        subtitle = subtitle[:1].upper() + subtitle[1:]
        lines = textwrap.wrap(subtitle, 105)[:3]
        self.y = 0.915
        for line in lines:
            f.text(MARGIN_X, self.y, _t(line), fontsize=8.5, color=MUTED, va='top')
            self.y -= 0.0135
        self.y -= 0.012

    def heading(self, text: str, keep_with: float = 0.06):
        self.ensure(0.034 + keep_with)
        self.fig.text(MARGIN_X, self.y, text, fontsize=12, fontweight='bold', color=NAVY, va='top')
        self.y -= 0.034

    def kpi_tiles(self, kpis: list[KpiEntry], previous_label: str):
        per_row, h, gap = 3, 0.078, 0.012
        w = (1 - 2 * MARGIN_X - gap * (per_row - 1)) / per_row
        for i, k in enumerate(kpis):
            col = i % per_row
            if col == 0:
                self.ensure(h + gap)
                row_top = self.y
            x = MARGIN_X + col * (w + gap)
            f = self.fig
            f.add_artist(FancyBboxPatch((x, row_top - h), w, h, boxstyle='round,pad=0,rounding_size=0.008',
                                        transform=f.transFigure, facecolor=NAVY, edgecolor='none'))
            f.text(x + 0.015, row_top - 0.012, '\n'.join(textwrap.wrap(k.metric, 30)[:2]),
                   color='#DCE4F2', fontsize=7.5, va='top', linespacing=1.15)
            f.text(x + 0.015, row_top - 0.045, _t(k.value), color='white', fontsize=16, fontweight='bold', va='center')
            if k.change:
                text, tone = k.change
                colour = {'good': '#7DDC9C', 'bad': '#FF9C8F'}.get(tone, '#C9D3E3')
                f.text(x + 0.015, row_top - 0.067, f'{text} vs previous period', color=colour, fontsize=6.8, va='center')
            if col == per_row - 1 or i == len(kpis) - 1:
                self.y = row_top - h - gap
        if any(k.change for k in kpis) and previous_label:
            self.fig.text(MARGIN_X, self.y + 0.004, f'Changes compare with {previous_label}.',
                          fontsize=7, color=MUTED, va='top', style='italic')
            self.y -= 0.02
        self.y -= 0.01

    def bullets(self, lines: list[str]):
        for line in lines:
            wrapped = textwrap.wrap(line, 118)
            self.ensure(0.0135 * len(wrapped) + 0.01)
            self.fig.text(MARGIN_X, self.y, '-', fontsize=8.5, color=BLUE, va='top')
            for part in wrapped:
                self.fig.text(MARGIN_X + 0.018, self.y, _t(part), fontsize=8.5, color=TEXT, va='top')
                self.y -= 0.0135
            self.y -= 0.006
        self.y -= 0.01

    def chart_row(self, drawers: list[Callable[[Figure], None]], height: float = 0.27):
        self.ensure(height)
        top = self.y
        n = len(drawers)
        # Sub-figures ignore gridspec margins, so spacer rows and columns position the row.
        gap = 0.02
        cell_w = (1 - 2 * MARGIN_X - gap * (n - 1)) / n
        widths = [MARGIN_X]
        for i in range(n):
            widths += [cell_w] + ([gap] if i < n - 1 else [])
        widths.append(MARGIN_X)
        heights = [max(1 - top, 1e-3), height, max(top - height, 1e-3)]
        gs = self.fig.add_gridspec(3, len(widths), height_ratios=heights, width_ratios=widths,
                                   left=0, right=1, bottom=0, top=1, wspace=0, hspace=0)
        for i, draw in enumerate(drawers):
            sub = self.fig.add_subfigure(gs[1, 1 + 2 * i])
            sub.set_facecolor('none')
            try:
                draw(sub)
                _fit_to_cell(sub)
            except Exception as exc:  # one failed chart should not lose the report
                sub.clear()
                sub.text(0.5, 0.5, f'This chart could not be drawn\n({exc})', ha='center', va='center',
                         fontsize=8, color=RED)
        self.y = top - height - 0.012

    def close(self):
        if self.fig is not None:
            self._finish_page()


def _drawer(fn, *args) -> Callable[[Figure], None]:
    def draw(fig):
        ax = fig.add_subplot(111)
        fn(ax, *args)
    return draw


def generate_report(path: str, data: ReportData, options: ReportOptions | None = None,
                    today: pd.Timestamp | None = None) -> int:
    options = options or ReportOptions()
    today = pd.Timestamp(today or date.today())
    generated = analytics.format_date(today)
    df = data.df
    history = data.history_df if data.history_df is not None else df

    with mpl.rc_context(LIGHT_RC):
        with PdfPages(path, metadata={'Title': options.title, 'Author': 'HR Employee Analytics Dashboard',
                                      'Subject': data.scope[:200]}) as pdf:
            pager = _Pager(pdf, options.title, generated)
            pager.first_page_header(f'{data.scope} - {len(df):,} employees')

            if options.include_kpis and data.kpis:
                pager.heading('Key figures', keep_with=0.09)
                pager.kpi_tiles(data.kpis, data.previous_label)

            highlights = build_highlights(df, history, today)
            if highlights:
                pager.heading('Highlights')
                pager.bullets(highlights)

            def rows_of_two(drawers):
                for i in range(0, len(drawers), 2):
                    pager.chart_row(drawers[i:i + 2])

            if options.include_dashboard_charts and data.chart_configs:
                pager.heading('Dashboard charts', keep_with=0.27)
                rows_of_two([_drawer(draw_snapshot, df, c['metric'], c['dimension'], c.get('chart_type', 'Auto'))
                             for c in data.chart_configs])

            if options.include_overview_charts:
                pager.heading('Workforce overview', keep_with=0.27)
                overview = [
                    _drawer(draw_snapshot, df, 'Total Employees', 'Department'),
                    _drawer(draw_snapshot, df, 'Overall Turnover Rate (%)', 'Department'),
                    _drawer(draw_snapshot, df, 'Total Employees', 'Age Group'),
                    _drawer(draw_snapshot, df, 'Average Salary ($)', 'Job Role'),
                    _drawer(draw_hires_departures, history, today),
                    _drawer(draw_snapshot, df, 'Average Tenure (yrs)', 'Department'),
                ]
                rows_of_two(overview)

            if options.include_analytics_charts and data.analytics_charts:
                pager.heading('Charts from the Analytics tab', keep_with=0.28)
                for _title, draw in data.analytics_charts:
                    pager.chart_row([draw], height=0.28)

            pager.close()
            return pager.page_no
