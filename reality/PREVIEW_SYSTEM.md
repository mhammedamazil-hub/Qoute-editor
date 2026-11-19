# CPU preview - `preview.frame`

A headless renderer that draws one frame of a run to a PNG. It needs no GPU, no display and no desktop.

## What it is for

Visual checks: is the sphere on the floor, which way is it moving, did it touch. It is not a physical measurement.
An image cannot carry exact values, so every number shown is also returned in `description`. Do not take a value
from the picture.

## Method

- Orthographic projection. The camera is set by `azimuth_deg` (default -35) and `elevation_deg` (default 20, limit
  -89 to 89) and looks at the centre of the run's bounding box.
- One ray per pixel. Each ray is tested against the analytic sphere (at the chosen record's position) and against each
  infinite plane. The nearest hit is shaded.
- Shading: Lambert with one fixed light direction. The floor is drawn as a checkerboard; its colour is a display
  choice only.
- PNG encoder: pure Python, RGB, 8-bit, no compression library (zlib from the standard library).

## Overlays

Drawn as 2D lines over the shaded image:

- yellow arrow - velocity of the sphere centre; length scaled so the run's maximum speed has a fixed on-screen length;
- red arrow - gravity force m g, length scaled to m g;
- cyan disc - contact point when the sphere touches a plane in that frame.

Switch them off with `show_velocity`, `show_gravity`, `show_contacts` (CLI: `--no-velocity`, `--no-gravity`,
`--no-contacts`).

## Output

- `out_path`: a file ending in `.png` (the CLI requires `--out`). Without it, only the description and optional base64
  are returned.
- `include_base64`: adds `png_base64` and `mime_type` to the result.
- `description`:
  - `frame`: index, time, contacts, position, velocity, speed of the frame shown;
  - `image`: width and height in pixels, `metres_per_pixel`, projection, azimuth, elevation, view basis vectors and the
    view centre; `projected` gives the centre and radius of each body in pixels.

## Limits

Width and height are integers >= 16. Each side is at most `max_image_side` (2048) and the area at most `max_pixels`
(1,000,000). Larger requests fail with `resource_limit` before any pixel is computed. Measured on the development machine (2 cores, Python 3.11): a 300-record run at 480 x 320 takes about 0.6 s, most of it
the ray casting. Re-measure before quoting a time.

## Determinism

The same run, record and parameters give the same bytes (the PNG has no timestamp). This is tested.

## Not included

GIF, animation, mesh rendering, lighting models beyond Lambert, colour management, and any physical rendering
(see the limitations of visual realism in `LIMITATIONS.md`).
