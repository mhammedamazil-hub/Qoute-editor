# Resource limits and error codes

Every operation that can run long or allocate memory checks a set of budgets. A request that exceeds one stops with a
`resource_limit` error before the work is done (for the step, record and pixel budgets) or during the run (for the
wall-clock and memory budgets). Nothing is silently truncated.

## Defaults

| name | default | meaning |
|---|---|---|
| `max_steps` | 2,000,000 | integration steps per run (about 100 s at 1e-4 s, see `PERFORMANCE_REPORT.md`) |
| `max_records` | 200,000 | stored time samples per run; raise `record_interval` to fit |
| `max_wall_seconds` | 120 | wall-clock budget per run, checked during the step loop |
| `max_memory_mb` | 1024 | process peak resident memory, checked during the step loop |
| `max_pixels` | 1,000,000 | preview width x height |
| `max_image_side` | 2048 | preview width or height |
| `threads` | 1 | the only supported value; the kernel is single-threaded |

`python -m reality.control info` prints these values.

## Overriding

- CLI: `--limit NAME=VALUE` (repeatable) on `simulate run`, `simulate sweep-friction` and `preview frame`.
- API and MCP: a `limits` object with any of the names above.

Unknown names are refused. Values must be non-negative numbers.

## Error codes

Stable across releases; `OperationError.code` and the `error.code` field of every error document.

| code | meaning | typical cause |
|---|---|---|
| `invalid_argument` | an argument has the wrong type, range or value | `duration` < 0; unknown argument |
| `schema_error` | a scene or run document does not satisfy its schema | missing field; file is not JSON |
| `unsupported` | valid input that this release does not implement | more than one body in a run |
| `resource_limit` | a budget was exceeded | too many steps; image too large |
| `invalid_state` | the simulation reached a non-physical state and stopped | penetration above tolerance; non-finite state |
| `cancelled` | the caller cancelled the operation | reserved; not exposed in this release |
| `not_found` | a named body, plane, material, file or operation does not exist | misspelt id |

## What is checked during a run

- finite state at every check interval (every 500 steps);
- penetration of the sphere into a plane, against `1e-6 m`; a larger value stops the run with `invalid_state`;
- quaternion norm error, recorded in `checks.max_quaternion_norm_error`.

The checks are reported in every run document, so a run that finished has passed them.
