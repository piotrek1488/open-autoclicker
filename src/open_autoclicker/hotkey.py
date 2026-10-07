"""Global hotkey listener.

Wraps pynput's GlobalHotKeys so a single configurable shortcut can toggle the
clicker from anywhere, even when the window is not focused. The listener runs
in its own thread (managed internally by pynput).
"""

from __future__ import annotations

from typing import Callable, Optional

from pynput import keyboard


# Human-friendly default shown in the UI; stored/parsed in pynput notation.
DEFAULT_HOTKEY = "<f6>"


def normalize_hotkey(text: str) -> str:
    """Normalise a user-entered hotkey string into pynput's canonical form.

    Accepts things like "F6", "Ctrl+Shift+K", "<ctrl>+<alt>+h" and returns a
    string pynput's HotKey.parse understands, e.g. "<ctrl>+<shift>+k".
    Raises ValueError if the result cannot be parsed.
    """
    if not text or not text.strip():
        raise ValueError("Hotkey is empty")

    parts = [p.strip().lower() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("Hotkey is empty")

    modifiers = {"ctrl", "control", "alt", "alt_gr", "shift", "cmd", "super", "win"}
    alias = {"control": "ctrl", "win": "cmd", "super": "cmd"}

    tokens = []
    for part in parts:
        # Already in canonical "<name>" form (e.g. re-applying "<f6>"): keep as-is.
        if part.startswith("<") and part.endswith(">") and len(part) > 2:
            tokens.append(part)
            continue
        key = alias.get(part, part)
        if key in modifiers:
            tokens.append(f"<{key}>")
        elif len(part) == 1:
            tokens.append(part)
        else:
            # Named key such as f6, space, enter, esc.
            tokens.append(f"<{key}>")

    combo = "+".join(tokens)
    # Validate by parsing; raises ValueError on bad input.
    keyboard.HotKey.parse(combo)
    return combo


class HotkeyManager:
    """Registers a single global hotkey that invokes a callback when pressed."""

    def __init__(self) -> None:
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._combo: Optional[str] = None
        self._callback: Optional[Callable[[], None]] = None

    @property
    def active_hotkey(self) -> Optional[str]:
        return self._combo

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        """Register (or re-register) the global hotkey.

        hotkey: a string accepted by normalize_hotkey.
        callback: invoked (from the listener thread) when the hotkey fires.
        """
        combo = normalize_hotkey(hotkey)
        self.stop()
        self._callback = callback
        self._combo = combo
        self._listener = keyboard.GlobalHotKeys({combo: self._on_activate})
        self._listener.start()

    def _on_activate(self) -> None:
        if self._callback is not None:
            self._callback()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
