"""Application bootstrap.

Uses absolute imports so it works both as a package module (``python -m
open_autoclicker``) and as a standalone entry script frozen by PyInstaller,
where relative imports have no parent package.
"""

from __future__ import annotations

import sys


def app_icon():
    """Load the bundled application icon as a QIcon.

    Works both from source and from a PyInstaller bundle. Returns an empty
    QIcon if the resource cannot be found, so startup never fails over an icon.
    """
    from importlib.resources import files

    from PySide6.QtGui import QIcon

    try:
        path = files("open_autoclicker.resources") / "icon.png"
        return QIcon(str(path))
    except Exception:
        return QIcon()


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from open_autoclicker import APP_ID, APP_NAME
    from open_autoclicker.gui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_ID)

    icon = app_icon()
    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
