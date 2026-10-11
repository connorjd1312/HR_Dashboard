# Entry point for the HR Analytics Dashboard application.
# Run this file to launch the application: python HR_Analytics_Dashboard.py

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

# In the packaged .exe, bundled files are unpacked to sys._MEIPASS instead
APP_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def main():
    # Create the Qt application — required before any UI elements are created
    app = QApplication(sys.argv)

    # Fusion gives a consistent, modern look across all Windows versions
    app.setStyle('Fusion')
    app.setWindowIcon(QIcon(str(APP_DIR / 'assets' / 'app.ico')))

    # Create and display the main window
    window = MainWindow()
    window.show()

    # Hand control to Qt's event loop — app runs until the window is closed
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
