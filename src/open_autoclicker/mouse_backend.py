"""Mouse control backends.

Two implementations behind a common interface:

* ``PynputBackend`` — uses pynput. Works on X11, Windows and macOS.
* ``UinputBackend`` — uses evdev's ``/dev/uinput`` (Linux only). This operates
  at the kernel input layer, so it also works under Wayland, where pynput's
  cursor movement is blocked by the compositor.

``make_backend()`` picks the right one for the current environment, preferring
uinput on a Linux/Wayland session and falling back to pynput otherwise.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Protocol

from .clicker import MouseButton


class MouseBackend(Protocol):
    """Minimal mouse control surface used by the engine."""

    def move(self, dx: int, dy: int) -> None:
        """Move the cursor by a relative offset."""

    def click(self, button: MouseButton, count: int) -> None:
        """Press and release ``button`` ``count`` times."""

    def close(self) -> None:
        """Release any resources."""


class PynputBackend:
    """Mouse control via pynput (X11, Windows, macOS)."""

    def __init__(self) -> None:
        from pynput.mouse import Controller

        self._mouse = Controller()

    def move(self, dx: int, dy: int) -> None:
        self._mouse.move(dx, dy)

    def click(self, button: MouseButton, count: int) -> None:
        self._mouse.click(button.to_pynput(), count)

    def close(self) -> None:
        pass


class UinputBackend:
    """Mouse control via evdev /dev/uinput (Linux, works under Wayland)."""

    def __init__(self) -> None:
        from evdev import UInput, ecodes

        self._ecodes = ecodes
        capabilities = {
            ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y],
            ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE],
        }
        self._ui = UInput(capabilities, name="open-autoclicker-virtual-mouse")
        # Give the compositor a moment to register the new input device.
        time.sleep(0.3)

    def _button_code(self, button: MouseButton) -> int:
        e = self._ecodes
        return {
            MouseButton.LEFT: e.BTN_LEFT,
            MouseButton.MIDDLE: e.BTN_MIDDLE,
            MouseButton.RIGHT: e.BTN_RIGHT,
        }[button]

    def move(self, dx: int, dy: int) -> None:
        e = self._ecodes
        if dx:
            self._ui.write(e.EV_REL, e.REL_X, dx)
        if dy:
            self._ui.write(e.EV_REL, e.REL_Y, dy)
        self._ui.syn()

    def click(self, button: MouseButton, count: int) -> None:
        e = self._ecodes
        code = self._button_code(button)
        for _ in range(count):
            self._ui.write(e.EV_KEY, code, 1)  # press
            self._ui.syn()
            self._ui.write(e.EV_KEY, code, 0)  # release
            self._ui.syn()
            time.sleep(0.01)

    def close(self) -> None:
        try:
            self._ui.close()
        except Exception:
            pass


def _is_wayland() -> bool:
    return (
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        or bool(os.environ.get("WAYLAND_DISPLAY"))
    )


def make_backend() -> MouseBackend:
    """Return the best available mouse backend for this environment.

    On Linux/Wayland, pynput cannot move the cursor, so uinput is preferred.
    If uinput is unavailable (missing evdev or no permission on /dev/uinput),
    fall back to pynput so clicking still works where it can.
    """
    if sys.platform.startswith("linux") and _is_wayland():
        try:
            return UinputBackend()
        except Exception:
            # evdev missing, or no write access to /dev/uinput.
            return PynputBackend()
    return PynputBackend()
