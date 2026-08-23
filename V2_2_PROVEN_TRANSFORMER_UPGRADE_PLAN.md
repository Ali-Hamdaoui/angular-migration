# Angular Migration Factory V2.2 Proven Transformer Upgrade Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:executing-plans` and execute phases sequentially in this checkout. Do not create worktrees, branches, or parallel phase implementations.

**Goal:** Replace the new-plan authoritative combined `ng update` path with the proven, restart-safe adjacent-major workflow: evidence-bound CLI authority, disposable discovery, deterministic target intent, bound-npm lock authority selection, canonical V1/V2/V3 resolved-state reading, converged/reproducible lock, dynamic migrate-only ledger, clean validation, exact governed promotion, seal, and copy-forward.

**Architecture:** SQLite and immutable artifacts remain workflow authority. Existing runtime resolution, structured command execution, sandbox copying, checkpoints, gates, workspace generations, repair lineage, promotion, and sealing are evolved in place. New evidence is stored as typed, checksum-bound JSON in existing artifact/checkpoint records; no SQL schema change is required.

**Tech stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy/SQLite, Alembic, LangGraph, pytest, structured Node/npm/npx command worker, Angular CLI.

**Spec:** User-supplied “PROVEN 11→21 TRANSFORMER — MASTER IMPLEMENTATION PLAYBOOK AUTHORING TASK”; code truth at branch `v2.2`, HEAD `30e35af18e151a87fcad5629a39f060fd9d0e2a9`.

## Global constraints

- Execute phases sequentially in the same `v2.2` checkout; never use worktrees.
- External source and sealed generations are immutable.
- Every process uses the registered structured command worker with argv, `shell=false`, an approved alias, bound runtime checksum, timeout, network policy, and complete stdout/stderr/result evidence.
- Angular CLI execution is authorized by an exact absolute installed entrypoint plus package/executable checksum and actual-version proof; `npx --package` selection alone is never CLI authority.
- The governed PATH is an exact checksum-bound ordered value assembled from approved runtime/toolchain and policy-required OS directories; it never inherits an unbounded ambient PATH tail, and child npm resolution must equal the bound npm descriptor.
- `stderr` is evidence, not failure; process exit code owns command status, while semantic validators own stage success.
- Never use `--force`, `--allow-dirty`, or `--legacy-peer-deps`.
- npm remains the transitive graph solver; the Factory owns policy and direct dependency intent only.
- `package.json` is the sole root requested-dependency intent authority. It is parsed once into an immutable, section-preserving `DependencyIntent` (`dependencies`, `devDependencies`, `optionalDependencies`, `peerDependencies`, `peerDependenciesMeta`) before semantic evaluation. The bound exact npm version selects a `LockfileAuthority` through `LockfileAuthorityPolicy`; npm 6–11 prefer `npm-shrinkwrap.json` over `package-lock.json`, while npm 12+ treats shrinkwrap as unsupported and requires an explicit policy when it is present. `PackageLockReader` proves resolved lock state without reconstructing original root ranges from V1.
- Never encode fixture failures, package names, Angular-major branches, fixed runtime paths, or unconditional lock deletion as orchestration logic.
- New repair proposals cannot execute commands, select runtime, solve dependencies, or edit `package-lock.json`/`npm-shrinkwrap.json`.
- Existing gates G07–G12, reviewer separation, human approvals, checksums, and lineage remain mandatory.
- Historical plans and payloads remain readable and recoverable under their original semantics.
- A phase is complete only when its focused tests pass, no new failures appear relative to Phase 0, and its required runtime proof passes or blocks on an explicit missing governed runtime.

---

## 1. Executive decision

Current new plans are not safe enough for the proven 11→21 chain. `StageExecutionPlanService.create()` still plans `bootstrap_install → angular_update → target_version_check → lockfile_generation → final_install → migrate_packages → build/test`, and the V6 updater mutates the active stage workspace. The upgrade is a plan-versioned authority/sequencing refactor, not a Factory rewrite.

Decision:

1. New plans use semantic version `transformer-plan-v2.2-proven-1` stored inside existing `StageExecutionPlanModel.stage_plan` JSON through a new `StageExecutionPlan.transformer_semantic_version` field.
2. Missing semantic version means `transformer-plan-legacy-1`; a nonterminal legacy continuation never switches graph semantics.
3. New plan execution uses existing services wherever ownership is already correct.
4. No new production subsystem, SQL table, dependency, process runner, runtime resolver, gate system, or artifact store is introduced.
5. New evidence uses existing `StageStepModel`, `StageCheckpointModel`, `StageWorkspaceBindingModel`, `WorkspaceGenerationModel`, `CandidatePromotionModel`, `RepairAttemptModel`, gate rows, and immutable artifacts.
6. `backend/app/domain/lockfile_compatibility.py` owns npm-version-aware `LockfileAuthority` selection and the one canonical V1/V2/V3 resolved-state reader; Transformer services neither choose lock filenames nor inspect `packages[""]` directly.
7. Runtime operation is explicit: PRODUCTION requires an exact certified profile; QUALIFICATION may exercise an officially allowed profile only with immutable operator authorization and cannot certify it merely because commands passed.

## 2. Current code-truth architecture

| Area | Current truth | Evidence |
|---|---|---|
| Plan | Mandatory groups include authoritative `angular_update`, Core-only planned migrate, lock and final install | `backend/app/services/planning_application_service.py:89-209`; `backend/app/domain/planning.py:155-201` |
| Updater | V5/V6 render normal `ng update`; V6 combines framework cohort and toolchain packages | `backend/app/domain/command.py:317-436` |
| Graph | `prepare → runtime/preflight/G07 → bootstrap → angular_update → version/G08 → final install/build/test → G09/G12/seal` | `backend/app/orchestration/transformer_graph.py:227-328` |
| Workspace | Preparation creates one active stage binding and `pre_bootstrap` checkpoint | `backend/app/services/transformer_stage_service.py:107-203` |
| Runtime | Node/npm/npx are path-independent, paired, checksum-bound, and G07-authorized | `runtime_resolver_authority.py:53-182`; `command_executor_service.py:213-316,1266-1428` |
| Runtime certification | Domain distinguishes `EXACT_CERTIFIED` from `RANGE_COMPATIBLE`, but `enforce_stage_certification()` currently accepts `allowed` rather than requiring `certified` | `backend/app/domain/runtime_certification.py:26-118`; `backend/app/services/runtime_certification_service.py:124-148` |
| Command | Worker is sole subprocess authority, uses `shell=False`, and determines success from return code | `backend/app/command_execution/worker.py:642-747` |
| CLI authority | Updater/migrate renderers invoke `npx`; `--package` and local binaries share PATH, so requested CLI version is not executable identity proof | `backend/app/domain/command.py:317-475`; `backend/app/services/command_executor_service.py:318-329` |
| Lock | Runner validates one repair-authorized package-lock-only result and has classified stale-lock recovery | `lockfile_generation_runner.py:373-498,805-1011,1140-1297` |
| Lock authority/reader | Baseline currently prefers `package-lock.json` over `npm-shrinkwrap.json`, contrary to the bound npm policy for npm 6–11; its V1 fallback and other closure/preflight/migration parsers mix manifest intent with incompatible lock shapes, while some require V3 `packages[""]` | `backend/app/domain/baseline.py:137-174`; `backend/app/domain/lockfile_compatibility.py:17-32`; `backend/app/services/dependency_closure_service.py:612-648` |
| Migration | Exact migrate-only renderer exists; owner discovery inspects changed direct dependencies but special-cases Core/CLI | `command.py:438-475`; `package_migration_service.py:104-280` |
| Validation | Install/build/test/lint run against active binding; baseline delta is lint-only | `validation_runner.py:54-343`; `baseline_aware_validation_service.py:55-126` |
| Repair | Bounded proposer/reviewer/preimage controls exist, but apply mutates active binding and new schemas still permit dependency/unified-diff shapes | `repair_application_service.py:661-737,1286-1599`; `transformer_graph.py:3047-3650` |
| Promotion | Monotonic generation authority exists; candidate validation is containment/package-only and not in Transformer | `workspace_authority_service.py:36-235`; `candidate_promotion_service.py:50-118` |
| Seal | G09/G11/G12, target verification, cleanliness, immutable copy, chain hash, and N+1 derivation exist | `stage_sealing_service.py:100-280`; `transformer_sealing_flow.py:62-575` |

## 3. Proven manual E2E findings

The validated chain was sequential: Angular 11.0.4 → Core/CLI 12.2.17/12.2.18 → 13.3.12/13.3.11 → 14.3.0/14.2.13 → 15.2.10/15.2.11 → 16.2.12/16.2.16 → 17.3.12/17.3.17 → 18.2.14/18.2.21 → 19.2.25/19.2.27 → 20.3.29/20.3.34 → 21.2.21/21.2.21. These values are evidence inputs, not orchestration constants.

Observed runtime tuples are certification candidates only when their immutable logs prove exact Node/npm/npx, source, target, commands, dependency tree, build, tests, and seal. Official Angular compatibility ranges and Factory-certified exact profiles are separate concepts.

The experiment proves generic mechanisms are required for: evidence-bound actual CLI ownership, a fully governed child-process npm/PATH, governed version-check strategy properties, npm-version-sensitive peer behavior, section-aware package.json root intent (required/dev/optional/peer plus `peerDependenciesMeta`), optional omission semantics, npm-version-aware lock authority selection, canonical V1/V2/V3 resolved-state interpretation, partial updater mutation, stale-lock classification, exit-zero lock rejection by `npm ci`, valid duplicate transitives, physical-tree residue detected by `npm ls`, exit-code authority over stderr, isolated source repair, baseline diagnostic delta, discovery completeness independent of process exit, and harness/parser failure ownership.

## 4. Non-negotiable target architecture

```text
SEALED N
→ SELECT PRODUCTION OR QUALIFICATION MODE
→ RESOLVE GOVERNED RUNTIME
→ BIND GOVERNED PROCESS ENVIRONMENT (exact Node/npm/npx, PATH, allowed environment, child npm)
→ FRESH SOURCE BASELINE
→ construct section-aware DependencyIntent → select lock authority under the bound npm policy → canonical V1/V2/V3 resolved-state read
→ section-aware manifest-intent/lock-resolution proof → npm ci against the same authority → npm ls --all --json → exact source proof → build → tests
→ FREEZE SOURCE BASELINE
→ BIND DISCOVERY CLI TOOLCHAIN AUTHORITY (absolute entrypoint, package integrity, actual CLI)
→ DISPOSABLE DISCOVERY → assess exit and completeness separately
→ TargetIntent → discard discovery
→ CLEAN AUTHORITATIVE TARGET from frozen source
→ dependency plan → preserve-first lock solve
→ one classified authority-scoped fresh fallback if eligible (shrinkwrap replacement requires explicit policy)
→ bounded two-identical-SHA convergence
→ CLEAN MATERIALIZATION → npm ci → npm ls → exact target proof
→ installed ng-update inspection → MigrationLedger
→ bind exact materialized target CLI absolute authority
→ required migrate-only + governed optional decisions
→ reconcile only if section-aware `DependencyIntent` or selected lock authority changed
→ FREEZE TARGET AUTHORITY
→ BRAND-NEW VALIDATION → npm ci → npm ls → exact proof → build/test/lint
→ PRE_EXISTING/NEW/RESOLVED/CHANGED delta
→ NORMAL PASS: G09 → exact promotion → G12 → seal → N+1
→ FAIL: owner route → isolated candidate → clean validation
→ REPAIRED PASS: G11 → G09 → exact promotion → G12 → seal → N+1
```

## 5. Current-vs-target gap matrix

| Proven behavior | Current V2.2 | Required disposition | Priority |
|---|---|---|---|
| Certified catalogue truth | Official and empirical labels/values can diverge from manual evidence | Reconcile evidence first; never fabricate certification | P0-0 |
| Production/qualification bootstrap | Production enforcer can accept allowed-but-uncertified and qualification authority is implicit | Explicit plan mode; production requires certified, qualification requires allowed+operator authorization+reviewed evidence | P0-0 |
| Plan semantics | No graph semantic discriminator | Add JSON-level semantic version; preserve legacy | P0-1 |
| Root dependency authority | V1 resolved entries are used as though they could own original requested ranges | `package.json` is parsed into section-aware `DependencyIntent`; reader owns resolved state; root-sync compares intent under the bound npm capability | P0-2 |
| Root dependency sections | Root sections can be flattened before evaluation | Immutable `DependencyIntent` preserves required/dev/optional/peer/optional-peer semantics and `peerDependenciesMeta` through root-sync | P0-2 |
| Lockfile precedence | Baseline prefers package-lock over shrinkwrap, while npm precedence varies by bound npm capability | Canonical npm-version-aware `LockfileAuthorityPolicy`: npm 6–11 shrinkwrap then package-lock; npm 12+ package-lock with explicit unsupported-shrinkwrap policy | P0-2 |
| Lockfile schemas | V1 fallback and V3-only parsing are scattered | Canonical resolved-state `PackageLockReader` for V1/V2/V3 after authority selection | P0-2 |
| Fresh per-stage source baseline | Active stage workspace doubles as baseline/authority | Add source-baseline generation and evidence | P0-2 |
| `npm ls --all --json` | Missing in Transformer | Add registered command and semantic parser | P0-2 |
| Disposable update discovery | Updater mutates active binding | Run only against disposable binding | P0-3 |
| Discovery CLI identity | `npx --package`/local lookup can execute a different CLI | Bind requested=actual absolute CLI toolchain authority or block | P0-3 |
| Exit vs completeness | Command success drives flow | Persist independent fields and deterministic completeness proof | P0-3 |
| Target intent | Implicit in updater mutations | Persist normalized, source-bound TargetIntent | P0-3 |
| Preserve-first/fresh lock | Repair-only partial implementation assumes package-lock deletion | Make normal-path state machine; package-lock fallback is bounded, shrinkwrap replacement requires explicit policy | P0-4 |
| Two matching SHAs | Missing | Require consecutive equality with finite budget | P0-4 |
| Clean lock proof | Final install is not convergence-bound | New materialization generation, `npm ci`, `npm ls` | P0-4 |
| Dynamic migration owners | Direct changes plus Core/CLI priority | Installed metadata owners, no Core-only plan | P0-5 |
| Migrate-only CLI identity | Generic npx lookup can select non-target CLI | Execute exact installed target CLI through checksummed absolute entrypoint | P0-5 |
| Optional migrations | Not fully governed | RUN/SKIP/PENDING HUMAN ledger decisions | P0-5/P1 |
| Authority freeze | General fingerprints only | Explicit package.json/selected-lock/workspace freeze artifact | P0-6 |
| Clean validation | Reuses active workspace | Copy without governed volatile output | P0-6 |
| Diagnostic delta | Lint-only subset | Build/test/lint PRE_EXISTING/NEW/RESOLVED/CHANGED | P0-6 |
| Exact promotion/order | Service disconnected, weak fingerprint, and plan wording conflicts on G09/G11 | Normal G09→promote→G12; repaired G11→G09→promote→G12; bind one fingerprint | P0-7 |
| Failure owner | Environment/dependency/source regex fallback | Phase/evidence first: HARNESS/RUNTIME/DEPENDENCY/LOCKFILE/SOURCE | P1 |
| Repair isolation | Applies to active workspace | Apply only to candidate generation | P1 |
| LLM contract | Can produce dependency/unified-diff shapes | One ProblemGroup; structured source intent only | P1 |
| Reviewer | Three decisions | Add INSUFFICIENT_CONTEXT | P1 |
| Restart | Knows current legacy nodes | Add every new node/generation reconstruction | P1 |

## 6. Compatibility catalogue truth model

Three layers remain distinct:

1. **Allowed envelope:** official Angular Node/TypeScript/RxJS constraints in `CompatibilityCatalogueEntry`.
2. **Observed evidence:** immutable runtime/E2E artifacts identifying exact Node/npm/npx, source/target Core and CLI, toolchain, commands, and outcomes.
3. **Certified profile:** exact tuple promoted to certified only when layer 2 is complete and checksum-bound.

`CompatibilityCatalogueProvider` may describe an allowed route without claiming it is certified. Exact cohort resolution uses the versioned catalogue plus checksum-bound registry metadata. It never substitutes `targetMajor.0.0` as proof.

Two immutable plan modes resolve the certification bootstrap loop:

1. **PRODUCTION:** official allowed envelope + exact Factory-certified runtime profile. `RuntimeCertificationService.enforce_stage_certification()` must require `decision.certified is True`, not merely `allowed`. Missing certification blocks with `STAGE_RUNTIME_CERTIFICATION_REQUIRED`.
2. **QUALIFICATION:** official allowed envelope + paired Node/npm/npx from approved local inventory + an immutable `RuntimeQualificationAuthorization` naming actor, purpose, stage range, runtime descriptor checksums, catalogue checksum, expiry, and authorization checksum. It may execute the same proven workflow only in qualification-owned generations/runs. It cannot expose the profile to PRODUCTION or set `certified=True`.

Qualification produces a checksum-bound `RuntimeQualificationEvidence` artifact containing authorization, exact Node/npm/npx paths/versions/checksums, the npm exact-version `LockfileAuthorityPolicy`, governed PATH checksum, CLI toolchain authorities, section-aware `DependencyIntent` and checksum, selected lock authority/resolved-state/root-sync classifications (including deferred npm-spec and peer/optional evidence), npm-ci/tree/build/test/migration/validation/gate/promotion/seal evidence, and final fingerprint chain. A separate deterministic `promote_qualification_evidence()` operation validates completeness, official-envelope membership, descriptor stability, artifact checksums, and an explicit reviewer/actor decision before writing the certified decision. Command success alone never promotes certification. Existing artifact metadata, audit events, and `RuntimeCertificationModel` remain; the immutable qualification/certification decision artifact is authority and the row is its query projection, so no SQL change is required.

Phase 1 must reconcile current catalogue rows against repository evidence. Manual values without immutable repository evidence remain `observed_external`/uncertified and become explicitly authorized QUALIFICATION inputs in Phase 14, never production inputs.

## 7. Command model

### [REUSE]

- `npm-ci-bootstrap`, `npm-ci-final`, `npm-lockfile-generate`, build/test/lint templates.
- `angular-version-verify` only for legacy replay; its generic npx lookup is not proven CLI authority.
- Worker policy, runtime/checksum verification, artifact capture, exit-code semantics.

### [UPDATE]

Add to `backend/app/domain/command.py` and default registry. For proven Angular commands, `executable` is the exact governed Node descriptor selected by the worker and the first argv item is a validated absolute Angular CLI JavaScript entrypoint. On platforms where the approved executable is the installed `.bin/ng` shim, the absolute shim may be invoked directly only when its target and checksum resolve to the same authority. No PATH lookup chooses `ng`.

```text
npm-dependency-tree:
  executable npm
  argv ["ls", "--all", "--json"]
  network none

npm-dependency-direct:
  executable npm
  argv ["ls", "--depth=0", "--json"]
  network none

npm-explain-package:
  executable npm
  argv ["explain", "{package}", "--json"]
  network none

npm-package-metadata:
  executable npm
  argv ["view", "{package}@{exact_version}", "--json"]
  network registry-read

angular-cli-authority-version:
  executable {governed_node_absolute}
  argv ["{angular_cli_entrypoint_absolute}", "version"]
  network none

angular-update-discovery:
  executable {governed_node_absolute}
  argv ["{angular_cli_entrypoint_absolute}", "update", "{package@exact...}"]
  network registry-read

angular-migrate-range:
  executable {governed_node_absolute}
  argv ["{target_cli_entrypoint_absolute}", "update", "{package}", "--migrate-only", "--from", "{from_exact}", "--to", "{to_exact}"]
  network registry-read

angular-migrate-name:
  executable {governed_node_absolute}
  argv ["{target_cli_entrypoint_absolute}", "update", "{package}", "--migrate-only", "--from", "{from_exact}", "--to", "{to_exact}", "--name", "{migration_name}"]
  network registry-read
```

`AngularCliToolchainAuthority` is the single generic authority contract; `purpose` distinguishes DISCOVERY and MIGRATION. It binds `strategy_id`, `strategy_version`, purpose, requested CLI exact, installed CLI package version, absolute CLI script/shim path, script/shim SHA256, package integrity/checksum, Node/npm/npx `RuntimeExecutableDescriptor` identities/checksums, exact governed PATH and checksum, allowed environment map/checksum, child-visible npm resolved path/version/checksum, CLI-version proof execution/artifact, source generation fingerprint, target stage identity, toolchain-generation fingerprint, optional version-check policy, and authority checksum. `NG_DISABLE_VERSION_CHECK=1` is permitted only when the selected versioned strategy explicitly contains and certifies that environment property; it is not a global default.

Before either Angular command, deterministic authorization must prove requested CLI = installed package CLI = execution-coupled actual CLI authority = checksummed absolute entrypoint. A standalone earlier `ng version` is insufficient when a strategy can self-delegate: the strategy must also provide certified no-delegation/version-check behavior or execution-time package/process evidence proving the CLI package root/version that handled the update. If it cannot, discovery blocks. `shutil.which("npm", path=governed_path)` must resolve to the bound npm descriptor, and the CLI child environment inherits exactly that governed PATH. Mismatch blocks with `ANGULAR_CLI_AUTHORITY_MISMATCH`, `ANGULAR_CLI_DELEGATION_UNPROVEN`, or `CHILD_PACKAGE_MANAGER_AUTHORITY_MISMATCH` before authoritative intent acceptance.

All bindings validate absolute containment (source-local or prepared isolated toolchain for discovery; materialized target for migration), package names, exact semantic versions, bounded list size, migration name, authority checksum, and plan membership. `npx --package` may appear only as a toolchain-preparation step inside a separately evidence-backed strategy; the discovery execution still invokes the resulting proven absolute CLI entrypoint, and package selection is never the proof. V2–V6 `angular-update-exact`, npx-based `angular-migrate-range-v1`, and `angular-migrate-installed` remain [DEPRECATE]/[REMOVE-LATER]: registered for historical replay but never selected by a proven plan.

## 8. TargetIntent model

Add the Pydantic contract to existing `backend/app/domain/transformation.py` and persist it as immutable JSON:

```python
class TargetIntent(BaseModel):
    schema_version: Literal["target-intent-v1"]
    run_id: str
    stage_id: str
    source_baseline_fingerprint: str
    discovery_execution_id: str
    process_exit_code: int | None
    discovery_complete: bool
    completeness_findings: tuple[str, ...]
    dependency_intent: DependencyIntent
    dependency_intent_checksum: str
    source_package_json_sha256: str
    discovered_package_json_sha256: str
    target_cohort: dict[str, str]
    catalogue_checksum: str
    registry_snapshot_checksum: str
    discovery_toolchain_authority_checksum: str
    checksum: str
```

Completeness requires a valid `AngularCliToolchainAuthority` with requested=actual CLI proof, a parseable post-discovery manifest, unchanged non-dependency root fields unless explicitly authorized, exact required target Core/CLI intent, every governed direct cohort member resolvable inside catalogue/registry constraints, and no ambiguous dependency section ownership. Source files and discovery lock changes are never copied into TargetIntent.

## 9. LockResolution model and state machine

Extend `[UPDATE] backend/app/domain/lockfile_compatibility.py:17-32` rather than adding another selector/parser. The bound exact npm descriptor is an input to the only selector used by the Factory, and `LockfileAuthorityPolicy` is a package-manager capability policy, not an Angular-major branch:

```python
class DependencyIntentKind(str, Enum):
    REQUIRED = "REQUIRED"
    DEV = "DEV"
    OPTIONAL = "OPTIONAL"
    PEER = "PEER"
    OPTIONAL_PEER = "OPTIONAL_PEER"

class DependencyIntent(BaseModel):
    schema_version: Literal["dependency-intent-v1"]
    dependencies: Mapping[str, str]
    dev_dependencies: Mapping[str, str]
    optional_dependencies: Mapping[str, str]
    peer_dependencies: Mapping[str, str]
    peer_dependencies_meta: Mapping[str, Mapping[str, object]]
    checksum: str

    def kind_for(self, package: str, section: str) -> DependencyIntentKind: ...

class LockfileAuthorityPolicy(BaseModel):
    npm_exact_version: str
    npm_major: int
    shrinkwrap_behavior: Literal["PREFERRED", "UNSUPPORTED"]
    unsupported_shrinkwrap_action: Literal["BLOCK", "IGNORE_WITH_PACKAGE_LOCK", "MIGRATE_AND_REMOVE"] | None
    peer_auto_install: Literal["NOT_AUTOMATIC", "NPM_SOLVER"]
    optional_peer_absence_allowed: bool
    optional_dependency_omission: Literal["ALLOWED_WITH_NPM_EVIDENCE", "DEFER_TO_NPM"]
    dev_dependencies_required: bool
    policy_version: str
    checksum: str

class LockfileAuthority(BaseModel):
    path: Path
    kind: Literal["SHRINKWRAP", "PACKAGE_LOCK"]
    filename: Literal["npm-shrinkwrap.json", "package-lock.json"]
    lockfile_version: Literal[1, 2, 3]
    sha256: str
    policy_checksum: str

def select_lockfile_authority(
    workspace: Path, *, policy: LockfileAuthorityPolicy
) -> LockfileAuthority: ...
```

