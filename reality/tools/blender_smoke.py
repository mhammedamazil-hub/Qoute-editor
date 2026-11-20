"""Headless smoke test of the Reality Physics add-on inside Blender's own Python (``bpy``).

Run with a Blender-compatible interpreter, for example ``python3.11 tools/blender_smoke.py``. It needs the ``bpy``
module (PyPI). It is not part of ``pytest``, because ``bpy`` is large and needs system graphics libraries.

What it checks:
- the add-on registers and its operators run from the UI context;
- objects are marked (sphere body, horizontal plane), the bake writes location and rotation keyframes;
- the keyframed positions equal the Python reference (``reality_physics.scene_build.bake_scene``) at the final frame;
- an OBJ export and re-import keeps the mesh.
Phase 6 (colliders), after the checks above:
- an OBJ import through the add-on's own operator, then "Mark as collider" with the triangle-mesh shape (static);
- a sphere bakes onto the mesh floor and rests at its radius; a static box and the mesh are not keyed;
- a dynamic box bakes onto a plane and rests at its half height; a rotated sphere bakes (float32 rotation);
- refusals: a mirrored object, an off-centre origin, and a dynamic box with a mesh floor (box-mesh is not implemented).
Exit code 0 means all checks passed. The script prints every check.
"""

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(HERE / "blender_addon"))

import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402

import reality_physics  # noqa: E402
from reality_physics import scene_build as SB  # noqa: E402

failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


bpy.ops.wm.read_factory_settings(use_empty=True)
reality_physics.register()
scn = bpy.context.scene
scn.render.fps = 24
scn.render.fps_base = 1.0
scn.frame_start = 1
scn.frame_end = 49  # 48 frames = 2 s

bpy.ops.mesh.primitive_plane_add(size=10.0, location=(0.0, 0.0, 0.0))
floor = bpy.context.active_object
floor.name = "Floor"
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.05, location=(0.0, 0.0, 2.0))
ball = bpy.context.active_object
ball.name = "Sphere.001"

bpy.context.view_layer.objects.active = floor
r = bpy.ops.reality.mark_plane()
check("mark_plane returns FINISHED", r == {"FINISHED"}, str(r))
check("plane flag set", bool(floor.get("reality_plane")))

bpy.context.view_layer.objects.active = ball
r = bpy.ops.reality.mark_body()
check("mark_body returns FINISHED", r == {"FINISHED"}, str(r))
check("body flag set", bool(ball.get("reality_body")))
ball["reality_restitution"] = 0.6
floor["reality_restitution"] = 0.6

r = bpy.ops.reality.bake()
check("bake returns FINISHED", r == {"FINISHED"}, str(r))

ad = ball.animation_data
action = ad.action if ad else None
check("ball has an action", action is not None)


def _fcurves(obj):
    """All F-curves of an object's action. Blender 5 keeps them in layers > strips > channelbag(slot)."""
    act = obj.animation_data.action
    if hasattr(act, "fcurves"):  # Blender before layered actions
        return list(act.fcurves)
    strip = act.layers[0].strips[0]
    return list(strip.channelbag(obj.animation_data.action_slot).fcurves)


if action is not None:
    curves = _fcurves(ball)
    loc_curves = [c for c in curves if c.data_path == "location"]
    rot_curves = [c for c in curves if c.data_path == "rotation_quaternion"]
    check("location curves x,y,z", len(loc_curves) == 3, str(len(loc_curves)))
    check("rotation curves w,x,y,z", len(rot_curves) == 4, str(len(rot_curves)))
    frames = sorted({int(round(k.co[0])) for c in loc_curves for k in c.keyframe_points})
    check("keys on frames 1..49", frames == list(range(1, 50)), f"{frames[:3]}..{frames[-3:]} n={len(frames)}")

# Python reference with the same inputs (initial state = the ball's state before the bake: x=0,y=0,z=2)
ref = SB.bake_scene(
    [{"id": "Sphere_001", "radius": 0.05, "material": "steel", "position": [0.0, 0.0, 2.0],
      "quaternion": [1.0, 0.0, 0.0, 0.0], "velocity": [0.0, 0.0, 0.0], "omega": [0.0, 0.0, 0.0],
      "friction": 0.5, "restitution": 0.6}],
    [{"id": "Floor", "normal": [0.0, 0.0, 1.0], "offset": 0.0, "friction": 0.5, "restitution": 0.6}],
    frames=48, fps=24.0, frame_start=1)
