# Angular Migration Control Tower â€” Optimized MVP Workflow Specification

**Project:** AI Frontend Migration Factory â€” Angular 11+  
**Reference POC:** Angular 18.x â†’ Angular 21.x  
**Migration objective:** Technical compatibility upgrade with strict functional-parity constraints  
**Backend scope:** Unchanged  
**Execution authority:** FastAPI backend and controlled sandbox worker  
**Orchestration:** LangGraph-backed deterministic state machine  
**LLM provider:** Azure OpenAI through a backend LLM Gateway  
**Default LLM deployment:** GPT-5 mini

---

## 1. Purpose

This document defines the optimized end-to-end workflow for the Angular Migration Control Tower MVP.

The workflow must remain simple for the user while being deterministic, resumable, auditable, secure, and version-aware internally.

User-visible flow:

```text
Select source â†’ Select output â†’ Select target â†’ Validate â†’ Start â†’ Monitor â†’ Review â†’ Open migrated app
```

Optimized backend flow:

```text
Preflight and immutable snapshot
â†’ Source-runtime resolution
â†’ Parallel discovery
â†’ Baseline qualification
â†’ Feasibility decision and approval
â†’ Migration planning and approval
â†’ Major-by-major stage execution
â†’ Final assurance
â†’ Atomic delivery
â†’ Evidence report
```

The workflow intentionally separates:

- **technical migration success**;
- **functional-parity assurance**;
- **security and quality assurance**;
- **delivery readiness**.

A successful build alone must never be reported as proof of complete functional parity.

---

## 2. Scope and Support Policy

### 2.1 Product Scope

The product architecture targets Angular 11 and later.

The MVP reference case is:

```text
Angular 18.x â†’ Angular 19.x â†’ Angular 20.x â†’ Angular 21.x
```

The target Angular version is selected from a company-approved target policy. Angular 21.x remains the approved target for this POC even when a newer Angular version exists.

### 2.2 MVP-Verified Scope

The first implementation should validate this narrower topology before claiming general Angular 11+ coverage:

- Angular CLI workspace;
- one primary frontend application;
- npm package manager;
- valid `package-lock.json`;
- Angular 18.x source family;
- Angular 21.x target family;
- Node.js runtime available through isolated worker profiles;
- backend unchanged;
- existing tests and lint reused when configured;
- no automatic modernization.

Other topologies can be detected and classified without being silently accepted.

### 2.3 Explicit Non-Goals

The MVP does not perform:

- AngularJS migration;
- Angular 2â€“10 migration;
- backend migration;
- UI redesign;
- business-logic refactoring;
- API-contract redesign;
- authentication or authorization redesign;
- state-management replacement;
- automatic standalone conversion;
- automatic signals conversion;
- automatic new control-flow conversion;
- automatic zoneless conversion;
- unapproved build-system modernization;
- test-framework replacement;
- unapproved external security, browser, or quality tooling.

### 2.4 Excluded MVP Tools

The following tools remain excluded unless company policy is updated:

```text
Playwright
Cypress
OSV scanner
Snyk
SonarQube
Semgrep
```

Their related gates must be reported as:

```text
manual_validation_required
```

or:

```text
deferred_company_tool_required
```

They must never be shown as passed when they were not executed.

### 2.5 Migration Support Levels

Every resolved migration path must receive a support level:

| Support level | Meaning |
|---|---|
| `officially_supported` | The stage is covered by the current Angular support window and normal official update policy. |
| `historical_validated` | The stage uses an unsupported historical Angular version but has passed the factoryâ€™s fixture and regression suite. |
| `historical_experimental` | The stage is technically possible but has not yet reached the factoryâ€™s required validation threshold. |
| `blocked` | No approved, safe, or reproducible path exists. |

Because Angular 18 and 19 are historical versions, the Angular 18 â†’ 21 POC must not automatically claim official support. Until the internal fixture suite passes, the default path classification should be:

```yaml
migration_support_level: historical_experimental
```

It can be promoted to `historical_validated` only through the factory evaluation process.

---

## 3. Workflow Optimization Objectives

The optimized workflow applies the following improvements.

| Optimization | Previous weakness | Optimized decision |
|---|---|---|
| Resolve the source runtime before baseline | Baseline could run with an incompatible Node.js version | Resolve an exact source-compatible runtime immediately after intake |
| Parallelize read-only discovery | Route, dependency, configuration, and topology scans were sequential | Run independent deterministic scans concurrently |
| Fast-fail before expensive work | Registry, disk, lockfile, or topology blockers appeared late | Add a preflight feasibility gate |
| Use deterministic services first | LLM could be called for version parsing and basic checks | Reserve LLM calls for ambiguity, diagnosis, planning narrative, and repair proposals |
| Publish only after final delivery gate | `migrated-app` could contain an incomplete workspace | Keep work internal and publish atomically at completion |
| Use exact stage versions | `^19`, `^20`, and `^21` are not reproducible over time | Resolve and persist exact package and toolchain versions |
| Validate cheapest gates first | Full builds could run before simple policy failures were detected | Run diff, dependency, lockfile, version, and symbol checks before expensive validation |
| Avoid repetitive manual gates | Browser and visual checks at every stage create unnecessary interruption | Use risk-triggered stage review and one mandatory final parity review |
| Avoid repeated repairs | Repair loop could retry the same ineffective patch | Fingerprint failures and patches; stop when no progress is detected |
| Make state resumable | Overlapping run and validation states were difficult to recover | Separate run status, phase, stage status, and step status |
| Stream ordered events | Polling can miss transitions or duplicate UI state | Use SSE with sequence numbers and replay support |
| Reuse safe results | Identical source and policy inputs were repeatedly analyzed | Cache by source hash, policy version, and artifact checksum |

---

## 4. Core Principles

| Principle | Rule |
|---|---|
| Strict parity constraints | Preserve approved UI, behavior, routes, API usage, business rules, validation behavior, and expected outputs. |
| Compatibility before modernization | Optional modernization is a separate, approved workflow. |
| Minimal diff | Apply only the smallest change required for compatibility and validation. |
| One major version at a time | Generate and execute one Angular-major transition per stage. |
| Source immutability | Never mutate the source folder. Prove immutability with a content manifest. |
| Internal workspace first | All transformation happens in an internal run workspace, not in the final delivery directory. |
| Backend execution authority | Agents propose; the backend authorizes and executes. |
| Deterministic-first | Version parsing, compatibility checks, state transitions, command validation, builds, checksums, and artifact storage are deterministic. |
| Validation-gated progression | No stage commits without mandatory evidence or an explicit accepted-risk event. |
| Bounded repair | Repair is limited by risk, attempts, time, token budget, and progress detection. |
| Immutable evidence | Stage and repair artifacts are append-only and checksum-bound. |
| Recoverable execution | Every external command has an execution record, idempotency key, lease, timeout, and cancellation policy. |
| Least privilege | Workers receive only required filesystem, process, network, and secret permissions. |

---

## 5. User Experience

### 5.1 Main Interfaces

The MVP has two primary pages:

1. **Migration Setup Page**
2. **Migration Control Tower Page**

A report viewer, diff viewer, log viewer, and AI Assistant panel are opened from the Control Tower.

### 5.2 Setup Inputs

| Field | Description | MVP rule |
|---|---|---|
| Source application path | Path to the existing Angular application | Required and read-only |
| Target output path | Parent directory for factory data and final output | Required and writable |
| Target Angular family | Company-approved target | Angular 21.x for the POC |
| Migration mode | Scope policy | Strict compatibility |
| Auto-approval | Automatic handling of eligible gates | Off by default |

### 5.3 Optimized Setup Layout

```text
--------------------------------------------------------------
Angular Migration Factory
--------------------------------------------------------------
Source Angular application: [____________________________] [Browse]
Target output directory:    [____________________________] [Browse]
Target Angular family:      [Angular 21.x               v]
Migration mode:             [Strict Compatibility        ]
Auto approval:              [OFF]

[Validate Configuration]                       [Start Migration]
--------------------------------------------------------------
Preflight result: Not validated
--------------------------------------------------------------
```

`Start Migration` remains disabled until a successful preflight result exists for the current input checksum.

---

## 6. Preflight Validation and Fast-Fail Policy

### 6.1 Purpose