Selection is deterministic and matches the bound npm capability. For npm 6–11, `shrinkwrap_behavior=PREFERRED`: choose `npm-shrinkwrap.json` when present, otherwise `package-lock.json`, otherwise raise `PACKAGE_LOCK_MISSING`; when both exist, shrinkwrap is the sole authority. For npm 12+, `shrinkwrap_behavior=UNSUPPORTED`: `unsupported_shrinkwrap_action` must be explicit; `IGNORE_WITH_PACKAGE_LOCK` may select `package-lock.json` when both files exist, `MIGRATE_AND_REMOVE` authorizes a governed conversion, and `BLOCK` fails closed. If shrinkwrap is the only candidate, raise `SHRINKWRAP_UNSUPPORTED_BY_NPM` unless `MIGRATE_AND_REMOVE` authorizes the change. Unsupported npm majors or missing exact npm identity block with `LOCK_AUTHORITY_POLICY_UNSUPPORTED`. An unsupported or malformed authoritative shrinkwrap never silently falls through to a valid package-lock. A lone `yarn.lock` is not selected; in an npm-governed stage it blocks under existing package-manager policy. No Yarn migration support is added.

The selected authority is then parsed by `PackageLockReader`, the one pure canonical resolved-state reader used by baseline/source proof, dependency closure/preflight, LockResolution, target proof, failure bundles, and migration owner exact-version lookup:

```python
class PackageLockReader:
    @classmethod
    def from_authority(cls, authority: LockfileAuthority) -> "PackageLockReader": ...
    def detect_version(self) -> Literal[1, 2, 3]: ...
    def top_level_resolved_version(self, package: str) -> str | None: ...
    def resolved_version(self, package: str, *, parent_path: str | None = None) -> str | None: ...
    def dependency_edges(self, package: str, *, parent_path: str | None = None) -> Mapping[str, str]: ...
    def requested_edges(self, package: str, *, parent_path: str | None = None) -> Mapping[str, str]: ...
    def integrity(self, package: str, *, parent_path: str | None = None) -> str | None: ...
    def package_exists(self, package: str, *, parent_path: str | None = None) -> bool: ...
    def dependency_set(self) -> LockfileDependencySet: ...
    def root_sync_with_manifest(
        self,
        dependency_intent: DependencyIntent,
        npm_capability_policy: LockfileAuthorityPolicy,
        *,
        npm_evidence: Mapping[str, object] | None = None,
    ) -> LockfileRootSyncResult: ...
```

`LockfileRootSyncResult` records each package, `DependencyIntentKind`, source section, requested spec, resolved version if any, npm capability/policy checksum, static evaluation result, absence semantics, one of `STATIC_CHECK`, `VERIFIED`, `MISMATCH`, or `DEFER_TO_NPM`, a reason code, and (when deferred) the governed npm solve/`npm ci`/`npm ls` evidence reference. `STATIC_CHECK` is an evaluation capability/result only; it is not success until the result is `VERIFIED` or deferred semantic authority is proven by npm. Root sync consumes `DependencyIntent` and the bound capability policy; it does not accept a flattened manifest map.

Conceptually each finding is immutable and section-aware:

```python
class RootSyncFinding(BaseModel):
    package: str
    section: Literal["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"]
    kind: DependencyIntentKind
    peer_metadata: Mapping[str, object] | None
    requested_spec: str
    resolved_version: str | None
    npm_capability_policy_checksum: str
    static_result: Literal["STATIC_CHECK", "VERIFIED", "MISMATCH", "DEFER_TO_NPM"]
    status: str  # e.g. ROOT_REQUIRED_VERIFIED, ROOT_OPTIONAL_ABSENT_ALLOWED
    absence_semantics: str | None
    reason_code: str
    deferred_npm_evidence_ref: str | None
```

`RootSyncFinding.status` is descriptive evidence, not a second success authority. Required/dev missing entries are mismatches; optional and optional-peer absence can be allowed; npm 3–6 peer absence is allowed-or-deferred; npm 7+ peer outcomes remain npm-solver evidence. A contradictory npm tree overrides any permissive static finding.

`package.json` owns requested root `dependencies`, `devDependencies`, `optionalDependencies`, `peerDependencies`, and `peerDependenciesMeta`; the baseline parser constructs one immutable `DependencyIntent` and preserves all sections until root sync completes. A peer with `peerDependenciesMeta[package].optional == true` is classified `OPTIONAL_PEER`, never ordinary `PEER`. V1 supplies top-level/nested resolved versions, nested `dependencies`, `requires` requested edges, integrity/resolved metadata, and dev/optional flags where present; it never reconstructs original root requested ranges. V2/V3 may contain declaration mirrors under `packages[""]`, but callers still take root intent only from `DependencyIntent` created from package.json. They use `packages` plus dependency metadata for resolved nodes and edges.

Root-sync applies these section/capability rules without becoming an npm solver:

- `REQUIRED` (`dependencies`): supported registry specs with compatible resolution are `VERIFIED`; deterministic incompatibility or missing resolution is `MISMATCH`; unsupported/complex specs are `DEFER_TO_NPM`.
- `DEV` (`devDependencies`): governed migration install mode requires materialization, so compatible resolution is `VERIFIED`, missing resolution is `MISMATCH`, and unsupported specs are `DEFER_TO_NPM`; dev entries are never silently ignored.
- `OPTIONAL` (`optionalDependencies`): present entries are validated normally; absent entries are `OPTIONAL_ABSENT_ALLOWED` only when the bound npm/platform evidence permits omission. Absence never synthesizes a lock entry and never authorizes fresh-lock fallback by itself.
- `PEER` (`peerDependencies`) under npm 3–6: peer absence is not an ordinary required-root mismatch because peers are not automatically installed; a present compatible peer may be `VERIFIED`, while absence is `ROOT_PEER_ABSENT_NPM6_ALLOWED_OR_DEFERRED` and is finalized only with governed npm/tree evidence. npm warnings remain evidence and root sync never fabricates installation.
- `PEER` under npm 7+: `peer_auto_install=NPM_SOLVER` delegates peer graph behavior to governed npm solve/`npm ci`/`npm ls`; Python may statically verify only safe simple versions, while npm evidence owns final success or dependency failure.
- `OPTIONAL_PEER` (`peerDependenciesMeta[package].optional == true`): absence is `OPTIONAL_PEER_ABSENT_ALLOWED`; presence is validated for compatibility; absence is never `MISMATCH`.

`optional_dependency_omission`, `optional_peer_absence_allowed`, `peer_auto_install`, `dev_dependencies_required`, npm major/exact version, lock-authority behavior, policy version, and policy checksum are all bound inputs. The governed install mode must include dev dependencies for migration/build/test unless an explicit policy says otherwise.

Rename `LockfileDependencySet.root_dependencies` to `top_level_resolved`; it contains exact resolved versions only. If historical serialized evidence uses the old field, the legacy reader may map it into `top_level_resolved` without exposing it as requested intent, while all new writers emit only the new name. `root_sync_with_manifest` uses a versioned, bounded static-check allowlist already shared by the repository's dependency-source/spec validators and returns `STATIC_CHECK`, `VERIFIED`, `MISMATCH`, or `DEFER_TO_NPM` for each requested spec. The allowlist may cover only already-proven simple registry forms; the reader must not recreate npm semver/spec behavior in Python. Tilde specs, compound comparator sets, `x`/`*`, OR expressions, npm aliases, `file:`, `git:`, `workspace:`, and any other non-allowlisted or non-registry spec defer to npm rather than being guessed. A deferred spec can pass only after governed npm lock generation and clean `npm ci`/`npm ls` provide semantic authority, with selected lock/tree evidence bound to the same execution; npm rejection routes to dependency/lock ownership.

Callers receive the same resolved-state contract for V1/V2/V3 and never inspect either representation. The reader preserves authority filename/kind, raw bytes/payload/schema/checksum, and canonical dependency-set checksum for evidence and never rewrites JSON. Non-object JSON, missing/non-integer/unsupported `lockfileVersion`, invalid root/dependency shapes, and ambiguous entries raise explicit `PACKAGE_LOCK_MALFORMED` or `PACKAGE_LOCK_VERSION_UNSUPPORTED`; absence is separately `PACKAGE_LOCK_MISSING`.

Every solve/materialization ledger records exact npm identity/policy checksum and input/output lockfile version. A V1→V2/V3 schema transition is valid only when caused by the governed npm solver, root sync passes (or every `DEFER_TO_NPM` spec has the governed npm evidence), exact package evidence remains provable, raw before/after artifacts are immutable, and `LockSchemaTransitionEvidence` binds old/new versions, npm identity, execution ID, and checksums. No Transformer service assumes `packages[""]` exists.

Use `LockfileGenerationRunner` as the single solve owner after removing its normal-path dependency on `RepairAttemptModel`; it consumes `LockfileAuthority` plus `PackageLockReader` results rather than filenames or raw lock dictionaries.

```text
mode = PRESERVE | FRESH
status = READY | RUNNING | CONVERGED | MATERIALIZING | PROVED | FAILED
attempt = 1..max_attempts (frozen policy default 5)
fresh_fallback_used = false initially
previous_lock_sha256 = null initially
```

For each solve attempt:

1. Verify live binding equals expected generation fingerprint.
2. Re-select and verify authority, then record selected filename/kind, manifest SHA, input lock SHA/version/canonical dependency-set checksum, runtime identity, mode, attempt, and command authority.
3. Run the existing registered npm lock-generation command (`npm install --package-lock-only`) in the governed workspace; the selected authority, not the flag's name, determines which lock file npm consumes/writes.
4. Classify nonzero result by phase/evidence.
5. On zero, re-select the same authority kind, re-read it through `PackageLockReader`, verify manifest/`DependencyIntent` unchanged, only the selected authoritative lock changed, schema supported, section-aware intent synchronized with resolved state under the exact npm capability, and any schema transition evidence complete.
6. Record output lock SHA.
7. If output SHA equals the preceding successful attempt, mark converged; otherwise queue the next attempt.
8. Exceeding budget yields `LOCK_CONVERGENCE_EXHAUSTED`.

Fresh fallback is allowed once only for a proven inherited stale/corrupt/incompatible lock and is authority-kind/policy specific. For PACKAGE_LOCK authority, reconstruct target intent, remove only root `package-lock.json`, verify no shrinkwrap appeared (or verify the explicit npm 12+ unsupported-shrinkwrap policy), reset convergence comparison, and continue in FRESH mode. For SHRINKWRAP authority, automatic deletion/replacement is forbidden: removal or conversion to package-lock requires an explicit checksum-bound dependency-policy decision naming the shrinkwrap preimage and intended resulting authority, after which the runner reconstructs and re-selects authority. Without that decision, block with `SHRINKWRAP_POLICY_DECISION_REQUIRED` or `SHRINKWRAP_UNSUPPORTED_BY_NPM` as applicable. ETARGET, general peer incompatibility, runtime, harness, workspace faults, or the mere presence of shrinkwrap do not authorize deletion.

After convergence, create a clean materialization generation, re-select the same authority, run `npm ci`, prove package and selected-lock SHAs unchanged, prove npm and Factory referenced the same filename/kind/checksum, run `npm ls --all --json`, validate the physical/logical tree, and only then mark `PROVED`. Duplicate transitive package names are valid unless npm identifies an invalid, missing, or extraneous edge.

Persist `LockResolutionLedger` as an immutable artifact containing cycle ID, mode, exact npm descriptor/policy checksum, authority filename/kind, attempt records, input/output raw SHA and lockfile versions, canonical dependency-set checksums, `DependencyIntent` checksum, per-section/per-kind/absence-aware root-sync findings and deferred npm evidence, schema-transition evidence/checksum, fallback classification/evidence or shrinkwrap policy decision, converged SHA, materialization execution IDs, npm-ci/npm-ls authority proof, dependency-tree checksum, and terminal status.

## 10. Dependency planning model

The deterministic planner reads root requested intent exclusively from authoritative package.json through the immutable section-preserving `DependencyIntent`; it reads resolved state from the canonical npm-policy-selected `LockfileAuthority`/`PackageLockReader`, plus installed tree, registry metadata, `engines`, `ng-update`, packageGroup, requirements, Stage Knowledge, and official catalogue. It consumes section-aware `root_sync_with_manifest` findings as `VERIFIED`/`MISMATCH` or `DEFER_TO_NPM`; it never flattens sections or invents a result for a deferred spec. Direct dispositions are `KEEP | UPGRADE | REMOVE | REPLACE | DETACH_TEMPORARILY | BLOCK | UNKNOWN`.

The Factory validates and freezes direct intent. npm alone resolves transitives. No custom SAT solver, global package-version database, fixture package branch, or “one version per package name” rule is permitted.

Existing `DependencyRepairPreflightService`, `DependencyClosureService`, and `DependencyNormalizationService` remain deterministic primitives. New-plan dependency changes are backend-authored from TargetIntent and metadata; the Main Repair LLM is not called.

## 11. MigrationLedger

After target materialization:

1. Bind the exact npm capability policy, construct section-aware source/target `DependencyIntent` from package.json, select lock authorities, and compare exact resolved versions through `PackageLockReader`, including V1 sources and nested lookup where evidence requires it.
2. Inspect installed target manifests for `ng-update.migrations`.
3. P06-A includes every changed direct package that declares a migration collection; no Core/CLI priority set.
4. P06-B traverses `packageGroup` and `requirements`, parses applicable collection entries in `(from, to]`, and supports individually named optional migrations with deterministic ordering/dependency decisions.
5. Build a MIGRATION-purpose `AngularCliToolchainAuthority` from the materialized target's installed CLI package and absolute entrypoint; required owners run proven `angular-migrate-range` only through that authority.
6. Optional entries are RUN, SKIP, or PENDING HUMAN; PENDING blocks before execution.
7. Record each execution’s pre/post fingerprint, package.json SHA, and selected lock filename/kind/SHA.
8. Re-enter LockResolution only when dependency authority changed.

Artifact fields: schema/version, source/target `DependencyIntent` and checksum, npm capability/policy checksum, source/target locks, metadata/collection checksums, ordered owners, from/to exact, required/optional entries, decision authority, execution IDs, pre/post fingerprints, changed authority flag, status, checksum.

## 12. Validation and diagnostic delta model

`StageSandboxCopier` creates source, materialization, validation, and repair candidates while excluding governed volatile output. `.git`, `node_modules`, `dist`, `.angular`, caches, logs, and symlinks never become inherited validation state.

Normalize diagnostics to `(tool, target, relative_path, code_or_rule, severity, normalized_message)`. Compare source baseline and target:

```text
PRE_EXISTING: same identity and message in both
NEW:          target only
RESOLVED:     source only
CHANGED:      same identity, different severity/message
```

`BaselineAwareValidationService` becomes build/test/lint-aware. Approved pre-existing debt may pass only under the existing G03/G09 policy; NEW or disallowed CHANGED diagnostics fail even if another command succeeds.

`ValidationSummary` binds candidate path/fingerprint, package SHA, immutable section-aware `DependencyIntent` checksum, exact npm/`LockfileAuthorityPolicy` checksum, selected lock filename/kind/raw SHA/version/canonical dependency-set checksum, section-aware root-sync classifications, target CLI authority checksum, npm-ci authority/tree/exact-version evidence, validation executions, DiagnosticDelta checksum, target plan/catalogue/runtime checksums, status, and artifact checksum. Exact source/target validation selects through the npm-policy `LockfileAuthority`, reads V1/V2/V3 resolved state only through `PackageLockReader`, and takes root intent only from `DependencyIntent` created from package.json.

## 13. Failure-owner routing

Phase and evidence type precede message regex:

| Owner | Examples by evidence class | Destination |
|---|---|---|
| HARNESS | parser failure, missing artifact, command-worker loss, contaminated disposable generation, filesystem/platform failure | platform recovery/reconstruct/retry; never Repair LLM |
| RUNTIME | unresolved/mismatched/checksum-changed Node/npm/npx, CLI entrypoint/package/actual-version/delegation mismatch, governed PATH or child npm mismatch, incompatible engines | runtime/toolchain resolver; never Repair LLM |
| DEPENDENCY | ETARGET, peer/engine incompatibility, npm peer-solver failure, invalid npm tree, or section-aware required/dev/peer conflict | compatibility planner + npm solver |
| LOCKFILE | missing/wrong-precedence/drifted authority, malformed/unsupported authoritative lock, section-aware required/dev manifest/resolution mismatch, stale/corrupt/inherited lock, nonconvergence, missing shrinkwrap policy decision, invalid schema transition, or converged lock rejected/consumed differently by clean `npm ci` | LockResolution/dependency-policy decision |
| DETERMINISTIC_SOURCE | exact versioned Stage Knowledge rule matches diagnostics and preimage | isolated deterministic candidate |
| MAIN_REPAIR | unknown application source/template/test/config | one bounded ProblemGroup to Main Repair LLM |

## 14. Repair and reviewer architecture

Main Repair LLM input is exactly one `ProblemGroup`, source/target context, normalized diagnostics, baseline delta, bounded authoritative files, exact preimages, Stage Knowledge, allowed validation targets, and current human request-change text. Output is structured `replace_text`, `create_text_file`, or `delete_text_file` intent only.

New proposals cannot contain dependency operations or `unified_diff`; compatibility readers retain old shapes. Reviewer decisions are `accept | request_changes | reject | insufficient_context`, and reviewer schema forbids operations/diff/commands. G10 and current human policy remain authoritative. After repaired clean validation, the only success route is G11→G09→exact promotion→G12→seal.

## 15. Candidate, promotion, and sealing model

Repair apply receives a frozen failed generation, copies it to a contained repair candidate, and applies through existing `PatchApplyService`. The active binding remains unchanged. A separate clean validation generation is created from the repaired candidate. Failed candidates are recorded but never promoted.

`CandidatePromotionService` must use `STAGE_FINGERPRINT_PROFILE`, load the exact approved ValidationSummary and gate packages, rehash the candidate, and enforce one order. Normal validation creates/awaits G09, then promotes. Repaired validation creates/awaits G11, then creates/awaits G09, then promotes. Both paths create G12 only after promotion makes that generation active.

```text
live candidate fingerprint
== ValidationSummary.candidate_fingerprint
== approved G11 workspace_fingerprint (repair path only)
== approved G09 workspace_fingerprint
== CandidatePromotionDecision.candidate_fingerprint
== active promoted workspace fingerprint
== StageSealingService source fingerprint
```

For proven plans, `StageGateService` keeps existing code-truth `G11 → CREATE_G09` and changes the G09 approved successor from direct `CREATE_G12` to `PROMOTE_VALIDATED`; legacy plans retain their historical successor. Promotion success advances to `CREATE_G12`; G12 approval advances to seal. `StageSealingService` additionally enforces active binding = promoted fingerprint = G09 fingerprint = optional G11 fingerprint = validation fingerprint before G12 copy/seal. Existing seal manifest, chain hash, target version verification, and `NextStageMaterializerService` remain.

## 16. Backward compatibility strategy

- Add `transformer_semantic_version` to the Pydantic stage-plan JSON contract; no DB column.
- Add immutable `run_mode`; missing mode reads as PRODUCTION, and QUALIFICATION always requires its authorization checksum.
- Planner emits `transformer-plan-v2.2-proven-1` only after Phase 2.
- Dispatcher selects legacy/proven handlers once per continuation from its persisted stage plan.
- Old V2–V6 updater templates, installed-migration helper, node names, recovery code, repair dependency operations, and unified-diff readers remain [DEPRECATE]/[REMOVE-LATER].
- Legacy npx-based updater/migrate templates retain historical behavior only; proven plans require `AngularCliToolchainAuthority`.
- Existing lock evidence remains readable, while every new proven run records selected authority and normalizes its V1/V2/V3 resolved state through `PackageLockReader` without rewriting stored JSON. Missing authority metadata on historical evidence is interpreted only by the legacy semantic handler.
- New plan writers never emit legacy shapes.
- Legacy nonterminal continuations complete under legacy semantics; no mid-stage conversion exists.
- Removal requires an explicit compatibility-window decision and proof that no nonterminal persisted row references the legacy shape.

## 17. Complete new Transformer graph

```text
validate_g06 → select_run_mode → prepare_stage_layout → resolve_runtime
  ├─ PRODUCTION + exact certified profile → continue
  ├─ PRODUCTION + uncertified → block STAGE_RUNTIME_CERTIFICATION_REQUIRED
  ├─ QUALIFICATION + officially allowed + explicit authorization → continue in qualification authority
  └─ QUALIFICATION without envelope/authorization → block
→ dependency_preflight
→ collect_stage_knowledge → create/wait_g07
→ create_source_baseline → construct_dependency_intent → bind_npm_lock_authority_policy → select_source_lock_authority → read_source_resolved_lock_v1_v2_v3
→ prove_section_aware_manifest_intent_vs_lock_resolution → source_install_same_authority → source_tree → source_version_proof
→ source_build → source_test → source_diagnostic_capture → freeze_source_baseline
→ create_discovery_generation → prepare/select_discovery_toolchain
→ prove_discovery_cli_and_child_npm_authority → run_discovery → assess_discovery
  ├─ preflight CLI/PATH/child-npm authority mismatch → block before discovery command
  ├─ execution-time CLI/delegation mismatch → discard disposable result and block before TargetIntent
  ├─ incomplete/retryable → next governed discovery strategy → run_discovery
  ├─ incomplete/exhausted → classify_failure
  └─ complete (exit zero or nonzero) → persist_target_intent → discard_discovery
→ create_authoritative_target → apply_target_intent → dependency_plan
→ select_target_lock_authority(bound npm policy) → lock_resolution(canonical authority + reader)
  ├─ PACKAGE_LOCK + classified fallback eligible → governed package-lock regeneration → lock_resolution
  ├─ npm 6–11 SHRINKWRAP + no explicit replacement policy → block SHRINKWRAP_POLICY_DECISION_REQUIRED
  ├─ npm 12+ SHRINKWRAP present/unsupported without migration policy → block SHRINKWRAP_UNSUPPORTED_BY_NPM
  ├─ SHRINKWRAP + approved replacement/migration policy → governed authority replacement → reselect authority → lock_resolution
  └─ converged → create_materialization
→ reselect_materialized_lock_authority → target_install_same_authority → target_tree → target_version_proof
→ inspect_migration_metadata → build_migration_ledger
→ bind/prove exact materialized target CLI authority → create/wait_g08
→ execute_migration_owner loop → compare_dependency_authority
  ├─ changed → lock_resolution
  └─ unchanged → freeze_target_authority
→ create_validation_generation → validation_install → validation_tree
→ validation_version_proof → validation_build → validation_test → validation_lint?
→ diagnostic_delta → aggregate_validation
  ├─ normal pass → create/wait_g09 → promote_validated → create/wait_g12
  │        → seal_stage → materialize_next_stage → next stage/complete
  └─ fail → classify_failure
           ├─ HARNESS → platform_recovery → failed node
           ├─ RUNTIME → resolve_runtime → reconstruct → failed node
           ├─ DEPENDENCY → deterministic_dependency_plan → lock_resolution
           ├─ LOCKFILE → lock_resolution
           ├─ DETERMINISTIC_SOURCE → create/apply_repair_candidate
           └─ MAIN_REPAIR → create candidate → propose → review → G10 → apply
          → create clean validation → full validation → create/wait_g11
          → create/wait_g09 → promote_validated → create/wait_g12 → seal

QUALIFICATION terminal evidence → immutable qualification bundle → explicit evidence review
  ├─ deterministic evidence promotion accepted → exact profile becomes certified for future PRODUCTION plans
  └─ incomplete/rejected → remains observed/allowed only; never production-certified
```

## 18. Phase dependency graph

```text
P00 baseline
 └─ P01 catalogue truth
     └─ P02 semantic version
         └─ P03 lock authority/resolved reader/source baseline
             └─ P04 discovery/intent
                 └─ P05 lock resolution
                     └─ P06 materialization/migrations
                         └─ P07 freeze/validation/delta
                             └─ P08 promotion/seal
                                 ├─ P09 failure ownership
                                 │   └─ P10 repair isolation/LLM
                                 │       └─ P11 deterministic rules
                                 └─ P12 recovery/idempotency
                                     └─ P13 projections
                                         └─ P14 adjacent qualification
                                             └─ P15 final 11→21 E2E
```

## 19. Phase-by-phase implementation

## Phase P00 — Baseline and code-truth freeze

### Objective

Freeze repository identity, current architecture ranges, and the pre-change test node/result set so later failures can be classified as baseline or regression.

### Why

At audited HEAD the full suite cannot collect, and the executable remainder is heavily red. Implementation without a frozen node-level baseline would make regression attribution unreliable.

### Preconditions

Clean `v2.2` checkout; no implementation phase has started.

### Existing code to REUSE unchanged

- [REUSE] `AGENT.md:1-473` — architecture and runtime contract.
- [REUSE] `TRANSFORMER_PRODUCTION_IMPLEMENTATION_PLAN.md:1-2041` — original production Transformer decisions and compatibility constraints.
- [REUSE] `backend/pyproject.toml:1-27` — pytest and ruff configuration.
- [REUSE] `scripts/test-backend.ps1:1-8`, `scripts/quality.ps1:1-27` — verified repository quality entrypoints.

### Existing code to UPDATE

NONE.

### New files to ADD

NONE. Store baseline output outside the repository under the run/operator evidence directory; do not commit generated logs.

### Files explicitly NOT to touch

All production, test, frontend, Alembic, and fixture files.

### Data/contracts

The baseline manifest is JSON with `branch`, `head`, `status`, command, Python version, collected node IDs, passed/failed/skipped/error node IDs, failure categories, timestamp, and SHA256 of raw pytest output. It is operator evidence, not a runtime DB contract.

### Workflow transitions

None. This phase records truth only.

### Command templates

None.

### Failure/recovery behavior

Do not repair failures. If HEAD/status changes during capture, discard the capture and restart P00. Preserve full-suite collection failure separately from the executable-suite result.

### Implementation steps

1. Record `git branch --show-current`, `git rev-parse HEAD`, `git status --short`, and repository root.
2. Run full backend pytest and record the collection blocker.
3. Run the backend suite with `--continue-on-collection-errors` to capture executable node-level results without excluding any file; record this as diagnostic baseline evidence, not a release waiver.
4. Group failures by shared contract, not by guessed production root cause.
5. Record focused Transformer/planning/lock/repair/runtime/sealing nodes for later phase comparisons.
6. Review the file/range inventory in sections 2 and 5 against current HEAD.

