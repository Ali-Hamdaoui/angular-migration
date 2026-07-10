# Angular Migration Control Tower — Enhanced MVP Workflow Specification

## 1. Purpose

This document defines the enhanced workflow for the **Angular Migration Control Tower MVP**.

The goal of the MVP is to migrate an Angular frontend application from an **Angular 18.x family version** to **Angular 21.x** while preserving **strict functional parity**.

The migration concerns only the Angular frontend. The backend application remains unchanged.

The workflow must be **version-range aware**. Angular `18.0.x`, `18.1.x`, and `18.2.x` must all be accepted as Angular 18 family projects. The system must not be hardcoded to a single patch version such as `18.2.x`.

The product must behave simply for the user, but strictly and safely internally.

User-visible flow:

```text
Source path → Target path → Target Angular version → Start Migration → Watch progress → Open migrated app
```

Backend-controlled flow:

```text
Eligibility → Baseline → Analysis → Approval → Compatibility Resolution → Planning → Approval → Stage Toolchain Profiles → Transformation → Static Symbol Verification → Build Validation → Repair → Checkpoint → Final Report
```

---

## 2. MVP Scope

### 2.1 In Scope

The MVP supports:

- Angular 11 and later source projects.
- MVP reference migration: Angular 18.x → Angular 21.x.
- One-major-version-at-a-time migration.
- Strict compatibility migration.
- Sandbox-only mutation.
- Dynamic compatibility resolution.
- Stage-by-stage validation.
- Low-risk repair automation.
- Final evidence reporting.
- AI Assistant support based on workflow state and generated artifacts.
- Azure OpenAI / GPT-5 mini usage through a backend LLM Gateway.
- LLM token and cost reporting.

### 2.2 Out of Scope

The MVP does not support:

- AngularJS 1.x migration.
- Angular 2–10 migration.
- Backend migration.
- UI redesign.
- Business logic refactoring.
- API contract changes.
- Authentication or authorization changes.
- State-management replacement.
- Automatic standalone migration.
- Automatic signals migration.
- Automatic new control-flow migration.
- Automatic zoneless migration.
- Unapproved browser, security, or quality tools.

### 2.3 Excluded MVP Tools

The following tools must not be used in the MVP unless the architecture is explicitly updated later:

```text
Playwright
Cypress
OSV scanner
Snyk
SonarQube
Semgrep
```

Browser, visual, security, and quality gates are reported as **manual** or **deferred company-tool-required** gates.

---

## 3. Core Product Principles

| Principle | Meaning |
|---|---|
| Strict parity first | The migrated app must preserve the same UI, behavior, routes, API calls, business rules, validation behavior, and expected outputs. |
| Compatibility before modernization | The default goal is technical migration, not redesign or modernization. |
| Minimal diff | Apply the smallest safe change required to install, build, and run on the target Angular version. |
| One major version at a time | Angular 18 → 19 → 20 → 21, instead of jumping directly from 18 to 21. |
| Backend unchanged | The Java/Spring Boot backend remains untouched. |
| Sandbox-only mutation | The original source folder must never be mutated. |
| Backend execution authority | Agents and LLMs may propose actions, but only the backend validates and executes them. |
| Backend-owned state | The frontend must not infer workflow status locally. |
| Validation-gated progress | A stage cannot complete without mandatory validation or explicit accepted risk. |
| Controlled repair | The Repair Agent can perform only low-risk technical compatibility repairs, maximum three attempts per stage. |
| Traceability | Every command, patch, validation, approval, repair, rollback, and final result must be persisted as an artifact. |
| Version-range awareness | Exact patch versions are detected, but planning uses version families such as Angular 18.x, 19.x, 20.x, and 21.x. |

---

## 4. Main Product Experience

The user experience is divided into two main interfaces:

1. **Migration Setup Page**
2. **Migration Progress / Control Tower Page**

The setup page captures migration inputs.

The Control Tower page allows the user to:

- Monitor the migration.
- See current stage and agent status.
- Inspect validation results.
- Review manual/deferred gates.
- Approve or reject gates when required.
- Open generated reports.
- Chat with the AI Assistant about the current migration.
- Cancel the migration if needed.

---

## 5. Migration Setup Page

### 5.1 User Inputs

| Field | Description | Example |
|---|---|---|
| Legacy application path | Local path to the source Angular application. | `C:\projects\legacy-angular-app` |
| Target output path | Local folder where the migrated solution and migration artifacts will be stored. | `C:\migrations\legacy-angular-app-angular21` |
| Target Angular version | Selected from approved target versions. For MVP, only Angular 21.x is available. | `Angular 21.x` |
| Migration mode | Default migration mode. | `Strict Compatibility / Strict Parity` |
| Optional auto-approval mode | Bypasses eligible low-risk approval gates only when policy allows it. | `Auto Approval OFF` by default |

### 5.2 Setup Page Layout

```text
--------------------------------------------------
Angular Migration Factory
--------------------------------------------------
Legacy Angular app path: [____________________]
Target output path:      [____________________]
Target Angular version:  [Angular 21.x        v]
Migration mode:          [Strict Compatibility]
Auto approval:           [OFF]

[Validate Paths]  [Start Migration]
--------------------------------------------------
```

### 5.3 Input Validation Before Start

Before enabling `Start Migration`, the backend should validate:

- The legacy path exists.
- The legacy path is readable.
- The legacy path contains an Angular project.
- `package.json` exists.
- Angular version can be detected.
- Angular major version is 11 or later.
- AngularJS indicators are not dominant.
- `angular.json` exists or the project can still be confidently classified as Angular.
- The target path exists or can be created.
- The target path is writable.
- The target path does not overwrite the original source project.
- The selected target version is available in the approved target list.
- The source and target paths are not the same folder.

Example validation failure:

```text
The selected source path is not eligible.
Reason: Angular version could not be detected from package.json.
```

Example target path failure:

```text
The selected target path is unsafe.
Reason: Target path cannot be the same as the source project path.
```

---

## 6. Target Output Folder Structure

The original source folder must remain read-only. The migration work happens inside the target output path.

Recommended structure:

```text
<target-output-path>/
  migrated-app/
    # Final migrated Angular application

  .migration-factory/
    runs/
      <run-id>/
        00_job_setup/
        01_baseline/
        02_analysis/
        03_planning/
        04_workflow_state/
        05_sandbox_transform/
        06_validation/
        07_repair/
        08_final/
```

### 6.1 Folder Meaning

