# Planning Agent end-to-end completion design

## Status

Approved in conversation on 2026-07-29.

This specification supersedes the completion boundary in
`2026-07-28-transformation-readiness-design.md`. The earlier design stopped
after the first stage command was queued. This design closes the full
code-truth audit through successful Angular 21 stage validation.

## Issue assessment

### Issue

- ID: no tracker ID supplied
- Title: Complete the Planning Agent and transformation-readiness audit
- Branch: `hermes/01-command-runtime`
- Starting SHA: `99b464a5f3bcaa9537695f46f5589ded163dfdb0`

### Expected behavior

Planning must produce checksum-bound deterministic plans, complete proposer and
reviewer processing, persist the versioned Planning/G06 package, and wait for
human approval. An approved current G06 must expose an explicit
checksum-bound Start transformation action. Starting a stage must prepare a
contained workspace and durably execute every approved command in order.
Command outcomes must update ordered stage steps, stop on failure, trigger
deterministic validation on success, and generate the next adjacent-major plan.
The same controlled loop must support Angular 18 to 19, 19 to 20, and 20 to 21.

### Current behavior

- `migration_run_service.py` does not compile because `get_state()` contains an
  unclosed `return {` before the actual `state` dictionary.
- Planning computes its deterministic checksum and proposer-output checksum but
  does not send either value as explicit trusted LLM context.
- `StageExecutionPlan.commands` is grouped in a dictionary without an
  authoritative execution sequence.
- Stage start creates pending step rows but flattens dictionary values and
  queues only the first command.
- Stage steps have no sequence or durable command-execution binding.
- Command completion persists evidence but does not advance its stage step,
  authorize the next command, validate the stage, or stop progression
  authoritatively.
- G06 approval has no frontend Start transformation control.
- No production loop produces the 19-to-20 and 20-to-21 stage plans.
- Command references do not carry the selected runtime profile checksum.
- No persisted three-stage dry run proves the complete boundary.

### Root cause

The implemented readiness slice established deterministic planning, command
authority, safe stage preparation, and first-command queueing. It did not
establish a persisted stage-continuation aggregate. Consequently, ordering,
step ownership, terminal callbacks, validation, and later-stage planning have
no single authoritative application service.

### Conclusion

Ready to implement as ordered vertical slices. The external source remains
read-only and no human approval gate is removed.

## Scope

The implementation covers audit patches P0 through P8:

1. Restore backend syntax and API importability.
2. Supply trusted Planning checksum tokens.
3. Make command order explicit and immutable.
4. Persist step/execution identity and implement durable continuation.
5. Expose an explicit Start transformation action after G06 approval.
6. Validate completed stages and plan later stages.
7. Bind runtime profiles and package-resolution evidence.
8. Prove the complete path with persisted integration coverage.

The work does not run an uncontrolled migration against an external user
workspace. Production execution continues to operate only on a contained
stage workspace through `CommandExecutorService`.

## Authority boundaries

- SQLite and `StateTransitionService` remain workflow truth.
- Deterministic services own plans, versions, validation, and completion facts.
- The Planning proposer and reviewer may explain and review deterministic
  evidence; they cannot create executable truth.
- G06 remains a mandatory stage-specific human gate.
- The stage-start endpoint is the only transformation-start mutation.
- `CommandExecutorService` remains the only process-execution path.
- `StageContinuationCoordinator` owns stage-step progression but never starts a
  subprocess directly.
- Artifacts remain immutable, registered, and checksum-bound.
- The external source remains read-only.
- No database transaction spans filesystem copies, registry calls, LLM calls,
  subprocess execution, or approval waits.

## Architecture

```text
deterministic migration + stage plan
                |
                v
Planning proposer/reviewer with trusted checksum tokens
                |
                v
pending stage-specific G06 --human approval-->
                |
                v
explicit Start transformation API/UI action
                |
                v
contained stage preparation + ordered persisted steps
                |
                v
StageContinuationCoordinator
                |
                v
policy authorization -> CommandExecutor -> immutable evidence
                |                                  |
                +<------- terminal outcome --------+
                |
                v
deterministic stage validation
                |
        +-------+--------+
        |                |
      failure       stage passed
        |                |
       stop       next route entry?
                         |
                   +-----+-----+
                   |           |
                  yes          no
                   |           |
              next plan/G06  final report
                              + COMPLETED
```