### Tests to ADD/UPDATE

- Baseline expected: full suite stops collecting because `tests/test_transformer_stage_runtime_integration.py` imports absent `_runtime_bindings_from_stage`.
- Baseline executable result: record the exact passed/failed/skipped/error counts produced with collection errors retained; do not convert the missing-helper import into an excluded-file baseline.
- Baseline executable errors: `test_command_terminal_lifecycle.py::test_cancellation_and_timeout_keep_distinct_terminal_states` plus the two failing setup/error cases in `test_s3_f02_api_integration.py`; retain exact node IDs from the raw pytest manifest.
- Baseline failure clusters: shared persistence/harness state, repair/recovery lineage, runtime discovery/binding, command lifecycle, compatibility catalogue/planning, lock/dependency evidence, and projection/API/assistant drift.
- New expected: none.
- Regression rule: P00 changes no tracked file and therefore cannot change any result.

### Commands to run

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q --tb=no
.\.venv\Scripts\python.exe -m pytest -q --tb=no --continue-on-collection-errors
Pop-Location
```

### Runtime validation

Not a behavioral phase. Input is the current backend test corpus; source/target Angular and stage runtime are not applicable. Pass when both baseline outcomes and raw-output checksums are recorded. Inspect pytest collection output and the external baseline manifest on failure.

### Acceptance criteria

- [ ] Branch is `v2.2` and HEAD is recorded.
- [ ] Worktree is clean before and after capture.
- [ ] Full-suite collection blocker is recorded separately.
- [ ] The collection blocker is assigned to P12 and is not waived by excluding its test file.
- [ ] Executable-suite counts and node IDs are frozen.
- [ ] Failure categories include catalogue/planning, runtime, command lifecycle, dependency/lock, repair/recovery, persistence/harness, and projection/API drift.

### Completion evidence

External baseline manifest plus raw pytest logs and checksums; no repository modification.

### Rollback/recovery notes

Delete the incomplete external capture and rerun. There is no repository state to roll back.

### Agent handoff

P01 may rely on the exact repository identity and must compare every test result against the frozen node set.

## Phase P01 — P0-0 Compatibility truth and production/qualification authority

### Objective

Separate official support envelopes from exact Factory-certified runtime/target evidence, make production fail closed, and provide an explicitly authorized qualification path that cannot auto-certify.

### Why

Current catalogue values and labels do not consistently match the proven manual chain, while manual observations alone are not immutable certification evidence.

### Preconditions

P00 complete and baseline evidence available.

### Existing code to REUSE unchanged

- [REUSE] `backend/app/services/runtime_resolver_authority.py:53-215` — path-independent executable discovery/guard.
- [REUSE] `backend/app/services/runtime_resolution_application_service.py:36-210` — runtime evidence persistence.
- [REUSE] `backend/app/services/stage_runtime_service.py` — stage binding and certification lookup.
- [REUSE] `backend/app/repositories/catalogue_certification_models.py` and migrations `20260816_52`, `20260816_54`, `20260817_69` — existing catalogue/certification persistence.
- [REUSE] existing immutable artifact metadata and audit-event records for qualification authorization/evidence/review; no new table.

### Existing code to UPDATE

- [UPDATE] `backend/app/domain/compatibility.py:59-144` — `RuntimeProofProfile`, `CompatibilityCatalogueEntry`; add explicit evidence classification (`official_envelope`, `observed`, `certified`) and require immutable artifact/checksum references before certified status. Callers: compatibility resolution, planner, runtime certification. Compatibility: deserialize old rows as observed/uncertified.
- [UPDATE] `backend/app/services/compatibility_catalogue_provider.py:17-279` — retain official ranges; reconcile exact targets/profiles only where repository evidence proves them; remove misleading “proven/certified/passed” labels without evidence. Callers: compatibility application, planner, tests. Compatibility: catalogue version increments; old catalogue versions remain loadable.
- [UPDATE] `backend/app/services/compatibility_application_service.py` — block production selection of allowed-but-uncertified exact profiles with `STAGE_RUNTIME_CERTIFICATION_REQUIRED`; keep analysis reporting available. Callers: G05/planner.
- [UPDATE] `backend/app/services/registry_snapshot_builder.py:19-69` — retain all queried package metadata instead of filtering to Core/TypeScript/RxJS; bind metadata to registry identity/checksum. Callers: compatibility/dependency planning.
- [UPDATE] `backend/app/domain/runtime_certification.py:26-118` — add PRODUCTION/QUALIFICATION decision inputs and immutable authorization/evidence/promotion contracts; preserve existing classifications.
- [UPDATE] `backend/app/services/runtime_certification_service.py:32-166` — production requires `certified=True`; qualification requires official range compatibility plus explicit authorization; add evidence validation/promotion separate from execution.
- [UPDATE] `backend/tests/test_compatibility_catalogue_provider.py` and `test_catalogue_certification_f30.py` — replace stale exact expectations with evidence-status assertions.
- [UPDATE] `backend/tests/test_runtime_certification_f11.py` and `backend/tests/test_stage_runtime_f02.py` — production rejection, qualification authorization, no auto-promotion, and deterministic certification promotion.

### New files to ADD

NONE. Existing catalogue/certification rows and immutable artifacts own this evidence.

### Files explicitly NOT to touch

Transformer graph, command templates, repair code, frontend, workspace generation models, and all Alembic migrations.

### Data/contracts

`RuntimeProofProfile` adds evidence artifact ID/checksum and a status that cannot be `certified` without both. `CompatibilityCatalogue.version` advances according to existing version convention. The manual chain values enter as `observed_external` unless immutable repository evidence is found. Add plan `run_mode: PRODUCTION | QUALIFICATION`, `RuntimeQualificationAuthorization`, `RuntimeQualificationEvidence`, and `RuntimeCertificationPromotionDecision` as checksum-bound JSON contracts stored through existing artifacts/audit records. Use deterministic immutable paths `04_workflow_state/stages/{stage_id}/runtime-qualification/{authorization_digest}/authorization.json`, `.../evidence.json`, and `.../promotion.json`, where the digest is lowercase SHA256 hex without a scheme prefix. Derive `RuntimeCertificationModel.id` from stage, exact runtime descriptor checksums, catalogue checksum, and promotion/evidence checksum, then store the authoritative certification decision at `04_workflow_state/stages/{stage_id}/runtime-certifications/{record_id}.json`. `enforce_stage_certification()` loads and revalidates that artifact by row ID/path, so the existing row remains an indexed projection and no evidence-reference column is required.

### Workflow transitions

PRODUCTION: allowed envelope → certified exact evidence lookup → execute or `STAGE_RUNTIME_CERTIFICATION_REQUIRED`. QUALIFICATION: allowed envelope → approved inventory tuple → explicit authorization → qualification-only workflow/evidence → explicit review → deterministic certification promotion or remain uncertified. No qualification output is silently exposed to production.

### Command templates

No new templates. Existing runtime probes remain authoritative.

### Failure/recovery behavior

Missing/corrupt evidence blocks certification without changing old evidence. Production never falls back to qualification. Qualification restart reloads the same mode, authorization, inventory descriptors, and checksums; stale/expired/mismatched authorization blocks. A command-pass cannot set certification. No runtime is auto-installed.

### Implementation steps

1. Add failing tests for certification without immutable evidence and allowed-but-uncertified routes.
2. Inventory every exact/proven/certified catalogue tuple and its evidence reference.
3. Implement evidence-status validation in domain contracts.
4. Reconcile provider data without copying manual values into certified rows.
5. Update compatibility resolution to select only authorized certified profiles.
6. Expand registry snapshot metadata without a package allowlist.
7. Add explicit qualification authorization/evidence/review contracts using existing artifact/audit persistence.
8. Split production enforcement from qualification resolution; change current `allowed` enforcement to exact `certified` enforcement.
9. Add deterministic promotion that validates the complete immutable evidence bundle before certification.
10. Run focused tests and compare against P00.

### Tests to ADD/UPDATE

- Unit: `test_compatibility_catalogue_provider.py::test_certified_profile_requires_immutable_exact_tuple_evidence`.
- Unit: official range may exist without certified profile.
- Integration: `test_runtime_certification_f11.py` rejects mismatched executable/evidence checksums.
- Integration: production rejects RANGE_COMPATIBLE; qualification accepts it only with matching explicit authorization and never auto-certifies.
- Integration: evidence promotion rejects incomplete/checksum-drifted bundles and certifies only after explicit review.
- Baseline expected: current catalogue tests are among P00 failures.
- New expected: updated catalogue/certification tests pass.
- Regression rule: no previously passing runtime guard or catalogue checksum test may fail.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_compatibility_catalogue_provider.py tests/test_compatibility_catalogue_f09.py tests/test_catalogue_certification_f30.py tests/test_runtime_certification_f11.py tests/test_stage_runtime_f02.py
.\.venv\Scripts\python.exe -m ruff check app/domain/compatibility.py app/domain/runtime_certification.py app/services/compatibility_catalogue_provider.py app/services/compatibility_application_service.py app/services/registry_snapshot_builder.py app/services/runtime_certification_service.py
Pop-Location
```

### Runtime validation

Fixture/input: one certified production tuple and one allowed-but-uncertified qualification tuple. Evidence: mode, authorization actor/purpose/checksum, catalogue snapshot, exact Node/npm/npx paths/versions/checksums, complete qualification bundle, review, and promotion decision. Pass when production accepts only the certified tuple, qualification runs only the explicitly authorized tuple, and certification appears only after deterministic evidence promotion. Inspect authorization/evidence/promotion artifacts on failure.

### Acceptance criteria

- [ ] Official envelope and certified exact profile are distinct.
- [ ] No exact tuple is certified without immutable evidence.
- [ ] Manual values are not fabricated into certification.
- [ ] Planner-facing resolution blocks uncertified production profiles.
- [ ] Qualification can use an officially allowed uncertified profile only with explicit actor/purpose authorization.
- [ ] Qualification never bypasses official constraints and never auto-promotes on command success.
- [ ] Immutable qualification evidence plus explicit review is required before certified status.
- [ ] No Angular-major orchestration branch is added.

### Completion evidence

Updated catalogue snapshot/checksum, focused test output, evidence reconciliation table, and no Alembic change.

### Rollback/recovery notes

Old catalogue versions remain loadable. Revert the new catalogue version pointer if reconciliation is rejected; never rewrite historical evidence.

### Agent handoff

P02 may rely on explicit immutable PRODUCTION/QUALIFICATION mode and a catalogue API that distinguishes allowed, qualification-authorized, and certified truth.

## Phase P02 — P0-1 Proven plan and graph semantic version

### Objective

Introduce an immutable semantic discriminator so new plans use the proven graph while historical nonterminal plans keep legacy behavior.

### Why

Changing the meaning of existing node or command groups in place would silently migrate persisted continuations halfway through execution.

### Preconditions

P01 complete; catalogue version and certification rules frozen.

### Existing code to REUSE unchanged

- [REUSE] `StageExecutionPlanModel.stage_plan` JSON storage and plan checksum/version rows.
- [REUSE] `TransformationContinuationModel.stage_plan_id` and state-version/lease mechanics.
- [REUSE] historical command-template version registry.

### Existing code to UPDATE

- [UPDATE] `backend/app/domain/planning.py:155-201` — add `transformer_semantic_version` and `run_mode`; validate legacy and proven command-group sets separately. Callers: planner, command policy, next-stage materializer. Compatibility: missing semantic field maps to legacy and missing mode maps to PRODUCTION.
- [UPDATE] `backend/app/domain/transformation.py:46-117` — add proven node vocabulary and owner routes; retain legacy enum values. Callers: graph, recovery, API projection.
- [UPDATE] `backend/app/services/planning_application_service.py:89-209` — emit `transformer-plan-v2.2-proven-1` and new command groups only for new plans; stop prebinding Core-only migration. Callers: planning and next-stage generation.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:227-328` — dispatch by persisted semantic version before node handling; reject unknown version. Compatibility: legacy handler unchanged.
- [UPDATE] `backend/app/services/next_stage_materializer_service.py:36-166` — carry semantic version and derive N+1 plan from sealed N.
- [UPDATE] `backend/tests/test_planning_application_service_s2_f06_i01.py`, `test_transformation_continuation.py`, `test_next_stage_materializer.py`.

### New files to ADD

NONE.

### Files explicitly NOT to touch

Alembic, SQLAlchemy models, command worker execution semantics, runtime resolver, repair schemas, frontend.

### Data/contracts

`transformer_semantic_version: Literal["transformer-plan-legacy-1", "transformer-plan-v2.2-proven-1"]` and `run_mode: Literal["PRODUCTION", "QUALIFICATION"]`. Persisted JSON without semantic version is normalized to legacy and without mode to PRODUCTION on read but not rewritten. QUALIFICATION additionally binds its authorization checksum; a plan cannot change mode after creation.

### Workflow transitions

Before: one dispatcher for every continuation. After: load stage plan → choose immutable legacy/proven transition table and immutable mode → enforce matching runtime authority → execute current node.

### Command templates

Only command-group contract names are introduced here; concrete new templates arrive in their behavior phases. Proven plan generation remains disabled behind the semantic-version writer until required templates are registered.

### Failure/recovery behavior

Unknown semantic version blocks with `TRANSFORMER_SEMANTIC_VERSION_UNSUPPORTED`. Restart always reloads the same persisted version. No fallback from proven to legacy or vice versa.

### Implementation steps

1. Add legacy-missing-field and unknown-version tests.
2. Extend plan/node contracts.
3. Add separate command-group validators.
4. Add dispatcher semantic selection without changing legacy handlers.
5. Make planner and next-stage materializer persist the proven version behind an explicit readiness constant that remains false until P08.
6. Add mode/qualification-authorization binding and reject mode changes or missing qualification authority.
7. Verify plan checksums include semantic version, mode, and authorization checksum where applicable.

### Tests to ADD/UPDATE

- Unit: missing semantic field selects legacy.
- Unit: unknown version blocks.
- Unit: missing mode is legacy-compatible PRODUCTION; QUALIFICATION without authorization blocks; mode cannot change on restart/N+1.
- Integration: a legacy continuation remains on `angular_update`; a proven fixture dispatches to `create_source_baseline`.
- Baseline expected: planning fixtures currently fail catalogue authority checks.
- New expected: semantic-version tests pass; reconciled planning tests pass.
- Regression rule: historical command/template replay tests cannot change outcome.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_planning_application_service_s2_f06_i01.py tests/test_planning_transformation_boundary.py tests/test_transformation_continuation.py tests/test_next_stage_materializer.py
.\.venv\Scripts\python.exe -m ruff check app/domain/planning.py app/domain/transformation.py app/services/planning_application_service.py app/orchestration/transformer_graph.py app/services/next_stage_materializer_service.py
Pop-Location
```

### Runtime validation

Fixture: one seeded legacy continuation and one nonexecuting proven-plan fixture. Source/target: any adjacent supported stage. Runtime: not invoked. Evidence: persisted plan JSON/checksum and selected next node. Pass when legacy/proven selection is deterministic across restart. Inspect stage-plan and continuation rows on failure.

### Acceptance criteria

- [ ] Semantic version is checksum-bound in plan JSON.
- [ ] Historical missing field maps to legacy without row rewrite.
- [ ] Unknown version fails closed.
- [ ] New and legacy transition tables are distinct.
- [ ] No production proven plan executes before P08 readiness activation.

### Completion evidence

Focused test output and serialized legacy/proven plan examples.

### Rollback/recovery notes

The readiness writer remains disabled, so rollback is removal of unused proven dispatch code. Existing plans are unaffected.

### Agent handoff

P03 can add proven baseline nodes without touching legacy execution.

## Phase P03 — P0-2 Canonical LockfileAuthority/PackageLockReader and fresh source baseline

### Objective

First establish bound-npm capability/lock authority selection and one canonical V1/V2/V3 resolved-state reader, then for each proven stage create and freeze a clean source baseline proving section-aware `DependencyIntent` against that selected lock, `npm ci`/`npm ls` authority equality, full tree, exact source cohort, build, tests, and baseline diagnostics.

### Why

Angular 11/npm6 uses V1 while modern stages use V2/V3; V1 cannot reconstruct original root requested ranges, current parsing is fragmented, baseline chooses package-lock ahead of shrinkwrap contrary to npm, and some services assume `packages[""]`. Current bootstrap also runs in the active stage workspace and lacks `npm ls` and complete stage-local source proof.

### Preconditions

P02 semantic dispatch exists; P01 provides immutable mode and either certified PRODUCTION runtime authority or explicitly authorized officially allowed QUALIFICATION authority.

### Existing code to REUSE unchanged

- [REUSE] `backend/app/services/stage_preparation_primitives.py:24-100` / `StageSandboxCopier` — atomic copy and volatile exclusion.
- [REUSE] `TransformerStageService.snapshot_workspace`, checkpoint and reconstruction helpers.
- [REUSE] existing `npm-ci-bootstrap`, build/test/lint templates and `ValidationRunner.source_fingerprint`.
- [REUSE] runtime binding and G07 validation.
- [REUSE] `backend/app/domain/lockfile_compatibility.py:17-32` — `LockfileDependencySet` result contract and compatibility consumer.
- [REUSE] `backend/app/domain/baseline.py:157-168` — existing missing/exact-version mismatch concepts to preserve behind the canonical intent-versus-resolution result; its filename precedence and raw shape parsing are updated below.

### Existing code to UPDATE

- [UPDATE] `backend/app/domain/command.py:540-712` — register `npm-dependency-tree` (`npm ls --all --json`) as a read-only structured command. Callers: planner/stage runner.
- [UPDATE] `backend/app/domain/lockfile_compatibility.py:17-167` — add section 9 npm-version-aware `LockfileAuthorityPolicy`, section-aware `DependencyIntent`/`DependencyIntentKind`, resolved-state `PackageLockReader`, supported-version/shape errors, canonical top-level/nested versions, requested/resolved edges, integrity/root-sync classifications, bounded static spec checks with `DEFER_TO_NPM`, and rename `LockfileDependencySet` root field to exact `top_level_resolved` with legacy-read compatibility.
- [UPDATE] `backend/app/domain/baseline.py:59-134` — construct immutable `DependencyIntent` from package.json with distinct `dependencies`, `devDependencies`, `optionalDependencies`, `peerDependencies`, and `peerDependenciesMeta`; classify optional peers without flattening sections before root-sync. Legacy flattened views remain readable only outside proven semantic evaluation.
- [UPDATE] `backend/app/domain/baseline.py:137-174` — replace its current package-lock-first selection with npm-version-aware `select_lockfile_authority(..., policy=...)`, construct `DependencyIntent`, and delegate section-aware root sync to `PackageLockReader`; package.json remains requested-root authority.
- [UPDATE] `backend/app/services/planning_application_service.py:143-178` — include source install/tree/proof/build/test groups in proven plans.
- [UPDATE] `backend/app/services/transformer_stage_service.py:107-203,443-715,718-1493` — create contained `source-baseline-g{n}` from sealed input, bind/snapshot it without promoting it as target authority, and queue explicit source groups.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:341-491,958-1131` — proven flow after G07 runs source baseline nodes and freezes evidence.
- [UPDATE] `backend/app/services/angular_transformation_evidence_service.py:29-96` — generalize exact source proof across present governed cohort using `DependencyIntent`, selected lock authority/canonical resolved reader, installed metadata, `npm ls`, and local CLI evidence.
- [UPDATE] `backend/app/services/baseline_aware_validation_service.py:55-249` — expose diagnostic normalization for later delta while preserving lint behavior until P07.
- [UPDATE] `backend/tests/test_lockfile_compatibility_f08.py`, `backend/tests/test_baseline_domain_s1_f10.py`, `backend/tests/test_command_registry_service.py`, `backend/tests/test_planning_application_service_s2_f06_i01.py`, `backend/tests/test_angular_transformation_evidence.py`, `backend/tests/test_baseline_aware_validation_service.py`, and `backend/tests/test_transformer_stage_reconstruction.py` — V1/V2/V3 reader, source command registration, plan ordering, proof, diagnostics, and generation reconstruction.

### New files to ADD

NONE. Source evidence is a typed artifact in `domain/transformation.py` and existing artifact storage.

### Files explicitly NOT to touch

Lock runner, package migration, repair, promotion, sealing, frontend, DB schema.

### Data/contracts

Add section 9 authority-policy/reader/error/root-sync contracts and immutable `DependencyIntent`/`DependencyIntentKind`. Extend `PackageMetadata` to preserve all five package.json sections, including `peerDependenciesMeta`, and prohibit flattening before proven root-sync. Extend `LockfileResult` with exact npm/policy checksum, selected filename/kind, raw SHA/version, canonical dependency-set checksum, per-package section/kind/absence-aware root-sync classification, and findings. `SourceBaselineEvidence` binds those fields plus `DependencyIntent` checksum, input sealed checkpoint/fingerprint, manifest intent checksum, runtime identity/checksum, npm-ci/npm-ls selected-authority proof, install/tree/version/build/test/lint execution IDs and artifact checksums, exact cohort, normalized diagnostics, baseline fingerprint, and status/checksum.

### Workflow transitions

Proven G07 → `create_source_baseline → construct_dependency_intent → select_source_lock_authority → canonical_resolved_lock_read → prove_section_aware_manifest_intent_vs_resolution → source_install_same_authority → source_tree → source_version_proof → source_build → source_test → source_diagnostic_capture → freeze_source_baseline → create_discovery_generation`. Unsupported/malformed selected authority blocks before npm mutation; an invalid shrinkwrap never falls through to package-lock.

### Command templates

Reuse install/build/test. Add `npm-dependency-tree` exactly as section 7. No process runs against the sealed input itself.

### Failure/recovery behavior

Command failure routes by owner once P09 exists; until then it blocks with phase-specific evidence. Restart reconstructs the source baseline, `DependencyIntent`, npm capability policy, and selected authority from the sealed checkpoint and reuses terminal command evidence by idempotency key. Dirty/live mismatch or a changed npm policy is never accepted.

### Implementation steps

1. Add failing selector tests for package-lock only, shrinkwrap only, both, neither, and malformed shrinkwrap with valid package-lock present.
2. Add failing resolved-state tests for V1, V2, V3, malformed/unsupported locks, manifest semantic mismatch, top-level resolution, nested `requires`/dependency lookup, and `STATIC_CHECK`/`VERIFIED`/`MISMATCH`/`DEFER_TO_NPM` outcomes.
3. Preserve package.json dependency section ownership, implement immutable `DependencyIntent`/`DependencyIntentKind`, npm-version-aware `LockfileAuthorityPolicy`/`LockfileAuthority`, and `PackageLockReader` in the existing lockfile compatibility domain, and make baseline prequalification delegate section-aware root sync to them while keeping package.json as root intent authority.
4. Add command renderer/registry tests for exact npm-ls argv.
5. Add SourceBaselineEvidence contract and checksum binding.
6. Add generation path/copy/checkpoint helpers using `StageSandboxCopier`.
7. Add proven graph nodes and explicit command group queueing.
8. Extend exact cohort proof through the selected authority/reader without hard-coded package/schema branches.
9. Persist normalized baseline diagnostics and freeze checkpoint.
10. Add restart tests after authority selection, lock read, copy, command queue, terminal command, and pre-freeze.

### Tests to ADD/UPDATE

- Unit: npm-ls renderer rejects extra arguments.
- Unit: package-lock only selects PACKAGE_LOCK; shrinkwrap only and both select SHRINKWRAP; neither is missing; malformed authoritative shrinkwrap does not fall through.
- Unit: V1 manifest request `^1.0.0` with top-level resolution `1.2.3` is compatible; absent required dependency and exact `1.2.3` resolved as `1.2.4` are explicit mismatches.
- Unit: `DependencyIntent` preserves dependencies/devDependencies/optionalDependencies/peerDependencies/peerDependenciesMeta and classifies `peerDependenciesMeta[package].optional == true` as `OPTIONAL_PEER`; no caller uses a flattened map for semantic authority.
- Unit: required dependency missing and dev dependency missing in governed normal install mode are `MISMATCH`; optional dependency absent with valid npm/platform evidence is allowed; optional present but incompatible is `MISMATCH`.
- Unit: npm 3–6 peer absence is not automatically `MISMATCH`; present compatible peer is `VERIFIED`; npm 7+ peer behavior defers to bound npm; optional peer absence is allowed; optional peer incompatibility is `MISMATCH`; complex peer specs are `DEFER_TO_NPM`.
- Unit: V1 nested `requires`/dependency edges, V2/V3 equivalent resolved-state behavior, integrity lookup, malformed JSON/shape, unsupported version, and root manifest mismatch.
- Unit: exact and allowlisted simple registry specs (including the proven simple-caret `^0.2.3` case) produce deterministic `VERIFIED`/`MISMATCH`; tilde/compound-comparator/x/star/OR/alias/file/git/workspace and other unsupported specs produce `DEFER_TO_NPM` without Python guessing, and deferred specs require governed npm solve/clean-ci evidence.
- Unit: bound npm 6–11 selects shrinkwrap before package-lock; bound npm 12+ selects package-lock only under explicit unsupported-shrinkwrap policy, and shrinkwrap-only npm 12+ blocks without migration/removal policy.
- Unit: no caller can obtain or infer original root requested ranges from a V1 lock; new `LockfileDependencySet` writers expose exact `top_level_resolved` only.
- Unit: no consumer requires `packages[""]` for V1.
- Unit: root-sync findings preserve package, section/kind, requested spec, resolved version, policy checksum, absence semantics, reason code, and deferred evidence; source proof rejects manifest/lock/installed/tree mismatch.
- Integration: extend `test_transformer_bootstrap_vertical.py` for clean source generation and restart.
- Integration: `test_transformer_stage_reconstruction.py` proves no volatile inheritance.
- [ADD] `backend/tests/test_proven_transformer_runtime.py` is deferred to P14; its runtime matrix covers this source-baseline scenario, so P03 adds no file.
- Baseline expected: existing bootstrap/runtime tests include P00 failures.
- New expected: new baseline-focused nodes pass.
- Regression rule: no previously passing copier/checkpoint/runtime test regresses.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_lockfile_compatibility_f08.py tests/test_baseline_domain_s1_f10.py tests/test_command_registry_service.py tests/test_transformer_bootstrap_vertical.py tests/test_transformer_stage_reconstruction.py tests/test_angular_transformation_evidence.py tests/test_validation_runner.py
.\.venv\Scripts\python.exe -m ruff check app/domain/command.py app/domain/lockfile_compatibility.py app/domain/baseline.py app/domain/transformation.py app/services/transformer_stage_service.py app/orchestration/transformer_graph.py app/services/angular_transformation_evidence_service.py
Pop-Location
```

