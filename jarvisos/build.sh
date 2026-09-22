#!/bin/bash
# JARVISOS ISO builder — reproducible, one command:
#   ./build.sh [minimal|full]
# Output: dist/JARVISOS.iso (+ .sha256)
#
# Requires: Debian/Ubuntu build host, root (or sudo), live-build,
# network access to a Debian mirror. See docs/iso-creation.md
# This script NEVER touches the host's disks/bootloader — everything happens
# inside ./build-tmp/ (or $JARVIS_BUILD_DIR).
set -euo pipefail

PROFILE="${1:-minimal}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(cat "$SRC_DIR/VERSION")"
BUILD_DIR="${JARVIS_BUILD_DIR:-$SRC_DIR/build-tmp}"
OUT_DIR="$SRC_DIR/dist"
ISO_NAME="JARVISOS-${VERSION}-${PROFILE}.iso"

log() { echo "[jarvis-build] $*"; }
die() { echo "[jarvis-build] ERROR: $*" >&2; exit 1; }

[ "$PROFILE" = "minimal" ] || [ "$PROFILE" = "full" ] \
  || die "profile must be 'minimal' or 'full' (got '$PROFILE')"

if [ "$(id -u)" -ne 0 ]; then
  # Re-exec under sudo so lb build (which needs root for chroot/mounts) works.
  log "re-executing with sudo (build needs root for chroot/mounts only)"
  exec sudo -E bash "$0" "$PROFILE"
fi

for t in lb debootstrap mksquashfs xorriso; do
  command -v "$t" >/dev/null 2>&1 || die "missing build tool: $t (see docs/iso-creation.md)"
done

# Safety: refuse to run if the build dir escapes the project.
case "$BUILD_DIR" in
  "$SRC_DIR"/*) ;;
  *) die "JARVIS_BUILD_DIR must be inside $SRC_DIR (refusing: $BUILD_DIR)" ;;
esac

mkdir -p "$BUILD_DIR" "$OUT_DIR"
rm -rf "$BUILD_DIR/lb"

log "JARVISOS $VERSION ($PROFILE) — staging live-build config"
bash "$SRC_DIR/build/stage.sh" "$PROFILE" "$BUILD_DIR/lb" "$VERSION"

log "entering build dir: $BUILD_DIR/lb"
cd "$BUILD_DIR/lb"

log "running lb config"
bash auto/config

log "running lb build (this takes a while: bootstrap + squashfs + iso)"
lb build 2>&1 | tee "$OUT_DIR/build-${PROFILE}.log"

ISO_SRC="$(ls -1 live-image-*.hybrid.iso 2>/dev/null | head -n1 || true)"
[ -n "$ISO_SRC" ] || die "lb build finished but no .hybrid.iso was produced"

mv "$ISO_SRC" "$OUT_DIR/$ISO_NAME"
ln -sf "$ISO_NAME" "$OUT_DIR/JARVISOS.iso"
( cd "$OUT_DIR" && sha256sum "$ISO_NAME" > "$ISO_NAME.sha256" )

log "validating ISO"
bash "$SRC_DIR/scripts/validate-iso.sh" "$OUT_DIR/$ISO_NAME" || \
  die "ISO validation failed"

log "OK: $OUT_DIR/$ISO_NAME"
log "sha256: $(cat "$OUT_DIR/$ISO_NAME.sha256")"
log "test it: ./scripts/qemu-test.sh $OUT_DIR/$ISO_NAME"
