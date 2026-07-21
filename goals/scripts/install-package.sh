#!/usr/bin/env bash
set -Eeuo pipefail
REPO="${REPO:-/home/ubuntu/angular-migration}"
PACKAGE_ROOT="${PACKAGE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
AGENTS_SOURCE="${AGENTS_SOURCE:?set AGENTS_SOURCE to AGENTS_AMFA_HERMES_V3.md}"
[[ -d "$REPO/.git" && -d "$PACKAGE_ROOT/goals" ]] || { echo "ERROR: invalid repository or package root" >&2; exit 1; }
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="${BACKUP_ROOT:-/home/ubuntu/amfa-package-backups}"
BACKUP="$BACKUP_ROOT/$STAMP"
if [[ -e "$REPO/goals" || -e "$REPO/AGENTS.md" ]]; then
  mkdir -p "$BACKUP"
  [[ ! -e "$REPO/goals" ]] || cp -a "$REPO/goals" "$BACKUP/"
  [[ ! -e "$REPO/AGENTS.md" ]] || cp -a "$REPO/AGENTS.md" "$BACKUP/AGENTS.md"
fi
rm -rf "$REPO/goals"
cp -a "$PACKAGE_ROOT/goals" "$REPO/goals"
cp "$AGENTS_SOURCE" "$REPO/AGENTS.md"
(cd "$REPO" && python3 goals/validation/validate_package.py)
echo "Installed V3 package. Backup (when needed): $BACKUP"
