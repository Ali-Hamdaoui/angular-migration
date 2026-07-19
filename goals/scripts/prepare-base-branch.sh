#!/usr/bin/env bash
set -Eeuo pipefail
REPO="${REPO:-/home/ubuntu/angular-migration}"
BASE_BRANCH="goal"
cd "$REPO"
git fetch --prune origin
if ! git show-ref --verify --quiet "refs/remotes/origin/$BASE_BRANCH"; then
  echo "ERROR: origin/goal does not exist. This package never creates it from dev automatically." >&2
  echo "Create and review the shared goal branch explicitly, then rerun." >&2
  exit 2
fi
if git show-ref --verify --quiet "refs/heads/$BASE_BRANCH"; then
  git switch "$BASE_BRANCH"
else
  git switch --create "$BASE_BRANCH" --track "origin/$BASE_BRANCH"
fi
git pull --ff-only origin "$BASE_BRANCH"
[[ -z "$(git status --porcelain)" ]] || { echo "ERROR: base checkout is not clean" >&2; exit 3; }
printf 'Prepared %s at %s\n' "$BASE_BRANCH" "$(git rev-parse HEAD)"
