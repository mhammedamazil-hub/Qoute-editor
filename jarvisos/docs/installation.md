# Installing JARVISOS to disk

> Back up your data. Installing erases the target disk/partitions you select.
> The installer refuses the live USB stick itself as a target.

## Option A — graphical installer (full profile only)

The `full` ISO includes Calamares:

1. Boot the live session → click **Install JARVISOS**.
2. Follow Calamares (language, disk, user, password).
3. Reboot, remove USB, log in at the JARVIS greeter.

## Option B — guided TUI (`jarvis-install`, all profiles)

1. Boot live → open terminal → `sudo jarvis-install`
   (or click **Install JARVISOS**).
2. Choose **whole-disk** (type the disk + `ERASE`) or **manual**
   (prepare partitions in `gparted` first, then pick root + EFI).
3. Enter username/password/hostname; the script copies the live system,
   writes fstab, creates your user, installs GRUB (UEFI or legacy),
   and drops live autologin so you boot to the greeter.
4. Dry-run first if unsure: `jarvis-install --dry-run` (prints every step).

Requirements: target PC must be x86_64 with UEFI (or legacy BIOS);
GRUB install needs internet (downloads `grub-efi-amd64` in the target).

## Post-install

1. Log in → open **Settings → AI Providers** → paste keys → Test.
2. Settings → Network/Bluetooth to connect; Voice → test mic.
3. Install extras on demand: `jarvis install blender` / App Manager.
4. Keep updated: `jarvis update the system`.

## Removing / dual-boot

- Dual-boot: use **manual** mode, install into free partitions, keep your
  existing EFI partition (do NOT format it — mount only). GRUB os-prober
  picks up other systems.
- Uninstall: delete the JARVISOS partitions from your other OS and remove
  the `JARVISOS` EFI entry (`efibootmgr -d … -B -b NNNN`).
