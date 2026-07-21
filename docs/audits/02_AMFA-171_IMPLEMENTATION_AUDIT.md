# AMFA-171 Targeted Implementation Audit — Corrected Authoritative Version

## 1. Audit identity

| Field | Value |
| --- | --- |
| Issue | AMFA-171 — S3-F05-I02 — API/Evidence: Persist stage-start, G07, and sandbox evidence |
| Parent | AMFA-144 |
| Consumed dependency | AMFA-170 — committed at `079c42e40024f820afd7d7f11b5c1fd956b80bcd` |
| Branch | `hermes/02-stage-workspace-bootstrap` |
| Audit mode | Targeted vertical-slice audit; no repository-wide re-audit |
| Audit date | 2026-07-21 |
| Purpose | Define only the AMFA-171 delta that remains after AMFA-170, without reimplementing closed behavior |
| Result | Ready for targeted implementation under the scope controls in this report |

This corrected report supersedes the first AMFA-171 audit draft as the implementation plan for AMFA-171. It preserves the original factual observations and executed-command record, but corrects scope inflation by separating:

```text
production implementation status
from
executable proof status
```

A requirement is not a production gap merely because its existing proof was not executed during the audit.

---

## 2. Pinned repository state

The initial audit preflight observed the following authoritative state before the audit report was created:

| Check | Observed | Required | Result |
| --- | --- | --- | --- |
| Branch | `hermes/02-stage-workspace-bootstrap` | same | PASS |
| HEAD | `079c42e40024f820afd7d7f11b5c1fd956b80bcd` | same | PASS |
| Upstream | `origin/hermes/02-stage-workspace-bootstrap` | same | PASS |
| Ahead / behind | `0 0` | `0 0` | PASS |
| Initial working tree | clean | clean | PASS |
| `docs/sprint.md` Git blob | `4c9a17670ce6d988bdcad48d43e805dbf9a0c53e` | same | PASS |
| Repository baseline Git blob | `cd793cf4fa81a92467fe963a4b984f5c74509fab` | same | PASS |
| AMFA-170 audit Git blob | `1f769b3150c99e029aa689e0e00afad3555d0eab` | same | PASS |

All future AMFA-171 implementation and review work must start from this exact commit unless a separately approved documentation-only commit changes the audit file. A production implementation prompt must stop if the production base differs unexpectedly.

---

## 3. Authority hierarchy

Apply this order without exception:

1. `docs/sprint.md`
   Exact functional authority for AMFA-144, AMFA-170 and AMFA-171.

2. Root `AGENTS.md` and any more-specific `AGENTS.md`
   Repository operating rules.

3. Current code, migrations and tests at the pinned base
   Implementation reality.

4. `docs/audits/00_REPOSITORY_AUDIT_BASELINE.md`
   Repository map, authorities, dependencies and reusable commands only.

5. `docs/audits/01_AMFA-170_IMPLEMENTATION_AUDIT.md`
   Historical findings and consumed AMFA-170 contracts only.

The baseline and prior audit must never replace or broaden the exact AMFA-171 wording.

---

## 4. Exact AMFA-171 scope

The sprint assigns AMFA-171 the persistence, API, event and immutable-evidence layer for the stage-start, G07 and sandbox vertical slice.

The exact functional themes are:

- migration-stage preparation persistence;
- active stage-plan and version persistence;
- authoritative stage input, sandbox workspace and fingerprints;
- gate versions;
- append-only decisions;
- idempotency and correlations;
- artifacts and immutable evidence;
- prepare-stage, G07 decision and sandbox creation APIs;
- durable named events for `STAGE_CREATED`, `STAGE_PREPARING`, `STAGE_PLAN_LOCKED`, `STAGE_WAITING_APPROVAL` and `SANDBOX_READY`;
- finalized stage-start package, exact plan/profile bindings, copy report, input manifest/fingerprint and sandbox verification;
- upgrade/rollback, stale binding, duplicate, event ordering, artifact failure, interrupted-copy, restart, authorization and protected-transition proofs;
- old G07 decisions must never satisfy changed bindings.

