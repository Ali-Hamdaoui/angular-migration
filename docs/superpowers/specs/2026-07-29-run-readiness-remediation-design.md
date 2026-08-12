# Run readiness remediation design

## Status

Approved in conversation on 2026-07-29.

This design repairs the evidence and planning defects reproduced by
`run-16a48fc55de7`. That run remains the immutable forensic reference. The
repairs are proven with a fresh database and fresh migration run.

This design stops at the Planning/Transformation boundary. Completion means a
fresh run has a current human-approved G06 and has not started transformation.
Transformation execution, stage continuation, and the Transformation Agent
remain the next development phase.

## Issue assessment

### Issue

- ID: no tracker ID supplied
- Title: Repair all audited gaps before Transformation Agent development
- Branch: `hermes/01-command-runtime`
- Starting SHA: `836f1e99b964bc980e4bed4246b4fbfbb430f02e`

### Expected behavior

The controlled migration pipeline must produce internally consistent,
checksum-bound evidence from source intake through Planning. Baseline facts
must describe the commands that actually ran. Discovery must distinguish
static evidence from unresolved expressions. Planning must derive executable
facts only from deterministic evidence, persist safe proposer/reviewer
outcomes, create valid stage-scoped records, and stop at a current G06 human
gate. A fresh run must reach approved G06 with clean artifact and database
integrity and without creating a transformation workspace or queuing a
transformation command.

### Reproduced current behavior

The audited run proved the following defects:

1. Baseline summary reports lint as passed even though lint is not configured.
2. The stage plan resolves a nonexistent `lint` script and includes
   `npm run lint`.
3. The Jest parser reports two tests although the command log reports 14 tests
   in two suites.
4. `npm ci` reports 86 vulnerabilities, including four critical findings, but
   the baseline and final analysis do not surface them.
5. Backend integration evidence misses literal
   `https://jsonplaceholder.typicode.com/users` references and labels the
   relevant files dynamic or unresolved.
6. Sensitive-file evidence includes noisy control and editor files and marks
   all findings as behavior-sensitive.
7. Six stage-scoped artifact rows violate the
   `artifact_metadata.stage_id -> migration_stages.id` foreign key because the
   parent stage row does not exist.
8. The Planning reviewer did not accept the explanation, but the proposer and
   reviewer decision details were not preserved.
9. A review rejection becomes a non-retryable `technical_failed` job and a
   generic `planning-input-resolution-failure.json` artifact.
10. Run status remains `PLANNING_RUNNING` after `PLANNING_FAILED`, and the
    failure reason says planning failed before plan creation even though the
    migration and stage plans already exist.
11. The six versioned Planning/G06 artifacts are absent and G06 is blocked.

### Conclusion

Ready to implement as four ordered repair slices followed by a fresh-run
readiness proof.

## Authority and immutability

- SQLite and `StateTransitionService` remain workflow truth.
- Deterministic services own baseline, discovery, plan, validation, and
  readiness facts.
- LLM agents may explain and review deterministic evidence but cannot create or
  change executable truth.
- Artifact payloads remain immutable and checksum-bound.
- `run-16a48fc55de7` artifact payloads, events, gate decisions, and failure
  outcome are not rewritten.
- A schema/data migration may add missing parent `migration_stages` rows when
  that is required to restore declared referential integrity. It must not
  alter existing artifact payloads or checksums.
- The external Angular source remains read-only.
- G02, G03, G04, G05, and G06 remain mandatory human gates.
- No transformation start endpoint is called by the readiness proof.

## Architecture

```text
source snapshot
      |
      v
baseline execution ---------> exact status/count/security evidence
      |
      v
discovery/parity -----------> static endpoints + bounded manual unknowns
      |
      v
Analysis + G04
      |
      v
feasibility + G05
      |
      v
deterministic plan ---------> planned migration stage parent
      |
      v
Planning proposer/reviewer -> accepted or durable governed revision outcome
      |
      v
versioned Planning package + pending G06
      |
      v
human G06 approval
      |
      v
READINESS_COMPLETE (stop; transformation not started)
```

## Repair slice 1: baseline evidence correctness

### Status aggregation

Baseline aggregation preserves authoritative target vocabulary:

- an executed successful target is `passed`;
- missing lint is `skipped_not_configured`;
- a reused canonical target is `skipped_not_applicable`;
- aggregate summaries must not convert skipped outcomes to `passed`.

`baseline_summary.json`, `baseline_qualification.json`, and API projections
must agree with the per-kind reports. A missing optional lint target may still
allow qualification under policy, but the stored lint fact remains
`skipped_not_configured`.

### Jest count parsing

The parser reads the `Tests:` line for test cases and the `Test Suites:` line
for suite count. The baseline target result stores the test-case count. Tests
cover singular/plural forms, comma-separated counts, failed tests, and output
that contains only a suite summary.

### Dependency security evidence

Install output parsing produces a structured immutable dependency-security
artifact containing:

- total vulnerability count;
- low, moderate, high, and critical counts;
- parser confidence;
- source command/execution identifiers;
- whether the result is a known baseline risk or a policy blocker.

