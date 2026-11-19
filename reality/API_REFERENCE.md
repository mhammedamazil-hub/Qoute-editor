# Python API reference - `reality.control`

The API has no logic of its own. `reality.control.operations` holds every operation; the CLI and the MCP adapter call
the same function. The Python API adds two entry points: `call` (dict in, dict out) and `call_json` (JSON text in and
out, errors returned as documents).

```python
import json
from reality.control import api, operations, OperationError

scene = api.call("scene.create", {"name": "demo"})
scene = api.call("scene.add_sphere", {"scene": scene, "id": "ball", "radius": 0.05,
                                      "material": "steel", "position": [0, 0, 0.05], "velocity": [2, 0, 0]})
scene = api.call("scene.add_plane", {"scene": scene, "id": "floor"})
scene = api.call("scene.set_contact", {"scene": scene, "body": "ball", "plane": "floor", "friction": 0.1})
run = api.call("simulate.run", {"scene": scene, "duration": 1.0})
summary = api.call("inspect.summary", {"result": run})

text = api.call_json("scene.validate", '{"scene": ' + json.dumps(scene) + '}')   # JSON text in and out
```

## Functions

- `api.call(name, args=None) -> dict` - run one operation. Raises `OperationError` for every expected failure.
  Non-JSON-compatible results are refused (`invalid_state`), so every result can be written with `json.dumps`.
- `api.call_json(name, args_json) -> str` - same, with JSON text. Returns `{"error": ...}` text instead of raising.
- `api.operations_list() -> list` - name, description and input schema of each operation.
- `operations.list_operations()` - the same list, from the registry module.
- `operations.call(name, args)` - the function `api.call` wraps.

## Errors

`OperationError(code, message, details=None)` with `.code`, `.message`, `.details` and `.to_dict()`. The codes are
listed in `RESOURCE_LIMITS.md` (section "Error codes"). Codes are part of the interface.

## Operations

22 operations. Each has an input schema (JSON Schema subset, see `control/schema.py`); unknown or mistyped arguments
are rejected before the operation runs.

| operation | purpose |
|---|---|
| `scene.create` | new empty scene |
| `scene.add_sphere`, `scene.add_plane` | add a body or a plane |
| `scene.set_body`, `scene.set_gravity`, `scene.set_contact`, `scene.remove` | edit a scene |
| `scene.validate`, `scene.describe` | check and summarise a scene |
| `scene.materials` | material names for `scene.add_sphere` |
| `simulate.run` | run from t = 0 or from a checkpoint |
| `simulate.sweep_friction` | one summary per friction value |
| `inspect.body`, `inspect.scene`, `inspect.series` | read a run at a record or over time |
| `inspect.rolling_onset`, `inspect.summary` | slide-to-roll time; final state and checks |
| `preview.frame` | PNG and numerical description of one frame |
| `experiment.compare` | difference between two runs |
| `export.bundle` | scene, run, report and preview in a directory, with hashes |
| `validate.run` | validation cases from the registry |
| `system.info` | version, limits, interfaces |

Run `python -m reality.control ops NAME` or `api.operations_list()` for the exact schema.

## Determinism

A run document holds everything needed to reproduce it: the scene (with its SHA-256), the numerical configuration, the
software version, `random_seed: null` (the kernel has no stochastic component) and the limits used. Everything except
`diagnostics` is bit-for-bit reproducible on the same platform (verified by `tests/test_control.py`).

## Stability

The operation names, argument names and error codes are the public interface of this release. Adding optional
arguments is allowed. Renaming, removing or changing the meaning of an argument needs a version bump.