### Scope interpretation rules

1. AMFA-170 behavior is consumed, not rebuilt.
2. Existing production behavior with missing proof is a **proof gap**, not automatically a production gap.
3. A dedicated sandbox `GET` endpoint is not mandatory unless no existing authoritative API/projection/replay contract can satisfy restart retrieval.
4. A separate input-manifest artifact is not mandatory if the existing immutable stage-start package already contains the complete canonical manifest, fingerprint, plan/profile identities, versions and checksums and supports authoritative readback.
5. An artifact-store failure does not require a “failure artifact.” It requires fail-closed behavior, no false success event/state, and durable correlated failure evidence through an appropriate available channel.
6. Event-order production changes are authorized only after a red transaction-boundary test proves that a dependent event can become durable or externally visible before its required rows/artifact metadata.
7. Append-only applies to business decision history. A mutable current gate projection may remain if immutable decision history is added and old decisions cannot authorize changed bindings.

---

## 5. Consumed AMFA-170 contracts — do not reimplement

The following are closed production contracts at the pinned AMFA-170 commit and must be preserved:

| Contract | Existing production authority |
| --- | --- |
| Authoritative active plan, stage plan, G06 and source snapshot resolution | `StagePreparationApplicationService._resolve_active_plan` |
| Deterministic stage identity and migration-stage creation | `prepare_stage` and `MigrationStageModel` |
| Current-version re-detection | Existing prepare path |
| Lease-protected preparation and exact lease cleanup | `prepare_stage` lease lifecycle |
| `CREATED/PREPARING/PLAN_LOCKED/WAITING_APPROVAL` transition authority | `StateTransitionService` through prepare flow |
| Stage-start package construction and existing immutable evidence write | `_persist_stage_start_evidence`, G07 package builder, `LocalFilesystemArtifactStore` |
| Persistent G07 creation, version binding, expiry and stale validation | G07 model and `_validate_current_g07` |
| G07 decision idempotent replay and changed-binding stale handling | `decide_g07` as closed by AMFA-170, pending AMFA-171 append-only history extension |
| Sandbox pending/copying/verified lifecycle | `StageWorkspaceModel` and sandbox service path |
| Safe copy, validation and reconstruction | `BaselineSandboxService`, workspace services |
| Fingerprint/count/size verification | Existing workspace verification path |
| Duplicate sandbox protection and exactly-once `SANDBOX_READY` | Existing create/replay path |
| Interrupted-copy restart reconstruction | Existing reconstruction path |
| Checksum-addressed immutable artifact-store behavior | `LocalFilesystemArtifactStore` |

### Mandatory implementation rule

For every matrix row whose production status is `CLOSED_BY_AMFA170`:

```text
Required production change = NONE
```

unless a red AMFA-171 integration/API/evidence test proves a narrow defect in the exposed contract. Production code may not be rewritten merely to make tests easier.

---

## 6. Status model used by this audit

### Production status

- `CLOSED_BY_AMFA170` — required production behavior already exists and must be preserved.
- `PARTIAL_AMFA171` — a usable base exists, but AMFA-171 owns a confirmed narrow extension.
- `OPEN_AMFA171` — confirmed required production behavior is absent.
- `CONDITIONAL_TEST_FIRST` — production defect is not proven; add a red test first and change production only if it fails for the expected reason.
- `OUT_OF_SCOPE` — not owned by AMFA-171.

### Proof status

- `PROVED` — qualifying executable proof was observed.
- `PARTIAL` — some related tests passed, but the exact acceptance condition is not fully proved.
- `OPEN` — the required executable proof is missing or was not successfully executed.

A Codex implementation verdict may be `PASS` only when:

