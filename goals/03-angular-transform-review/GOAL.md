# G03 — Exact Angular Transformation and G08

## Identity

| Field | Value |
|---|---|
| Folder | `03-angular-transform-review` |
| Base branch | `goal` |
| Assigned branch | `hermes/03-angular-transform-review` |
| Worktree | `/home/ubuntu/amfa-worktrees/03-angular-transform-review` |
| External runtime | `/home/ubuntu/amfa-runtime/03-angular-transform-review` |
| Backend / frontend | `8303` / `3303` |
| Jira features | AMFA-146, AMFA-147, AMFA-148 |
| Jira subtasks | 12 tasks |

## Objective

Execute the exact approved Angular major update, prove the resolved target version, capture the complete transformation diff, classify changed-file risk, and enforce human G08 acceptance.

## Feature coverage

| Backlog feature | Jira | Title | Exact backlog dependencies |
|---|---|---|---|
| S3-F07 | AMFA-146 | Execute the exact Angular update and verify the target version | S3-F06 |
| S3-F08 | AMFA-147 | Capture transformation diffs and classify changed-file risk | S3-F07 |
| S3-F09 | AMFA-148 | Review and decide G08 transformation acceptance | S3-F08 |

## Goal dependencies

- `G02`

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

Use `/home/ubuntu/amfa-runtime/03-angular-transform-review` and ports 8303/3303. Run exact manual cases in `manual-tests/` after automated green. Full Angular fixtures must be generated outside Git and submitted through production APIs.

## Documentation and audits

Generate as-built docs only after runtime green, then run the two independent final audits. Correct implementation/docs and rerun affected tests until both pass.

## Completion and push

Validate `evidence/completion.json` against `goals/shared/contracts/goal_completion.schema.json`. Push only `hermes/03-angular-transform-review` when `branch_ready=true`, all intended changes are committed, and the worktree is clean. `integration_verified` remains false until integration evidence exists.

```bash
git push --set-upstream origin hermes/03-angular-transform-review
```

Never push protected branches, merge, rebase, cherry-pick, force-push, edit Jira, or modify another worktree.
