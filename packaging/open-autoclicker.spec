# PyInstaller spec file for Open Auto Clicker.
# Build with:  pyinstaller packaging/open-autoclicker.spec
#
# Produces a one-folder bundle under dist/open-autoclicker (and, on macOS,
# a dist/Open Auto Clicker.app bundle).

import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# pynput loads its platform backend dynamically at runtime (importlib), so
# PyInstaller's static analysis misses it. collect_submodules only grabs the
# current platform's backend, so we also list every backend explicitly. The
# imports for other platforms simply won't be used at runtime.
hidden = collect_submodules("pynput") + [
    # Linux (X11)
    "pynput.keyboard._xorg",
    "pynput.mouse._xorg",
    "pynput._util.xorg",
    "pynput._util.xorg_keysyms",
    # Windows
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "pynput._util.win32",
    # macOS
    "pynput.keyboard._darwin",
    "pynput.mouse._darwin",
    "pynput._util.darwin",
]

# Linux-only: evdev powers the Wayland cursor backend (imported lazily).
if sys.platform.startswith("linux"):
    hidden += collect_submodules("evdev")

# Per-platform icon file for the executable/bundle.
if sys.platform == "win32":
    exe_icon = "icon.ico"
elif sys.platform == "darwin":
    exe_icon = "icon.icns"
else:
    exe_icon = None  # Linux icon comes from the .desktop entry + hicolor theme

a = Analysis(
    ["../src/open_autoclicker/app.py"],
    pathex=["../src"],
    binaries=[],
    # Ship the PNG so the Qt window icon works at runtime on every platform.
    datas=[("../src/open_autoclicker/resources/icon.png", "open_autoclicker/resources")],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="open-autoclicker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app: no console window on Windows
    icon=exe_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="open-autoclicker",
)

# macOS .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Open Auto Clicker.app",
        icon="icon.icns",
        bundle_identifier="io.github.open_autoclicker",
        info_plist={
            "NSHighResolutionCapable": True,
            # macOS requires asking for Accessibility permission for input control.
            "NSAppleEventsUsageDescription": "Open Auto Clicker needs control of the mouse to perform clicks.",
        },
    )