Preflight catches inexpensive blockers before source copying, dependency installation, LLM calls, or migration planning.

### 6.2 Path Safety Checks

The backend must validate:

- source exists and is readable;
- target exists or can be created;
- target is writable;
- source and target are not equal;
- target is not nested inside source;
- source is not nested inside the targetâ€™s internal workspace;
- canonical paths remain inside approved roots;
- symlinks, Windows junctions, and `..` segments cannot escape approved roots;
- the target is not a protected operating-system directory;
- sufficient disk space exists for snapshot, dependencies, artifacts, and final delivery;
- path length and invalid filename risks are recorded;
- concurrent active runs do not claim the same delivery directory.

### 6.3 Project Eligibility Checks

The backend must verify:

- `package.json` exists;
- Angular packages can be detected;
- AngularJS indicators are not dominant;
- source Angular major is 11 or later;
- exact `@angular/core` and CLI versions can be resolved or classified as inconsistent;
- package-manager and lockfile type can be identified;
- workspace topology can be classified;
- selected target family is allowed by policy.

### 6.4 Environment Checks

The backend must verify:

- Git executable availability;
- selected package-manager availability;
- source-compatible worker profile availability;
- target-stage worker profiles availability;
- approved registry connectivity;
- private registry authentication availability without exposing credentials;
- proxy and certificate configuration availability;
- Azure OpenAI availability is not required for deterministic preflight, but LLM policy configuration is valid;
- SQLite state store and artifact filesystem are writable.

### 6.5 Preflight Result

```json
{
  "input_checksum": "sha256:...",
  "status": "passed",
  "source_path_safe": true,
  "target_path_safe": true,
  "angular_detected": true,
  "source_angular_exact": "18.2.13",
  "source_family": "18.x",
  "workspace_topology": "single_application_cli_workspace",
  "package_manager": "npm",
  "lockfile": "package-lock.json",
  "source_runtime_profile_available": true,
  "stage_runtime_profiles_available": true,
  "registry_access": "available",
  "blocking_reasons": [],
  "warnings": []
}
```

Preflight statuses:

```text
passed
passed_with_warnings
blocked
expired
```

A result becomes `expired` when any input, policy, source metadata, or environment capability changes.

---

## 7. Internal Workspace and Atomic Delivery

### 7.1 Important Optimization

The migration must not work directly inside `<target-output-path>/migrated-app`.

An incomplete or failed run must never appear to the user as a finished migrated application.

### 7.2 Canonical Directory Structure

```text
<target-output-path>/
â”œâ”€â”€ migrated-app/                         # Published only after delivery gate
â””â”€â”€ .migration-factory/
    â”œâ”€â”€ workspaces/
    â”‚   â””â”€â”€ <run-id>/
    â”‚       â””â”€â”€ repository/               # Mutable internal Git workspace
    â”œâ”€â”€ snapshots/
    â”‚   â””â”€â”€ <source-snapshot-id>/
    â””â”€â”€ runs/
        â””â”€â”€ <run-id>/
            â”œâ”€â”€ global/
            â”‚   â”œâ”€â”€ 00_setup/
            â”‚   â”œâ”€â”€ 01_discovery/
            â”‚   â”œâ”€â”€ 02_baseline/
            â”‚   â”œâ”€â”€ 03_analysis/
            â”‚   â”œâ”€â”€ 04_planning/
            â”‚   â””â”€â”€ 05_state/
            â”œâ”€â”€ stages/
            â”‚   â”œâ”€â”€ angular-18-to-19/
            â”‚   â”‚   â”œâ”€â”€ 00_checkpoint/
            â”‚   â”‚   â”œâ”€â”€ 01_transform/
            â”‚   â”‚   â”œâ”€â”€ 02_validation/
            â”‚   â”‚   â””â”€â”€ 03_repair/
            â”‚   â”‚       â”œâ”€â”€ attempt-001/
            â”‚   â”‚       â”œâ”€â”€ attempt-002/
            â”‚   â”‚       â””â”€â”€ attempt-003/
            â”‚   â”œâ”€â”€ angular-19-to-20/
            â”‚   â””â”€â”€ angular-20-to-21/
            â”œâ”€â”€ final_assurance/
            â”œâ”€â”€ delivery/
            â””â”€â”€ final_report/
```

### 7.3 Immutable Source Snapshot

At run creation, the backend must:

1. create a source manifest;
2. calculate a source content hash;
3. capture Git metadata when available;
4. create an immutable snapshot or controlled copy;
5. create a mutable internal Git repository from that snapshot;
6. verify source content again after migration.

The source manifest should exclude transient directories only according to explicit policy, for example:

```text
node_modules
.angular/cache
dist
coverage
```

Exclusions must be recorded; they cannot be silently assumed.

### 7.4 Final Publication

The final app is published only when the delivery gate passes:

```text
internal workspace
â†’ clean delivery copy
â†’ delivery validation
â†’ temporary publish directory
â†’ atomic rename to migrated-app
```

If `migrated-app` already exists, the backend must use an explicit replace/versioning policy. It must never silently overwrite an existing delivery.

---

## 8. Optimized Macro Workflow

The UI displays six macro phases. Detailed steps remain visible within each phase.

```text
Phase 1 â€” Preflight and Snapshot
Phase 2 â€” Discovery and Baseline
Phase 3 â€” Feasibility and Planning
Phase 4 â€” Staged Migration
Phase 5 â€” Final Assurance
Phase 6 â€” Delivery and Reporting
```

### 8.1 Full Workflow

```text
Create run
â†’ bind validated setup checksum
â†’ create immutable source snapshot
â†’ classify workspace topology
â†’ resolve exact source-compatible runtime
â†’ run parallel deterministic discovery
â†’ verify registry/private-package access
â†’ audit lifecycle scripts
â†’ run baseline qualification
â†’ resolve historical/official migration support
â†’ produce analysis and feasibility package
â†’ Analysis/Feasibility Approval
â†’ resolve exact stage versions and runtime images
â†’ generate migration plan and structured command registry
â†’ Plan Approval
â†’ execute each major-version stage
â†’ perform final assurance and manual parity gate
â†’ run delivery gate
â†’ publish migrated-app atomically
â†’ generate final evidence and usage report
```

---

## 9. Phase 1 â€” Run Creation, Snapshot, and Topology

### 9.1 Create Migration Run

`POST /migrations` creates a run only when it references a valid preflight checksum.

```json
{
  "preflight_checksum": "sha256:...",
  "source_path": "C:\\projects\\legacy-angular-app",
  "target_output_path": "C:\\migrations\\legacy-angular-app-angular21",
  "target_angular_family": "21.x",
  "migration_mode": "strict_compatibility",
  "auto_approval_mode": "off"
}
```

The backend returns:

```json
{
  "run_id": "run-001",
  "status": "created",
  "phase": "preflight_snapshot",
  "events_url": "/migrations/run-001/events",
  "state_url": "/migrations/run-001/state"
}
```

### 9.2 Workspace Topology Classification

The classifier identifies:

```text
single_application_cli_workspace
multi_application_cli_workspace
application_with_local_libraries
publishable_library_workspace
nx_workspace
microfrontend_workspace
custom_builder_workspace
ssr_or_hybrid_workspace
unknown_workspace
```

Each topology receives one of:

```text
supported
conditionally_supported
requires_human_review
blocked_for_mvp
```

The MVP must block unsupported topology instead of attempting a partial migration.

### 9.3 Source Runtime Resolution

This step occurs before baseline execution.

It resolves:

- exact Node.js version or approved compatible version;
- exact package-manager version;
- source Angular CLI execution strategy;
- operating-system worker image;
- proxy, registry, and certificate profile;
- worker image digest.

Example:

```json
{
  "profile_id": "angular-source-18-npm",
  "node_exact": "22.12.0",
  "npm_exact": "resolved-approved-version",
  "angular_cli_exact": "18.2.13",
  "worker_image_digest": "sha256:...",
  "network_policy": "approved_registries_only"
}
```

---

## 10. Phase 2 â€” Parallel Discovery

### 10.1 Optimization Rule

Independent read-only scans should run concurrently after the source snapshot is available.

Suggested parallel group:

```text
Workspace structure scan
Dependency and lockfile scan
Route and navigation scan
Backend integration scan
Environment and proxy scan
Test and lint scan
Builder and deployment scan
UI library and theme scan
State-management scan
Install-script scan
Secret-indicator scan
Parity-manifest scan
```

The orchestrator waits for the complete discovery group before creating the analysis summary.

### 10.2 Deterministic Discovery Services

These are services or gates, not LLM agents:

- Workspace Topology Classifier;
- Version Detector;
- Dependency Inventory Builder;
- Lockfile Inspector;
- Package Lifecycle-Script Auditor;
- Route Inventory Builder;
- Backend Contract Snapshot Builder;
- Build-System Detector;
- Test/Lint Inventory Builder;
- Changed-File Sensitivity Policy Loader;
- Browser Support Policy Resolver;
- Source Secret Redactor/Indicator Scanner.

### 10.3 Discovery Artifacts

```text
global/01_discovery/workspace_topology.json
global/01_discovery/version_inventory.json
global/01_discovery/package_inventory.json
global/01_discovery/dependency_graph.json
global/01_discovery/dependency_audit.json
global/01_discovery/private_package_inventory.json
global/01_discovery/lockfile_analysis.json
global/01_discovery/package_install_script_audit.json
global/01_discovery/route_inventory.json
global/01_discovery/backend_contract_snapshot.json
global/01_discovery/environment_inventory.json
global/01_discovery/build_system_inventory.json
global/01_discovery/test_lint_inventory.json
global/01_discovery/ui_theme_inventory.json
global/01_discovery/state_management_inventory.json
global/01_discovery/browser_support_policy.json
global/01_discovery/parity_manifest_baseline.json
```

### 10.4 Dependency Classification

```text
safe
needs_version_bump
needs_migration_guide
requires_approval
unknown_risk
blocking
```

The dependency record should include:

- package name;
- exact installed/resolved version;
- declared range;
- direct or transitive classification;
- Angular peer range;
- private/public source;
- lifecycle scripts;
- planned stage action;
- evidence source;
- confidence;
- human-review requirement.

---

## 11. Baseline Qualification

### 11.1 Purpose

Baseline qualification establishes what works and what already fails before migration.

It must execute inside the source-compatible runtime profile, never the host runtime by accident.

### 11.2 Baseline Sequence

```text
Validate package metadata and lockfile
â†’ apply lifecycle-script policy
â†’ perform clean reproducible install
â†’ verify resolved dependency tree
â†’ run configured baseline builds
â†’ run existing tests if configured
â†’ run existing lint if configured
â†’ capture bundle and output metadata
â†’ capture failure fingerprints
â†’ assign baseline qualification status
```

### 11.3 Reproducible Install Policy

For npm projects with a valid lockfile:

```text
npm ci
```

is preferred for clean validation.

If the lockfile is absent or inconsistent:

- do not silently use a non-reproducible install;
- classify the baseline as `reproducibility_degraded`;
- generate a proposed lockfile strategy;
- require plan approval before generating or replacing a lockfile.

### 11.4 Lifecycle-Script Policy

The audit must classify root and dependency lifecycle scripts:

```text
allowed
allowed_in_restricted_sandbox
requires_review
blocked
unknown
```

Installation is blocked when a prohibited script or unapproved source is detected.

The system must recognize that disabling all scripts may prevent legitimate package installation. Therefore, `ignore-scripts` is a policy option, not an unconditional default.

### 11.5 Baseline Qualification Status

```text
qualified
qualified_with_known_failures
reproducibility_degraded
blocked_by_environment
blocked_by_project
```

### 11.6 Failure Fingerprints

Every baseline failure receives a stable fingerprint based on:

- gate;
- normalized error code;
- file path;
- line/column when stable;
- normalized message;
- tool version.

Example:

```json
{
  "fingerprint": "sha256:...",
  "gate": "unit_tests",
  "classification": "pre_existing",
  "error_code": "TEST_FAILURE",
  "file": "src/app/example/example.spec.ts",
  "normalized_message": "expected true to be false"
}
```

Later validation distinguishes:

```text
pre_existing_unchanged
pre_existing_changed
migration_caused
resolved_pre_existing
unknown_origin
```

### 11.7 Baseline Artifacts

```text
global/02_baseline/source_toolchain_profile.json
global/02_baseline/baseline_install_report.json
global/02_baseline/baseline_dependency_tree.json
global/02_baseline/baseline_build_reports/
global/02_baseline/baseline_test_report.json
global/02_baseline/baseline_lint_report.json
global/02_baseline/baseline_bundle_metrics.json
global/02_baseline/baseline_failure_fingerprints.json
global/02_baseline/baseline_qualification_summary.json
```

---

## 12. Analysis and Feasibility Decision

### 12.1 Analysis Agent

The Analysis Agent consumes deterministic artifacts and produces:

- concise project summary;
- migration risks;
- unsupported or conditional topology findings;
- dependency risks;
- backend-contract risks;
- build-system risks;
- test coverage limitations;
- parity-assurance limitations;
- human-readable baseline interpretation.

It does not rediscover versions or parse the repository independently when deterministic artifacts already exist.

### 12.2 Compatibility and Feasibility Resolver

Before the first approval, the resolver determines whether a valid path exists.

It produces:

- exact source version;
- approved target family;
- major-version ladder;
- per-stage support level;
- source and stage runtime availability;
- package-manager strategy;
- build-system strategy;
- private-package readiness;
- baseline readiness;
- overall feasibility decision.

### 12.3 Feasibility Decision

```text
feasible
feasible_with_warnings
requires_manual_preparation
blocked
```

Example:

```json
{
  "decision": "feasible_with_warnings",
  "overall_support_level": "historical_experimental",
  "upgrade_ladder": [
    "angular-18-to-19",
    "angular-19-to-20",
    "angular-20-to-21"
  ],
  "blocking_reasons": [],
  "warnings": [
    "Angular 18 and 19 are outside current Angular support.",
    "Visual parity remains a manual MVP gate."
  ]
}
```

### 12.4 Analysis and Feasibility Approval

The first approval gate covers the complete discovery package, not only an LLM summary.

The approval checksum binds:

- source snapshot;
- baseline qualification;
- dependency audit;
- parity manifest;
- compatibility resolution;
- feasibility decision;
- risk assessment.

Decisions:

```text
approved
approved_with_risk
modification_requested
rejected
```

A blocked feasibility decision cannot be auto-approved.

---

## 13. Phase 3 â€” Migration Planning

### 13.1 Planning Inputs

- approved discovery and feasibility package;
- exact source snapshot hash;
- client constraints;
- compatibility policy version;
- build-system decision;
- package-manager policy;
- excluded-tool policy;
- auto-approval policy;
- runtime image catalog;
- validation policy;
- repair policy.

### 13.2 Exact Stage Resolution

The plan may express the user target as `21.x`, but execution profiles must pin exact versions.

Example:

```json
{
  "stage_id": "angular-18-to-19",
  "source_angular_exact": "18.2.13",
  "target_angular_exact": "resolved_approved_19_patch",
  "angular_cli_exact": "resolved_approved_19_patch",
  "typescript_exact": "resolved_compatible_version",
  "rxjs_exact_or_range": "resolved_compatible_policy",
  "node_exact": "resolved_compatible_version",
  "package_manager_exact": "resolved_approved_version",
  "worker_image_digest": "sha256:..."
}
```

The exact resolved profile is immutable after plan approval. A new package release must not change an already-approved run.

### 13.3 Build-System Decision

Each stage profile includes:

```text
preserve_existing_builder
required_compatibility_change
separate_builder_migration_unit
blocked_custom_builder
```

Build-system modernization must not be hidden inside the framework upgrade.

If Angular CLI proposes migration from the webpack `browser` builder to the newer application builder, the workflow must:

- detect the proposal;
- record the affected files and output assumptions;
- preserve the builder by default when safe;
- create a separate migration unit when migration is required or approved;
- require explicit approval when output paths, SSR, styles, deployment, or custom builders may change.

### 13.4 Planning Outputs

```text
global/04_planning/migration_plan.yaml
global/04_planning/upgrade_ladder.yaml
global/04_planning/stage_toolchain_profiles.json
global/04_planning/structured_command_registry.json
global/04_planning/validation_plan.json
global/04_planning/parity_assurance_plan.json
global/04_planning/allowed_and_forbidden_changes.yaml
global/04_planning/build_system_decision.json
global/04_planning/repair_policy.json
global/04_planning/rollback_strategy.json
global/04_planning/delivery_plan.json
global/04_planning/approval_request.md
```

