"""PySide6 GUI for Open Auto Clicker.

The engine and hotkey callbacks fire on background threads, so everything that
touches widgets is marshalled onto the Qt thread via signals.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, __version__
from .clicker import ClickConfig, ClickType, ClickerEngine, MouseButton
from .hotkey import DEFAULT_HOTKEY, HotkeyManager, normalize_hotkey


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
        self.setMinimumWidth(380)

        self._engine = ClickerEngine()
        self._hotkeys = HotkeyManager()
        self._bridge = _EngineBridge()

        self._build_ui()
        self._wire_signals()
        self._register_hotkey(DEFAULT_HOTKEY, announce=False)
        self._update_button_states(running=False)

    # ---- UI construction -------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Click interval
        interval_box = QGroupBox("Click interval")
        interval_form = QFormLayout(interval_box)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(0, 3_600_000)
        self.interval_spin.setValue(100)
        self.interval_spin.setSuffix(" ms")
        interval_form.addRow("Interval:", self.interval_spin)

        self.jitter_spin = QSpinBox()
        self.jitter_spin.setRange(0, 3_600_000)
        self.jitter_spin.setValue(0)
        self.jitter_spin.setSuffix(" ms")
        interval_form.addRow("Random extra delay:", self.jitter_spin)

        self.predelay_spin = QSpinBox()
        self.predelay_spin.setRange(0, 3_600_000)
        self.predelay_spin.setValue(0)
        self.predelay_spin.setSuffix(" ms")
        interval_form.addRow("Start delay:", self.predelay_spin)
        root.addWidget(interval_box)

        # Click options
        options_box = QGroupBox("Click options")
        options_form = QFormLayout(options_box)
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

    # ---- config ----------------------------------------------------------------
    def _build_config(self) -> ClickConfig:
        repeat = None if self.repeat_infinite.isChecked() else self.repeat_count_spin.value()
        return ClickConfig(
            interval_ms=self.interval_spin.value(),
            button=self.button_combo.currentData(),
            click_type=self.click_combo.currentData(),
            repeat_count=repeat,
            random_jitter_ms=self.jitter_spin.value(),
            start_delay_ms=self.predelay_spin.value(),
        )

    def _set_config_enabled(self, enabled: bool) -> None:
        for widget in (
            self.interval_spin,
            self.jitter_spin,
            self.predelay_spin,
            self.button_combo,
            self.click_combo,
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
    @Slot()
    def on_engine_started(self) -> None:
        self._set_config_enabled(False)
        self._update_button_states(running=True)
        self.status_label.setText("Clicking...")

    @Slot(int)
    def on_engine_stopped(self, total: int) -> None:
        self._set_config_enabled(True)
        self._update_button_states(running=False)
        self.status_label.setText(f"Stopped after {total} clicks")

    @Slot(int)
    def on_engine_tick(self, count: int) -> None:
        self.status_label.setText(f"Clicking... ({count})")

    @Slot(str)
    def on_engine_error(self, message: str) -> None:
        self._update_button_states(running=False)
        self._set_config_enabled(True)
        QMessageBox.critical(self, "Error", message)

    # ---- lifecycle -------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._engine.stop(join=True)
        self._hotkeys.stop()
        super().closeEvent(event)