1. every `OPEN_AMFA171` and `PARTIAL_AMFA171` production gap assigned for implementation is closed;
2. every `CONDITIONAL_TEST_FIRST` row is resolved by either a passing no-change proof or a proven minimal fix;
3. every required proof row is `PROVED`;
4. no `CLOSED_BY_AMFA170` behavior was unnecessarily rebuilt.

---

## 7. Corrected requirement-to-code-to-test matrix

| ID / exact requirement theme | Production status | Proof status | Existing production symbol / contract | Confirmed production gap | Authorized production change | Required executable proof and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| R01 — persist migration-stage preparation | `CLOSED_BY_AMFA170` | `OPEN` | `MigrationStageModel`; deterministic `prepare_stage` creation/replay | None confirmed | **NONE** | Prove exactly one stage row across initial prepare and replay; assert run/stage/order identity and correlation to transitions/evidence |
| R02 — active stage-plan/version | `CLOSED_BY_AMFA170` | `OPEN` | `_resolve_active_plan`; `ActivePlanVersionModel`; `StageExecutionPlanModel` | None confirmed | **NONE** | Prove prepare/API readback uses exact active plan ID, stage-plan ID, version and checksum |
| R03 — authoritative stage input, workspace and fingerprints | `CLOSED_BY_AMFA170` | `PARTIAL` | `SourceSnapshotModel`; `StageWorkspaceModel`; workspace fingerprint verification | None for core persistence/copy verification | **NONE for core behavior** | Prove persisted input/workspace identities, source and sandbox fingerprints, mismatch rejection and replay identity |
| R04 — gate versions | `CLOSED_BY_AMFA170` | `OPEN` | `G07ApprovalModel.gate_version`; `_validate_current_g07` | None confirmed | **NONE** | Prove current gate version is returned and stale gate version is rejected at service/API boundaries |
| R05 — append-only G07 decisions | `OPEN_AMFA171` | `OPEN` | Current gate projection is mutable in `G07ApprovalModel`; `decide_g07` updates it | Immutable business decision history absent | Add a narrow append-only decision-history model/table linked to the current gate projection; preserve replay semantics | Prove first append, same-key identical replay without duplicate, changed payload conflict, immutable prior records and old-decision rejection after binding drift |
| R06a — existing idempotency | `CLOSED_BY_AMFA170` | `PARTIAL` | Prepare, G07 and workspace request checksums/keys | None confirmed | **NONE** | Prove identical replay and changed-payload conflict across prepare, decision and copy |
| R06b — durable correlations | `OPEN_AMFA171` | `OPEN` | Records/events/artifact metadata lack one authoritative end-to-end correlation contract | Durable cross-record correlation not fully persisted/exposed | Add the minimum correlation fields/metadata needed to join stage, gate, decision, workspace, artifacts and events; reuse existing IDs/checksums | Prove one correlation chain across DB rows, artifact metadata and event payloads, including replay |
| R07 — canonical stage-prepare API | `PARTIAL_AMFA171` | `OPEN` | Existing `POST /api/v1/runs/{run_id}/stages/prepare` invokes correct service | Parent contract expects a stage identifier in the canonical route; current body-selected route differs | Add/align the exact canonical route while preserving internal service and backward compatibility only where necessary | HTTP contract proof: owner request, replay, stale/error mapping, exact response identities and event sequence |
| R08 — G07 read and decision APIs | `PARTIAL_AMFA171` | `OPEN` | Existing G07 GET and decision POST routes/services | Server authentication/run authorization absent; append-only persistence absent for decision POST | Inject authenticated actor, enforce run access, prohibit body actor spoofing; route decision through append-only history | HTTP owner/unauthenticated/foreign/spoofed tests; read after restart; identical replay and changed payload conflict |
| R09 — sandbox creation and restart retrieval | `PARTIAL_AMFA171` | `OPEN` | Sandbox POST, replay and reconstruction already exist | Authorization absent; authoritative restart retrieval path not yet demonstrated | Add auth to POST. First test existing run/stage projection or idempotent replay retrieval. Add a dedicated GET only if no existing authoritative contract satisfies the exact requirement | Create/duplicate/restart proof, foreign/unauthenticated rejection, and authoritative retrieval after service/session restart |
| R10 — named events after required durable writes | `CONDITIONAL_TEST_FIRST` | `OPEN` | Transition rows and events are created inside the existing workflow/session | No proven durability-order defect; source order alone is insufficient evidence | **No production change unless a red transaction/failure test proves premature durable or external visibility** | Force artifact/metadata failure before commit and prove no dependent event or false success is durable/visible; prove ordered correlations after successful commit |
| R11 — stage-start package and exact plan/profile | `CLOSED_BY_AMFA170` | `OPEN` | G07 package builder and `_persist_stage_start_evidence` write immutable stage-start evidence | None confirmed | **NONE** | Read artifact back and assert exact plan/profile IDs, versions, checksums, input identity and gate package checksum |
| R12 — copy report | `OPEN_AMFA171` | `OPEN` | Safe-copy report type/path exists but no registered immutable copy-report evidence was found | Required copy report is not finalized as retrievable immutable evidence | Produce and register canonical copy-report evidence after authoritative copy/reconstruction outcome and before dependent success event | Prove artifact ID/checksum/readback on normal copy and restart reconstruction; no duplicate artifact on replay |
| R13 — input manifest/fingerprint evidence | `CONDITIONAL_TEST_FIRST` | `OPEN` | `StageInputManifest` is already embedded in the stage-start/G07 package | It is unproven whether the existing immutable package fully satisfies finalization/readback | First prove canonical completeness and immutable readback. Add a separate manifest artifact only if the package cannot meet the exact requirement | Assert manifest paths/count/size/fingerprint, plan/profile bindings and checksum from immutable evidence; tamper/stale fingerprint rejection |
| R14 — sandbox verification evidence | `OPEN_AMFA171` | `OPEN` | Workspace verification currently exists as mutable JSON/state | No finalized immutable sandbox-verification evidence artifact/package | Produce and register canonical immutable sandbox-verification evidence linked to workspace/copy report/correlation | Prove checksum/readback, tamper detection, restart retrieval and ready-event linkage |
| R15 — Alembic upgrade and rollback | `PARTIAL_AMFA171` | `OPEN` | Existing AMFA-170 migrations create current stage/G07/workspace schema | AMFA-171 schema additions for append-only decisions/correlations/evidence links require a narrow migration; lifecycle proof absent | Add only the migration needed by confirmed AMFA-171 production gaps | Disposable DB: upgrade from previous head, schema/index/FK checks, downgrade across new migration, re-upgrade and current=head |
| R16 — stale authority bindings; old decisions never satisfy changed bindings | `CLOSED_BY_AMFA170` for gate invalidation; `PARTIAL_AMFA171` for immutable history linkage | `OPEN` | `_validate_current_g07`, `_invalidate_g07`, AMFA-170 stale replay fix | Append-only history must not authorize changed bindings | Preserve stale authority logic; ensure append-only decision records are historical only and current authorization revalidates gate bindings | State, plan, profile/policy, G06, fingerprint, artifact and gate-version drift tests; old approved decision rejected without deletion/mutation of history |
| R17 — duplicates, interrupted copy and restart | `CLOSED_BY_AMFA170` for duplicate/reconstruction behavior; `OPEN_AMFA171` for interruption evidence | `OPEN` | Existing decision replay, sandbox replay and reconstruction | Durable interrupted-copy/recovery evidence absent | Add the minimum durable interruption/recovery evidence linked to existing workspace lifecycle; do not build a second recovery mechanism | Duplicate decisions/copies, no duplicate ready event, crash/restart reconstruction, interruption and recovery evidence readback |
| R18 — artifact-store failures | `CONDITIONAL_TEST_FIRST` | `OPEN` | Immutable artifact store and stage-start write already exist | Failure ordering and fail-closed behavior for newly required evidence are unproved | Do not invent a failure artifact. Change production only if failure tests reveal false success, missing durable failure state, or premature event | Inject writer failure for stage-start/copy/verification evidence; prove no false ready/success event, no corrupt metadata and correlated failure/retry behavior |
| R19 — authorization and protected transitions | `PARTIAL_AMFA171` | `OPEN` | State-transition protection exists; stage routes trust client actor and lack run-access dependency | Authentication, server-owned actor and run authorization absent on exposed routes | Use existing authentication/authorization authorities; remove client control over effective actor; preserve transition service | HTTP unauthenticated, foreign run, spoofed actor and authorized owner tests; protected-transition regression tests |

