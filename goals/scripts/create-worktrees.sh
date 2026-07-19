#!/usr/bin/env bash
set -Eeuo pipefail
REPO="${REPO:-/home/ubuntu/angular-migration}"
WORKTREE_ROOT="${WORKTREE_ROOT:-/home/ubuntu/amfa-worktrees}"
RUNTIME_ROOT="${RUNTIME_ROOT:-/home/ubuntu/amfa-runtime}"
LOCK="$WORKTREE_ROOT/.base-lock.json"
AGENTS="$REPO/AGENTS.md"

cd "$REPO"
git fetch --prune origin
git switch goal
git pull --ff-only origin goal
[[ -z "$(git status --porcelain)" ]] || { echo "ERROR: base checkout not clean" >&2; exit 2; }
BASE_SHA="$(git rev-parse HEAD)"
REMOTE_URL="$(git remote get-url origin)"
AGENTS_SHA="$(sha256sum "$AGENTS" | awk '{print $1}')"
mkdir -p "$WORKTREE_ROOT" "$RUNTIME_ROOT"

if [[ -f "$LOCK" ]]; then
  LOCKED_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["base_sha"])' "$LOCK")"
  [[ "$LOCKED_SHA" == "$BASE_SHA" ]] || { echo "ERROR: base drift: lock=$LOCKED_SHA current=$BASE_SHA. Integrate/remove worktrees deliberately; do not overwrite the lock." >&2; exit 3; }
else
  python3 - "$LOCK" "$BASE_SHA" "$REMOTE_URL" "$AGENTS_SHA" <<'PYLOCK'
import json,sys,datetime
p,sha,remote,agents=sys.argv[1:]
json.dump({'schema_version':'1.0','base_branch':'goal','base_sha':sha,'remote_url':remote,'root_agents_sha256':agents,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat()},open(p,'w'),indent=2)
open(p,'a').write('\n')
PYLOCK
fi

python3 - "$REPO/goals/GOAL_INDEX.yaml" <<'PYINDEX' | while IFS='|' read -r gid folder branch bp fp; do
import re,sys
text=open(sys.argv[1]).read()
for block in re.split(r'(?=  - order: )',text):
    if not block.startswith('  - order: '): continue
    def one(pattern):
        m=re.search(pattern,block); return m.group(1) if m else ''
    print('|'.join([one(r'    id: (\S+)'),one(r'    folder: (\S+)'),one(r'    branch: (\S+)'),one(r'    backend_port: (\d+)'),one(r'    frontend_port: (\d+)')]))
PYINDEX
  WT="$WORKTREE_ROOT/$folder"; RT="$RUNTIME_ROOT/$folder"
  if [[ -e "$WT" ]]; then
    [[ -d "$WT/.git" || -f "$WT/.git" ]] || { echo "ERROR: existing non-worktree path $WT" >&2; exit 4; }
    ACTUAL_BRANCH="$(git -C "$WT" branch --show-current)"
    [[ "$ACTUAL_BRANCH" == "$branch" ]] || { echo "ERROR: $WT uses $ACTUAL_BRANCH, expected $branch" >&2; exit 5; }
    git -C "$WT" merge-base --is-ancestor "$BASE_SHA" HEAD || { echo "ERROR: locked base is not ancestor of $WT" >&2; exit 6; }
  elif git show-ref --verify --quiet "refs/heads/$branch"; then
    git worktree add "$WT" "$branch"
  elif git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    git worktree add --track -b "$branch" "$WT" "origin/$branch"
  else
    git worktree add -b "$branch" "$WT" "$BASE_SHA"
  fi
  [[ "$(git -C "$WT" remote get-url origin)" == "$REMOTE_URL" ]] || { echo "ERROR: remote mismatch for $WT" >&2; exit 7; }
  git -C "$WT" merge-base --is-ancestor "$BASE_SHA" HEAD || { echo "ERROR: $branch is not based on locked goal SHA $BASE_SHA" >&2; exit 8; }
  [[ -z "$(git -C "$WT" status --porcelain)" ]] || { echo "ERROR: worktree $WT is not clean at preparation time" >&2; exit 9; }
  mkdir -p "$RT"/{database,artifacts,logs,temporary,fixtures,browser-profile,playwright,state,venv}
  chmod 700 "$RT" "$RT"/*
  python3 - "$RT/session.json" "$gid" "$folder" "$branch" "$BASE_SHA" "$WT" "$RT" "$bp" "$fp" "$AGENTS_SHA" <<'PYSESSION'
import json,sys,datetime
p,gid,folder,branch,base,wt,rt,bp,fp,agents=sys.argv[1:]
obj={'schema_version':'1.0','goal_id':gid,'goal_folder':folder,'branch':branch,'base_sha':base,'worktree':wt,'runtime_root':rt,'backend_port':int(bp),'frontend_port':int(fp),'langgraph_namespace':f'amfa-{folder}','root_agents_sha256':agents,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
json.dump(obj,open(p,'w'),indent=2); open(p,'a').write('\n')
PYSESSION
  echo "READY $gid $branch $WT runtime=$RT ports=$bp/$fp"
done

git worktree list