## Planning checksum binding

`PlanningAgentService.explain()` continues to compute checksums in the backend.
It adds trusted context segments whose content is a small canonical JSON
binding object, separate from the plan payload:

- `deterministic-plan-binding` contains the exact deterministic plan checksum.
- `proposer-output-binding` contains the exact proposer-output checksum for the
  reviewer.

The prompt policies instruct the model to copy these supplied values exactly.
The existing fail-closed equality checks remain. The proposer is not expected
to implement Python canonicalization, and the reviewer is not expected to hash
untrusted proposer JSON.

Tests must prove that the production-shaped request contains the exact tokens,
that a model which only copies supplied bindings succeeds, and that any changed
token is rejected.

## Explicit immutable execution order

`StageExecutionPlan` gains an `execution_steps` tuple. Each element includes:

- one-based `sequence`;
- stable step key and command group;
- complete `CommandTemplateReference`;
- conditional policy;
- expected runtime profile checksum.

The grouped `commands` projection may remain temporarily for API compatibility,
but it is derived from `execution_steps`. Runtime code must never infer order
from dictionary iteration. Serialization and reload must preserve the same
first, next, and final commands.

The standard sequence is:

1. bootstrap `npm ci`;
2. exact Angular/CLI update;
3. target-version verification;
4. final `npm ci`;
5. production build;
6. tests;
7. conditional lint.

## Persistence model

### Stage steps

`stage_steps` gains:

- `sequence`;
- `command_id`;
- `template_id`;
- `template_version`;
- `planned_command_checksum`;
- `conditional`;
- `attempt_count`;
- `current_execution_id`.

There is a unique constraint on `(stage_id, sequence)`. Step identity and
planned-command checksum are immutable after creation. Status, attempt count,
execution binding, and timestamps change only through the transition and
continuation services.

### Command executions

`command_executions` gains:

- `step_id`;
- `attempt_number`.

There is a unique constraint on `(step_id, attempt_number)` when a step is
present. This retains execution history while identifying the current attempt
from the stage step.

### Migration ancestry

The repository currently exposes two Alembic heads:
`20260727_19` and `20260728_32`. A merge revision first establishes one head.
The stage-continuation schema revision then descends from that merge. A fresh
upgrade and an upgrade from the existing schema are both required validation.

## Stage continuation coordinator

`StageContinuationCoordinator` is a focused application service with these
operations:

- initialize a prepared stage;
- queue the first eligible step;
- handle a committed terminal execution;
- reconcile terminal executions whose continuation was interrupted;
- validate the final step and finish the stage;
- start later-stage planning after a passed stage.

The coordinator selects a step by persisted sequence and status. It validates
the step's planned-command checksum against the active stage plan before every
authorization. It authorizes exactly one step and calls
`CommandExecutorService.queue_authorized_command()` with a deterministic key.
It never calls a worker or subprocess directly.

Deterministic operation keys include:

```text
<run>:<stage>:step:<sequence>:authorize
<run>:<stage>:step:<sequence>:attempt:<attempt>:queue
<execution>:terminal-continuation
<stage>:validate
<stage>:plan-next
```

Unique constraints and payload-identity checks make duplicate starts,
completions, and recovery calls converge on the original persisted result.

## Command lifecycle integration

When a queued execution starts, its bound step becomes `RUNNING` through
`StateTransitionService`. The worker performs the subprocess without an open
database transaction.

`CommandExecutorService` commits terminal status, artifacts, metadata, and the
terminal command event before continuation begins. After that commit, it calls
the coordinator in a new database transaction.

- Success marks the step `PASSED` and queues the next eligible step.
- Conditional lint becomes `SKIPPED` only when the immutable step policy says
  lint is unavailable.
