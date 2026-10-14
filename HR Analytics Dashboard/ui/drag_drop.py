from __future__ import annotations

from PyQt6.QtCore import QMimeData, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

KPI_MIME = 'application/x-hr-dashboard-kpi'
PANEL_MIME = 'application/x-hr-dashboard-panel'

_DRAG_PICTURE_WIDTH = 300


def start_drag(source: QWidget, mime_type: str, payload: str, picture_of: QWidget | None = None) -> None:
    # Parented to the window in case the source widget is deleted
    drag = QDrag(source.window())
    mime = QMimeData()
    mime.setData(mime_type, payload.encode('utf-8'))
    drag.setMimeData(mime)

    pix = (picture_of or source).grab()
    if pix.width() > _DRAG_PICTURE_WIDTH:
        pix = pix.scaledToWidth(_DRAG_PICTURE_WIDTH, Qt.TransformationMode.SmoothTransformation)
    faded = QPixmap(pix.size())
    faded.fill(Qt.GlobalColor.transparent)
    p = QPainter(faded)
    p.setOpacity(0.7)
    p.drawPixmap(0, 0, pix)
    p.end()
    drag.setPixmap(faded)
    drag.setHotSpot(QPoint(min(40, faded.width() // 2), 14))
    drag.exec(Qt.DropAction.MoveAction)


def mime_payload(mime: QMimeData, mime_type: str) -> str | None:
    if not mime.hasFormat(mime_type):
        return None
    return bytes(mime.data(mime_type)).decode('utf-8')


class DragHandle(QWidget):

    drag_requested = pyqtSignal()

    def __init__(self, parent=None, tooltip: str = 'Drag to rearrange'):
        super().__init__(parent)
        self.setFixedSize(16, 24)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(tooltip)
        self._press = None
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#2E75B6' if self._hover else '#9AA5B1'))
        for col in range(2):
            for row in range(3):
                p.drawEllipse(QPoint(5 + col * 6, 6 + row * 6), 1, 1)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance():
                self._press = None
                self.drag_requested.emit()
                self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        self._press = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
