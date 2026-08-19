from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal


# Clickable KPI card; emits clicked(metric) on body click, remove_clicked(metric) on ✕.
class KPICard(QFrame):

    clicked        = pyqtSignal(str)
    remove_clicked = pyqtSignal(str)

    def __init__(self, metric: str, value: str, parent=None):
        super().__init__(parent)
        self._metric = metric

        self.setObjectName('KPICard')
        self.setStyleSheet('''
            QFrame#KPICard           { background: #1F3864; border-radius: 8px; }
            QFrame#KPICard:hover     { background: #2E75B6; }
        ''')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(86)

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
            'color: white; font-size: 11px; font-family: Arial; background: transparent;'
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
            'color: white; font-size: 22px; font-weight: bold; font-family: Arial; background: transparent;'
        )
        v.addWidget(self._value)
        v.addStretch()

    def set_value(self, value: str):
        self._value.setText(value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._metric)
        super().mousePressEvent(event)


# Tile that opens a menu of available metrics when clicked.
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
