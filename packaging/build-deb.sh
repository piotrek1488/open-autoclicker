#!/usr/bin/env bash
# Build a .deb package from the PyInstaller one-folder bundle.
#
# Usage:
#   pyinstaller packaging/open-autoclicker.spec     # produces dist/open-autoclicker/
#   bash packaging/build-deb.sh                      # produces dist/open-autoclicker_<ver>_amd64.deb
#
# The resulting package bundles its own Python + Qt runtime, so it only depends
# on a handful of base X/graphics libraries that ship with every modern
# Debian/Ubuntu. It intentionally does NOT depend on the renamed
# libgdk-pixbuf2.0-0 package that broke older builds.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml" | head -1)"
ARCH="amd64"
PKG="open-autoclicker"
BUNDLE="$ROOT/dist/open-autoclicker"
PKGROOT="$ROOT/dist/pkgroot"

if [[ ! -d "$BUNDLE" ]]; then
  echo "error: $BUNDLE not found. Run 'pyinstaller packaging/open-autoclicker.spec' first." >&2
  exit 1
fi

echo "Packaging $PKG $VERSION ($ARCH)"
rm -rf "$PKGROOT"

# Layout: bundle under /opt, launcher symlink in /usr/bin, desktop entry + icon.
install -d "$PKGROOT/opt/$PKG"
cp -r "$BUNDLE/." "$PKGROOT/opt/$PKG/"

install -d "$PKGROOT/usr/bin"
ln -sf "/opt/$PKG/$PKG" "$PKGROOT/usr/bin/$PKG"

install -d "$PKGROOT/usr/share/applications"
cp "$HERE/open-autoclicker.desktop" "$PKGROOT/usr/share/applications/"

# Control metadata. Dependencies are deliberately minimal because the Qt/Python
# runtime is bundled; these are just the low-level X libs PyInstaller needs.
install -d "$PKGROOT/DEBIAN"
INSTALLED_KB="$(du -sk "$PKGROOT" | cut -f1)"
cat > "$PKGROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Open Auto Clicker contributors <noreply@example.com>
Installed-Size: $INSTALLED_KB
Depends: libc6, libx11-6, libxext6, libxrender1, libgl1
Description: Cross-platform mouse auto clicker
 Open Auto Clicker simulates and automates mouse clicks with a configurable
 interval, button, click type, repeat count, random delay and a global hotkey.
 The Qt and Python runtime are bundled, so no system Python is required.
EOF

OUT="$ROOT/dist/${PKG}_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$PKGROOT" "$OUT"
echo "Built $OUT"
