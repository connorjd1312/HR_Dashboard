from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter

from core import analytics, dashboard_layout
from ui.drag_drop import KPI_MIME, mime_payload, start_drag


# Clickable KPI card; emits clicked(metric) on body click
class KPICard(QFrame):

    clicked = pyqtSignal(str)
    remove_clicked = pyqtSignal(str)

    def __init__(self, metric: str, value: str, parent=None, change: tuple | None = None,
                 change_tooltip: str = ''):
        super().__init__(parent)
        self._metric = metric
        self._press_pos = None

        self.setObjectName('KPICard')
        self.setStyleSheet('''
            QFrame#KPICard           { background: #1F3864; border-radius: 8px; }
            QFrame#KPICard:hover     { background: #2E75B6; }
        ''')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(86)
        description = analytics.describe_metric(metric)
        hint = 'Click to see the breakdown.  Drag to rearrange the cards.'
        self.setToolTip(f'{description}\n\n{hint}' if description else hint)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 8, 10, 10)
        v.setSpacing(2)

        # Top row: metric name + ✕ button
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        self._label = QLabel(metric)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(
            'color: white; font-size: 11px; background: transparent;'
        )
        top.addWidget(self._label, 1)

        rm = QPushButton('✕')
        rm.setFixedSize(20, 20)
        rm.setCursor(Qt.CursorShape.PointingHandCursor)
        rm.setStyleSheet('''
            QPushButton {
                color: white;
                background: rgba(255,255,255,0.18);
                border: none; border-radius: 10px;
                font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: rgba(220,80,80,0.85); }
        ''')
        rm.clicked.connect(lambda: self.remove_clicked.emit(self._metric))
        top.addWidget(rm)
        v.addLayout(top)

        self._value = QLabel(value)
        self._value.setStyleSheet(
            'color: white; font-size: 22px; font-weight: bold; background: transparent;'
        )
        v.addWidget(self._value)

        # Change vs the previous period, e.g. '▼ 2.1 pts vs previous period'
        if change:
            text, tone = change
            colour = {'good': '#7DDC9C', 'bad': '#FF9C8F'}.get(tone, '#C9D3E3')
            change_lbl = QLabel(f'{text} vs previous period')
            # Wrap on narrow windows
            change_lbl.setWordWrap(True)
            change_lbl.setStyleSheet(f'color: {colour}; font-size: 11px; background: transparent;')
            if change_tooltip:
                change_lbl.setToolTip(change_tooltip)
            v.addWidget(change_lbl)
        v.addStretch()

    def set_value(self, value: str):
        self._value.setText(value)

    # A press that stays put is a click; one that moves is a drag

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self._press_pos).manhattanLength()
                >= QApplication.startDragDistance()):
            self._press_pos = None
            start_drag(self, KPI_MIME, self._metric)
            return  # the drop may have rebuilt this card
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            self._press_pos = None
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit(self._metric)
        super().mouseReleaseEvent(event)


class KPIRow(QWidget):

    reordered = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(8)
        self._indicator_x: int | None = None

    def _cards(self) -> list[KPICard]:
        cards = []
        for i in range(self._row.count()):
            w = self._row.itemAt(i).widget()
            if isinstance(w, KPICard):
                cards.append(w)
        return cards

    def drop_index(self, x: float) -> int:
        return dashboard_layout.insertion_index([c.geometry().center().x() for c in self._cards()], x)

    def _indicator_position(self, index: int) -> int | None:
        cards = self._cards()
        if not cards:
            return None
        spacing = self._row.spacing()
        if index <= 0:
            return max(0, cards[0].geometry().left() - spacing // 2)
        if index >= len(cards):
            return cards[-1].geometry().right() + spacing // 2
        return (cards[index - 1].geometry().right() + cards[index].geometry().left()) // 2

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(KPI_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(KPI_MIME):
            self._indicator_x = self._indicator_position(self.drop_index(event.position().x()))
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._indicator_x = None
        self.update()

    def dropEvent(self, event):
        metric = mime_payload(event.mimeData(), KPI_MIME)
        index = self.drop_index(event.position().x())
        self._indicator_x = None
        self.update()
        if metric:
            event.acceptProposedAction()
            self.reordered.emit(metric, index)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._indicator_x is not None:
            p = QPainter(self)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#F5A623'))
            p.drawRoundedRect(self._indicator_x - 2, 0, 4, self.height(), 2, 2)
            p.end()


# Tile that opens a menu of available metrics when clicked
class AddKPIButton(QFrame):

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('AddKPIButton')
        self.setStyleSheet('''
            QFrame#AddKPIButton {
                background: white;
                border: 2px dashed #B0B7C1;
                border-radius: 8px;
            }
            QFrame#AddKPIButton:hover {
                border-color: #2E75B6;
                background: #EBF5FB;
            }
        ''')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(86)

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)

        plus = QLabel('＋  Add Card')
        plus.setStyleSheet(
            'color: #2E75B6; font-size: 12px; font-weight: bold; background: transparent; border: none;'
        )
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(plus)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
