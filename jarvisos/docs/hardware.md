# Hardware requirements & 4 GB tuning

## Requirements

| | Minimum | Recommended |
|---|---|---|
| CPU | 64-bit dual-core (2010+) | Intel i3+ / AMD equivalent |
| RAM | **4 GB** (Performance mode) | 6–8 GB (Cinematic mode) |
| GPU | any with kernel modesetting (Intel iGPU fine) | Intel HD 4000+ |
| Disk | 12 GB free (live USB: 8 GB stick) | 25 GB+ SSD |
| Boot | x86_64 UEFI (legacy BIOS supported) | UEFI, Secure Boot off |
| Net | optional (offline fully usable) | Wi-Fi for AI + installs |

Supported out of the box: Wi-Fi (incl. Intel/Realtek/Atheros firmware),
Bluetooth, USB, audio/mic (PipeWire), webcams (V4L2), printers (CUPS),
touchpads, multi-monitor (arandr), battery/thermal sensors.

## 4 GB tuning (what JARVISOS already does)

- Openbox + custom shell instead of GNOME/KDE (~50 MB vs ~800 MB).
- No compositor, static HUD core, 5 s status polling in Performance mode
  (auto-selected below 5120 MB; override in Settings → Performance).
- No local LLM, no always-on ML: clap DSP ≈ 1–2% CPU; STT only while
  push-to-talk records; cloud calls are short HTTPS requests.
- `apt-recommends false` keeps the base image small.

## If the system feels slow

1. Settings → Performance → `performance`; log out/in.
2. Close the browser when using Blender (biggest RAM users).
3. `jarvis-monitor` → find the hog (`what is using my ram?`).
4. Add swap: `sudo fallocate -l 2G /swapfile && sudo mkswap /swapfile …`
   (live session: swapfile on disk works the same way).
5. Consider the `minimal` profile ISO (no LibreOffice/GIMP/VLC preinstalled).
