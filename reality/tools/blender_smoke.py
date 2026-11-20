"""Headless smoke test of the Reality Physics add-on inside Blender's own Python (``bpy``).

Run with a Blender-compatible interpreter, for example ``python3.11 tools/blender_smoke.py``. It needs the ``bpy``
module (PyPI). It is not part of ``pytest``, because ``bpy`` is large and needs system graphics libraries.

What it checks:
- the add-on registers and its operators run from the UI context;
- objects are marked (sphere body, horizontal plane), the bake writes location and rotation keyframes;
- the keyframed positions equal the Python reference (``reality_physics.scene_build.bake_scene``) at the final frame;
- an OBJ export and re-import keeps the mesh.
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

reality_physics.unregister()
print("RESULT:", "ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(0 if not failures else 1)
