"""Reality Physics: a Blender add-on that bakes PROJECT REALITY rigid-body motion into keyframes.

It adds a "Reality" tab to the 3D Viewport sidebar. It does not replace Blender's own systems (the rigid body world,
animation, rendering). The workflow:

1. Import meshes (File > Import > Wavefront OBJ, or the Reality tab's OBJ button).
2. Select an object and mark it: "Mark as body" (sphere), "Mark as plane" (horizontal plane, normal = object Z), or
   "Mark as collider" (sphere, box or static triangle mesh, dynamic or static).
3. Set the custom properties in the Reality panel: material, velocity, body-frame angular velocity, friction,
   restitution, and an optional radius override.
4. Press "Bake motion". Each dynamic body gets location and rotation keyframes over the scene frame range. Static
   bodies and meshes are not keyed.

Units: Blender's own (metres, seconds, Z up). Gravity is {0, 0, -9.80665} m/s^2, the standard value.
The motion is computed by the headless kernel (``simulate.multibody``), never by Blender's rigid body world.

Limits (checked before baking, with a message):
- Sphere and box bodies must have their origin at the geometric centre (Object > Set Origin > Origin to Geometry),
  because the keyframes move the origin. Mirrored objects (negative scale) and sheared transforms are refused; apply
  the transform first. Parented bodies are refused. Modifiers must be applied before a mesh collider is marked.
- Triangle mesh colliders are static only.
- Box-box and box-mesh contacts are not implemented in the kernel; a bake that needs one is refused.
- Baking overwrites existing location and rotation keyframes of dynamic bodies at the frames it writes.
- There are no gameplay systems in this version.
"""

