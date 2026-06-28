#!/usr/bin/env bash
#
# Install OBD Toolkit on Raspberry Pi OS / Debian / Ubuntu (incl. 64-bit ARM).
#
# It uses the SYSTEM PySide6/Qt (from apt) — which is the reliable path on ARM,
# where prebuilt PySide6 wheels are not always available — and pip-installs the
# rest into a venv that can see those system packages.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/JWalen/OBD-Toolkit/master/scripts/install-pi.sh | bash
#   # or: bash scripts/install-pi.sh
#
set -euo pipefail

REPO="https://github.com/JWalen/OBD-Toolkit"
VENV="$HOME/.local/share/obd-toolkit/venv"
BINDIR="$HOME/.local/bin"
APPDIR="$HOME/.local/share/applications"

echo "==> Installing system Qt / PySide6 and serial support (apt)…"
sudo apt-get update
sudo apt-get install -y \
  python3-full python3-venv python3-pip git \
  python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pyside6.qtsvg \
  python3-numpy python3-serial \
  || {
    echo "!! apt install failed. On older distros the package names differ;"
    echo "   see ${REPO}#linux--raspberry-pi for manual steps."
    exit 1
  }

echo "==> Creating venv (with access to system PySide6)…"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade pip

echo "==> Installing OBD Toolkit (live-OBD + plotting; PySide6 comes from the system)…"
# Note: NOT the [gui] extra — that would pull PySide6 from pip. We add pyqtgraph
# and certifi explicitly and rely on the apt-installed PySide6.
"$VENV/bin/pip" install "vcds-toolkit[obd] @ git+${REPO}.git" pyqtgraph certifi

echo "==> Adding a launcher…"
mkdir -p "$BINDIR" "$APPDIR"
ln -sf "$VENV/bin/obd-toolkit" "$BINDIR/obd-toolkit"
cat > "$APPDIR/obd-toolkit.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OBD Toolkit
Comment=Analyze VCDS logs and capture live OBD-II data
Exec=$VENV/bin/obd-toolkit
Icon=utilities-terminal
Categories=Utility;Development;
Terminal=false
EOF

echo "==> Granting serial-port access (dialout group) for ELM327 adapters…"
sudo usermod -aG dialout "$USER" || true

cat <<EOF

✅ Done.

Launch it with:   obd-toolkit
  (make sure $BINDIR is on your PATH, or run: $VENV/bin/obd-toolkit)

A few notes:
  • Log out/in once so the new 'dialout' group takes effect (needed to read
    /dev/ttyUSB0 etc. for a USB ELM327).
  • Update later with:  $VENV/bin/pip install --upgrade "vcds-toolkit @ git+${REPO}.git"
EOF