| Folder | Purpose |
|---|---|
| `migrated-app/` | The final migrated Angular solution that the user can open after migration. |
| `.migration-factory/runs/<run-id>/` | Internal run folder containing artifacts, logs, state, validation results, repair reports, and final reports. |
| `00_job_setup/` | Eligibility result, target policy, read-only verification, setup request, LLM provider config redacted. |
| `01_baseline/` | Baseline versions, baseline build/test/lint results, baseline routes, backend contract snapshot, manual notes. |
| `02_analysis/` | Angular workspace analysis, dependency audit, package inventory, route inventory, backend integration inventory. |
| `03_planning/` | Compatibility resolution, upgrade ladder, stage toolchain profiles, command registry, migration plan, approval request. |
| `04_workflow_state/` | Run state, stage state history, agent execution history, approval events, AI chat events, LLM interaction logs, rollback events. |
| `05_sandbox_transform/` | Applied migrations, patch ledger, command outputs, diffs, changed-file risk classification. |
| `06_validation/` | Install/build/test/lint/static symbol/backend config validation reports. |
| `07_repair/` | Repair attempts, repair diagnoses, patch proposals, repair risk decisions, escalation requests. |
| `08_final/` | Final evidence report, manual actions, unresolved blockers, security protocol compliance, LLM usage summary. |

### 6.2 Key Artifact Rule

The user should mainly use:

```text
<target-output-path>/migrated-app/
```

The audit trail is stored separately in:

```text
<target-output-path>/.migration-factory/runs/<run-id>/
```

This keeps the final migrated app clean while preserving complete migration evidence.

---

## 7. Start Migration Action

When the user presses `Start Migration`, the frontend sends a migration request to the backend.

Example request:

```json
{
  "source_path": "C:\\projects\\legacy-angular-app",
  "target_output_path": "C:\\migrations\\legacy-angular-app-angular21",
  "target_angular_family": "21.x",
  "migration_mode": "strict_compatibility",
  "preserve_ui": true,
  "preserve_behavior": true,
  "preserve_business_logic": true,
  "preserve_api_contracts": true,
  "preserve_authentication_authorization": true,
  "allow_optional_modernization": false,
  "auto_approval_enabled": false
}
```

The backend then:

1. Creates a new `run_id`.
2. Persists the original setup request.
3. Creates the target output folder structure.
4. Copies the source Angular app into the target workspace.
5. Verifies that the original legacy path is not mutated.
6. Creates the initial workflow state.
7. Redirects the user to the Migration Progress / Control Tower page.

---

## 8. Enhanced End-to-End Workflow

The enhanced MVP workflow is:

```text
Create migration run
→ Validate source path and target path
→ Verify source is Angular 11+ and not AngularJS
→ Create target output structure
→ Copy source project into sandbox workspace
→ Mark original source as read-only
→ Capture strict parity constraints
→ Detect package manager and lockfile
→ Capture baseline versions, routes, backend config, scripts, and dependency inventory
→ Run baseline install/build/test/lint when possible
→ Run Analysis Agent
→ Generate dependency audit, package install script audit, route inventory, backend contract snapshot, and risk assessment
→ Wait for Analysis Approval
→ Run Compatibility Resolver
→ Generate dynamic upgrade ladder: Angular 18.x → 19.x → 20.x → 21.x
→ Generate stage toolchain profiles for Node.js, TypeScript, RxJS, Angular CLI, package manager, commands, validation gates, and rollback points
→ Generate migration plan and approved command registry
→ Wait for Plan Approval
→ For each stage:
   → select stage toolchain profile
   → verify sandbox and checkpoint
   → execute approved Angular update command
   → capture command output and diffs
   → run static symbol verification
   → run install validation
   → verify Angular target version
   → run build validation
   → run tests if configured
   → run lint if configured
   → recheck route inventory
   → recheck backend config and API-sensitive files
   → classify changed files by risk
   → repair low-risk migration-caused errors if needed, maximum three attempts
   → request human approval for high-risk or unclear changes
   → rollback patch or stage if needed
   → checkpoint completed stage
→ Generate final migration evidence report
→ Generate manual actions required
→ Generate unresolved blockers report if needed
→ Generate LLM usage and cost summary
→ Generate security protocol compliance summary
→ Mark migration as Completed, Completed with Manual Items, Completed with Accepted Risk, Failed, Cancelled, or Diagnostic Hold
```

---

## 9. Baseline Phase

### 9.1 Purpose

The baseline phase captures the state of the source Angular app before migration.

This protects the workflow from confusing pre-existing issues with migration-caused issues.

For example, if the Angular 18 app already has failing tests, the system should record this before attempting Angular 19 migration.

### 9.2 Baseline Steps

```text
Detect package manager
→ detect lockfile
→ capture Angular/CLI/TypeScript/RxJS/Node versions
→ capture package scripts
→ capture route inventory
→ capture environment and proxy config
→ capture backend contract snapshot
→ capture dependency inventory
→ run baseline install if safe
→ run baseline build if possible
→ run baseline tests if configured
→ run baseline lint if configured
→ store baseline status
```

### 9.3 Baseline Artifacts

```text
01_baseline/baseline_versions.json
01_baseline/baseline_package_scripts.json
01_baseline/baseline_routes.json
01_baseline/backend_contract_snapshot.json
01_baseline/baseline_install_report.json
01_baseline/baseline_build_report.json
01_baseline/baseline_test_report.json
01_baseline/baseline_lint_report.json
01_baseline/baseline_run_report.json
01_baseline/manual_baseline_notes.md
```

### 9.4 Baseline Failure Rule

If the baseline fails before migration, the workflow should not automatically stop unless the failure blocks analysis or migration.

Instead, it should record:

```text
baseline_status: failed_before_migration
```

Then the final report must clearly distinguish:

```text
Pre-existing issue
```

from:

```text
Migration-caused issue
```

---

## 10. Analysis Phase

### 10.1 Analysis Agent Responsibilities

The Analysis Agent performs read-only analysis of the Angular workspace.

It must detect:

- Angular version.
- Angular CLI version.
- TypeScript version.
- RxJS version.
- Zone.js version.
- Node.js runtime version if available.
- Package manager and lockfile.
- Workspace structure.
- Angular modules/components/routes.
- Existing tests.
- Existing lint setup.
- Build scripts.
- Environment files.
- Proxy configuration.
- Backend integration points.
- API base URLs.
- HTTP interceptors.
- Auth-sensitive frontend files.
- UI libraries such as Angular Material/CDK, PrimeNG, Bootstrap, internal UI kits.
- State management such as NgRx, Akita, NGXS, service-based stores, or custom stores.
- Custom builders.
- Private packages.
- Package install scripts.

### 10.2 Analysis Artifacts

```text
02_analysis/angular_workspace_analysis.json
02_analysis/package_inventory.json
02_analysis/dependency_graph.json
02_analysis/dependency_audit.json
02_analysis/private_package_inventory.json
02_analysis/package_install_script_audit.json
02_analysis/route_inventory.json
02_analysis/environment_inventory.json
02_analysis/backend_integration_inventory.json
02_analysis/material_cdk_inventory.json
02_analysis/test_inventory.json
02_analysis/lint_inventory.json
02_analysis/changed_file_sensitivity_rules.json
02_analysis/risk_assessment.json
```

### 10.3 Dependency Risk Categories