bl_info = {
    "name": "Reality Physics",
    "author": "PROJECT REALITY",
    "version": (0, 3, 0),
    "blender": (5, 0, 0),  # tested on Blender 5.0.1 (bpy) only
    "location": "View3D > Sidebar > Reality",
    "description": "Bake PROJECT REALITY sphere, box and mesh contact motion into keyframes",
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
from bpy.props import BoolProperty, EnumProperty, StringProperty  # noqa: E402
from bpy.types import Operator, Panel  # noqa: E402
from mathutils import Vector  # noqa: E402

from reality_physics import scene_build as SB  # noqa: E402

_FILE_LABEL = "File"
_FILE_SUBTYPE = "FILE_PATH"
SPHERE_TOL = 1e-3  # relative: largest and smallest bounding-box side must agree to this fraction
CENTRE_TOL = 1e-4  # relative: the bounding-box centre must lie this close to the origin (fraction of the largest side)
SHEAR_TOL = 1e-6   # the matrix must equal rotation times scale to this tolerance
# Literals used by the Blender property declarations live here: pyflakes reads string literals inside class-body
# annotations as forward references, which is a false positive for these properties.
_SHAPE_LABEL = "Shape"
_SHAPE_DEFAULT = "SPHERE"
_SHAPE_ITEMS = (
    ("SPHERE", "Sphere", "A sphere body"),
    ("BOX", "Box", "A box body, half-extents from the object size"),
    ("MESH", "Triangle mesh", "A static triangle mesh"),
)
_STATIC_LABEL = "Static"
_STATIC_DESC = "The object does not move (no keyframes)"


def _check_transform(obj) -> None:
    """Refuse mirrored, sheared or parented transforms. Raises ValueError with a message."""
    if obj.parent is not None:
        raise ValueError(f"{obj.name}: unparent marked objects before baking")
    m = obj.matrix_world
    if m.determinant() < 0.0:
        raise ValueError(f"{obj.name}: mirrored object (negative scale); apply the scale first (Ctrl+A)")
    loc, rot, scale = m.decompose()
    rebuilt = rot.to_matrix().to_4x4()
    for i in range(3):
        rebuilt.col[i] = rebuilt.col[i] * scale[i]
    for i in range(3):
        for j in range(3):
            if abs(rebuilt[i][j] - m[i][j]) > SHEAR_TOL * max(1.0, abs(m[i][j])):
                raise ValueError(f"{obj.name}: sheared transform; apply the transform first (Ctrl+A)")


def _origin_at_centre(obj) -> None:
    """A sphere or box body is keyed by its origin, so the origin must be the centre of its bounding box."""
    corners = [Vector(c) for c in obj.bound_box]
    centre = sum(corners, Vector((0.0, 0.0, 0.0))) / 8.0
    size = max(float(d) for d in obj.dimensions)
    if centre.length > CENTRE_TOL * max(size, 1e-12):
        raise ValueError(f"{obj.name}: origin is not at the geometric centre; "
                         f"use Object > Set Origin > Origin to Geometry")


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


def _box_half_extents(obj) -> list:
    dims = [float(d) for d in obj.dimensions]
    if min(dims) <= 0.0:
        raise ValueError(f"{obj.name}: box has no size")
    return [d / 2.0 for d in dims]


def _mesh_collider(obj):
    """Vertices (already scaled, in the mesh frame), triangles, and the pose of a triangle-mesh collider."""
    if obj.type != "MESH":
        raise ValueError(f"{obj.name}: triangle colliders must be mesh objects")
    if len(obj.modifiers) > 0:  # the kernel reads the mesh data, not the evaluated mesh
        raise ValueError(f"{obj.name}: apply the modifiers before marking a triangle collider")
    _check_transform(obj)
    loc, rot, scale = obj.matrix_world.decompose()
    me = obj.data
    me.calc_loop_triangles()
    vertices = [[v.co.x * scale.x, v.co.y * scale.y, v.co.z * scale.z] for v in me.vertices]
    triangles = [[int(i) for i in tri.vertices] for tri in me.loop_triangles]
    if not triangles:
        raise ValueError(f"{obj.name}: the mesh has no triangles")
    return vertices, triangles, [loc.x, loc.y, loc.z], SB.unit_quaternion([rot.w, rot.x, rot.y, rot.z])


def _is_static(obj) -> bool:
    return bool(obj.get("reality_static", False))


def _collect(scene):
    """Read marked objects into the descriptions the kernel needs.

    Returns (bodies, planes, meshes, keyed) where ``keyed`` maps the id of each dynamic body to its Blender object.
    Raises ValueError with a message on bad input.
    """
    bodies, planes, meshes, keyed = [], [], [], {}
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
        elif obj.get("reality_mesh"):
            vertices, triangles, pos, quat = _mesh_collider(obj)
            mid = SB.safe_id(obj.name, used)
            used.append(mid)
            meshes.append({
                "id": mid, "vertices": vertices, "triangles": triangles, "position": pos, "quaternion": quat,
                "friction": float(obj.get("reality_friction", SB.DEFAULT_FRICTION)),
                "restitution": float(obj.get("reality_restitution", SB.DEFAULT_RESTITUTION)),
            })
        elif obj.get("reality_body"):
            shape = str(obj.get("reality_shape", "sphere"))
            if obj.type != "MESH":
                raise ValueError(f"{obj.name}: bodies must be mesh objects")
            _check_transform(obj)
            if shape == "box":
                half = _box_half_extents(obj)
            elif shape == "sphere":
                half = None
                radius = _sphere_radius(obj)
            else:
                raise ValueError(f"{obj.name}: unknown body shape {shape!r}")
            _origin_at_centre(obj)
            static = _is_static(obj)
            bid = SB.safe_id(obj.name, used)
            used.append(bid)
            q = obj.matrix_world.to_quaternion()
            entry = {
                "id": bid, "shape": shape, "static": static,
                "position": list(obj.matrix_world.translation),
                "quaternion": SB.unit_quaternion([q.w, q.x, q.y, q.z]),
                "friction": float(obj.get("reality_friction", SB.DEFAULT_FRICTION)),
                "restitution": float(obj.get("reality_restitution", SB.DEFAULT_RESTITUTION)),
            }
            if shape == "box":
                entry["half_extents"] = half
            else:
                entry["radius"] = radius
            if static:
                if any(abs(float(x)) > 0.0 for x in obj.get("reality_velocity", (0.0, 0.0, 0.0))) or \
                        any(abs(float(x)) > 0.0 for x in obj.get("reality_omega", (0.0, 0.0, 0.0))):
                    raise ValueError(f"{obj.name}: a static body has zero velocity and omega; reset them")
                entry["velocity"] = [0.0, 0.0, 0.0]
                entry["omega"] = [0.0, 0.0, 0.0]
            else:
                entry["material"] = str(obj.get("reality_material", "steel"))
                entry["velocity"] = [float(x) for x in obj.get("reality_velocity", (0.0, 0.0, 0.0))]
                entry["omega"] = [float(x) for x in obj.get("reality_omega", (0.0, 0.0, 0.0))]
                keyed[bid] = obj
            bodies.append(entry)
    return bodies, planes, meshes, keyed


def bake(context) -> dict:
    """Run the kernel over the scene frame range and write keyframes. Returns a summary dict."""
    scn = context.scene
    fps = scn.render.fps / scn.render.fps_base
    frames = scn.frame_end - scn.frame_start
    if frames < 1:
        raise ValueError("the scene frame range must span at least one frame")
    bodies, planes, meshes, keyed = _collect(scn)
    if not bodies:
        raise ValueError("no bodies: mark at least one sphere or box with 'Mark as body' or 'Mark as collider'")
    if not keyed:
        raise ValueError("no dynamic bodies: every marked body is static, so there is nothing to bake")
    out = SB.bake_scene(bodies, planes, frames=frames, fps=fps, frame_start=scn.frame_start, meshes=meshes)
    for sample in out["samples"]:
        f = sample["frame"]
        for bid, state in sample["bodies"].items():
            obj = keyed[bid]
            obj.location = state["position"]
            obj.rotation_mode = "QUATERNION"
            obj.rotation_quaternion = state["quaternion"]
            obj.keyframe_insert(data_path="location", frame=f)
            obj.keyframe_insert(data_path="rotation_quaternion", frame=f)
    final = out["result"]["final_state"]["bodies"]
    return {"bodies": len(bodies), "keyed": len(out["keyed"]), "static": len(out["static"]),
            "planes": len(planes), "meshes": len(meshes), "schema_version": out["scene"]["schema_version"],
            "frames": frames, "fps": fps,
            "substeps": out["timestep"]["substeps"], "dt": out["timestep"]["dt"],
            "max_penetration_m": out["result"]["checks"]["max_penetration_m"],
            "final_positions": {k: v["position"] for k, v in final.items()}}


_MARK_DEFAULTS = {"reality_material": "steel", "reality_velocity": [0.0, 0.0, 0.0],
                  "reality_omega": [0.0, 0.0, 0.0], "reality_friction": 0.5, "reality_restitution": 0.0}


def _set_kind(obj, kind: str, shape: str = "sphere", static: bool = False) -> None:
    """Set the exclusive marks: kind is 'body', 'mesh' or 'plane'."""
    obj["reality_plane"] = kind == "plane"
    obj["reality_body"] = kind == "body"
    obj["reality_mesh"] = kind == "mesh"
    obj["reality_shape"] = shape
    obj["reality_static"] = static
    for key, value in _MARK_DEFAULTS.items():
        if key not in obj:
            obj[key] = value


class REALITY_OT_mark_body(Operator):
    bl_idname = "reality.mark_body"
    bl_label = "Mark as body"
    bl_description = "Make the active mesh a dynamic Reality sphere body"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "select a mesh object first")
            return {"CANCELLED"}
        try:
            _sphere_radius(obj)
            _origin_at_centre(obj)
        except ValueError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        _set_kind(obj, "body", "sphere", False)
        return {"FINISHED"}