### Runtime validation

Fixture: sealed Angular 11/npm6 V1 source for 11→12 first, plus V2/V3, shrinkwrap-only, and both-lock fixtures. Runtime expected: mode-authorized profile, never fixed host path. Observable evidence: package.json intent checksum, exact npm/policy checksum, selected filename/kind, raw/schema/checksummed canonical resolved-state read, npm-ci same-authority proof, node/npm/npx identity, clean copy exclusions, npm-ls JSON, exact source cohort, build/test outputs, diagnostic artifact, frozen fingerprint. Pass when bound-npm authority selection is exact, all lock versions produce the canonical contract, and intent/resolution bind to one SourceBaselineEvidence checksum. Inspect authority policy/selection, then reader/root-sync evidence.

### Acceptance criteria

- [ ] Every proven stage starts from the previous sealed generation.
- [ ] Runtime resolves before baseline commands.
- [ ] Source baseline is a fresh contained copy.
- [ ] `node_modules`, `dist`, `.angular`, and `.git` are not inherited.
- [ ] `npm ci`, `npm ls`, exact source, build, and tests are all proven.
- [ ] Angular 11/npm6 lockfileVersion 1 and V2/V3 are supported through one reader.
- [ ] package.json is parsed into a section-preserving `DependencyIntent`; no proven caller flattens dependency sections before root-sync.
- [ ] `dependencies` and governed `devDependencies` require valid materialization; optional omission and peer absence follow bound npm/platform semantics.
- [ ] package.json, never V1 lock data, owns original root requested ranges.
- [ ] Lock authority follows the bound npm policy: npm 6–11 select shrinkwrap before package-lock; npm 12+ treats shrinkwrap as unsupported and requires explicit policy while selecting package-lock.
- [ ] Malformed or unsupported selected authority cannot fall through to another file.
- [ ] Root-sync uses section-aware `STATIC_CHECK` → `VERIFIED`/`MISMATCH` or `DEFER_TO_NPM`; Python never guesses unsupported npm specs or peer/optional behavior.
- [ ] Factory selection and source `npm ci` evidence bind the same filename/kind/checksum.
- [ ] Malformed/unsupported locks fail explicitly before source mutation.
- [ ] No Transformer source proof assumes `packages[""]` exists.
- [ ] Baseline diagnostics and fingerprint are immutable.

### Completion evidence

SourceBaselineEvidence artifact, source checkpoint, command logs/results, focused tests, and runtime proof/blocker.

### Rollback/recovery notes

Source baseline is disposable. Delete/quarantine an incomplete generation and reconstruct from sealed input; never mutate the sealed checkpoint.

### Agent handoff

P04 may rely on an immutable source-baseline checkpoint and complete source evidence.

## Phase P04 — P0-3 Evidence-bound CLI authority, disposable discovery, and TargetIntent

### Objective

Bind the actual Angular CLI, Node/npm/npx, PATH, environment, source generation, and target stage before making Angular update a disposable target-intent probe whose process result is independent from deterministic discovery completeness.

### Why

`npx --package` does not prove which CLI executable owns execution because local binaries share PATH, and child npm may drift unless PATH is fully governed. Combined updater failures can also partially mutate manifests/source, while nonzero probes can still produce complete target intent.

### Preconditions

P03 source baseline frozen; a versioned evidence-backed discovery strategy and mode-authorized runtime are available from the plan/Stage Knowledge.

### Existing code to REUSE unchanged

- [REUSE] command worker/policy/runtime binding/artifact capture.
- [REUSE] `backend/app/domain/runtime_execution.py:21-109` — exact absolute `RuntimeExecutableDescriptor` identity/checksum.
- [REUSE] `backend/app/services/runtime_resolver_authority.py:53-215` — paired Node/npm/npx discovery and checksum authority.
- [REUSE] `StageSandboxCopier`, checkpoint/reconstruction, prompt evidence and human prompt policy.
- [REUSE] exact target cohort from frozen stage plan.

### Existing code to UPDATE

- [UPDATE] `backend/app/domain/command.py:136-190,317-475,598-712` — add authority-bound `angular-cli-authority-version` and `angular-update-discovery`; permit a validated authority-resolved executable/absolute first argv; mark npx V2–V6 [DEPRECATE]/[REMOVE-LATER] for legacy only.
- [UPDATE] `backend/app/domain/transformation.py` — add `AngularCliToolchainAuthority`, `DiscoveryResult`, and `TargetIntent` contracts from sections 7/8.
- [UPDATE] `backend/app/services/stage_execution_application_service.py:398-441` — validate frozen discovery authority checksum, absolute entrypoint containment/integrity, exact package list, and command binding.
- [UPDATE] `backend/app/services/command_executor_service.py:281-360,1366-1424` — build the exact governed PATH/environment, reject ambient-path drift, and prove child-visible npm resolves to the bound descriptor before execution.
- [UPDATE] `backend/app/services/transformer_stage_service.py:466-650,718-1493` — queue discovery against a disposable alias/checkpoint only.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:451-957` — replace proven `_angular_update` with create/run/assess/persist/discard nodes; retain legacy method.
- [UPDATE] `backend/app/services/stage_knowledge_service.py:37-88` — select versioned discovery strategies by observed capabilities, not Angular-major branches.
- [UPDATE] `backend/tests/test_ng_update_governance_f14.py`, `backend/tests/test_command_registry_service.py`, `backend/tests/test_planning_transformation_boundary.py`, and `backend/tests/test_target_inspection_generation.py` — discovery-only scope, renderer policy, legacy/proven planning split, and disposable generation.

### New files to ADD

NONE.

### Files explicitly NOT to touch

Active target binding promotion, lock runner, migrations, repair LLM, sealing, DB schema, frontend.

### Data/contracts

`AngularCliToolchainAuthority` is section 7. `DiscoveryResult` records its checksum and CLI-version proof plus execution ID, exit/status, pre/post manifest/lock/workspace checksums, completeness boolean/findings, strategy ID/version, prompt evidence, and artifact checksum. `TargetIntent` is section 8. Completeness parser accepts dependency sections only and rejects ambiguous/unapproved root mutations.

### Workflow transitions

Frozen source → create disposable → select a versioned strategy → prepare/locate CLI toolchain → resolve absolute CLI entrypoint/package integrity → construct governed PATH/environment → prove preflight CLI and child npm authority → run discovery → assess execution-coupled actual CLI/no-delegation evidence. Preflight mismatch blocks before the command; unexpected execution-time mismatch discards the disposable result and blocks before TargetIntent. Complete true continues regardless of zero/nonzero exit with evidence; incomplete selects the next governed strategy within budget or classifies failure. TargetIntent then creates the next authoritative generation; disposable workspace is discarded/quarantined.

### Command templates

Authority-version and discovery argv are exactly section 7. Normal proven discovery invokes the checksummed absolute CLI package entrypoint through the bound absolute Node executable (or an authority-proven equivalent absolute shim), never bare `ng` or generic npx resolution. An evidence-backed source-local strategy, a prepared isolated toolchain, or another evidence-backed strategy may be selected by Stage Knowledge/capabilities. `NG_DISABLE_VERSION_CHECK` is present only when that strategy version authorizes it. No force/legacy/allow-dirty. Historical updater templates remain executable only for persisted legacy plans.

### Failure/recovery behavior

Partial probe state is never authority. Restart re-resolves every toolchain path/checksum, governed PATH, child npm, source fingerprint, and stage binding before consuming terminal evidence; any mismatch invalidates the disposable attempt and blocks/reconstructs under the same strategy budget. Parser failure is HARNESS; CLI/Node/npm/PATH identity mismatch is RUNTIME/TOOLCHAIN authority failure; missing/incomplete intent is discovery failure; nonzero process with complete intent is a warning, not automatic failure.

### Implementation steps

1. Add failing tests proving npx package selection is not CLI authority and requested/actual mismatch blocks.
2. Add `AngularCliToolchainAuthority`, DiscoveryResult, and TargetIntent models/checksums.
3. Resolve source-local/prepared toolchain absolute CLI package entrypoint and integrity without a major branch.
4. Build/checksum an exact allowlisted environment and governed PATH; prove child npm resolution equals the bound descriptor.
5. Run the authority-version command and capture strategy-specific execution-coupled no-delegation/package-root proof; require requested=installed=actual CLI before accepting discovery output.
6. Add renderer/plan-membership tests and disposable generation binding.
7. Implement deterministic manifest intent parser/completeness rules.
8. Split graph process result from semantic assessment.
9. Persist authority/evidence before discarding/quarantining the probe.
10. Prove authoritative binding was never the discovery path and preserve legacy dispatch.

### Tests to ADD/UPDATE

- Unit: zero+complete, nonzero+complete, zero+incomplete, nonzero+incomplete.
- Unit: requested CLI differs from installed/actual/checksummed entrypoint; block before updater.
- Unit: absolute preflight CLI matches but update-time delegation is unproven; reject TargetIntent.
- Unit: governed PATH resolves npm/npx outside the bound install; block child package-manager authority.
- Unit: `NG_DISABLE_VERSION_CHECK` rejected unless the strategy version explicitly authorizes it.
- Unit: reject source/lock changes as TargetIntent authority.
- Integration: prompt/restart and partially mutated discovery never update active binding.
- Update `test_ng_update_governance_f14.py`, `test_command_registry_service.py`, `test_target_inspection_generation.py`, `test_command_terminal_lifecycle.py`.
- Baseline expected: legacy command/governance tests have P00 failures.
- New expected: proven discovery cases pass and legacy readers remain.
- Regression rule: no new plan references `angular-update-exact`.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_ng_update_governance_f14.py tests/test_command_registry_service.py tests/test_target_inspection_generation.py tests/test_transformer_prompt_service.py tests/test_command_terminal_lifecycle.py
.\.venv\Scripts\python.exe -m ruff check app/domain/command.py app/domain/transformation.py app/services/stage_execution_application_service.py app/services/command_executor_service.py app/services/transformer_stage_service.py app/orchestration/transformer_graph.py app/services/stage_knowledge_service.py
Pop-Location
```

### Runtime validation

Fixture: source baseline plus (a) source-local CLI strategy, (b) prepared isolated CLI strategy where available, and (c) deliberate local/npx ownership conflict. Runtime expected: mode-authorized bridge. Evidence: full toolchain authority, absolute CLI entrypoint/integrity, actual CLI version, governed PATH/environment checksum, child npm identity, disposable path, updater argv/runtime, stdout/stderr/exit, pre/post checksums, completeness findings, TargetIntent, active binding before/after. Pass only when requested CLI equals actual authority and discovery mutations never reach authority. Inspect toolchain authority before discovery output.

### Acceptance criteria

- [ ] New plans never execute combined update authoritatively.
- [ ] Discovery never assumes npx package selection proves CLI ownership.
- [ ] Requested, installed, and actual executing Angular CLI exact version are evidence-equal.
- [ ] Standalone version output cannot substitute for execution-coupled no-delegation/package-root proof.
- [ ] Absolute CLI entrypoint/package integrity and governed Node/npm/npx identities are checksum-bound.
- [ ] Child npm resolution and exact PATH/environment are governed.
- [ ] Preflight CLI/PATH/child-npm mismatch blocks before the command; execution-time CLI/delegation mismatch discards the probe and blocks before TargetIntent/authority mutation.
- [ ] Every discovery updater runs in a disposable generation.
- [ ] Exit status and completeness are separate.
- [ ] Nonzero+complete may continue only with deterministic evidence.
- [ ] Incomplete discovery cannot alter authority.
- [ ] TargetIntent contains dependency intent only and is source-bound.
- [ ] No force/legacy-peer flags exist.

### Completion evidence

DiscoveryResult, TargetIntent, disposable generation/checkpoint evidence, focused tests, runtime output.

### Rollback/recovery notes

Disable proven-plan readiness and discard disposable generations. Legacy plans continue unchanged.

### Agent handoff

P05 may rely on a checksum-bound TargetIntent and independently proven discovery toolchain authority; neither grants migration CLI authority.

## Phase P05 — P0-4 Generic LockResolution

### Objective

Implement preserve-first, classified one-time fresh fallback, bounded convergence, clean npm-ci proof, and dependency-tree proof as the normal proven path.

### Why

Current lock runner is repair-authority-bound, does not converge on two hashes, and treats structural package-lock success without clean reproducibility proof.

### Preconditions

P04 TargetIntent complete; clean authoritative target generation can be reconstructed from frozen source.

### Existing code to REUSE unchanged

- [REUSE] existing `npm-lockfile-generate` template and command worker.
- [REUSE] governed fingerprint scope, artifact registration, reconstruction, and classified package-lock deletion guard; lock selection/root-sync semantics are replaced by P03 authority/reader contracts.
- [REUSE] `StageStepModel`, lock evidence rows, immutable artifacts.

### Existing code to UPDATE

- [UPDATE] `backend/app/services/lockfile_generation_runner.py:1-1347` — implement section 9 state machine over the npm-version-selected authority; consume section-aware `DependencyIntent` and `LockfileRootSyncResult`; require deferred npm-spec/peer/optional classifications to be proven by governed solver/clean `npm ci`/`npm ls`; remove normal-path `RepairAttemptModel` requirement; retain legacy repair adapter; forbid shrinkwrap deletion/replacement without explicit dependency-policy authority. Callers: graph, recovery, repair transition.
- [UPDATE] `backend/app/services/dependency_closure_service.py:253-826` — replace V3 `packages[""]` assumptions with `PackageLockReader` top-level-resolved/nested-edge APIs and package.json intent.
- [UPDATE] `backend/app/services/dependency_repair_preflight_service.py:149-203` and `backend/app/services/dependency_failure_bundle_service.py:81-261` — replace local resolved-version extraction with the canonical reader.
- [UPDATE] `backend/app/services/transformer_stage_service.py:650-715,1494-1580` — queue attempt-keyed solve/install/tree commands against exact generation.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:4755-4895` — make lock normal-path/reconcile node and route semantic outcomes.
- [UPDATE] `backend/app/services/failure_evidence_service.py:635-1002` — include lock cycle/mode/attempt/phase evidence.
- [UPDATE] `backend/app/services/failure_intelligence_service.py:225-332` — recognize eligible inherited-lock failures separately from dependency/runtime/harness.
- [UPDATE] `backend/tests/test_lockfile_generation_runner.py`, `backend/tests/test_dependency_transition_evidence_mode.py`, `backend/tests/test_failure_evidence_service.py`, `backend/tests/test_failure_intelligence_f19.py`, and `backend/tests/test_command_recovery.py` — solver state, dependency evidence, classification, and restart.

### New files to ADD

NONE. `LockResolutionLedger` is a typed artifact in existing transformation contracts.

### Files explicitly NOT to touch

npm/Arborist internals, package-specific rules, repair LLM, candidate promotion, frontend, SQL schema.

### Data/contracts

Add LockResolutionMode/Status, `LockSchemaTransitionEvidence`, shrinkwrap replacement-policy reference, and `LockResolutionLedger`/attempt contracts. Freeze `max_attempts=5` in proven plan policy; it is configurable per policy, not major. Attempt identity includes stage, cycle, exact npm descriptor/policy checksum, selected authority kind, and ordinal. Every attempt binds `DependencyIntent` checksum, npm capability fields, filename/kind, reader version/dependency-set checksum, per-section/per-kind root-sync classifications (including absence semantics and deferred npm evidence), and raw lock checksum.

### Workflow transitions

Apply TargetIntent → construct/verify section-aware `DependencyIntent` → dependency plan → lock cycle. Converged → clean materialization → npm-ci → npm-ls → section-aware proof. Eligible preserve failure → one fresh cycle. Missing optional/optional-peer or npm6 peer resolution alone never authorizes fresh fallback. Other failure → owner route. Post-migration authority change starts a new cycle.

### Command templates

Reuse package-lock-only exact argv. Reuse npm-ci-final for materialization and npm-dependency-tree from P03. No force/legacy-peer flags.

### Failure/recovery behavior

Every attempt is immutable/idempotent. Restart re-selects authority and consumes terminal evidence only when filename/kind/checksum, `DependencyIntent` checksum, and npm capability policy match. Missing evidence blocks rather than reruns ambiguously. PACKAGE_LOCK fresh fallback reconstructs from TargetIntent and deletes only package-lock. Missing `REQUIRED`/required `DEV` resolution may fail the lock/dependency phase; missing `OPTIONAL`, `OPTIONAL_PEER`, or npm6 peer resolution alone cannot authorize fresh-lock deletion. SHRINKWRAP remains authority and blocks until an explicit replacement/removal policy decision is present. HARNESS reconstruction creates another clean materialization generation; it does not authorize fresh lock.

### Implementation steps

1. Write pure state-transition tests before runner changes.
2. Add ledger contracts and canonical checksum.
3. Replace runner/closure/preflight/failure-bundle filename selection and raw parsing with P03 `LockfileAuthority` + `PackageLockReader`.
4. Split normal authority from legacy repair adapter.
5. Implement preserve attempt and semantic verification.
6. Record governed V1→V2/V3 transitions without rewriting the solver's schema.
7. Implement consecutive-hash convergence and budget exhaustion.
8. Implement classified one-time PACKAGE_LOCK fallback and policy-gated SHRINKWRAP replacement/removal.
9. Add clean materialization, Factory/npm-ci selected-authority equality, checksum invariance, and npm-ls proof.
10. Add section-aware missing/optional/peer routing tests and restart tests at every authority-selection/queue/terminal/hash/schema-transition/fallback/materialization boundary.

### Tests to ADD/UPDATE

- Unit: convergence sequences `A,A`, `A,B,B`, exhaustion, restart replay.
- Unit: only eligible inherited-lock classification authorizes fresh fallback; shrinkwrap additionally requires an explicit checksum-bound dependency-policy decision.
- Unit: exit zero but npm-ci rejection fails LOCKFILE.
- Unit: duplicate transitives accepted; npm invalid/missing/extraneous rejected.
- Unit: V1/V2/V3 produce equivalent intent-versus-resolved evidence; governed V1→later transition is recorded; malformed/unsupported selected authority fails explicitly.
- Unit: static safe specs produce `VERIFIED`/`MISMATCH`, complex specs produce `DEFER_TO_NPM`, and deferred specs pass only with governed solver/clean-ci evidence; npm rejection remains a dependency/lock failure.
- Unit: required/dev missing can fail; optional missing with valid npm/platform evidence is allowed; optional present incompatible is `MISMATCH`; optional-peer missing is allowed; npm6 peer absence does not authorize deletion; npm7+ peer solver failure routes `DEPENDENCY`.
- Unit: bound npm 6–11 selects shrinkwrap when both files exist; bound npm 12+ uses package-lock only with explicit unsupported-shrinkwrap policy; malformed selected authority cannot fall through; package-lock fallback cannot delete shrinkwrap.
- Integration: update `test_lockfile_generation_runner.py`, `test_lockfile_compatibility_f08.py`, `test_transformer_repair_failure_governance.py`, `test_transformation_replan_recovery.py`, and `test_command_recovery.py` coverage.
- Baseline expected: lock evidence and shared runtime-correlation tests contain P00 failures.
- New expected: new lock state tests pass and legacy adapter expectations are updated explicitly.
- Regression rule: no direct selected-lock edit outside the runner; package-lock removal requires classified fallback and shrinkwrap removal/replacement additionally requires explicit policy authority.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_lockfile_generation_runner.py tests/test_lockfile_compatibility_f08.py tests/test_baseline_domain_s1_f10.py tests/test_dependency_closure_service.py tests/test_failure_evidence_service.py tests/test_failure_intelligence_f19.py tests/test_transformer_repair_failure_governance.py
.\.venv\Scripts\python.exe -m ruff check app/domain/lockfile_compatibility.py app/services/lockfile_generation_runner.py app/services/dependency_closure_service.py app/services/dependency_repair_preflight_service.py app/services/dependency_failure_bundle_service.py app/services/failure_evidence_service.py app/services/failure_intelligence_service.py app/orchestration/transformer_graph.py
Pop-Location
```

### Runtime validation

Fixture: TargetIntent plus section-aware `DependencyIntent`, Angular 11/npm6 V1 inherited lock and V2/V3 locks; include package-lock-only, shrinkwrap-only, both, malformed authoritative shrinkwrap, controlled stale-lock, and valid-multiple-transitive variants. Runtime: mode-authorized stage npm. Evidence: exact npm/policy checksum, selected filename/kind, manifest/intent section/kind/absence-aware root-sync proof, canonical input/output versions, V1→later transition where produced, dependency-set checksums, every solve argv/runtime/exit/SHA, classification/policy, fallback count, converged SHA, and same-authority clean npm-ci/npm-ls artifacts. Pass only with bound-npm selection, supported canonical reads, correct optional/peer handling, two consecutive SHAs, and valid clean tree. Inspect selector/policy/intent/root-sync/schema-transition evidence before solver logs.

### Acceptance criteria

- [ ] Preserve mode is always first.
- [ ] Fresh fallback is classified, selected-authority scoped, and at most once.
- [ ] PACKAGE_LOCK fallback affects only `package-lock.json`; SHRINKWRAP deletion/replacement requires explicit dependency-policy authority.
- [ ] Convergence requires two consecutive identical SHAs.
- [ ] Attempts are finite and restart-idempotent.
- [ ] Exit-zero lock generation is insufficient.
- [ ] Converged package.json/selected-lock authority passes clean same-authority npm-ci and npm-ls.
- [ ] Multiple valid transitive versions are accepted.
- [ ] LockResolution reads V1/V2/V3 only through `PackageLockReader` and records schema transitions.
- [ ] LockResolution and npm-ci bind the same npm-policy-selected `LockfileAuthority`; shrinkwrap wins when both files exist only for npm 6–11.
- [ ] Deferred npm specs are never guessed by Python and require governed npm solve/clean-ci semantic evidence.
- [ ] LockResolution consumes section-aware `DependencyIntent`; required/dev missing can fail, optional/optional-peer absence cannot authorize fresh fallback, and npm6 peer absence cannot authorize deletion.
- [ ] Peer conflicts produced by npm route to `DEPENDENCY`; the Factory never implements a peer solver.
- [ ] Unsupported/malformed lock shapes fail explicitly; no `packages[""]` assumption remains.

### Completion evidence

LockResolutionLedger with selected-authority/root-sync/fallback-policy evidence, same-authority materialization proof, focused tests, and stale/valid runtime scenarios.

### Rollback/recovery notes

Disable proven-plan readiness. Reconstruct target generation from frozen source+TargetIntent; no sealed/active generation is changed.

### Agent handoff

P06 may rely on a reproducible target lock, clean installed tree, and exact materialization generation.

## Phase P06 — P0-5 Exact target materialization and MigrationLedger (P06-A/P06-B)

### Objective

Prove the exact installed target cohort through section-aware `DependencyIntent` plus selected lock authority/canonical resolved reader, discover installed migration owners dynamically, bind the exact materialized target CLI authority, and execute required migrate-only work on the normal path.

### Why

Current evidence is Core/CLI-centric and current migration planning is Core-only despite a partially dynamic service.

### Preconditions

P05 materialization status PROVED with clean npm tree.

### P06-A — Required P0 installed migration-owner discovery

Implement the minimum complete owner ledger before any migration command is queued: compare changed direct intent from source/target `package.json`, use the npm-policy-selected source/target lock authorities and `PackageLockReader` for resolved evidence, inspect every installed changed direct package for valid `ng-update.migrations`, and emit deterministic required-owner entries. This phase owns removal of the Core/CLI priority special case; no package name is privileged.

### P06-B — Required P1 migration metadata traversal

Complete the ledger in the same P06 phase before handing off to P07 or starting P14. Traverse supported `packageGroup` and `requirements` metadata, parse applicable collections in `(from, to]`, discover individually named optional migrations, and apply explicit ordering/dependency rules. Each entry is `RUN`, `SKIP`, or `PENDING HUMAN`; unresolved requirements, ambiguous ownership, unsupported metadata, or pending human decisions block rather than silently omitting work. P06-B is the implementation owner for this P1 scope; P14 is qualification and must not be used to finish it.

### Existing code to REUSE unchanged

- [REUSE] legacy npx-based `angular-migrate-range-v1` only for historical replay; its migrate-only semantics and binding validation inform v2.
- [REUSE] installed exact-version reader in `PackageMigrationService`; raw lock lookup is replaced below.
- [REUSE] target version and transformation evidence artifact infrastructure.

### Existing code to UPDATE

