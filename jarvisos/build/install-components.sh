#!/bin/bash
# Install JARVISOS components into a filesystem-overlay directory.
# Usage: install-components.sh <overlay-dir>   (single source of truth:
# component sources live in jarvisos/*/, never duplicated in filesystem/).
# Also usable on a live/dev system with overlay=/ for iterative hacking
# (safe: only writes /usr/lib/jarvisos, /usr/bin/jarvis-*, /etc/jarvisos…).
set -euo pipefail

OVERLAY="${1:-}"
[ -n "$OVERLAY" ] || { echo "usage: install-components.sh <overlay-dir>" >&2; exit 2; }
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LIB="$OVERLAY/usr/lib/jarvisos"
BIN="$OVERLAY/usr/bin"
mkdir -p "$LIB"/{jarvis,shell,apps,helpers} "$BIN" "$OVERLAY/etc/jarvisos" \
  "$OVERLAY/usr/share/themes"

# --- python library ------------------------------------------------------
cp -a "$SRC_DIR/jarvis-core/jarvis/." "$LIB/jarvis/"
find "$LIB/jarvis" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

# --- shell + apps sources --------------------------------------------------
cp -a "$SRC_DIR/shell/"*.py "$LIB/shell/"
cp -a "$SRC_DIR/apps/"*_app.py "$LIB/apps/"

# --- launchers → /usr/bin ----------------------------------------------------
cp -a "$SRC_DIR/shell/bin/"* "$BIN/" 2>/dev/null || true
cp -a "$SRC_DIR/apps/bin/"* "$BIN/" 2>/dev/null || true
cp -a "$SRC_DIR/jarvis-core/bin/"* "$BIN/" 2>/dev/null || true
cp -a "$SRC_DIR/automation/bin/"* "$BIN/" 2>/dev/null || true
cp -a "$SRC_DIR/voice/bin/"* "$BIN/" 2>/dev/null || true
cp -a "$SRC_DIR/gestures/bin/"* "$BIN/" 2>/dev/null || true
cp -a "$SRC_DIR/scripts/helpers/"* "$BIN/" 2>/dev/null || true
cp -a "$SRC_DIR/jarvis-core/jarvisd.py" "$BIN/jarvis-core"
cp -a "$SRC_DIR/scripts/installer/jarvis-install" "$BIN/jarvis-install"
chmod +x "$BIN"/jarvis* 2>/dev/null || true

# --- defaults + themes ---------------------------------------------------------
cp -a "$SRC_DIR/settings/defaults.json" "$OVERLAY/etc/jarvisos/defaults.json"
cp -a "$SRC_DIR/themes/Jarvis-Dark" "$OVERLAY/usr/share/themes/Jarvis-Dark"

# --- boot banner on live login (serial/QEMU marker + friendly MOTD hook) -------
mkdir -p "$OVERLAY/etc/profile.d"
cat > "$OVERLAY/etc/profile.d/jarvis-banner.sh" <<'EOF'
# JARVISOS login banner (also the QEMU boot-test success marker path)
if [ -z "${JARVIS_BANNER_SHOWN:-}" ]; then
  export JARVIS_BANNER_SHOWN=1
  if command -v systemctl >/dev/null 2>&1; then
    echo "JARVIS CORE ...... READY"
  fi
fi
EOF

echo "[jarvis-install] components installed into $OVERLAY"
find "$LIB" "$OVERLAY/etc/jarvisos" -type f | sort
