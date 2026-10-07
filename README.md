<div align="center">
  <img src="packaging/icons/icon_256.png" width="96" height="96" alt="Open Auto Clicker icon">
  <h1>Open Auto Clicker</h1>
</div>

A simple, cross-platform mouse auto clicker with a GUI. It automates mouse
clicks at a configurable interval and runs on **Linux**, **Windows** and
**macOS**.

Built with Python, [PySide6](https://doc.qt.io/qtforpython/) (Qt) and
[pynput](https://pynput.readthedocs.io/).

## Features

- Left / middle / right mouse button
- Single or double click
- Click interval entered in **seconds** (minimum 1 s), with a live breakdown
  into seconds / minutes / hours next to the field (default: 4 minutes). The
  1 s floor guarantees you can always regain control of the pointer to stop.
- Random extra delay (jitter) and a one-off start delay, both in milliseconds
- Fixed number of repeats or "repeat until stopped"
- Global start/stop hotkey (default **F6**), works even when the window is not
  focused
- Separate **Start** and **Stop** buttons: Start is greyed-out while clicking,
  Stop is greyed-out while idle
- Optional **close-to-tray**: closing the window keeps the app running in the
  system tray; restore it from the tray menu. The preference is remembered.
- Fixed-size window; app icon in the dock / taskbar

## Usage

1. **Launch** the app (from your menu after installing, or `open-autoclicker`
   from a terminal).
2. **Set the interval** under *Click interval* — the value is in seconds, and
   the grey label next to it shows the equivalent in minutes/hours. Minimum is
   1 second.
3. **Pick the button and click type** under *Click options* (left/middle/right,
   single or double).
4. *(Optional)* Add a **random extra delay** for a less robotic rhythm, or a
   **start delay** to give yourself time to position the pointer before the
   first click.
5. **Choose how long to run** under *Repeat*: either "repeat until stopped" or
   a fixed number of clicks.
6. **Position the mouse** where you want the clicks to land.
7. Press **Start** (or your hotkey). The app clicks at the chosen interval.
8. Press **Stop**, or the hotkey again, to end. Because the interval is at
   least 1 second, you always have time to move the pointer back and stop.

### Global hotkey

The default start/stop hotkey is **F6** and works even when the window is not
focused. Change it in the *Global hotkey* box (e.g. `F6`, `Ctrl+Shift+K`) and
click **Apply**.

> On a pure **Wayland** session the global hotkey may not fire — this is a
> Wayland restriction, not a bug. Clicking from the Start button still works.

### Running in the background (tray)

With *Close button minimizes to the system tray* enabled (on by default),
closing the window keeps the app running in the tray instead of quitting.
Right-click (or click) the tray icon and choose **Show / Hide** to bring the
window back, or **Quit** to exit for real.

## Project layout

```
open-autoclicker/
├── pyproject.toml                 # package metadata + dependencies
├── src/open_autoclicker/
│   ├── __init__.py                # app name / version
│   ├── __main__.py                # module entry (python -m open_autoclicker)
│   ├── app.py                     # app bootstrap + entry point
│   ├── clicker.py                 # threaded click engine (no Qt dependency)
│   ├── hotkey.py                  # global hotkey manager
│   ├── gui.py                     # PySide6 window
│   └── resources/                 # bundled app icon
└── packaging/
    ├── open-autoclicker.spec      # PyInstaller build spec (all 3 OSes)
    ├── open-autoclicker.desktop   # Linux desktop entry
    ├── icon.svg / icon.ico / icon.icns   # app icons per platform
    └── build-deb.sh               # builds a .deb from the PyInstaller bundle
```

## Run from source

Requires Python 3.9+.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
open-autoclicker                   # or: python -m open_autoclicker
```

### Permissions note

Controlling the mouse and listening for a global hotkey needs OS-level input
access:

- **macOS**: on first run, grant the app (or your terminal) permission under
  *System Settings → Privacy & Security → Accessibility*.
- **Linux/Wayland**: global input works best under X11. On a pure Wayland
  session the global hotkey may not fire; clicking still works.
- **Windows**: no special setup; some antivirus tools flag input-automation
  tools, so you may need to allow it.

---

## Building installable packages

All three platforms use **PyInstaller** to bundle Python + Qt into a
self-contained app, so end users don't need Python installed. Build on the
target OS (PyInstaller does not cross-compile).

First install the build extra:

```bash
pip install -e ".[build]"
```

### Linux (.deb)

```bash
pyinstaller packaging/open-autoclicker.spec   # -> dist/open-autoclicker/
bash packaging/build-deb.sh                   # -> dist/open-autoclicker_<version>_amd64.deb
```

Install and test (version comes from `pyproject.toml`):

```bash
sudo apt install ./dist/open-autoclicker_*_amd64.deb
open-autoclicker
```

The `.deb` bundles its own Qt/Python runtime and depends only on a few base X
libraries (`libc6`, `libx11-6`, `libxext6`, `libxrender1`, `libgl1`). It does
**not** depend on `libgdk-pixbuf2.0-0`, the package whose rename broke older
GTK-based builds on newer Ubuntu/Debian.

> Prefer AppImage or Flatpak for wider distro coverage? The PyInstaller bundle
> in `dist/open-autoclicker/` is a ready input for either; the `.deb` is the
> default here because that's what the original request targeted.

### Windows (.exe)

Run in a *Windows* Python environment (PowerShell or cmd):

```powershell
pip install -e ".[build]"
pyinstaller packaging\open-autoclicker.spec
```

This produces `dist\open-autoclicker\open-autoclicker.exe` plus its runtime
files. Distribute that folder as a ZIP, or wrap it in an installer:

- **Inno Setup** (recommended): point its `[Files]` section at
  `dist\open-autoclicker\*` and set the `open-autoclicker.exe` as the launched
  binary to produce a single `setup.exe`.
- **NSIS**: same idea with a `.nsi` script.

### macOS (.app / .dmg)

Run on a *Mac*:

```bash
pip install -e ".[build]"
pyinstaller packaging/open-autoclicker.spec    # -> "dist/Open Auto Clicker.app"
```

Wrap the `.app` in a `.dmg` for distribution:

```bash
hdiutil create -volname "Open Auto Clicker" \
  -srcfolder "dist/Open Auto Clicker.app" \
  -ov -format UDZO "dist/OpenAutoClicker.dmg"
```

For distribution outside your own machine you'll also want to **codesign** and
**notarize** the app (`codesign --deep --sign ...` then `xcrun notarytool
submit`), otherwise Gatekeeper will warn users. For personal use the unsigned
`.app`/`.dmg` is fine (right-click → Open on first launch).

---

## Cutting a release

1. Bump the version in `pyproject.toml` (`version = "x.y.z"`) and in
   `src/open_autoclicker/__init__.py` (`__version__`).
2. Commit and tag: `git tag vX.Y.Z && git push --tags`.
3. Build the artifact on each OS as above:
   - Linux: `open-autoclicker_X.Y.Z_amd64.deb`
   - Windows: `setup.exe` (or a zipped `dist\open-autoclicker\` folder)
   - macOS: `OpenAutoClicker-X.Y.Z.dmg`
4. Create a GitHub Release for the tag and upload all three artifacts.

Because PyInstaller can't cross-compile, each artifact must be built on its own
OS. This repo ships GitHub Actions workflows that do exactly that:

- **`.github/workflows/build.yml`** — on every push to `master` (and on PRs),
  builds the `.deb`, Windows `.zip` and `.dmg` on a Linux/Windows/macOS matrix
  and uploads them as run artifacts. This is the "build after merge to master"
  pipeline.
- **`.github/workflows/release.yml`** — on pushing a tag `vX.Y.Z`, builds the
  same three artifacts and publishes them to a GitHub Release automatically.

> The workflows target the `master` branch. If your default branch is `main`,
> change the `branches:` key in `build.yml` accordingly.

## Notes

This application was built with the help of AI.

## License

MIT — see [LICENSE](LICENSE).