The evidence is included in the baseline package and Analysis inputs. The
qualification policy decides whether findings block, require explicit human
risk acceptance, or remain known baseline failures. The platform must never
silently report a clean baseline when the install evidence contains
vulnerabilities.

Raw audit text remains a command artifact. The structured artifact does not
execute `npm audit fix`, modify dependencies, or claim vulnerabilities are
resolved.

## Repair slice 2: discovery and parity accuracy

### Static backend integration references

The backend integration scanner extracts literal `http://` and `https://`
strings from TypeScript and configuration sources. A file is marked dynamic or
unresolved only when an endpoint expression cannot be statically resolved.
Literal endpoints and unresolved expressions may coexist in the same file and
must be represented separately.

The `user.service.ts` fixture must produce the JSONPlaceholder API root and no
false dynamic-endpoint unknown for the literal calls.

### Sensitive-file classification

The scanner uses bounded file categories:

- application runtime/configuration;
- dependency/build configuration;
- test code;
- editor/repository metadata;
- generated evidence/control files.

Only application and dependency/build files with behavior-relevant indicators
are `behavior_sensitive_requires_review`. Editor metadata, `.git` content, and
generated source manifests are excluded from behavior-sensitive findings.
Test-only references remain visible but are labelled test evidence.

### Parity result

`manual_validation_required` is true only when bounded unresolved evidence or a
policy-defined manual check remains. `proof_label` and confidence fields must
agree with the actual unknown list. Analysis receives both proven static facts
and remaining unknowns and must not restate a static URL as dynamic.

## Repair slice 3: deterministic Planning and persistence

### Script-aware stage plan

Planning reads package scripts and baseline target resolution from the approved
G05 input bundle.

- `resolved_scripts` contains only scripts proven to exist.
- Build and test commands reference their proven scripts/targets.
- If lint is unavailable, no executable `npm run lint` command is generated.
- Validation records lint as explicitly not configured.
- Every generated executable command remains a structured catalogue reference
  with `shell=false`, a bounded timeout, an approved network profile, a
  contained working-directory alias, and the selected runtime-profile
  checksum.

### Planned migration-stage parent

Before stage-scoped artifacts are registered, Planning creates or idempotently
reuses a `MigrationStageModel` parent with:

- the logical stage ID;
- the owning run;
- deterministic stage order;
- source and target families;
- exact resolved source and target versions where available;
- status `PLANNED`;
- no started or completed timestamp.

Stage start later reuses and transitions this row instead of creating a
conflicting parent. A migration backfills missing planned parents for existing
stage-plan artifacts and verifies ownership before inserting them.

Fresh and upgraded databases must return:

```text
PRAGMA integrity_check = ok
PRAGMA foreign_key_check = no rows
```

### Artifact registration

Planning persists the migration plan and first adjacent-major stage plan only
after their domain models, internal checksums, workspace fingerprint,
execution-profile binding, and parent stage are valid. Artifact filesystem
finalization occurs before success persistence. Failed finalization creates no
successful plan transition.

## Repair slice 4: Planning review and G06 recovery semantics

### Durable review outcomes

Planning proposer and reviewer invocations are persisted independently from
the final acceptance transaction. Safe structured outputs, checksum bindings,
usage, decision, notes, policy concerns, and confidence survive a reviewer
decision of `request_revision`, `reject`, or `insufficient_context`.

Raw prompts, secrets, and unrestricted provider payloads are not persisted.

### Outcome classification

- `accept`: persist the final Planning package and create pending G06.
- `request_revision`: persist a governed revision-required outcome and allow
  one bounded proposer revision using the recorded reviewer notes.
- `reject`: persist a terminal reviewed rejection; no G06 is created.
- `insufficient_context`: persist a blocked evidence outcome with safe missing
  context information; no G06 is created.
- gateway, persistence, or contract failure: classify as technical failure with
  accurate retryability.

A model decision is not an input-resolution failure. Diagnostic artifact names
and event reasons identify the actual stage and outcome.

### State consistency

Run status, phase status, approval status, planning-job status, review status,
and final workflow events are updated through one authoritative transition
path.

- A revision-required review waits for governed revision.
- A reviewed rejection is terminal for that plan version.
- A retryable technical failure records its next attempt.
- A terminal technical failure sets the run/phase failure projection.
- Failure messages never claim plan creation failed when plan rows exist.

API projections return the latest state/event versions rather than the
pre-review bootstrap versions.

### Accepted review artifacts

Only an accepted current review creates these immutable versioned artifacts:

1. `planning-input-manifest.json`
2. `planning-proposer-output.json`
3. `planning-reviewer-output.json`
4. `planning-explanation.json`
5. `planning-usage-cost.json`
6. `g06-package.json`

The G06 package binds the approved prerequisite artifact set, migration plan,
stage plan, workspace fingerprint, and plan version. Human approval must match
all current bindings.

## Fresh-run readiness proof

The failed audit run remains available for comparison. Verification uses a
fresh database upgraded to the single Alembic head and a fresh output root.

The proof performs:

