# G04 — Stage Validation, G09, G12, and Copy-Forward

## Identity

| Field | Value |
|---|---|
| Folder | `04-stage-validation-seal` |
| Base branch | `goal` |
| Assigned branch | `hermes/04-stage-validation-seal` |
| Worktree | `/home/ubuntu/amfa-worktrees/04-stage-validation-seal` |
| External runtime | `/home/ubuntu/amfa-runtime/04-stage-validation-seal` |
| Backend / frontend | `8304` / `3304` |
| Jira features | AMFA-149, AMFA-150, AMFA-151, AMFA-152, AMFA-153 |
| Jira subtasks | 20 tasks |

## Objective

Run final installation and static checks, complete build/test/lint/parity validation, decide G09, seal through G12, and reuse one parameterized stage engine for 18→19→20→21 copy-forward.

## Feature coverage

| Backlog feature | Jira | Title | Exact backlog dependencies |
|---|---|---|---|
| S3-F10 | AMFA-149 | Run final clean install and deterministic static checks | S3-F09 |
| S3-F11 | AMFA-150 | Run and inspect the required stage build matrix | S3-F10 |
| S3-F12 | AMFA-151 | Run complete stage tests and conditional lint | S3-F11 |
| S3-F13 | AMFA-152 | Compare parity evidence, display assurance, and decide G09 validation acceptance | S3-F10, S3-F11, S3-F12 |
| S3-F14 | AMFA-153 | Seal G12, copy forward, and reuse the parameterized stage engine through Angular 21 | S3-F13 |

## Goal dependencies

- `G03`

All ten sessions may begin together using frozen contracts. Do not absorb unavailable dependencies. Branch-local completion and integrated completion are separate as defined in root `AGENTS.md`.

## Required reading order

1. Root `AGENTS.md`.
2. `goals/shared/ARCHITECTURE.md`, `UPSTREAM_SPRINT2_BOUNDARY.md`, `PARALLEL_EXECUTION.md`, `RUNTIME_ISOLATION.md`, `HERMES_RUNTIME_POLICY.md`, and `LIVE_REPOSITORY_VERIFICATION.md`.
3. `CURRENT_CODE_MAP.md`, `CROSS_GOAL_CONTRACTS.md`, `SOURCE_CONTRACT.md`, `JIRA.md`, `ACCEPTANCE.md`, `OWNERSHIP.yaml`, and `MANUAL_TEST_PLAN.md`.
4. Every file in `tasks/` in `TASK_INDEX.md` order.
5. Applicable shared coding/testing/security/database/API/documentation/completion standards.
6. Live code/tests/docs on the assigned branch.

## Startup and planning

Create `evidence/current-state-gap-map.json`, `dependency-status.json`, and planned `shared-file-changes.json` before production edits. Reuse existing code; do not add parallel authorities. Verify the frozen contracts consumed/provided by this goal.

## Implementation

Execute every Jira task. Each task follows planner → sole implementer → independent reviewer → conditional fixer/re-review on FAIL. Keep the implementation vertical: backend/domain, persistence/API/events/artifacts, frontend/SSE, tests/security, and exact acceptance evidence.

## Runtime and manual validation

Use `/home/ubuntu/amfa-runtime/04-stage-validation-seal` and ports 8304/3304. Run exact manual cases in `manual-tests/` after automated green. Full Angular fixtures must be generated outside Git and submitted through production APIs.

## Documentation and audits

Generate as-built docs only after runtime green, then run the two independent final audits. Correct implementation/docs and rerun affected tests until both pass.

## Completion and push

Validate `evidence/completion.json` against `goals/shared/contracts/goal_completion.schema.json`. Push only `hermes/04-stage-validation-seal` when `branch_ready=true`, all intended changes are committed, and the worktree is clean. `integration_verified` remains false until integration evidence exists.

```bash
git push --set-upstream origin hermes/04-stage-validation-seal
```

Never push protected branches, merge, rebase, cherry-pick, force-push, edit Jira, or modify another worktree.