---

## 8. Corrected delta summary

### 8.1 Confirmed production changes authorized for AMFA-171

The implementation is authorized to make only these confirmed production changes unless a conditional red test proves another narrow defect:

1. **Append-only G07 decision history**
   Keep the current gate/current-state projection if useful; add immutable business decision records.

2. **Durable end-to-end correlations**
   Add only the fields/metadata required to join stage, gate, decision, workspace, artifacts and events.

3. **Canonical prepare API alignment**
   Expose the exact parent route/identifier contract without rewriting the preparation service.

4. **Authentication, authorization and server-owned actor**
   Protect prepare, G07 and sandbox routes using existing repository authorities; reject spoofed actor input.

5. **Immutable copy-report evidence**
   Finalize and register the authoritative copy result.

6. **Immutable sandbox-verification evidence**
   Finalize and register the authoritative verification result.

7. **Durable interrupted-copy/recovery evidence**
   Evidence only; reuse AMFA-170 reconstruction and exactly-once behavior.

8. **Narrow Alembic migration**
   Only for append-only decisions, correlations and required evidence references/indexes.

### 8.2 Conditional changes — tests first, no speculative code

1. **Event durability ordering**
   Change production only if a forced-failure/transaction test proves premature durable or external event visibility.

2. **Separate input-manifest artifact**
   Add only if the existing immutable stage-start package cannot provide complete canonical manifest/fingerprint identity and readback.

