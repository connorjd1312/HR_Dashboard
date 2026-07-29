# message_box.py
# Styled QMessageBox helpers.
#
# Plain QMessageBox.question()/.information()/etc. inherit text color from the
# OS palette but the box background from the Fusion style — on a dark-mode
# Windows theme that pairs white text with a white background, making the
# message unreadable. These helpers force explicit, always-readable colors
# matching the rest of the app.

from PyQt6.QtWidgets import QMessageBox

_STYLE = '''
    QMessageBox { background-color: white; }
    QMessageBox QLabel { color: #333333; font-size: 12px; background: transparent; }
    QMessageBox QPushButton {
        background-color: #1F3864; color: white;
        border: none; border-radius: 5px;
        padding: 6px 16px; font-size: 12px; min-width: 70px;
    }
    QMessageBox QPushButton:hover { background-color: #2E75B6; }
    QMessageBox QPushButton:pressed { background-color: #163060; }
'''


def _build(parent, icon, title, text):
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStyleSheet(_STYLE)
    return box


def information(parent, title, text):
    box = _build(parent, QMessageBox.Icon.Information, title, text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def warning(parent, title, text):
    box = _build(parent, QMessageBox.Icon.Warning, title, text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def critical(parent, title, text):
    box = _build(parent, QMessageBox.Icon.Critical, title, text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def question(parent, title, text,
             buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
             default=QMessageBox.StandardButton.No):
    box = _build(parent, QMessageBox.Icon.Question, title, text)
    box.setStandardButtons(buttons)
    box.setDefaultButton(default)
    return box.exec()


def custom(parent, title, text, button_specs):
    # button_specs: ordered list of (label, ButtonRole) tuples.
    # Returns the label of the clicked button, or None if dismissed unanswered.
    box = _build(parent, QMessageBox.Icon.Question, title, text)
    buttons = [box.addButton(label, role) for label, role in button_specs]
    box.exec()
    clicked = box.clickedButton()
    for label, btn in zip((spec[0] for spec in button_specs), buttons):
        if btn is clicked:
            return label
    return None
