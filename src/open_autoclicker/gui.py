"""PySide6 GUI for Open Auto Clicker.

The engine and hotkey callbacks fire on background threads, so everything that
touches widgets is marshalled onto the Qt thread via signals.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QSettings, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import APP_ID, APP_NAME, __version__
from .clicker import ClickConfig, ClickType, ClickerEngine, MouseButton
from .hotkey import DEFAULT_HOTKEY, HotkeyManager, normalize_hotkey
from .icons import app_icon


class _EngineBridge(QObject):
    """Re-emits thread-unsafe engine callbacks as Qt signals."""

    started = Signal()
    stopped = Signal(int)
    tick = Signal(int)
    error = Signal(str)
    hotkey_pressed = Signal()


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")

        # Keep only the minimize and close buttons; drop the maximize button so
        # the fixed-size window can't be maximized. MSWindowsFixedSizeDialogHint
        # tells the window manager (incl. GNOME/Wayland) the window is a fixed
        # size, which suppresses the maximize affordance that would otherwise be
        # drawn regardless of the button hints.
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
            | Qt.MSWindowsFixedSizeDialogHint
        )

        # Title-bar / taskbar icon.
        icon = app_icon()
        self._app_icon = icon
        if not icon.isNull():
            self.setWindowIcon(icon)

        self._settings = QSettings(APP_ID, APP_ID)
        self._engine = ClickerEngine()
        self._hotkeys = HotkeyManager()
        self._bridge = _EngineBridge()
        self._tray = None
        self._force_quit = False

        self._build_ui()
        self._wire_signals()
        self._setup_tray(icon)
        self._register_hotkey(DEFAULT_HOTKEY, announce=False)
        self._update_button_states(running=False)

        # Restore the "close to tray" preference.
        minimize = self._settings.value("minimize_to_tray", True, type=bool)
        self.minimize_to_tray_check.setChecked(minimize)

        # Restore the last-used interval (seconds), falling back to the default.
        saved_interval = self._settings.value(
            "interval_s", self.interval_spin.value(), type=int
        )
        self.interval_spin.setValue(saved_interval)
        self.interval_spin.valueChanged.connect(
            lambda v: self._settings.setValue("interval_s", v)
        )

        # Restore the click / cursor-movement mode and distance, then persist
        # any changes so the chosen mode (click, move, or both) is remembered.
        self.click_enabled_check.setChecked(
            self._settings.value("do_click", True, type=bool)
        )
        self.jiggle_check.setChecked(
            self._settings.value("jiggle", False, type=bool)
        )
        self.jiggle_px_spin.setValue(
            self._settings.value("jiggle_px", self.jiggle_px_spin.value(), type=int)
        )
        self.click_enabled_check.toggled.connect(
            lambda v: self._settings.setValue("do_click", v)
        )
        self.jiggle_check.toggled.connect(
            lambda v: self._settings.setValue("jiggle", v)
        )
        self.jiggle_px_spin.valueChanged.connect(
            lambda v: self._settings.setValue("jiggle_px", v)
        )

        # Lock the window to its natural size: no resizing, no maximizing.
        self.setFixedSize(self.sizeHint())

    # ---- UI construction -------------------------------------------------------
    def _make_ms_row(self, form, label, default, maximum, minimum=0):
        """Add a form row with a millisecond spinbox plus a live, grey
        human-readable duration label next to it. Returns (spinbox, label)."""
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(default)
        spin.setSuffix(" ms")

        human = QLabel()
        human.setStyleSheet("color: gray;")

        row = QHBoxLayout()
        row.addWidget(spin)
        row.addWidget(human)
        row.addStretch(1)
        form.addRow(label, row)
        return spin, human

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Click interval
        interval_box = QGroupBox("Click interval")
        interval_form = QFormLayout(interval_box)

        # Interval is entered in whole seconds (minimum 1 s). Jitter and start
        # delay stay in milliseconds for finer control.
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 86_400)  # 1 s .. 24 h
        self.interval_spin.setValue(240)  # default: 4 minutes
        self.interval_spin.setSuffix(" s")
        self.interval_human = QLabel()
        self.interval_human.setStyleSheet("color: gray;")
        interval_row = QHBoxLayout()
        interval_row.addWidget(self.interval_spin)
        interval_row.addWidget(self.interval_human)
        interval_row.addStretch(1)
        interval_form.addRow("Interval:", interval_row)

        self.jitter_spin, self.jitter_human = self._make_ms_row(
            interval_form, "Random extra delay:", default=0, maximum=3_600_000
        )
        self.predelay_spin, self.predelay_human = self._make_ms_row(
            interval_form, "Start delay:", default=0, maximum=3_600_000
        )
        root.addWidget(interval_box)

        # Click options
        options_box = QGroupBox("Click options")
        options_form = QFormLayout(options_box)
        self.click_enabled_check = QCheckBox("Click the mouse")
        self.click_enabled_check.setChecked(True)
        options_form.addRow(self.click_enabled_check)
        self.button_combo = QComboBox()
        self.button_combo.addItem("Left", MouseButton.LEFT)
        self.button_combo.addItem("Middle", MouseButton.MIDDLE)
        self.button_combo.addItem("Right", MouseButton.RIGHT)
        options_form.addRow("Mouse button:", self.button_combo)

        self.click_combo = QComboBox()
        self.click_combo.addItem("Single", ClickType.SINGLE)
        self.click_combo.addItem("Double", ClickType.DOUBLE)
        options_form.addRow("Click type:", self.click_combo)
        root.addWidget(options_box)

        # Cursor movement (anti-sleep jiggle), runs on the same interval.
        move_box = QGroupBox("Cursor movement")
        move_form = QFormLayout(move_box)
        self.jiggle_check = QCheckBox("Move the cursor (keeps the system awake)")
        move_form.addRow(self.jiggle_check)
        self.jiggle_px_spin = QSpinBox()
        self.jiggle_px_spin.setRange(1, 500)
        self.jiggle_px_spin.setValue(10)
        self.jiggle_px_spin.setSuffix(" px")
        move_form.addRow("Move distance:", self.jiggle_px_spin)
        root.addWidget(move_box)

        # Repeat
        repeat_box = QGroupBox("Repeat")
        repeat_layout = QVBoxLayout(repeat_box)
        self.repeat_infinite = QRadioButton("Repeat until stopped")
        self.repeat_infinite.setChecked(True)
        self.repeat_count_radio = QRadioButton("Repeat a fixed number of times")
        count_row = QHBoxLayout()
        self.repeat_count_spin = QSpinBox()
        self.repeat_count_spin.setRange(1, 10_000_000)
        self.repeat_count_spin.setValue(10)
        self.repeat_count_spin.setEnabled(False)
        count_row.addWidget(self.repeat_count_radio)
        count_row.addWidget(self.repeat_count_spin)
        count_row.addStretch(1)
        repeat_layout.addWidget(self.repeat_infinite)
        repeat_layout.addLayout(count_row)
        root.addWidget(repeat_box)

        # Hotkey
        hotkey_box = QGroupBox("Global hotkey (start / stop)")
        hotkey_form = QFormLayout(hotkey_box)
        hotkey_row = QHBoxLayout()
        self.hotkey_edit = QLineEdit(DEFAULT_HOTKEY)
        self.hotkey_apply = QPushButton("Apply")
        hotkey_row.addWidget(self.hotkey_edit)
        hotkey_row.addWidget(self.hotkey_apply)
        hotkey_form.addRow("Shortcut:", hotkey_row)
        hint = QLabel('e.g. "F6", "Ctrl+Shift+K"')
        hint.setStyleSheet("color: gray; font-size: 11px;")
        hotkey_form.addRow("", hint)
        root.addWidget(hotkey_box)

        # Window behaviour
        window_box = QGroupBox("Window")
        window_layout = QVBoxLayout(window_box)
        self.minimize_to_tray_check = QCheckBox(
            "Close button minimizes to the system tray"
        )
        window_layout.addWidget(self.minimize_to_tray_check)
        root.addWidget(window_box)

        # Start / Stop buttons
        buttons_row = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        buttons_row.addWidget(self.start_button)
        buttons_row.addWidget(self.stop_button)
        root.addLayout(buttons_row)

        # Status
        self.status_label = QLabel("Idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status_label)

    # ---- signal wiring ---------------------------------------------------------
    def _wire_signals(self) -> None:
        self.repeat_count_radio.toggled.connect(self.repeat_count_spin.setEnabled)

        self.start_button.clicked.connect(self.on_start_clicked)
        self.stop_button.clicked.connect(self.on_stop_clicked)
        self.hotkey_apply.clicked.connect(self.on_apply_hotkey)
        self.minimize_to_tray_check.toggled.connect(self._on_minimize_pref_changed)

        # Interval is in seconds: convert to ms for the human-readable label.
        self.interval_spin.valueChanged.connect(
            lambda s: self.interval_human.setText(
                self._format_duration(round(s * 1000))
            )
        )
        self.interval_human.setText(
            self._format_duration(round(self.interval_spin.value() * 1000))
        )

        # Jitter and start delay stay in milliseconds.
        for spin, human in (
            (self.jitter_spin, self.jitter_human),
            (self.predelay_spin, self.predelay_human),
        ):
            spin.valueChanged.connect(
                lambda ms, lbl=human: lbl.setText(self._format_duration(ms))
            )
            human.setText(self._format_duration(spin.value()))

        # Engine callbacks -> Qt signals (thread-safe hop onto the UI thread).
        self._engine.set_callbacks(
            on_started=self._bridge.started.emit,
            on_stopped=self._bridge.stopped.emit,
            on_tick=self._bridge.tick.emit,
            on_error=lambda exc: self._bridge.error.emit(str(exc)),
        )
        self._bridge.started.connect(self.on_engine_started)
        self._bridge.stopped.connect(self.on_engine_stopped)
        self._bridge.tick.connect(self.on_engine_tick)
        self._bridge.error.connect(self.on_engine_error)
        self._bridge.hotkey_pressed.connect(self.on_hotkey_toggle)

    # ---- interval helper -------------------------------------------------------
    @staticmethod
    def _format_duration(ms: int) -> str:
        """Return a short human-readable form of a millisecond duration."""
        if ms <= 0:
            return "0 s (as fast as possible)"
        if ms < 1000:
            return f"{ms} ms"

        hours, rem = divmod(ms, 3_600_000)
        minutes, rem = divmod(rem, 60_000)
        seconds = rem / 1000.0

        parts = []
        if hours:
            parts.append(f"{hours} h")
        if minutes:
            parts.append(f"{minutes} min")
        if seconds:
            # Drop a trailing ".0" for whole seconds.
            s = f"{seconds:.1f}".rstrip("0").rstrip(".")
            parts.append(f"{s} s")
        return " ".join(parts)

    # ---- config ----------------------------------------------------------------
    def _build_config(self) -> ClickConfig:
        repeat = None if self.repeat_infinite.isChecked() else self.repeat_count_spin.value()
        return ClickConfig(
            interval_ms=round(self.interval_spin.value() * 1000),  # seconds -> ms
            button=self.button_combo.currentData(),
            click_type=self.click_combo.currentData(),
            repeat_count=repeat,
            random_jitter_ms=self.jitter_spin.value(),
            start_delay_ms=self.predelay_spin.value(),
            do_click=self.click_enabled_check.isChecked(),
            jiggle=self.jiggle_check.isChecked(),
            jiggle_px=self.jiggle_px_spin.value(),
        )

    def _set_config_enabled(self, enabled: bool) -> None:
        for widget in (
            self.interval_spin,
            self.jitter_spin,
            self.predelay_spin,
            self.button_combo,
            self.click_combo,
            self.click_enabled_check,
            self.jiggle_check,
            self.jiggle_px_spin,
            self.repeat_infinite,
            self.repeat_count_radio,
            self.hotkey_edit,
            self.hotkey_apply,
        ):
            widget.setEnabled(enabled)
        # The count spinbox follows its radio only when config is editable.
        self.repeat_count_spin.setEnabled(enabled and self.repeat_count_radio.isChecked())

    def _update_button_states(self, running: bool) -> None:
        # Start is clickable only when stopped; Stop only when running.
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    # ---- button handlers -------------------------------------------------------
    @Slot()
    def on_start_clicked(self) -> None:
        if self._engine.is_running:
            return
        try:
            config = self._build_config()
            config.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return
        self._engine.start(config)

    @Slot()
    def on_stop_clicked(self) -> None:
        self._engine.stop()

    @Slot()
    def on_hotkey_toggle(self) -> None:
        # Mirror the two-button behaviour: toggle based on current state.
        if self._engine.is_running:
            self.on_stop_clicked()
        else:
            self.on_start_clicked()

    @Slot()
    def on_apply_hotkey(self) -> None:
        self._register_hotkey(self.hotkey_edit.text(), announce=True)

    def _register_hotkey(self, text: str, announce: bool) -> None:
        try:
            normalized = normalize_hotkey(text)
            self._hotkeys.register(normalized, self._bridge.hotkey_pressed.emit)
            self.hotkey_edit.setText(normalized)
            if announce:
                self.status_label.setText(f"Hotkey set to {normalized}")
        except (ValueError, Exception) as exc:  # pynput can raise generic errors
            QMessageBox.warning(self, "Invalid hotkey", f"Could not set hotkey: {exc}")

    # ---- engine signal handlers ------------------------------------------------
    def _action_word(self) -> str:
        """Describe the running action based on the enabled modes."""
        click = self.click_enabled_check.isChecked()
        move = self.jiggle_check.isChecked()
        if click and move:
            return "Clicking + moving"
        if move:
            return "Moving cursor"
        return "Clicking"

    @Slot()
    def on_engine_started(self) -> None:
        self._set_config_enabled(False)
        self._update_button_states(running=True)
        self._action_label = self._action_word()
        self.status_label.setText(f"{self._action_label}...")

    @Slot(int)
    def on_engine_stopped(self, total: int) -> None:
        self._set_config_enabled(True)
        self._update_button_states(running=False)
        self.status_label.setText(f"Stopped after {total} actions")

    @Slot(int)
    def on_engine_tick(self, count: int) -> None:
        label = getattr(self, "_action_label", "Running")
        self.status_label.setText(f"{label}... ({count})")

    @Slot(str)
    def on_engine_error(self, message: str) -> None:
        self._update_button_states(running=False)
        self._set_config_enabled(True)
        QMessageBox.critical(self, "Error", message)

    # ---- system tray -----------------------------------------------------------
    def _setup_tray(self, icon) -> None:
        """Create the system tray icon and its menu, if a tray is available."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._tray = QSystemTrayIcon(self)
        if not icon.isNull():
            self._tray.setIcon(icon)
        self._tray.setToolTip(APP_NAME)

        menu = QMenu()
        # "Show / Hide" is the default action. On desktops where a single click
        # opens the menu (e.g. GNOME/Wayland AppIndicator) it is the highlighted
        # entry, so showing/hiding the window takes minimal effort. Direct
        # tray click/double-click is intentionally not used: restoring from the
        # activation signal hangs under GNOME/Wayland AppIndicator.
        toggle_action = menu.addAction("Show / Hide")
        toggle_action.triggered.connect(self._toggle_window)
        menu.setDefaultAction(toggle_action)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_app)
        self._tray.setContextMenu(menu)

        self._tray.show()

    @Slot()
    def _on_minimize_pref_changed(self, checked: bool) -> None:
        self._settings.setValue("minimize_to_tray", checked)

    def _restore_window(self) -> None:
        """Bring the window back from the tray.

        Uses showNormal() to clear any minimized state and recreate the
        surface, then best-effort raise/activate (Wayland may ignore the
        latter, but they are harmless).
        """
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _toggle_window(self) -> None:
        """Hide the window if it is visible, otherwise restore it."""
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self._restore_window()

    @Slot()
    def quit_app(self) -> None:
        """Really exit the application (bypasses minimize-to-tray)."""
        self._shutdown()
        # Close via Qt's normal shutdown. The hotkey listener is a daemon
        # thread, so nothing keeps the process alive once the loop ends.
        QApplication.quit()

    def _shutdown(self) -> None:
        """Release everything cleanly before the process exits."""
        self._force_quit = True
        try:
            self._engine.close()
        except Exception:
            pass
        try:
            self._hotkeys.stop()
        except Exception:
            pass
        if self._tray is not None:
            self._tray.hide()

    # ---- lifecycle -------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        # If the user asked for close-to-tray and a tray is available, hide
        # instead of quitting (unless this is a real quit via the tray menu).
        if (
            not self._force_quit
            and self.minimize_to_tray_check.isChecked()
            and self._tray is not None
        ):
            event.ignore()
            self.hide()
            if not self._settings.value("tray_hint_shown", False, type=bool):
                self._tray.showMessage(
                    APP_NAME,
                    "Still running in the tray. Click the icon to restore.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
                self._settings.setValue("tray_hint_shown", True)
            return

        # Real shutdown: release everything and let Qt close normally. The
        # hotkey listener is a daemon thread, so the process ends on its own.
        self._shutdown()
        super().closeEvent(event)