3. **Dedicated sandbox retrieval endpoint**
   Add only if existing run/stage projection or idempotent service/API replay cannot satisfy authoritative restart retrieval.

### 8.3 Proof-only work — no production rewrite

The following require focused tests and evidence, not reimplementation:

- exactly-one migration-stage persistence;
- active plan/version resolution and readback;
- stage input/workspace/fingerprint identity;
- gate-version validation;
- existing prepare/decision/copy idempotency;
- stage-start package and exact plan/profile bindings;
- stale authority invalidation;
- duplicate sandbox protection;
- restart reconstruction;
- exactly-once `SANDBOX_READY`;
- transition protection.

---

## 9. Persistence and migration findings

The AMFA-170 schema is a valid base:

- `migration_stages` supplies stage identity and run/order uniqueness;
- planning models supply active plan/version references;
- `g07_approvals` supplies the current gate/package projection and replay bindings;
- `stage_workspaces` supplies workspace lifecycle and verification state;
- the AMFA-170 replay migration supplies additional idempotency/reconstruction fields.

The narrow persistence delta is:

```text
append-only G07 decision history
+ durable correlations
+ artifact/evidence references required by the final evidence packages
+ supporting unique/index/FK constraints
```

The implementation must not replace the current gate projection, stage identity or workspace lifecycle unless an exact red test proves incompatibility.

### Append-only decision model constraints

At minimum, each decision-history record must retain:

- immutable decision identity;
- gate identity and gate version;
- stage/run identity;
- decision value;
- authenticated actor identity;
- comment where allowed;
- canonical payload checksum;
- idempotency key and request checksum;
- durable correlation identity;
- creation timestamp;
- linkage needed to prove which current gate bindings were evaluated.

