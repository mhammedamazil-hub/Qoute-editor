# Reality Physics: Blender add-on (PROJECT REALITY)

Runs the PROJECT REALITY sphere and plane contact solver inside Blender's 3D Viewport and writes the result as
keyframes. It is an add-on: Blender's own systems are not changed. Blender's rigid body world, animation,
rendering and the OBJ importer are used as they are.

Status: **Blender 5.0.1 (`bpy` module) only, tested headlessly.** The viewport panel is not checked on screen
(no display in the build environment). The solver and keyframe output are checked (see Evidence).

## Install

Either copy `blender_addon/reality_physics/` into Blender's add-on folder, or keep it in this repository. The add-on
adds `reality/src` to `sys.path` when it finds it next to itself, so the repository layout works without installing
the `reality` package. Enable it under Edit > Preferences > Add-ons (name "Reality Physics").

## Workflow

1. **Import meshes.** File > Import > Wavefront (.obj), or the "Import OBJ" button in the Reality tab.
2. **Mark bodies and planes.** Select an object and press "Mark as body" (sphere) or "Mark as plane". A plane is
   infinite. Its normal is the object's local +Z axis, and it passes through the object's origin.
3. **Set properties** in the Reality panel (custom properties, so they are saved with the .blend file):
   - `reality_material`: a material name from `reality.materials` (default `steel`); it sets the mass.
   - `reality_velocity` (m/s), `reality_omega` (rad/s, body frame).
   - `reality_friction` (>= 0), `reality_restitution` (0 to 1).
   - `reality_radius` (m): an override. Otherwise the radius is half the bounding box. The bake refuses objects
     whose bounding box is not a sphere (sides differ by more than 0.1 %).
4. **Bake motion.** The bake runs over the scene frame range (`frame_start` to `frame_end`) at the scene frame rate
   and inserts `location` and `rotation_quaternion` keyframes on every marked body. Start state is the object's
   current world location and rotation.

## Conventions

- Blender units: metres, seconds, Z up. Gravity is {0, 0, -9.80665} m/s^2. No axis conversion.
- Quaternions are (w, x, y, z), the same as Blender's `rotation_quaternion`.
- The solver step is chosen so that each frame is a whole number of steps, with a step of at most 1 ms
  (`scene_build.bake_timestep`). At 24 fps that is 42 steps per frame.
- Contact coefficients: each contact uses the smaller friction and the smaller restitution of its two objects.
  This is a modelling choice for the add-on, not a physical law.

## Limits (also in `LIMITATIONS.md`)

- Bodies are spheres only. Planes are infinite and horizontal in practice (any normal works, but the plane is not
  bounded).
- Marked bodies must not be parented. Baking overwrites existing location and rotation keyframes of marked bodies at
  the frames it writes.
- One contact point per pair or plane. No contact manifolds, no continuous collision detection, no warm starting.
  Tall stacks drift (see `LIMITATIONS.md` section 5).
- No gameplay systems yet. This version is physics only.
- Blender's rigid body world is not used. If it is enabled on the same objects, the two will fight.

## Evidence

- `reality/tests/test_blender_scene_build.py` (14 tests, no `bpy` needed): timestep, id mapping, contact rule,
  drop and bounce, frame mapping, determinism.
- `reality/tools/blender_smoke.py` (needs `bpy`): registers the add-on; marks a plane and a sphere through the
  operators; bakes; checks 3 location and 4 rotation curves, keys on frames 1 to 49, and the final position against
  the Python reference (max difference 2.65e-9 m, float32 storage). Also an OBJ export and re-import (482 vertices
  kept). Run: `LD_LIBRARY_PATH=... python3.11 tools/blender_smoke.py` with `pip install bpy==5.0.1`.

The build environment has no X11 or GL libraries. `bpy` loads there only through stub shared libraries (a sandbox
workaround, not a supported configuration). Anything that needs a window, the viewport or GL is not verified.
