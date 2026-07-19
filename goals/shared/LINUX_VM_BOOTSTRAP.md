# Linux VM Bootstrap and Test Boundary

Required tools: Bash, Git, Python 3 with `venv`/pip, Node.js, npm, Hermes, curl, unzip, rsync, SHA-256 utility, and sufficient disk. Chromium/Playwright dependencies are required for applicable frontend manual evidence. SQLite CLI is recommended for evidence inspection.

The source repository contains Windows PowerShell developer scripts. On Ubuntu, do not assume those scripts execute. Read their behavior and provide/execute Linux-equivalent commands without weakening contracts.

Canonical backend setup is discovered from `backend/pyproject.toml`. Create an isolated virtual environment per worktree or a read-only shared package cache plus per-worktree venv. Run tests from repository root with explicit import path when required: `PYTHONPATH="$PWD:$PWD/backend" python3 -m pytest backend/tests`.

Frontend dependencies remain worktree-local or use a safe content-addressed package cache. Do not share mutable `node_modules` among worktrees. All full Angular fixtures are generated beneath the goal's external runtime root and enter the system through production intake APIs.