- [UPDATE] `backend/app/services/package_migration_service.py:1-289` — implement P06-A and P06-B: remove Core/CLI priority set and `_resolve_from_lock`; select source/target npm-policy `LockfileAuthority`, use package.json for changed direct intent and `PackageLockReader` for exact resolved/nested evidence; discover all changed direct installed owners with valid `ng-update.migrations`; traverse packageGroup/requirements and named optional metadata with deterministic ordering; build immutable ledger.
- [UPDATE] `backend/app/domain/command.py:212-235,438-475` — retain npx migrate-range v1 for legacy; add authority-bound v2 range and exact named renderer for proven optional RUN.
- [UPDATE] `backend/app/services/stage_execution_application_service.py:398-441` — bind range/name commands from frozen ledger and MIGRATION-purpose toolchain authority only.
- [UPDATE] `backend/app/services/command_executor_service.py:281-360,1366-1424` — enforce absolute target CLI containment/checksum, actual CLI proof, governed PATH, and child npm identity for each migrate-only execution.
- [UPDATE] `backend/app/services/angular_transformation_evidence_service.py:29-326` — prove all present governed cohort packages from manifest/lock/installed/tree/local CLI; attribute changes per migration execution.
- [UPDATE] `backend/app/services/stage_target_version_service.py:26-98` — require the same full target proof at boundaries.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:4927-5185` — execute ledger on normal path, loop owners, route failures, compare authority, reconcile conditionally.
- [UPDATE] `backend/tests/test_installed_migration_fallback.py`, `backend/tests/test_angular_transformation_evidence.py`, `backend/tests/test_target_inspection_generation.py`, `backend/tests/test_command_registry_service.py`, and `backend/tests/test_ng_update_governance_f14.py` — P06-A/P06-B installed metadata, packageGroup/requirements traversal, ordering/dependencies, optional decisions, ledger, exact proof, named renderer, and migrate-only governance.

### New files to ADD

NONE.

### Files explicitly NOT to touch

Installed migration CJS helper except deprecation comments, npm solver, repair LLM, promotion/seal, DB schema.

### Data/contracts

Add `MigrationLedger`, `MigrationOwner`, packageGroup/requirements dependency edges, ordering trace, and optional decision contracts as section 11. The ledger binds source/target section-aware `DependencyIntent` checksums (including `peerDependenciesMeta`), npm-policy-selected lock filenames/kinds/raw/version/canonical checksums, section/kind/absence-aware root-sync results, and the MIGRATION `AngularCliToolchainAuthority` checksum. P06-A owns changed direct package discovery with installed collections; P06-B owns packageGroup/requirements traversal, named optional entries, ordering, and dependency decisions without changing schema version readers.

### Workflow transitions

Target proof → P06-A owner discovery → P06-B packageGroup/requirements traversal and ordering → ledger → resolve `<target-generation>/node_modules/@angular/cli` package/bin metadata → bind absolute CLI entrypoint/shim → prove actual target CLI and child npm → G08 → owner loop → authority compare. Any CLI authority mismatch blocks before migration. Unchanged → freeze target. Changed → new LockResolution cycle then rematerialize/reprove and rebind toolchain authority before continuing.

### Command templates

Required owner: proven migrate-range v2 exact argv from section 7, using absolute installed target CLI authority. Optional named RUN: authority-bound migrate-name argv. The preferred portable invocation is governed absolute Node + absolute installed `@angular/cli/bin/ng.js`; an absolute `<target>/node_modules/.bin/ng(.cmd)` shim is allowed only after its target/checksum is proven equal. Bare `ng` and generic npx resolution are prohibited. PENDING waits on existing human gate; SKIP records decision and executes nothing.

### Failure/recovery behavior

Ledger/toolchain authority are frozen before G08 and command queueing. Restart revalidates target generation, CLI entrypoint/package integrity, actual version, runtime descriptors, governed PATH/child npm, and authority checksum before selecting the first nonterminal entry. Drift invalidates the migration attempt and rematerializes/rebinds; it never falls back to npx. Metadata/lock parser failure is HARNESS. Owner command failure enters owner routing. Unknown optional status blocks; nothing is silently run.

### Implementation steps

1. Implement P06-A installed owner discovery and add metadata-owner/V1-source/V2/V3-target selected-authority/resolved lookup tests without Angular package assumptions.
2. Implement P06-B packageGroup/requirements traversal, named optional migration metadata, deterministic ordering, and requirement/dependency decisions.
3. Add ledger contracts/checksum/order and toolchain-authority binding for both subphases.
4. Remove priority package set, local raw lock parser, and plan-time Core binding.
5. Resolve/prove the exact installed target CLI absolute entrypoint, package integrity, actual version, PATH, and child npm.
6. Generalize full target proof through `PackageLockReader`.
7. Add G08-bound normal migration loop using authority-bound renderers.
8. Add package.json/selected-lock before/after comparison and conditional lock cycle/rebinding.
9. Deprecate npx/CJS helpers for new plans while preserving replay.

### Tests to ADD/UPDATE

- Unit: arbitrary installed package with/without migrations; exact mismatch fails.
- Unit: changed direct intent comes from source/target manifests; V1 source and V2/V3 target exact resolved versions come from their selected authorities/readers, including nested lookup.
- Unit: target CLI package/entrypoint/version/checksum or child npm mismatch blocks before migrate-only.
- Unit: no Core-only behavior; changed direct owner ledger ordering stable.
- Unit: P06-A discovers every changed direct installed owner and P06-B traverses packageGroup/requirements, enforces ordering/dependency edges, records named optional entries, and blocks unresolved or PENDING decisions.
- Integration: migration executes from exact target CLI and resumes by ledger entry.
- Integration: unchanged authority skips lock; changed authority re-enters it.
- Update `test_installed_migration_fallback.py`, `test_angular_transformation_evidence.py`, `test_stage_sealing.py`.
- Baseline expected: evidence/repair-governance tests include P00 failures.
- New expected: migration-ledger scenarios pass.
- Regression rule: historical installed fallback remains readable but no proven plan selects it.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_installed_migration_fallback.py tests/test_lockfile_compatibility_f08.py tests/test_angular_transformation_evidence.py tests/test_command_registry_service.py tests/test_command_executor_services.py tests/test_stage_sealing.py tests/test_stage_execution_application_service.py tests/test_transformer_repair_failure_governance.py
.\.venv\Scripts\python.exe -m ruff check app/domain/command.py app/domain/lockfile_compatibility.py app/services/package_migration_service.py app/services/stage_execution_application_service.py app/services/command_executor_service.py app/services/angular_transformation_evidence_service.py app/services/stage_target_version_service.py app/orchestration/transformer_graph.py
Pop-Location
```

### Runtime validation

Fixture: clean target materialization containing at least one installed changed owner with migration metadata and a V1 source case. Runtime: mode-authorized target runtime. Evidence: source/target section-aware `DependencyIntent`, selected lock filename/kind and canonical resolved reads, section/kind/absence-aware root-sync proofs, full cohort proof, installed metadata/collection checksums, exact absolute target CLI/package/version/integrity, governed PATH/child npm, ledger checksum, migrate-only argv/result, pre/post authority comparison, optional decisions. Pass when required owners execute through the exact materialized target CLI and conditional reconcile/rebinding is correct. Inspect lock/toolchain authorities, then ledger/command evidence.

### Acceptance criteria

- [ ] Exact target proof covers every present governed cohort member.
- [ ] P06-A completes basic installed migration-owner discovery for every changed direct package.
- [ ] P06-B completes packageGroup/requirements traversal, optional metadata, ordering, and dependency rules before P07 handoff or P14 qualification.
- [ ] No supported packageGroup/requirements migration is silently omitted.
- [ ] Migration owner/version comparison uses package.json for direct intent and the npm-selected lock authority for resolved versions.
- [ ] Owners come from installed metadata, not a Core-only list.
- [ ] Required owners use exact target-workspace migrate-only.
- [ ] Migration CLI authority is the checksummed absolute CLI installed in the exact materialized target generation.
- [ ] Generic npx/local PATH resolution cannot own proven migrate-only execution.
- [ ] CLI/PATH/child npm mismatch blocks before any migration.
- [ ] Optional entries are RUN/SKIP/PENDING, never implicit.
- [ ] Reconciliation occurs only after authority change.
- [ ] Legacy helper is not selected by proven plans.

### Completion evidence

Target proof, MigrationLedger, per-owner execution/diff evidence, conditional lock evidence, focused/runtime tests.

### Rollback/recovery notes

Reconstruct from the frozen pre-migration target authority and replay incomplete ledger entries; never infer applied migrations solely from current files.

### Agent handoff

P07 may rely on a fully migrated target generation and exact dependency authority.

## Phase P07 — P0-6 Dependency freeze, clean validation, and diagnostic delta

### Objective

Freeze package.json/selected-lock/workspace authority and validate it in a brand-new generation with full dependency/version/build/test evidence and four-way diagnostic delta.

### Why

Current validation reuses the active workspace and baseline-aware acceptance is lint-only, allowing physical residue or undifferentiated diagnostics.

### Preconditions

P06 migration ledger terminal and any authority reconciliation PROVED.

### Existing code to REUSE unchanged

- [REUSE] `StageSandboxCopier`, canonical stage fingerprint profile, validation command registry, immutable artifacts.
- [REUSE] `ValidationRunner` target resolution and summary registration skeleton.
- [REUSE] approved G03/G09 baseline-debt authority checks.

### Existing code to UPDATE

- [UPDATE] `backend/app/services/validation_runner.py:46-360` — bind all commands to a new validation generation; add install/tree/version before build/test/lint; summary binds exact candidate fingerprint.
- [UPDATE] `backend/app/services/baseline_aware_validation_service.py:27-249` — normalize build/test/lint diagnostics and compute PRE_EXISTING/NEW/RESOLVED/CHANGED.
- [UPDATE] `backend/app/services/transformer_stage_service.py:718-1493` — create validation generation from dependency-authority freeze with volatile exclusions.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:958-1131,5214-5636` — normal and repaired validation use the same clean-generation path.
- [UPDATE] `backend/app/domain/transformation.py` — add `DependencyAuthorityFreeze`, `DiagnosticDelta`, `ValidationSummary`.
- [UPDATE] `backend/tests/test_validation_runner.py`, `backend/tests/test_baseline_aware_validation_service.py`, `backend/tests/test_validation_target_union.py`, `backend/tests/test_transformer_stage_reconstruction.py`, and `backend/tests/test_stage_validation_seal_f24.py` — clean generation, diagnostic delta, target union, reconstruction, and validation-to-seal boundary.

### New files to ADD

NONE.

### Files explicitly NOT to touch

Promotion/seal behavior, repair proposal schema, failure routing, DB models, frontend.

### Data/contracts

Freeze binds the immutable section-aware `DependencyIntent` (all five package.json sections) and checksum, exact npm descriptor and `LockfileAuthorityPolicy` checksum, selected lock filename/kind/raw SHA/version/canonical dependency-set checksum, per-section/per-kind root-sync classifications and absence semantics, npm-ci/npm-ls same-authority evidence, source workspace fingerprint, runtime/catalogue/plan checksums, migration ledger checksum, and target CLI authority checksum. Diagnostic/Validation contracts follow section 12 and use canonical sorted signatures; no flattened dependency map is semantic authority.

### Workflow transitions

Freeze → reconstruct `DependencyIntent`/npm capability → section-aware root-sync → create validation → npm-ci → npm-ls → exact proof → build → test → optional lint → diagnostic delta → aggregate. A normal pass waits for G09; a repaired pass waits for G11 and then G09; both promote only after their required approvals. Failure waits for P09 owner routing.

### Command templates

Reuse npm-ci-final, npm-dependency-tree, version/build/test/lint. Validation alias/path is plan-authorized and separate from active authority.

### Failure/recovery behavior

Any live mismatch discards/reconstructs validation from freeze. Validation re-selects lock authority before npm-ci; filename/kind/checksum drift or npm-ci consuming a different authority fails lock validation. npm-ci/tree/version faults classify later; no source LLM fallback here. Restart reuses terminal evidence only when generation fingerprint and freeze/authority checksums match.

### Implementation steps

1. Add pure diagnostic normalize/delta tests including changed messages/severity and path normalization.
2. Add freeze and validation contracts with section-aware `DependencyIntent`, exact npm capability policy, selected lock authority/resolved state, root-sync absence semantics, npm-ci/npm-ls equality, and target CLI authority bindings.
3. Create validation generation with exclusion assertions.
4. Extend runner sequence and candidate-bound summary.
5. Generalize baseline approval lookup across validation groups.
6. Route normal and repaired validation through one implementation.
7. Add restart and dirty-generation tests.

### Tests to ADD/UPDATE

- Unit: four diagnostic categories and deterministic checksum.
- Unit: pre-existing allowed only by approved policy; new/changed fail.
- Unit: required and dev root entries must materialize under the governed migration install mode; missing entries are mismatches.
- Unit: optional dependency absence is allowed only with valid npm/platform evidence; present incompatibility is a mismatch; optional-peer absence is allowed and present incompatibility is a mismatch.
- Unit: npm 3–6 peer absence is not an ordinary missing-root mismatch; npm 7+ peer conflicts and peer graph outcomes follow bound npm solve/ci/ls evidence.
- Unit: static peer/optional findings cannot override a contradictory npm dependency tree.
- Integration: `test_validation_runner.py` clean generation and full sequence.
- Integration: `test_baseline_aware_validation_service.py` build/test/lint.
- Integration: reconstruction excludes volatile output.
- Baseline expected: lint tests mostly pass; broader shared tests include P00 failures.
- New expected: all new delta/clean-validation tests pass.
- Regression rule: no validation summary can refer to the authoritative mutable path directly.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_validation_runner.py tests/test_baseline_aware_validation_service.py tests/test_validation_target_union.py tests/test_transformer_stage_reconstruction.py tests/test_stage_validation_seal_f24.py
.\.venv\Scripts\python.exe -m ruff check app/services/validation_runner.py app/services/baseline_aware_validation_service.py app/services/transformer_stage_service.py app/orchestration/transformer_graph.py app/domain/transformation.py
Pop-Location
```

### Runtime validation

Fixture: frozen migrated target plus source baseline diagnostics and section-aware `DependencyIntent`. Runtime: mode-authorized target with exact npm capability policy. Evidence: copied-path exclusions, per-section root-sync (including optional/peer absence semantics), npm-ci/npm-ls same-authority/tree proof, exact proof, build/test/lint outputs, normalized source/target signatures, delta, candidate fingerprint, and policy checksum. Pass when clean validation succeeds or fails solely according to approved delta policy; a static peer/optional finding cannot override contradictory npm tree evidence. Inspect validation generation and summary/delta artifacts on failure.

### Acceptance criteria

- [ ] Package/lock/workspace freeze is explicit and immutable.
- [ ] Validation is brand-new and contains no inherited governed volatile output.
- [ ] npm-ci, npm-ls, exact target, build, tests, and optional lint are bound.
- [ ] Validation target proof uses `PackageLockReader`; no V3-only root assumption exists.
- [ ] Validation uses immutable section-aware `DependencyIntent` from package.json and proves Factory/npm-ci/npm-ls selected the same shrinkwrap-or-package-lock authority under the exact npm capability policy.
- [ ] Dependencies and devDependencies require valid materialization under the governed migration install mode.
- [ ] Optional dependency absence and optional-peer absence are explicitly allowed only under their recorded evidence semantics; they are not synthesized into the lock.
- [ ] npm 3–6 peer absence is not treated as npm 7+ peer installation behavior; npm 7+ peer outcomes are owned by governed npm solver/tree evidence.
- [ ] Python does not solve peer or optional graphs, and static findings cannot override contradictory npm-ci/npm-ls evidence.
- [ ] PRE_EXISTING/NEW/RESOLVED/CHANGED are deterministic.
- [ ] Existing debt requires approved baseline authority.
- [ ] Validation summary binds the exact candidate fingerprint.

### Completion evidence

DependencyAuthorityFreeze, DiagnosticDelta, ValidationSummary, clean-generation inventory, focused/runtime tests.

### Rollback/recovery notes

Discard failed validation generations and reconstruct from the immutable freeze. Target authority remains unchanged.

### Agent handoff

P08 may promote only the exact candidate/fingerprint named by an approved ValidationSummary.

## Phase P08 — P0-7 Exact promotion, gates, seal, and N+1 handoff

### Objective

Promote only the generation proven by P07 after the correct gate sequence—normal G09, repaired G11 then G09—then create G12, seal it, and make that exact fingerprint the next adjacent source.

### Why

Validation has no value if promotion can select a different tree or occur before its approvals. Current code truth already maps G11 approval to CREATE_G09, but G09 currently advances directly to CREATE_G12; the proven semantic graph must insert promotion between G09 and G12 without changing legacy behavior.

### Preconditions

P07 complete; an immutable ValidationSummary exists; G09/G11 evidence policy is known; stage target identity is exact.

### Existing code to REUSE unchanged

- [REUSE] `backend/app/services/workspace_authority_service.py:36-235` — monotonic generation authority changes and lineage.
- [REUSE] `backend/app/services/stage_sealing_service.py:100-280` — G09, target proof, cleanliness, fingerprint, and seal invariants.
- [REUSE] `backend/app/orchestration/transformer_sealing_flow.py:53-123,159-575` — sealing/materialization/completion orchestration and terminal events after the gate-selection checks updated below.
- [REUSE] existing checkpoint, gate, continuation-token, audit-event, and next-stage persistence models.

### Existing code to UPDATE

- [UPDATE] `backend/app/services/candidate_promotion_service.py:50-213` — require approved ValidationSummary, use the canonical stage fingerprint profile, and prove candidate/fingerprint equality before delegating authority promotion.
- [UPDATE] `backend/app/services/stage_gate_service.py:55-351` — preserve code-truth G11→CREATE_G09; for proven plans route approved G09→PROMOTE_VALIDATED while legacy remains G09→CREATE_G12; G12→SEAL remains.
- [UPDATE] `backend/app/orchestration/transformer_sealing_flow.py:124-163,432-451` — seal only after approved G12 and verify required normal/repaired gate chain; never treat G11 as a substitute for G12 or G09.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:958-1131, 5214-5636` — replace same-workspace success with validated-generation promotion, then seal.
- [UPDATE] `backend/app/services/transformer_stage_service.py:107-203, 1495-1604` — persist promotion checkpoint and derive the next source only from sealed authority.
- [UPDATE] `backend/app/services/next_stage_materializer_service.py:36-166` — assert predecessor seal/fingerprint before N+1 creation.
- [UPDATE] promotion, gate, seal, next-stage, and full-completion tests listed below.

### New files to ADD

- [ADD] `backend/tests/test_proven_transformer_integration.py` — one cross-service happy-path/negative-invariant suite; do not create per-node test files.

### Files explicitly NOT to touch

DB schema/migrations, compatibility catalogue, command renderers, repair prompt contracts, frontend.

### Data/contracts

CandidatePromotion references stage, path kind NORMAL/REPAIRED, candidate_generation_id, ValidationSummary checksum, G11 package/decision checksum when repaired, G09 package/decision checksum, validated fingerprint, decision, approver, and timestamp using current records plus artifacts. The canonical fingerprint is `STAGE_FINGERPRINT_PROFILE`; no second fingerprint algorithm is allowed.

### Workflow transitions

NORMAL: VALIDATION_PASS → CREATE/WAIT_G09 → G09_APPROVED → PROMOTION_PENDING → AUTHORITY_PROMOTED → CREATE/WAIT_G12 → G12_APPROVED → SEALED → NEXT_STAGE_CREATED.

REPAIRED: REPAIR_VALIDATION_PASS → CREATE/WAIT_G11 → G11_APPROVED → CREATE/WAIT_G09 → G09_APPROVED → PROMOTION_PENDING → AUTHORITY_PROMOTED → CREATE/WAIT_G12 → G12_APPROVED → SEALED → NEXT_STAGE_CREATED.

Any missing decision or fingerprint inequality stops before authority mutation. Final-major seal transitions to journey completion instead of creating another stage.

### Command templates

NONE. Promotion and sealing are deterministic backend operations; they do not execute project commands.

### Failure/recovery behavior

Fingerprint or gate-chain mismatch is a governance failure, never repaired in place. Revalidation makes earlier pending/approved packages stale and creates a new chain. A crash before promotion resumes at the first missing approval; a crash after promotion reuses its exact lineage and proceeds to G12. Sealing rechecks G09, optional G11, promotion, active binding, and G12 idempotently. N+1 creation is unique per sealed predecessor.

### Implementation steps

1. Make candidate promotion consume ValidationSummary rather than directory existence alone.
2. Remove the home-grown promotion fingerprint from the decision path and call the canonical fingerprint service.
3. Add compare-and-promote checks under existing workspace authority transaction semantics.
4. Make the proven gate successor table explicit: repaired G11→G09; all proven G09→promotion; promotion→G12; G12→seal.
5. Bind G11/G09 packages to the same ValidationSummary/fingerprint without auto-approving human decisions.
6. Persist promotion before creating G12 and make seal require the exact promotion/G12 lineage.
7. Bind next-stage source generation/fingerprint to predecessor sealed authority.
8. Cover last-major completion and duplicate-resume behavior.

### Tests to ADD/UPDATE

- [UPDATE] `backend/tests/test_candidate_promotion_f22.py` — approved summary, mismatch rejection, monotonic promotion.
- [UPDATE] `backend/tests/test_workspace_authority_f07.py` — exact promoted lineage and duplicate handling.
- [UPDATE] `backend/tests/test_stage_gate_service.py` and `backend/tests/test_stage_sealing.py` — exact normal/repaired order, legacy successor compatibility, G12-after-promotion, and one fingerprint.
- [UPDATE] `backend/tests/test_next_stage_materializer.py` and `backend/tests/test_full_completion_invariant.py` — sealed-fingerprint handoff/final completion.
- [ADD] integration cases in `backend/tests/test_proven_transformer_integration.py`.
- Baseline expected: existing focused tests retain their documented P00 status.
- New expected: promotion mismatch and unvalidated candidate tests fail closed; happy path seals.
- Regression rule: `promoted_fingerprint == validated_fingerprint == sealed_fingerprint`.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_candidate_promotion_f22.py tests/test_workspace_authority_f07.py tests/test_stage_gate_service.py tests/test_stage_sealing.py tests/test_next_stage_materializer.py tests/test_full_completion_invariant.py tests/test_proven_transformer_integration.py
.\.venv\Scripts\python.exe -m ruff check app/services/candidate_promotion_service.py app/services/workspace_authority_service.py app/services/stage_gate_service.py app/services/stage_sealing_service.py app/orchestration/transformer_sealing_flow.py app/orchestration/transformer_graph.py
Pop-Location
```

### Runtime validation

Fixture: normal, repaired, missing-G11, missing-G09, pre-promotion-G12, and deliberately mismatched candidates. Evidence: ValidationSummary, ordered gate packages/decisions, promotion record, authority binding, G12, seal, next-stage binding. Pass only on `validated == G11(if repaired) == G09 == promoted == sealed`. Inspect the first missing/stale gate or fingerprint.

### Acceptance criteria

- [ ] Only an approved, exact validated generation is promotable.
- [ ] Normal validation requires G09 approval before promotion.
- [ ] Repaired validation requires G11 then G09 approval before promotion.
- [ ] G12 is created/approved only after the exact validated generation is active.
- [ ] Existing gate/reviewer/human requirements remain mandatory.
- [ ] Validated, optional G11, G09, promoted, active, and sealed fingerprints are equal.
- [ ] N+1 consumes the exact sealed N+1 predecessor authority.
- [ ] Resume cannot double-promote, double-seal, or fork a next stage.

### Completion evidence

Promotion record, authority lineage, gate decisions, stage seal, next-stage source binding, focused/integration results.

### Rollback/recovery notes

Never roll authority backward by deleting records. Resume or create/revalidate a new candidate under existing monotonic authority rules.

### Agent handoff

P09 may now route every non-pass result before any repair actor is selected; P10 must return repaired passes through G11→G09→promotion→G12.

## Phase P09 — P1-0 Evidence-first failure ownership

### Objective

Classify failed nodes by phase and authoritative evidence, then route exclusively to HARNESS, RUNTIME, DEPENDENCY, LOCKFILE, deterministic source rule, or Main Repair LLM ownership.

### Why

Exit code or stderr alone cannot distinguish platform residue, solver failure, incomplete discovery, and source incompatibility. Wrong ownership wastes retries and can let an LLM edit around infrastructure faults.

### Preconditions

P03-P08 emit phase-bound evidence; current failure taxonomy and persistence are understood; no classifier relies on fixture-specific messages alone.

### Existing code to REUSE unchanged

- [REUSE] `backend/app/services/failure_evidence_service.py:1-310` — normalized command/artifact evidence collection.
- [REUSE] `backend/app/services/failure_intelligence_service.py:1-343` — classification persistence and audit surface.
- [REUSE] current retry-budget, human-escalation, checkpoint, and failure-event records.
- [REUSE] worker terminal-state semantics: return code determines process failure; stderr remains evidence.

### Existing code to UPDATE