### 13.5 Plan Approval

The plan approval checksum binds all executable profiles and policies.

No stage starts when:

- the plan checksum changed;
- source snapshot changed;
- compatibility policy changed;
- runtime image is unavailable;
- command registry is invalid;
- approval is stale.

---

## 14. Auto-Approval Semantics

### 14.1 Modes

```text
off
normal_gates
safe_only
```

For the MVP UI, `Auto Approval ON` maps to `normal_gates` unless company policy chooses `safe_only`.

### 14.2 `normal_gates`

Automatically approves normal workflow gates, including:

- analysis/feasibility approval when not blocked;
- plan approval when no forbidden change exists;
- low-risk repair continuation;
- stage continuation after mandatory gates pass.

It must not override hard safety invariants:

- unsafe path;
- invalid/stale checksum;
- unsupported topology;
- missing private package;
- source mutation;
- command outside registry;
- blocked lifecycle script;
- `--force` without an explicit company policy;
- high-risk auth/API/business/UI behavior change;
- unresolved repeated repair;
- behavior that cannot be assessed.

### 14.3 Live Read Rule

Auto approval is stored in backend run policy and read at every gate.

It must not be copied only into frontend state or read only at migration start.

When the user changes the mode:

1. backend persists a policy-change event;
2. the change receives an effective event sequence;
3. the current waiting gate is reevaluated immediately;
4. eligible gates continue without toggling the setting off and on again;
5. the policy remains active for all later stages.

### 14.4 API

```http
PATCH /migrations/{runId}/approval-policy
```

```json
{
  "mode": "normal_gates",
  "reason": "User enabled Auto Approval from the Control Tower."
}
```

---

## 15. Structured Command Registry

### 15.1 No Raw Shell Strings

The backend must not accept arbitrary shell command strings from agents.

Use a structured request:

```json
{
  "command_id": "angular_update_stage",
  "executable": "npx",
  "arguments": [
    "--yes",
    "--package",
    "@angular/cli@{target_cli_exact}",
    "ng",
    "update",
    "@angular/core@{target_angular_exact}",
    "@angular/cli@{target_cli_exact}",
    "--verbose"
  ],
  "shell": false,
  "working_directory_alias": "run_workspace",
  "runtime_profile_id": "angular-stage-19",
  "timeout_seconds": 1800,
  "network_profile": "approved_registries_only",
  "cancellation_policy": "terminate_process_tree_then_restore_checkpoint"
}
```

The placeholders are expanded only from the checksum-bound stage profile.

### 15.2 Command Validation

Before execution, the backend validates:

- command ID exists in the approved registry;
- executable is allowlisted;
- arguments match the registered template;
- no shell operators or substitutions are present;
- working directory resolves inside the run workspace;
- runtime profile matches the current stage;
- environment variables are allowlisted;
- secrets are scoped to the command and redacted from logs;
- network policy matches the action;
- stage and state prerequisites are satisfied;
- idempotency key was not already completed.

### 15.3 Forbidden by Default

```text
--force
--legacy-peer-deps
arbitrary npm package addition
unapproved dependency replacement
unapproved builder migration
standalone/signals/control-flow/zoneless migrations
commands outside workspace
commands with shell=true
commands absent from registry
```

An approved exception must generate a new plan version or accepted-risk event.

### 15.4 Execution Record

Every command stores:

- execution ID;
- idempotency key;
- requesting component;
- stage and step;
- expanded executable and arguments;
- redacted environment aliases;
- runtime image digest;
- start/end time;
- timeout;
- exit code;
- stdout/stderr artifact references;
- cancellation result;
- produced file manifest;
- state transition sequence.

---

## 16. Phase 4 â€” Optimized Stage Lifecycle

Each major-version transition uses the same deterministic lifecycle.

### 16.1 Stage Lifecycle

```text
1. Acquire stage worker lease
2. Verify current checkpoint and workspace hash
3. Activate exact runtime profile
4. Create stage-start Git checkpoint
5. Execute approved Angular update
6. Capture update output and complete diff
7. Detect forbidden modernization or unexpected dependency changes
8. Validate lockfile and lifecycle-script policy
9. Perform clean frozen dependency installation
10. Verify exact Angular/CLI/TypeScript/RxJS/Node profile
11. Classify changed files and dependencies by risk
12. Run static symbol and template checks
13. Run targeted low-cost validation
14. Run full required build configurations
15. Run existing tests and lint when configured
16. Rebuild route, backend-contract, and parity manifests
17. Compare against previous checkpoint and original baseline
18. Enter repair loop only for eligible migration-caused failures
19. Trigger approval when risk policy requires it
20. Create immutable stage evidence and commit
21. Release worker lease and continue
```

### 16.2 Why This Order Is Faster

The workflow runs inexpensive blockers before expensive builds:

```text
Diff policy
â†’ lockfile policy
â†’ exact version check
â†’ risk classification
â†’ static checks
â†’ targeted validation
â†’ full build/test validation
```

A forbidden dependency or unexpected auth-file change can stop the stage before a costly full test run.

### 16.3 Update Command Strategy

The user target is a version family, but the stage command uses the exact approved target patch.

The system should follow the one-major-at-a-time strategy and prefer the latest approved patch selected at planning time.

The command must run in a clean internal Git workspace. The backend owns checkpoints and commits; CLI-generated commits are optional and should not duplicate backend checkpoint semantics.

### 16.4 Clean Installation After Update

After package and lockfile changes:

- remove the prior `node_modules` through controlled workspace cleanup;
- use a clean frozen install when supported;
- verify dependency-tree consistency;
- do not reuse `node_modules` across Angular-major stages;
- a shared package cache may be used only as a download optimization, not as evidence of installation correctness.

### 16.5 Stage Status

```text
pending
running
waiting_approval
repairing
passed
passed_with_manual_items
passed_with_accepted_risk
rolled_back
failed
cancelled
diagnostic_hold
```

### 16.6 Stage Step Status

```text
pending
running
passed
failed
blocked
skipped_not_configured
skipped_not_applicable
manual_validation_required
deferred_company_tool_required
accepted_risk
```

---

## 17. Validation Strategy

### 17.1 Mandatory Technical Gates Per Stage

| Gate | Purpose |
|---|---|
| Update execution | Confirm the approved migration command completed and produced expected evidence |
| Diff policy | Detect forbidden or unexpected changes before expensive validation |
| Lockfile integrity | Confirm package metadata and lockfile consistency |
| Clean install | Prove dependencies install in the exact stage runtime |
| Version profile | Confirm Angular, CLI, TypeScript, RxJS, Node, and package-manager compatibility |
| Changed-file risk | Determine whether automatic continuation is allowed |
| Static symbol/template checks | Detect unresolved imports, phantom APIs, and template references |
| Build validation | Build all required application/library targets and configurations |
| Route comparison | Detect route, guard, resolver, and redirect differences |
| Backend-contract comparison | Detect frontend API, interceptor, auth, payload, or environment changes |
| Parity-manifest comparison | Produce structured evidence of observable-contract changes |

### 17.2 Conditional Gates

- existing unit tests;
- existing lint;
- library package build;
- SSR/prerender build;
- service-worker build;
- i18n build;
- custom project targets explicitly approved by topology policy.

### 17.3 Risk-Adaptive Manual Validation

To avoid repeating the same manual work after every major stage:

- final browser smoke and visual parity remain mandatory manual MVP gates;
- an intermediate manual gate is triggered only when a stage changes UI, CSS/theme, routing, guard, form validation, auth, API behavior, or other high-risk files;
- low-risk package/config-only stages may continue with manual review deferred to final assurance;
- every deferred stage item remains visible in the final report.

### 17.4 Build Targets

The plan identifies every required project and configuration.

Example:

```yaml
projects:
  customer-portal:
    type: application
    required_builds:
      - development
      - production
    tests: configured
    lint: configured
  shared-ui:
    type: library
    required_builds:
      - package
```

The workflow must not assume that a single `npm run build` validates a multi-project workspace.

