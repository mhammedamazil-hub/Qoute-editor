# Creating JARVISOS.iso (reproducible build)

## One-command build

```bash
cd jarvisos
./build.sh          # minimal profile → dist/JARVISOS.iso
./build.sh full     # + Calamares, Blender, GIMP, VLC, LibreOffice
```

Output: `dist/JARVISOS-<version>-<profile>.iso`,
symlinked as `dist/JARVISOS.iso`, plus `.sha256` and a build log.

## Build-host requirements

- Debian 12 / Ubuntu 22.04+ (x86_64), root via sudo, ~15 GB free disk.
- Network access to a Debian mirror (`deb.debian.org`).
- Packages: `live-build debootstrap squashfs-tools xorriso qemu-system-x86`
  (QEMU only for testing):
  ```bash
  sudo apt-get install live-build debootstrap squashfs-tools xorriso \
       qemu-system-x86 ovmf
  ```

> The build only writes inside `jarvisos/build-tmp/` (override with
> `JARVIS_BUILD_DIR`, must stay inside the repo). It never touches host
> disks, partitions, or bootloaders.

## What the build does

1. `build/stage.sh` assembles a live-build tree from single sources:
   `packages/*.list` → package lists; `filesystem/` → `includes.chroot`;
   `boot/` → Plymouth/GRUB/issues; `iso/*.cfg` → bootloader templates;
   `build/install-components.sh` installs the Python lib, shell, apps,
   launchers, defaults, and themes into the overlay.
2. `lb config` (see `build/lb-config.sh`): bookworm, amd64, hybrid ISO,
   `syslinux` (BIOS) + `grub-efi` (UEFI), firmware included, user `jarvis`.
3. `lb build`: bootstrap → install packages → chroot hook (user groups,
   lightdm autologin, X session, pip extras `pyautogui/mss/vosk`, services)
   → squashfs → binary hook renders the real kernel names into the
   GRUB/syslinux menus → hybrid ISO.
4. `scripts/validate-iso.sh` checks PVD, El Torito, `/live` contents.

## No Debian mirror? Use CI

Push to GitHub — `.github/workflows/jarvisos-iso.yml` builds both profiles
on a runner with full network, validates them, and uploads the ISOs as
artifacts (90-day retention). Download from the Actions tab.

## Reproducibility notes

- Same inputs (`VERSION`, package lists, overlay) → same package set;
  `lb config --cache true` keeps bootstrap deterministic-ish per mirror
  snapshot. For bit-identical rebuilds, pin `--mirror-bootstrap` to a
  `snapshot.debian.org` timestamp (documented in `build/lb-config.sh`).
- Version stamp: `/etc/jarvisos-release` + GRUB `iso-volume`.

## Build troubleshooting

| Symptom | Fix |
|---|---|
| `lb: command not found` | install `live-build` (Debian/Ubuntu host only) |
| debootstrap 403/timeout | check mirror access; set `--mirror-bootstrap` to a local mirror |
| `mksquashfs` OOM on 4 GB host | close apps; ensure ≥2 GB free RAM + swap |
| pip extras fail in hook | non-fatal (logged); automation falls back to xdotool |
| stale `build-tmp` | `sudo lb clean --purge` inside it, or `rm -rf build-tmp` |
