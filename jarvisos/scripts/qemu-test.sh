#!/bin/bash
# qemu-test.sh — boot the ISO in QEMU and check for a successful live boot.
# Needs: qemu-system-x86 (+ OVMF for UEFI; falls back to BIOS boot).
# Host-safe: no disks attached except the ISO; snapshot mode; no KVM needed
# (uses TCG when /dev/kvm is absent — slow but workable).
# Usage: ./scripts/qemu-test.sh dist/JARVISOS.iso [--uefi] [--timeout 600]
set -u

ISO="${1:-}"; UEFI=0; TIMEOUT=600
shift || true
while [ $# -gt 0 ]; do
  case "$1" in --uefi) UEFI=1;; --timeout) TIMEOUT="$2"; shift;; *) ;; esac
  shift
done
[ -n "$ISO" ] && [ -f "$ISO" ] || { echo "usage: qemu-test.sh ISO [--uefi] [--timeout S]" >&2; exit 2; }
command -v qemu-system-x86_64 >/dev/null 2>&1 || { echo "qemu-system-x86_64 not installed" >&2; exit 3; }

LOG="$(mktemp -d)/jarvis-qemu.log"
ACCEL="tcg"; [ -e /dev/kvm ] && ACCEL="kvm"
ARGS=(-m 2048 -smp 2 -accel "$ACCEL" -cdrom "$ISO" -boot d -snapshot
  -display none -serial "file:$LOG" -no-reboot
  -nic none)
if [ "$UEFI" = 1 ]; then
  OVMF="$(ls /usr/share/OVMF/OVMF_CODE*.fd 2>/dev/null | head -n1 || true)"
  [ -n "$OVMF" ] || { echo "OVMF firmware not found (need ovmf package)" >&2; exit 3; }
  VARS="$(mktemp -d)/vars.fd"; cp /usr/share/OVMF/OVMF_VARS*.fd "$VARS" 2>/dev/null || cp "$OVMF" "$VARS"
  ARGS+=(-drive "if=pflash,format=raw,readonly=on,file=$OVMF"
         -drive "if=pflash,format=raw,file=$VARS")
fi

echo "[qemu] booting $ISO (accel=$ACCEL uefi=$UEFI timeout=${TIMEOUT}s)…"
echo "[qemu] serial log: $LOG"
timeout "$TIMEOUT" qemu-system-x86_64 "${ARGS[@]}" &
QEMU_PID=$!
# success markers from the live boot (live-boot + our rc.local banner)
deadline=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $deadline ]; do
  sleep 15
  if grep -qiE "JARVIS CORE \.+ READY|Live system|jarvisos login" "$LOG" 2>/dev/null; then
    echo "[qemu] SUCCESS: live system reached login/banner."
    grep -iE "JARVIS|Live system|login" "$LOG" | tail -5
    kill "$QEMU_PID" 2>/dev/null || true
    exit 0
  fi
  kill -0 "$QEMU_PID" 2>/dev/null || break
done
echo "[qemu] TIMEOUT/EXIT without success markers. Last log lines:"
tail -30 "$LOG" 2>/dev/null || echo "(no serial output)"
kill "$QEMU_PID" 2>/dev/null || true
exit 1
