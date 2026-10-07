"""Access to bundled image resources.

Kept in its own module so both the app bootstrap and the GUI can use it
without importing each other.
"""

from __future__ import annotations

from importlib.resources import files


def app_icon():
    """Load the bundled application icon as a QIcon.

    Works both from source and from a PyInstaller bundle. Returns an empty
    QIcon if the resource cannot be found, so startup never fails over an icon.
    """
    from PySide6.QtGui import QIcon

    try:
        path = files("open_autoclicker.resources") / "icon.png"
        return QIcon(str(path))
    except Exception:
        return QIcon()