### 17.5 Technical Stage Definition of Done

A stage is technically passed only when:

- exact target profile is installed;
- mandatory technical gates pass;
- no new unresolved migration-caused failure remains;
- changed-file risk permits continuation or approval exists;
- backend-contract comparison is approved;
- checkpoint and evidence artifacts are committed;
- workspace hash matches the committed stage output.

---

## 18. Functional-Parity Assurance

### 18.1 Separate Assurance Dimensions

The run stores independent statuses:

```json
{
  "technical_upgrade_status": "passed",
  "functional_parity_status": "manual_validation_pending",
  "security_assurance_status": "deferred_company_tool_required",
  "quality_assurance_status": "deferred_company_tool_required",
  "delivery_readiness": "conditionally_ready"
}
```

### 18.2 Parity Manifest

The baseline and each stage capture:

- route paths;
- redirects;
- lazy-loading boundaries;
- guards and resolvers;
- API base URLs;
- endpoint and HTTP-method references where statically identifiable;
- interceptors;
- auth-header and cookie/token references;
- request builders;
- response mappers;
- form validators;
- error-handling paths;
- translation keys;
- assets and global styles;
- theme configuration;
- polyfills;
- service-worker configuration;
- SSR/prerender configuration;
- output paths and bundle budgets;
- supported browser contract.

### 18.3 Browser Support Contract

Strict parity means approved behavior on the agreed target browser matrix.

The setup/analysis package records:

```json
{
  "legacy_browser_requirements": [],
  "target_angular_browser_baseline": "resolved_from_target_policy",
  "client_required_browsers": [],
  "unsupported_requirements": [],
  "decision": "approved_target_matrix"
}
```

A browser requirement unsupported by Angular 21 must be explicitly accepted, changed, or block delivery.

### 18.4 Manual Final Parity Gate

Without approved browser automation, the final assurance package generates a manual checklist covering:

- application boot;
- primary navigation;
- lazy routes;
- login/logout where environment permits;
- guarded routes;
- representative forms and validators;
- API requests and error handling;
- critical pages;
- visual layout and theme;
- browser console errors;
- asset and translation loading.

Result statuses:

```text
verified
verified_with_accepted_differences
manual_validation_pending
failed
not_executed
```

---

## 19. Changed-File and Dependency Risk Model

### 19.1 Risk Is Content-Aware

Path-based classification is only the first signal. The classifier should also inspect the type of change.

For example, adding a missing import in an auth service is not automatically high risk if behavior is unchanged, but it still requires stricter validation because the file is sensitive.

### 19.2 Risk Levels

| Risk | Examples | Default action |
|---|---|---|
| Low | package/config changes, generated migration edits, missing import, type-only compatibility fix | Auto-continue after validation |
| Medium | routing declarations, RxJS pipelines, Material module configuration, test setup | Continue only when plan and validation policy allow |
| High | auth, interceptors, guards, API mappers, environment behavior, form validators, business/calculation services, CSS/theme/layout | Human or auto-approval policy review; full targeted evidence required |
| Blocked | unknown private package behavior, ambiguous expected output, source mutation, unsupported command, untrusted lifecycle action | Diagnostic hold |

### 19.3 Unexpected Change Rule

A changed file outside the approved migration units causes:

```text
WAITING_APPROVAL
```

or:

```text
DIAGNOSTIC_HOLD
```

The agent cannot silently expand the plan.

---

## 20. Repair Loop Optimization

### 20.1 Eligibility

Repair is allowed only when the failure is:

- new after the current stage;
- attributable to migration or approved dependency alignment;
- low risk, or explicitly approved medium risk;
- supported by enough local evidence;
- inside the approved repair scope.

### 20.2 Optimized Repair Cycle

```text
Normalize and fingerprint failure
â†’ compare with baseline and previous attempts
â†’ gather minimal relevant context
â†’ deterministic fix lookup
â†’ LLM diagnosis only when needed
â†’ validate structured patch proposal
â†’ apply minimal patch
â†’ static checks
â†’ targeted validation
â†’ compare error delta
â†’ full stage validation only after targeted success
```

### 20.3 Attempt and Progress Rules

- maximum three total repair attempts per stage;
- maximum two attempts for the same failure fingerprint;
- do not apply the same patch fingerprint twice;
- if the normalized error set does not improve after an attempt, escalate early;
- a new failure introduced by repair triggers immediate patch rollback;
- repair has time, token, and cost budgets;
- high-risk behavior changes are never auto-repaired.

### 20.4 Repair Context Optimization

The LLM receives only:

- normalized error excerpt;
- affected-file snippets;
- relevant stage profile;
- current diff;
- approved/forbidden change policy;
- previous attempt delta;
- locally resolvable symbol and package metadata.

It does not receive the whole repository by default.

### 20.5 Repair Artifacts Per Attempt

```text
stages/<stage-id>/03_repair/attempt-001/
â”œâ”€â”€ failure_fingerprint.json
â”œâ”€â”€ diagnosis.json
â”œâ”€â”€ llm_patch_proposal.json
â”œâ”€â”€ backend_patch_validation.json
â”œâ”€â”€ patch.diff
â”œâ”€â”€ static_check.json
â”œâ”€â”€ targeted_validation.json
â”œâ”€â”€ error_delta.json
â””â”€â”€ decision.json
```

---

## 21. Rollback and Checkpoints

### 21.1 Checkpoints

Create checkpoints at:

- immutable source snapshot;
- baseline-qualified workspace;
- start of every major stage;
- successful end of every major stage;
- before every repair patch;
- final delivery candidate.

### 21.2 Rollback Levels

| Level | Trigger | Action |
|---|---|---|
| Patch rollback | Patch fails static or targeted validation | Revert patch commit and preserve attempt artifacts |
| Stage rollback | Stage becomes unstable or repair budget is exhausted | Reset to stage-start commit |
| Migration rollback | User restarts or abandons the whole migration | Restore baseline-qualified workspace |
| Diagnostic hold | State is useful for investigation but unsafe to continue | Preserve exact workspace and stop automation |

### 21.3 Integrity Verification

After rollback, verify:

- Git commit/checkpoint hash;
- workspace file manifest;
- package metadata and lockfile hash;
- active runtime profile;
- current state version.

No resume is allowed when these values do not match the checkpoint.

---

## 22. State Machine Optimization

### 22.1 Avoid Overlapping Global States

Use four separate dimensions rather than dozens of ambiguous global state names.

#### Run Status

```text
created
running
waiting_approval
cancelling
cancelled
diagnostic_hold
failed
completed
```

#### Run Phase

```text
preflight_snapshot
discovery
baseline
analysis_feasibility
planning
stage_execution
final_assurance
delivery
reporting
```

#### Stage Status

```text
pending
running
waiting_approval
repairing
passed
passed_with_manual_items
passed_with_accepted_risk
rolled_back
failed
cancelled
diagnostic_hold
```

#### Step Status

```text
pending
running
passed
failed
blocked
skipped
manual
deferred
accepted_risk
```

This model prevents contradictions such as the run being both `BUILD_RUNNING` and `VALIDATION_RUNNING`.

### 22.2 Transition Contract

Every transition includes:

```json
{
  "event_id": "uuid",
  "event_sequence": 127,
  "run_id": "run-001",
  "stage_id": "angular-18-to-19",
  "idempotency_key": "sha256:...",
  "previous_state_version": 34,
  "new_state_version": 35,
  "previous_status": "running",
  "new_status": "waiting_approval",
  "phase": "stage_execution",
  "step": "changed_file_risk_review",
  "actor": "orchestrator",
  "reason": "High-risk interceptor file changed.",
  "artifact_refs": []
}
```

### 22.3 Worker Lease

Long-running work requires:

- worker lease ID;
- heartbeat;
- lease expiry;
- current execution ID;
- safe recovery decision;
- prevention of duplicate worker ownership.

A lost worker produces `diagnostic_hold` or safe retry according to command idempotency.

### 22.4 Atomic State and Artifact Updates

A step is not marked passed until:

1. required artifacts are stored;
2. content hashes are recorded;
3. state transaction commits;
4. event is appended.

The UI must never see `passed` before its evidence exists.

---

## 23. Cancellation and Resume

### 23.1 Cancellation States

```text
cancel_requested
cancelling
cancelled
```

