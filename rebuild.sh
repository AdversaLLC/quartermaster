#!/usr/bin/env bash
# Rebuild the local plugin snapshot and the Quartermaster index.
# Usage: ./rebuild.sh [workers]   (default 16 parallel fetches)
# Needs Claude Code installed: fetch.py reads its plugin directory cache.
set -euo pipefail
cd "$(dirname "$0")"

echo "1/3 fetching plugin manifests into repos/ ..."
python3 fetch.py "${1:-16}"

echo "2/3 building snapshot.json and lists/ ..."
python3 build_index.py

echo "3/3 building qm_index.json ..."
python3 qm_build.py

echo "done"
