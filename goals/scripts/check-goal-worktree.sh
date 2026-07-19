#!/usr/bin/env bash
set -Eeuo pipefail
FOLDER="${1:?usage: check-goal-worktree.sh <goal-folder> <branch>}"
EXPECTED_BRANCH="${2:?usage: check-goal-worktree.sh <goal-folder> <branch>}"
WT="/home/ubuntu/amfa-worktrees/$FOLDER"
RT="/home/ubuntu/amfa-runtime/$FOLDER"
LOCK="/home/ubuntu/amfa-worktrees/.base-lock.json"
SESSION="$RT/session.json"
[[ "$(pwd -P)" == "$WT" ]] || { echo "ERROR: wrong cwd $(pwd -P), expected $WT" >&2; exit 1; }
[[ -f "$LOCK" && -f "$SESSION" ]] || { echo "ERROR: missing base lock or session metadata" >&2; exit 2; }
BASE_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["base_sha"])' "$LOCK")"
LOCK_REMOTE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["remote_url"])' "$LOCK")"
LOCK_AGENTS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["root_agents_sha256"])' "$LOCK")"
[[ "$(git branch --show-current)" == "$EXPECTED_BRANCH" ]] || { echo "ERROR: wrong branch" >&2; exit 3; }
[[ "$(git remote get-url origin)" == "$LOCK_REMOTE" ]] || { echo "ERROR: remote drift" >&2; exit 4; }
git merge-base --is-ancestor "$BASE_SHA" HEAD || { echo "ERROR: base SHA not ancestor" >&2; exit 5; }
[[ "$(sha256sum AGENTS.md | awk '{print $1}')" == "$LOCK_AGENTS" ]] || { echo "ERROR: root AGENTS.md drift from session lock" >&2; exit 6; }
[[ -f "goals/$FOLDER/GOAL.md" ]] || { echo "ERROR: assigned goal absent" >&2; exit 7; }
[[ -w "$RT" ]] || { echo "ERROR: runtime root not writable" >&2; exit 8; }
[[ -z "$(git status --porcelain)" ]] || { echo "ERROR: worktree has changes before launch" >&2; exit 9; }
python3 - "$SESSION" "$FOLDER" "$EXPECTED_BRANCH" "$BASE_SHA" <<'PYSESSIONCHECK'
import json,sys
p,folder,branch,base=sys.argv[1:]; d=json.load(open(p))
assert d['goal_folder']==folder and d['branch']==branch and d['base_sha']==base
print(f"session={d['goal_id']} ports={d['backend_port']}/{d['frontend_port']} namespace={d['langgraph_namespace']}")
PYSESSIONCHECK
echo "READY $FOLDER $EXPECTED_BRANCH base=$BASE_SHA head=$(git rev-parse HEAD)"
