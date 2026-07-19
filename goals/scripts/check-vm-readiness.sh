#!/usr/bin/env bash
set -Eeuo pipefail
REPO="${REPO:-/home/ubuntu/angular-migration}"
REQUIRED=(bash git python3 node npm hermes curl unzip rsync sha256sum)
for cmd in "${REQUIRED[@]}"; do command -v "$cmd" >/dev/null || { echo "ERROR: missing $cmd" >&2; exit 1; }; done
python3 -m venv --help >/dev/null 2>&1 || { echo "ERROR: Python venv support missing" >&2; exit 2; }
cd "$REPO"
[[ "$(git branch --show-current)" == "goal" ]] || { echo "ERROR: base checkout must be on goal" >&2; exit 3; }
[[ -z "$(git status --porcelain)" ]] || { echo "ERROR: base checkout not clean" >&2; exit 4; }
python3 goals/validation/validate_package.py
mkdir -p /home/ubuntu/amfa-worktrees /home/ubuntu/amfa-runtime
touch /home/ubuntu/amfa-runtime/.write-test && rm /home/ubuntu/amfa-runtime/.write-test
for port in $(seq 3301 3310) $(seq 8301 8310); do
  if command -v ss >/dev/null && ss -ltn "sport = :$port" | grep -q LISTEN; then echo "ERROR: port $port already in use" >&2; exit 5; fi
done
printf 'git=%s\npython=%s\nnode=%s\nnpm=%s\nhermes=%s\n' "$(git --version)" "$(python3 --version 2>&1)" "$(node --version)" "$(npm --version)" "$(hermes --version 2>/dev/null || echo installed)"
if command -v sqlite3 >/dev/null; then sqlite3 --version; else echo "WARN: sqlite3 CLI missing (recommended for evidence inspection)"; fi
if command -v chromium >/dev/null || command -v chromium-browser >/dev/null || command -v google-chrome >/dev/null; then echo "browser=available"; else echo "WARN: Chromium/Chrome not found; UI manual evidence may require Playwright browser installation"; fi
df -h /home/ubuntu