| Category | Meaning |
|---|---|
| `safe` | No special risk detected. |
| `needs_version_bump` | Package likely needs version alignment during upgrade. |
| `needs_migration_guide` | Package has known migration rules or breaking changes. |
| `requires_approval` | Package change may affect behavior or delivery. |
| `unknown_risk` | The risk cannot be determined automatically. |
| `blocking` | Package or dependency issue blocks automatic migration. |

### 10.4 Package Install Script Audit

Before dependency installation, the workflow should inspect package metadata and lockfiles where possible to identify scripts such as:

```text
preinstall
install
postinstall
prepare
```

These scripts must execute only inside the sandbox and must be reported in the final evidence.

---

## 11. Human Approval Gate 1 — Analysis Approval

After analysis, the workflow enters:

```text
WAITING_ANALYSIS_APPROVAL
```

The user can:

- Approve the analysis.
- Reject the migration.
- Request analysis modification.
- Approve with risk.

### 11.1 Analysis Approval Rules

The backend must verify:

- The approval is attached to the latest analysis artifact checksum.
- The workflow is currently waiting for analysis approval.
- The user decision is persisted as an approval event.
- The frontend and AI Assistant use the same backend approval endpoint.

### 11.2 Analysis Approval Artifact

```text
04_workflow_state/approval_events.json
```

Example approval event:

```json
{
  "approval_gate": "analysis",
  "approved_by": "user",
  "approval_source": "ui_button",
  "checksum": "sha256:analysis-artifact-checksum",
  "decision": "approved",
  "user_comment": "Analysis accepted. Continue to planning."
}
```

---

## 12. Compatibility Resolver

### 12.1 Purpose

The Compatibility Resolver converts exact detected versions into migration-ready version families and stage profiles.

It prevents the system from becoming a brittle script for one exact demo version.

Example:

```text
Angular 18.0.4 → Angular 18.x
Angular 18.1.7 → Angular 18.x
Angular 18.2.13 → Angular 18.x
```

All of them should resolve to the same major-version ladder when the target is Angular 21.x:

```text
Angular 18.x → Angular 19.x → Angular 20.x → Angular 21.x
```

### 12.2 Compatibility Resolver Responsibilities

The resolver must generate:

- Source Angular family.
- Source Angular major/minor/patch.
- Target Angular family.
- Target Angular major.
- One-major-at-a-time upgrade ladder.
- Compatible Node.js range per stage.
- Compatible TypeScript range per stage.
- Compatible RxJS range per stage.
- Angular CLI target per stage.
- Package manager behavior.
- Validation plan per stage.
- Rollback point per stage.

### 12.3 Compatibility Resolution Artifact

```text
03_planning/compatibility_resolution.json
```

Example:

```json
{
  "artifact": "03_planning/compatibility_resolution.json",
  "detected_versions": {
    "angular_core": "18.2.13",
    "angular_cli": "18.2.13",
    "typescript": "5.5.x",
    "rxjs": "7.8.x"
  },
  "normalized_versions": {
    "source_angular_family": "18.x",
    "source_angular_major": 18,
    "target_angular_family": "21.x",
    "target_angular_major": 21
  },
  "upgrade_ladder": [
    "angular-18-to-19",
    "angular-19-to-20",
    "angular-20-to-21"
  ],
  "decision": "compatible_profile_resolved"
}
```

---

## 13. Stage Toolchain Profiles

### 13.1 Purpose

Every migration stage must have an explicit toolchain profile.

The Transformation Agent and Build / Validation Agent must not guess versions or commands.

They must consume the approved stage profile generated by the Planning Agent and bound by checksum.

### 13.2 Stage Toolchain Profile Fields

| Field | Purpose |
|---|---|
| `stage_id` | Unique stage identifier, for example `angular-18-to-19`. |
| `source_angular_major` | Source major version for the stage. |
| `target_angular_major` | Target major version for the stage. |
| `node_range` | Allowed Node.js runtime range for the stage. |
| `typescript_range` | Required TypeScript range for the target Angular stage. |
| `rxjs_range` | Required RxJS range for the target Angular stage. |
| `angular_cli_target` | Angular CLI target selector, for example `^19`. |
| `package_manager_policy` | npm/yarn/pnpm behavior based on detected lockfile and company policy. |
| `command_plan` | Approved install, update, build, test, and lint commands. |
| `validation_plan` | Mandatory, conditional, manual, and deferred gates. |
| `rollback_point` | Checkpoint to restore if the stage fails. |

### 13.3 Example Stage Toolchain Profile

```json
{
  "stage_id": "angular-18-to-19",
  "source_angular_major": 18,
  "target_angular_major": 19,
  "angular_cli_target": "^19",
  "node_range": "resolved_from_compatibility_policy",
  "typescript_range": "resolved_from_compatibility_policy",
  "rxjs_range": "resolved_from_compatibility_policy",
  "package_manager": "npm",
  "update_command": "npx ng update @angular/core@^19 @angular/cli@^19",
  "validation_gates": [
    "install",
    "angular_version_check",
    "static_symbol_check",
    "build",
    "unit_tests_if_configured",
    "lint_if_configured",
    "route_inventory",
    "backend_config_check"
  ],
  "manual_gates": [
    "browser_smoke",
    "visual_parity"
  ],
  "deferred_gates": [
    "external_security_scan",
    "external_quality_scan"
  ],
  "rollback_point": "stage_start_checkpoint"
}
```

---

## 14. Planning Phase

### 14.1 Planning Agent Responsibilities

The Planning Agent generates a controlled migration plan based on:

- Approved analysis.
- Compatibility resolution.
- Source Angular family.
- Target Angular family.
- Dependency audit.
- Backend contract snapshot.
- Strict parity constraints.
- MVP excluded-tool policy.
- Company security constraints.

The Planning Agent must produce:

- Upgrade ladder.
- Stage toolchain profiles.
- Command registry.
- Validation gates.
- Allowed and forbidden changes.
- Repair policy.
- Rollback strategy.
- Approval request.

### 14.2 Planning Artifacts

```text
03_planning/compatibility_resolution.json
03_planning/upgrade_ladder.yaml
03_planning/stage_toolchain_profiles.json
03_planning/command_registry.json
03_planning/migration_plan.yaml
03_planning/migration_units.yaml
03_planning/allowed_and_forbidden_changes.yaml
03_planning/risk_assessment.json
03_planning/rollback_strategy.md
03_planning/approval_request.md
03_planning/llm_plan_rationale_summary.md
```

### 14.3 Allowed Changes

Allowed changes include only minimal technical compatibility changes, such as:

- Angular package version alignment.
- Angular CLI configuration updates required for compatibility.
- TypeScript/RxJS compatibility fixes.
- Deprecated API replacement required for build/runtime compatibility.
- Angular Material/CDK alignment if present and required.
- Test configuration update required for validation.
- Backend proxy/environment config preservation.

### 14.4 Forbidden Changes Without Approval

The plan must explicitly forbid:

```text
standalone_migration
signal_api_migration
new_control_flow_migration
inject_function_style_refactor
zoneless_migration
ui_redesign
business_logic_change
api_contract_change
authentication_authorization_change
state_management_replacement
introduction_of_unapproved_external_tools
```

