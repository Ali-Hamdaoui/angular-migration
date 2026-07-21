# AMFA Sprint 3–4 Hermes Goal System V3

This package converts all authoritative Sprint 3 and Sprint 4 backlog work into ten bounded capability goals for isolated Hermes worktree sessions.

- Base branch: `goal` (must already exist remotely)
- Goal branches: `hermes/01-*` through `hermes/10-*`
- Worktree root: `/home/ubuntu/amfa-worktrees`
- Runtime root: `/home/ubuntu/amfa-runtime` (outside Git)
- Jira coverage: 29 feature issues and 116 bounded implementation subtasks
- Sprint 2: read-only upstream dependency owned by another developer
- Goal 10: two phases—branch-local acceptance harness, then integrated 18→21 proof

## Install

1. Place the V3 `AGENTS.md` at the repository root.
2. Copy this `goals/` directory into `/home/ubuntu/angular-migration/goals`.
3. Run `python3 goals/validation/validate_package.py`.
4. Run `goals/scripts/prepare-base-branch.sh` and `goals/scripts/check-vm-readiness.sh`.
5. Run `goals/scripts/create-worktrees.sh` once to freeze the base SHA and create/validate all worktrees.
6. Launch each Hermes session from its assigned worktree with the local terminal backend and the command in `goals/launch-commands/`.

Do not reuse V1/V2 files. Read `V2_FINAL_AUDIT_AND_V3_CORRECTIONS.md` for corrected defects and `shared/GOAL10_TWO_PHASE_PROTOCOL.md` for the integrated-proof boundary.
