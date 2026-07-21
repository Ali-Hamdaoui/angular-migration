#!/usr/bin/env bash
set -Eeuo pipefail

FOLDER="${1:?usage: prepare-goal-environment.sh <goal-folder>}"
WT="/home/ubuntu/amfa-worktrees/$FOLDER"
RT="/home/ubuntu/amfa-runtime/$FOLDER"

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
    exit 2
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

[[ -d "$WT" && -f "$RT/session.json" ]] || {
  echo "ERROR: create worktrees first" >&2
  exit 1
}

cd "$WT"

VENV_ROOT="$RT/venv/python"
VENV_PYTHON="$VENV_ROOT/bin/python"

if [[ -x "$VENV_PYTHON" ]]; then
  if ! "$VENV_PYTHON" -c \
    'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'
  then
    echo "Removing unsupported existing Python environment"
    rm -rf "$VENV_ROOT"
  fi
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_ROOT"
fi

"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel

if [[ -f backend/pyproject.toml ]]; then
  "$VENV_PYTHON" -m pip install -e ./backend

  "$VENV_PYTHON" -m pip install \
    "httpx>=0.27,<1.0" \
    "pytest>=8.0,<9.0" \
    "ruff>=0.12,<1.0"
fi

if [[ -f frontend/package-lock.json ]]; then
  (
    cd frontend
    npm ci
  )
elif [[ -f frontend/package.json ]]; then
  echo \
    "WARN: frontend/package-lock.json absent; do not run npm install silently. Follow repository policy." \
    >&2
fi

echo "Prepared goal: $FOLDER"
echo "Python: $("$VENV_PYTHON" --version)"
echo "Runtime: $RT"
echo "Activate with:"
echo "source $VENV_ROOT/bin/activate"