Identical same-key replay must reuse the same decision record. A changed payload under the same key must conflict. Historical decisions must never be mutated or treated as authorization for changed bindings.

---

## 10. API and authorization findings

| API concern | Current usable base | Confirmed AMFA-171 delta |
| --- | --- | --- |
| Prepare | Existing route invokes the closed AMFA-170 preparation service | Add/align canonical `{stageId}` route contract; authenticate caller; enforce run access; server owns actor |
| G07 read | Existing persisted-gate read service/route | Authenticate and authorize; prove restart readback and stale representation |
| G07 decision | Existing decision service with binding/replay validation | Authenticate/authorize; server actor; persist append-only history while retaining current projection |
| Sandbox create | Existing safe create/replay/reconstruct service and POST route | Authenticate/authorize and prove HTTP duplicate/restart behavior |
| Sandbox retrieval | Existing persistence/reconstruction may be sufficient | First prove an existing authoritative retrieval path; create a dedicated GET only if that proof fails |

### Authorization constraints

- The effective actor must come from the authenticated server context.
- A body `actor` value must not override the authenticated identity.
- Every run-scoped route must enforce access to that run.
- Existing protected transition checks remain authoritative and must be regression-tested, not replaced.

---

## 11. Events, artifacts and evidence findings

### Existing evidence to preserve

AMFA-170 already writes checksum-addressed stage-start evidence through the artifact store and records metadata. The existing package must first be tested for canonical completeness before any additional manifest artifact is introduced.

### Confirmed missing finalized evidence

1. **Copy report**
   A canonical, checksum-addressed, retrievable evidence object for the authoritative copy/reconstruction result.

2. **Sandbox verification**
   A canonical, checksum-addressed, retrievable evidence object for source/sandbox fingerprint, count, size and verification outcome.

3. **Interrupted-copy/recovery evidence**
   Durable evidence of the interrupted state and the later reconstruction/recovery outcome, linked to the same workspace and correlation.

### Event durability rule

A source-code call order is not sufficient to prove a defect. The required proof is transactional:

```text
forced required-evidence failure before commit
→ no dependent success/ready event becomes durable or externally visible
→ no false successful stage/workspace state
```

If this test passes on existing production code, no event-order refactor is authorized.

---

## 12. Idempotency, stale bindings, replay and restart

AMFA-170 already supplies the core behavior. AMFA-171 must extend it without replacing it:

- prepare replay remains deterministic and exactly-once;
- same G07 decision key and identical payload reuse one immutable decision record;
- changed payload under the same key conflicts;
- current authorization always revalidates current gate bindings;
- historical approved decisions remain immutable but cannot satisfy changed state, plan, profile/policy, G06, fingerprint, artifact or gate-version bindings;
- duplicate sandbox requests do not copy twice or emit multiple ready events;
- restart reconstruction remains the only copy-recovery authority;
- AMFA-171 adds durable interruption/recovery evidence and API-level proof.

---

## 13. Required executable test plan

Create a focused AMFA-171 suite, preferably in a dedicated file such as:

```text
backend/tests/test_stage_preparation_persistence_api_s3_f05_i02.py
```

Use existing tests when they already prove a requirement. Do not duplicate tests only to increase counts.

### Test group A — proof-only AMFA-170 contracts

- exactly one `MigrationStageModel` after prepare and replay;
- exact active plan/stage-plan/version/checksum readback;
- persisted source input/workspace/fingerprint identity;
- gate-version stale rejection;
- exact stage-start artifact readback including plan/profile and input bindings;
- stale state/plan/profile-or-policy/G06/fingerprint/artifact/gate-version cases;
- duplicate prepare, decision and sandbox behavior;
- restart reconstruction and exactly-one `SANDBOX_READY`;
- protected transition regressions.

Production changes are forbidden for this group unless an exact test fails and demonstrates a narrow regression not already classified.

