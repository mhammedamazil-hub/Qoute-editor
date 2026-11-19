"""Command-line interface: ``python -m reality.control <command> ...`` (see CLI_REFERENCE.md).

Conventions:
- stdout always holds one JSON document (results, summaries or an error object);
- exit code 0 on success, 1 on an operation error (``{"error": {...}}`` on stdout), 2 on a usage error;
- scene and run files are plain JSON; commands that edit a scene write the file in place unless --out is given.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from . import operations as ops
from . import scene as S
from .errors import OperationError


# ------------------------------------------------------------------ helpers
def _load(path: str, kind: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        raise OperationError("not_found", f"{kind} file {path!r} does not exist")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except json.JSONDecodeError as exc:
        raise OperationError("schema_error", f"{kind} file {path!r} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise OperationError("schema_error", f"{kind} file {path!r} must contain a JSON object")
    return doc


def _save(path: str, doc: Dict[str, Any]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, allow_nan=False)
        fh.write("\n")


def _emit(doc: Any) -> None:
    sys.stdout.write(json.dumps(doc, indent=2, allow_nan=False) + "\n")


def _args(**kwargs: Any) -> Dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


def _limits(items: Optional[List[str]]) -> Optional[Dict[str, float]]:
    if not items:
        return None
    out: Dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise OperationError("invalid_argument", f"limit {item!r} must look like name=value")
        key, value = item.split("=", 1)
        try:
            out[key.strip()] = float(value)
        except ValueError as exc:
            raise OperationError("invalid_argument", f"limit {key} value {value!r} is not a number") from exc
    return out


def _scene_summary(doc: Dict[str, Any], path: Optional[str]) -> Dict[str, Any]:
    v = S.validate(doc)
    return {"written": path, "name": doc.get("name"), "bodies": [b["id"] for b in doc.get("bodies", [])],
            "planes": [p["id"] for p in doc.get("planes", [])], "contacts": len(doc.get("contacts", [])),
            "valid": v["valid"], "errors": v["errors"], "warnings": v["warnings"]}


def _scene_edit(path: str, op: str, out: Optional[str], **kwargs: Any) -> int:
    doc = _load(path, "scene")
    new = ops.call(op, {"scene": doc, **kwargs})
    target = out or path
    _save(target, new)
    _emit(_scene_summary(new, target))
    return 0


# ----------------------------------------------------------------- handlers
def _cmd_info(_args_ns) -> int:
    _emit(ops.call("system.info"))
    return 0


def _cmd_ops(args_ns) -> int:
    listing = ops.list_operations()
    if args_ns.name:
        match = [o for o in listing if o["name"] == args_ns.name]
        if not match:
            raise OperationError("not_found", f"no operation {args_ns.name!r}", {"available": [o["name"] for o in listing]})
        _emit(match[0])
    else:
        _emit([{"name": o["name"], "description": o["description"]} for o in listing])
    return 0


def _cmd_call(args_ns) -> int:
    raw = args_ns.args
    if raw.startswith("@"):
        with open(raw[1:], "r", encoding="utf-8") as fh:
            raw = fh.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise OperationError("invalid_argument", f"--args is not valid JSON: {exc}") from exc
    _emit(ops.call(args_ns.operation, payload))
    return 0


# scene
def _cmd_scene_new(a) -> int:
    doc = ops.call("scene.create", _args(name=a.name, gravity=a.gravity))
    _save(a.file, doc)
    _emit(_scene_summary(doc, a.file))
    return 0


def _cmd_scene_add_sphere(a) -> int:
    kwargs = _args(id=a.id, radius=a.radius, material=a.material, mass=a.mass, density=a.density,
                   position=a.position, velocity=a.velocity, omega=a.omega)
    return _scene_edit(a.file, "scene.add_sphere", a.out, **kwargs)


def _cmd_scene_add_plane(a) -> int:
    kwargs = _args(id=a.id, normal=a.normal, offset=a.offset)
    return _scene_edit(a.file, "scene.add_plane", a.out, **kwargs)


def _cmd_scene_set_body(a) -> int:
    fields = _args(radius=a.radius, material=a.material, mass=a.mass, density=a.density,
                   position=a.position, velocity=a.velocity, omega=a.omega)
    return _scene_edit(a.file, "scene.set_body", a.out, id=a.id, fields=fields)


def _cmd_scene_set_gravity(a) -> int:
    return _scene_edit(a.file, "scene.set_gravity", a.out, gravity=a.gravity)


def _cmd_scene_set_contact(a) -> int:
    kwargs = _args(body=a.body, plane=a.plane, friction=a.friction, restitution=a.restitution)
    return _scene_edit(a.file, "scene.set_contact", a.out, **kwargs)


def _cmd_scene_remove(a) -> int:
    return _scene_edit(a.file, "scene.remove", a.out, id=a.id)


def _cmd_scene_validate(a) -> int:
    doc = _load(a.file, "scene")
    report = ops.call("scene.validate", {"scene": doc})
    _emit(report)
    return 0 if report["valid"] else 1


def _cmd_scene_describe(a) -> int:
    _emit(ops.call("scene.describe", {"scene": _load(a.file, "scene")}))
    return 0


def _cmd_scene_materials(_a) -> int:
    _emit(ops.call("scene.materials"))
    return 0


# simulate
def _cmd_simulate_run(a) -> int:
    scene_doc = _load(a.scene, "scene")
    checkpoint = _load(a.checkpoint, "checkpoint") if a.checkpoint else None
    if checkpoint is not None and "final_state" in checkpoint:
        checkpoint = checkpoint["final_state"]
    kwargs = _args(scene=scene_doc, duration=a.duration, dt=a.dt, record_interval=a.record_interval,
                   checkpoint=checkpoint, limits=_limits(a.limit))
    result = ops.call("simulate.run", kwargs)
    if a.out:
        _save(a.out, result)
        _emit({"written": a.out, "summary": ops.call("inspect.summary", {"result": result}),
               "diagnostics": result["diagnostics"], "scene_sha256": result["scene_sha256"]})
    else:
        _emit(result)
    return 0


def _cmd_simulate_sweep(a) -> int:
    kwargs = _args(scene=_load(a.scene, "scene"), body=a.body, plane=a.plane, friction_values=a.values,
                   duration=a.duration, dt=a.dt, record_interval=a.record_interval, limits=_limits(a.limit))
    _emit(ops.call("simulate.sweep_friction", kwargs))
    return 0


# inspect
def _cmd_inspect_body(a) -> int:
    _emit(ops.call("inspect.body", {"result": _load(a.run, "run"), "body": a.body, "index": a.index}))
    return 0


def _cmd_inspect_scene(a) -> int:
    _emit(ops.call("inspect.scene", {"result": _load(a.run, "run"), "index": a.index}))
    return 0


def _cmd_inspect_series(a) -> int:
    kwargs = _args(result=_load(a.run, "run"), body=a.body, fields=a.fields)
    _emit(ops.call("inspect.series", kwargs))
    return 0


def _cmd_inspect_rolling(a) -> int:
    _emit(ops.call("inspect.rolling_onset", {"result": _load(a.run, "run"), "body": a.body}))
    return 0


def _cmd_inspect_summary(a) -> int:
    _emit(ops.call("inspect.summary", {"result": _load(a.run, "run")}))
    return 0


# preview
def _cmd_preview_frame(a) -> int:
    kwargs = _args(result=_load(a.run, "run"), index=a.index, width=a.width, height=a.height,
                   azimuth_deg=a.azimuth, elevation_deg=a.elevation, out_path=a.out,
                   show_velocity=not a.no_velocity, show_gravity=not a.no_gravity,
                   show_contacts=not a.no_contacts, include_base64=a.base64 or None,
                   limits=_limits(a.limit))
    out = ops.call("preview.frame", kwargs)
    if not a.base64:
        out.pop("png_base64", None)
        out.pop("mime_type", None)
    _emit(out)
    return 0


# experiment / export / validate
def _cmd_compare(a) -> int:
    _emit(ops.call("experiment.compare", {"a": _load(a.run_a, "run"), "b": _load(a.run_b, "run"), "body": a.body}))
    return 0


def _cmd_export(a) -> int:
    kwargs = _args(out_dir=a.out_dir, scene=_load(a.scene, "scene"), result=_load(a.run, "run"),
                   preview_path=a.preview)
    _emit(ops.call("export.bundle", kwargs))
    return 0


def _cmd_validate(a) -> int:
    report = ops.call("validate.run", {"domain": a.domain})
    if a.out:
        _save(a.out, report)
    _emit({k: v for k, v in report.items() if k != "cases"} |
          {"failing": [c["case_id"] for c in report["cases"] if not c["passed"]], "written": a.out})
    return 0 if report["all_passed"] else 1


def _cmd_mcp(_a) -> int:
    from .mcp import serve
    return serve()


# ------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m reality.control",
                                description="PROJECT REALITY headless control CLI (JSON on stdout).")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="package version, default limits, interfaces").set_defaults(func=_cmd_info)
    po = sub.add_parser("ops", help="list operations, or show one operation's input schema")
    po.add_argument("name", nargs="?")
    po.set_defaults(func=_cmd_ops)
    pc = sub.add_parser("call", help="run any operation with JSON arguments (inline or @file)")
    pc.add_argument("operation")
    pc.add_argument("--args", default="{}", help="JSON object, or @path/to/file.json")
    pc.set_defaults(func=_cmd_call)

    scene = sub.add_parser("scene", help="create and edit scene files").add_subparsers(dest="scene_cmd", required=True)
    s = scene.add_parser("new")
    s.add_argument("file")
    s.add_argument("--name", required=True)
    s.add_argument("--gravity", type=float, nargs=3, metavar=("GX", "GY", "GZ"))
    s.set_defaults(func=_cmd_scene_new)

    s = scene.add_parser("add-sphere")
    s.add_argument("file")
    s.add_argument("--id", required=True)
    s.add_argument("--radius", type=float, required=True, help="metres")
    grp = s.add_mutually_exclusive_group(required=True)
    grp.add_argument("--material")
    grp.add_argument("--mass", type=float, help="kg")
    grp.add_argument("--density", type=float, help="kg/m^3")
    s.add_argument("--position", type=float, nargs=3)
    s.add_argument("--velocity", type=float, nargs=3)
    s.add_argument("--omega", type=float, nargs=3)
    s.add_argument("--out")
    s.set_defaults(func=_cmd_scene_add_sphere)

    s = scene.add_parser("add-plane")
    s.add_argument("file")
    s.add_argument("--id", required=True)
    s.add_argument("--normal", type=float, nargs=3)
    s.add_argument("--offset", type=float)
    s.add_argument("--out")
    s.set_defaults(func=_cmd_scene_add_plane)

    s = scene.add_parser("set-body")
    s.add_argument("file")
    s.add_argument("--id", required=True)
    s.add_argument("--radius", type=float)
    s.add_argument("--material")
    s.add_argument("--mass", type=float)
    s.add_argument("--density", type=float)
    s.add_argument("--position", type=float, nargs=3)
    s.add_argument("--velocity", type=float, nargs=3)
    s.add_argument("--omega", type=float, nargs=3)
    s.add_argument("--out")
    s.set_defaults(func=_cmd_scene_set_body)

    s = scene.add_parser("set-gravity")
    s.add_argument("file")
    s.add_argument("gravity", type=float, nargs=3, metavar=("GX", "GY", "GZ"))
    s.add_argument("--out")
    s.set_defaults(func=_cmd_scene_set_gravity)

    s = scene.add_parser("set-contact")
    s.add_argument("file")
    s.add_argument("--body", required=True)
    s.add_argument("--plane", required=True)
    s.add_argument("--friction", type=float, required=True)
    s.add_argument("--restitution", type=float)
    s.add_argument("--out")
    s.set_defaults(func=_cmd_scene_set_contact)

    s = scene.add_parser("remove")
    s.add_argument("file")
    s.add_argument("--id", required=True)
    s.add_argument("--out")
    s.set_defaults(func=_cmd_scene_remove)

    s = scene.add_parser("validate")
    s.add_argument("file")
    s.set_defaults(func=_cmd_scene_validate)

    s = scene.add_parser("describe")
    s.add_argument("file")
    s.set_defaults(func=_cmd_scene_describe)

    scene.add_parser("materials").set_defaults(func=_cmd_scene_materials)

    sim = sub.add_parser("simulate", help="run scenes headless").add_subparsers(dest="sim_cmd", required=True)
    s = sim.add_parser("run")
    s.add_argument("scene")
    s.add_argument("--duration", type=float, required=True, help="seconds")
    s.add_argument("--dt", type=float, help="requested step (default 1e-4 s)")
    s.add_argument("--record-interval", type=float, dest="record_interval", help="default 0.01 s")
    s.add_argument("--checkpoint", help="a run file or checkpoint file of the same scene")
    s.add_argument("--out", help="write the full run document here; otherwise print it")
    s.add_argument("--limit", action="append", metavar="NAME=VALUE", help="resource limit, see RESOURCE_LIMITS.md")
    s.set_defaults(func=_cmd_simulate_run)

    s = sim.add_parser("sweep-friction")
    s.add_argument("scene")
    s.add_argument("--body", required=True)
    s.add_argument("--plane", required=True)
    s.add_argument("--values", type=float, nargs="+", required=True)
    s.add_argument("--duration", type=float, required=True)
    s.add_argument("--dt", type=float)
    s.add_argument("--record-interval", type=float, dest="record_interval")
    s.add_argument("--limit", action="append", metavar="NAME=VALUE")
    s.set_defaults(func=_cmd_simulate_sweep)

    ins = sub.add_parser("inspect", help="read run files").add_subparsers(dest="inspect_cmd", required=True)
    s = ins.add_parser("body")
    s.add_argument("run")
    s.add_argument("--body", required=True)
    s.add_argument("--index", type=int, default=-1)
    s.set_defaults(func=_cmd_inspect_body)
    s = ins.add_parser("scene")
    s.add_argument("run")
    s.add_argument("--index", type=int, default=-1)
    s.set_defaults(func=_cmd_inspect_scene)
    s = ins.add_parser("series")
    s.add_argument("run")
    s.add_argument("--body", required=True)
    s.add_argument("--fields", nargs="+")
    s.set_defaults(func=_cmd_inspect_series)
    s = ins.add_parser("rolling-onset")
    s.add_argument("run")
    s.add_argument("--body", required=True)
    s.set_defaults(func=_cmd_inspect_rolling)
    s = ins.add_parser("summary")
    s.add_argument("run")
    s.set_defaults(func=_cmd_inspect_summary)

    pv = sub.add_parser("preview", help="render images").add_subparsers(dest="preview_cmd", required=True)
    s = pv.add_parser("frame")
    s.add_argument("run")
    s.add_argument("--out", required=True, help="PNG path to write")
    s.add_argument("--index", type=int, default=-1)
    s.add_argument("--width", type=int, default=480)
    s.add_argument("--height", type=int, default=320)
    s.add_argument("--azimuth", type=float, default=-35.0)
    s.add_argument("--elevation", type=float, default=20.0)
    s.add_argument("--no-velocity", action="store_true")
    s.add_argument("--no-gravity", action="store_true")
    s.add_argument("--no-contacts", action="store_true")
    s.add_argument("--base64", action="store_true", help="also print the PNG as base64 in the JSON")
    s.add_argument("--limit", action="append", metavar="NAME=VALUE")
    s.set_defaults(func=_cmd_preview_frame)

    s = sub.add_parser("compare", help="compare two run files")
    s.add_argument("run_a")
    s.add_argument("run_b")
    s.add_argument("--body", required=True)
    s.set_defaults(func=_cmd_compare)

    s = sub.add_parser("export", help="write a bundle directory")
    s.add_argument("--out-dir", required=True)
    s.add_argument("--scene", required=True)
    s.add_argument("--run", required=True)
    s.add_argument("--preview", help="an existing PNG to copy in")
    s.set_defaults(func=_cmd_export)

    s = sub.add_parser("validate", help="run validation cases")
    s.add_argument("--domain", default="all", help="all, sim, or a registry domain name")
    s.add_argument("--out", help="write the full report JSON here")
    s.set_defaults(func=_cmd_validate)

    sub.add_parser("mcp", help="serve operations over MCP (stdio JSON-RPC)").set_defaults(func=_cmd_mcp)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as exc:  # argparse already printed usage to stderr
        return 2 if exc.code not in (0, None) else 0
    try:
        return int(ns.func(ns) or 0)
    except OperationError as exc:
        _emit(exc.to_dict())
        return 1
