# SOURCES

Everything in this research set traces to one of the items below. Nothing was taken from a README, a blog post or a
search summary as a fact about code.

## 1. GitHub API metadata (`meta/`)

- Endpoint: `https://api.github.com/repos/{owner}/{repo}` (one JSON per project, file name = the project label).
- Fetched by `fetch_meta.sh` from `slugs.txt` (43 slugs), with corrections in `slugs2.txt`.
- Fields used: `full_name`, `html_url`, `license.spdx_id`, `language`, `archived`, `pushed_at`, `default_branch`,
  `stargazers_count`, `description`. The API response is stored unchanged.
- Two files are failed lookups, not data: `meta/CRYENGINE.json` (slug `CRYENGINE/CRYENGINE`, 404) and
  `meta/microStudio2.json` (slug `microstudio-io/microstudio`, 404). The `full_name` field is absent from both. The
  corrected slugs wrote their own files (`CRYENGINE_mirror.json`, `microStudio.json`).
- Not stored: the time of the fetch. The `pushed_at` values include dates later than the session date (2026-11-19);
  they are reported as returned.

## 2. Licence files (`licence/`, `licence_check.json`)

- Endpoint: `https://api.github.com/repos/{repo}/license` (base64 content, decoded by `fetch_license.py`).
- Where the endpoint returned 404, the repository root and the README were inspected by hand (`roots.py`, the README
  endpoint `repos/{repo}/readme`, and `repos/{repo}/git/trees/HEAD?recursive=1` for Xash3D). Results are in
  `../ENGINE_DATABASE.md`, column "Licence (verified text)".
- For CRYENGINE (mirror), Xash3D FWGS, Urho3D and pygame, the licence was not in a LICENSE file at the root. Urho3D's
  MIT licence is in `licenses/urho3d/LICENSE` (read through the API). pygame's LGPL-2.1 statement is in its README.

## 3. Source trees (physics review only)

Downloaded as codeload tarballs of each default branch, and extracted under `/tmp/er/src` (not in this repository,
271 MB). Snapshot SHAs from `GET /repos/{repo}/commits/{branch}`:

| Project | Repository | Branch | Commit | Commit date (API) |
|---|---|---|---|---|
| Rapier | dimforge/rapier | master | 475caa3ff4646fd9a796b67d14116256f4962bc7 | 2026-10-10 |
| Jolt | jrouwe/JoltPhysics | master | 56d450906bb3774ddd0261a6af0a1c8b089cc835 | 2026-11-21 |
| ReactPhysics3D | DanielChappuis/reactphysics3d | master | 7000610a244ea85377e4f4c9bcdf68af0159b595 | 2025-01-09 |
| Chipmunk2D | slembcke/Chipmunk2D | master | f2f3d66220b8bb1568b8402c6d194d73d4e477d1 | 2026-05-05 |
| cannon-es | pmndrs/cannon-es | master | dd971c4a604acdbb211955382e7a80de1f31edfb | 2024-01-06 |
| Box2D | erincatto/box2d | (workspace copy from Phase 7; version read from `include/box2d/base.h`: v3.2.0) | not recorded | not recorded |
| MuJoCo | google-deepmind/mujoco | (Phase 7 copy at `/tmp/src2/mujoco-main`; main branch at download) | not recorded | not recorded |

Box2D and MuJoCo were downloaded in Phase 7, and their commit SHAs were not recorded at that time. This is stated, not
filled in.

The Reality side of the comparison is from this repository at HEAD `6b3d324` (`reality/src/reality/collision/`).

## 4. Name and slug corrections (recorded, not silent)

- microStudio: `microstudio/microstudio` and `microstudio-io/microstudio` return 404. The project is `pmgl/microstudio`
  (search by name; API returns MIT).
- Wicked Engine: `turanszkics/WickedEngine` (my first spelling) returns 404. The project is `turanszkij/WickedEngine`.
- CRYENGINE: `CRYENGINE/CRYENGINE` returns 404. The only public mirror found is `MergHQ/CRYENGINE` (licence: none in the
  repo; README says the CRYENGINE license agreement governs). Whether this mirror is official was not verified.
- Minetest: `minetest/minetest` redirects (301). The project is now `luanti-org/luanti`.
- Urho3D: the repository full name is `urho3d/urho3d`. The `/license` endpoint returned 404 for it, so its licence was
  taken from the README (MIT) and from `licenses/urho3d/LICENSE`, read through the contents API.
- Xash3D FWGS: `FWGS/xash3d-fwgs`.

## 5. Scripts

- `fetch_meta.sh`: API metadata for each slug.
- `fetch_license.py`: licence files through the API.
- `fetch_physics.sh`: tarball download for the five physics projects. Tarballs go to `$ER_WORK` (default `/tmp/er`),
  not into this folder. Branch names are read from `meta/`.
- `fetch_meta.sh`, `fetch_license.py`, `tabulate.py` and `roots.py` run from the folder that contains them.
- `roots.py`: root listing for projects without a LICENSE file.
- `tabulate.py`: a text table and CSV from `meta/`.
- `build_database.py`: writes `../ENGINE_DATABASE.md` and `../database.csv` from `meta/`, `licence_check.json` and the
  licence classes it contains. Run it from this folder: `python3 build_database.py`.

The fetch scripts use the sandbox's outbound access to `api.github.com` and `codeload.github.com`. They were run in this
session. The API is unauthenticated, so the rate limit applies.