### Test group B — append-only decisions and correlations

Red tests first:

- first decision appends one immutable record;
- identical same-key replay returns the same record;
- changed payload under the same key conflicts;
- a later legitimate decision creates a new record where the domain allows it;
- historical records never mutate;
- old approval cannot authorize changed bindings;
- stage/gate/decision/workspace/artifact/event share the expected durable correlation chain.

### Test group C — API and authorization

- canonical prepare route and identifier contract;
- G07 read and decision routes;
- sandbox create route;
- existing authoritative restart retrieval path;
- unauthenticated request rejected;
- foreign run rejected;
- body actor spoofing rejected/ignored in favor of authenticated actor;
- stale/replay/error mapping at HTTP boundary;
- dedicated sandbox GET tested only if group-first discovery proves it is required.

### Test group D — immutable evidence

- copy-report artifact ID/checksum/readback;
- sandbox-verification artifact ID/checksum/readback;
- interrupted-copy and recovery evidence;
- replay does not duplicate artifacts;
- existing stage-start package contains exact plan/profile/input manifest/fingerprint, or a red test proves a separate manifest artifact is necessary;
- tamper and checksum mismatch fail closed.

### Test group E — durability and failures

- artifact-store failure before stage-start evidence finalization;
- copy-report evidence failure;
- sandbox-verification evidence failure;
- no dependent success/ready event or false success state;
- retry/restart behavior remains deterministic;
- no “failure artifact” requirement unless explicitly introduced by an authoritative contract.

### Test group F — Alembic

On an isolated disposable database:

```text
previous head
→ upgrade to AMFA-171 head
→ inspect tables, columns, FKs, unique constraints and indexes
→ downgrade across AMFA-171 migration
→ re-upgrade
→ current = AMFA-171 head
```

---

## 14. Targeted implementation sequence

### Step 0 — persistent closure matrix and red tests

Before production changes, create and maintain:

```text
Requirement
→ Production status
→ Proof status
→ Existing symbol
→ Confirmed gap
→ Red test
→ Minimal change
→ Observed result
→ Evidence artifact/log
→ CLOSED/OPEN
```

Add red tests for all confirmed production gaps and conditional questions. Record actual red output. Do not claim a red phase that was not executed.

### Step 1 — append-only decisions and correlations

Owned areas, subject to exact repository structure:

- stage/G07 persistence models;
- one narrow Alembic migration;
- model exports/repository helpers;
- minimal `decide_g07` extension;
- event/artifact metadata correlation propagation.

Preserve the current gate projection and AMFA-170 binding validation.

### Step 2 — finalize required evidence

Add the minimum helpers needed to finalize:

- copy report;
- sandbox verification;
- interrupted-copy/recovery evidence.

First prove whether the existing stage-start artifact already satisfies input-manifest/fingerprint finalization. Do not create redundant evidence packages.

### Step 3 — canonical API and authorization

- add/align the exact prepare route;
- protect prepare, G07 and sandbox routes;
- use authenticated server actor;
- enforce run access;
- retain existing application services;
- prove existing restart retrieval before adding a new endpoint.

### Step 4 — conditional durability fixes

Run forced-failure transaction tests. Change event/write ordering only if the tests prove a real durability defect.

### Step 5 — full focused validation

- focused AMFA-171 suite twice;
- consumed AMFA-170 regression suite;
- auth/API tests;
- artifact-store and workspace security tests;
- isolated Alembic up/down/up/current;
- compileall;
- repository-authoritative Ruff command;
- `git diff --check`;
- independent adversarial review.

---

## 15. Explicit non-goals

AMFA-171 must not:

