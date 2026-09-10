# chart_widget.py
# A reusable PyQt6 widget that embeds a Matplotlib figure inside the application window.
# PyQt6 and Matplotlib are separate libraries — this class bridges them using
# FigureCanvasQTAgg, which is Matplotlib's official Qt rendering backend.
# Every chart in the application (bar, pie, line) is drawn using an instance of this class.

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.colors import to_rgba
from PyQt6.QtCore import Qt
from matplotlib.figure import Figure
from matplotlib.patches import Circle
from PyQt6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout, QSplitter


# Drag handle between resizable charts — turns blue on hover so it's discoverable.
SPLITTER_STYLE = '''
    QSplitter::handle { background: #E5E7EB; border-radius: 2px; }
    QSplitter::handle:hover { background: #2E75B6; }
'''


def make_splitter(orientation) -> QSplitter:
    # QSplitter the user can drag to resize charts; panes can't collapse to nothing.
    splitter = QSplitter(orientation)
    splitter.setHandleWidth(6)
    splitter.setChildrenCollapsible(False)
    splitter.setStyleSheet(SPLITTER_STYLE)
    return splitter


def set_title_with_period(ax, title, period=None, **title_kwargs):
    # Chart title with an optional smaller grey line underneath showing the
    # time period the chart covers.
    title_kwargs.setdefault('fontsize', 11)
    title_kwargs.setdefault('fontweight', 'bold')
    ax.set_title(title, pad=20 if period else 6, **title_kwargs)
    if period:
        ax.text(0.5, 1.012, period, transform=ax.transAxes, ha='center',
                va='bottom', fontsize=9, color='#555555')


def draw_pie(ax, labels, values, colors, donut=False, value_fmt=None):
    # Pie/donut with percentages inside the larger slices and a legend beside
    # it, so labels on small neighbouring slices can't overlap each other.
    total = float(sum(values)) or 1.0
    wedges, _texts, _pcts = ax.pie(
        values, colors=colors, startangle=90, counterclock=False,
        autopct=lambda p: f'{p:.0f}%' if p >= 6 else '',
        pctdistance=0.78 if donut else 0.65,
        textprops={'fontsize': 8, 'color': 'white', 'fontweight': 'bold'},
        wedgeprops={'linewidth': 1, 'edgecolor': 'white'},
    )
    if donut:
        ax.add_artist(Circle((0, 0), 0.55, fc='white'))
    fmt = value_fmt or (lambda v: f'{v:,.0f}')
    legend_labels = [f'{lbl}  {fmt(v)} ({v / total:.0%})' for lbl, v in zip(labels, values)]
    ax.legend(wedges, legend_labels, loc='center left', bbox_to_anchor=(1.0, 0.5),
              fontsize=8, frameon=False)
    ax.set_aspect('equal')
    return wedges


# Hover highlight for clickable bars / slices / points
_HOVER_EDGE = '#F5A623'   # amber outline — stands out against the blues and navy
_HOVER_DARKEN = 0.75      # hovered fill is darkened to this fraction


