# Worktree, Branch, and Runtime Rules

- Base branch: `goal`.
- Base checkout: `/home/ubuntu/angular-migration`.
- Worktrees: `/home/ubuntu/amfa-worktrees/<goal-folder>`.
- Runtime: `/home/ubuntu/amfa-runtime/<goal-folder>`.
- Goal branches: exactly those in `GOAL_INDEX.yaml`.

At launch verify:

```bash
pwd
git rev-parse --show-toplevel
git branch --show-current
git status --short
git rev-parse HEAD
cat /home/ubuntu/amfa-worktrees/.base-sha
git remote -v
```

A session never creates/switches/merges/rebases branches or edits another worktree. It may push its assigned branch after branch completion is fully green.
