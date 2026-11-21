import json, base64, os, urllib.request, urllib.error, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
inv = json.load(open("inventory.json"))
os.makedirs("licence", exist_ok=True)
out = []
for r in inv:
    if r.get("status") != "ok":
        continue
    repo = r["repo"]
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/license",
                                 headers={"Accept": "application/vnd.github+json"})
    entry = {"project": r["project"], "repo": repo}
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read().decode())
        entry["file"] = d.get("path", "")
        entry["spdx_api"] = (d.get("license") or {}).get("spdx_id", "")
        text = base64.b64decode(d.get("content", "")).decode("utf-8", "replace")
        entry["bytes"] = len(text)
        entry["head"] = " ".join(text.split())[:160]
        with open(f"licence/{r['project'].replace(' ', '_').replace('/', '_')}.txt", "w") as fh:
            fh.write(text)
        entry["status"] = "ok"
    except urllib.error.HTTPError as exc:
        entry["status"] = f"http_{exc.code}"
    except Exception as exc:  # recorded, not hidden
        entry["status"] = f"error: {type(exc).__name__}: {exc}"
    out.append(entry)
    time.sleep(0.3)
json.dump(out, open("licence_check.json", "w"), indent=1)
for e in out:
    print(e["project"], "|", e.get("status"), "|", e.get("spdx_api", ""), "|", e.get("file", ""), "|", e.get("head", "")[:110])
print("LIC_DONE")
