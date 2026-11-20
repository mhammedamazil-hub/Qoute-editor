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
body-body contact, no thermal or stress fields. These are listed in `AI_CAPABILITY_MATRIX.md`. v1 is unchanged.

## Schema v2: several bodies (`"schema_version": 2`)

Same `schema` (`reality.scene`) and `environment`, with these lists:

- `bodies`: each `{id, type: "sphere", radius, position, velocity, omega}` and exactly one of `material`, `mass` or
  `density`. Mass properties use the same derivation as v1 (`scene.mass_properties`). Optional `quaternion`
  `(w, x, y, z)`, unit length, body to world; default identity. The v2 validator rejects a non-unit quaternion.
- `planes`: each `{id, normal, offset}`. The normal must be non-zero (it is normalised internally).
- `contacts`: each `{a, b, friction, restitution}`. `a` is a body id. `b` is a plane id (sphere-plane) or another
  body id (sphere-sphere). `friction >= 0`, `restitution` in `[0, 1]`. Each contact has its own coefficients. A pair
  or plane that is not listed does not collide. A pair may be listed once only.

Example (two spheres on a floor): `{"schema": "reality.scene", "schema_version": 2, "name": "stack",
"environment": {"gravity": [0, 0, -9.80665]}, "bodies": [...], "planes": [{"id": "floor", "normal": [0, 0, 1],
"offset": 0}], "contacts": [{"a": "bottom", "b": "floor", "friction": 0.5, "restitution": 0}, ...]}`.

`scene.validate` dispatches on `schema_version`, so v2 scenes are checked by the v2 rules. `simulate.run` refuses v2
scenes and points to `simulate.multibody`. Run documents are `reality.multibody_run` version 1: `records` hold each
body's state, energies, `momentum_total` and touching `contacts`; `checks` report the largest penetration
(tolerance 1e-6 m) and the quaternion norm error; `diagnostics` holds wall time and memory and is not reproducible.

v2 limits: no checkpoint, no sweep, no non-sphere shapes, one contact point per pair or plane.

**Meshes in v2 (approved change, Phase 6).** A v2 document with a non-empty `meshes` list is a collision scene with the
v2 rules: `bodies` are spheres only, with no `static` flag; `planes` as above; `meshes` are static triangle meshes
(`id`, `vertices`, `triangles`, optional `position` and `quaternion`, exactly as in v3); `contacts` may name a mesh as
`b` (sphere-mesh). Such a document runs on the collision solver (`control/collision_scene.py`) and returns
`reality.collision_run`. The sphere solver is not used for it: `multibody_scene.validate_v2` refuses `meshes`
explicitly. A v2 document with no `meshes` key, or an empty list, is unchanged and runs on the sphere solver
(`reality.multibody_run`).

## Schema v3: spheres, boxes, planes, static meshes (`"schema_version": 3`)

Same `schema` and `environment`. Versions 1 and 2 are unchanged. Implementation: `control/collision_scene.py`; the
geometry is in `src/reality/collision/` (see `COLLISION_GEOMETRY.md`).

- `bodies`: each `{id, type, ...}` with `type` `"sphere"` (`radius`) or `"box"` (`half_extents` = `[hx, hy, hz]`, half
  the edge lengths along body axes, all > 0). Both: `position`, `velocity`, `omega` (body frame), optional unit
  `quaternion`, optional `static` (true or false). Dynamic bodies need exactly one of `material`, `mass` or `density`
  (box volume is `8 hx hy hz`). A static body has no mass: it must not give one, and it must have zero velocity and
  zero `omega`.
- `planes`: each `{id, normal, offset}`, the normal not all zero.
- `meshes`: static triangle meshes, each `{id, vertices, triangles, position?, quaternion?}`. `vertices` are
  `[x, y, z]` in the mesh frame; `triangles` are three integer indices each. Zero-area triangles are a warning.
  A triangle that repeats a vertex index is an error. A mesh has at most 200,000 vertices and triangles; the scene has
  at most 400,000 triangles in total (`collision.MESH_LIMITS`).
- `contacts`: each `{a, b, friction, restitution}`. `a` is a body. `b` is a body, a plane or a mesh. Not listed means
  not colliding. A pair may be listed once only, and a body cannot contact itself. Two static bodies cannot form a
  contact.

Supported pairs: sphere-sphere, sphere-box, sphere-plane, box-plane, box-box, sphere-mesh. Box-mesh is rejected with
`unsupported` and the pair named in the message. It is not ignored. Box-box contacts are SAT with clipping (up to 8
contact points per pair, not reduced); see `COLLISION_GEOMETRY.md` and `BOX_BOX_STUDY.md`.

Limits: 256 bodies, 64 planes, 2,048 contacts, the mesh limits above. Exceeding a limit is a `schema_error` with the
count and the limit in the message.

Run document: `reality.collision_run` version 1, produced by `simulate.multibody` when `schema_version` is 3. Each record
holds every body (dynamic and static: the same keys; a static body has zero velocity and energy and `static: true`),
the planes' contacts as `plane:<id>`, `body:<id>` or `mesh:<id>` entries, `momentum_total` and `energy_total`.
`checks` report `max_penetration_m` (tolerance 1e-6 m), `max_quaternion_norm_error` and `finite_state`.
`diagnostics` holds wall time and memory and is not reproducible.

`collision.query` lists the contacts of a v3 scene at its initial state, without stepping. `collision.validate_mesh`
checks raw vertices and triangles and reports the BVH size.

## Validation

`scene.validate` returns `{"valid", "errors", "warnings"}` and never raises. Warnings are advisory: for example a body
with no contact entry does not collide. Errors make the scene unusable; `simulate.run` refuses an invalid scene with
`schema_error`.

## Hash

`scene_sha256` is the SHA-256 of the canonical JSON (sorted keys, no whitespace). It appears in every run document and
in every export report, so a run can be matched to its scene.
