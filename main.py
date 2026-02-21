"""
main.py - Application entry point.

Run from the hackadoodle/ root:
    python main.py
"""

import sys
from pathlib import Path

# Make sure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from geekmagic_app.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Hackadoodle")
    app.setStyle("Fusion")   # consistent look across Windows/Mac/Linux

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
