#!/bin/bash
# Download source tarballs (codeload) for the physics engines, at the default branch recorded in meta/.
# Tarballs are large (about 271 MB), so they go to $ER_WORK (default /tmp/er), NOT into the repository.
SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="${ER_WORK:-/tmp/er}"
mkdir -p "$WORK/src" || exit 1
for pair in "Rapier:dimforge/rapier" "Jolt:jrouwe/JoltPhysics" "ReactPhysics3D:DanielChappuis/reactphysics3d" "Chipmunk:slembcke/Chipmunk2D" "cannon-es:pmndrs/cannon-es"; do
  name=${pair%%:*}; repo=${pair#*:}
  branch=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['default_branch'])" "$SRC/meta/$name.json")
  code=$(curl -s -m 300 -L -o "$WORK/src/$name.tar.gz" -w "%{http_code}" "https://codeload.github.com/$repo/tar.gz/refs/heads/$branch")
  size=$(stat -c %s "$WORK/src/$name.tar.gz" 2>/dev/null || echo 0)
  echo "$name $repo $branch http=$code bytes=$size"
  if [ "$code" = "200" ] && [ "$size" -gt 1000 ]; then
    mkdir -p "$WORK/src/$name" && tar -xzf "$WORK/src/$name.tar.gz" -C "$WORK/src/$name" --strip-components=1 && echo "  extracted $name"
  fi
done
echo PHYS_FETCH_DONE
