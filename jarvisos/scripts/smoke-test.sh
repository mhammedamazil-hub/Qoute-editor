#!/bin/bash
# smoke-test.sh — headless end-to-end check, no ISO/QEMU needed.
# Runs: pytest, `jarvis --local` command drill, daemon socket round-trip,
# installer refusal checks, shell-script syntax checks.
set -euo pipefail
cd "$(dirname "$0")/.."

say() { echo "[smoke] $*"; }

PY="python3"
[ -x .venv/bin/python ] && PY=".venv/bin/python"

say "1/6 pytest"
$PY -m pytest tests/ -q 2>&1 | tail -2

say "2/6 py_compile all sources"
python3 -m py_compile $(find . -name "*.py" -not -path "./.venv/*")
echo "  compile OK"

say "3/6 bash -n all shell sources"
for f in build.sh build/stage.sh build/install-components.sh build/lb-config.sh \
         build/hooks/live/* scripts/*.sh scripts/helpers/* scripts/installer/* \
         shell/bin/* apps/bin/* jarvis-core/bin/* automation/bin/* voice/bin/* \
         gestures/bin/*; do
  [ -f "$f" ] || continue
  case "$f" in *.py|*.pyc|*__pycache__*) continue;; esac
  head -n1 "$f" | grep -qE "^#!.*\b(bash|sh)\b" || continue
  bash -n "$f" || { echo "SYNTAX FAIL: $f"; exit 1; }
done
echo "  shell syntax OK"

say "4/6 jarvis CLI drill (--local, headless-safe commands)"
export PYTHONPATH="$PWD/jarvis-core"
for cmd in "what is using my ram?" "what can you do?" "show recent files" "take a screenshot"; do
  out="$(python3 jarvis-core/bin/jarvis --local "$cmd" 2>&1 | head -2 || true)"
  echo "  $cmd => ${out:0:90}"
done

say "5/6 daemon socket round-trip"
export XDG_RUNTIME_DIR="$(mktemp -d)"
$PY jarvis-core/jarvisd.py & DPID=$!
sleep 2
python3 - <<'EOF'
import sys
sys.path.insert(0, "shell")
import client
r = client.text_command("what is using my ram?")
assert r["ok"] and "RAM" in r["say"], r
r = client.text_command("reboot")
assert r["needs_confirm"], r
r = client.confirm(r["confirm_token"], False)
assert r["say"] == "Cancelled.", r
r = client.stats()
assert r["ok"] and "mem_percent" in r["data"], r
print("  daemon round-trip OK (text/confirm-cancel/stats)")
EOF
kill "$DPID" 2>/dev/null || true

say "6/6 installer safety refusals"
bash scripts/installer/jarvis-install --help >/dev/null && echo "  --help OK"
out="$(bash scripts/installer/jarvis-install --dry-run </dev/null 2>&1 || true)"
if grep -q "not running on a JARVISOS live system" <<<"$out"; then
  echo "  non-live refusal OK"
else
  echo "  non-live refusal FAILED"; exit 1
fi

say "SMOKE TEST PASSED"