- implement AMFA-172 frontend behavior;
- absorb AMFA-173 broader documentation/security work beyond the exact AMFA-171 API authorization requirement;
- perform the AMFA-144 parent integration audit;
- rewrite `StagePreparationApplicationService`;
- replace AMFA-170 plan resolution, G07 validation, workspace copy or recovery authority;
- build a second sandbox-copy mechanism;
- add a dedicated sandbox GET before proving no existing retrieval contract satisfies restart retrieval;
- create a separate input-manifest artifact before proving the stage-start package is insufficient;
- invent a failure artifact;
- fix the unrelated `target_cli_exact=None` baseline defect in `tests/test_planning_evidence_persistence_api_s2_f06_i02.py`;
- perform repository-wide cleanup or architectural refactoring.

---

## 16. Commands executed and observed results from the audit

| Working directory | Exact command | Exit | Observed result |
| --- | --- | --- | --- |
| Repository root | `git fetch origin --prune; git branch --show-current; git rev-parse HEAD; git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'; git rev-list --left-right --count '@{upstream}...HEAD'; git status --short; git diff --check; git hash-object docs/sprint.md; git hash-object docs/audits/00_REPOSITORY_AUDIT_BASELINE.md; git hash-object docs/audits/01_AMFA-170_IMPLEMENTATION_AUDIT.md` | 0 | Pinned state and all three expected Git blob IDs matched; initial status/diff output empty |
| Repository root | `python -m pytest backend/tests/test_stage_workspace.py -q` | 1 | Collection error: `ModuleNotFoundError: No module named 'sqlalchemy'`; no test result |
| `backend` | `.\\.venv\\Scripts\\python.exe -m pytest tests/test_stage_workspace.py -q` | 124 | Timed out after 64.2 seconds; no usable pass/fail count |
| `backend` | `.\\.venv\\Scripts\\python.exe -m pytest tests/test_stage_workspace.py --collect-only -q` | 0 | 62 tests collected |
| `backend` | `.\\.venv\\Scripts\\python.exe -m pytest tests/test_stage_workspace.py::test_package_builder_creates_valid_package_with_checksum tests/test_stage_workspace.py::TestStageWorkspaceServiceVerifyFingerprint tests/test_stage_workspace.py::TestAMFA170ClosureProof::test_prepare_persists_and_reuses_stage_start_evidence tests/test_stage_workspace.py::TestAMFA170ClosureProof::test_g07_replay_requires_identical_payload -q` | 0 | 6 passed in 7.97 seconds |
| Repository root | `python -m pytest -q backend/tests/test_persistence.py::test_alembic_feature_schema_upgrades_and_rolls_back_on_temporary_sqlite` | 1 | Collection/import environment unusable; no migration lifecycle proof |

The six passing tests prove only their cited lower-level facts. They do not prove HTTP authorization, append-only decisions, AMFA-171 migration lifecycle, conditional event durability or the missing final evidence objects.

---

## 17. Implementation closure rules

Codex or any other implementation agent must not return PASS unless the final closure matrix shows:

- all confirmed production gaps `CLOSED`;
- every conditional row resolved by an observed test result;
- every proof-only row `PROVED`;
- no unapproved endpoint/artifact/model introduced;
- no AMFA-170 authority duplicated or replaced;
- all migrations reversible on a disposable database;
- all required artifacts checksum-verified and retrievable;
- all API actors server-derived and run-authorized;
- old immutable decisions unable to authorize changed bindings;
- no dependent success event after failed required evidence persistence;
- final diff limited to AMFA-171-owned files plus focused tests and its migration.

An independent reviewer must inspect the actual diff, schema, tests and validation logs before commit.

---

## 18. Corrected audit verdict

```text
READY FOR TARGETED AMFA-171 IMPLEMENTATION
```

AMFA-171 is not already complete. However, the implementation delta is **not nineteen new features**.

The corrected scope is:

```text
8 confirmed production changes
+ 3 conditional test-first questions
+ proof-only closure for existing AMFA-170 contracts
```

The implementation must preserve AMFA-170 and close only the exact confirmed or test-proven AMFA-171 gaps defined above.