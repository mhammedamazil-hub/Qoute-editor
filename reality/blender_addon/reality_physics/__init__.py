"""Reality Physics: a Blender add-on that bakes PROJECT REALITY rigid-body motion into keyframes.

It adds a "Reality" tab to the 3D Viewport sidebar. It does not replace Blender's own systems (the rigid body world,
animation, rendering). The workflow:

1. Import meshes (File > Import > Wavefront OBJ, or the Reality tab's OBJ button).
2. Select an object and press "Mark as body" (spheres) or "Mark as plane" (horizontal planes, normal = object Z).
3. Set the custom properties in the Reality panel: material, velocity, body-frame angular velocity, friction,
   restitution, and an optional radius override.
4. Press "Bake motion". Each marked body gets location and rotation keyframes over the scene frame range.

Units: Blender's own (metres, seconds, Z up). Gravity is {0, 0, -9.80665} m/s^2, the standard value.
The motion is computed by the same solver as the headless tools (``reality.multibody``, ``reality.control``).

Limits: marked bodies must be spheres (the shape is checked against the bounding box) and must not be parented.
Baking overwrites existing location and rotation keyframes of marked bodies at the frames it writes. There are no
gameplay systems in this version.
"""

bl_info = {
    "name": "Reality Physics",
    "author": "PROJECT REALITY",
    "version": (0, 2, 0),
    "blender": (5, 0, 0),  # tested on Blender 5.0.1 (bpy) only
    "location": "View3D > Sidebar > Reality",
    "description": "Bake PROJECT REALITY sphere and plane contact motion into keyframes",
    "category": "Animation",
}

import os
import sys
from pathlib import Path

# The add-on needs the `reality` package. It lives in the repository's reality/src. Add it to the path when the add-on
# is used from the repository layout (reality/blender_addon/reality_physics/ -> reality/src).
_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import bpy  # noqa: E402
from bpy.props import StringProperty  # noqa: E402
from bpy.types import Operator, Panel  # noqa: E402
from mathutils import Vector  # noqa: E402

from reality_physics import scene_build as SB  # noqa: E402

_FILE_LABEL = "File"
_FILE_SUBTYPE = "FILE_PATH"
SPHERE_TOL = 1e-3  # relative: largest and smallest bounding-box side must agree to this fraction


def _sphere_radius(obj) -> float:
    override = obj.get("reality_radius")
    if override:
        return float(override)
    dims = [float(d) for d in obj.dimensions]
    big, small = max(dims), min(dims)
    if big <= 0.0:
        raise ValueError(f"{obj.name}: object has no size")
    if (big - small) > SPHERE_TOL * big:
        raise ValueError(f"{obj.name}: not a sphere (bounding box {dims}); set reality_radius to override")
    return big / 2.0


def _collect(scene):
    """Read marked objects into body and plane descriptions. Raises ValueError with a message on bad input."""
    bodies, planes, objects = [], [], []
    used: list = []
    for obj in scene.objects:
        if obj.get("reality_plane"):
            n = obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))
            n.normalize()
            loc = obj.matrix_world.translation
            planes.append({
                "id": SB.safe_id(obj.name, used), "normal": [n.x, n.y, n.z], "offset": n.dot(loc),
                "friction": float(obj.get("reality_friction", SB.DEFAULT_FRICTION)),
                "restitution": float(obj.get("reality_restitution", SB.DEFAULT_RESTITUTION)),
            })
            used.append(planes[-1]["id"])
        elif obj.get("reality_body"):
            if obj.type != "MESH":
                raise ValueError(f"{obj.name}: bodies must be mesh objects")
            if obj.parent is not None:
                raise ValueError(f"{obj.name}: unparent marked bodies before baking")
            bid = SB.safe_id(obj.name, used)
            used.append(bid)
            q = obj.matrix_world.to_quaternion()
            bodies.append({
                "id": bid, "radius": _sphere_radius(obj),
                "material": str(obj.get("reality_material", "steel")),
                "position": list(obj.matrix_world.translation),
                "quaternion": [q.w, q.x, q.y, q.z],
                "velocity": [float(x) for x in obj.get("reality_velocity", (0.0, 0.0, 0.0))],
                "omega": [float(x) for x in obj.get("reality_omega", (0.0, 0.0, 0.0))],
                "friction": float(obj.get("reality_friction", SB.DEFAULT_FRICTION)),
                "restitution": float(obj.get("reality_restitution", SB.DEFAULT_RESTITUTION)),
            })
            objects.append((bid, obj))
    return bodies, planes, objects


