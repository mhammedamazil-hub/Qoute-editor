# Scene schema v1 - `reality.scene`

A scene is one JSON object. It is the input of `simulate.run` and of every scene operation. Units are SI everywhere.

```json
{
  "schema": "reality.scene",
  "schema_version": 1,
  "name": "sphere-plane",
  "environment": {"gravity": [0.0, 0.0, -9.80665], "units": "SI"},
  "bodies": [
    {"id": "ball", "type": "sphere", "radius": 0.05, "material": "steel",
     "position": [0.0, 0.0, 0.05], "velocity": [2.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0]}
  ],
  "planes": [{"id": "floor", "normal": [0.0, 0.0, 1.0], "offset": 0.0}],
  "contacts": [{"body": "ball", "plane": "floor", "friction": 0.1, "restitution": 0.0}],
  "random_seed": null
}
```

## Fields

- `schema` must be `"reality.scene"`; `schema_version` must be `1`. Other values are refused.
- `name`: non-empty string, at most 120 characters.
- `environment.gravity`: three finite numbers, m/s^2. Default (0, 0, -9.80665). `units` is `"SI"`.
- `bodies`: list of spheres. Each has:
  - `id`: letter first, then letters, digits, `_` or `-`, at most 64 characters. Unique across bodies and planes.
  - `type`: `"sphere"` (the only type in v1).
  - `radius`: metres, > 0.
  - Exactly one of `material` (a name from `scene.materials`, density taken from the database), `mass` (kg, > 0) or
    `density` (kg/m^3, > 0). The chosen source is recorded in `density_source` by `scene.describe`.
  - `position`, `velocity` (m, m/s), `omega` (rad/s, body-centred, world axes at t = 0).
- `planes`: infinite planes `{x : n . x = offset}`. `normal` is any non-zero vector (normalised on use); the free side
  is `n . x > offset`.
- `contacts`: one entry per body-plane pair that collides. `friction` is a dimensionless Coulomb coefficient >= 0;
  `restitution` is in [0, 1]. A body-plane pair without an entry does not collide.
- `random_seed`: must be `null`. The kernel has no stochastic component.

## Limits of v1

One body per run (the runner refuses more with `unsupported`). Spheres and infinite planes only. No meshes, no
body-body contact, no thermal or stress fields. These are listed in `AI_CAPABILITY_MATRIX.md`.

## Validation

`scene.validate` returns `{"valid", "errors", "warnings"}` and never raises. Warnings are advisory: for example a body
with no contact entry does not collide. Errors make the scene unusable; `simulate.run` refuses an invalid scene with
`schema_error`.

## Hash

`scene_sha256` is the SHA-256 of the canonical JSON (sorted keys, no whitespace). It appears in every run document and
in every export report, so a run can be matched to its scene.
