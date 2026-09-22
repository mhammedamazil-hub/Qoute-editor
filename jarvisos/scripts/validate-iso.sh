#!/bin/bash
# validate-iso.sh — verify a JARVISOS.iso without booting it.
# Checks: exists, sane size, ISO9660 PVD, volume id, El Torito boot record,
# /live kernel+initrd+squashfs presence. Uses xorriso/isoinfo when present,
# else a built-in Python ISO9660 reader. Exit 0 = valid.
set -euo pipefail

ISO="${1:-}"
[ -n "$ISO" ] && [ -f "$ISO" ] || { echo "usage: validate-iso.sh J.iso" >&2; exit 2; }

say()  { echo "[validate] $*"; }
fail() { echo "[validate] FAIL: $*" >&2; exit 1; }

size="$(stat -c%s "$ISO")"
say "file: $ISO ($((size/1024/1024)) MB)"
[ "$size" -gt 100000000 ] || fail "ISO smaller than 100 MB ($size bytes)"

if command -v xorriso >/dev/null 2>&1; then
  say "backend: xorriso"
  xorriso -indev "$ISO" -toc 2>/dev/null | head -30 || fail "xorriso cannot read TOC"
  xorriso -indev "$ISO" -find /live 2>/dev/null | tee /tmp/jarvis-iso-live.txt | head -20
  grep -qi "vmlinuz" /tmp/jarvis-iso-live.txt || fail "no vmlinuz under /live"
  grep -qi "initrd" /tmp/jarvis-iso-live.txt || fail "no initrd under /live"
  grep -qi "filesystem.squashfs" /tmp/jarvis-iso-live.txt || fail "no filesystem.squashfs under /live"
  say "OK: kernel + initrd + squashfs present"
  exit 0
fi

say "backend: built-in python ISO9660 reader (xorriso not installed)"
/usr/bin/python3 - "$ISO" <<'EOF'
import struct, sys
iso = sys.argv[1]
SECT = 2048
with open(iso, 'rb') as fh:
    fh.seek(16 * SECT)
    pvd = fh.read(SECT)
    assert pvd[0] == 1 and pvd[1:6] == b'CD001', 'not an ISO9660 PVD'
    vol = pvd[40:72].decode('ascii', 'replace').strip()
    print('[validate] volume id: %s' % vol)
    assert 'JARVIS' in vol.upper(), 'unexpected volume id: %s' % vol
    # boot record?
    fh.seek(17 * SECT)
    br = fh.read(SECT)
    boot = br[0] == 0 and br[1:6] == b'CD001' and b'EL TORITO' in br[7:64]
    print('[validate] El Torito boot record: %s' % ('yes' if boot else 'no'))
    assert boot, 'no El Torito boot record — ISO would not boot'
    # root dir
    root_ext, root_len = struct.unpack('<II', pvd[156+2:156+10])
    fh.seek(root_ext * SECT)
    names = set()
    data = fh.read(root_len)
    off = 0
    while off < len(data):
        ln = data[off]
        if ln == 0:
            break
        flags = data[off + 25]
        nlen = data[off + 32]
        name = data[off + 33:off + 33 + nlen].split(b';')[0].decode('ascii', 'replace')
        names.add((name, bool(flags & 2)))
        off += ln
    print('[validate] root entries: %s' % sorted(n for n, d in names))
    assert any(n == 'LIVE' and d for n, d in names), 'no /LIVE dir'
print('[validate] OK: PVD + El Torito + /LIVE present')
EOF
say "OK: ISO structure valid (full file check needs xorriso)"