### 23.2 Cancellation Sequence

```text
User requests cancellation
â†’ persist cancel_requested event
â†’ stop scheduling new steps
â†’ signal current command
â†’ wait command-specific grace period
â†’ terminate complete process tree if required
â†’ capture partial logs and exit reason
â†’ restore stage-start checkpoint when workspace is unsafe
â†’ verify workspace integrity
â†’ generate partial report
â†’ mark cancelled
```

### 23.3 Command Cancellation Policy

Each command is classified:

```text
immediately_interruptible
interruptible_with_grace_period
checkpoint_bound
non_interruptible_short_operation
```

The command registry defines the policy; the agent does not decide it dynamically.

### 23.4 Resume Eligibility

Resume is allowed only when:

- state and artifacts are consistent;
- no active worker lease exists;
- workspace matches a safe checkpoint;
- exact runtime image is available;
- source snapshot still exists;
- plan and policy checksums remain valid;
- pending approval is still current.

Resume actions:

```text
continue_waiting_gate
retry_failed_step
resume_from_stage_start
resume_from_last_completed_stage
```

A cancelled run may resume only when its preserved workspace passes integrity verification.

---

## 24. Control Tower State and SSE

### 24.1 SSE as Primary Update Channel

Use Server-Sent Events for backend-to-frontend workflow updates.

```http
GET /migrations/{runId}/events
Accept: text/event-stream
Last-Event-ID: 126
```

Every event includes the monotonic sequence number.

### 24.2 Recovery

On initial load or reconnect:

1. UI fetches the latest state snapshot;
2. UI opens SSE using the latest event sequence;
3. backend replays missed events when retained;
4. if replay is unavailable, UI refreshes the full snapshot;
5. frontend reducer ignores duplicate or older sequences.

### 24.3 UI Source of Truth

The UI renders only backend data for:

- run and phase;
- current stage and step;
- agent/component statuses;
- validation results;
- approvals;
- auto-approval policy;
- repair attempts;
- cancellation;
- manual/deferred items;
- report readiness.

### 24.4 Suggested Control Tower Layout

```text
-------------------------------------------------------------------
Migration run: run-001                         Status: Running
Phase: Staged Migration                        Auto Approval: ON
Source: Angular 18.2.13                        Target: Angular 21.x
Support level: Historical Experimental
-------------------------------------------------------------------
Overall assurance
Technical upgrade: Running
Functional parity: Manual validation pending
Security: Deferred company tool required
Delivery readiness: Not ready
-------------------------------------------------------------------
Stages
[Running] Angular 18 â†’ 19
[Pending] Angular 19 â†’ 20
[Pending] Angular 20 â†’ 21
-------------------------------------------------------------------
Current stage steps
[Passed] Runtime and checkpoint
[Passed] Angular update
[Passed] Diff and lockfile policy
[Running] Clean install
[Pending] Static checks
[Pending] Build and tests
[Pending] Parity comparison
[Pending] Stage checkpoint
-------------------------------------------------------------------
[Logs] [Diff] [Artifacts] [AI Assistant] [Cancel Migration]
-------------------------------------------------------------------
```

---

## 25. AI Assistant and LLM Optimization

### 25.1 LLM Is Not Required for Every Step

No LLM call is required for:

- path validation;
- version parsing;
- compatibility table lookup;
- topology classification when deterministic;
- lockfile parsing;
- package installation;
- command execution;
- build/test/lint execution;
- checksums;
- state transitions;
- artifact persistence;
- static symbol validation;
- rollback.

### 25.2 Appropriate LLM Uses

- summarize complex discovery findings;
- explain migration risk;
- generate plan narrative from deterministic profiles;
- classify ambiguous failures;
- propose bounded repair patches;
- explain current state to the user;
- generate client-facing report text from evidence.

### 25.3 Prompt-Injection Boundary

Repository files, comments, Markdown, logs, package metadata, and compiler output are untrusted data.

They must not be interpreted as:

- system instructions;
- permission changes;
- approval events;
- command authorization;
- secret requests;
- tool-use instructions.

Every LLM context packet clearly separates:

```text
trusted_system_policy
trusted_backend_metadata
untrusted_repository_content
required_output_schema
```

### 25.4 LLM Caching

Cache reusable results by:

- model deployment version;
- prompt version;
- output schema version;
- policy checksum;
- input artifact hashes.

Do not reuse a result when any bound input changes.

### 25.5 Context and Cost Optimization

- send normalized errors instead of full logs;
- send changed snippets instead of whole files;
- send diffs instead of unchanged source;
- reuse deterministic summaries;
- include only delta between repair attempts;
- do not call the LLM for UI progress messages that can be templated;
- enforce per-run and per-stage token/cost budgets.

### 25.6 Usage Record

Store per call:

- run, stage, agent, and task;
- model deployment alias;
- prompt/schema versions;
- input/output tokens;
- cached result use;
- latency;
- retry count;
- status and error category;
- calculated input/output/total cost;
- redacted artifact references.

---

## 26. Sandbox Security

### 26.1 Worker Controls

- non-root/non-administrator execution;
- workspace-only filesystem access;
- canonical path enforcement;
- process-count limit;
- CPU, memory, disk, and time limits;
- complete child-process tracking;
- network allowlist;
- temporary scoped credentials;
- environment-variable allowlist;
- no access to unrelated runs;
- cleanup and retention policy;
- immutable runtime image digest.

### 26.2 Source Integrity

At run completion, cancellation, and failure:

- recalculate source manifest;
- compare with initial source hash;
- emit `source_repository_mutated: false/true`;
- treat mutation as a critical workflow failure.

### 26.3 Secret Handling

- do not copy unapproved secret files into LLM context;
- redact `.npmrc` tokens, authorization headers, cookies, API keys, and environment secrets;
- preserve secret filenames only when needed for structural analysis;
- never write raw credentials to command or LLM artifacts.

---

## 27. Final Assurance

### 27.1 Inputs

- all completed stage checkpoints;
- original and final parity manifests;
- technical validation reports;
- manual/deferred gate status;
- repair and risk history;
- source integrity report;
- delivery plan.

### 27.2 Final Technical Validation

Run from a clean final-stage workspace:

- clean frozen install;
- exact version profile check;
- required production builds;
- all existing tests and lint when configured;
- route and backend-contract comparison;
- final diff classification;
- final dependency and lifecycle-script inventory;
- bundle/output comparison;
- source immutability verification.

This final clean validation prevents a stage-local cache from hiding delivery problems.

### 27.3 Manual and Deferred Review

- browser smoke: manual;
- visual parity: manual;
- security scan: deferred company tool;
- quality scan: deferred company tool.

The delivery policy determines whether manual items may remain pending or require explicit acceptance.

---

## 28. Delivery Gate and Atomic Publication

### 28.1 Delivery Outputs

- clean migrated application;
- Git history with stage checkpoints;
- unified patch bundle;
- migration manifest;
- final dependency lockfile;
- README with exact runtime requirements;
- final technical report;
- manual actions list;
- unresolved blockers;
- token/cost summary.

### 28.2 Delivery Gate

Before publication:

- final technical validation passed;
- source remained unchanged;
- final app contains no internal artifact directories;
- no raw secrets are present;
- delivery manifest matches file hashes;
- output location is safe and not occupied unexpectedly;
- final assurance and accepted-risk statuses are recorded;
- delivery candidate is committed and immutable.

### 28.3 Publication Result

```json
{
  "delivery_status": "published",
  "delivery_path": "C:\\migrations\\legacy-angular-app-angular21\\migrated-app",
  "delivery_manifest_hash": "sha256:...",
  "final_commit": "git-sha",
  "technical_upgrade_status": "passed",
  "functional_parity_status": "manual_validation_pending"
}
```

---

## 29. Artifact Contract

### 29.1 Artifact Envelope

Every JSON artifact contains:

```json
{
  "schema_version": "1.0",
  "artifact_id": "uuid",
  "artifact_type": "stage_validation_summary",
  "run_id": "run-001",
  "stage_id": "angular-18-to-19",
  "attempt": null,
  "producer": "build_validation_service",
  "created_at": "ISO-8601",
  "policy_version": "migration-policy-v1",
  "input_artifact_hashes": [],
  "content_hash": "sha256:..."
}
```

