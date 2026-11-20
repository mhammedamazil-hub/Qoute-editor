# Reality Physics: Blender add-on (PROJECT REALITY)

Runs the PROJECT REALITY contact solver inside Blender's 3D Viewport and writes the result as keyframes. It is an
add-on: Blender's own systems are not changed. Blender's rigid body world is not used. Blender's animation, rendering
and OBJ importer are used as they are.

Status: **Blender 5.0.1 (`bpy` module) only, tested headlessly.** The viewport panel is not checked on screen
(no display in the build environment). The solver, the collider rules and the keyframe output are checked (see Evidence).

## Install

Either copy `blender_addon/reality_physics/` into Blender's add-on folder, or keep it in this repository. The add-on
adds `reality/src` to `sys.path` when it finds it next to itself, so the repository layout works without installing
the `reality` package. Enable it under Edit > Preferences > Add-ons (name "Reality Physics").

## Workflow

1. **Import meshes.** File > Import > Wavefront (.obj), or the "Import OBJ" button in the Reality tab.
2. **Mark colliders.** Select an object and use one of:
   - "Mark as body": a dynamic sphere (the radius is half the bounding box).
   - "Mark as collider": a **sphere**, a **box** (dynamic or static, half-extents from the object size) or a
     **triangle mesh** (always static; its triangles are taken from the mesh data).
   - "Mark as plane": an infinite horizontal plane. Its normal is the object's local +Z axis, through its origin.
3. **Set properties** in the Reality panel (custom properties, so they are saved with the .blend file):
   - `reality_material`: a material name from `reality.materials` (default `steel`); it sets the mass. Not used by static
     bodies.
   - `reality_velocity` (m/s), `reality_omega` (rad/s, body frame). A static body must have zero velocity and omega.
   - `reality_friction` (>= 0), `reality_restitution` (0 to 1).
   - `reality_radius` (m): a sphere override. Otherwise the radius is half the bounding box. The mark refuses objects
     whose bounding box is not a sphere (sides differ by more than 0.1 %).
4. **Bake motion.** The bake runs over the scene frame range (`frame_start` to `frame_end`) at the scene frame rate and
   inserts `location` and `rotation_quaternion` keyframes on every **dynamic** body. Static bodies and meshes are not
   keyed. The start state is each object's current world location and rotation.

## Conventions

- Blender units: metres, seconds, Z up. Gravity is {0, 0, -9.80665} m/s^2. No axis conversion.
- Quaternions are (w, x, y, z), the same as Blender's `rotation_quaternion`. They are normalised in double precision
  before the scene is built, because Blender stores them as float32.
- The solver step is chosen so that each frame is a whole number of steps, with a step of at most 1 ms
  (`scene_build.bake_timestep`). At 24 fps that is 42 steps per frame.
- Scene version: all-dynamic-sphere scenes are written as schema v2 (with a `meshes` list when meshes are marked);
  scenes with boxes or static bodies are written as schema v3. The kernel validates every scene before it runs
  (`scene_build.run_scene`), and a refusal is reported with the kernel's reasons.
- Contact coefficients: each contact uses the smaller friction and the smaller restitution of its two objects (a mesh
  uses its own values). This is a modelling choice for the add-on, not a physical law.

## Refusals (checked before baking, with a message)

- A sphere or box whose origin is not at its geometric centre: the keyframes move the origin, so the centre must be
  there. Use Object > Set Origin > Origin to Geometry.
- A mirrored object (negative scale) or a sheared transform: apply the transform first (Ctrl+A).
- A parented marked object: unparent it first.
- A triangle mesh with modifiers: apply them first.
- A dynamic box touching a triangle mesh, or two dynamic boxes: box-mesh and box-box contacts are not implemented in
  the kernel.
- A static body with a non-zero velocity or omega, a dynamic body with no material, and invalid meshes (the kernel's
  mesh rules apply).

In Blender an operator that reports an error raises `RuntimeError` when called from Python. The UI shows the message.

## Limits (also in `LIMITATIONS.md`)

- Dynamic bodies: spheres and boxes. Triangle mesh colliders: static only.
- Baking overwrites existing location and rotation keyframes of dynamic bodies at the frames it writes.
- One contact point per sphere-plane or sphere-sphere pair. Box-plane uses corner contacts only. No contact manifolds,
  no continuous collision detection, no warm starting. Tall stacks drift (see `LIMITATIONS.md` section 5).
- A body at rest sits a small distance from its surface, of the order of g dt^2 for the step used (see `LIMITATIONS.md`
  section 5a for the measured values).
- No gameplay systems yet. This version is physics only.
- Blender's rigid body world is not used. If it is enabled on the same objects, the two will fight.

## Evidence

- `reality/tests/test_blender_scene_build.py` (14 tests) and `reality/tests/test_blender_colliders.py` (15 tests), no
  `bpy` needed: timestep, id mapping, contact rules, drop and bounce, box and static-body rules, mesh contacts,
  frame mapping, determinism, quaternion normalisation.
- `reality/tools/blender_smoke.py` (needs `bpy`, 34 checks, all passing under bpy 5.0.1): registers the add-on; marks
  planes, spheres, boxes and meshes through the operators; imports an OBJ through the add-on's operator; bakes; checks the
  keyframes (3 location and 4 rotation curves, keys on frames 1 to 49); checks the sphere-on-mesh rest height (0.050003 m
  against 0.05 m), the box-on-plane rest height (0.100005 m against 0.1 m), a rotated sphere (its float32 rotation
  fails the 1e-9 tolerance without normalisation), the static bodies not being keyed, and the refusals listed above.
  Also the earlier checks: the final position of a dropped sphere equals the Python reference (max difference 2.65e-9 m,
  float32 storage) and an OBJ export and re-import (482 vertices kept).
  Run: `LD_LIBRARY_PATH=... python3.11 tools/blender_smoke.py` with `pip install bpy==5.0.1`.

The build environment has no X11 or GL libraries. `bpy` loads there only through stub shared libraries (a sandbox
workaround, not a supported configuration). Anything that needs a window, the viewport or GL is not verified.
