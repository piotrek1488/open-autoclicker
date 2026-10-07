"""Application bootstrap.

Uses absolute imports so it works both as a package module (``python -m
open_autoclicker``) and as a standalone entry script frozen by PyInstaller,
where relative imports have no parent package.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    # Drop any inherited startup-notification tokens so a stale token can't be
    # reused for this process.
    for var in ("DESKTOP_STARTUP_ID", "XDG_ACTIVATION_TOKEN"):
        os.environ.pop(var, None)

    from PySide6.QtWidgets import QApplication

    from open_autoclicker import APP_ID, APP_NAME
    from open_autoclicker.gui import MainWindow
    from open_autoclicker.icons import app_icon

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # Note: deliberately not calling setApplicationDisplayName — Qt would append
    # " - <display name>" to every window title.
    app.setDesktopFileName(APP_ID)

    icon = app_icon()
    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