LLM-derived artifacts also include:

```text
model_deployment_alias
prompt_version
output_schema_version
```

### 29.2 Artifact Rules

- immutable after creation;
- stage- and attempt-scoped paths;
- content-addressed or checksum-indexed;
- no overwrite of prior evidence;
- large logs stored as chunked files, not database blobs;
- SQLite stores metadata and state, while the filesystem stores artifacts;
- artifact creation and state transition are transactional from the workflow perspective;
- retention and cleanup status are recorded.

---

## 30. Recommended Backend APIs

### 30.1 Validate Setup

```http
POST /migration-preflights
```

Returns a preflight ID and checksum.

### 30.2 Create Run

```http
POST /migrations
```

Requires the preflight checksum.

### 30.3 Get State Snapshot

```http
GET /migrations/{runId}/state
```

Suggested response:

```json
{
  "run_id": "run-001",
  "status": "running",
  "phase": "stage_execution",
  "state_version": 35,
  "latest_event_sequence": 127,
  "current_stage_id": "angular-18-to-19",
  "current_step": "clean_install",
  "auto_approval_mode": "normal_gates",
  "assurance": {
    "technical_upgrade": "running",
    "functional_parity": "manual_validation_pending",
    "security": "deferred_company_tool_required",
    "delivery_readiness": "not_ready"
  },
  "stages": []
}
```

### 30.4 SSE Events

```http
GET /migrations/{runId}/events
```

### 30.5 Submit Approval

```http
POST /migrations/{runId}/approvals
```

```json
{
  "gate_id": "plan-approval",
  "artifact_set_checksum": "sha256:...",
  "decision": "approved",
  "source": "ui_button",
  "comment": "Approved."
}
```

### 30.6 Change Auto-Approval Policy

```http
PATCH /migrations/{runId}/approval-policy
```

### 30.7 Cancel

```http
POST /migrations/{runId}/cancel
```

The endpoint is idempotent.

### 30.8 Resume

```http
POST /migrations/{runId}/resume
```

```json
{
  "strategy": "last_safe_checkpoint"
}
```

### 30.9 Assistant Chat

```http
POST /migrations/{runId}/assistant/chat
```

### 30.10 Artifacts

```http
GET /migrations/{runId}/artifacts
GET /migrations/{runId}/artifacts/{artifactId}
```

Do not allow arbitrary filesystem paths in the artifact API.

---

## 31. Performance and Cost Optimizations

### 31.1 Safe Caches

| Cache | Key | Reuse rule |
|---|---|---|
| Source discovery | source hash + scanner version + policy version | Reuse only when all match |
| Compatibility profile | exact source versions + target policy + catalog version | Immutable per approved plan |
| Package download cache | package-manager and registry profile | Download optimization only; never reuse `node_modules` as validation evidence |
| LLM result | model + prompt + schema + input artifact hashes | Reuse when all bound inputs match |
| Migration guidance | Angular/package exact versions + source revision | Read-only context cache |

### 31.2 Resource-Aware Parallelism

Safe parallelism:

- deterministic read-only discovery scans;
- report generation from immutable artifacts;
- independent final artifact packaging.

Potentially sequential or capacity-limited:

- npm installations;
- Angular builds;
- tests;
- multiple workers writing SQLite state;
- commands sharing the same workspace.

### 31.3 SQLite MVP Boundary

For the SQLite MVP:

- one backend host;
- limited concurrent migration runs;
- one active mutating worker per run;
- WAL mode when appropriate;
- short state transactions;
- artifact content outside the database;
- serialized critical writes;
- explicit migration path to PostgreSQL for distributed workers or multiple backend instances.

### 31.4 Log Optimization

- stream bounded log chunks through SSE;
- persist full logs as artifacts;
- create normalized error summaries;
- avoid sending complete logs to the LLM;
- keep the UI log buffer bounded;
- support pagination and search in stored logs.

---

## 32. Observability

Track per run, stage, and step:

- duration;
- queue wait;
- worker runtime;
- command exit codes;
- retries;
- repair attempts;
- rollback count;
- build/test duration;
- artifact size;
- SSE reconnect count;
- token usage;
- LLM latency and failures;
- input/output/total cost;
- cache hits;
- accepted risks;
- manual items;
- cancellation latency.

Recommended operational alerts:

- worker heartbeat lost;
- disk threshold exceeded;
- source mutation detected;
- repeated command timeout;
- Azure OpenAI quota/rate-limit issue;
- state/artifact inconsistency;
- stuck waiting state;
- orphaned workspace;
- SQLite write contention threshold exceeded.

---

## 33. Final Run Status

The run status remains concise:

```text
completed
failed
cancelled
diagnostic_hold
```

The meaning is completed by independent assurance fields.

Example:

```json
{
  "run_status": "completed",
  "technical_upgrade_status": "passed",
  "functional_parity_status": "manual_validation_pending",
  "security_assurance_status": "deferred_company_tool_required",
  "quality_assurance_status": "deferred_company_tool_required",
  "delivery_status": "published_with_manual_items"
}
```

This avoids ambiguous statuses such as a single `Completed` value that hides remaining manual gates.

---

## 34. MVP Definition of Done

The optimized MVP is successful when:

- setup validation produces a checksum-bound preflight result;
- unsafe paths and unsupported topologies fail fast;
- source snapshot and immutability proof are generated;
- exact source-compatible runtime is used for baseline;
- independent discovery scans execute in parallel;
- pre-existing failures are fingerprinted;
- feasibility and support level are visible before approval;
- exact stage toolchains are resolved and checksum-bound;
- commands use structured backend authorization, not raw shell strings;
- Angular 18 â†’ 19 â†’ 20 â†’ 21 executes one major at a time;
- every stage performs clean installation and required validation;
- build-system migration cannot happen silently;
- repair is bounded and progress-aware;
- auto approval persists and is reevaluated at every gate;
- cancellation stops future work and safely handles the active process tree;
- resume verifies checkpoint integrity;
- SSE delivers ordered backend-owned state;
- technical and parity statuses are reported separately;
- final application is published only after the delivery gate;
- artifacts are immutable and organized by stage/attempt;
- token and cost reporting is complete;
- the final report exposes every manual, deferred, failed, accepted-risk, and unresolved item.

---

## 35. Recommended Implementation Priority

### P0 â€” Core POC Reliability

1. Preflight and safe path validation.
2. Immutable source snapshot and internal workspace.
3. Simplified multidimensional state model.
4. Exact source and stage runtime profiles.
5. Baseline qualification and failure fingerprints.
6. Structured command registry.
7. Major-by-major execution and stage checkpoints.
8. Clean install, version check, build, and existing test/lint gates.
9. Repair loop with attempt/progress limits.
10. SSE state stream with snapshot recovery.
11. Cancellation and process-tree handling.
12. Atomic final publication.

### P1 â€” Internal Demonstration Quality

1. Parallel discovery.
2. Workspace topology policy.
3. Parity manifest and backend-contract comparison.
4. Risk-adaptive manual validation.
5. Auto-approval policy updates at runtime.
6. LLM prompt-injection boundary.
7. Token, cost, and quota dashboards.
8. Idempotency, leases, and crash recovery.
9. Stage/attempt immutable artifact model.
10. Final clean assurance run.

### P2 â€” Enterprise Extension

1. Company-approved browser automation.
2. Company-approved security and quality tooling.
3. PostgreSQL and distributed workers.
4. RBAC and approval separation of duties.
5. Multi-application, Nx, microfrontend, SSR, and custom-builder paths.
6. Pull-request and CI/CD integration.
7. Tenant isolation, encryption, retention, and disaster recovery.
8. Full AI migration evaluation and model-promotion gates.

---

## 36. Final Optimized Product Rule

The user sees a simple flow:

```text
Source â†’ Output â†’ Target â†’ Validate â†’ Start â†’ Monitor â†’ Review â†’ Open migrated app
```

The platform enforces:

```text
Safe intake
â†’ immutable snapshot
â†’ exact source runtime
â†’ parallel discovery
â†’ qualified baseline
â†’ feasibility approval
â†’ exact approved plan
â†’ controlled stage loop
â†’ bounded repair
â†’ independent assurance
â†’ atomic delivery
â†’ complete evidence
```

