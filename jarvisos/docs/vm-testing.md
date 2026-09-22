# VM testing guide

## QEMU (automated smoke boot)

```bash
./scripts/qemu-test.sh dist/JARVISOS.iso            # BIOS, 2 GB RAM, TCG/KVM
./scripts/qemu-test.sh dist/JARVISOS.iso --uefi     # UEFI via OVMF
```

The script boots with serial logging and greps for the live-boot success
markers (`JARVIS CORE ...... READY` / login prompt). Exit 0 = boot OK.
No KVM? It falls back to TCG (slow — allow up to 10 min).

## QEMU (interactive desktop)

```bash
qemu-system-x86_64 -m 2048 -smp 2 -enable-kvm -cdrom dist/JARVISOS.iso \
  -boot d -vga std -soundhw hda -device usb-tablet
```

## VirtualBox

1. New VM → Linux/Debian 64-bit, 2048 MB RAM, 128 MB video, EFI **enabled**
   (Settings → System → Motherboard → Enable EFI).
2. Storage → attach `JARVISOS.iso` as optical, Live CD.
3. Audio: PulseAudio + ICH AC97 (mic passthrough: enable microphone).
4. Boot → autologin to the JARVIS desktop.

## Verification checklist

- [ ] Boot menu appears (GRUB on UEFI / syslinux on BIOS), 3 entries.
- [ ] Plymouth splash → autologin → HUD + launcher + status + dock.
- [ ] Terminal works (`jarvis-terminal`, normal bash).
- [ ] Files works (navigate, new folder, rename, trash).
- [ ] App launcher buttons open apps; normal windows resize/focus/Alt-Tab.
- [ ] Network: `nmcli device wifi list` / Settings → Network.
- [ ] Mic: Settings → Voice → Test microphone.
- [ ] `jarvis status` → online; `jarvis what is using my ram?` answers.
- [ ] Clap toggle in Settings → Clap/Gestures (needs mic passthrough).
- [ ] AI Settings page saves keys (0600 file) — no key ever shown back.
- [ ] `jarvis reboot` asks for confirmation; ESC stops automation.
- [ ] Idle RAM ≈ 450–650 MB (`free -m` after 2 min idle).

## Measuring idle RAM

Boot, wait 2 minutes, open terminal: `free -m` (use the `available` column:
`used ≈ total − available`). Target: **< 700 MB used** on the minimal
profile. If higher, check `jarvis-monitor` → top processes, and confirm
Performance mode is active (Settings → Performance, or
`jarvis config appearance.performance_mode`).
