"""Application entry point."""

from __future__ import annotations

import sys


def main() -> int:
    # Import inside main so `python -m open_autoclicker --version`-style tooling
    # and packaging can import the module without a display/Qt available.
    from PySide6.QtWidgets import QApplication

    from . import APP_ID, APP_NAME
    from .gui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_ID)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
