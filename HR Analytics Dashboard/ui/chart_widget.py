# chart_widget.py
# A reusable PyQt6 widget that embeds a Matplotlib figure inside the application window.
# PyQt6 and Matplotlib are separate libraries — this class bridges them using
# FigureCanvasQTAgg, which is Matplotlib's official Qt rendering backend.
# Every chart in the application (bar, pie, line) is drawn using an instance of this class.

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QSizePolicy


class ChartWidget(FigureCanvasQTAgg):
    def __init__(self, width=6, height=4, dpi=100, parent=None):
        # Create a Matplotlib figure at the given size and resolution
        fig = Figure(figsize=(width, height), dpi=dpi)

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
        """Remove all content from the chart area so it can be redrawn."""
        self.axes.cla()

    def refresh(self):
        """Tighten layout to prevent label clipping, then repaint the canvas."""
        self.figure.tight_layout()
        self.draw()
