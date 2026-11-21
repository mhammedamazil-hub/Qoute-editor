import json, urllib.request, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
repos = {"CRYENGINE": "MergHQ/CRYENGINE", "Xash3D": "FWGS/xash3d-fwgs", "Urho3D": "urho3d/urho3d", "pygame": "pygame/pygame"}
for name, repo in repos.items():
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/contents/", headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            items = json.loads(r.read().decode())
        names = [i["name"] for i in items]
        lic = [n for n in names if "LIC" in n.upper() or "COPY" in n.upper()]
        print(name, repo, "| root entries:", len(names), "| licence-like:", lic)
    except Exception as exc:
        print(name, repo, "ERROR", type(exc).__name__, exc)