1. Source intake and immutable snapshot.
2. Runtime resolution and G02 approval.
3. Baseline install/build/test/lint projection and G03 approval.
4. Discovery/parity capture and Analysis review.
5. G04 approval.
6. Feasibility resolution and G05 approval.
7. Deterministic plan and planned-stage persistence.
8. Planning proposer/reviewer acceptance.
9. Six-artifact G06 package creation.
10. Human G06 approval.
11. Final readiness inspection without calling stage start.

The live proof uses the configured governed gateway. A deterministic controlled
gateway integration test separately proves the same application path without
depending on provider variability.

## Acceptance criteria

### Artifact integrity

- Every registered artifact exists.
- Every payload has one valid metadata sidecar.
- Every payload checksum matches SQLite and its sidecar.
- No unregistered payloads or orphan sidecars exist.
- Every JSON payload parses without a BOM.
- Source snapshot manifest entries match size and SHA-256.

### Evidence semantics

- Missing lint remains `skipped_not_configured` in reports, summary, Analysis,
  and Planning.
- Jest reports 14 tests for the audited fixture.
- Dependency vulnerability totals are represented in structured baseline and
  Analysis evidence.
- Literal JSONPlaceholder endpoints are captured as static evidence.
- No editor, Git, or generated manifest file is classified as application
  behavior-sensitive.
- Remaining manual validation items are explicit and evidence-bound.

### Planning and database

- Migration and stage plans pass domain validation and internal checksums.
- The first stage has a valid `migration_stages` parent before artifact
  registration.
- All generated commands correspond to proven scripts and approved catalogue
  entries.
- Runtime-profile checksums are non-null and current.
- Database integrity and foreign-key checks pass.

### Review and gate

- Proposer and reviewer invocations retain safe durable evidence.
- Non-accepted decisions preserve decision and notes and create no G06.
- An accepted review creates exactly the six required artifacts.
- G06 is current, checksum-bound, and human approved.
- Planning job and run projections agree.

### Transformation boundary

- No stage start event exists.
- No stage sandbox is prepared.
- No transformation command is authorized or queued.
- No external source file changes.
- The final verdict is `READY_FOR_TRANSFORMATION_DEVELOPMENT`.

## Testing strategy

All production changes follow red-green-refactor:

1. Add a failing focused regression test for one reproduced defect.
2. Run it and confirm the expected failure.
3. Implement the smallest owner-local correction.
4. Run the focused test and related service suite.
5. Continue only after the slice is green.

Required verification includes:

- baseline domain/service/parser tests;
- parity scanner and Analysis input tests;
- Planning generation and review-evidence tests;
- stage-start compatibility tests for planned parent reuse;
- migration upgrade tests from fresh and current schemas;
- SQLite integrity and foreign-key checks;
- API route/projection tests;
- focused frontend tests if projections change;
- backend compile and import checks;
- full backend test suite;
- frontend typecheck, lint, tests, and production build;
- artifact inspection against a controlled fresh run;
- a live fresh run to approved G06 when the configured gateway is available;
- `git diff --check` and a final scope audit.

Environment-dependent failures are reported separately and are never converted
to passing evidence.

## Error handling and recovery

- Invalid baseline output produces bounded parser diagnostics and does not
  invent success.
- Unknown endpoint expressions remain explicit unknowns.
- Missing script evidence prevents command generation for that script.
- Stage-parent ownership conflict blocks artifact registration.
- Artifact finalization failure records no successful plan/review transition.
- Reviewer nonacceptance preserves the review outcome and creates no G06.
- Retryable gateway failure schedules a bounded retry; a terminal failure
  updates authoritative run state.
- Stale gate, plan, workspace, or artifact bindings fail closed.
- Duplicate requests replay only when their payload checksum matches.

## Delivery order

1. Baseline status, count, and dependency-security evidence.
2. Static endpoint and sensitive-file classification.
3. Script-aware plan generation and stage-parent persistence/migration.
4. Durable review outcomes, state consistency, and G06 artifact creation.
5. Controlled integration proof.
6. Live fresh-run proof and final readiness audit.

Each slice must pass focused tests before the next slice begins.

## Risks and mitigations

- **Historical data repair:** backfill only missing parent stage rows derived
  from immutable plan evidence; reject ambiguous ownership.
- **Policy ambiguity for vulnerabilities:** store exact facts first and let the
  versioned qualification policy determine blocker versus accepted risk.
- **Provider variability:** deterministic integration transport proves code
  behavior; live proof is required for environment readiness.
- **LLM transaction rollback:** invocation/outcome persistence is separated
  from accepted-package creation.
- **Cross-service drift:** baseline facts feed Analysis and Planning through one
  checksum-bound bundle.
- **Scope expansion into transformation:** readiness verification explicitly
  asserts no stage start, sandbox preparation, authorization, or command queue.

## Out of scope

- Implementing or running the Transformation Agent.
- Starting a transformation stage.
- Executing Angular update commands.
- Repairing or rewriting immutable artifacts from `run-16a48fc55de7`.
- Automatically applying dependency fixes.
- Removing human approval gates.
- Unrelated backend or frontend refactoring.
- Committing or pushing without explicit user authorization.
