"""Application bootstrap.

Uses absolute imports so it works both as a package module (``python -m
open_autoclicker``) and as a standalone entry script frozen by PyInstaller,
where relative imports have no parent package.
"""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from open_autoclicker import APP_ID, APP_NAME
    from open_autoclicker.gui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_ID)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
