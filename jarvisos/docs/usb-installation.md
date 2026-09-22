# USB installation (write, live-boot)

## Write the ISO to USB

You need an 8 GB+ stick. **All data on the stick will be erased.**

Linux:
```bash
lsblk                      # identify the stick, e.g. /dev/sdb (NOT sda!)
sudo dd if=dist/JARVISOS.iso of=/dev/sdb bs=4M status=progress conv=fsync
```

Windows: use [Rufus](https://rufus.ie) → select `JARVISOS.iso` →
partition scheme GPT, target UEFI → START (DD mode if asked).

Verify first: `sha256sum -c dist/JARVISOS*.iso.sha256`.

## Boot from USB

1. Plug in, power on, open the boot menu (F12/F9/F8/Esc — varies).
2. Choose the UEFI entry for your stick.
3. Pick **JARVISOS Live** (or Performance mode on very weak machines).
4. The live session autologs in as `jarvis` — nothing is installed yet.

Secure Boot: JARVISOS ships no Secure Boot shim signature — disable Secure
Boot in firmware, or enroll your own keys (see `docs/troubleshooting.md`).

## Live session notes

- Full OS: browse, terminal, files, settings, Wi-Fi, Bluetooth, mic.
- Persistence: the live session is amnesic by design. To keep data, install
  to disk (`Install JARVISOS` icon) — see `docs/installation.md`.
- On 4 GB machines the shell auto-selects Performance mode.
