# PyInstaller spec file for Open Auto Clicker.
# Build with:  pyinstaller packaging/open-autoclicker.spec
#
# Produces a one-folder bundle under dist/open-autoclicker (and, on macOS,
# a dist/Open Auto Clicker.app bundle).

import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hidden = collect_submodules("pynput")

a = Analysis(
    ["../src/open_autoclicker/__main__.py"],
    pathex=["../src"],
    binaries=[],
    datas=[],
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
        icon=None,  # add path to an .icns here if you have one
        bundle_identifier="io.github.open_autoclicker",
        info_plist={
            "NSHighResolutionCapable": True,
            # macOS requires asking for Accessibility permission for input control.
            "NSAppleEventsUsageDescription": "Open Auto Clicker needs control of the mouse to perform clicks.",
        },
    )
