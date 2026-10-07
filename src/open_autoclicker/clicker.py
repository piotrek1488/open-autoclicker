"""Core auto-clicking engine.

Runs the click loop in a background thread so the GUI stays responsive.
The engine is intentionally free of any Qt dependency so it can be tested
and reused in isolation.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from pynput.mouse import Button


class MouseButton(str, Enum):
    """Mouse button to click."""

    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"

    def to_pynput(self) -> Button:
        return {
            MouseButton.LEFT: Button.left,
            MouseButton.MIDDLE: Button.middle,
            MouseButton.RIGHT: Button.right,
        }[self]


class ClickType(str, Enum):
    """Single or double click per iteration."""

    SINGLE = "single"
    DOUBLE = "double"


# Minimum allowed interval between clicks. A 1 s floor guarantees the user can
# always move the pointer and click Stop (or the tray) to regain control.
MIN_INTERVAL_MS = 1000


@dataclass
class ClickConfig:
    """Configuration for a clicking session.

    interval_ms: base delay between clicks in milliseconds.
    button: which mouse button to press.
    click_type: single or double click per repetition.
    repeat_count: number of clicks to perform; None or <= 0 means infinite.
    random_jitter_ms: maximum extra random delay (0..jitter) added to each
        interval to emulate a more human-like cadence.
    start_delay_ms: one-off delay before the first click (pre-delay).
    """

    interval_ms: int = 1000
    button: MouseButton = MouseButton.LEFT
    click_type: ClickType = ClickType.SINGLE
    repeat_count: Optional[int] = None
    random_jitter_ms: int = 0
    start_delay_ms: int = 0
    # Independent actions performed each interval. Any combination is valid as
    # long as at least one is enabled: click only, jiggle only, or both.
    do_click: bool = True
    jiggle: bool = False
    jiggle_px: int = 1

    def __post_init__(self) -> None:
        # Ensure enums are actual enum members, not bare strings (can happen
        # when Qt's QComboBox.currentData() returns a serialised value inside
        # a frozen/PyInstaller bundle).
        if isinstance(self.button, str) and not isinstance(self.button, MouseButton):
            self.button = MouseButton(self.button)
        if isinstance(self.click_type, str) and not isinstance(self.click_type, ClickType):
            self.click_type = ClickType(self.click_type)

    def validate(self) -> None:
        # Enforce a 1 s floor on the interval: faster than that and the user may
        # not be able to regain control of the pointer to stop the app.
        if self.interval_ms < MIN_INTERVAL_MS:
            raise ValueError(
                f"interval_ms must be >= {MIN_INTERVAL_MS} (at least 1 second)"
            )
        if self.random_jitter_ms < 0:
            raise ValueError("random_jitter_ms must be >= 0")
        if self.start_delay_ms < 0:
            raise ValueError("start_delay_ms must be >= 0")
        if not self.do_click and not self.jiggle:
            raise ValueError("Enable clicking, cursor movement, or both")
        if self.jiggle_px < 1:
            raise ValueError("jiggle_px must be >= 1")

    def is_infinite(self) -> bool:
        return self.repeat_count is None or self.repeat_count <= 0


@dataclass
class _Callbacks:
    on_started: Optional[Callable[[], None]] = None
    on_stopped: Optional[Callable[[int], None]] = None
    on_tick: Optional[Callable[[int], None]] = None
    on_error: Optional[Callable[[Exception], None]] = None


class ClickerEngine:
    """Threaded auto-clicker.

    Call start(config) to begin and stop() to end. Callbacks are invoked from
    the worker thread, so GUI consumers must marshal them onto the UI thread.
    """

    def __init__(self, backend=None) -> None:
        # Mouse backend is created lazily on start() so the right one is chosen
        # for the current session. Tests may inject a fake via `backend`.
        self._backend = backend
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._clicks_done = 0
        self._callbacks = _Callbacks()

    # ---- callback registration -------------------------------------------------
    def set_callbacks(
        self,
        on_started: Optional[Callable[[], None]] = None,
        on_stopped: Optional[Callable[[int], None]] = None,
        on_tick: Optional[Callable[[int], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._callbacks = _Callbacks(on_started, on_stopped, on_tick, on_error)

    # ---- state -----------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def clicks_done(self) -> int:
        return self._clicks_done

    # ---- control ---------------------------------------------------------------
    def start(self, config: ClickConfig) -> bool:
        """Start clicking. Returns False if already running."""
        config.validate()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            if self._backend is None:
                # Lazy import avoids a circular import with mouse_backend.
                from .mouse_backend import make_backend

                self._backend = make_backend()
            self._stop_event.clear()
            self._clicks_done = 0
            self._thread = threading.Thread(
                target=self._run, args=(config,), name="clicker-engine", daemon=True
            )
            self._thread.start()
        return True

    def stop(self, join: bool = False, timeout: float = 2.0) -> None:
        """Signal the worker to stop. Optionally wait for it to finish."""
        self._stop_event.set()
        if join:
            thread = self._thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout)

    def close(self) -> None:
        """Stop the engine and release the mouse backend (e.g. /dev/uinput)."""
        self.stop(join=True)
        if self._backend is not None:
            try:
                self._backend.close()
            except Exception:
                pass
            self._backend = None

    def toggle(self, config: ClickConfig) -> bool:
        """Start if stopped, stop if running. Returns True if now running."""
        if self.is_running:
            self.stop()
            return False
        self.start(config)
        return True

    # ---- worker ----------------------------------------------------------------
    def _run(self, config: ClickConfig) -> None:
        if self._callbacks.on_started:
            self._callbacks.on_started()
        try:
            if config.start_delay_ms > 0:
                if self._sleep_interruptible(config.start_delay_ms / 1000.0):
                    return

            button = config.button
            double = config.click_type == ClickType.DOUBLE

            while not self._stop_event.is_set():
                if not config.is_infinite() and self._clicks_done >= config.repeat_count:
                    break

                # Each iteration performs the enabled actions. Move first so a
                # click lands at the nudged position when both are on.
                if config.jiggle:
                    self._do_jiggle(config.jiggle_px)
                if config.do_click:
                    self._do_click(button, double)

                self._clicks_done += 1
                if self._callbacks.on_tick:
                    self._callbacks.on_tick(self._clicks_done)

                if not config.is_infinite() and self._clicks_done >= config.repeat_count:
                    break

                delay = config.interval_ms / 1000.0
                if config.random_jitter_ms > 0:
                    delay += random.uniform(0, config.random_jitter_ms / 1000.0)
                if self._sleep_interruptible(delay):
                    break
        except Exception as exc:  # pragma: no cover - defensive
            if self._callbacks.on_error:
                self._callbacks.on_error(exc)
        finally:
            if self._callbacks.on_stopped:
                self._callbacks.on_stopped(self._clicks_done)

    def _do_click(self, button: MouseButton, double: bool) -> None:
        count = 2 if double else 1
        self._backend.click(button, count)

    def _do_jiggle(self, px: int) -> None:
        """Nudge the cursor out and back so it ends on its starting point.

        The move is split into small 1 px steps. A single large relative move is
        distorted by pointer acceleration (libinput), so the return move would
        not exactly cancel the outward one and the cursor would drift. Stepping
        in 1 px increments keeps each move below the acceleration threshold, so
        out and back cancel cleanly.
        """
        step = 1 if px >= 0 else -1
        for _ in range(abs(px)):
            self._backend.move(step, 0)
            time.sleep(0.002)
        time.sleep(0.03)
        for _ in range(abs(px)):
            self._backend.move(-step, 0)
            time.sleep(0.002)

    def _sleep_interruptible(self, seconds: float) -> bool:
        """Sleep up to `seconds`, waking early if stop is requested.

        Returns True if a stop was requested during the sleep.
        """
        if seconds <= 0:
            return self._stop_event.is_set()
        # Event.wait returns True as soon as the event is set.
        return self._stop_event.wait(seconds)
