#!/bin/bash
# Assemble a live-build config/ directory from the jarvisos/ sources.
# Usage: stage.sh <minimal|full> <dest-lb-dir> <version>
# Single-source-of-truth: packages/, filesystem/, boot/, iso/ + component dirs.
set -euo pipefail

PROFILE="$1"; DEST="$2"; VERSION="$3"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { echo "[jarvis-stage] $*"; }

rm -rf "$DEST"
mkdir -p "$DEST/config" "$DEST/auto"

# --- auto/config (lb config driver) --------------------------------------
sed -e "s/__PROFILE__/$PROFILE/g" -e "s/__VERSION__/$VERSION/g" \
  "$SRC_DIR/build/lb-config.sh" > "$DEST/auto/config"
chmod +x "$DEST/auto/config"

# --- package lists --------------------------------------------------------
mkdir -p "$DEST/config/package-lists"
cp "$SRC_DIR/packages/base.list"    "$DEST/config/package-lists/jarvis-base.list.chroot"
cp "$SRC_DIR/packages/desktop.list" "$DEST/config/package-lists/jarvis-desktop.list.chroot"
cp "$SRC_DIR/packages/jarvis.list"  "$DEST/config/package-lists/jarvis.list.chroot"
if [ "$PROFILE" = "full" ]; then
  cp "$SRC_DIR/packages/full.list"  "$DEST/config/package-lists/jarvis-full.list.chroot"
fi

# --- filesystem overlay → includes.chroot ---------------------------------
mkdir -p "$DEST/config/includes.chroot"
cp -a "$SRC_DIR/filesystem/." "$DEST/config/includes.chroot/"

# --- install components (lib + shell + apps + launchers) into overlay ----
bash "$SRC_DIR/build/install-components.sh" \
  "$DEST/config/includes.chroot"

# --- boot assets ----------------------------------------------------------
# Plymouth theme + grub theme + issue/motd land in the overlay:
mkdir -p "$DEST/config/includes.chroot/usr/share/plymouth/themes/jarvis"
cp -a "$SRC_DIR/boot/plymouth/." "$DEST/config/includes.chroot/usr/share/plymouth/themes/jarvis/"
mkdir -p "$DEST/config/includes.chroot/usr/share/grub/themes/jarvis"
cp -a "$SRC_DIR/boot/grub-theme/." "$DEST/config/includes.chroot/usr/share/grub/themes/jarvis/" 2>/dev/null || true
cp "$SRC_DIR/boot/issue" "$DEST/config/includes.chroot/etc/issue"
cp "$SRC_DIR/boot/motd"  "$DEST/config/includes.chroot/etc/motd"

# --- bootloader (ISO) config ----------------------------------------------
mkdir -p "$DEST/config/bootloaders"
cp "$SRC_DIR/iso/grub.cfg"    "$DEST/config/bootloaders/grub.cfg" 2>/dev/null || true
cp "$SRC_DIR/iso/syslinux.cfg" "$DEST/config/bootloaders/syslinux.cfg" 2>/dev/null || true
if [ -d "$SRC_DIR/iso/splash" ]; then
  mkdir -p "$DEST/config/bootloaders/splash"
  cp -a "$SRC_DIR/iso/splash/." "$DEST/config/bootloaders/splash/"
fi

# --- hooks -----------------------------------------------------------------
mkdir -p "$DEST/config/hooks/live"
cp "$SRC_DIR/build/hooks/live/"*.hook.chroot "$DEST/config/hooks/live/"
cp "$SRC_DIR/build/hooks/live/"*.hook.binary "$DEST/config/hooks/live/" 2>/dev/null || true
chmod +x "$DEST/config/hooks/live/"*.hook.chroot "$DEST/config/hooks/live/"*.hook.binary 2>/dev/null || true

# --- archives (Brave/VSCode repos are added post-install by app-manager,
# --- never baked into the image; keep only Debian here) --------------------
# (live-build default debian archive is enough; see docs/iso-creation.md)

# --- version stamp ----------------------------------------------------------
mkdir -p "$DEST/config/includes.chroot/etc"
echo "JARVISOS $VERSION ($PROFILE)" > "$DEST/config/includes.chroot/etc/jarvisos-release"
cat "$SRC_DIR/VERSION" > "$DEST/config/includes.chroot/etc/jarvisos-version"

log "staged $PROFILE tree at $DEST"
find "$DEST/config" | sort | head -50