scn.frame_set(49)
got = ball.matrix_world.translation
want = ref["samples"][-1]["bodies"]["Sphere_001"]["position"]
err = max(abs(a - b) for a, b in zip(got, want))
check("final position equals Python reference", err < 1e-5, f"max |diff| = {err:.2e} m, got z={got.z:.4f}")
scn.frame_set(1)
check("frame 1 starts at the object's initial height", abs(ball.matrix_world.translation.z - 2.0) < 1e-6)

tmp = tempfile.mkdtemp(prefix="reality_obj_")
obj_path = os.path.join(tmp, "ball.obj")
bpy.ops.object.select_all(action="DESELECT")
ball.select_set(True)
bpy.context.view_layer.objects.active = ball
bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True)
check("OBJ exported", os.path.isfile(obj_path) and os.path.getsize(obj_path) > 0)
verts_before = len(ball.data.vertices)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
bpy.ops.wm.obj_import(filepath=obj_path)
imported = [o for o in bpy.context.scene.objects if o.type == "MESH"]
check("OBJ re-imported as a mesh", len(imported) == 1)
if imported:
    check("OBJ vertex count kept", len(imported[0].data.vertices) == verts_before,
          f"{len(imported[0].data.vertices)} vs {verts_before}")


# ---------------------------------------------------------------- Phase 6: colliders (boxes, static meshes, static bodies)
def _clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def _select(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _operator_refused(call, needle):
    """A Blender operator that reports ERROR raises RuntimeError when called from Python. The check passes only
    when the refusal carries the expected reason; any other outcome fails."""
    try:
        result = call()
    except RuntimeError as err:
        return needle in str(err)
    return result == {"CANCELLED"} and False  # a refusal must raise with its reason, not just cancel


def _keyed(obj):
    """True when the object has location and rotation F-curves in its action."""
    if obj.animation_data is None or obj.animation_data.action is None:
        return False
    curves = _fcurves(obj)
    return (any(c.data_path == "location" for c in curves)
            and any(c.data_path == "rotation_quaternion" for c in curves))


_clear()
tmp6 = tempfile.mkdtemp(prefix="reality_colliders_")
bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 0.0))
ground_src = bpy.context.active_object
ground_src.name = "GroundSrc"
ground_path = os.path.join(tmp6, "ground.obj")
_select(ground_src)
bpy.ops.wm.obj_export(filepath=ground_path, export_selected_objects=True)
_clear()
r = bpy.ops.reality.import_obj(filepath=ground_path)
check("add-on OBJ import operator returns FINISHED", r == {"FINISHED"}, str(r))
imported = [o for o in scn.objects if o.type == "MESH"]
check("OBJ import gives one mesh", len(imported) == 1, str(len(imported)))
ground = imported[0]
_select(ground)
r = bpy.ops.reality.mark_collider(shape="MESH")
check("mark_collider MESH returns FINISHED", r == {"FINISHED"}, str(r))
check("mesh flags set (static)", bool(ground.get("reality_mesh")) and bool(ground.get("reality_static")))

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.05, location=(0.0, 0.0, 0.5))
ball = bpy.context.active_object
ball.name = "Ball"
_select(ball)
r = bpy.ops.reality.mark_body()
check("mark_body on the ball returns FINISHED", r == {"FINISHED"}, str(r))

bpy.ops.mesh.primitive_cube_add(size=0.2, location=(1.0, 0.0, 0.1))
pillar = bpy.context.active_object
pillar.name = "Pillar"
_select(pillar)
r = bpy.ops.reality.mark_collider(shape="BOX", static=True)
check("mark_collider BOX static returns FINISHED", r == {"FINISHED"}, str(r))

summary = reality_physics.bake(bpy.context)
check("mesh bake: 1 dynamic body, 1 static body, 1 mesh, schema v3",
      (summary["keyed"], summary["static"], summary["meshes"], summary["schema_version"]) == (1, 1, 1, 3),
      str(summary))
