# G08 — Startup Reconciliation and Migration Assistant

## Identity

| Field | Value |
|---|---|
| Folder | `08-reconciliation-assistant` |
| Base branch | `goal` |
| Assigned branch | `hermes/08-reconciliation-assistant` |
| Worktree | `/home/ubuntu/amfa-worktrees/08-reconciliation-assistant` |
| External runtime | `/home/ubuntu/amfa-runtime/08-reconciliation-assistant` |
| Backend / frontend | `8308` / `3308` |
| Jira features | AMFA-220, AMFA-221 |
| Jira subtasks | 8 tasks |

## Objective

Reconcile interrupted commands, leases, artifacts, workspaces, and LangGraph checkpoints at startup, then provide a read-only evidence-grounded Migration Assistant over authoritative state.

## Feature coverage

| Backlog feature | Jira | Title | Exact backlog dependencies |
|---|---|---|---|
| S4-F10 | AMFA-220 | Reconcile interrupted commands, leases, artifacts, and graph state on startup | S3-F04, S3-F14, S4-F09 |
| S4-F11 | AMFA-221 | Explain authoritative migration state through the AI Assistant | S2-F03, S4-F10 |

## Goal dependencies

- `G01`
- `G04`
- `G07`
- `S2-F03`

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

Use `/home/ubuntu/amfa-runtime/08-reconciliation-assistant` and ports 8308/3308. Run exact manual cases in `manual-tests/` after automated green. Full Angular fixtures must be generated outside Git and submitted through production APIs.

## Documentation and audits

Generate as-built docs only after runtime green, then run the two independent final audits. Correct implementation/docs and rerun affected tests until both pass.

## Completion and push

Validate `evidence/completion.json` against `goals/shared/contracts/goal_completion.schema.json`. Push only `hermes/08-reconciliation-assistant` when `branch_ready=true`, all intended changes are committed, and the worktree is clean. `integration_verified` remains false until integration evidence exists.

```bash
git push --set-upstream origin hermes/08-reconciliation-assistant
```

Never push protected branches, merge, rebase, cherry-pick, force-push, edit Jira, or modify another worktree.