class HoverHighlighter:
    # Highlights the clickable chart element under the mouse (darker fill,
    # amber outline, hand cursor) and shows a tooltip, so users can tell which
    # parts of a chart they can click to drill down.

    def __init__(self, canvas):
        self._canvas = canvas
        self._items: dict = {}        # artist -> tooltip text
        self._hovered = None
        self._saved_style = None
        self._tooltip = None
        canvas.mpl_connect('motion_notify_event', self._on_move)
        canvas.mpl_connect('figure_leave_event', lambda _e: self._set_hovered(None, None))

    def set_items(self, items: dict):
        # Called after every redraw with the new clickable artists.
        self._items = items
        self._hovered = None
        self._saved_style = None
        self._tooltip = None
        self._canvas.unsetCursor()

    def _on_move(self, event):
        hit = None
        if event.inaxes is not None:
            for artist in self._items:
                if artist.axes is event.inaxes and artist.contains(event)[0]:
                    hit = artist
                    break
        self._set_hovered(hit, event)

    def _set_hovered(self, artist, event):
        if artist is self._hovered:
            if artist is not None:
                self._move_tooltip(event)
            return
        changed = self._hovered is not None or artist is not None
        self._restore()
        self._hovered = artist
        if artist is None:
            self._canvas.unsetCursor()
        else:
            self._saved_style = (artist.get_facecolor() if hasattr(artist, 'get_facecolor') else None,
                                 artist.get_edgecolor() if hasattr(artist, 'get_edgecolor') else None,
                                 artist.get_linewidth() if hasattr(artist, 'get_linewidth') else None,
                                 artist.get_zorder())
            if hasattr(artist, 'set_facecolor') and not hasattr(artist, 'get_xydata'):
                r, g, b, a = to_rgba(artist.get_facecolor())
                artist.set_facecolor((r * _HOVER_DARKEN, g * _HOVER_DARKEN, b * _HOVER_DARKEN, a))
                artist.set_edgecolor(_HOVER_EDGE)
                artist.set_linewidth(2.5)
            else:  # line marker
                artist.set_markeredgecolor(_HOVER_EDGE)
                artist.set_markeredgewidth(2.5)
                artist.set_markersize(artist.get_markersize() * 1.4)
            artist.set_zorder(5)
            self._canvas.setCursor(Qt.CursorShape.PointingHandCursor)
            self._show_tooltip(artist, event)
        if changed:
            self._canvas.draw_idle()

    def _restore(self):
        artist = self._hovered
        if artist is None or self._saved_style is None:
            if self._tooltip is not None:
                self._tooltip.set_visible(False)
            return
        face, edge, width, zorder = self._saved_style
        if hasattr(artist, 'get_xydata'):
            artist.set_markeredgecolor(artist.get_color())
            artist.set_markeredgewidth(1.0)
            artist.set_markersize(artist.get_markersize() / 1.4)
        else:
            artist.set_facecolor(face)
            artist.set_edgecolor(edge)
            artist.set_linewidth(width)
        artist.set_zorder(zorder)
        if self._tooltip is not None:
            self._tooltip.set_visible(False)
        self._saved_style = None

    def _show_tooltip(self, artist, event):
        ax = artist.axes
        if self._tooltip is None or self._tooltip.axes is not ax:
            self._tooltip = ax.annotate(
                '', xy=(0, 0), xycoords='figure pixels', xytext=(12, 12),
                textcoords='offset points', fontsize=9, zorder=10,
                bbox=dict(boxstyle='round,pad=0.4', fc='#1F3864', ec='none', alpha=0.92),
                color='white', annotation_clip=False,
            )
        self._tooltip.set_text(self._items[artist])
        self._tooltip.set_visible(True)
        self._move_tooltip(event)

    def _move_tooltip(self, event):
        if self._tooltip is None or event is None:
            return
        fig_w = self._canvas.figure.bbox.width
        # Flip the tooltip to the left of the cursor near the right edge
        self._tooltip.set_position((-12, 12) if event.x > fig_w * 0.65 else (12, 12))
        self._tooltip.set_horizontalalignment('right' if event.x > fig_w * 0.65 else 'left')
        self._tooltip.xy = (event.x, event.y)
        self._canvas.draw_idle()


class ChartWidget(FigureCanvasQTAgg):
    def __init__(self, width=6, height=4, dpi=100, parent=None):
        # Create a Matplotlib figure at the given size and resolution
        # 'tight' layout re-fits titles and labels every time the chart is
        # resized, so nothing gets clipped when the user drags a divider.
        fig = Figure(figsize=(width, height), dpi=dpi, layout='tight')

        # axes is the area where the chart is actually drawn
        self.axes = fig.add_subplot(111)

        # Pass the figure to the Qt canvas so it can render it
        super().__init__(fig)
        self.setParent(parent)

        # Allow the widget to grow and shrink with the window
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    def clear_axes(self):
        # Remove all content from the chart area so it can be redrawn.
        self.axes.cla()

    def reset_axes(self, polar=False):
        # Replace axes — needed when switching between standard and polar (radar) types.
        self.figure.clear()
        self.axes = self.figure.add_subplot(111, polar=polar)

    def refresh(self):
        # Repaint the canvas. The 'tight' layout engine prevents label clipping;
        # it's re-set here because a one-off fig.tight_layout() call elsewhere
        # would otherwise switch automatic re-fitting off.
        self.figure.set_layout_engine('tight')
        self.draw()


# ChartWidget paired with a Matplotlib navigation toolbar (zoom, pan, save).
class ChartWithToolbar(QWidget):

    def __init__(self, width=6, height=4, dpi=100, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._chart = ChartWidget(width=width, height=height, dpi=dpi)
        self._toolbar = NavigationToolbar2QT(self._chart, self)

        layout.addWidget(self._toolbar)
        layout.addWidget(self._chart)

    @property
    def axes(self):
        return self._chart.axes

    def clear_axes(self):
        self._chart.clear_axes()

    def reset_axes(self, polar=False):
        self._chart.reset_axes(polar=polar)

    @property
    def figure(self):
        return self._chart.figure

    def redraw(self):
        self._chart.draw()

    def set_hover_items(self, items: dict):
        # items: {artist: tooltip text} for the clickable parts of the chart.
        if not hasattr(self, '_hover'):
            self._hover = HoverHighlighter(self._chart)
        self._hover.set_items(items)

    def set_toolbar_visible(self, visible: bool):
        # Small charts hide the zoom/pan toolbar to give the chart more room.
        self._toolbar.setVisible(visible)

    def refresh(self):
        self._chart.refresh()