check("mesh bake: ball keyed, static pillar and mesh not keyed",
      _keyed(ball) and not _keyed(pillar) and not _keyed(ground))
scn.frame_set(49)
z_ball = ball.matrix_world.translation.z
check("ball rests on the mesh at its radius (0.05 m)", abs(z_ball - 0.05) < 1e-4, f"z = {z_ball:.6f}")
check("max penetration within the kernel tolerance", summary["max_penetration_m"] <= 1e-6,
      f"{summary['max_penetration_m']:.2e} m")
scn.frame_set(1)

_clear()
bpy.ops.mesh.primitive_plane_add(size=10.0, location=(0.0, 0.0, 0.0))
floor6 = bpy.context.active_object
floor6.name = "Floor"
_select(floor6)
check("mark_plane returns FINISHED", bpy.ops.reality.mark_plane() == {"FINISHED"})
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.0, 0.0, 0.5))
crate = bpy.context.active_object
crate.name = "Crate"
_select(crate)
check("mark_collider BOX dynamic returns FINISHED",
      bpy.ops.reality.mark_collider(shape="BOX", static=False) == {"FINISHED"})
r = bpy.ops.reality.bake()
check("box bake returns FINISHED", r == {"FINISHED"}, str(r))
check("box is keyed", _keyed(crate))
scn.frame_set(49)
z_crate = crate.matrix_world.translation.z
check("box rests on the plane at its half height (0.1 m)", abs(z_crate - 0.1) < 1e-4, f"z = {z_crate:.6f}")
scn.frame_set(1)

_clear()
bpy.ops.mesh.primitive_plane_add(size=10.0, location=(0.0, 0.0, 0.0))
_select(bpy.context.active_object)
bpy.ops.reality.mark_plane()
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.05, location=(0.0, 0.0, 0.5))
rotated = bpy.context.active_object
rotated.name = "Rotated"
rotated.rotation_euler = (0.3, 0.5, 0.2)  # float32 rotation: the case that the unit-quaternion fix covers
bpy.context.view_layer.update()
_select(rotated)
bpy.ops.reality.mark_body()
r = bpy.ops.reality.bake()
check("rotated sphere bakes (float32 quaternion normalised)", r == {"FINISHED"}, str(r))
scn.frame_set(49)
check("rotated sphere rests on the plane at its radius", abs(rotated.matrix_world.translation.z - 0.05) < 1e-4,
      f"z = {rotated.matrix_world.translation.z:.6f}")
scn.frame_set(1)

_clear()
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.0, 0.0, 0.5))
mirror = bpy.context.active_object
mirror.name = "Mirror"
mirror.scale = (-1.0, 1.0, 1.0)
bpy.context.view_layer.update()
_select(mirror)
check("mirrored box is refused with the mirror reason", _operator_refused(
    lambda: bpy.ops.reality.mark_collider(shape="BOX", static=False), "mirrored"))

_clear()
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.0, 0.0, 0.5))
off = bpy.context.active_object
off.name = "OffCentre"
off.data.transform(Matrix.Translation((0.3, 0.0, 0.0)))
off.data.update()
bpy.context.view_layer.update()
_select(off)
check("off-centre origin is refused with the origin reason", _operator_refused(
    lambda: bpy.ops.reality.mark_collider(shape="BOX", static=False), "geometric centre"))

_clear()
bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 0.0))
mfloor = bpy.context.active_object
mfloor.name = "MeshFloor"
_select(mfloor)
bpy.ops.reality.mark_collider(shape="MESH")
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.0, 0.0, 0.5))
bx = bpy.context.active_object
bx.name = "BoxOnMesh"
_select(bx)
bpy.ops.reality.mark_collider(shape="BOX", static=False)
refused = False
try:
    reality_physics.bake(bpy.context)
except ValueError as err:
    refused = "box-mesh" in str(err)
check("dynamic box with a mesh floor is refused with the box-mesh reason", refused)

reality_physics.unregister()
print("RESULT:", "ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(0 if not failures else 1)
