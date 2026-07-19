# G10 — Angular 18→21 Acceptance Harness and Integrated Runtime Proof

## Identity

| Field | Value |
|---|---|
| Folder | `10-full-runtime-proof` |
| Base branch | `goal` |
| Assigned branch | `hermes/10-full-runtime-proof` |
| Worktree | `/home/ubuntu/amfa-worktrees/10-full-runtime-proof` |
| External runtime | `/home/ubuntu/amfa-runtime/10-full-runtime-proof` |
| Backend / frontend | `8310` / `3310` |
| Jira feature | AMFA-225 / S4-F15 |
| Jira subtasks | AMFA-282–285 |

## Objective

Build the reusable external acceptance harness in Phase A, then—only after Sprint 2 and G01–G09 are integrated—execute the complete Angular 18.0.x/18.2.x→19→20→21 production proof in Phase B.

## Required dependencies

S4-F15 depends on S4-F01–F14 plus S2-F03. Production proof also requires the approved plan boundary from Sprint 2 and the integrated goal branches. Frozen contracts permit Phase A to begin in parallel; they do not prove production behavior.

## Phase A — branch-local harness implementation

Implement only branch-owned harness capabilities defined by the four Jira task files:

- external temporary Angular fixture generation, with no full workspace committed to Git;
- passing, repairable, environment-blocked, slow/cancellable, and restart fixtures;
- safe real subprocess profiles and deterministic fake-model integration suite;
- acceptance-suite orchestration and immutable runtime evidence collector;
- contract/security tests against frozen schemas and consuming ports;
- optional read-only operator acceptance status endpoint/UI if justified by the backlog and existing architecture.

Do not implement duplicate CommandExecutor, stage engine, repair chain, assistant, assurance, delivery, or reporting services. Those are consumed during Phase B.

Phase A closes only as `harness_ready`; AMFA-225 remains incomplete. List every blocked integrated criterion explicitly.

## Phase B — integrated product proof

Run only on an integration branch containing required Sprint 2 and G01–G09 commits. Replace all test fakes with real production adapters. Exercise production APIs and the real external runtime layout for:

1. Angular 18.0.x and 18.2.x passing paths through 19, 20, and 21.
2. All applicable human gates and stale-state protection.
3. One real migration failure, FailureEvidence/C-Lite/RepairContextPack, Proposer, non-authoring Reviewer, G10, exact patch apply, normal validation, and G11.
4. Environment failure without a code patch and no-progress protection.
5. Cancellation and process-tree cleanup.
6. Backend restart, lease/checkpoint reconciliation, SSE reconnect/replay, and no duplicate side effects.
7. Assistant evidence-grounded answer and labelled deterministic fallback.
8. Independent final assurance/G13, candidate/G14 atomic publication, deterministic report/optional narrative/G15.
9. Source fingerprint unchanged and final output fingerprint/evidence complete.
10. Human product sign-off.

## Required workflow

For each Jira task: planner → sole implementer → independent reviewer → conditional fixer/re-review on FAIL. After applicable automated and manual validation, generate as-built documentation and run both final auditors.

## Completion and push

Validate `evidence/completion.json` against the V3 schema.

- Phase A push: `completion_level=harness_ready`, `branch_ready=true`, `harness_ready=true`, `integration_verified=false`, `jira_complete=false`.
- Phase B completion: `completion_level=integration_verified`, all tests/manual evidence/audits PASS, human sign-off approved, `integration_verified=true`, `jira_complete=true`.

Push only the assigned branch when Phase A branch-owned work is green:

```bash
git push --set-upstream origin hermes/10-full-runtime-proof
```

Never claim AMFA-225 complete from Phase A evidence.
