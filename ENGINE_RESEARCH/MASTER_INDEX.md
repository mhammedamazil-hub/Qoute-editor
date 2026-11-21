# ENGINE_RESEARCH: master index

Workstream B of the directive: open-source game-engine intelligence. This folder is the record. Read `COVERAGE.md` first:
it states how deep each project was reviewed. Most projects are at "licence and metadata" level.

## Status

- Inventory: all 43 projects in the directive's list are accounted for (`ENGINE_DATABASE.md`, `database.csv`).
- Licences: checked for all 43 against the licence file or README. Xash3D FWGS is not verified (no licence file found).
  CRYENGINE mirror, Flax and Defold are source-available under restrictive licences, not open source (see Licence notes).
- Source reviews: 7 projects at targeted source level, all physics (`PHYSICS/`). No project reached full-source review.
- Proposals: none prioritised yet. `ADOPTION_CANDIDATES.md` lists candidates. Tiers wait for Phase 7 to close.
- Phase 7 is not affected by this work. Its code and tests are committed at `6b3d324`.

## Files

| File | What it is |
|---|---|
| `COVERAGE.md` | review level and what was read for each project |
| `ENGINE_DATABASE.md` | the database: repo, language, last push, archived, licence (as verified), licence class, review level |
| `database.csv` | the same database, for machines |
| `ADOPTION_CANDIDATES.md` | candidate ideas, their source fact, Reality's status, and the evidence needed |
| `PHYSICS/collision_solver_review.md` | targeted source review: manifold size, reduction, defaults, warm starting, CCD, broadphase; comparison with Reality |
| `ARCHITECTURE/README.md` | scope, no findings yet |
| `RENDERING/README.md` | scope, no findings yet |
| `PERFORMANCE/README.md` | no measurements for other engines; Reality's numbers are in `reality/BOX_BOX_STUDY.md` |
| `AI_AUTOMATION/README.md` | not started; scope not defined in the workspace |
| `COMPARATIVE_ANALYSIS/README.md` | the physics comparison, and what is pending |
| `SOURCES/SOURCES.md` | every source, endpoint, commit SHA, slug correction, and script |
| `SOURCES/meta/`, `SOURCES/licence/`, `SOURCES/*.json` | stored API responses and licence texts behind the database |
| `SOURCES/build_database.py` | regenerates `ENGINE_DATABASE.md` and `database.csv` |

## Key findings (source-level, with references in the review)

1. Manifold size differs: Box2D 2 points; Rapier, Jolt, ReactPhysics3D 4; Chipmunk2D 2. Reality keeps every distinct
   clipped vertex of a face contact, with no reduction. Consequence for Reality is a hypothesis (see the review).
2. Default solver iteration counts: Jolt 10 velocity and 2 position, ReactPhysics3D 6 and 3, Rapier 4 (plus PGS and
   stabilisation), cannon-es 10, Chipmunk2D 10. Reality uses 128 Gauss–Seidel sweeps for box steps. The methods differ
   (soft contacts in Box2D and Rapier), so these numbers are not a measure of extra work.
3. Warm starting is on by default in Jolt and present in Rapier, ReactPhysics3D and Chipmunk2D. Reality has none.
4. CCD exists in Box2D (`enableContinuous`, default on), Jolt (per-body LinearCast), and Rapier (`dynamics/ccd`). None was
   found in ReactPhysics3D, cannon-es or Chipmunk2D. Reality has none.
5. Broadphases are trees, grids or sweeps in every physics engine reviewed. Reality lists all pairs (O(N²)). Measured in
   Reality: 0.32 s/step at N = 100 and 62 s/step at N = 500.

## Licence notes

- Source-available, not open source by licence text: Flax (EULA), CRYENGINE mirror (licence agreement), Defold (Defold License
  1.0; clause 4(a) forbids selling or commercialising the Work as a Game Engine Product).
- Not verified: Xash3D FWGS (no licence file found in the tree).
- Copyleft: Luanti (LGPL-2.1+ code), OpenRA (GPL-3.0), VCMI (GPL-2.0), Quake3e (GPL-2.0), UPBGE (GPL), pygame (LGPL-2.1).

## How to reproduce

From `ENGINE_RESEARCH/SOURCES`: `bash fetch_meta.sh` (needs `slugs.txt`), `python3 fetch_license.py`, `bash fetch_physics.sh`
(downloads about 271 MB into `/tmp/er/src`), then `python3 build_database.py`. The physics review was done by reading
the named files in those trees; the review document gives the paths.

## Limits

- Reviews are targeted. No project has a full-source review.
- No performance measurements for other engines. None are claimed.
- The directive's AI_AUTOMATION scope is not defined in the workspace, so that folder has no content.
- Two projects' snapshot SHAs (Box2D, MuJoCo) were not recorded when they were downloaded in Phase 7.
