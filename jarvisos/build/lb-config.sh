#!/bin/sh
# live-build configuration driver for JARVISOS.
# __PROFILE__ and __VERSION__ are substituted by build/stage.sh.
set -e

lb config noauto \
  --distribution bookworm \
  --archive-areas "main contrib non-free non-free-firmware" \
  --mirror-bootstrap "http://deb.debian.org/debian/" \
  --mirror-chroot "http://deb.debian.org/debian/" \
  --mirror-binary "http://deb.debian.org/debian/" \
  --security true \
  --updates true \
  --backports false \
  --binary-images iso-hybrid \
  --architectures amd64 \
  --linux-flavours amd64 \
  --bootloaders "syslinux grub-efi" \
  --bootloader-theme jarvis \
  --plymouth-theme jarvis \
  --debian-installer none \
  --archive-areas "main contrib non-free non-free-firmware" \
  --firmware-binary true \
  --firmware-chroot true \
  --swap-file-path none \
  --zsync false \
  --checksums sha256 \
  --image-name "JARVISOS-__VERSION__-__PROFILE__" \
  --iso-application "JARVISOS" \
  --iso-publisher "JARVISOS project" \
  --iso-volume "JARVISOS __VERSION__" \
  --memtest none \
  --win32-loader false \
  --username jarvis \
  --hostname jarvisos \
  --locales "en_US.UTF-8" \
  --keyboard-layouts us \
  --timezone Etc/UTC \
  --apt-recommends false \
  --apt-secure true \
  --cache true \
  --uefi-secure-boot none \
  "${@}"