---

## 15. Human Approval Gate 2 — Plan Approval

After planning, the workflow enters:

```text
WAITING_PLAN_APPROVAL
```

The user can:

- Approve the plan.
- Reject the migration.
- Request plan modification.
- Approve with risk.

### 15.1 Plan Approval Rules

The backend must verify:

- The approved plan checksum is current.
- The upgrade ladder checksum is current.
- The allowed/forbidden changes checksum is current.
- The command registry checksum is current.
- The workflow is currently waiting for plan approval.
- No transformation starts before approval.

### 15.2 Auto Approval Rule

If auto approval is enabled, it may bypass only approval gates that are explicitly classified as safe by backend policy.

Auto approval must not bypass:

- Initial plan approval if company policy requires human validation.
- `--force` usage.
- Dependency replacement.
- Auth/interceptor/guard changes.
- API contract changes.
- UI behavior changes.
- Form validation changes.
- Security-sensitive files.
- Failed static symbol verification.
- Repeated repair failure.
- Low-confidence LLM patch proposals.

Auto approval must be read from backend state throughout the whole migration. The workflow must not read it only once at migration start.

---

## 16. Command Registry and Command Safety

### 16.1 Purpose

The command registry defines which commands agents may request.

Agents do not execute shell commands directly.

The backend validates every command before execution.

### 16.2 Approved Command Registry

Example:

```json
{
  "stage_id": "angular-18-to-19",
  "allowed_commands": [
    {
      "id": "ng_update_angular_19",
      "command": "npx ng update @angular/core@^19 @angular/cli@^19",
      "working_directory": "sandbox_workspace",
      "requires_approval": false
    },
    {
      "id": "install_dependencies",
      "command": "npm install",
      "working_directory": "sandbox_workspace",
      "requires_approval": false
    },
    {
      "id": "build_application",
      "command": "npm run build",
      "working_directory": "sandbox_workspace",
      "requires_approval": false
    }
  ]
}
```

### 16.3 Forbidden Commands by Default

The backend must reject by default:

```text
ng update --force
npm install --force
npm install --legacy-peer-deps
pnpm install --force
yarn install --force
standalone migration commands
signals migration commands
new control-flow migration commands
zoneless migration commands
unapproved package replacement
unapproved external scanner execution
commands outside the sandbox workspace
commands not present in the approved command registry
```

### 16.4 Force Flag Rule

If a command requires `--force`, the workflow must stop and enter:

```text
WAITING_APPROVAL
```

The final report must record:

- Why `--force` was needed.
- Who approved it.
- What risk was accepted.
- Which stage was affected.

---

## 17. Stage-Based Migration View

For the MVP reference case, the dynamically generated stages are:

```text
Stage 1: Angular 18.x → Angular 19.x
Stage 2: Angular 19.x → Angular 20.x
Stage 3: Angular 20.x → Angular 21.x
```

These stages are generated by the Compatibility Resolver. They must not be hardcoded to Angular `18.2.x`.

### 17.1 Stage Statuses

| Status | Meaning |
|---|---|
| `Pending` | Stage has not started yet. |
| `Running` | Stage is currently active. |
| `Completed` | Mandatory technical gates passed and no unresolved manual/accepted-risk item affects completion. |
| `Completed with Manual Items` | Technical gates passed, but MVP manual/deferred gates remain documented. |
| `Completed with Accepted Risk` | A risk or missing validation was explicitly accepted and recorded. |
| `Failed` | Stage failed and cannot continue automatically. |
| `Repairing` | Repair Agent is trying to fix a technical migration error. |
| `Waiting Approval` | Human approval or accepted risk is required. |
| `Rolled Back` | Stage was reverted to a previous checkpoint. |
| `Diagnostic Hold` | Automation stopped safely and preserved the failed state for investigation. |
| `Cancelled` | The user cancelled the migration during this stage. |

### 17.2 Stage Card Example

```text
Stage 1 — Angular 18.x → Angular 19.x
Status: Running
Current Agent: Build / Validation Agent
Repair Attempts: 0/3
Mandatory Gates: install, Angular version check, static symbol check, build, route inventory, backend config check
Conditional Gates: tests if configured, lint if configured
Manual Gates: browser smoke, visual parity
Deferred Gates: external security scan, external quality scan
```

---

## 18. Detailed Stage Lifecycle

Each Angular major-version stage executes this lifecycle:

```text
1. Create stage state
2. Select stage toolchain profile
3. Verify sandbox workspace
4. Audit dependencies and package install scripts
5. Confirm MCP policy for the stage
6. Create stage-start checkpoint
7. Execute approved Angular update command
8. Capture command output, changed files, package diff, and lockfile diff
9. Run static symbol verification
10. Run install validation
11. Run Angular version check
12. Run build validation
13. Run existing tests if configured
14. Run existing lint if configured
15. Rebuild route inventory
16. Recheck backend configuration references
17. Classify changed files by risk
18. If validation fails, enter Repair Agent loop
19. If risky changes are detected, enter Waiting Approval
20. If mandatory gates pass, create stage checkpoint
21. Mark stage as Completed, Completed with Manual Items, or Completed with Accepted Risk
```

### 18.1 Stage 1 Example

```text
Stage 1: Angular 18.x → Angular 19.x
→ select Angular 19 toolchain profile
→ checkpoint before stage
→ run approved Angular 19 update command
→ validate install/build/static symbols
→ repair if needed
→ checkpoint if valid
```

### 18.2 Stage 2 Example

```text
Stage 2: Angular 19.x → Angular 20.x
→ select Angular 20 toolchain profile
→ checkpoint before stage
→ run approved Angular 20 update command
→ validate install/build/static symbols
→ repair if needed
→ checkpoint if valid
```

### 18.3 Stage 3 Example

```text
Stage 3: Angular 20.x → Angular 21.x
→ select Angular 21 toolchain profile
→ checkpoint before stage
→ run approved Angular 21 update command
→ align target TypeScript/RxJS/CLI policy
→ validate install/build/static symbols
→ repair if needed
→ checkpoint if valid
```

---

## 19. Agent Status View Under Each Stage

Under every stage, the user should see the agents involved in that stage and their statuses.

### 19.1 Pre-Stage Agents

| Agent | Role |
|---|---|
| Eligibility and Constraint Agent | Confirms the project is Angular 11+ and records strict parity constraints. |
| Baseline Agent | Captures baseline versions, routes, backend contract, scripts, and baseline validation status. |
| Analysis Agent | Analyzes Angular version, dependencies, routes, build config, tests, backend integration, and risks. |
| Compatibility Resolver | Generates source/target version families, upgrade ladder, and compatibility profiles. |
| Planning Agent | Generates the migration plan, stage toolchain profiles, validation gates, command registry, and rollback strategy. |

### 19.2 Stage Agents