- [UPDATE] `backend/app/domain/failure_intelligence.py:1-78` — add proven phase/owner values and structured completeness/reproducibility facts while retaining legacy values.
- [UPDATE] `backend/app/services/failure_evidence_service.py:1-310` — ingest TargetIntent, section-aware `DependencyIntent`, exact npm capability policy, section/kind/absence-aware root-sync, LockResolution, runtime, generation, ledger, freeze, and diagnostic evidence.
- [UPDATE] `backend/app/services/failure_intelligence_service.py:1-343` — phase-first deterministic routing and confidence/reason contract.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:1598-2214` — classify before retry/repair; dispatch only to the named owner.
- [UPDATE] `backend/app/services/dependency_failure_bundle_service.py:1-286` — bind dependency/lock inputs for their specialist owners.
- [UPDATE] `backend/tests/test_failure_intelligence_f19.py`, `backend/tests/test_failure_evidence_service.py`, `backend/tests/test_failure_classification_persistence.py`, `backend/tests/test_classify_failure_livelock.py`, and `backend/tests/test_transformer_repair_failure_governance.py` — phase evidence, owner persistence, retry ceiling, and source-LLM exclusion.

### New files to ADD

NONE.

### Files explicitly NOT to touch

DB migrations, LLM patch generation, candidate promotion, catalogue values, frontend.

### Data/contracts

FailureDecision = `{phase, owner, category, evidence_refs, reason_codes, confidence, retryable, completeness_state, dependency_intent_checksum, npm_capability_policy_checksum, root_sync_findings}`. Each root-sync finding retains package, section/kind, requested spec, resolved version, absence semantics, and deferred npm evidence. Owners are PLATFORM_RECOVERY, RUNTIME_RESOLVER, COMPATIBILITY_PLANNER, LOCK_RESOLVER, DETERMINISTIC_REPAIR, MAIN_REPAIR_LLM, or HUMAN under existing governance. Legacy categories remain readable.

### Workflow transitions

Any node fail → CAPTURE_EVIDENCE → CLASSIFY → one owner queue. Discovery exit nonzero + COMPLETE TargetIntent continues with warning; INCOMPLETE blocks/reroutes. No classifier path falls through to source repair.

### Command templates

NONE. Owners later schedule catalogued commands; classification executes none.

### Failure/recovery behavior

Missing/corrupt harness evidence or an internal selector/reader exception routes PLATFORM_RECOVERY. A validly detected missing/malformed/unsupported selected lock authority or section-aware required/dev manifest/root-sync mismatch routes LOCK_RESOLVER with its explicit code. Optional dependency or optional-peer absence is not automatically a failure; npm/platform evidence must classify it as allowed or deferred. npm 3–6 peer absence is not automatically a mismatch, while npm 7+ peer conflicts produced by the bound npm solver route DEPENDENCY. Parser/policy inability to interpret section metadata routes HARNESS or `DEFER_TO_NPM`, never source repair. CLI entrypoint/version/checksum, governed PATH, child npm, or runtime incompatibility routes RUNTIME_RESOLVER/TOOLCHAIN recovery. Convergence/reproducibility or missing shrinkwrap replacement policy routes lock/dependency-policy ownership. Known rule match routes deterministic repair. Only bounded source/template/test/config groups reach Main Repair LLM. Low confidence follows existing human policy rather than guessing.

### Implementation steps

1. Extend enum/schema readers additively.
2. Define required evidence by phase and explicit absence semantics.
3. Implement pure routing precedence with table-driven tests.
4. Persist decision before dispatch.
5. Separate discovery completeness from process success.
6. Prevent source-LLM dispatch for platform/runtime/dependency/lock categories.
7. Add retry budget ownership and livelock assertions.

### Tests to ADD/UPDATE

- [UPDATE] `backend/tests/test_failure_evidence_service.py` — phase artifact ingestion, section-aware intent/policy evidence, and missing evidence.
- [UPDATE] `backend/tests/test_failure_intelligence_f19.py` and `backend/tests/test_failure_classification_persistence.py` — owner decisions/backward compatibility.
- [UPDATE] `backend/tests/test_classify_failure_livelock.py` — finite owner retry.
- [UPDATE] `backend/tests/test_transformer_repair_failure_governance.py` — platform categories never reach source repair.
- [UPDATE] integration suite with discovery nonzero/complete, npm-ci-after-lock failures, required/dev missing resolution, optional/optional-peer omission, npm6 peer absence, and npm7+ peer conflict.
- Regression rule: a diagnostic must retain phase, command, generation, runtime, and evidence identity.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_failure_evidence_service.py tests/test_failure_intelligence_f19.py tests/test_failure_classification_persistence.py tests/test_classify_failure_livelock.py tests/test_transformer_repair_failure_governance.py tests/test_proven_transformer_integration.py
.\.venv\Scripts\python.exe -m ruff check app/domain/failure_intelligence.py app/services/failure_evidence_service.py app/services/failure_intelligence_service.py app/services/dependency_failure_bundle_service.py app/orchestration/transformer_graph.py
Pop-Location
```

### Runtime validation

Fixtures: harness/parser policy error, incompatible runtime, required/dev root missing, allowed optional or optional-peer omission, npm 3–6 peer absence, npm 7+ peer conflict, non-convergent lock, known rule, unknown source error, and discovery nonzero/complete. Evidence: one persisted FailureDecision each with intent/policy/root-sync refs. Pass when expected owner is exact and mutually exclusive; optional/optional-peer absence and npm6 peer absence do not fail by themselves. Inspect precedence reason codes on mismatch.

### Acceptance criteria

- [ ] Classification is evidence/phase based, not stderr based.
- [ ] Discovery success and completeness are independent.
- [ ] Platform/runtime/dependency/lock failures never route to source LLM repair.
- [ ] CLI/PATH/child npm authority faults route to runtime/toolchain recovery; canonical lock-shape faults route to lock ownership.
- [ ] Required root or dev materialization/manifest-lock inconsistency routes LOCKFILE or DEPENDENCY by phase/evidence; npm-produced peer conflicts route DEPENDENCY.
- [ ] Optional dependency omission, optional-peer omission, and npm3–6 peer absence are not automatic failures or fresh-lock authorization.
- [ ] Metadata/policy parser inability routes HARNESS or `DEFER_TO_NPM`, never source repair.
- [ ] Unknown source repair receives only a bounded ProblemGroup.
- [ ] Retry and escalation remain finite and governed.

### Completion evidence

Routing decision table, persisted examples, focused/integration results, unchanged governance proofs.

### Rollback/recovery notes

New classifiers can be disabled by proven-plan semantic version; legacy stages retain old routing. Preserve all evidence for reclassification.

### Agent handoff

P10 assumes MAIN_REPAIR_LLM is reachable only through an approved P09 FailureDecision.

## Phase P10 — P1-1 Isolated repair candidate, bounded LLM intent, and reviewer

### Objective

Make all source repair candidate-scoped; give the Main Repair LLM one bounded ProblemGroup and make the Reviewer decide without authoring replacement patches.

### Why

The current repair application can apply against active authority. Proven behavior requires isolated candidates, exact preimages, clean revalidation, and promotion only after approval.

### Preconditions

P09 routing complete; P07 validation is reusable; current repair/reviewer/human gates remain authoritative.

### Existing code to REUSE unchanged

- [REUSE] existing RepairAttempt, ProblemGroup, reviewer-decision, human-approval, artifact, and checkpoint persistence.
- [REUSE] `backend/app/services/patch_apply_service.py:1-305` — preimage-aware patch mechanics after adding the candidate-root assertion below.
- [REUSE] existing prompt safety, audit, retry ceiling, and reviewer/human governance.

### Existing code to UPDATE

- [UPDATE] `backend/app/services/repair_application_service.py:661-737, 1286-1760, 5682-5895` — build one bounded context, require structured intent, and target a candidate generation.
- [UPDATE] `backend/app/services/patch_apply_service.py:1-305` — reject authoritative roots, fabricated/missing preimages, commands, lock edits, and out-of-scope files.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:3047-3650, 5214-5636` — create candidate, apply approved intent there, then invoke the single clean-validation path.
- [UPDATE] reviewer contracts/services under `backend/app/domain/repair_lifecycle.py:1-136` and `backend/app/services/repair_application_service.py` — enforce ACCEPT, REQUEST_CHANGES, REJECT, INSUFFICIENT_CONTEXT only; no replacement patch field.
- [UPDATE] `backend/tests/test_repair_application_service.py`, `backend/tests/test_patch_apply_service.py`, `backend/tests/test_analysis_reviewer_lifecycle_regression.py`, and `backend/tests/test_transformer_repair_failure_governance.py` — bounded intent, candidate-root safety, reviewer decisions, and human governance.

### New files to ADD

NONE.

### Files explicitly NOT to touch

DB schema/migrations, package-lock or npm-shrinkwrap contents, runtime binding decisions, npm solver decisions, authoritative generation files, frontend.

### Data/contracts

RepairContext binds exactly one ProblemGroup, current candidate file preimages, normalized diagnostics, target/stage/runtime/ledger/freeze context, allowed paths, and evidence checksums. RepairIntent contains file operations with exact preimage hash and rationale; no command/runtime/dependency-lock fields. ReviewerDecision is one of the four governed outcomes plus reasons/context requests.

### Workflow transitions

SOURCE_FAILURE → CANDIDATE_CREATED → INTENT_PROPOSED → REVIEWED. ACCEPT → APPLY_TO_CANDIDATE → CLEAN_REVALIDATE → G11 → G09 → P08 exact promotion → G12 → seal. REQUEST_CHANGES → bounded proposal retry. INSUFFICIENT_CONTEXT → evidence acquisition/human route. REJECT → next governed attempt or human. No transition edits authority directly.

### Command templates

The LLM and reviewer receive no command template. Revalidation commands are P07 catalogue commands scheduled by the backend.

### Failure/recovery behavior

Preimage mismatch invalidates intent and requests a new context; it never force-applies. Candidate mutation failure discards candidate. Reviewer cannot mutate the proposal. Candidate validation failure returns new diagnostics through P09. Retry exhaustion follows existing human governance.

### Implementation steps

1. Reuse generation creation to clone only governed source/authority files into a repair candidate.
2. Bind one ProblemGroup and exact current preimages.
3. Narrow proposal schema to structured file intent and validate trust boundaries.
4. Add candidate-root and forbidden-path assertions to patch application.
5. Narrow reviewer output and discard any authored replacement content.
6. Route accepted candidates through P07, then require G11 and G09 before P08 promotion; create G12 only after promotion.
7. Keep all existing human approval checkpoints and audit events.

### Tests to ADD/UPDATE

- [UPDATE] `backend/tests/test_repair_application_service.py` — bounded context, schema, candidate targeting, retry outcomes.
- [UPDATE] `backend/tests/test_patch_apply_service.py` — authority/lock/command/preimage rejection.
- [UPDATE] `backend/tests/test_analysis_reviewer_lifecycle_regression.py` — exact four decisions and no patch authorship.
- [UPDATE] `backend/tests/test_transformer_repair_failure_governance.py` — human invariants and clean revalidation.
- [UPDATE] integration suite: failed candidate leaves authority unchanged; accepted validated candidate promotes.
- Regression rule: authoritative fingerprint is unchanged until P08.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_repair_application_service.py tests/test_patch_apply_service.py tests/test_analysis_reviewer_lifecycle_regression.py tests/test_transformer_repair_failure_governance.py tests/test_proven_transformer_integration.py
.\.venv\Scripts\python.exe -m ruff check app/services/repair_application_service.py app/services/patch_apply_service.py app/orchestration/transformer_graph.py
Pop-Location
```

### Runtime validation

Fixture: unknown source failure with one ProblemGroup and two candidate attempts. Evidence: candidate fingerprint before/after, prompt/context checksum, structured intent, reviewer decision, patch audit, ValidationSummary. Pass when failed candidate cannot change authority and accepted candidate reaches P08. Inspect preimage/scope rejection first.

### Acceptance criteria

- [ ] Main Repair LLM receives one bounded ProblemGroup and authoritative current candidate files.
- [ ] It emits intent only: no commands, lock edits, runtime choices, or invented preimages.
- [ ] Reviewer emits exactly one governed decision and no replacement patch.
- [ ] Human approvals remain mandatory where currently required.
- [ ] Repair never mutates authority before clean validation and promotion.
- [ ] Repaired validation approval order is G11→G09→promotion→G12→seal.

### Completion evidence

Bounded context/intent schemas, reviewer decisions, patch audit, unchanged-authority proof, candidate validation/promotion records.

### Rollback/recovery notes

Discard the isolated candidate and retain its evidence. Never reverse an applied authoritative change because none occurs before P08.

### Agent handoff

P11 may intercept only exact deterministic rule matches before Main Repair LLM proposal.

## Phase P11 — P1-2 Versioned deterministic Stage Knowledge rules

### Objective

Represent proven deterministic source fixes as versioned, evidence-matched Stage Knowledge rather than Angular-major/package/example branches.

### Why

Known fixes should be reproducible and cheap, but hard-coded fixture examples turn a migration platform into a brittle script.

### Preconditions

P09 owner routing and P10 candidate safety complete; Stage Knowledge catalogue/checksum mechanisms are available.

### Existing code to REUSE unchanged

- [REUSE] `backend/app/services/stage_knowledge_service.py:1-138` — version lookup, activation, and evidence/audit patterns.
- [REUSE] `backend/app/repositories/stage_knowledge_models.py:1-31` and current JSON payload storage — no schema change.
- [REUSE] P10 candidate, preimage, review/human, validation, and promotion paths.

### Existing code to UPDATE

- [UPDATE] `backend/app/domain/stage_knowledge.py:32-122` — replace executable major/package special cases with generic rule schema and capability predicates; keep legacy readers.
- [UPDATE] `backend/app/services/stage_knowledge_service.py:1-138` — deterministic exact-match evaluation, checksum, and operation rendering.
- [UPDATE] `backend/app/api/stage_knowledge_contracts.py:1-49` and `backend/app/api/routes/stage_knowledge.py:1-87` — project generic rules without executable arbitrary code.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:1598-2214` — choose deterministic owner only on one exact active rule match.
- [UPDATE] `backend/tests/test_stage_knowledge_f17.py`, `backend/tests/test_transformer_repair_failure_governance.py`, and `backend/tests/test_patch_apply_service.py` — rule matching, routing, candidate intent, and preimage enforcement.

### New files to ADD

NONE.

### Files explicitly NOT to touch

DB migrations, Angular-major conditionals, fixed Node paths, package-lock/npm-shrinkwrap direct edits, LLM reviewer outcome set.

### Data/contracts

Rule = `{rule_id, version, active, diagnostic_predicates, stage_capability_predicates, file_globs, required_preimage, operation_template, expected_postcondition, checksum}`. Predicates consume normalized evidence/catalogue/runtime capabilities; operation templates use the same bounded RepairIntent operations as P10.

### Workflow transitions

P09 source failure → evaluate active rules. Exactly one match → create candidate → render deterministic intent → validate preimage → apply → P07. Zero matches → P10 Main Repair LLM. Multiple matches/invalid knowledge → human/knowledge governance; never pick by order.

### Command templates

NONE. Deterministic rules author file intent, not shell commands.

### Failure/recovery behavior

Rule checksum/preimage/postcondition failure disables that attempt and routes via governed evidence, not a blind retry. A failing repaired candidate is reclassified from its new evidence. Knowledge activation remains auditable/versioned.

### Implementation steps

1. Add generic schema parsing to existing payload model.
2. Preserve legacy knowledge read compatibility but stop new proven plans from executing embedded special cases.
3. Implement pure predicate matching and ambiguity rejection.
4. Render only P10-valid operations against current candidate preimages.
5. Require postcondition plus clean validation.
6. Add API projections and activation audit.

### Tests to ADD/UPDATE

- [UPDATE] `backend/tests/test_stage_knowledge_f17.py` — exact/no/ambiguous matches, version/checksum, legacy reads.
- [UPDATE] `backend/tests/test_transformer_repair_failure_governance.py` — deterministic-before-LLM and candidate isolation.
- [UPDATE] `backend/tests/test_patch_apply_service.py` — rendered operation uses exact preimage.
- Regression rule: tests use synthetic capabilities/diagnostics, never a named Angular-major fix.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_stage_knowledge_f17.py tests/test_transformer_repair_failure_governance.py tests/test_patch_apply_service.py
.\.venv\Scripts\python.exe -m ruff check app/domain/stage_knowledge.py app/services/stage_knowledge_service.py app/api/stage_knowledge_contracts.py app/api/routes/stage_knowledge.py app/orchestration/transformer_graph.py
Pop-Location
```

### Runtime validation

Fixture: synthetic normalized diagnostic with one active matching rule, plus zero/multiple cases. Evidence: knowledge version/checksum, match trace, candidate intent, postcondition, ValidationSummary. Pass only for unique exact match and clean validation. Inspect predicate trace on failure.

### Acceptance criteria

- [ ] No fixture-specific Angular major, package, source rename, or Node path is executable code.
- [ ] Deterministic rules are versioned, checksummed, evidence-driven, and auditable.
- [ ] Zero matches route to bounded LLM; multiple matches fail closed.
- [ ] Rules operate only on isolated candidates and require P07/P08.

### Completion evidence

Generic schema, match traces, knowledge audit, focused tests, candidate validation proof.

### Rollback/recovery notes

Deactivate the faulty knowledge version and replay classification from retained evidence; no DB rollback is needed.

### Agent handoff

P12 adds restart/idempotency guarantees across every proven node and repair branch.

## Phase P12 — P1-3 Recovery, restart, and idempotency

### Objective

Make every proven node safely resumable from durable evidence, including run mode/qualification authorization, CLI toolchain authority, manifest/selected-lock authority/schema transition, partial commands, gate order, candidate repair, promotion, and sealing; restore full pytest collection against the final reconstruction API.

### Why

Adjacent migrations are long-running and external tools can partly mutate disposable/candidate workspaces. A restart must neither trust unbound residue nor repeat irreversible authority changes.

### Preconditions

P02 semantic version and P03-P11 node artifacts/checkpoints are defined; worker wake and stage reconstruction behavior is understood.

### Existing code to REUSE unchanged

- [REUSE] existing StageStep, StageCheckpoint, command lifecycle, artifact, generation, binding, promotion, seal, and continuation records.
- [REUSE] `backend/app/services/stage_recovery_service.py:101-1787` — persisted recovery decisions and retry governance.
- [REUSE] `backend/app/orchestration/transformer_worker.py:1-287` — wake/claim loop and existing single-owner execution.
- [REUSE] `backend/app/services/transformer_stage_service.py:718-1493` — reconstruction base.

### Existing code to UPDATE

- [UPDATE] `backend/app/services/stage_recovery_service.py:101-1787` — recognize every proven node, its mode/toolchain/lock/gate terminal evidence, section-aware `DependencyIntent`/npm policy, invalidation boundary, and retry owner.
- [UPDATE] `backend/app/services/transformer_stage_service.py:718-1493` — reconstruct proven semantic plans, generation bindings, and pending node from checksummed evidence.
- [UPDATE] `backend/app/orchestration/transformer_worker.py:1-287` — wake proven stages without duplicating claimed commands or terminal transitions.
- [UPDATE] `backend/app/orchestration/transformer_graph.py:227-328, 1598-2214` — central idempotency guard before each side effect.
- [UPDATE] `backend/app/services/command_executor_service.py:281-832` — expose terminal command evidence consistently to recovery; preserve return-code semantics.
- [UPDATE] `backend/tests/test_transformation_replan_recovery.py`, `backend/tests/test_command_recovery.py`, `backend/tests/test_transformer_worker_wake.py`, `backend/tests/test_transformer_stage_reconstruction.py`, and `backend/tests/test_command_terminal_lifecycle.py` — proven-node resume, command reconciliation, wake, reconstruction, and terminal-state distinction.
- [UPDATE] `backend/tests/test_transformer_stage_runtime_integration.py` — remove the stale import/reference to missing `_runtime_bindings_from_stage`; adapt the test to the final public proven runtime-binding/reconstruction API and verify semantic plan version, immutable mode/certification authority, exact runtime descriptors, CLI authority where applicable, and restart behavior. Do not resurrect the private helper unless current production code truth independently requires it.

### New files to ADD

NONE.

### Files explicitly NOT to touch

DB schema/migrations, OS-specific cleanup scripts, new queues, distributed locks, frontend.

### Data/contracts

Each node defines `input_checksum`, `attempt_id`, `generation_id`, `terminal_evidence_refs`, `output_checksum`, and `invalidation_reason`. Runtime/toolchain nodes additionally bind mode, qualification authorization checksum, absolute CLI/package/runtime identities, governed PATH/environment, child npm, source/target fingerprints, and actual-version proof. Lock nodes bind the exact npm descriptor, `LockfileAuthorityPolicy` (including peer-install, optional-omission, and dev-install capabilities), immutable section-aware `DependencyIntent` and checksum, selected filename/kind/raw SHA, reader schema/version/dependency-set, per-package section/kind/absence-aware root-sync classification (`VERIFIED`, `MISMATCH`, or `DEFER_TO_NPM`), npm-ci/npm-ls same-authority evidence, policy, and transition checksums. Gate nodes bind path kind, ValidationSummary, G11 if repaired, G09, promotion, G12, and one fingerprint. Missing proven metadata makes a legacy step, not a guessed completion.

### Workflow transitions

WAKE → RECONSTRUCT → validate semantic version, immutable run mode, qualification authorization if applicable, runtime/toolchain/checksums/authority, section-aware `DependencyIntent` including `peerDependenciesMeta`, exact npm capability/policy, re-selected lock authority/reader/root-sync/npm-ci/npm-ls evidence, and generation → reuse terminal output or invalidate disposable generation → resume one pending node. Command RUNNING state is reconciled by existing lifecycle rules. Repaired recovery resumes the first missing step in G11→G09→promotion→G12→seal; normal recovery uses G09→promotion→G12→seal. No later decision implies an earlier one.

### Command templates

No new commands. Recovered commands reuse the exact persisted CommandSpec; a changed input checksum creates a new attempt rather than replaying stale output.

### Failure/recovery behavior

Disposable discovery/validation/candidate residue is discarded on ambiguous mutation. CLI path/checksum/version, PATH, child npm, target-generation, mode, authorization, section-aware intent, or npm capability-policy drift invalidates the command authority and re-resolves/reconstructs; ambient npm changes never reinterpret a stage. It never falls back to npx/PATH. Canonical lock evidence is re-selected using the bound npm policy and re-read from immutable raw bytes; authority drift, malformed authoritative shrinkwrap, unsupported selected lock, or missing npm 12+ shrinkwrap policy remains the same explicit lock failure and never falls through. Shrinkwrap replacement still requires its persisted policy decision. Required/dev missing resolution can fail according to phase evidence; optional/optional-peer omission and npm3–6 peer absence do not authorize deletion or fallback by themselves. Authoritative source/target is never cleaned destructively. Windows cleanup failure is PLATFORM_RECOVERY with a new generation/path. Parser implementation/harness failure retains raw evidence and reruns only after recovery. Retry budgets are finite.

### Implementation steps

1. Define terminal-evidence requirements per proven node.
2. Extend reconstruction mapping by semantic version and immutable PRODUCTION/QUALIFICATION mode.
3. Add one graph-level idempotency guard used by all proven side-effect nodes.
4. Revalidate discovery/migration CLI toolchain authority, section-aware `DependencyIntent`/`peerDependenciesMeta`, exact npm capability policy, and manifest/selected-lock/root-sync/schema evidence before command reuse.
5. Reconcile queued/running/terminal command state before scheduling.
6. Invalidate only disposable/candidate generations on uncertain partial mutation.
7. Resume exact gate chains and make promotion, G12, seal, next-stage creation, and completion idempotent against existing records.
8. Adapt `test_transformer_stage_runtime_integration.py` to the public final reconstruction API and prove collection without resurrecting a stale private helper.
9. Add failure injection at every boundary.

### Tests to ADD/UPDATE

