# CLI reference - `python -m reality.control`

Every command prints one JSON document on stdout. Exit codes:

| code | meaning |
|---|---|
| 0 | success (for `scene validate` and `validate`: the check passed) |
| 1 | an operation error (`{"error": {"code", "message", "details"}}` on stdout) or a failed check |
| 2 | a usage error from argparse (message on stderr) |

Run from a checkout with `PYTHONPATH=src`, or after `pip install -e .`. Scene and run files are plain JSON. Commands
that edit a scene write the file in place unless `--out` is given. All numbers are SI.

## Discovery

- `info` - package version, Python version, default resource limits, schema versions, interfaces.
- `ops [NAME]` - list operations, or print one operation's input schema.
- `call OPERATION --args JSON|@file` - run any registry operation with a JSON object of arguments.

## Scene (`scene ...`)

- `scene new FILE --name NAME [--gravity GX GY GZ]` - new scene; default gravity is (0, 0, -9.80665).
- `scene add-sphere FILE --id ID --radius R (--material M | --mass KG | --density RHO) [--position X Y Z] [--velocity VX VY VZ] [--omega WX WY WZ] [--out FILE]`
- `scene add-plane FILE --id ID [--normal NX NY NZ] [--offset D] [--out FILE]` - plane `n . x = D`; free side `n . x > D`.
- `scene set-body FILE --id ID [--radius R] [--material M] [--mass KG] [--density RHO] [--position ...] [--velocity ...] [--omega ...] [--out FILE]`
- `scene set-gravity FILE GX GY GZ [--out FILE]`
- `scene set-contact FILE --body ID --plane ID --friction MU [--restitution E] [--out FILE]`
- `scene remove FILE --id ID [--out FILE]`
- `scene validate FILE` - `{"valid", "errors", "warnings"}`; exit 1 when invalid.
- `scene describe FILE` - masses, inertia, densities, contacts.
- `scene materials` - the material names accepted by `--material`.

## Simulation (`simulate ...`)

- `simulate run SCENE --duration S [--dt S] [--record-interval S] [--checkpoint RUN_OR_CHECKPOINT] [--out FILE] [--limit NAME=VALUE ...]`
  - Without `--out` the full run document goes to stdout. With `--out` the file holds the run and stdout holds a summary.
  - `--checkpoint` takes an earlier run file (its `final_state` is used) and continues from that time. The scene must be the same one that produced the checkpoint.
- `simulate sweep-friction SCENE --body ID --plane ID --values MU1 MU2 ... --duration S [--dt S] [--record-interval S] [--limit ...]` - one summary per friction value; at most 100 values.

## Inspection (`inspect ...`)

- `inspect body RUN --body ID [--index I]` - one record (default last): position, velocity, orientation, angular velocity, energies, plus an `unsupported` list with reasons.
- `inspect scene RUN [--index I]` - all bodies and planes at one record, and the checks.
- `inspect series RUN --body ID [--fields F ...]` - time series. Fields: `x y z vx vy vz speed omega_wz ke_translational ke_rotational potential_gravity contacts`.
- `inspect rolling-onset RUN --body ID` - time the sphere starts to roll (see PHYSICS note in `AI_CAPABILITY_MATRIX.md`).
- `inspect summary RUN` - final state, rolling onset, maximum penetration, checks.

## Preview and comparison

- `preview frame RUN --out FILE.png [--index I] [--width W] [--height H] [--azimuth DEG] [--elevation DEG] [--no-velocity] [--no-gravity] [--no-contacts] [--base64] [--limit ...]` - writes a PNG and prints the numerical description. See `PREVIEW_SYSTEM.md`.
- `compare RUN_A RUN_B --body ID` - changed scene fields, final-state differences, rolling-onset shift, energies.

## Export and validation

- `export --out-dir DIR --scene SCENE --run RUN [--preview PNG]` - writes `scene.json`, `run.json`, `report.md` and optionally `preview.png`, and prints SHA-256 and size of each file.
- `validate [--domain all|sim|NAME] [--out FILE]` - runs validation cases. `sim` runs the scene-pipeline cases SIM-01..03. Exit 1 if any case fails.

## Server

- `mcp` - serve the registry over MCP on stdin and stdout (see `MCP_REFERENCE.md`).

## Example

```bash
export PYTHONPATH=src
python -m reality.control scene new s.json --name demo
python -m reality.control scene add-sphere s.json --id ball --radius 0.05 --material steel --position 0 0 0.05 --velocity 2 0 0
python -m reality.control scene add-plane s.json --id floor
python -m reality.control scene set-contact s.json --body ball --plane floor --friction 0.1
python -m reality.control simulate run s.json --duration 3 --out run.json
python -m reality.control inspect summary run.json
python -m reality.control preview frame run.json --out frame.png
```