- Failure marks the step and stage `FAILED`.
- Cancellation marks the step and stage `CANCELLED`.
- Timeout marks the step and stage `FAILED` with timeout evidence.
- No terminal failure authorizes or queues a later step.

If the process stops after the command commit but before the callback, a
reconciliation operation locates terminal stage executions without a matching
terminal-continuation event and invokes the same idempotent coordinator method.

## Deterministic stage validation

The last successful or explicitly skipped step invokes
`StageValidationService`. It performs read-only checks against persisted data
and the contained stage workspace:

- all required steps are terminal and acceptable;
- every executed step has an accepted authorization;
- required stdout, stderr, command-log, result, and manifest metadata is
  present and checksum-valid;
- result and manifest bindings match the step, stage plan, runtime profile, and
  execution;
- installed Angular core and CLI versions match the exact stage targets;
- required build and test executions passed;
- lint passed or was explicitly skipped by the plan;
- runtime profile checksum still matches the approved plan;
- dependency and lockfile changes are captured;
- completed workspace fingerprint is recorded;
- the registered external-source fingerprint is unchanged.

The service writes an immutable `stage-validation.json` report plus dependency,
lockfile, and workspace-fingerprint evidence. Only a passing report may move
the stage to `PASSED`.

## Later-stage planning

After a passed stage, `NextStagePlanningService`:

1. Reads the next route entry from the approved migration route.
2. Uses the completed stage workspace and fingerprint as the next stage input.
3. Resolves project scripts and targets from that workspace.
4. Resolves the exact stage-compatible runtime profile and checksum.
5. Resolves exact Angular/CLI versions from a versioned compatibility and
   package-registry snapshot.
6. Generates and persists the next `StageExecutionPlan`.
7. Runs the standard Planning proposer and reviewer with explicit trusted
   binding tokens.
8. Persists the next versioned Planning explanation and G06 package.
9. Creates a pending stage-specific G06 and waits.

The user must approve G06 and select Start transformation again. Human approval
is therefore explicit at every materially different stage plan.

After the Angular 21 stage passes, the service writes a route-completion report
and transitions the run to `COMPLETED`. It generates no further plan.

If later-stage Planning fails, the completed preceding stage remains passed.
The planning job records a retryable or terminal failure without reverting
valid stage evidence.

## Runtime and package binding

The selected execution profile checksum is stored at stage-plan level and
copied into every command reference and execution step. Start, authorization,
worker dispatch, terminal validation, and recovery all compare the current
profile to that checksum.

Exact Angular and CLI patch versions come from a versioned registry snapshot
that records package availability, integrity where available, support status,
and historical-bridge risk. Unsupported historical stages require explicit
catalogue evidence and risk acceptance; they are not silently treated as
currently supported.

## API and frontend

The existing endpoint remains authoritative:

```text
POST /api/v1/runs/{run_id}/stages/{stage_id}/start
```

Its read projection exposes:

- `start_permitted`;
- current gate version and decision;
- plan and stage-plan checksums;
- artifact-set checksum;
- workspace fingerprint;
- expected state version;
- existing preparation, authorization, and execution identifiers.

The Planning panel renders Start transformation only when the current G06 is
approved, no start exists for that plan, the authoritative projection is
connected, and all bindings are present. A `409` refreshes authoritative state
and displays the stale reason. The frontend never substitutes new checksum
values or silently retries a stale mutation.

The stage projection displays steps in persisted sequence order with command
identity, attempt, current execution, status, and evidence links. Reconnect
uses the authoritative projection and cannot duplicate progression.

## Error and transaction boundaries

- Planning checksum mismatch creates no G06.
- Runtime-profile or package-evidence mismatch prevents stage start.
- Sandbox-copy or fingerprint failure creates no prepared stage success state.
- Persistence failure after sandbox finalization invokes existing cleanup or
  quarantine behavior.
- Authorization rejection blocks the step and queues nothing.
- Command failure, timeout, or cancellation stops the stage.
- Stage-validation failure prevents later-stage planning.
- Duplicate mutations return the original persisted result when payload
  identity matches and reject conflicting reuse.
