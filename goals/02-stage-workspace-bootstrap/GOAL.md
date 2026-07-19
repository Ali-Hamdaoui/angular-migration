# G02 — Stage Workspace, G07, and Bootstrap

## Identity

| Field | Value |
|---|---|
| Folder | `02-stage-workspace-bootstrap` |
| Base branch | `goal` |
| Assigned branch | `hermes/02-stage-workspace-bootstrap` |
| Worktree | `/home/ubuntu/amfa-worktrees/02-stage-workspace-bootstrap` |
| External runtime | `/home/ubuntu/amfa-runtime/02-stage-workspace-bootstrap` |
| Backend / frontend | `8302` / `3302` |
| Jira features | AMFA-144, AMFA-145 |
| Jira subtasks | 8 tasks |

## Objective

Create the dedicated run-scoped stage sandbox, bind and decide G07, and perform the authorized bootstrap clean installation without mutating the external source or reusing generated dependencies.

## Feature coverage

| Backlog feature | Jira | Title | Exact backlog dependencies |
|---|---|---|---|
| S3-F05 | AMFA-144 | Prepare a dedicated run-scoped stage sandbox and decide G07 stage start | S2-F07, S3-F04 |
| S3-F06 | AMFA-145 | Run the stage bootstrap clean install | S3-F05 |

## Goal dependencies

- `G01`
- `S2-F07`

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

Use `/home/ubuntu/amfa-runtime/02-stage-workspace-bootstrap` and ports 8302/3302. Run exact manual cases in `manual-tests/` after automated green. Full Angular fixtures must be generated outside Git and submitted through production APIs.

## Documentation and audits

Generate as-built docs only after runtime green, then run the two independent final audits. Correct implementation/docs and rerun affected tests until both pass.

## Completion and push

Validate `evidence/completion.json` against `goals/shared/contracts/goal_completion.schema.json`. Push only `hermes/02-stage-workspace-bootstrap` when `branch_ready=true`, all intended changes are committed, and the worktree is clean. `integration_verified` remains false until integration evidence exists.

```bash
git push --set-upstream origin hermes/02-stage-workspace-bootstrap
```

Never push protected branches, merge, rebase, cherry-pick, force-push, edit Jira, or modify another worktree.