- [UPDATE] `backend/tests/test_transformation_replan_recovery.py` and `backend/tests/test_command_recovery.py` — node recovery matrix and finite retry.
- [UPDATE] `backend/tests/test_transformer_stage_reconstruction.py` — semantic plan, section-aware dependency bindings, exact npm capability policy, and evidence checksums.
- [UPDATE] `backend/tests/test_transformer_worker_wake.py` — no duplicate command/transition.
- [UPDATE] `backend/tests/test_command_terminal_lifecycle.py` — cancellation and timeout remain distinct.
- [UPDATE] `backend/tests/test_transformer_stage_runtime_integration.py` — collects normally and validates exact runtime/mode/certification/toolchain reconstruction and restart behavior through public code truth.
- [UPDATE] integration suite with crash points after toolchain proof, discovery, `DependencyIntent`/policy construction, lock read/schema transition/attempt, migration authority, freeze, G11, G09, promotion, G12, and seal; include ambient npm-version drift and deferred peer/optional evidence.
- Regression rule: resume produces one logical output per input checksum.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_transformation_replan_recovery.py tests/test_command_recovery.py tests/test_transformer_stage_reconstruction.py tests/test_transformer_worker_wake.py tests/test_command_terminal_lifecycle.py tests/test_proven_transformer_integration.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_transformer_stage_runtime_integration.py
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m ruff check app/services/stage_recovery_service.py app/services/transformer_stage_service.py app/services/command_executor_service.py app/orchestration/transformer_worker.py app/orchestration/transformer_graph.py
Pop-Location
```

### Runtime validation

Fixture: injected crash after every mutating boundary for normal, repaired, and qualification runs, plus the repaired runtime-integration collector. Evidence: mode/authorization, CLI authority, section-aware `DependencyIntent`/`peerDependenciesMeta`, exact npm capability policy, manifest/selected-lock/root-sync/schema transition, deferred npm evidence, pre/post checkpoints, attempts, generation inventories, gate decisions, command terminal records, authority lineage, and clean collection output. Pass when resumed outcome matches uninterrupted outcome, ambient npm/policy drift blocks, no duplicate/out-of-order transition exists, and all backend tests collect. Inspect first checksum/order divergence or collection traceback.

### Acceptance criteria

- [ ] Every proven node has a documented terminal-evidence predicate.
- [ ] Partial disposable/candidate mutation is never mistaken for completion.
- [ ] Commands, promotion, seal, and N+1 creation are idempotent.
- [ ] Toolchain identity/PATH/child npm and qualification authority are re-proven on restart.
- [ ] Exact npm capability/policy, section-aware `DependencyIntent`/`peerDependenciesMeta`, lock authority, V1/V2/V3 resolved state, root-sync section/kind/absence classifications/deferred npm proof, npm-ci/npm-ls equality, and schema-transition evidence are reconstructable from immutable artifacts.
- [ ] Restart cannot reinterpret required/dev/optional/peer/optional-peer semantics under an ambient npm version; policy checksum drift invalidates reuse.
- [ ] `test_transformer_stage_runtime_integration.py` collects normally through the final public runtime reconstruction API.
- [ ] Full backend `pytest --collect-only -q` succeeds before P15; no test file is excluded to establish regression status.
- [ ] Repaired recovery cannot skip G11 or G09; normal recovery cannot promote before G09; G12 cannot precede promotion.
- [ ] Retry ceilings and owner routing survive restart.
- [ ] No recovery deletes or rewinds authoritative generations.

### Completion evidence

Recovery matrix, injected-crash results, uninterrupted/resumed fingerprint equality, command and authority audit, focused runtime-integration result, and full successful collection manifest.

### Rollback/recovery notes

Disable proven-plan scheduling for new stages if recovery regressions appear; existing proven stages remain reconstructable from retained versioned artifacts. Do not rewrite history.

### Agent handoff

P13 may expose these states, but must not recreate orchestration logic in API or frontend.

## Phase P13 — P1-4 API and frontend projections

### Objective

Expose proven-plan mode/certification, CLI authority, lock schema, node, evidence, failure owner, candidate, validation, ordered gates, promotion, and seal state through existing read projections and UI surfaces.

### Why

Operators need accurate progress and decisions. The API/UI must project backend truth and never infer completeness from process exit or duplicate the state machine.

### Preconditions

P02-P12 persisted contracts are stable; existing transformation/detail/workflow projection endpoints and UI stage views are identified.

### Existing code to REUSE unchanged

- [REUSE] existing transformation/workflow API routes, event stream, artifact preview, reviewer/human action endpoints, and frontend data-fetch pattern.
- [REUSE] `backend/app/services/workflow_projection_service.py:1-242` — projection composition and compatibility conventions.
- [REUSE] `frontend/src/components/ArtifactPreviewPanel.tsx` — evidence display rather than a new viewer.

### Existing code to UPDATE

- [UPDATE] `backend/app/services/workflow_projection_service.py:97-242` — add optional proven-plan/current-node/evidence/owner/generation fields.
- [UPDATE] `backend/app/api/routes/transformation.py:323-867` — return additive proven projection fields from `_projection` and the existing GET route.
- [UPDATE] `frontend/src/types/transformation.ts:1-166` — add optional proven projection fields.
- [UPDATE] `frontend/src/components/TransformationPanel.tsx:88-496` — render backend-provided labels, completeness, owner, evidence, and governed actions.
- [UPDATE] `backend/tests/test_transformation_api.py`, `backend/tests/test_assistant_r5_workflow_projection.py`, and `frontend/src/components/__tests__/TransformationPanel.test.tsx` — legacy/proven API and UI projections.

### New files to ADD

NONE.

### Files explicitly NOT to touch

Backend orchestration decisions, DB schema, command execution, lock solver, LLM contracts, a new frontend state store.

### Data/contracts

Additive optional projection: `{plan_semantic_version, run_mode, runtime_certification_status, qualification_authorization_ref, cli_authority_status, cli_actual_version, lockfile_version, lock_schema_transition, current_node, node_status, completeness_status, failure_owner, source_generation, candidate_generation, validation_generation, g11_status, g09_status, promotion_status, g12_status, seal_status, evidence_refs}`. Legacy stages omit fields or return legacy version; clients tolerate both.

### Workflow transitions

Backend events update the existing projection. UI renders waiting/running/blocked/review/validated/promoted/sealed states and invokes only existing governed action endpoints. It never advances a node.

### Command templates

NONE.

### Failure/recovery behavior

Unknown future node/owner values render as a neutral backend label plus raw evidence link. Projection lag cannot authorize an action. API serialization failure is HARNESS/platform evidence, not migration failure.

### Implementation steps

1. Add optional backend projection fields with legacy-safe defaults.
2. Extend route contracts without removing current fields.
3. Regenerate/update frontend types using the repository's current method.
4. Map backend labels to existing progress/detail components.
5. Reuse artifact and governance action surfaces.
6. Add unknown-value and legacy-stage tests.

### Tests to ADD/UPDATE

- [UPDATE] `backend/tests/test_transformation_api.py` and `backend/tests/test_assistant_r5_workflow_projection.py` — additive fields and legacy payload.
- [UPDATE] `frontend/src/components/__tests__/TransformationPanel.test.tsx` — proven/legacy/unknown-value rendering and no client-owned transition.
- API regression: old payload fields and human/reviewer actions are unchanged.
- Frontend regression: no client-side derivation of discovery completeness or promotion readiness.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_assistant_r5_workflow_projection.py tests/test_s3_f02_api_integration.py
.\.venv\Scripts\python.exe -m ruff check app/services/workflow_projection_service.py app/api/routes/transformation.py
Pop-Location
Push-Location frontend
npm test -- --run
npm run typecheck
npm run build
Pop-Location
```

### Runtime validation

Fixture: one legacy stage and proven stages at discovery-incomplete, review-waiting, validated, and sealed. Evidence: raw API payload and rendered component assertions. Pass when projection exactly reflects persisted backend state and legacy view remains usable. Inspect serializer/version adapter on failure.

### Acceptance criteria

- [ ] API additions are optional and backward-compatible.
- [ ] UI projects backend state; it owns no migration decisions.
- [ ] Discovery completeness, failure owner, generation identity, and seal are visible.
- [ ] Production/qualification, certification, actual CLI authority, lock schema, and ordered G11/G09/promotion/G12 status are visible without client inference.
- [ ] Existing reviewer/human workflows remain the only governed action surfaces.

### Completion evidence

API examples, contract/component tests, typecheck, frontend build, legacy/proven screenshots or test snapshots where already used.

### Rollback/recovery notes

Frontend can ignore additive fields. Backend version gate can omit proven projection for legacy plans; no data migration is required.

### Agent handoff

P14 qualifies actual adjacent runtimes and commands using backend evidence, not UI state.

## Phase P14 — P2-0 Adjacent runtime and command qualification

### Objective

Use explicit QUALIFICATION mode to prove the generic workflow across every officially allowed adjacent runtime bridge, review/promote immutable evidence to certification, and then make those exact profiles eligible for later PRODUCTION execution without hard-coded paths or major branches.

### Why

Unit fixtures cannot prove legacy CLI escape behavior, npm-version peer semantics, installed migration metadata, filesystem residue, or clean reproducibility.

### Preconditions

P00-P13 complete, including terminal P06-A basic owner discovery and P06-B packageGroup/requirements traversal, optional metadata, ordering, and dependency rules; official compatibility envelopes exist; approved local paired runtime inventory, per-row qualification authorization, required fixture snapshots, and registry access are available. Exact profiles may be uncertified—that is the purpose of this phase—but unsupported profiles are ineligible.

### Existing code to REUSE unchanged

- [REUSE] runtime resolver/binding services and approved local paired-runtime inventory; qualification mode does not require that an allowed tuple is already certified.
- [REUSE] P01 mode, qualification authorization/evidence/review/promotion contracts and existing artifact/audit/certification persistence.
- [REUSE] command worker/sandbox, evidence/artifact persistence, stage checkpoints, and proven graph.
- [REUSE] existing adjacent-stage/runtime integration harness patterns.

### Existing code to UPDATE

- [UPDATE] `backend/tests/test_runtime_resolver_authority_f01.py`, `backend/tests/test_runtime_execution_domain_f01.py`, `backend/tests/test_stage_runtime_f02.py`, and `backend/tests/test_runtime_certification_f11.py` — governed selection, binding, executable provenance, and missing-runtime block.
- [UPDATE] `backend/app/domain/runtime_certification.py:26-118` and `backend/app/services/runtime_certification_service.py:32-166` — exercise allowed uncertified tuples only in qualification mode and deterministically promote reviewed complete evidence.
- [UPDATE] `backend/tests/test_compatibility_catalogue_provider.py` and `backend/tests/test_planning_application_service_s2_f06_i01.py` — catalogue-driven 11→12 through 20→21 fixture rows without executable branches.
- [UPDATE] `backend/app/runtime_profiles/README.md` and `docs/capabilities/01-command-runtime/README.md` — required local/CI runtime inventory and evidence retention.

### New files to ADD

- [ADD] `backend/tests/test_proven_transformer_runtime.py` — opt-in real-runtime matrix; one file covers all adjacent rows.

### Files explicitly NOT to touch

Production special cases, fixed machine paths, auto-install behavior, DB schema, or package-lock/shrinkwrap fixtures hand-edited to pass.

### Data/contracts

Each matrix row records mode, qualification authorization actor/purpose/checksum, source/target exacts, catalogue checksum, selected Node/npm/npx absolute paths/versions/checksums, the exact-version `LockfileAuthorityPolicy` checksum and peer/optional/dev capability fields, discovery and migration CLI authorities, governed PATH/child npm proof, immutable section-aware `DependencyIntent` (dependencies, devDependencies, optionalDependencies, peerDependencies, peerDependenciesMeta) and checksum, selected lock filename/kind/raw SHA/schema/canonical resolved-state/root-sync classifications by section/kind/absence and transitions, npm-ci/npm-ls same-authority proof, compiler/RxJS/Zone proofs, TargetIntent, LockResolution, MigrationLedger, ValidationSummary, normal G09→promotion→G12 or repaired G11→G09→promotion→G12, seal, reviewer/promotion decision, certification artifact checksum, and outcome. Sanitized evidence retains executable identity/checksum while credentials are excluded.

### Workflow transitions

For each adjacent pair: create immutable QUALIFICATION plan/authorization → resolve officially allowed inventory tuple → run P03-P08; on failure run P09-P12 → seal qualification generation → build/review evidence → deterministic certification promotion → feed exact qualification seal to the next qualification row. Missing inventory yields BLOCKED_RUNTIME evidence; unsupported envelope or missing authorization blocks before execution. Certification is never inferred from the seal alone.

### Command templates

Use the production command catalogue and explicit qualification mode. Test runner selects rows by official catalogue envelope/environment inventory and invokes the same authority-bound templates; it must not duplicate npm/ng command strings or use npx package selection as CLI proof.

### Failure/recovery behavior

Missing runtime/registry or authorization is an explicit blocked qualification with evidence, never a pass. Descriptor/toolchain/PATH/checksum drift invalidates the row and its promotion eligibility. Incomplete, failed, or unreviewed evidence remains observed/allowed only. Residue uses platform recovery and a new generation. A failed row stops downstream qualification because N+1 lacks sealed authority. No installer, `--force`, or `--legacy-peer-deps` escape.

### Implementation steps

1. Enumerate adjacent rows from official compatibility catalogue data.
2. Resolve approved paired local inventory without requiring prior exact certification; reject outside-envelope tuples.
3. Create explicit per-row qualification authorization recording actor/purpose/descriptors/catalogue/expiry.
4. Run each qualification row sequentially from the preceding qualification seal using exact discovery/migration CLI authorities.
5. Assert section-aware `DependencyIntent` (including `peerDependenciesMeta`), bound-npm `LockfileAuthorityPolicy` selection, V1/V2/V3 resolved-state/root-sync classifications (including deferred npm-spec/peer/optional proof), Factory/npm-ci/npm-ls authority equality, command, gate-order, and all evidence contracts.
6. Exercise preserve-lock and classified-fresh-lock paths with generic fixtures where naturally triggered or controlled; prove required/dev missing can fail, while optional/optional-peer omission and npm6 peer absence never authorize deletion, and npm7+ peer conflicts route to npm dependency solving.
7. Freeze the complete evidence bundle and require explicit review.
8. Run deterministic evidence promotion; confirm the exact profile becomes certified only afterward.
9. Archive checksums/logs and produce qualification and certification matrix summaries.

### Tests to ADD/UPDATE

- [ADD] `backend/tests/test_proven_transformer_runtime.py` with adjacent matrix and runtime marker.
- [UPDATE] `backend/tests/test_runtime_resolver_authority_f01.py`, `backend/tests/test_runtime_execution_domain_f01.py`, `backend/tests/test_stage_runtime_f02.py`, and `backend/tests/test_runtime_certification_f11.py` for provenance and missing-runtime block.
- [UPDATE] integration suite for generic fixture-controlled alternate paths.
- [UPDATE] runtime certification cases for production rejection before promotion, qualification authorization, incomplete evidence, explicit review, and post-promotion production eligibility.
- [UPDATE] runtime matrix cases for npm 6–11 package-lock/shrinkwrap precedence, npm 12+ unsupported-shrinkwrap policy, malformed authoritative shrinkwrap, deferred npm-spec proof, policy-gated shrinkwrap fallback, npm6 peer absence/presence semantics, modern npm peer graph behavior, required/dev materialization, optional omission, optional-peer omission, compatible peer, and peer conflict.
- Regression rule: all rows use the same semantic graph and command catalogue.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests/test_runtime_resolver_authority_f01.py tests/test_runtime_execution_domain_f01.py tests/test_proven_transformer_integration.py
.\.venv\Scripts\python.exe -m pytest -q -m runtime tests/test_proven_transformer_runtime.py
Pop-Location
```

Before implementation, confirm actual marker and test filenames with `rg --files backend/tests | rg "runtime|binding|resolver"`; amend command names to repository truth rather than inventing aliases.

### Runtime validation

Fixture: authoritative sealed Angular 11 start plus catalogue-driven adjacent targets and generic dependency-section fixtures. Runtime: each officially allowed, explicitly authorized local binding in QUALIFICATION mode. Evidence: the full row contract above. Pass when all ten qualification rows select the same authority npm consumes, prove section-aware `DependencyIntent` against canonical resolved state, demonstrate npm6 peer absence is not treated as npm7 auto-install behavior, demonstrate modern npm peer solving, prove required/dev/optional/optional-peer semantics through governed npm-ci/npm-ls, seal sequentially, every evidence bundle is explicitly reviewed/deterministically promoted, and the exact ten profiles then appear certified for PRODUCTION. Inspect the first authority/root-sync/unauthorized/unsealed/unreviewed/unpromoted row; never run downstream rows independently as journey proof.

### Acceptance criteria

- [ ] One generic graph qualifies 11→12 through 20→21.
- [ ] PRODUCTION cannot execute an uncertified row; QUALIFICATION can exercise it only inside the official envelope with explicit authorization.
- [ ] Qualification success/seal does not auto-certify; immutable evidence, explicit review, and deterministic promotion are required.
- [ ] Every command uses its governed runtime binding and exact target workspace CLI where required.
- [ ] Discovery requested CLI equals actual absolute authority and child npm; migrate-only uses exact materialized target CLI.
- [ ] V1/V2/V3 lock evidence and any schema transition are captured.
- [ ] Each row binds package.json root intent, bound-npm lock policy/authority, canonical resolved state, root-sync classification (including any `DEFER_TO_NPM` proof), and npm-ci same-authority proof.
- [ ] Each row preserves section-aware `DependencyIntent` and `peerDependenciesMeta` through root-sync; no flattened map is semantic authority.
- [ ] Required and dev dependencies must materialize under the governed migration install mode; optional and optional-peer absence is allowed only under recorded npm/platform semantics.
- [ ] npm 3–6 peer absence is not treated as npm 7+ behavior; modern peer conflicts are decided by bound npm solve/ci/ls evidence, not Python.
- [ ] Optional/peer absence cannot by itself authorize fresh-lock deletion.
- [ ] Authoritative shrinkwrap cannot fall through or be replaced without explicit dependency-policy authority; npm 12+ unsupported shrinkwrap is explicit.
- [ ] Missing runtime is blocked, not silently substituted or installed.
- [ ] npm/CLI behavior is proven by evidence, not assumed by exit status.
- [ ] Each seal is the sole input authority for the next row.

### Completion evidence

Ten-row qualification matrix, authorization/evidence/review/promotion checksums, resulting certified-profile matrix, blocked-inventory report if any, and sequential qualification sealed-fingerprint chain.

### Rollback/recovery notes

Qualification creates disposable/test journey data only. Retain failed-row evidence, correct catalogue/runtime/platform ownership, and resume that row.

### Agent handoff

P15 performs a fresh PRODUCTION full-quality/E2E run using only profiles certified by P14; it cannot reuse qualification authorization as production authority or waive a blocked row.

## Phase P15 — P2-1 Final 11→21 E2E, documentation, and legacy deprecation

### Objective

Run the complete quality gate and real sequential journey, document operator/recovery behavior, and deprecate combined authoritative update for new proven plans without deleting historical replay support.

### Why

The upgrade is complete only when it proves the full chain, preserves governance/backward compatibility, and gives operators a precise recovery/deprecation contract.

### Preconditions

P00-P14 complete; P06-A/P06-B migration metadata traversal is terminal; P12 `.\.venv\Scripts\python.exe -m pytest --collect-only -q` succeeds with `test_transformer_stage_runtime_integration.py` included; all P0/P1 tests pass; all ten exact profiles have reviewed immutable evidence and certified status; no runtime row is blocked; section-aware `DependencyIntent`/npm capability semantics and root-sync evidence are proven; baseline deltas are reconciled rather than silently ignored.

### Existing code to REUSE unchanged

- [REUSE] existing README architecture/evidence sections, production readiness/checklist conventions, audit events, and legacy plan replay.
- [REUSE] existing backend/frontend lint, typecheck, unit, integration, and build scripts.

### Existing code to UPDATE

- [UPDATE] `README.md` — proven graph entry point, operator evidence, recovery, and deprecation notice.
- [UPDATE] `TRANSFORMER_PRODUCTION_IMPLEMENTATION_PLAN.md` — point to completed proven-plan semantics and retain its historical architecture distinctions.
- [UPDATE] `backend/app/runtime_profiles/README.md` and `docs/capabilities/01-command-runtime/README.md` — governed runtime and command evidence requirements; V2-V6 combined updater commands are legacy replay-compatible, not authoritative for new proven plans.
- [UPDATE] all affected test expectations after full-suite reconciliation.

### New files to ADD

NONE.

### Files explicitly NOT to touch

DB migrations, removal of legacy command types/readers, version-specific production branches, fixture-only bypass flags.

### Data/contracts

Release evidence bundle contains commit SHA, plan semantic version, catalogue/command/knowledge checksums, successful full collection manifest, unexcluded baseline/final test summaries, per-row immutable section-aware `DependencyIntent`/`peerDependenciesMeta` checksum, exact npm capability/policy checksum, selected lock filename/kind/raw/schema/canonical root-sync/absence/deferred evidence, npm-ci/npm-ls proof, ten-row runtime matrix, sequential fingerprint chain, open-risk decisions, and deprecation statement.

### Workflow transitions

Clean source stage 11 → PRODUCTION mode verifies exact certification per row → ten adjacent proven stages with authority-bound discovery/migration CLI, section-aware `DependencyIntent`, exact bound-npm capability/lock authority, and canonical resolved-state/root-sync proof → exact target 21 seal → journey completion. Any missing certification, authority mismatch, section/policy mismatch, or failure blocks/returns to its persisted P09 owner; production never switches to qualification and release readiness remains false.

### Command templates

Production E2E uses the command catalogue. Quality commands are below. Legacy combined update remains renderable only for historical plans; new proven plan creation never selects it as authoritative mutation.

### Failure/recovery behavior

Do not bless known baseline failures automatically. Classify each as pre-existing harness debt, fixed regression, or explicit release blocker with owner/evidence. Full E2E resumes at the first unsealed stage. Documentation cannot substitute for missing runtime proof.

### Implementation steps

1. Verify P12 full collection succeeds and the former runtime-integration collector is included.
2. Run focused P00-P14 suites and reconcile failures.
3. Run the full backend suite without exclusions plus frontend quality gates.
4. Run the sequential 11→21 runtime journey from clean starting authority.
5. Verify every production runtime certification, CLI authority, section-aware `DependencyIntent`/`peerDependenciesMeta`, exact npm capability policy, manifest/selected-lock/root-sync/absence/deferred npm/npm-ci/npm-ls proof, lock schema transition, gate chain, release evidence checksum, and fingerprint link.
6. Update operator/recovery/evidence documentation.
7. Mark combined authoritative updater deprecated for new proven plans while retaining legacy replay.
8. Review every section 23 acceptance item and record final decision.

### Tests to ADD/UPDATE

- [UPDATE] any affected existing tests only where the new semantic-version behavior intentionally changes assertions.
- [UPDATE] `backend/tests/test_proven_transformer_integration.py` and `backend/tests/test_proven_transformer_runtime.py` final journey cases.
- Full regression: plain backend suite with no ignored/excluded collector, frontend test/typecheck/build, lint, migration check, runtime matrix.
- Regression rule: no ignored failure without a persisted owner and release decision.

### Commands to run

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q -m runtime tests/test_proven_transformer_runtime.py
Pop-Location
Push-Location frontend
npm test -- --run
npm run typecheck
npm run build
Pop-Location
git diff --check
```

### Runtime validation

Fixture: clean authoritative Angular 11/npm6 V1 project plus approved baseline evidence and generic required/dev/optional/peer/optional-peer fixtures. Runtime: all P14-certified bridges in PRODUCTION mode. Evidence: certification decisions, discovery/migration CLI authorities, section-aware `DependencyIntent`/`peerDependenciesMeta`, exact npm `LockfileAuthorityPolicy`, npm-selected lock filename/kind and canonical section-aware root-sync/absence/deferred/npm-ci/npm-ls evidence, schema transitions, ordered gates, successful full collection/suite output, release bundle, and ten linked seals. Pass only when no qualification authorization is used, Factory and npm consume the same authority, Angular 21 is exact, final generation is validated/G09-approved/promoted/G12-approved/sealed, and every predecessor fingerprint links. Inspect the earliest collection/certification/authority/root-sync/lock/gate/fingerprint divergence.

### Acceptance criteria

- [ ] All section 23 checks pass or release is blocked.
- [ ] Full backend/frontend quality gates pass with reconciled baseline.
- [ ] Full backend pytest collection succeeds and the plain full-suite run excludes no test file.
- [ ] Ten adjacent stages form one sealed fingerprint chain.
- [ ] The final journey is PRODUCTION mode and every row rejects an uncertified or identity-drifted runtime/toolchain.
- [ ] Normal rows use G09→promotion→G12; repaired rows use G11→G09→promotion→G12; both seal only afterward.
- [ ] Documentation matches executable code truth and recovery behavior.
- [ ] Legacy combined authoritative update is deprecated for new plans but remains replayable.
- [ ] Final production evidence preserves section-aware `DependencyIntent` and exact npm capability policy at every stage; npm6 peer absence is not treated as npm7 behavior, optional/optional-peer omission is not a mismatch by itself, and peer conflicts are npm dependency evidence.

### Completion evidence

Release bundle, full command outputs, runtime matrix, fingerprint chain, documentation diff, deprecation proof, final architectural approval.

### Rollback/recovery notes

Disable creation of the proven semantic version while retaining all readers and persisted stages. Resume existing proven stages only when their versioned recovery contract is supported; never translate them silently to legacy semantics.

### Agent handoff

Implementation is release-ready only after the Completion Definition in section 27 is signed with this evidence.

## 20. Test strategy

### Level 1 — deterministic unit tests

Pure tests cover PRODUCTION/QUALIFICATION authorization and certification promotion, `AngularCliToolchainAuthority` containment/integrity/requested=actual checks, governed PATH/child npm, npm-version-aware `LockfileAuthorityPolicy` precedence and peer/optional/dev capability behavior, section-preserving `DependencyIntent`/`DependencyIntentKind` including `peerDependenciesMeta`, malformed-selected-authority behavior, `PackageLockReader` V1/V2/V3 resolved versions/nested requested edges/integrity/root-sync classifications, explicit `DEFER_TO_NPM` handling, TargetIntent parsing/completeness, lock failure classification/convergence/schema transition/policy-gated shrinkwrap fallback, P06-A/P06-B installed metadata traversal and ordering, MigrationLedger, diagnostic delta, ordered gate/fingerprint guards, and failure routing. They use synthetic packages/capabilities rather than named manual incidents. Every phase records baseline expected, new expected, and a regression rule.

### Level 2 — Transformer integration tests

`[ADD] backend/tests/test_proven_transformer_integration.py` is the single cross-service suite. It drives the versioned plan through the real DB repositories, continuation processing, structured command queue, artifact binding, workspace generations, gates, repair candidates, restart/recovery, promotion, seal, and next-stage creation. Existing service-owned suites remain `[UPDATE]`; do not duplicate their unit coverage in the integration file.

Required integration scenarios:

1. Happy adjacent stage through seal and N+1 handoff.
2. Production rejects uncertified runtime; qualification requires matching authorization and cannot auto-certify.
3. Discovery CLI requested/actual equality, governed child npm, nonzero COMPLETE intent, and incomplete intent.
4. npm 6–11 and npm 12+ lock-policy selection, package-lock-only/shrinkwrap-only/both/neither cases, malformed authoritative shrinkwrap without fallback, section-aware `DependencyIntent`/`peerDependenciesMeta`, required/dev/optional/optional-peer/peer root-sync classifications, npm6 peer absence, npm7+ peer solver outcomes, V1/V2/V3 resolved-state/root-sync classifications including deferred specs, V1→later evidence, preserve-lock success, package-lock fallback, policy-gated shrinkwrap fallback, non-convergence, and clean npm-ci/npm-ls authority/reproducibility rejection.
5. P06-A/P06-B required/optional migration ledger with packageGroup/requirements traversal, deterministic ordering/dependencies, exact target CLI authority, and dependency-authority unchanged/changed.
6. New versus pre-existing diagnostic.
7. Every failure owner, especially platform categories excluded from source LLM.
8. Normal G09→promotion→G12 and repaired G11→G09→promotion→G12, including failure at each boundary.
9. Failed/accepted repair candidate authority isolation.
10. Crash/resume at every mutating boundary.
11. `test_transformer_stage_runtime_integration.py` collects and runs through the public final reconstruction API; full collection has no import error or excluded file.

### Level 3 — governed real-runtime tests

