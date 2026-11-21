# COVERAGE

Status at the end of this session. Counts are for the 43 projects in the directive's list. Review levels, in order of depth:

- **full source**: the whole repository, or the whole subsystem a claim is about, was read. **None reached.**
- **targeted source**: named files were read, and every fact cites a file and line. (7 projects.)
- **documentation**: README or licence statement read, source not read. (4 projects.)
- **licence and metadata**: GitHub API metadata and the licence file read. No source review. (32 projects.)
- **metadata**: API only. **None in the final table.** Every project has at least a licence check.
- **unavailable**: could not be reached. **None.** Slug corrections are recorded in `SOURCES/SOURCES.md`.

## Per project

| Project | Review level | What was read | Not yet reviewed |
|---|---|---|---|
| Bevy | licence and metadata | LICENSE-APACHE, API | architecture (ECS, scheduling), rendering, performance |
| Godot | licence and metadata | LICENSE.txt, API | architecture, rendering, performance, AI tools |
| Ambient | licence and metadata | LICENSE-APACHE, API | architecture; last push 2025-01-07 |
| microStudio | licence and metadata | LICENSE.txt, API | architecture |
| Love2D | licence and metadata | bundled licence file, API | architecture |
| ggez | licence and metadata | LICENSE, API | architecture |
| Amethyst | licence and metadata | COPYING, API | architecture; archived |
| Piston | licence and metadata | LICENSE, API | architecture |
| GDevelop | licence and metadata | LICENSE.md (per-folder MIT statement), API | architecture |
| Panda3D | licence and metadata | LICENSE, API | architecture, rendering |
| Box2D | targeted source | v3.2.0 defaults, manifold type, CCD flag (see PHYSICS/) | the contact solver body, sleep, joints |
| Rapier | targeted source | manifold size, reduction, defaults, warm start, CCD reference (PHYSICS/) | the CCD algorithm, islands, soft-body code |
| MuJoCo | targeted source (Phase 7) | `engine_collision_box.c` (Phase 7 notes) | constraint solver, defaults (not re-read here) |
| ReactPhysics3D | targeted source | configuration limits, world defaults, warm-start call, broadphase file names (PHYSICS/) | narrowphase details, solver internals |
| Jolt | targeted source | settings defaults, manifold size, motion quality, warm-start ratio (PHYSICS/) | solver internals, islands, QuadTree details |
| cannon-es | targeted source | iteration default, default broadphase and solver, CCD search (PHYSICS/) | contact equation generation, SAP details |
| Chipmunk2D | targeted source | iteration default, slop, arbiter size, broadphase, warm-start storage (PHYSICS/) | the warm-start application path |
| Filament | licence and metadata | LICENSE, API | renderer (PBR, materials), performance |
| Wicked Engine | licence and metadata | LICENSE.txt, API | renderer, architecture |
| OGRE | licence and metadata | LICENSE, API | scene graph, rendering |
| CRYENGINE | documentation | mirror README (licence agreement), 404 for a LICENSE file | everything else (source-available, licence restricts use) |
| O3DE | licence and metadata | LICENSE.txt (default Apache-2.0), API | architecture (Gem system), rendering |
| Flax | documentation | README and LICENSE.md (EULA) | everything else (source-available under EULA) |
| Stride | licence and metadata | LICENSE.md, API | architecture (C#), rendering |
| Defold | licence and metadata | LICENSE.txt (Defold License 1.0, clause 4(a)), API | architecture, performance |
| PlayCanvas | licence and metadata | LICENSE, API | rendering, architecture |
| Babylon.js | licence and metadata | license.md, API | rendering, performance |
| Minetest (Luanti) | licence and metadata | LICENSE.txt (LGPL-2.1+ code statement), API | architecture, voxel engine |
| OpenRA | licence and metadata | COPYING (GPL-3.0), API | architecture |
| VCMI | licence and metadata | license.txt (GPL-2.0), API | architecture |
| Xash3D FWGS | documentation | README; licence not located | licence (unverified); engine |
| Quake3e | licence and metadata | COPYING.txt (GPL-2.0), API | renderer, architecture |
| Urho3D | licence and metadata | README and licenses/urho3d/LICENSE (MIT), API | architecture; archived |
| jMonkeyEngine | licence and metadata | LICENSE.md (BSD-3-Clause), API | architecture, scene graph |
| Macroquad | licence and metadata | LICENSE-APACHE, API | architecture |
| pygame | documentation | README (LGPL-2.1) | everything else |
| Arcade | licence and metadata | license.rst (MIT), API | architecture |
| Ebiten | licence and metadata | LICENSE (Apache-2.0), API | architecture, performance |
| Excalibur | licence and metadata | LICENSE.md (BSD-2-Clause), API | architecture |
| LittleJS | licence and metadata | LICENSE (MIT), API | architecture |
| Pyxel | licence and metadata | LICENSE (MIT), API | architecture |
| Flame | licence and metadata | LICENSE (MIT), API | architecture |
| UPBGE | licence and metadata | COPYING (Blender GPL), API | version of GPL not confirmed; architecture |

## Topic folders

| Folder | Projects with a source-level finding | Status |
|---|---|---|
| `PHYSICS/` | 7 (Box2D, Rapier, MuJoCo*, ReactPhysics3D, Jolt, cannon-es, Chipmunk2D) | contact and solver review written. *MuJoCo from Phase 7. |
| `ARCHITECTURE/` | 0 | no source review yet; scope listed |
| `RENDERING/` | 0 | no source review yet; scope listed |
| `PERFORMANCE/` | 0 | no measurements; scope listed |
| `AI_AUTOMATION/` | 0 | no source review; the directive's scope for this folder is not defined in the workspace (see MASTER_INDEX.md) |
| `COMPARATIVE_ANALYSIS/` | physics only (7) | cross-engine comparison limited to physics |

## What "complete" would require

The directive asks that every listed project be accounted for. All 43 are accounted for at the level in the table. It does
not ask for each to be read in full, but it asks for depth over summary. The 32 projects at "licence and metadata" are
the main gap. Reading them at targeted-source level would need a choice of subsystem per project and is not started.
