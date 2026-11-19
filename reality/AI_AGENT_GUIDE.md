# AI agent guide - PROJECT REALITY control layer

Use this when an AI agent (through MCP, the CLI or the Python API) drives the simulator. Read `AI_CAPABILITY_MATRIX.md`
first: it says what is implemented and what is not.

## Workflow

1. `system.info` (or `python -m reality.control info`): confirm the version and the limits.
2. `scene.materials`: pick a material name. Or give `mass` or `density` instead.
3. `scene.create`, then `scene.add_sphere`, `scene.add_plane`, `scene.set_contact`. Each returns the new scene; keep it.
4. `scene.validate`: read `errors` and `warnings`. Fix errors before running.
5. `simulate.run` with `duration` (seconds). Keep the returned run document; it is large (records and checks).
6. `inspect.summary` first. Then `inspect.series` or `inspect.body` for the quantity you need.
7. For a visual check, `preview.frame`. Read the numbers from `description`, not from the picture.
8. To compare, change one parameter (for example `scene.set_contact` friction), run again, and use `experiment.compare`.
   To sweep, use `simulate.sweep_friction`.
9. To save work, `export.bundle` writes the scene, run, report and preview with SHA-256 hashes.

## Rules for an agent

- Report numbers from the operation results. Do not infer a value from an image.
- A run's result depends only on its scene and its numerical settings (`dt`, `record_interval`). Say which were used.
- Check the `checks` block of the run document: a run is valid only if `checks.finite_state` is true and
  `checks.max_penetration_m` is within `checks.penetration_tolerance_m` (`inspect.summary` reports both).
- If a call fails, read `error.code`. `resource_limit` means change the request (larger `dt`, fewer records, smaller
  image), not retry it unchanged. `unsupported` means the feature is not in this release.
- Do not claim physical accuracy beyond the validation cases listed in `VALIDATION_REPORT.md`. The slide-to-roll
  time (SIM-01, SIM-02) and checkpoint restart (SIM-03) are the only scene-pipeline cases.
- Friction and restitution are per body-plane pair, with one value each. The rolling-onset time depends on friction; the
  final rolling speed does not (5/7 of the initial speed for a solid sphere), provided the run is long enough to reach
  rolling.

## Worked numbers (from the validation cases)

- Steel sphere, radius 0.05 m, speed 2 m/s, friction 0.1, restitution 0: rolling starts at 2 v0 /(7 mu g) = 0.5827 s;
  final speed 5/7 v0 = 1.4286 m/s; final spin 28.57 rad/s.

## Things an agent should not do

- Do not write the scene file by hand without `scene.validate` afterwards.
- Do not pass a checkpoint from a different scene; the run is refused.
- Do not assume more than one body is possible in a run; v1 refuses it.