| Agent / Gate | Role |
|---|---|
| Transformation Agent | Runs approved Angular upgrade commands and applies approved compatibility changes in sandbox. |
| Static Symbol Verification Gate | Checks imports, symbols, Angular APIs, template references, and unapproved dependencies after patches. |
| Build / Validation Agent | Runs install, version check, build, existing tests, existing lint, route inventory, backend config checks, and validation reporting. |
| Repair Agent | Fixes low-risk migration-caused technical errors with a maximum of three attempts per stage. |
| Checkpoint Step | Creates a safe checkpoint when a stage passes validation or accepted risk is recorded. |

### 19.3 Final Agent

| Agent | Role |
|---|---|
| Report Agent | Generates the final migration evidence report, manual actions, unresolved blockers, security compliance, and LLM usage summary. |

### 19.4 Agent Statuses

| Status | Meaning |
|---|---|
| `Pending` | Agent has not started yet. |
| `Running` | Agent is currently executing. |
| `Completed` | Agent completed successfully. |
| `Completed with Manual Items` | Technical gates passed, but manual/deferred gates remain documented. |
| `Completed with Accepted Risk` | Agent completed after explicit risk acceptance. |
| `Failed` | Agent failed. |
| `Blocked` | Agent cannot continue due to missing input, environment, package, approval, or unclear expected behavior. |
| `Waiting Approval` | User decision is required. |
| `Skipped` | Agent was intentionally skipped because it was not configured or not applicable. |

---

## 20. Workflow State Ownership

The frontend must not infer workflow status locally.

The backend state store is the single source of truth for:

- Current run status.
- Current stage.
- Current agent.
- Stage status.
- Agent status.
- Repair attempt count.
- Approval requirements.
- Manual/deferred gate status.
- Auto-approval mode.
- Cancel request status.
- Resume eligibility.
- Final completion status.

The UI should poll or subscribe to backend state updates and render cards from that state.

### 20.1 Core Run States

```text
CREATED
CLIENT_CONSTRAINTS_CAPTURED
ELIGIBILITY_RUNNING
ELIGIBILITY_FAILED
BASELINE_RUNNING
BASELINE_COMPLETED
ANALYSIS_RUNNING
ANALYSIS_COMPLETED
WAITING_ANALYSIS_APPROVAL
PLANNING_RUNNING
PLANNING_COMPLETED
WAITING_PLAN_APPROVAL
STAGE_RUNNING
TRANSFORMATION_RUNNING
STATIC_SYMBOL_CHECK_RUNNING
VALIDATION_RUNNING
BUILD_RUNNING
BUILD_FAILED
REPAIR_RUNNING
REPAIR_COMPLETED
REPAIR_FAILED
WAITING_REPAIR_APPROVAL
STAGE_COMPLETED
REPORT_RUNNING
COMPLETED
COMPLETED_WITH_MANUAL_ITEMS
COMPLETED_WITH_ACCEPTED_RISK
FAILED
CANCEL_REQUESTED
CANCELLED
DIAGNOSTIC_HOLD
```

### 20.2 Enhanced Stage States

```text
STAGE_CREATED
TOOLCHAIN_PROFILE_SELECTED
SANDBOX_READY
DEPENDENCY_AUDITED
MCP_CONTEXT_POLICY_RESOLVED
STAGE_CHECKPOINT_CREATED
TRANSFORMATION_RUNNING
STATIC_SYMBOL_CHECK_RUNNING
INSTALL_VALIDATION_RUNNING
ANGULAR_VERSION_CHECK_RUNNING
BUILD_VALIDATION_RUNNING
TEST_VALIDATION_RUNNING
LINT_VALIDATION_RUNNING
ROUTE_VALIDATION_RUNNING
BACKEND_CONFIG_VALIDATION_RUNNING
CHANGED_FILE_RISK_CLASSIFICATION_RUNNING
VALIDATION_PASSED
REPAIR_RUNNING
WAITING_APPROVAL
STAGE_COMMITTED
STAGE_ROLLED_BACK
DIAGNOSTIC_HOLD
CANCELLED
```

---

## 21. Validation Gates for MVP

### 21.1 Mandatory Gates

| Gate | Description |
|---|---|
| Install validation | Dependency installation succeeds using the detected package manager. |
| Angular version check | Angular version is updated to the expected stage target. |
| Static symbol verification | Imports, symbols, Angular APIs, templates, and dependencies are checked after patches. |
| Build validation | Angular build succeeds. |
| Route inventory | Angular routes are detected and documented. |
| Backend config check | Environment files, proxy config, API base URLs, and auth-sensitive config references are inspected. |
| Backend contract comparison | API-sensitive frontend references are compared against baseline. |
| Diff generation | Changed files are captured. |
| Changed-file risk classification | Changed files are classified by risk before auto-continuation. |

### 21.2 Conditional Gates

| Gate | Description |
|---|---|
| Existing tests | Run only if already configured in the project. |
| Existing lint | Run only if already configured in the project. |

### 21.3 Manual / Deferred Gates

| Gate | MVP Status |
|---|---|
| Browser smoke | `manual_validation_required` |
| Visual parity | `manual_validation_required` |
| External security scan | `deferred_company_tool_required` |
| External quality scan | `deferred_company_tool_required` |

### 21.4 Validation Status Vocabulary

Validation results must use explicit statuses:

```text
passed
failed
not_configured
manual_validation_required
deferred_company_tool_required
blocked_by_environment
accepted_risk
skipped_not_applicable
```

### 21.5 Stage Definition of Done

A stage can be completed only when:

- Install succeeds or an environment blocker is documented and accepted.
- Angular version is updated for the current stage.
- Static symbol verification passes.
- Build succeeds.
- Existing tests pass, or absence/not-configured status is documented.
- Existing lint passes, or absence/not-configured status is documented.
- Route inventory is generated.
- Backend config check is generated.
- Backend contract comparison is generated.
- Changed-file risk classification is generated.
- Manual browser/visual parity checklist is generated.
- External security/quality gates are marked deferred for company tooling.
- Repair history is recorded if repair was used.
- Diff is generated and classified.
- Human accepted risk is recorded if any required gate cannot be executed.

---

## 22. Static Symbol Verification Gate

### 22.1 Purpose

Static Symbol Verification is a deterministic anti-hallucination gate.

It prevents the workflow from continuing with:

- Nonexistent imports.
- Phantom APIs.
- Invalid Angular symbols.
- Invalid RxJS imports.
- Invalid Angular Material/CDK APIs.
- Broken template references.
- Unapproved dependency additions.

### 22.2 Checks

| Check | Expected Result |
|---|---|
| Import resolution | All imports introduced or changed by the patch resolve locally. |
| Symbol existence | All referenced classes, functions, constants, decorators, and members exist. |
| Angular/RxJS/Material API validity | No phantom APIs or package names are introduced. |
| Template diagnostics | Changed templates pass Angular compiler/template diagnostics where available. |
| Dependency approval | No new dependency appears without approved plan or human approval. |
| Changed-file sensitivity | Changed files are classified before auto-continuation. |

