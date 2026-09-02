# chart_widget.py
# A reusable PyQt6 widget that embeds a Matplotlib figure inside the application window.
# PyQt6 and Matplotlib are separate libraries — this class bridges them using
# FigureCanvasQTAgg, which is Matplotlib's official Qt rendering backend.
# Every chart in the application (bar, pie, line) is drawn using an instance of this class.

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
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

    def refresh(self):
        self._chart.refresh()