def bake(context) -> dict:
    """Run the solver over the scene frame range and write keyframes. Returns a summary dict."""
    scn = context.scene
    fps = scn.render.fps / scn.render.fps_base
    frames = scn.frame_end - scn.frame_start
    if frames < 1:
        raise ValueError("the scene frame range must span at least one frame")
    bodies, planes, objects = _collect(scn)
    if not bodies:
        raise ValueError("no bodies: mark at least one sphere with 'Mark as body'")
    out = SB.bake_scene(bodies, planes, frames=frames, fps=fps, frame_start=scn.frame_start)
    by_id = dict(objects)
    for sample in out["samples"]:
        f = sample["frame"]
        for bid, state in sample["bodies"].items():
            obj = by_id[bid]
            obj.location = state["position"]
            obj.rotation_mode = "QUATERNION"
            obj.rotation_quaternion = state["quaternion"]
            obj.keyframe_insert(data_path="location", frame=f)
            obj.keyframe_insert(data_path="rotation_quaternion", frame=f)
    final = out["result"]["final_state"]["bodies"]
    return {"bodies": len(bodies), "planes": len(planes), "frames": frames, "fps": fps,
            "substeps": out["timestep"]["substeps"], "dt": out["timestep"]["dt"],
            "max_penetration_m": out["result"]["checks"]["max_penetration_m"],
            "final_positions": {k: v["position"] for k, v in final.items()}}


_MARK_DEFAULTS = {"reality_material": "steel", "reality_velocity": [0.0, 0.0, 0.0],
                  "reality_omega": [0.0, 0.0, 0.0], "reality_friction": 0.5, "reality_restitution": 0.0}


class REALITY_OT_mark_body(Operator):
    bl_idname = "reality.mark_body"
    bl_label = "Mark as body"
    bl_description = "Make the active mesh a Reality sphere body"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "select a mesh object first")
            return {"CANCELLED"}
        try:
            _sphere_radius(obj)
        except ValueError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        obj["reality_plane"] = False
        obj["reality_body"] = True
        for key, value in _MARK_DEFAULTS.items():
            if key not in obj:
                obj[key] = value
        return {"FINISHED"}


class REALITY_OT_mark_plane(Operator):
    bl_idname = "reality.mark_plane"
    bl_label = "Mark as plane"
    bl_description = "Make the active object a horizontal plane; its +Z axis is the plane normal"

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            self.report({"ERROR"}, "select an object first")
            return {"CANCELLED"}
        obj["reality_body"] = False
        obj["reality_plane"] = True
        for key in ("reality_friction", "reality_restitution"):
            if key not in obj:
                obj[key] = _MARK_DEFAULTS[key]
        return {"FINISHED"}


class REALITY_OT_bake(Operator):
    bl_idname = "reality.bake"
    bl_label = "Bake motion"
    bl_description = "Simulate marked bodies over the scene frame range and key their location and rotation"

    def execute(self, context):
        try:
            summary = bake(context)
        except ValueError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        self.report({"INFO"}, f"baked {summary['bodies']} bodies over {summary['frames']} frames "
                              f"(dt {summary['dt']:.3e} s, max penetration {summary['max_penetration_m']:.2e} m)")
        return {"FINISHED"}


class REALITY_OT_import_obj(Operator):
    bl_idname = "reality.import_obj"
    bl_label = "Import OBJ"
    bl_description = "Import a Wavefront OBJ file (Blender's own importer)"

    filepath: StringProperty(name=_FILE_LABEL, subtype=_FILE_SUBTYPE)

    def execute(self, context):
        if not self.filepath or not os.path.isfile(self.filepath):
            self.report({"ERROR"}, "choose an existing .obj file")
            return {"CANCELLED"}
        bpy.ops.wm.obj_import(filepath=self.filepath)
        return {"FINISHED"}


class REALITY_PT_panel(Panel):
    bl_label = "Reality Physics"
    bl_idname = "REALITY_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Reality"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        layout.operator(REALITY_OT_mark_body.bl_idname, icon="MESH_UVSPHERE")
        layout.operator(REALITY_OT_mark_plane.bl_idname, icon="MESH_PLANE")
        if obj is not None:
            box = layout.box()
            box.label(text=f"{obj.name}: "
                      + ("plane" if obj.get("reality_plane") else "body" if obj.get("reality_body") else "unmarked"))
            if obj.get("reality_body"):
                for key in ("reality_material", "reality_velocity", "reality_omega",
                            "reality_friction", "reality_restitution"):
                    if key in obj:
                        box.prop(obj, f'["{key}"]', text=key.replace("reality_", ""))
                if "reality_radius" in obj:
                    box.prop(obj, '["reality_radius"]', text="radius override (m)")
        layout.separator()
        layout.operator(REALITY_OT_bake.bl_idname, icon="ANIM")
        layout.separator()
        layout.operator(REALITY_OT_import_obj.bl_idname, icon="IMPORT")


_CLASSES = (REALITY_OT_mark_body, REALITY_OT_mark_plane, REALITY_OT_bake, REALITY_OT_import_obj, REALITY_PT_panel)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