### 22.3 Static Symbol Artifact

```text
06_validation/static_symbol_check_report.json
```

Example:

```json
{
  "artifact": "06_validation/static_symbol_check_report.json",
  "stage_id": "angular-18-to-19",
  "status": "passed",
  "checks": {
    "imports_resolve": true,
    "symbols_exist": true,
    "angular_template_diagnostics_clean": true,
    "no_phantom_packages": true,
    "no_unapproved_dependency_added": true
  }
}
```

---

## 23. Backend Contract Protection

### 23.1 Purpose

Because the backend remains unchanged, the frontend migration must not silently change how the Angular app communicates with the backend.

The workflow must compare backend-related frontend behavior before and after migration.

### 23.2 Backend Contract Snapshot

The baseline snapshot should capture:

- Environment API base URLs.
- Proxy configuration.
- HTTP interceptors.
- Auth header logic.
- Token or cookie usage.
- API service files.
- Request payload builders.
- Response mappers.
- Error handling logic.
- Guards, resolvers, and route-level authorization references.

### 23.3 Backend Contract Comparison

After each stage, the workflow should compare:

```text
baseline backend contract snapshot
vs
current stage backend contract snapshot
```

It should flag changes in:

- API URLs.
- Proxy configuration.
- Auth logic.
- Interceptors.
- Guards.
- Request payload structure.
- Response mapper behavior.
- Environment files.
- Security-sensitive frontend logic.

### 23.4 Backend Contract Rule

If a backend contract change is detected, the workflow must enter:

```text
WAITING_APPROVAL
```

or:

```text
DIAGNOSTIC_HOLD
```

unless the change is clearly mechanical and approved by the plan.

---

## 24. Changed-File Risk Classification

### 24.1 Purpose

Before a stage auto-continues, changed files must be classified by risk.

### 24.2 Risk Levels

| Risk | File Examples | Default Decision |
|---|---|---|
| Low | `package.json`, lockfile, `angular.json`, `tsconfig`, browser config, polyfills, test setup | May auto-continue if validation passes. |
| Medium | Routing modules, shared modules, RxJS-heavy services, Angular Material module files | Auto-continue only if approved plan allows and validation passes. |
| High | Auth services, interceptors, guards, permissions, API mappers, form validators, calculation/business services, environment files | Human approval required. |
| Blocked | Files where expected behavior cannot be determined or private package behavior is unknown | Diagnostic hold or escalation. |

### 24.3 Artifact

```text
05_sandbox_transform/changed_file_risk_classification.json
```

---

## 25. Repair Agent and Repair Loop

### 25.1 Repair Scope

The Repair Agent can fix low-risk migration-caused technical errors.

Allowed examples:

- Missing imports.
- Missing symbols.
- Simple TypeScript typing fixes caused by framework upgrade.
- Approved dependency alignment inside the migration plan.
- Angular configuration fixes required for compatibility.
- Test configuration updates required for validation.
- Known deprecated API replacements required for build/runtime compatibility.

### 25.2 Restricted Repair Scope

The Repair Agent must not automatically change:

- Business rules.
- Calculations.
- API payloads.
- Authentication logic.
- Authorization logic.
- Security-sensitive logic.
- UI appearance.
- Layout.
- State-management design.
- Tests to hide real behavior changes.

### 25.3 Repair Loop Rules

If validation fails:

```text
Read validation failure
→ classify failure
→ identify affected files
→ classify risk
→ propose smallest safe patch
→ apply patch in sandbox only
→ run static symbol verification
→ run targeted validation
→ run full stage validation
→ checkpoint if successful
```

Rules:

- Maximum three repair attempts per stage.
- Repair only inside the target workspace.
- Apply the smallest safe patch.
- Run static symbol verification after every patch.
- Re-run targeted validation first.
- Re-run full stage validation after targeted validation succeeds.
- Escalate high-risk or unclear behavior changes.
- Stop after repeated failure.

### 25.4 Repair Attempt Artifact

```text
07_repair/repair_attempts.json
```

Example:

```json
{
  "attempt": 1,
  "stage": "angular-18-to-19",
  "error_category": "missing_import",
  "impacted_files": ["src/app/app.routes.ts"],
  "diagnosis": "Route configuration references a component without importing it.",
  "repair_strategy": "Add missing import only. Do not change route path or behavior.",
  "risk_level": "low",
  "minimal_diff": true,
  "behavior_change_expected": false,
  "validation_result": "passed",
  "escalated_to_human": false
}
```

---

## 26. Rollback Behavior

Rollback must be explicit and auditable.

| Rollback Level | When Used | Action |
|---|---|---|
| Patch rollback | Last repair patch failed static symbol check or targeted validation. | Undo only the last patch. |
| Stage rollback | Current major stage became unstable. | Reset to stage start checkpoint. |
| Migration rollback | Migration must be abandoned or restarted. | Reset to original copied baseline. |
| Diagnostic hold | Failed state is useful for human investigation. | Stop automation and preserve failed workspace. |

### 26.1 Rollback Artifact

```text
04_workflow_state/rollback_events.json
```

Each rollback event must record:

- Run ID.
- Stage ID.
- Rollback level.
- Triggering failure.
- Files affected.
- Checkpoint restored.
- User approval if required.
- Result.

---

## 27. Auto-Continue and Human Approval Rules

### 27.1 Auto-Continue Allowed Only When

Automatic continuation is allowed only when:

- Official Angular migration or approved compatibility patch succeeded.
- Static symbol verification passed.
- Install and build passed.
- Existing tests and lint passed or were explicitly not configured.
- Diff is mechanical, config-only, or low-risk compatibility-only.
- No `--force` flag was used.
- No dependency replacement was made without approval.
- No business, auth, API, routing, form validation, security-sensitive, or UI behavior file changed.

### 27.2 Human Approval Required When

Human approval is required when:

- `--force` is needed.
- A dependency replacement is needed.
- Auth, interceptor, guard, permission, routing, form validation, API mapper, or environment behavior changes are involved.
- Material, CSS, theme, layout, or visual behavior files changed.
- Static symbol verification fails.
- Tests fail and expected output is unclear.
- The same error repeats after repair.
- LLM confidence is low.
- Behavior preservation cannot be proven.

---

## 28. Migration Progress / Control Tower Page

After starting the migration, the user is redirected to a dedicated progress page.

The page shows:

- Overall migration status.
- Source Angular version.
- Target Angular version.
- Current active stage.
- Stage cards.
- Agent cards under each stage.
- Validation gate summary.
- Repair attempts.
- Logs and summaries.
- Manual/deferred validation items.
- Approval actions.
- Cancel Migration button.
- AI Assistant chatbot icon.
- Final report link when completed.

### 28.1 Progress Page Layout

