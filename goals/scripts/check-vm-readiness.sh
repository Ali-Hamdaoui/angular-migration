#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${REPO:-/home/ubuntu/angular-migration}"

resolve_python() {
  local candidate=""

  if [[ -n "${PYTHON_BIN:-}" ]]; then
    candidate="$PYTHON_BIN"
  else
    for name in python3.12 python3.11 python3; do
      if command -v "$name" >/dev/null 2>&1; then
        candidate="$(command -v "$name")"
        break
      fi
    done
  fi

  [[ -n "$candidate" && -x "$candidate" ]] || {
    echo "ERROR: Python 3.11+ interpreter not found" >&2
    exit 1
  }

  "$candidate" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit(
        f"ERROR: Python 3.11+ required; current={sys.version.split()[0]}"
    )
PY

  PYTHON_BIN="$candidate"
}

resolve_python

REQUIRED=(
  bash
  git
  node
  npm
  hermes
  curl
  unzip
  rsync
  sha256sum
)

for cmd in "${REQUIRED[@]}"; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing $cmd" >&2
    exit 1
  }
done

"$PYTHON_BIN" -m venv --help >/dev/null 2>&1 || {
  echo "ERROR: Python venv support missing for $PYTHON_BIN" >&2
  exit 2
}

cd "$REPO"

[[ "$(git branch --show-current)" == "goal" ]] || {
  echo "ERROR: base checkout must be on goal" >&2
  exit 3
}

[[ -z "$(git status --porcelain)" ]] || {
  echo "ERROR: base checkout not clean" >&2
  git status --short >&2
  exit 4
}

"$PYTHON_BIN" goals/validation/validate_package.py

mkdir -p \
  /home/ubuntu/amfa-worktrees \
  /home/ubuntu/amfa-runtime

touch /home/ubuntu/amfa-runtime/.write-test
rm /home/ubuntu/amfa-runtime/.write-test

for port in $(seq 3301 3310) $(seq 8301 8310); do
  if command -v ss >/dev/null 2>&1 &&
     ss -ltn "sport = :$port" | grep -q LISTEN; then
    echo "ERROR: port $port already in use" >&2
    exit 5
  fi
done

printf 'git=%s\npython=%s\nnode=%s\nnpm=%s\nhermes=%s\n' \
  "$(git --version)" \
  "$("$PYTHON_BIN" --version 2>&1)" \
  "$(node --version)" \
  "$(npm --version)" \
  "$(hermes --version 2>/dev/null || echo installed)"

if command -v sqlite3 >/dev/null 2>&1; then
  printf 'sqlite3=%s\n' "$(sqlite3 --version)"
else
  echo "WARN: sqlite3 CLI missing; recommended for evidence inspection"
fi

BROWSER_AVAILABLE=false

for browser in chromium chromium-browser google-chrome google-chrome-stable; do
  if command -v "$browser" >/dev/null 2>&1; then
    BROWSER_AVAILABLE=true
    break
  fi
done

PLAYWRIGHT_ROOT="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"

if [[ "$BROWSER_AVAILABLE" == false && -d "$PLAYWRIGHT_ROOT" ]]; then
  if find "$PLAYWRIGHT_ROOT" \
      -maxdepth 4 \
      -type f \
      \( -name chrome -o -name headless_shell \) \
      -perm -111 \
      -print -quit |
      grep -q .; then
    BROWSER_AVAILABLE=true
  fi
fi

if [[ "$BROWSER_AVAILABLE" == true ]]; then
  echo "browser=available"
else
  echo "WARN: Chromium/Chrome not found; install Playwright Chromium before manual UI validation"
fi

df -h /home/ubuntu
