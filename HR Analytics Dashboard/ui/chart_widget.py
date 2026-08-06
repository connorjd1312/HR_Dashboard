# chart_widget.py
# A reusable PyQt6 widget that embeds a Matplotlib figure inside the application window.
# PyQt6 and Matplotlib are separate libraries — this class bridges them using
# FigureCanvasQTAgg, which is Matplotlib's official Qt rendering backend.
# Every chart in the application (bar, pie, line) is drawn using an instance of this class.

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout
from PyQt6.QtGui import QPalette, QColor


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
        # Remove all content from the chart area so it can be redrawn.
        self.axes.cla()

    def reset_axes(self, polar=False):
        # Replace axes — needed when switching between standard and polar (radar) types.
        self.figure.clear()
        self.axes = self.figure.add_subplot(111, polar=polar)

    def refresh(self):
        # Tighten layout to prevent label clipping, then repaint the canvas.
        self.figure.tight_layout()
        self.draw()


# ChartWidget paired with a Matplotlib navigation toolbar (zoom, pan, save).
class ChartWithToolbar(QWidget):

    def __init__(self, width=6, height=4, dpi=100, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # NavigationToolbar2QT bakes its icon colours once, at construction,
        # based on whether its background looks dark or light. On a system in
        # dark mode (and with no palette set yet) that reads as "dark", so
        # matplotlib recolours every icon white. Every chart card in this app
        # is then explicitly styled white, so those pre-baked white icons
        # render on a white background and disappear (Save, Pan/"Move", etc.).
        # Forcing a light palette here — before the toolbar is built — keeps
        # matplotlib on the light-background branch so icons stay their normal
        # dark colour no matter what the OS theme is.
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor('white'))
        pal.setColor(QPalette.ColorRole.WindowText, QColor('black'))
        pal.setColor(QPalette.ColorRole.Button, QColor('white'))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor('black'))
        self.setPalette(pal)

        self._chart = ChartWidget(width=width, height=height, dpi=dpi)
        self._toolbar = NavigationToolbar2QT(self._chart, self)
        self._toolbar.setStyleSheet('''
            QToolBar { background: white; border: none; spacing: 2px; }
            QToolButton { background: white; border: none; border-radius: 4px; padding: 3px; }
            QToolButton:hover { background: #EBF5FB; }
            QToolButton:pressed, QToolButton:checked { background: #D6EAF8; }
        ''')

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
