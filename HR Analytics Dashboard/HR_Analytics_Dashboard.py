# Entry point for the HR Analytics Dashboard application.
# Run this file to launch the application: python HR_Analytics_Dashboard.py

import sys

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    # Create the Qt application — required before any UI elements are created
    app = QApplication(sys.argv)

    # Fusion gives a consistent, modern look across all Windows versions
    app.setStyle('Fusion')

    # Create and display the main window
    window = MainWindow()
    window.show()

    # Hand control to Qt's event loop — app runs until the window is closed
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
