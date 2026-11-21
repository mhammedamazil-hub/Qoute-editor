#!/bin/bash
# Fetch GitHub API metadata for each candidate slug. Records HTTP status; no guessing of fields.
cd "$(dirname "$0")" || exit 1
mkdir -p meta
while read -r name slug; do
  code=$(curl -s -m 20 -o "meta/$name.json" -w "%{http_code}" "https://api.github.com/repos/$slug")
  echo "$name $slug $code"
done < slugs.txt
echo META_DONE
