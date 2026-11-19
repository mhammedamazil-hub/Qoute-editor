# PROJECT REALITY engine: real-time runtime (first vertical slice)

A browser runtime that runs and draws PROJECT REALITY scenes in real time. It is a foundation, not a finished game
engine. Read "What it is not" before you judge it.

## What it does

- Loads `reality.scene` v1 files (one sphere, infinite planes, friction and restitution per contact).
- Simulates them with a fixed physics step of 1e-4 s. The stepper is a TypeScript port of the Python kernel's
  `reality.contact.step_sphere` (predict, detect, impulse with restitution and Coulomb friction, move, rotate).
- Draws them with three.js: a checker floor on the scene's planes, a striped ball (so spin is visible), shadows, a
  path trail, a velocity arrow, and a light flash on contact.
- Transport: play, pause, step 10 ms, reset, speed 0.05x to 2x, live friction and restitution sliders, live readouts
  (time, position, velocity, spin, kinetic energy, contact state, real-time factor).

Scenes: `public/scenes/rolling-sphere.json` (slides, then rolls), `ramp-roll.json` (rolls down a 20 degree ramp from
rest), `bouncing-sphere.json` (restitution 0.7).

## Run it

```bash
cd engine
npm install
npm run dev        # http://localhost:5180 (listens on 0.0.0.0)
npm test           # 24 tests
npm run typecheck
npm run build      # dist/, about 565 kB JavaScript (142 kB gzipped), mostly three.js
```

## How it is verified

The Python kernel is the reference. `reality/tools/export_engine_assets.py` runs `reality.control.simulate.run` on
each scene and stores the trajectory in `test/fixtures/`. `test/reference.test.ts` replays the same scene in the
browser physics and compares every recorded sample.

| check | result |
|---|---|
| Position, velocity versus Python, bounce and ramp scenes | identical (maximum difference 0) |
| Spin, quaternion versus Python, all three scenes | maximum difference 6.7e-16 |
| Free fall versus the semi-implicit Euler closed form | exact to 1e-9 m |
| Elastic bounce, first apex | error proportional to dt (halving dt halves the error; ratio checked in tests) |
| Slide to roll, t = 2 v0 / (7 mu g), final speed 5/7 v0 | onset within 2e-3 relative; final speed within 5e-4 m/s |
| Ramp roll, a = 5/7 g sin(theta) | within 2e-3 relative |
| Quaternion norm over 2 s with contacts | within 1e-12 |
| Frame mapping (position and orientation, proper rotation) | within 1e-12 |
| Fixed-step scheduler: real time, clamping, pause | tested (`test/loop.test.ts`) |
| Python side: material densities and fixture scene hashes match | `reality/tests/test_engine_assets.py` |

Measured throughput in Node on the development machine (2 cores): about 2.2 million physics steps per second,
roughly 220 times real time at dt = 1e-4 s. Re-measure before quoting it.

The browser view was **not** checked by eye. There is no browser in the build environment, so the rendering is verified
only by the mapping tests and by a successful build and dev-server response. Open the preview and check it.

## Physics limits (inherited from the kernel)

- One sphere, uniform density, solid. One contact point per step. Infinite planes only.
- No tunnelling protection: fast bodies can pass through thin geometry. Penetration is projected out each step.
- Semi-implicit Euler: the first-order error in dt is visible in bounce heights (about 4 parts in 10^4 per 1e-4 s).
- Friction is a Coulomb model with one coefficient per contact pair. Not a measured value for any real pair of
  surfaces.

## What it is not (honest scope)

A commercial engine of the kind the phrase "RAGE-level" usually means needs thousands of person-years: a renderer with
global illumination and streaming, an asset pipeline, animation, audio, networking, scripting, editor tooling, and
content. This folder has none of those. It is a verified simulation core with a live viewer. The next steps, in order
of value:

1. Multiple bodies and body-body contact (needed for anything beyond one ball).
2. Mesh colliders and a mesh format (OBJ is the proposal awaiting the user's decision).
3. Asset loading, a scene editor in the browser, and undo.
4. Rendering quality: PBR materials from the material database, image-based lighting, post-processing.
5. Audio from the acoustics model (ACOU-01..06 exist in the kernel, not wired here).
6. Performance work: a Web Worker for physics, and WebAssembly for hot loops, if profiling asks for it.

## Layout

```
engine/
  src/physics/   vec.ts (math), sphere.ts (contact stepper), scene.ts (loader and fixed-step World),
                 materials.generated.ts (generated from the Python kernel; do not edit)
  src/core/      loop.ts (fixed-step scheduler)
  src/render/    viewer.ts (three.js view, coordinate mapping)
  src/app/       main.ts (UI and frame loop)
  public/scenes/ scene files (reality.scene v1)
  test/          physics, reference (Python cross-check), loop, view tests; fixtures/ generated
```
