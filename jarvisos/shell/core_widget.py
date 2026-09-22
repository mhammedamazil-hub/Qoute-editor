"""Arc-reactor core widget (Cairo). Animated in Cinematic mode, single
static frame in Performance mode. Zero cost when animations are off."""
from __future__ import annotations

import math

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib
    HAVE_GTK = True
except (ImportError, ValueError):
    HAVE_GTK = False


ACCENT = (0.20, 0.88, 1.0)  # #35e0ff


if HAVE_GTK:

    class CoreWidget(Gtk.DrawingArea):
        def __init__(self, size=190, animated=True):
            super().__init__()
            self.set_size_request(size, size)
            self.phase = 0.0
            self.level = 0.35  # 0..1 activity glow
            self.connect("draw", self._on_draw)
            if animated:
                GLib.timeout_add(50, self._tick)

        def _tick(self):
            self.phase += 0.06
            self.queue_draw()
            return True

        def pulse(self, level=0.9):
            self.level = max(0.1, min(1.0, level))
            self.queue_draw()

        def _on_draw(self, _w, cr):
            w = self.get_allocated_width()
            h = self.get_allocated_height()
            cx, cy = w / 2, h / 2
            radius = min(w, h) / 2 - 4
            r, g, b = ACCENT
            # outer glow
            cr.set_source_rgba(r, g, b, 0.10 + 0.10 * self.level)
            cr.arc(cx, cy, radius, 0, 2 * math.pi)
            cr.fill()
            # orbital rings (rotate with phase)
            for i, (frac, width, alpha) in enumerate(
                    [(0.96, 2.0, 0.9), (0.80, 1.5, 0.6), (0.64, 6.0, 0.35)]):
                cr.set_source_rgba(r, g, b, alpha)
                cr.set_line_width(width)
                start = self.phase * (1 + 0.4 * i) + i
                cr.arc(cx, cy, radius * frac, start, start + 4.4)
                cr.stroke()
            # tick marks
            cr.set_source_rgba(r, g, b, 0.5)
            cr.set_line_width(1.5)
            for k in range(24):
                a = k * math.pi / 12 + self.phase * 0.3
                x1, y1 = cx + math.cos(a) * radius * 0.70, \
                    cy + math.sin(a) * radius * 0.70
                x2, y2 = cx + math.cos(a) * radius * 0.76, \
                    cy + math.sin(a) * radius * 0.76
                cr.move_to(x1, y1)
                cr.line_to(x2, y2)
            cr.stroke()
            # inner core
            cr.set_source_rgba(0.85, 0.98, 1.0, 0.95)
            cr.arc(cx, cy, radius * 0.30 * (0.9 + 0.2 * self.level),
                   0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(r, g, b, 0.9)
            cr.set_line_width(2.0)
            cr.arc(cx, cy, radius * 0.42, 0, 2 * math.pi)
            cr.stroke()
            # decay activity glow toward idle
            self.level += (0.35 - self.level) * 0.05
            return False

else:  # pragma: no cover - headless import guard

    class CoreWidget:  # type: ignore
        def __init__(self, *a, **k):
            raise RuntimeError("GTK3 (python3-gi) is required for the shell")
