# G09 — Final Assurance, Delivery, Reporting, and G13–G15

## Identity

| Field | Value |
|---|---|
| Folder | `09-assurance-delivery-report` |
| Base branch | `goal` |
| Assigned branch | `hermes/09-assurance-delivery-report` |
| Worktree | `/home/ubuntu/amfa-worktrees/09-assurance-delivery-report` |
| External runtime | `/home/ubuntu/amfa-runtime/09-assurance-delivery-report` |
| Backend / frontend | `8309` / `3309` |
| Jira features | AMFA-222, AMFA-223, AMFA-224 |
| Jira subtasks | 12 tasks |

## Objective

Run independent final assurance, decide G13, create and atomically publish the delivery candidate through G14, then generate deterministic evidence reporting with optional narrative and G15.

## Feature coverage

| Backlog feature | Jira | Title | Exact backlog dependencies |
|---|---|---|---|
| S4-F12 | AMFA-222 | Run independent final assurance and decide G13 | S3-F14, S4-F08, S4-F10 |
| S4-F13 | AMFA-223 | Create a delivery candidate and publish atomically through G14 | S4-F12 |
| S4-F14 | AMFA-224 | Generate the deterministic evidence report, optional AI narrative, and decide G15 | S4-F11, S4-F13 |

## Goal dependencies

- `G04`
- `G07`
- `G08`

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

Use `/home/ubuntu/amfa-runtime/09-assurance-delivery-report` and ports 8309/3309. Run exact manual cases in `manual-tests/` after automated green. Full Angular fixtures must be generated outside Git and submitted through production APIs.

## Documentation and audits

Generate as-built docs only after runtime green, then run the two independent final audits. Correct implementation/docs and rerun affected tests until both pass.

## Completion and push

Validate `evidence/completion.json` against `goals/shared/contracts/goal_completion.schema.json`. Push only `hermes/09-assurance-delivery-report` when `branch_ready=true`, all intended changes are committed, and the worktree is clean. `integration_verified` remains false until integration evidence exists.

```bash
git push --set-upstream origin hermes/09-assurance-delivery-report
```

Never push protected branches, merge, rebase, cherry-pick, force-push, edit Jira, or modify another worktree.
