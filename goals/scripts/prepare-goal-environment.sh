#!/usr/bin/env bash
set -Eeuo pipefail
FOLDER="${1:?usage: prepare-goal-environment.sh <goal-folder>}"
WT="/home/ubuntu/amfa-worktrees/$FOLDER"
RT="/home/ubuntu/amfa-runtime/$FOLDER"
[[ -d "$WT" && -f "$RT/session.json" ]] || { echo "ERROR: create worktrees first" >&2; exit 1; }
cd "$WT"
python3 -m venv "$RT/venv/python"
"$RT/venv/python/bin/python" -m pip install --upgrade pip
if [[ -f backend/pyproject.toml ]]; then
  "$RT/venv/python/bin/pip" install -e './backend[dev]'
fi
if [[ -f frontend/package-lock.json ]]; then
  (cd frontend && npm ci)
elif [[ -f frontend/package.json ]]; then
  echo "WARN: frontend/package-lock.json absent; do not run npm install silently. Follow repository policy." >&2
fi
echo "Prepared $FOLDER; activate with: source $RT/venv/python/bin/activate"