`[ADD] backend/tests/test_proven_transformer_runtime.py` first executes explicitly authorized QUALIFICATION rows to produce reviewed certification evidence, then the final suite executes a fresh PRODUCTION chain using those certifications. It runs actual npm/Angular commands through the production worker and exact CLI authorities. Mocks are insufficient for CLI ownership/child npm, updater behavior, npm-version-aware lock precedence and capability policy, npm6 V1 intent-versus-resolution/schema transition and non-installed peer semantics, modern npm peer graph solving, required/dev materialization, optional/optional-peer omission, compatible peer, peer conflict, selected-authority convergence/clean npm-ci/npm-ls/tree, deferred npm-spec semantic proof, installed migration metadata including packageGroup/requirements traversal, target-CLI migrate-only, ordered gates, build/test, promotion, or seal. It never auto-installs a runtime: unavailable inventory is explicit BLOCKED evidence and a release blocker.

### Baseline and regression accounting

The P00 baseline is immutable evidence, not a waiver. Its `--continue-on-collection-errors` diagnostic capture does not authorize an excluded-file regression run. P12 must restore clean collection, after which every implementation run emits `PRE_EXISTING_BASELINE`, `FIXED_BASELINE`, and `NEW_REGRESSION` from the full unexcluded suite. Any failure not signature-matched to the frozen baseline is new; a changed signature requires review rather than automatic grandfathering.

## 21. Runtime qualification matrix

Rows are data selected from official compatibility envelopes plus approved local paired-runtime inventory. Stage number is matrix input only; algorithms consume constraints, mode, authorization, installed metadata, and evidence. Each row has two separate outcomes: QUALIFICATION proves/promotes an exact profile; the final P15 PRODUCTION run proves that only the promoted certification is accepted.

| Adjacent stage | QUALIFICATION input | Certification result | Required later PRODUCTION result |
|---|---|---|---|
| 11→12 | Allowed envelope ∩ approved inventory + explicit authorization; npm6/V1 fixture | Reviewed complete evidence deterministically promotes exact tuple | Certified tuple only; exact 12 sealed and feeds 12→13 |
| 12→13 | Same generic qualification resolver/authorization | Same evidence review/promotion | Certified tuple only; exact 13 sealed; linked predecessor |
| 13→14 | Same generic qualification resolver/authorization | Same evidence review/promotion | Certified tuple only; exact 14 sealed; linked predecessor |
| 14→15 | Same generic qualification resolver/authorization | Same evidence review/promotion | Certified tuple only; exact 15 sealed; linked predecessor |
| 15→16 | Same generic qualification resolver/authorization | Same evidence review/promotion | Certified tuple only; exact 16 sealed; linked predecessor |
| 16→17 | Same generic qualification resolver/authorization | Same evidence review/promotion | Certified tuple only; exact 17 sealed; linked predecessor |
| 17→18 | Same generic qualification resolver/authorization | Same evidence review/promotion | Certified tuple only; exact 18 sealed; linked predecessor |
| 18→19 | Same generic qualification resolver/authorization | Same evidence review/promotion | Certified tuple only; exact 19 sealed; linked predecessor |
| 19→20 | Same generic qualification resolver/authorization | Same evidence review/promotion | Certified tuple only; exact 20 sealed; linked predecessor |
| 20→21 | Same generic qualification resolver/authorization | Same evidence review/promotion | Certified tuple only; exact 21 sealed; journey complete |

Every row persists:

- run mode, qualification authorization actor/purpose/checksum, evidence reviewer/promotion decision, and final certification checksum;
- exact executable paths/checksums and `node --version`, `npm --version`, `npx --version`;
- discovery and migration strategy/version, absolute CLI entrypoint/package integrity, requested/installed/actual CLI equality, governed PATH/environment checksum, and child-visible npm identity;
- exact Angular Core, Angular CLI, TypeScript, RxJS, and Zone proofs;
- package.json checksum plus immutable section-aware `DependencyIntent`/`peerDependenciesMeta` checksum and root-declaration intent; exact npm capability/policy checksum; selected lock filename/kind/raw SHA/version, canonical resolved dependency-set and per-section/kind/absence root-sync checksum, V1→later schema-transition evidence where applicable, npm-ci/npm-ls same-authority proof, and workspace fingerprint;
- source BaselineProof, TargetIntent, bound npm exact version/`LockfileAuthorityPolicy`, chosen lock strategy/attempts/convergence, clean npm-ci, npm-ls result, and root-sync spec classifications;
- MigrationLedger with P06-A/P06-B owner/traversal decisions/results, packageGroup/requirements ordering/dependencies, dependency-authority comparison, build/test outputs, DiagnosticDelta, ValidationSummary, normal G09→promotion→G12 or repaired G11→G09→promotion→G12, and seal.

If an approved runtime is absent, outside the official envelope, or lacks explicit qualification authorization, record constraints/inventory and BLOCK; do not use PATH fallback or install a runtime. A lone `yarn.lock` in an npm-governed row blocks under package-manager policy. Under npm 6–11, malformed authoritative shrinkwrap blocks without package-lock fallback; under npm 12+, shrinkwrap is unsupported and requires explicit migration/removal policy. Required/dev entries must materialize under the governed install mode; optional and optional-peer omission is allowed only with recorded npm/platform evidence; npm6 peer absence is not an ordinary missing dependency, and npm7+ peer conflicts require governed npm solver/tree evidence. Passing qualification evidence remains uncertified until explicit review and deterministic promotion. Each qualification row begins only from the previous qualification seal; the separate P15 production chain begins from clean Angular 11 and uses only certified profiles.

## 22. Final 11→21 E2E procedure

1. Pin release commit, PRODUCTION mode, proven plan version, catalogue, ten reviewed certification decision checksums, command catalogue, and Stage Knowledge checksums.
2. Import/create the clean authoritative Angular 11 source and prove its current seal/fingerprint.
3. Resolve the 11→12 exact certified bridge runtime; reject allowed-only or identity-drifted tuples.
4. Execute P03 section-aware package.json `DependencyIntent` plus bound-npm capability/lock-policy/canonical V1 proof, P04 absolute discovery CLI/child-npm authority and disposable discovery, P05 selected-lock/section-aware root-sync/schema-transition/npm-ci/npm-ls proof (including any `DEFER_TO_NPM` semantic checks), P06-A/P06-B exact target CLI materialization and complete migration metadata traversal, P07 fresh validation, and the correct P08 gate/promotion/seal order.
5. If any node fails, persist P09 ownership; use platform/runtime/dependency/lock recovery or P10/P11 isolated repair as selected. Revalidate before promotion.
6. Assert sealed target fingerprint is the next stage's source fingerprint.
7. Repeat steps 3-6 for every adjacent row through 20→21; never skip a major or seed a later row independently.
8. At every row verify production certification, requested=actual CLI authority, governed PATH/child npm, section-aware `DependencyIntent`/`peerDependenciesMeta`, bound npm exact capability/policy, selected filename/kind/checksum, resolved reader/root-sync/absence/deferred/schema/npm-ci/npm-ls evidence, section 21 bundle, and no prohibited command option.
9. At final seal, prove exact target 21 cohort, complete the journey through the existing completion service, and verify all ten predecessor links.
10. Run the complete P15 quality commands with no excluded test file and archive the release evidence bundle. Any collection error, qualification-mode fallback, uncertified/unavailable runtime, CLI authority mismatch, unsupported or wrong-precedence lock authority, incomplete evidence, unresolved regression, out-of-order/missing gate, or fingerprint mismatch means NOT READY.

## 23. Consolidated acceptance checklist

- [ ] New plans do not use combined `ng update` as authoritative mutation.
- [ ] Every updater target discovery runs in a disposable generation.
- [ ] Discovery process exit and discovery completeness are separate.
- [ ] Nonzero discovery exit may continue only when deterministic evidence proves TargetIntent complete and accepted.
- [ ] Incomplete discovery cannot mutate the authoritative generation.
- [ ] Every adjacent stage begins from the previously sealed generation.
- [ ] Every stage resolves a governed runtime and persists executable provenance/checksum.
- [ ] Production cannot execute with an uncertified runtime; allowed-but-uncertified blocks with `STAGE_RUNTIME_CERTIFICATION_REQUIRED`.
- [ ] Qualification can exercise an officially allowed uncertified runtime only under explicit checksum-bound qualification authority.
- [ ] Qualification never bypasses official compatibility constraints and never auto-promotes certification.
- [ ] Immutable complete qualification evidence, explicit review, and deterministic promotion are required before certified status.
- [ ] Discovery does not assume npx package selection proves CLI ownership.
- [ ] Exact requested/installed/actual executing Angular CLI identity and absolute entrypoint/package integrity are evidence-bound.
- [ ] Governed PATH/environment makes child npm/npm identity equal the bound descriptor.
- [ ] CLI entrypoint/version/checksum/PATH/child-npm mismatch blocks: preflight drift before command, discovery-time delegation before TargetIntent, and migration drift before migrate-only.
- [ ] No command uses `--force`.
- [ ] No command uses `--legacy-peer-deps`.
- [ ] Source baseline proves `npm ci`, `npm ls --all --json`, exact source cohort, build, tests, and baseline diagnostics.
- [ ] Angular 11/npm6 `lockfileVersion: 1` is supported.
- [ ] package.json is authoritative for root requested dependency intent.
- [ ] package.json `dependencies`, `devDependencies`, `optionalDependencies`, `peerDependencies`, and `peerDependenciesMeta` remain distinct through `DependencyIntent` and root-sync; no flattened map is semantic authority.
- [ ] `peerDependenciesMeta[package].optional == true` classifies that peer as `OPTIONAL_PEER` and is preserved/evaluated.
- [ ] Required dependencies and devDependencies require valid materialization under the governed migration install mode.
- [ ] Optional dependency absence is not automatically a mismatch and never synthesizes a lock entry.
- [ ] Optional peer absence is explicitly allowed; present optional peers are compatibility-checked.
- [ ] npm 3–6 peer absence is not treated as npm7+ missing-dependency behavior.
- [ ] npm 7+ peer behavior is evaluated through the exact bound npm capability and governed npm solve/npm-ci/npm-ls evidence.
- [ ] Python does not become a peer or optional dependency solver.
- [ ] Peer conflicts route to dependency planning/npm solver ownership.
- [ ] Optional or peer absence cannot by itself authorize fresh-lock deletion.
- [ ] The npm capability policy is checksum-bound and survives restart without ambient-version reinterpretation.
- [ ] Final validation proves section-aware intent against same-authority npm-ci/npm-ls evidence.
- [ ] A V1 lock is never treated as the source of original root dependency ranges.
- [ ] V1/V2/V3 share one canonical resolved-state `PackageLockReader` contract.
- [ ] Root-sync uses only a bounded static check: safe specs become `VERIFIED`/`MISMATCH`; unsupported or complex npm specs become `DEFER_TO_NPM` and are never guessed by Python.
- [ ] Every root-sync finding records the `STATIC_CHECK` capability/result and its deterministic successor or deferred npm evidence.
- [ ] Every `DEFER_TO_NPM` result is backed by governed npm solve and clean `npm ci` semantic evidence.
- [ ] No Transformer service assumes `packages[""]` exists.
- [ ] Unsupported/malformed lock JSON or shape fails with an explicit code.
- [ ] The bound exact npm version selects one `LockfileAuthorityPolicy`: npm 6–11 use shrinkwrap before package-lock; npm 12+ use package-lock with explicit unsupported-shrinkwrap policy.
- [ ] Factory lock evidence and npm-ci operate against the same selected filename/kind/checksum.
- [ ] A malformed authoritative shrinkwrap cannot silently fall back to package-lock.
- [ ] Shrinkwrap deletion or replacement requires an explicit checksum-bound dependency-policy decision.
- [ ] V1→V2/V3 solver transitions are immutable evidence, not silent normalization.
- [ ] Lock strategy attempts preserve-first.
- [ ] Fresh-lock fallback is failure-classified and bounded.
- [ ] Lock convergence requires two consecutive matching SHA256 values.
- [ ] Lock convergence has a finite configured maximum.
- [ ] A converged lock passes clean `npm ci` in a fresh generation.
- [ ] Target dependency tree passes `npm ls --all --json` semantic validation.
- [ ] Exact installed target Angular/CLI/TypeScript/RxJS/Zone matches frozen stage authority.
- [ ] Migrate-only owners are discovered from installed ng-update metadata rather than a Core-only hard-coded plan.
- [ ] P06-A basic installed migration-owner discovery is complete for every changed direct package.
- [ ] P06-B packageGroup/requirements traversal, optional migration metadata, ordering, and dependency rules are implemented and terminal before P07/P14.
- [ ] No supported packageGroup/requirements migration is silently omitted.
- [ ] Required migrations run exactly once through exact target workspace CLI.
- [ ] Migration uses the exact checksummed absolute CLI authority installed in the materialized target generation, not generic npx/PATH lookup.
- [ ] Optional migrations receive explicit RUN/SKIP/PENDING policy; PENDING cannot pass.
- [ ] Dependency reconciliation after migrations occurs only if package.json or selected lock authority changed.
- [ ] Package.json and selected shrinkwrap-or-package-lock authority are checksummed/frozen before validation.
- [ ] Fresh validation never inherits `node_modules`, `dist`, or `.angular`.
- [ ] Validation reruns clean `npm ci`, dependency tree, exact target proof, build, and tests.
- [ ] Build/test diagnostics compare against the approved source baseline.
- [ ] PRE_EXISTING, NEW, RESOLVED, and CHANGED diagnostics are distinguishable.
- [ ] HARNESS faults cannot reach application repair LLM.
- [ ] RUNTIME faults cannot reach application repair LLM.
- [ ] LOCKFILE faults cannot reach application repair LLM.
- [ ] DEPENDENCY faults route to compatibility planning/npm solving, not source LLM.
- [ ] Dependency transitive solving remains npm-owned; legitimate multiple transitive versions are not normalized away.
- [ ] Main Repair LLM receives one bounded ProblemGroup plus exact current candidate files/evidence/stage context.
- [ ] Repair LLM cannot execute commands.
- [ ] Repair LLM cannot choose runtime.
- [ ] Repair LLM cannot directly modify package-lock or npm-shrinkwrap.
- [ ] Repair LLM cannot fabricate preimages.
- [ ] Reviewer returns ACCEPT/REQUEST_CHANGES/REJECT/INSUFFICIENT_CONTEXT and cannot author a replacement patch.
- [ ] Existing human and governance gates remain intact.
- [ ] Repair operates only on an isolated candidate.
- [ ] Failed repair cannot mutate active authority.
- [ ] Candidate receives the same full clean validation as the normal path.
- [ ] Normal validation uses G09 approval before promotion.
- [ ] Repaired validation uses G11 then G09 approval before promotion.
- [ ] G12 occurs only after the correct validated generation is promoted and active.
- [ ] Validated fingerprint equals G11 when repaired, G09 approved workspace, promoted/active fingerprint, and sealed source fingerprint.
- [ ] N sealed output becomes N+1 source.
- [ ] Restart/recovery works from DB plus immutable artifacts, not assumptions about a surviving live directory.
- [ ] Historical plan/template/repair compatibility remains supported.
- [ ] Existing updater V2-V6 commands remain replayable but are deprecated for new authoritative proven plans.
- [ ] Runtime validation exists and passes for every adjacent stage 11→12 through 20→21.
- [ ] Full backend pytest collection succeeds before final E2E, including `test_transformer_stage_runtime_integration.py`.
- [ ] No backend test file is excluded from the P15 regression run; remaining failures, if any, are test failures rather than collection/import errors.
- [ ] P12/P15 pytest commands invoke `.\.venv\Scripts\python.exe` from the backend checkout; ambient `python` is never used for final acceptance.
- [ ] Full Angular 11→21 sequential fixture completes stage → validate → promote → seal → next stage.
- [ ] stderr alone never determines command failure; exit code is process authority and semantic validators determine node success.
- [ ] Exit code zero alone never determines discovery, lock, dependency, validation, promotion, or seal success.
- [ ] Promoted generation is the exact generation that passed validation and the path-correct pre-promotion gates; G12 then approves that active generation for sealing.
- [ ] No new DB table, orchestration framework, command executor, runtime resolver, artifact store, or gate system was introduced without new code-truth proof.

## 24. Risks

| Rank | Risk | Consequence | Mitigation/evidence |
|---:|---|---|---|
| 1 | Compatibility catalogue supported ranges and certified exact runtime evidence currently disagree | Wrong bridge runtime or blocked valid stage | P01 reconciliation, provenance/checksum, fail closed before plan creation |
| 2 | Current graph assumes updater mutation in active stage workspace | Authority corruption or mixed old/new semantics | P02 version gate; P04 disposable binding; legacy branch retained |
| 3 | npm/CLI behavior varies by installed versions and may exit successfully with semantically invalid state | False lock/discovery success | Structured evidence, bounded convergence, clean npm-ci/tree/exact proof, P14 real runtimes |
| 4 | Repair/recovery paths currently have broad lineage and shared-state test failures | Candidate leakage, duplicate work, or authority mutation | P10 candidate-root guard, P12 idempotency matrix, fingerprint equality gates |
| 5 | Installed ng-update metadata formats/ownership can vary | Missing/duplicate migrations | Defensive generic parser, raw metadata artifact, required/optional policy, exact-once ledger tests |
| 6 | Existing suite has substantial pre-existing persistence/harness failures | Regressions hidden in baseline noise | Frozen signatures, focused tests, PRE_EXISTING/FIXED/NEW accounting, final reconciliation |
| 7 | Windows residue/EPERM can survive a nominally successful command | Dirty false-positive validation | new-generation reconstruction, inventory assertions, PLATFORM_RECOVERY routing |
| 8 | Backward compatibility could accidentally reinterpret persisted stages | Unrecoverable in-flight journeys | semantic version, additive readers, legacy command retention, mixed-version recovery tests |
| 9 | `npx --package` or ambient PATH selects a different CLI/npm than requested | Discovery/migration executed by ungoverned toolchain | Absolute CLI entrypoint/integrity, actual-version proof, exact PATH/child npm, block on mismatch |
| 10 | V1 resolved tree is mistaken for original root requested ranges | Angular 11 intent/root-sync proof is false | package.json-owned root intent plus one V1/V2/V3 resolved-state reader |
| 11 | Qualification success is mistaken for certification or gate order drifts | Uncertified production execution or unapproved promotion | Explicit mode/authorization/review/promotion and binary G11/G09/promotion/G12 tests |
| 12 | Factory lock precedence is not bound to the exact npm capability | Factory and npm consume different authorities or npm 12 silently ignores shrinkwrap | One npm-version-aware `LockfileAuthorityPolicy`, same-authority npm-ci proof, explicit unsupported-shrinkwrap policy, and no malformed-authority fallback |
| 13 | Stale runtime integration import remains a collection error | P15 cannot establish full regression status | P12 owns public-API test adaptation and requires successful full `--collect-only` |
| 14 | Complex npm package specs are guessed by Python | False root-sync success or rejection | Bounded static checks plus `DEFER_TO_NPM`; governed solve/clean-ci evidence is semantic authority |
| 15 | packageGroup/requirements traversal remains deferred after basic owner discovery | Required migrations are silently omitted | P06-B is an explicit implementation/acceptance gate before P07 and P14 |
| 16 | npm generations differ in peer installation and optional omission semantics | False manifest/lock mismatch, unnecessary lock deletion, or invalid stage block | Section-aware `DependencyIntent` plus exact npm capability policy, `DEFER_TO_NPM`, and clean same-authority npm-ci/npm-ls proof |

## 25. Explicit non-goals

- No worktrees, branches, commits, pushes, or implementation during this planning task.
- No unrelated frontend redesign; P13 is projection-only.
- No new DB tables/columns: existing JSON/artifact/generation/checkpoint records are sufficient unless implementation discovers contrary code truth and stops for approval.
- No replacement of LangGraph, SQLite, command worker, runtime resolver, artifact store, workspace authority, gate system, or sealing service.
- No `--force`, `--legacy-peer-deps`, unconditional lock deletion, fixed Node paths, or automatic undeclared runtime installation.
- No assumption that `npx --package`, bare `ng`, local PATH precedence, or command success proves Angular CLI/runtime authority.
- No scattered `lockfileVersion` branches or direct Transformer reliance on `packages[""]`; schema handling belongs to `PackageLockReader`.
- No V1-derived reconstruction of original root ranges; package.json remains root intent authority for every schema.
- No package-lock-first selection outside the bound npm policy, malformed-shrinkwrap fallback, silent shrinkwrap replacement, or Yarn migration support; `LockfileAuthorityPolicy` owns npm-version-aware precedence.
- No Python recreation of full npm semver/spec behavior; unsupported/complex specs defer to governed npm solve and clean `npm ci`.
- No flattening of package.json dependency sections before root-sync, no Python peer/optional graph solver, and no assumption that every root declaration must be an ordinary resolved package; npm owns peer/transitive solving and optional materialization decisions.
- No qualification-to-certification auto-promotion and no use of qualification authorization in a production run.
- No Angular-major, package-name, reporter-version, source rename, or manual incident encoded as production branching.
- No custom transitive dependency solver and no rule banning legitimate multiple transitive versions.
- No LLM command execution, runtime choice, direct package-lock/shrinkwrap editing, fabricated preimages, or reviewer-authored patch.
- No promotion of failed/unvalidated candidates and no continuation from a dirty/unproven live workspace.
- No immediate deletion of updater V2-V6 or legacy plan/repair readers; they are historical replay compatibility.

## 26. Agent execution rules

1. Execute phases sequentially P00→P15. A phase starts only when its Preconditions and prior Agent handoff are satisfied.
2. Use `superpowers:executing-plans` for implementation execution, but do not create a worktree; this repository/contract explicitly prohibits it.
3. Re-open the named current files and confirm line ranges at implementation time because edits shift lines. If responsibility moved, update this plan/evidence before coding.
4. Touch only files labelled `[UPDATE]` or `[ADD]` in the active phase. `[REUSE]` means inspect/use unchanged. `[DEPRECATE]` and `[REMOVE-LATER]` retain historical behavior.
5. Stop if a DB migration, new production file, replacement subsystem, new dependency, fixture-specific branch, or scope expansion appears necessary; provide code-truth proof and request architectural approval.
6. Preserve user changes and keep each phase diff minimal. Reuse existing models/services before extracting anything.
7. Write tests before/with behavior, run the exact focused commands, then record baseline/new/regression results and Completion evidence.
8. Production commands must be registered structured argv, `shell=false`, approved alias/profile/runtime/network/environment/timeout, with stdout/stderr/exit evidence.
9. Never infer semantic success from stderr or exit code alone. Never mark a node terminal without its contract evidence and checksum.
10. Never infer CLI authority from npx package selection or PATH. Require the absolute checksummed CLI entrypoint, actual-version proof, exact runtime/environment, and child npm identity.
11. Bind exact npm first, construct section-aware `DependencyIntent` from package.json, route root-sync through that intent plus the checksum-bound npm capability policy, route every npm lock selection through `LockfileAuthorityPolicy`/`LockfileAuthority`, and route selected V1/V2/V3 resolved-state reads through `PackageLockReader`; do not flatten sections or add filename/schema branches to callers.
12. Keep PRODUCTION and QUALIFICATION immutable and disjoint; certification requires separately reviewed/promoted evidence.
13. Preserve gate order: normal G09→promotion→G12; repaired G11→G09→promotion→G12; seal only afterward.
14. On failure, persist evidence, use P09 ownership, and follow Rollback/recovery notes. Do not improvise bypass flags or mutate authority.
15. At phase completion, update the evidence ledger and hand off only the guarantees stated in Agent handoff.
16. Do not collapse phases merely to reduce commit count; ownership and rollback boundaries are intentional. Commits, if later authorized, should remain phase-scoped.

## 27. Completion definition

V2.2 is implementation-complete only when all of the following are true:

1. P00-P15 Acceptance criteria and Completion evidence are recorded against one release commit.
2. All section 23 items pass; there are no waivers for authority, runtime, lock reproducibility, candidate isolation, governance, fingerprint equality, or sequential seals.
3. P06-A and P06-B are complete before qualification; P12 restores clean backend collection through the public runtime-reconstruction API; focused deterministic/Transformer tests and the full unexcluded backend/frontend gates pass, with any test failure separately signature-matched, owned, and resolved before release approval. Collection/import errors and excluded test files are never acceptable regression status.
4. The governed matrix completes all ten explicitly authorized qualification rows, reviews/promotes their immutable evidence to ten exact certifications, then passes a separate PRODUCTION chain with no missing/uncertified runtime.
5. A clean full E2E demonstrates requested=actual absolute discovery/migration CLI authority, governed child npm/PATH, section-aware package.json `DependencyIntent`/`peerDependenciesMeta`, exact npm capability and bound-npm `LockfileAuthorityPolicy`, canonical V1/V2/V3 resolved-state/root-sync classifications including required/dev/optional/peer/optional-peer absence semantics and governed `DEFER_TO_NPM` proof, schema-transition evidence, Factory/npm-ci/npm-ls same-authority proof, policy-gated shrinkwrap replacement, discovery-only combined update, preserve-first/classified lock fallback, complete P06-A/P06-B dynamic MigrationLedger, clean validation/delta, governed repair, path-correct G11/G09/promotion/G12, seal, recovery, and journey completion.
6. New proven plans select `transformer-plan-v2.2-proven-1`; historical plans still reconstruct/replay under legacy semantics.
7. Operator/API/frontend documentation matches persisted backend truth and identifies all recovery owners/evidence.
8. Principal architecture/release review confirms no npx/PATH authority assumption, V1-root-range inference, section flattening before root-sync, Python peer/optional solver, wrong npm capability/lock precedence/fallback, scattered lock filename/schema logic, certification bootstrap bypass, unresolved collection blocker, gate-order contradiction, prohibited special case, replacement subsystem, or unapproved schema change.

Correction-pass verdict: **ARCHITECTURE FROZEN — READY TO IMPLEMENT P00→P15**. Until every completion condition is satisfied, the V2.2 implementation itself remains not release-ready.
