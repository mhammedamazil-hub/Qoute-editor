import csv, json, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
rows = []
# name -> meta file; project list in the directive order
order = [
    ("Bevy", "Bevy"), ("Godot", "Godot"), ("Ambient", "Ambient"), ("microStudio", "microStudio"),
    ("Love2D", "Love2D"), ("ggez", "ggez"), ("Amethyst", "Amethyst"), ("Piston", "Piston"),
    ("GDevelop", "GDevelop"), ("Panda3D", "Panda3D"), ("Box2D", "Box2D"), ("Rapier", "Rapier"),
    ("MuJoCo", "MuJoCo"), ("ReactPhysics3D", "ReactPhysics3D"), ("Jolt", "Jolt"), ("cannon-es", "cannon-es"),
    ("Chipmunk", "Chipmunk"), ("Filament", "Filament"), ("Wicked Engine", "WickedEngine"), ("OGRE", "OGRE"),
    ("CRYENGINE", "CRYENGINE_mirror"), ("O3DE", "O3DE"), ("Flax", "Flax"), ("Stride", "Stride"),
    ("Defold", "Defold"), ("PlayCanvas", "PlayCanvas"), ("Babylon.js", "Babylon"), ("Minetest (Luanti)", "Minetest"),
    ("OpenRA", "OpenRA"), ("VCMI", "VCMI"), ("Xash3D FWGS", "Xash3D"), ("Quake3e", "Quake3e"),
    ("Urho3D", "Urho3D"), ("jMonkeyEngine", "jMonkeyEngine"), ("Macroquad", "Macroquad"), ("pygame", "pygame"),
    ("Arcade", "Arcade"), ("Ebiten", "Ebiten"), ("Excalibur", "Excalibur"), ("LittleJS", "LittleJS"),
    ("Pyxel", "Pyxel"), ("Flame", "Flame"), ("UPBGE", "UPBGE"),
]
for label, fname in order:
    path = f"meta/{fname}.json"
    if not os.path.exists(path):
        rows.append({"project": label, "status": "missing"}); continue
    d = json.load(open(path))
    if "full_name" not in d:
        rows.append({"project": label, "status": "api_error", "message": d.get("message", "")}); continue
    lic = d.get("license") or {}
    rows.append({
        "project": label,
        "repo": d["full_name"],
        "url": d["html_url"],
        "spdx_api": lic.get("spdx_id") or "",
        "licence_name_api": lic.get("name") or "",
        "language_api": d.get("language") or "",
        "archived": d.get("archived"),
        "pushed_at": d.get("pushed_at", "")[:10],
        "stars": d.get("stargazers_count"),
        "default_branch": d.get("default_branch"),
        "description": (d.get("description") or "")[:140],
        "status": "ok",
    })

with open("inventory.json", "w") as fh:
    json.dump(rows, fh, indent=1)
fields = ["project", "repo", "url", "spdx_api", "licence_name_api", "language_api", "archived", "pushed_at",
          "stars", "default_branch", "description", "status", "message"]
with open("inventory.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
ok = sum(1 for r in rows if r.get("status") == "ok")
print("rows", len(rows), "ok", ok)
for r in rows:
    print(f'{r["project"]:20} {r.get("repo","-"):38} {r.get("spdx_api","-") or "-":14} {r.get("language_api","-") or "-":12} arch={r.get("archived")} pushed={r.get("pushed_at","-")} stars={r.get("stars","-")}')