```text
--------------------------------------------------
Migration Run: run-001
Source: Angular 18.x
Target: Angular 21.x
Status: Running
Output: C:\migrations\legacy-angular-app-angular21
Auto Approval: OFF
--------------------------------------------------

Stages
[Running]   Stage 1: Angular 18.x → 19.x
[Pending]   Stage 2: Angular 19.x → 20.x
[Pending]   Stage 3: Angular 20.x → 21.x

Selected Stage: Angular 18.x → 19.x
--------------------------------------------------
Agents
[Completed] Transformation Agent
[Running]   Static Symbol Verification Gate
[Pending]   Build / Validation Agent
[Pending]   Repair Agent
[Pending]   Checkpoint
--------------------------------------------------
Validation Gates
[Pending] Install
[Pending] Angular Version Check
[Running] Static Symbol Check
[Pending] Build
[Not Configured] Tests
[Not Configured] Lint
[Manual] Browser Smoke
[Manual] Visual Parity
[Deferred] Security Scan
[Deferred] Quality Scan
--------------------------------------------------
Latest Summary
The Transformation Agent completed the approved Angular update command.
Static symbol verification is now checking imports, symbols, templates, and dependencies.
--------------------------------------------------
[Open AI Assistant]  [Cancel Migration]
--------------------------------------------------
```

---

## 29. Cancel and Resume Behavior

### 29.1 Cancel Migration

The user can cancel migration from the Control Tower page.

Cancel behavior:

```text
User clicks Cancel Migration
→ backend receives cancel request
→ orchestrator stops scheduling new agent work
→ current safe process is interrupted or allowed to finish safely depending on command type
→ run is marked CANCEL_REQUESTED then CANCELLED
→ artifacts and logs are preserved
→ original source remains unchanged
→ user can return to setup page
```

### 29.2 Cancel Rules

- Cancel must not delete the original source.
- Cancel must not hide artifacts.
- Cancel must not leave frontend state inconsistent with backend state.
- Cancel must stop future stages and agents.
- Cancel should preserve enough evidence to understand where the migration stopped.

### 29.3 Resume Migration

Resume may be allowed only from safe states:

```text
DIAGNOSTIC_HOLD
WAITING_APPROVAL
FAILED after repair
CANCELLED if workspace was preserved
```

Resume rules:

- Resume must reload state from backend state store.
- Resume must not infer state from frontend cards.
- Resume must verify artifact checksums.
- Resume must verify sandbox integrity.
- Resume must continue from the last safe checkpoint.

---

## 30. AI Assistant Chatbot Experience

The Migration Progress page includes a chatbot icon.

When the user clicks it, the AI Assistant opens and can answer questions about the current migration.

### 30.1 Assistant Capabilities

The AI Assistant can answer questions such as:

```text
What is happening now?
Which stage is currently running?
Why is Stage 1 taking time?
What files changed in Angular 18 → 19?
Did the build pass?
Why did the Repair Agent run?
What did the Repair Agent change?
What validations are manual for the MVP?
Where is the final migrated app located?
What are the remaining risks?
How many tokens were used so far?
What is the estimated LLM cost for this run?
```

### 30.2 Assistant Knowledge Sources

The Assistant must answer based on generated artifacts and backend state, not guesses.

It can read:

- Current workflow state.
- Stage state history.
- Agent execution history.
- Compatibility resolution.
- Stage toolchain profiles.
- Analysis artifacts.
- Planning artifacts.
- Command registry.
- Build and validation reports.
- Repair reports.
- Patch ledger and diffs.
- Backend contract snapshot and comparison.
- LLM usage logs.
- Final report artifacts.
- MCP Context Support outputs if available.

### 30.3 Assistant Restrictions

The AI Assistant must not:

- Execute commands directly.
- Modify files directly.
- Approve gates silently.
- Invent validation results.
- Claim a manual/deferred gate passed if it was not executed.
- Expand scope to modernization unless explicitly approved.
- Access raw secrets, tokens, API keys, or private credentials.

### 30.4 Assistant Example Answer

```text
The migration is currently in Stage 1: Angular 18.x to Angular 19.x.
The Transformation Agent has completed the approved Angular update command.
The Static Symbol Verification Gate is now checking imports, symbols, templates, and dependencies.
No repair attempt has been used yet.
The original source folder has not been modified; all changes are happening inside the target workspace.
```

---

## 31. LLM and Azure OpenAI Usage

### 31.1 LLM Provider

For the MVP:

- Azure OpenAI API is the LLM provider.
- GPT-5 mini is the default main LLM deployment.
- Agents access the model only through the backend LLM Gateway.
- Deployment name, endpoint, API version, and credentials must be backend configuration.
- The frontend and agents must never receive Azure OpenAI credentials.

### 31.2 LLM Usage Rules

Agents may use the LLM for:

- Reasoning summaries.
- Analysis summaries.
- Risk explanations.
- Planning narratives.
- Failure diagnosis.
- Patch proposals.
- Repair summaries.
- Final report generation.
- User-facing assistant answers.

The LLM must not:

- Execute commands.
- Modify files.
- Approve gates.
- Decide workflow transitions independently.
- Be the sole correctness gate.
- Receive secrets or unnecessary repository-wide context.

### 31.3 LLM Gateway Responsibilities

The backend LLM Gateway must:

- Centralize all Azure OpenAI calls.
- Redact secrets before sending context.
- Send targeted context only.
- Enforce token limits.
- Enforce timeout and retry policy.
- Require structured outputs for agent decisions.
- Log redacted LLM interactions.
- Store token usage if available.
- Support cost calculation.

### 31.4 LLM Artifacts

```text
00_job_setup/llm_provider_config_redacted.json
04_workflow_state/llm_interaction_log_redacted.json
03_planning/llm_plan_rationale_summary.md
06_validation/llm_failure_classification_summary.json
07_repair/llm_patch_proposals.json
08_final/llm_usage_summary.md
```

### 31.5 LLM Usage and Cost Summary

The final report should include:

```text
Total input tokens
Total output tokens
Total tokens
Input token cost
Output token cost
Total LLM cost
```

If the project uses hardcoded prices, the report should explicitly show the pricing assumptions.

Example:

```text
Pricing assumption:
Input:  $0.25 per 1M input tokens
Output: $2.00 per 1M output tokens
```

Example formula:

```text
input_cost = total_input_tokens / 1_000_000 * input_price_per_million
output_cost = total_output_tokens / 1_000_000 * output_price_per_million
total_cost = input_cost + output_cost
```

---

## 32. MCP Context Support Policy

### 32.1 MVP Policy

MCP is optional and disabled by default.

If approved, MCP is used only as read-only context support for the LLM.

It may provide:

- Angular documentation.
- Migration guidance.
- Best practices.
- Official examples.
- Explanation support.

### 32.2 Forbidden MCP Actions in MVP

MCP must not execute:

```text
ng update
build
test
lint
dev server
file mutation
workspace mutation
package installation
```

### 32.3 MCP Modes