This workflow reduces unnecessary LLM usage, catches blockers earlier, avoids repeated manual work, prevents incomplete output from being mistaken for a finished migration, and makes cancellation, recovery, audit, and delivery behavior explicit.

---


## 37. Component Ownership and Agent Display

### 37.1 Deterministic Components

The following components execute deterministic logic and should not be presented internally as autonomous LLM agents:

| Component | Responsibility |
|---|---|
| Source Intake Validator | Safe path, source, target, and preflight validation |
| Snapshot Service | Immutable source capture and integrity manifest |
| Workspace Topology Classifier | Angular CLI, multi-project, library, Nx, SSR, custom-builder, and microfrontend classification |
| Compatibility Resolver | Exact version and support-level resolution |
| Toolchain Runtime Manager | Exact Node.js, package-manager, CLI, and worker-image selection |
| Command Policy Engine | Structured command authorization |
| Baseline Qualification Service | Clean install, build, tests, lint, and failure fingerprinting |
| Static Symbol Gate | Import, symbol, template, and package verification |
| Parity Evidence Engine | Route, backend-contract, configuration, and observable-contract comparison |
| Checkpoint Service | Git checkpoint, rollback, and integrity verification |
| Artifact Service | Immutable evidence persistence and hashing |
| Worker Supervisor | Lease, heartbeat, timeout, cancellation, and resource controls |
| Delivery Service | Clean delivery copy and atomic publication |

### 37.2 AI-Assisted Agents

| Agent | Primary responsibility | Mutation authority |
|---|---|---|
| Analysis Agent | Explain deterministic findings and migration risks | None |
| Planning Agent | Produce the human-readable migration plan from approved profiles | None |
| Transformation Agent | Request approved stage actions and bounded deterministic patches | Sandbox through backend only |
| Build/Validation Agent | Classify and summarize validation outcomes | None |
| Repair Agent | Diagnose eligible migration failures and propose minimal patches | Sandbox through backend only |
| Report Agent | Generate evidence-based technical and client reports | None |
| AI Assistant | Explain state, artifacts, decisions, risks, and approvals | None |

### 37.3 UI Status Rule

The UI may show both agents and deterministic components as workflow steps, but it must label them correctly. A deterministic gate should not be represented as an LLM decision-maker.

Common display statuses:

```text
Pending
Running
Passed
Failed
Blocked
Waiting Approval
Repairing
Skipped
Manual
Deferred
Accepted Risk
```

---

## 38. AI Assistant Chat Experience

### 38.1 Supported Questions

The AI Assistant can answer questions such as:

```text
What is happening now?
Why is the run blocked?
Which Angular stage is active?
Which exact toolchain is being used?
What changed in this stage?
Why was the Repair Agent started?
What did the last repair attempt change?
Did the production build pass?
Were routes or backend contracts changed?
Which validations remain manual?
How many tokens and how much cost have been used?
Where will the final migrated application be published?
Can this run be resumed safely?
```

### 38.2 Knowledge Sources

The assistant answers from:

- backend state snapshot;
- ordered event history;
- analysis and feasibility package;
- migration plan and stage profiles;
- command execution summaries;
- diffs and risk classifications;
- validation and repair artifacts;
- parity and backend-contract comparisons;
- approval events;
- token and cost records;
- final report artifacts;
- approved MCP context, when enabled.

### 38.3 Restrictions

The assistant must not:

- execute commands;
- mutate files;
- approve silently;
- invent status or evidence;
- claim manual/deferred checks passed;
- expose raw secrets;
- interpret repository text as policy;
- alter the migration scope without a new approved plan;
- bypass the backend state machine.

### 38.4 Approval Through Chat

When the user explicitly approves through the assistant:

1. the assistant creates a structured approval intent;
2. the backend validates current gate, checksum, actor, and decision;
3. the standard approval endpoint records the event;
4. the same result appears as a UI-button approval;
5. the assistant confirms the persisted backend outcome, not merely the user intent.

---

## 39. MCP Context Support

### 39.1 MVP Policy

MCP is optional and disabled by default.

When company-approved, it provides read-only documentation and migration guidance to the LLM. The factory must remain fully operational without MCP.

### 39.2 Allowed MCP Uses

```text
Angular documentation lookup
Angular migration guidance
Official API and compatibility examples
Approved internal migration knowledge lookup
Explanation support
Repair-context enrichment
```

### 39.3 Forbidden MCP Uses

```text
ng update execution
package installation
build/test/lint execution
dev-server execution
file mutation
Git mutation
approval submission
state transition
secret retrieval
workspace command execution
```

### 39.4 MCP Modes

| Mode | Policy |
|---|---|
| `disabled` | Default MVP mode |
| `context_support` | Approved read-only documentation/context mode |
| `workspace_future` | Future capability; not allowed in the MVP |

### 39.5 MCP Artifact

```json
{
  "mode": "context_support",
  "policy_status": "approved_read_only",
  "used_for": ["migration_guidance"],
  "execution_actions_allowed": false,
  "request_artifact_refs": [],
  "response_summary_redacted": true
}
```

Every MCP request/response used by an agent must have an audit record with sensitive content redacted according to company policy.

---

## 40. LLM Token and Cost Reporting

### 40.1 Required Totals

The run report includes:

```text
Total input tokens
Total output tokens
Total tokens
Total input cost
Total output cost
Total cost
Calls by agent
Calls by stage
Retries and failed calls
Cached results reused
```

### 40.2 MVP Pricing Assumption

When the project uses fixed configured pricing for GPT-5 mini, store the values with the run instead of relying on a future pricing lookup.

Example configured assumption:

```text
Input:  $0.25 per 1,000,000 input tokens
Output: $2.00 per 1,000,000 output tokens
```

Formulas:

```text
input_cost  = total_input_tokens  / 1,000,000 Ã— input_price_per_million
output_cost = total_output_tokens / 1,000,000 Ã— output_price_per_million
total_cost  = input_cost + output_cost
```

### 40.3 Pricing Versioning

Every run records:

```json
{
  "currency": "USD",
  "input_price_per_million": 0.25,
  "output_price_per_million": 2.0,
  "pricing_source": "mvp_configured_fixed_price",
  "pricing_effective_at_run_creation": "ISO-8601"
}
```

Changing configured pricing affects new runs only. Historical reports retain the assumption used for their calculations.

### 40.4 Budget Actions

```text
continue
warn
block_new_llm_calls
use_deterministic_fallback
diagnostic_hold
require_approval
```

Budget exhaustion must never authorize an unvalidated patch. The workflow either continues deterministically or stops safely.

---

## 41. Final Reports and User Output

### 41.1 Published Application

```text
<target-output-path>/migrated-app/
```

### 41.2 Final Evidence Directory

```text
<resolved-output-root>/.migration-factory/runs/<run-id>/reports/
```

### 41.3 Required Final Artifacts

```text
final_migration_evidence_report.md
executive_summary.md
technical_upgrade_summary.md
stage_summary.json
final_diff.patch
changed_file_risk_summary.json
functional_parity_status.md
manual_actions_required.md
accepted_risks.json
unresolved_blockers.json
source_integrity_report.json
security_protocol_compliance.md
llm_usage_and_cost_summary.md
delivery_manifest.json
```

### 41.4 Report Integrity Rules

The Report Agent must:

- use persisted artifacts only;
- identify unexecuted and deferred checks;
- distinguish pre-existing and migration-caused failures;
- distinguish technical success and functional parity;
- show exact versions and runtime profiles;
- show approvals and accepted risks;
- show repair attempts and rollbacks;
- show source-integrity result;
- show the exact delivery location and manifest hash;
- refuse generation when essential evidence is missing or inconsistent.

### 41.5 Final User Actions

The Control Tower exposes:

```text
Open migrated application folder
Open final report
Open technical logs
Open final diff
Review manual parity checklist
Export report when PDF/DOCX support is enabled
Start a new run from the same source snapshot
```

---

## References Used for Workflow Decisions

- Angular version compatibility and browser support policy.
- Angular versioning, support windows, and one-major-at-a-time update policy.
- Angular CLI `ng update` command behavior and options.
- Angular application build-system migration guidance.
- npm clean-install behavior for lockfile-based projects.
- Internal AI Migration â€” Angular architecture study and MVP security constraints.
