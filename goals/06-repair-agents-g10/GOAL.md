# G06 — Repair Proposer, Reviewer, and G10

## Identity

| Field | Value |
|---|---|
| Folder | `06-repair-agents-g10` |
| Base branch | `goal` |
| Assigned branch | `hermes/06-repair-agents-g10` |
| Worktree | `/home/ubuntu/amfa-worktrees/06-repair-agents-g10` |
| External runtime | `/home/ubuntu/amfa-runtime/06-repair-agents-g10` |
| Backend / frontend | `8306` / `3306` |
| Jira features | AMFA-214, AMFA-215, AMFA-216 |
| Jira subtasks | 12 tasks |

## Objective

Implement the checksum-bound Repair Proposer, independent non-authoring Repair Reviewer, reviewed proposal persistence, and human G10 Apply/Reject package through the existing governed Azure gateway.

## Feature coverage

| Backlog feature | Jira | Title | Exact backlog dependencies |
|---|---|---|---|
| S4-F04 | AMFA-214 | Generate a checksum-bound Repair Proposer candidate | S4-F03, S2-F03 |
| S4-F05 | AMFA-215 | Review the Repair Proposer candidate with a non-authoring Reviewer | S4-F04 |
| S4-F06 | AMFA-216 | Persist the reviewed proposal and decide G10 Apply or Reject | S4-F05 |

## Goal dependencies

- `G05`
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

Use `/home/ubuntu/amfa-runtime/06-repair-agents-g10` and ports 8306/3306. Run exact manual cases in `manual-tests/` after automated green. Full Angular fixtures must be generated outside Git and submitted through production APIs.

## Documentation and audits

Generate as-built docs only after runtime green, then run the two independent final audits. Correct implementation/docs and rerun affected tests until both pass.

## Completion and push

Validate `evidence/completion.json` against `goals/shared/contracts/goal_completion.schema.json`. Push only `hermes/06-repair-agents-g10` when `branch_ready=true`, all intended changes are committed, and the worktree is clean. `integration_verified` remains false until integration evidence exists.

```bash
git push --set-upstream origin hermes/06-repair-agents-g10
```

Never push protected branches, merge, rebase, cherry-pick, force-push, edit Jira, or modify another worktree.