| Mode | MVP Policy | Allowed Use | Forbidden Use |
|---|---|---|---|
| MCP Disabled Mode | Default | No MCP usage. | None. |
| MCP Context Support Mode | Optional, company-approved only | Read-only documentation and guidance context. | Command execution, file mutation, build/test/lint/devserver. |
| MCP Workspace Mode | Future only | Not part of MVP. | Must not bypass backend authority. |

### 32.4 MCP Artifact

```text
04_workflow_state/mcp_context_usage_log.json
```

Example:

```json
{
  "mode": "disabled | context_support | workspace_future",
  "policy_status": "disabled_by_default | approved_read_only | blocked",
  "used_for": ["documentation_lookup", "migration_guidance", "repair_reasoning"],
  "execution_actions_allowed": false
}
```

---

## 33. Build-System Migration Policy

Angular build-system changes can affect output structure, styles, SSR behavior, deployment, and custom builders.

For strict parity, the MVP must not treat build-system migration as optional modernization.

### 33.1 Rules

- Preserve the existing build architecture by default.
- Accept Angular CLI-required build configuration changes only when needed for compatibility.
- Do not migrate to a new builder as optional modernization unless explicitly approved.
- If Angular CLI proposes a build-system migration, record it as a plan decision.
- Require approval if the build-system change affects output structure, SSR behavior, custom builders, styles, or deployment assumptions.

### 33.2 Build-System Artifact

```text
03_planning/build_system_migration_decision.md
```

---

## 34. Final Output Expected by the User

When all stages pass, the user should be able to go to the target output path and find the migrated Angular solution.

Expected final app:

```text
<target-output-path>/migrated-app/
```

Expected final evidence:

```text
<target-output-path>/.migration-factory/runs/<run-id>/08_final/
```

This folder contains:

```text
final_migration_evidence_report.md
compatibility_upgrade_summary.md
manual_actions_required.md
unresolved_blockers.json
security_protocol_compliance.md
llm_usage_summary.md
final_report_export.pdf or .docx if enabled later
```

---

## 35. Final Run Statuses

| Final Status | Meaning |
|---|---|
| `Completed` | Migration completed and mandatory technical gates passed. |
| `Completed with Manual Items` | Migration completed technically, but manual/deferred MVP gates remain documented. |
| `Completed with Accepted Risk` | Migration completed after explicit accepted risk was recorded. |
| `Failed` | Migration could not complete. |
| `Cancelled` | User cancelled the migration. |
| `Diagnostic Hold` | Automation stopped safely and preserved failed state for investigation. |

---

## 36. Recommended Backend APIs

### 36.1 Create Migration Run

```http
POST /migrations
```

```json
{
  "source_path": "C:\\projects\\legacy-angular-app",
  "target_output_path": "C:\\migrations\\legacy-angular-app-angular21",
  "target_angular_family": "21.x",
  "migration_mode": "strict_compatibility",
  "auto_approval_enabled": false
}
```

### 36.2 Get Run State

```http
GET /migrations/{runId}/state
```

Returns:

```json
{
  "run_id": "run-001",
  "status": "running",
  "source_angular_family": "18.x",
  "target_angular_family": "21.x",
  "current_stage_id": "angular-18-to-19",
  "current_agent": "build_validation_agent",
  "auto_approval_enabled": false,
  "cancel_requested": false,
  "stages": [
    {
      "stage_id": "angular-18-to-19",
      "status": "running",
      "source_angular_major": 18,
      "target_angular_major": 19,
      "repair_attempts": 0,
      "max_repair_attempts": 3
    },
    {
      "stage_id": "angular-19-to-20",
      "status": "pending",
      "source_angular_major": 19,
      "target_angular_major": 20
    },
    {
      "stage_id": "angular-20-to-21",
      "status": "pending",
      "source_angular_major": 20,
      "target_angular_major": 21
    }
  ]
}
```

### 36.3 Submit Approval

```http
POST /migrations/{runId}/approvals
```

```json
{
  "approval_gate": "analysis | planning | repair | accepted_risk",
  "approval_source": "ui_button | assistant_command",
  "checksum": "sha256:...",
  "decision": "approved | rejected | modification_requested | approved_with_risk",
  "user_comment": "optional"
}
```

### 36.4 Chat With AI Assistant

```http
POST /migrations/{runId}/assistant/chat
```

```json
{
  "message": "What is happening now in the migration?"
}
```

The assistant should answer using backend state and artifacts.

### 36.5 Get Artifact

```http
GET /migrations/{runId}/artifacts/{artifactPath}
```

Used by the UI to open:

- Reports.
- Logs.
- Diffs.
- Validation results.
- Repair reports.
- Final evidence.

### 36.6 Cancel Migration

```http
POST /migrations/{runId}/cancel
```

```json
{
  "reason": "User cancelled migration from Control Tower UI."
}
```

### 36.7 Resume Migration

```http
POST /migrations/{runId}/resume
```

```json
{
  "resume_from": "last_safe_checkpoint"
}
```

---

## 37. Definition of a Successful MVP Workflow

The MVP workflow is successful when:

- The user can enter a local Angular source path.
- The user can enter a target output path.
- The user can select Angular 21.x as the target.
- The system validates source and target paths.
- The source is confirmed as Angular 11+.
- AngularJS/pre-Angular-11 projects are rejected.
- The original legacy app folder is not mutated.
- The target workspace is created safely.
- Baseline state is captured before migration.
- The user is redirected to a migration progress page after starting.
- The progress page shows backend-driven stage cards from Angular 18.x to Angular 21.x.
- Each stage shows pending, running, completed, failed, repairing, waiting approval, diagnostic hold, or cancelled status.
- Each stage shows agent-level statuses.
- A dynamic upgrade ladder is generated by the Compatibility Resolver.
- Stage toolchain profiles are generated and used.
- Commands are validated by the backend command registry.
- Transformation starts only after plan approval.
- Each stage runs install, Angular version check, static symbol verification, build, route inventory, and backend config validation.
- Existing tests and lint run only if configured.
- Manual and deferred gates are visible, not hidden.
- The Repair Agent performs only low-risk compatibility repairs, maximum three attempts per stage.
- High-risk changes wait for human approval.
- Cancel migration works safely.
- The AI Assistant answers based on backend state and artifacts.
- LLM usage and cost are recorded.
- The target output path contains the migrated app.
- The final report explains what happened, what changed, what passed, what was manual/deferred, what risks were accepted, and what remains unresolved.

---

## 38. Key Product Rule

The system must be simple for the user and strict internally.

The user sees:

```text
Source path → Target path → Target Angular version → Start Migration → Watch progress → Open migrated app
```

The backend controls:

```text
Eligibility
→ Baseline
→ Analysis
→ Approval
→ Compatibility Resolution
→ Planning
→ Approval
→ Stage Toolchain Profiles
→ Transformation
→ Static Symbol Verification
→ Build Validation
→ Backend Contract Check
→ Repair
→ Risk Classification
→ Checkpoint
→ Final Report
```

This separation keeps the product easy to use while preserving the reliability, traceability, and safety required for an enterprise Angular migration factory.