class REALITY_OT_mark_collider(Operator):
    bl_idname = "reality.mark_collider"
    bl_label = "Mark as collider"
    bl_description = "Make the active object a sphere, box (dynamic or static) or static triangle-mesh collider"

    shape: EnumProperty(name=_SHAPE_LABEL, items=_SHAPE_ITEMS, default=_SHAPE_DEFAULT)
    static: BoolProperty(name=_STATIC_LABEL, description=_STATIC_DESC, default=False)

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "select a mesh object first")
            return {"CANCELLED"}
        if self.shape == "MESH" and not self.static:
            self.report({"INFO"}, "triangle meshes are static; the static flag is set")
        try:
            if self.shape == "MESH":
                _mesh_collider(obj)  # validates now, so the error shows here and not at bake time
                _set_kind(obj, "mesh", "mesh", True)
            else:
                shape = "sphere" if self.shape == "SPHERE" else "box"
                _check_transform(obj)
                if shape == "sphere":
                    _sphere_radius(obj)
                else:
                    _box_half_extents(obj)
                _origin_at_centre(obj)
                if self.static and any(abs(float(x)) > 0.0 for x in obj.get("reality_velocity", (0.0, 0.0, 0.0))):
                    raise ValueError(f"{obj.name}: a static body has zero velocity; reset reality_velocity first")
                _set_kind(obj, "body", shape, bool(self.static))
        except ValueError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
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
        obj["reality_mesh"] = False
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
        self.report({"INFO"}, f"baked {summary['keyed']} dynamic bodies over {summary['frames']} frames "
                              f"(schema v{summary['schema_version']}, {summary['static']} static, "
                              f"{summary['meshes']} meshes, dt {summary['dt']:.3e} s, "
                              f"max penetration {summary['max_penetration_m']:.2e} m)")
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
        layout.operator(REALITY_OT_mark_collider.bl_idname, icon="MESH_CUBE")
        layout.operator(REALITY_OT_mark_plane.bl_idname, icon="MESH_PLANE")
        if obj is not None:
            box = layout.box()
            if obj.get("reality_plane"):
                kind = "plane"
            elif obj.get("reality_mesh"):
                kind = "triangle mesh (static)"
            elif obj.get("reality_body"):
                kind = (f"{obj.get('reality_shape', 'sphere')} ("
                        + ("static" if obj.get("reality_static") else "dynamic") + ")")
            else:
                kind = "unmarked"
            box.label(text=f"{obj.name}: {kind}")
            if obj.get("reality_body") and not obj.get("reality_static"):
                for key in ("reality_material", "reality_velocity", "reality_omega",
                            "reality_friction", "reality_restitution"):
                    if key in obj:
                        box.prop(obj, f'["{key}"]', text=key.replace("reality_", ""))
                if "reality_radius" in obj:
                    box.prop(obj, '["reality_radius"]', text="radius override (m)")
            elif obj.get("reality_mesh") or obj.get("reality_plane"):
                for key in ("reality_friction", "reality_restitution"):
                    if key in obj:
                        box.prop(obj, f'["{key}"]', text=key.replace("reality_", ""))
        layout.separator()
        layout.operator(REALITY_OT_bake.bl_idname, icon="ANIM")
        layout.separator()
        layout.operator(REALITY_OT_import_obj.bl_idname, icon="IMPORT")


_CLASSES = (REALITY_OT_mark_body, REALITY_OT_mark_collider, REALITY_OT_mark_plane, REALITY_OT_bake,
            REALITY_OT_import_obj, REALITY_PT_panel)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
