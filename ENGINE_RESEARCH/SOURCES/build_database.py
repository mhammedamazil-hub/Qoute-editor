"""Build ENGINE_DATABASE.md and database.csv from the stored GitHub API metadata (SOURCES/meta) and the stored
licence results (SOURCES/licence_check.json). Run from ENGINE_RESEARCH/SOURCES:  python3 build_database.py

Columns that come from the API (repo, language, last push, archived, description) are copied, not written by hand.
Columns that need a reading of a licence file or of source code are written in CLASSES below, and each entry names
the file that was read. Entries marked "API only" were not checked against a file.
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)

# project label -> (meta file stem, licence as verified from the file read, licence class, review level, note)
CLASSES = {
    "Bevy": ("Bevy", "Apache-2.0 (LICENSE-APACHE read)", "OSI permissive", "licence and metadata", ""),
    "Godot": ("Godot", "MIT (LICENSE.txt read)", "OSI permissive", "licence and metadata", ""),
    "Ambient": ("Ambient", "Apache-2.0 (LICENSE-APACHE read)", "OSI permissive", "licence and metadata",
                "last push 2025-01-07; older than most rows"),
    "microStudio": ("microStudio", "MIT (LICENSE.txt read)", "OSI permissive", "licence and metadata", ""),
    "Love2D": ("Love2D", "zlib for LOVE (first entry of the bundled licence file; other components MIT/Expat etc.)",
               "OSI permissive", "licence and metadata", "API NOASSERTION because of bundled third-party notices"),
    "ggez": ("ggez", "MIT (LICENSE read)", "OSI permissive", "licence and metadata", ""),
    "Amethyst": ("Amethyst", "Apache-2.0 or MIT, at the user's option (COPYING read)", "OSI permissive",
                 "licence and metadata", "ARCHIVED on GitHub"),
    "Piston": ("Piston", "MIT (LICENSE read)", "OSI permissive", "licence and metadata", ""),
    "GDevelop": ("GDevelop", "MIT for Core, GDJS, IDE and Extensions (LICENSE.md header read)", "OSI permissive",
                 "licence and metadata", "API NOASSERTION; the file states MIT per folder"),
    "Panda3D": ("Panda3D", "Modified BSD, CMU copyright (LICENSE read)", "OSI permissive", "licence and metadata",
                "API NOASSERTION; text is BSD-style"),
    "Box2D": ("Box2D", "MIT (LICENSE read); source is v3.2.0", "OSI permissive", "targeted source",
              "physics; see PHYSICS/"),
    "Rapier": ("Rapier", "Apache-2.0 (LICENSE read)", "OSI permissive", "targeted source", "physics; see PHYSICS/"),
    "MuJoCo": ("MuJoCo", "Apache-2.0 (LICENSE read)", "OSI permissive", "targeted source (Phase 7)",
               "physics; collision file reviewed in Phase 7; see PHYSICS/"),
    "ReactPhysics3D": ("ReactPhysics3D", "Zlib (LICENSE read)", "OSI permissive", "targeted source",
                       "physics; see PHYSICS/"),
    "Jolt": ("Jolt", "MIT (LICENSE read)", "OSI permissive", "targeted source", "physics; see PHYSICS/"),
    "cannon-es": ("cannon-es", "MIT (LICENSE read)", "OSI permissive", "targeted source", "physics; see PHYSICS/"),
    "Chipmunk": ("Chipmunk", "MIT (LICENSE.txt read)", "OSI permissive", "targeted source", "physics; see PHYSICS/"),
    "Filament": ("Filament", "Apache-2.0 (LICENSE read)", "OSI permissive", "licence and metadata", ""),
    "Wicked Engine": ("WickedEngine", "MIT (LICENSE.txt read)", "OSI permissive", "licence and metadata", ""),
    "OGRE": ("OGRE", "MIT (LICENSE read)", "OSI permissive", "licence and metadata", ""),
    "CRYENGINE": ("CRYENGINE_mirror", "No licence file in the mirror. README: source governed by the CRYENGINE "
                  "license agreement (ce-terms)", "custom agreement; NOT open source",
                  "documentation (README)", "mirror slug MergHQ/CRYENGINE; official CRYENGINE/CRYENGINE returned 404"),
    "O3DE": ("O3DE", "Apache-2.0 is the default (LICENSE.txt read); other licences apply to some parts",
             "OSI permissive (default)", "licence and metadata", "API NOASSERTION"),
    "Flax": ("Flax", "Flax Engine End User License Agreement (README and LICENSE.md read)",
             "custom EULA; source-available, NOT open source", "documentation (README)", ""),
    "Stride": ("Stride", "MIT (LICENSE.md read)", "OSI permissive", "licence and metadata", ""),
    "Defold": ("Defold", "Defold License 1.0 (LICENSE.txt read). Clause 4(a): no selling or commercialising the Work "
               "as a Game Engine Product", "custom; source-available with restrictions",
               "licence and metadata", "API NOASSERTION; not presented as an OSI licence in the text"),
    "PlayCanvas": ("PlayCanvas", "MIT (LICENSE read)", "OSI permissive", "licence and metadata", ""),
    "Babylon.js": ("Babylon", "Apache-2.0 (license.md read)", "OSI permissive", "licence and metadata", ""),
    "Minetest (Luanti)": ("Minetest", "LGPL-2.1 or later for the code (LICENSE.txt read); textures and sounds under "
                          "their own licences", "OSI copyleft", "licence and metadata",
                          "renamed from minetest/minetest; GitHub redirect"),
    "OpenRA": ("OpenRA", "GPL-3.0 (COPYING read)", "OSI copyleft", "licence and metadata", ""),
    "VCMI": ("VCMI", "GPL-2.0 (license.txt read)", "OSI copyleft", "licence and metadata", ""),
    "Xash3D FWGS": ("Xash3D", "NOT VERIFIED: no licence file at the repository root; tree search found only "
                    "3rdparty/ps4compat/LICENSE", "unverified", "documentation (README)",
                    "do not describe as open source until the licence is located"),
    "Quake3e": ("Quake3e", "GPL-2.0 (COPYING.txt read)", "OSI copyleft", "licence and metadata", ""),
    "Urho3D": ("Urho3D", "MIT (README and licenses/urho3d/LICENSE read); no root licence file", "OSI permissive",
               "licence and metadata", "ARCHIVED on GitHub"),
    "jMonkeyEngine": ("jMonkeyEngine", "BSD-3-Clause (LICENSE.md read)", "OSI permissive",
                      "licence and metadata", ""),
    "Macroquad": ("Macroquad", "Apache-2.0 (LICENSE-APACHE read)", "OSI permissive", "licence and metadata", ""),
    "pygame": ("pygame", "LGPL-2.1 (README read; file docs/LGPL.txt referenced)", "OSI copyleft (LGPL)",
               "documentation (README)", ""),
    "Arcade": ("Arcade", "MIT (license.rst read)", "OSI permissive", "licence and metadata", "API NOASSERTION"),
    "Ebiten": ("Ebiten", "Apache-2.0 (LICENSE read)", "OSI permissive", "licence and metadata", ""),
    "Excalibur": ("Excalibur", "BSD-2-Clause (LICENSE.md read)", "OSI permissive", "licence and metadata", ""),
    "LittleJS": ("LittleJS", "MIT (LICENSE read)", "OSI permissive", "licence and metadata", ""),
    "Pyxel": ("Pyxel", "MIT (LICENSE read)", "OSI permissive", "licence and metadata", "API NOASSERTION"),
    "Flame": ("Flame", "MIT (LICENSE read)", "OSI permissive", "licence and metadata", ""),
    "UPBGE": ("UPBGE", "GPL (COPYING read: Blender's GPL; GPL version not confirmed)", "OSI copyleft",
              "licence and metadata", "Blender-based; API NOASSERTION"),
}


def main():
    inv = json.load(open(os.path.join(HERE, "inventory.json")))
    rows = []
    for rec in inv:
        label = rec["project"]
        stem, licence, cls, review, note = CLASSES[label]
        meta = json.load(open(os.path.join(HERE, "meta", f"{stem}.json")))
        if "full_name" not in meta:
            raise SystemExit(f"{label}: metadata missing")
        rows.append({
            "project": label,
            "repo": meta["full_name"],
            "url": meta["html_url"],
            "language_api": meta.get("language") or "",
            "last_push": (meta.get("pushed_at") or "")[:10],
            "archived": meta.get("archived"),
            "stars": meta.get("stargazers_count"),
            "licence_verified": licence,
            "licence_class": cls,
            "review_level": review,
            "api_description": (meta.get("description") or "").strip(),
            "note": note,
        })
    fields = list(rows[0].keys())
    with open(os.path.join(OUT, "database.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# ENGINE_DATABASE",
        "",
        "One row per project in the directive's list (43 entries). Source: GitHub API metadata (`SOURCES/meta/`), "
        "licence files and README statements read through the API (`SOURCES/licence/`), and source reviews under "
        "`PHYSICS/`. The description column is the repository's own API description, not an assessment. "
        "Review levels follow `COVERAGE.md`.",
        "",
        "| Project | Repository | Language (API) | Last push | Archived | Licence (verified text) | Licence class | Review level | Notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        repo = f"[{r['repo']}]({r['url']})"
        lines.append("| {p} | {repo} | {lang} | {push} | {arch} | {lic} | {cls} | {rev} | {note} |".format(
            p=r["project"], repo=repo, lang=r["language_api"] or "-", push=r["last_push"],
            arch="yes" if r["archived"] else "no", lic=r["licence_verified"], cls=r["licence_class"],
            rev=r["review_level"], note=r["note"] or "-"))
    lines += [
        "",
        "## Repository descriptions (API, verbatim)",
        "",
    ]
    for r in rows:
        lines.append(f"- **{r['project']}**: {r['api_description'] or '(no description in API)'}")
    lines += [
        "",
        "## Notes on the table",
        "",
        "- *Licence (verified text)* is what the file or README states. *Licence class* is a grouping by that text. "
        "Only the 'OSI' labels are a grouping, not a certification.",
        "- *Source-available* projects (CRYENGINE mirror, Flax, Defold) are not open source by their licence text, "
        "and are not treated as open source anywhere in this folder.",
        "- Last-push dates are copied from the API responses in `SOURCES/meta/`, unchanged. Some are later than the "
        "session date (2026-11-19 UTC). The fetch time is not recorded in the stored files, so this is reported as "
        "returned, not explained.",
    ]
    with open(os.path.join(OUT, "ENGINE_DATABASE.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("rows", len(rows))


if __name__ == "__main__":
    main()