- Filesystem, LLM, registry, and subprocess side effects occur outside database
  transactions.

Errors expose stable codes, safe correlation data, and evidence identifiers.
They do not persist prompts, secrets, unrestricted environment data, or raw
provider payloads.

## Verification design

Every production behavior is introduced through a failing regression test.

### Backend health

- `python -m compileall -q app`
- API import and test collection
- focused migration-run service tests

### Planning binding

- proposer receives exact trusted deterministic checksum;
- reviewer receives exact trusted deterministic and proposer checksums;
- copy-only controlled transports reach accepted review;
- changed bindings fail closed;
- all six versioned Planning/G06 artifacts are registered.

### Ordering and persistence

- serialized/reloaded plan retains exact sequence;
- bootstrap is always first;
- schema constraints reject duplicate stage sequences and attempts;
- projection orders steps by sequence;
- runtime-profile checksum is present and enforced.

### Continuation

- success queues only the next step;
- duplicate completion queues nothing twice;
- failure, timeout, and cancellation stop progression;
- each command receives an independent accepted authorization;
- step lifecycle follows command lifecycle;
- conditional lint is explicitly skipped;
- interrupted callbacks are reconciled safely;
- final success invokes validation.

### Later stages

- 18-to-19 success creates a 19-to-20 plan from the completed workspace;
- 19-to-20 success creates a 20-to-21 plan;
- failed stages create no later plan;
- every later plan requires a new G06 and explicit start;
- Angular 21 validation completes the route.

### Persisted dry run

One integration scenario uses:

- real SQLite persistence and migrations;
- real transition, artifact, command-policy, queue, coordinator, and validation
  services;
- a controlled Planning gateway that copies supplied trusted tokens and does
  not perform hidden checksum calculations;
- a controlled process adapter that produces deterministic outcomes while
  exercising the production executor lifecycle;
- explicit G06 approval and Start action for all three stages;
- exact assertions for state versions, events, steps, authorizations,
  executions, artifacts, stage reports, next-stage plans, and final completion.

### Frontend and regression checks

- API client contract test;
- start-control hook and component tests;
- stale and duplicate submission tests;
- TypeScript check;
- lint;
- production build;
- focused backend suites;
- full backend suite;
- `git diff --check`;
- fresh and existing-database migration upgrades.

Live package-registry verification is reported separately from deterministic
test proof. A manual recipe covers execution against a fresh real Angular 18
fixture without treating that optional environment check as unit evidence.

## Delivery slices

1. P0: syntax repair and importability.
2. P1: trusted Planning checksum tokens and G06 artifact proof.
3. P2: explicit sequence and runtime-profile checksum.
4. P3: persistence migration and durable coordinator.
5. P4: explicit API/frontend start control.
6. P5: deterministic validation and later-stage planning.
7. P6/P7: runtime and registry evidence enforcement.
8. P8: three-stage persisted dry run and manual acceptance recipe.

Each slice receives focused regression validation before the next begins.

## Risks and mitigations

- **Migration divergence:** merge current Alembic heads and test both fresh and
  existing upgrades.
- **Duplicate continuation:** deterministic keys, unique constraints, and
  payload-identity checks.
- **Crash after terminal commit:** persisted terminal event plus idempotent
  reconciliation.
- **Filesystem/database split:** finalize artifacts before success persistence;
  clean or quarantine failed finalization.
- **Runtime drift:** checksum profile at plan, command, authorization, worker,
  and validation boundaries.
- **Historical package availability:** versioned registry evidence and explicit
  risk, never an unsupported assumption.
- **Large service coupling:** keep planning review, continuation, validation,
  and later-stage planning as separate application services.

## Out of scope

- Removing or bypassing approval gates.
- Executing shell strings or bypassing command policy.
- Mutating the external source workspace.
- Automatically applying Repair Proposer diffs.
- Claiming a real user application migrated successfully from controlled test
  fixtures alone.
- Unrelated workflow or frontend refactoring.
