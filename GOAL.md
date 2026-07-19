# G04 — Stage Validation, G09/G12 Gates, Sealing, and Copy-Forward

## Identity

| Field | Value |
|-------|-------|
| Folder | `04-stage-validation-seal` |
| Base branch | `goal` (`d759861...`) |
| Assigned branch | `hermes/04-stage-validation-seal` |
| Worktree | `/home/ubuntu/amfa-worktrees/04-stage-validation-seal` |
| External runtime | `/home/ubuntu/amfa-runtime/04-stage-validation-seal` |
| Backend / frontend | `8304` / `3304` |
| Jira features | AMFA-149, AMFA-150, AMFA-151, AMFA-152, AMFA-153 |
| Jira subtasks | 20 tasks (AMFA-190 through AMFA-209) |

## Objective

Implement five bounded capabilities for the Angular Migration control plane:

1. **S3-F10** — Final clean install and deterministic static checks
2. **S3-F11** — Stage build matrix execution and inspection
3. **S3-F12** — Stage test suite and conditional lint
4. **S3-F13** — Parity comparison, assurance aggregation, and G09 validation gate
5. **S3-F14** — G12 seal gate, stage cleanup, copy-forward, and parameterized stage loop

All backed by deterministic domain services, SQLite state/events, immutable checksum-bound artifacts, and frontend projections. No automated G09/G12 bypass. No duplicate of upstream Sprint 2 or Goal 01/03 capabilities.

## Feature coverage

| Backlog feature | Jira | Title | Dependencies |
|-----------------|------|-------|--------------|
| S3-F10 | AMFA-149 | Run final clean install and deterministic static checks | S3-F09 |
| S3-F11 | AMFA-150 | Run and inspect the required stage build matrix | S3-F10 |
| S3-F12 | AMFA-151 | Run complete stage tests and conditional lint | S3-F11 |
| S3-F13 | AMFA-152 | Compare parity evidence, display assurance, and decide G09 | S3-F10, S3-F11, S3-F12 |
| S3-F14 | AMFA-153 | Seal G12, copy forward, parameterized stage engine | S3-F13 |

## Implementation plan

Execute tasks in TASK_INDEX.md order. Each Jira subtask follows the mandated subagent cycle:
planner → implementer → reviewer → conditional fixer/re-review.

### Phase 1 — S3-F10 Final install + static checks (AMFA-190–193)
- Domain: `ValidationService` with install/static boundary, npm-ci command, TS/template/import check adapters
- DB/API/Events: Models, routes, transitions, artifact hooks
- Frontend: Install/static check panel and event projections
- Tests: Unit, API, component, security, regression

### Phase 2 — S3-F11 Build matrix (AMFA-194–197)
- Domain: `StageBuildService`, per-target build execution, matrix aggregation
- DB/API/Events: Build records, result persistence, STAGE_BUILD events
- Frontend: Build matrix display, streaming status
- Tests: Full coverage

### Phase 3 — S3-F12 Stage tests + lint (AMFA-198–201)
- Domain: `StageTestService`, test suite execution, conditional lint
- DB/API/Events: Test records, failures, STAGE_TESTS events
- Frontend: Test result panel, lint status, failure details
- Tests: Full coverage

### Phase 4 — S3-F13 Parity/comparison + G09 (AMFA-202–205)
- Domain: `RouteComparisonService`, `BackendIntegrationComparisonService`, `AssuranceAggregator`
- DB/API/Events: Assurance dimensions, G09 gate model, PARITY_COMPARISON events
- Frontend: Assurance dashboard, G09 decision panel
- Tests: Full coverage

### Phase 5 — S3-F14 Seal + copy-forward (AMFA-206–209)
- Domain: `StageCompletionService`, `StageCopyForwardService`, G12 gate
- DB/API/Events: G12 model, stage output fingerprints, next-stage sandbox
- Frontend: Seal/cleanup panel, G12 decision panel, stage loop display
- Tests: Full coverage

### Phase 6 — Capability closeout
- C90: Integration contract tests
- C91: Independent manual runtime validation
- C92: As-built documentation
- C93: Final audits, completion, and push

## Reuse boundaries

**Reuse existing** from the `goal` branch:
- `BaselineValidationApplicationService` — pattern reference, not copy
- `BaselineParityApplicationService` — pattern reference, not copy
- `BaselineTargetDiscoveryService` — target discovery pattern
- `BaselineFailureFingerprintService` — fingerprinting pattern
- `StateTransitionService` — transition authority
- `LocalFilesystemArtifactStore` — artifact authority
- `CommandPolicy`/`ExecutionWorker` — execution authority
- Existing DB models: `MigrationRunModel`, `BaselineQualificationModel`, `BaselineValidationModel`, `WorkflowEventModel`

**Do NOT duplicate** from upstream:
- Sprint 2 feature work (S2-F01 through S2-F09)
- Goal 01 Command Runtime
- Goal 03 Angular Transform Review
- Parallel state/event/artifact authorities

## Architecture patterns

```
Backend route handler → Application service → Domain service
  → Repository (SQLAlchemy) + Transition Service (state/events)
  → Artifact Store (immutable evidence)
  → Frontend via SSE events + GET projections
```

- One authoritative path per operation
- State version gating for all mutations
- Idempotency key for all mutations (replay returns original)
- Immutable artifact SHA-256 registration before state advancement
- G09/G12 are persistent gate records bound to state version + artifact checksum + plan version + workspace fingerprint
- No automated gate bypass; human decision required
- Copy-forward re-resolves exact versions before each new stage

## Completion criteria

- All 20 Jira subtask review cycles pass (PASS)
- C90 contract/integration tests pass
- Automated tests pass for all features
- Manual runtime validation passes
- As-built documentation complete
- Both final auditors PASS
- Shared/database changes recorded
- `branch_ready=true` in `evidence/completion.json`
- Only `hermes/04-stage-validation-seal` branch pushed
- `integration_verified=true` only after integrated evidence with other goals
