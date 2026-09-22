"""System stats from /proc and /sys — no daemons, ~zero overhead."""
from __future__ import annotations

import glob
import os
import time

_last_cpu = None


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def mem():
    """Return dict(total_mb, used_mb, avail_mb, percent, swap_*)."""
    info = {}
    for line in _read("/proc/meminfo").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(":"):
            try:
                info[parts[0][:-1]] = int(parts[1])  # kB
            except ValueError:
                pass
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(0, total - avail)
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    return {
        "total_mb": total // 1024,
        "used_mb": used // 1024,
        "avail_mb": avail // 1024,
        "percent": round(100.0 * used / total, 1) if total else 0.0,
        "swap_total_mb": swap_total // 1024,
        "swap_used_mb": (swap_total - swap_free) // 1024,
    }


def cpu_percent(interval=0.1):
    """CPU usage % across all cores (two /proc/stat samples)."""
    global _last_cpu

    def sample():
        line = _read("/proc/stat").splitlines()
        if not line or not line[0].startswith("cpu "):
            return None
        return [int(x) for x in line[0].split()[1:]]

    first = sample()
    if first is None:
        return 0.0
    time.sleep(interval)
    second = sample()
    if second is None:
        return 0.0
    idle1 = first[3] + (first[4] if len(first) > 4 else 0)
    idle2 = second[3] + (second[4] if len(second) > 4 else 0)
    total1, total2 = sum(first), sum(second)
    if total2 == total1:
        return 0.0
    return round(100.0 * (1.0 - (idle2 - idle1) / (total2 - total1)), 1)


def cpu_count():
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def loadavg():
    try:
        with open("/proc/loadavg") as fh:
            a, b, c = fh.read().split()[:3]
        return float(a), float(b), float(c)
    except (OSError, ValueError):
        return 0.0, 0.0, 0.0


def disk(path="/"):
    """Return dict(total_gb, used_gb, free_gb, percent) for path."""
    try:
        st = os.statvfs(path)
    except OSError:
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0.0}
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - free
    gb = 1024 ** 3
    return {
        "total_gb": round(total / gb, 1),
        "used_gb": round(used / gb, 1),
        "free_gb": round(free / gb, 1),
        "percent": round(100.0 * used / total, 1) if total else 0.0,
    }


def battery():
    """Return dict(percent, state, time) or None when no battery exists."""
    for bat in sorted(glob.glob("/sys/class/power_supply/BAT*")):
        cap = _read(os.path.join(bat, "capacity")).strip()
        state = _read(os.path.join(bat, "status")).strip().lower()
        try:
            pct = int(cap)
        except ValueError:
            continue
        return {"percent": pct, "state": state or "unknown", "time": ""}
    # alternative: upower-less desktops expose charge_* only
    return None


def temperature():
    """Best-effort CPU temp in °C, or None."""
    best = None
    for zone in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            val = int(_read(zone).strip())
        except ValueError:
            continue
        c = val / 1000.0 if val > 1000 else float(val)
        if 0 < c < 125 and (best is None or c > best):
            best = c
    return round(best, 1) if best is not None else None


def top_processes(limit=8):
    """Top processes by RSS. Returns list of dicts(pid, name, rss_mb, cpu_s)."""
    procs = []
    for pid in [p for p in os.listdir("/proc") if p.isdigit()]:
        try:
            with open("/proc/%s/stat" % pid, encoding="utf-8",
                      errors="replace") as fh:
                stat = fh.read().rsplit(")", 1)[1].split()
            utime = int(stat[11])
            stime = int(stat[12])
            rss_pages = int(stat[21])
            with open("/proc/%s/comm" % pid, encoding="utf-8",
                      errors="replace") as fh:
                name = fh.read().strip()
            procs.append({
                "pid": int(pid), "name": name,
                "rss_mb": round(rss_pages * 4096 / 1024 ** 2, 1),
                "cpu_s": round((utime + stime) / 100.0, 1),
            })
        except (OSError, ValueError, IndexError):
            continue
    procs.sort(key=lambda p: p["rss_mb"], reverse=True)
    return procs[:limit]


def summary():
    """One-shot dict for the shell's right panel (cheap: no cpu% sample)."""
    m = mem()
    d = disk(os.path.expanduser("~"))
    b = battery()
    return {
        "mem_percent": m["percent"],
        "mem_used_mb": m["used_mb"],
        "mem_total_mb": m["total_mb"],
        "disk_percent": d["percent"],
        "disk_free_gb": d["free_gb"],
        "battery_percent": b["percent"] if b else None,
        "battery_state": b["state"] if b else "no battery",
        "temp_c": temperature(),
        "load1": loadavg()[0],
    }
