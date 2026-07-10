**AI Frontend Migration Factory**

Angular 11+ Compatibility Migration  
Reliable, Reproducible, and Auditable Agent Architecture

**Scope:** Angular 11+ technical compatibility upgrade with strict functional-parity controls  
**MVP reference:** Angular 18.x → Angular 21.x, backend unchanged, version-range aware  
**Architecture stack:** FastAPI, LangGraph, SQLite for the single-node MVP, local artifact store, sandbox worker, Server-Sent Events, Next.js, Azure OpenAI LLM Gateway  
**LLM deployment:** GPT-5 mini as the configurable default deployment

**Updated after architecture audit:** 2026-07-10

Prepared for architecture review, implementation planning, backlog generation, and MVP delivery.

# Document Control

| Item | Decision / Value |
|---|---|
| Document purpose | Define an implementable architecture for an Angular migration factory, including deterministic services, bounded AI agents, workflow state, secure execution, evidence, recovery, validation, and delivery. |
| Primary scope | Angular 11 and later. AngularJS and pre-Angular-11 applications are out of scope. Complex workspaces may be classified as unsupported by the MVP even when their Angular version is eligible. |
| MVP reference | Angular 18.x → Angular 21.x. Angular 21 is the fixed POC target selected by the project; it must not be described as the latest Angular release. |
| Migration objective | Technical compatibility upgrade with the minimum required changes. Modernization remains a separate, explicitly approved capability. |
| Assurance model | Technical upgrade success, functional parity, security assurance, and delivery readiness are tracked independently. A successful build alone does not prove functional parity. |
| Historical-version policy | Unsupported Angular source or intermediate versions are processed only through an internally validated historical compatibility catalog and receive an explicit support level. |
| Baseline policy | No transformation starts before a baseline qualification captures the original install, build, test, lint, route, API, configuration, and known-failure state. |
| Runtime policy | Every migration stage uses an explicit, isolated, exact-version toolchain profile with an immutable runtime-image digest or equivalent reproducible environment definition. |
| Mutation policy | The original source remains read-only. All mutation occurs inside an isolated sandbox copy. |
| Execution authority | Agents submit structured action requests. The backend validates executable, arguments, paths, environment, network, approval, and policy before execution. Arbitrary shell strings are forbidden. |
| MVP tool exclusions | Playwright, Cypress, OSV scanner, Snyk, SonarQube, and Semgrep are excluded from the current MVP. Their gates are manual or deferred and are never reported as passed when not executed. |
| LLM policy | The LLM is optional for deterministic components. It supports explanation, planning narrative, ambiguous diagnosis, bounded patch proposals, and reporting through the backend LLM Gateway. |
| State policy | Backend state and persisted events are the source of truth. Transitions use state versions, idempotency keys, worker leases, checkpoints, and recovery rules. |
| Artifact policy | Artifacts are immutable, checksum-bound, schema-versioned, and organized by run, stage, and repair attempt. |
| MVP database | SQLite with WAL is acceptable only for a single-host, limited-concurrency MVP. PostgreSQL is required before distributed or multi-instance execution. |

# Table of Contents

- 1. Executive Summary
- 2. Architecture Principles
- 3. Angular Version Support and Historical Compatibility Policy
- 4. Version-Range Compatibility and Dynamic Version Resolution
- 5. Compatibility Resolver and Stage Toolchain Profiles
- 6. Source Intake, Workspace Topology, and Baseline Qualification
- 7. Target System Architecture
- 8. Toolchain Runtime Manager and Reproducible Execution
- 9. Sandbox, Command, and Package Execution Security
- 10. MCP Context Support Policy
- 11. Agent Execution Model
- 12. Common Agent Contract
- 13. Agent Catalog and Responsibility Matrix
- 14. Detailed Agent Specifications
- 15. Workflow State Management
- 16. Artifact Model and Audit Trail
- 17. Tooling Policy and MVP Restrictions
- 18. Validation Gates and Definition of Done
- 19. Functional Parity Assurance, Browser Support, and Build-System Policy
- 20. Dependency Audit, Install Script Audit, and Backend Contract Snapshot
- 21. Repair Policy, Rollback, and Escalation Rules
- 22. Azure OpenAI LLM Assistance Layer and Per-Agent LLM Access
- 23. AI Quality Evaluation and Regression Suite
- 24. Observability, Token Usage, Cost, Quotas, and Operations
- 25. API and Schema Examples
- 26. Delivery and Handover
- 27. MVP Implementation Recommendation
- 28. Prioritized Implementation Plan
- 29. Roadmap and Future Extensions
- Appendix A. Example Artifact Schemas
- Appendix B. Glossary
- References

# 1. Executive Summary

This document defines the detailed architecture of the Angular 11+ Compatibility Migration Factory from an agentic execution perspective. The factory is designed to upgrade Angular applications from version 11 or later to a client-approved supported target version while preserving strict functional parity.

The system must not be treated as a generic modernization tool. Its default behavior is compatibility migration only. Any redesign, standalone migration, signals migration, new control-flow migration, state-management replacement, API contract change, authentication change, or business-logic refactor is blocked unless explicitly approved.

The architecture uses a small number of specialized agents. Each agent has a limited responsibility, a controlled input contract, a structured output contract, allowed tools, forbidden actions, generated artifacts, and escalation rules. The backend remains the execution authority: agents can request actions, but the backend validates and executes them inside a sandbox workspace only.

## 1.1 MVP Design Direction

- Use a single Angular 11+ compatibility upgrade path.

- For the current POC, execute Angular 18 → 19 → 20 → 21 as staged upgrades.

- Keep the backend unchanged; only the Angular frontend is in scope.

- Use official Angular CLI and package-manager commands before LLM reasoning.

- Use existing project test and lint commands only if already configured.

- Do not introduce Playwright, Cypress, OSV, Snyk, SonarQube, or Semgrep in the MVP.

- Generate manual/deferred validation items where company-approved tools are not available.

- Persist every analysis, approval, command, patch, validation result, repair attempt, and report artifact.

## 1.2 Updated Assurance Direction

The revised architecture adds five mandatory controls that were previously under-specified:

1. a source-compatible baseline qualification before any mutation;
2. explicit historical support levels for unsupported Angular versions;
3. reproducible per-stage runtime isolation;
4. separate technical, parity, security, and delivery statuses;
5. idempotent, recoverable, and security-hardened execution.

The POC target remains Angular 21 because that is the approved project target. The platform must resolve the actual current Angular support landscape at planning time and must not infer “latest” from a static document.

# 2. Architecture Principles

| **Principle**                      | **Meaning**                                                                                                                                                                                  |
|------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Functional parity first            | The migrated application must preserve the same visible behavior, user journeys, routes, API contracts, business rules, validation behavior, and expected outputs.                           |
| Minimal diff                       | Every automatic change must be the smallest safe technical change required to make the upgrade install, build, test, run, or integrate correctly.                                            |
| Compatibility before modernization | The default objective is technical upgrade. Optional modernization is a separate, explicit, client-approved phase.                                                                           |
| One major version at a time        | Angular upgrades should normally be staged by major version to isolate failures and improve repair reliability.                                                                              |
| Sandbox-only mutation              | The source repository is read-only. All mutations occur inside a sandbox workspace or sandbox branch.                                                                                        |
| Deterministic-first execution      | Official Angular CLI migrations, package metadata, compiler diagnostics, lockfile parsing, and AST-based patches are preferred over free-form LLM edits.                                     |
| Backend execution authority        | The LLM or agent can propose actions, but only the backend validates, approves, and executes commands.                                                                                       |
| Validation-gated progress          | A stage is complete only when required validation passes or accepted risk is explicitly documented.                                                                                          |
| Controlled repair loop             | The Repair Agent can fix low-risk migration-caused errors only, with a maximum of three attempts per stage.                                                                                  |
| Traceability                       | Every decision, command, patch, approval, failure, repair, validation result, and final report must be persisted as an artifact.                                                             |
| Version-range compatibility        | The system must support Angular major/minor/patch ranges and must not hardcode exact patch versions such as 18.2.x only.                                                                     |
| Static symbol verification         | Every AI-generated or Repair Agent patch must pass deterministic checks for imports, symbols, Angular APIs, template references, and unapproved dependency additions before full validation. |
| MCP as context support             | MCP is optional and used only to provide read-only Angular documentation and guidance context to the LLM in the MVP. It must not execute migration actions.                                  |
| Security-compliant validation      | Unapproved external tools are not introduced. Excluded gates are reported as manual, deferred, or company-tool-required instead of hidden or falsely passed.                                 |

## 2.1 Explicit Non-Goals

- No AngularJS migration in this project scope.

- No Angular 2-10 migration in this project scope unless a future extension is approved.

- No UI redesign, color change, layout change, or UX redesign.

- No business logic refactoring.

- No API contract change, payload change, authentication change, or authorization change.

- No default migration to standalone components, signals, new control flow, inject(), or zoneless mode.

- No test framework replacement unless explicitly approved and required for validation.

- No introduction of unapproved external security, quality, browser, or E2E tools in the MVP.

# 3. Angular Version Support and Historical Compatibility Policy

The factory supports Angular 11+ as a product scope, but it must not imply that every historical upgrade path is currently supported by the Angular team.

As of the 2026-07-10 architecture update, Angular 22 is active, Angular 21 and Angular 20 are supported, and Angular 2 through 19 are outside official support. The Compatibility Resolver must therefore separate current official support from internal historical compatibility evidence.

## 3.1 Support-Level Vocabulary

| Support level | Meaning | Default behavior |
|---|---|---|
| `officially_supported` | Source-to-target transition satisfies current Angular support rules. | May proceed when all other policies pass. |
| `historical_validated` | One or more versions are outside support, but the exact transition family passes the factory regression suite. | Proceed with a visible historical-risk notice. |
| `historical_experimental` | Archived packages and migrations are available, but internal evidence is incomplete. | Human approval required before execution. |
| `blocked` | No safe profile, toolchain, migration package, or evidence exists. | Stop before mutation. |

## 3.2 Historical Compatibility Catalog

The catalog is a versioned policy dataset owned by the platform, not generated by the LLM. It stores:

- source Angular family;
- target Angular family;
- exact known-good Angular CLI ranges;
- Node.js, npm, TypeScript, RxJS, and Zone.js constraints;
- required archived package availability;
- known migration warnings and breaking changes;
- builder migration behavior;
- private-package compatibility notes;
- validated fixture projects;
- last validation date;
- catalog version and checksum.

```yaml
catalog_entry:
  source_family: angular-18.x
  target_family: angular-19.x
  support_level: historical_validated
  validated_fixture_suite: angular-18-to-19-v3
  last_validated_at: 2026-07-10
  official_support_at_validation_time: false
  required_runtime_profile: node-22-stage
  evidence_checksum: sha256:...
```

## 3.3 Target Selection Policy

- The target is client-approved and company-approved.
- The planner resolves an exact target patch at planning time and stores it in the approved stage profile.
- The target must not be called “latest” unless the resolver verifies that fact at runtime.
- Preview, `next`, release-candidate, developer-preview, or experimental targets are blocked by default.
- A final target outside official support requires an explicit approved-risk decision.

# 4. Version-Range Compatibility and Dynamic Version Resolution

The Angular Migration Factory must not be hardcoded to exact Angular patch versions such as Angular 18.2.x only. The platform must support version families and compatibility ranges.

The Analysis Agent must detect the exact installed versions of Angular, Angular CLI, TypeScript, RxJS, Zone.js, Node.js, and the package manager. However, the Planning Agent must reason using normalized version families such as Angular 18.x, Angular 19.x, Angular 20.x, and Angular 21.x.

For example, Angular 18.0.x, Angular 18.1.x, and Angular 18.2.x are all treated as Angular 18 family projects. They should all be eligible if the source policy accepts Angular 11 and later.

The Compatibility Resolver is responsible for converting exact detected versions into migration-ready compatibility profiles. It resolves:

- source Angular major, minor, and patch

- source Angular family

- target Angular family

- compatible Node.js range per stage

- compatible TypeScript range per stage

- compatible RxJS range per stage

- compatible Angular CLI target per stage

- package manager behavior

- stage-by-stage upgrade ladder

- command plan for each stage

- validation plan for each stage

The system must fail only when no valid compatibility profile can be resolved, not because the exact patch version was not explicitly listed in the product configuration.

Example:

Angular 18.0.4 and Angular 18.2.13 must both resolve to the Angular 18 source family. If the target is Angular 21, both should produce the same major-version ladder:

Angular 18 → Angular 19 → Angular 20 → Angular 21

The exact patch versions may influence dependency alignment and toolchain selection, but they must not create separate hardcoded workflows.

Version resolution must use official Angular compatibility data, company policy, and client-approved target constraints. The architecture must avoid static profiles such as angular-18.2-to-21.2 and prefer reusable profiles such as angular-11-plus-to-client-approved-target.

This rule ensures the product supports Angular X → Angular Y migration instead of becoming a brittle script for one exact demo version.

# 5. Compatibility Resolver and Stage Toolchain Profiles

The Compatibility Resolver is the component that makes the migration factory reliable across Angular version ranges. It prevents the platform from becoming a static script for one exact version, such as Angular 18.2.x. It receives exact detected versions from the Analysis Agent and converts them into normalized version families, compatibility decisions, and executable stage profiles.

## 5.1 Compatibility Resolver Responsibilities

- Normalize exact detected versions into source families, for example 18.0.4 → Angular 18.x.

- Resolve the target Angular family from client policy, company policy, and supported Angular compatibility data.

- Generate the one-major-at-a-time ladder from source major to target major.

- Resolve Node.js, TypeScript, RxJS, Zone.js, Angular CLI, and package manager behavior per stage.

- Generate command plans and validation plans per stage.

- Fail only when no safe compatibility profile exists, not when a patch version was not explicitly listed.

## 5.2 Compatibility Resolution Output

{  
"artifact": "03_planning/compatibility_resolution.json",  
"detected_versions": {  
"angular_core": "18.0.4",  
"angular_cli": "18.0.7",  
"typescript": "5.4.x",  
"rxjs": "7.8.x"  
},  
"normalized_versions": {  
"source_angular_family": "18.x",  
"source_angular_major": 18,  
"target_angular_family": "21.x",  
"target_angular_major": 21  
},  
"upgrade_ladder": \["18-to-19", "19-to-20", "20-to-21"\],  
"decision": "compatible_profile_resolved"  
}

## 5.3 Stage Toolchain Profile

Every migration stage must have an explicit toolchain profile. The Transformation and Build agents must not infer or guess stage versions or commands. They must consume the approved stage profile generated by the Planning Agent and bound by checksum.

| **Field**                                   | **Purpose**                                                                                     |
|---------------------------------------------|-------------------------------------------------------------------------------------------------|
| stage_id                                    | Unique stage identifier, for example angular-18-to-19.                                          |
| source_angular_major / target_angular_major | Major version transition controlled by the upgrade ladder.                                      |
| node_range                                  | Allowed Node.js runtime range for the stage, resolved dynamically.                              |
| typescript_range                            | Allowed TypeScript range for the target Angular stage.                                          |
| rxjs_range                                  | Allowed RxJS range for the target Angular stage.                                                |
| angular_cli_target                          | CLI target selector, for example ^19, not a hardcoded patch unless company policy requires one. |
| package_manager_policy                      | npm/yarn/pnpm behavior based on detected lockfile and company policy.                           |
| command_plan                                | Approved install, update, build, test, and lint commands for the stage.                         |
| validation_plan                             | Required, conditional, manual, and deferred gates for the stage.                                |
| rollback_point                              | The checkpoint to restore if the stage or a patch fails.                                        |

## 5.4 Stage Toolchain Profile Example

{  
"artifact": "03_planning/stage_toolchain_profiles.json",  
"stage_id": "angular-18-to-19",  
"source_angular_major": 18,  
"target_angular_major": 19,  
"angular_cli_target": "^19",  
"node_range": "resolved_from_compatibility_policy",  
"typescript_range": "resolved_from_compatibility_policy",  
"rxjs_range": "resolved_from_compatibility_policy",  
"package_manager": "npm",  
"update_command": "ng update @angular/core@^19 @angular/cli@^19",  
"validation_gates": \["install", "static_symbol_check", "build", "unit_tests_if_configured", "lint_if_configured"\],  
"manual_gates": \["browser_smoke", "visual_parity"\],  
"deferred_gates": \["external_security_scan", "external_quality_scan"\],  
"rollback_point": "stage_start_checkpoint"  
}

## 5.5 Builder Strategy in the Stage Profile

Every stage profile includes an explicit builder decision:

```yaml
builder_strategy:
  detected_builder: "@angular-devkit/build-angular:browser"
  target_strategy: preserve
  builder_migration_allowed: false
  reason: strict_parity_framework_upgrade_only
```

Interactive prompts are disabled or handled through a preapproved deterministic answer policy. The factory must not silently accept optional modernization or build-system migration prompts.

# 6. Source Intake, Workspace Topology, and Baseline Qualification

This section adds the deterministic intake and baseline controls that must run before agentic planning.

## 6.1 Source Intake Validator

The validator accepts one of the following source types:

- local directory path;
- Git repository URL and branch or commit;
- uploaded source archive.

It must verify:

- source exists and is readable;
- target exists or can be created;
- source and target are not the same path;
- target is not nested inside source;
- source is not nested inside target;
- canonical paths remain inside configured allowed roots;
- symlinks cannot escape the approved roots;
- sufficient disk space exists;
- source Git state and commit are captured when applicable;
- a content hash is captured before any work begins.

## 6.2 Workspace Topology Classification

The factory must classify the workspace before deciding that it can migrate it.

```text
single_application
multi_application
application_with_local_libraries
publishable_library_workspace
nx_workspace
microfrontend_workspace
custom_builder_workspace
ssr_or_hybrid_workspace
unknown_or_unsupported
```

The MVP may support only `single_application` and a controlled subset of `application_with_local_libraries`. Other categories must be explicitly blocked or require a dedicated profile.

The topology artifact identifies every Angular project, project type, source root, build target, test target, lint target, custom builder, local library, SSR target, service worker, i18n configuration, web worker, and deployment-specific configuration.

## 6.3 Baseline Qualification Gate

No transformation is allowed before baseline qualification completes.

The baseline service uses the source-compatible toolchain profile and records:

- clean/frozen dependency installation result;
- Angular and toolchain versions;
- build result for every required project and configuration;
- existing TypeScript and Angular compiler diagnostics;
- existing unit-test results;
- existing lint results;
- route and lazy-route manifest;
- API/backend contract manifest;
- browser-support and polyfill configuration;
- bundle budgets and output metrics when available;
- existing known failures and warnings;
- application startup status when a safe startup command exists;
- manual baseline observations.

A failing baseline is not automatically rejected. Failures receive stable fingerprints so later validation can classify them as `pre_existing`, `changed_pre_existing`, `new_migration_failure`, or `resolved_pre_existing`.

```json
{
  "baseline_status": "qualified_with_known_failures",
  "migration_allowed": true,
  "known_failures": [
    {
      "fingerprint": "TS2322:src/app/example.ts:42",
      "classification": "pre_existing"
    }
  ],
  "comparison_policy": "migration_must_not_introduce_new_failures"
}
```

## 6.4 Baseline Artifacts

```text
01_baseline/
├── source_snapshot_manifest.json
├── source_toolchain_profile.json
├── workspace_topology.json
├── baseline_install_report.json
├── baseline_build_report.json
├── baseline_test_report.json
├── baseline_lint_report.json
├── baseline_route_manifest.json
├── baseline_api_contract_manifest.json
├── baseline_browser_policy.json
├── baseline_bundle_metrics.json
├── baseline_known_failures.json
└── baseline_qualification_summary.json
```

# 7. Target System Architecture

The Angular migration factory should reuse the same enterprise operating model as the Spring Boot Migration Factory: a Control Tower UI, a backend execution authority, an orchestrator, a sandbox workspace, an artifact store, and a state store.

> Control Tower UI - > AI Assistant  
> \|  
> v  
> FastAPI Backend / Execution Authority  
> \|  
> v  
> LangGraph Orchestrator  
> \|  
> v  
> Eligibility + Constraints → Analysis → Approval → Planning → Approval  
> \|  
> v  
> For each Angular major stage:  
> Transformation → Build/Validation → Repair Loop → Checkpoint  
> \|  
> v  
> Report Agent → Final Evidence Report

## 7.1 Main Components

| **Component**               | **Responsibility**                                                                                                                                            |
|-----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Control Tower UI            | Creates migration jobs, captures environment information, displays backend-driven workflow state, exposes approvals, and provides access to the AI Assistant. |
| AI Assistant                | User-facing conversational layer for explanation, clarification, feedback capture, and approval assistance. It does not execute commands or mutate code.      |
| Backend Execution Authority | Validates structured actions, checks permissions, enforces sandbox-only mutation, executes commands, persists logs, and rejects unsafe requests.              |
| LangGraph Orchestrator      | Coordinates agent sequence, state transitions, approval gates, stage execution, retry limits, repair loops, and escalation.                                   |
| Sandbox Workspace           | The only mutable copy of the application during transformation and repair.                                                                                    |
| Artifact Store              | Stores analysis reports, plans, approvals, diffs, logs, validation reports, repair reports, and final evidence.                                               |
| State Store                 | Stores run state, stage state, current agent, approval status, validation gate status, and repair attempt count. This is the source of truth for the UI.      |

## 7.2 Revised Component Boundaries

The target architecture also includes deterministic infrastructure services: Source Intake Validator, Baseline Qualification Service, Workspace Topology Classifier, Historical Compatibility Catalog, Toolchain Runtime Manager, Command Policy Engine, Parity Evidence Engine, Worker Supervisor, Usage and Cost Collector, and Delivery Service.

These services surround the agent workflow. They provide facts, execution, enforcement, and evidence; they are not implemented as free-form LLM agents.

# 8. Toolchain Runtime Manager and Reproducible Execution

A stage toolchain profile is not complete until it can be executed in a reproducible runtime. Angular 11 and Angular 21 require different Node.js and TypeScript ranges, so the full Angular 11+ product cannot depend on one globally installed Node.js runtime.

## 8.1 Toolchain Runtime Manager

The Runtime Manager resolves and prepares the exact execution environment for baseline and every migration stage.

```yaml
runtime:
  operating_system: linux
  architecture: amd64
  node_exact_version: 22.12.0
  npm_exact_version: approved_exact_version
  angular_cli_exact_version: resolved_exact_version
  typescript_exact_version: resolved_exact_version
  environment_image_digest: sha256:...
  package_cache_policy: read_only_shared_cache
  network_policy: approved_registries_only
```

Permitted implementation approaches include company-approved containers, isolated worker images, or another immutable runtime mechanism. The runtime identity must be stored in every command artifact.

## 8.2 Exact Version Resolution

- Use version families to plan the upgrade ladder.
- Resolve exact package versions before execution.
- Store exact versions and registry metadata in the approved stage profile.
- Prefer the latest approved patch within the chosen major, but never allow an unrecorded version drift after approval.
- Reapproval is required when the exact version, registry source, runtime image, or command plan changes.

## 8.3 Package-Manager Reproducibility

The package-manager policy must distinguish between:

- `npm install`;
- `npm ci`;
- `npm install --package-lock-only`;
- `npm update`;
- `ng update`.

Baseline validation should use a frozen installation when a valid lockfile exists. After `ng update` changes package metadata, the stage must produce a new lockfile, validate it, and run a clean frozen installation before the stage can pass.

The runtime profile captures `.npmrc`, proxy, certificate, private registry, workspace, Corepack, cache, and lifecycle-script policy without persisting secrets.

## 8.4 Cross-Platform Risk

The Analysis Agent records the source operating system and detects:

- path-case inconsistencies;
- Windows-only scripts;
- shell-specific syntax;
- executable permission assumptions;
- path separator assumptions;
- native dependencies.

These findings become planning risks when the migration worker uses a different operating system.

# 9. Sandbox, Command, and Package Execution Security

The migration worker processes untrusted source code and package metadata. Sandbox-only mutation is necessary but not sufficient.

## 9.1 Structured Command Contract

Raw shell command strings are forbidden. The backend receives structured commands:

```json
{
  "executable": "npx",
  "arguments": [
    "ng",
    "update",
    "@angular/core@^19",
    "@angular/cli@^19",
    "--create-commits",
    "--verbose"
  ],
  "shell_enabled": false,
  "working_directory_id": "sandbox-root",
  "environment_profile": "angular-stage-19",
  "timeout_seconds": 1800,
  "idempotency_key": "run-stage-command-checksum"
}
```

The backend validates executable, each argument, current workflow state, approved plan checksum, stage profile checksum, working directory, environment variables, timeout, network policy, and required approval.

## 9.2 Sandbox Controls

Mandatory controls:

- non-root/non-administrator execution;
- path canonicalization and symlink escape prevention;
- no filesystem access outside the run workspace and approved caches;
- process, CPU, memory, disk, and execution-time limits;
- restricted network access;
- complete child-process-tree termination on cancel or timeout;
- environment-variable allowlist;
- command-specific secret injection;
- immutable runtime identity;
- source content-hash verification after execution;
- deterministic cleanup and retention policy.

## 9.3 Lifecycle-Script Enforcement

The package install script audit must lead to a decision, not only a report.

```json
{
  "install_script_policy": {
    "default": "deny_or_ignore",
    "approved_packages": [],
    "blocked_packages": [],
    "requires_human_approval": true
  }
}
```

Remote Git dependencies, remote tarballs, unapproved registries, and packages requiring privileged or external execution are blocked by default.

## 9.4 Repository Content Is Untrusted LLM Data

README files, code comments, source strings, dependency metadata, test names, and build logs are data, not instructions. They cannot alter system policy, permissions, approvals, tools, or scope.

Every LLM-enabled prompt must explicitly label repository content as untrusted. Tool calls are created only by backend code from schema-validated outputs; instructions embedded in repository content are never executed.

Add the following artifact:

```text
04_workflow_state/llm_untrusted_content_events.json
```

# 10. MCP Context Support Policy

MCP is not an execution dependency in the MVP. It is an optional context-support capability for the LLM. Its role is to provide Angular documentation, migration guidance, best practices, and official examples so the LLM can plan, diagnose, and propose repairs with better context. All execution, patching, validation, rollback, and approval remain controlled by the backend.

## 10.1 MCP Modes

| **Mode**                 | **MVP Policy**                  | **Allowed Use**                                                                                                                            | **Forbidden Use**                                                                                 |
|--------------------------|---------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| MCP Disabled Mode        | Default                         | No MCP server is started. The factory uses backend-controlled commands and local project analysis.                                         | None, because MCP is not used.                                                                    |
| MCP Context Support Mode | Optional, company-approved only | Read-only Angular documentation search, best-practices lookup, migration guidance, official examples, and explanation support for the LLM. | No command execution, no file mutation, no ng update, no build/test/devserver execution.          |
| MCP Workspace Mode       | Future only, not MVP            | Could inspect workspace or run targets only after company approval, readiness probe, and backend authorization.                            | Must not bypass backend authority, approval gates, sandbox policy, or modernization restrictions. |

## 10.2 MCP Security Rules

- MCP is disabled by default unless approved by company security policy.

- The migration factory must work without MCP.

- In the MVP, MCP is read-only context support for the LLM, not a command runner.

- The LLM may use MCP context to propose a diagnosis or patch, but the backend validates and applies any patch.

- MCP must not execute ng update, build, test, lint, devserver, or modernization actions in the MVP.

- Every MCP request and response must be logged as an artifact if MCP is enabled.

## 10.3 MCP Artifact

{  
"artifact": "04_workflow_state/mcp_context_usage_log.json",  
"mode": "disabled \| context_support \| workspace_future",  
"policy_status": "disabled_by_default \| approved_read_only \| blocked",  
"used_for": \["documentation_lookup", "migration_guidance", "repair_reasoning"\],  
"execution_actions_allowed": false  
}

# 11. Agent Execution Model

Each agent is a bounded worker. It receives a structured input, reads only the artifacts it is allowed to read, requests only the actions it is allowed to request, and returns a structured result. The orchestrator decides the next state based on that result.

## 11.1 Agent Permissions Model

| **Permission Type**             | **Allowed For**                                                                                                                        | **Rule**                                                                                       |
|---------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| Read repository                 | Eligibility, Analysis, Transformation, Build, Repair                                                                                   | Allowed only through sandbox/read-only workspace rules. Source repository must not be mutated. |
| Execute commands                | Transformation and Build through backend only                                                                                          | Agents request commands; backend validates and executes.                                       |
| Mutate files                    | Transformation and Repair only                                                                                                         | Mutation is sandbox-only and must follow approved plan and risk policy.                        |
| Approve workflow                | Human Approval Gate only                                                                                                               | AI Assistant may submit approval command, but backend records the same approval event as UI.   |
| Generate final report           | Report Agent                                                                                                                           | Report must summarize persisted evidence only; no invented claims.                             |
| Compatibility Resolver          | Normalizes exact versions into version families and generates compatibility resolution, upgrade ladder, and stage toolchain profiles.  | No command execution or mutation; planning support only.                                       |
| Static Symbol Verification Gate | Deterministically checks imports, symbols, Angular APIs, templates, and unapproved dependencies after patches.                         | No repair; only verifies and reports.                                                          |
| Dependency Audit Gate           | Classifies dependencies, private packages, custom builders, UI libraries, state management, and install scripts before stage planning. | No external scanners in MVP; metadata-based only.                                              |

## 11.2 Agent Result Statuses

| **Status**                  | **Meaning**                                                                                    | **Typical Next State**                          |
|-----------------------------|------------------------------------------------------------------------------------------------|-------------------------------------------------|
| completed                   | The agent finished successfully and produced expected artifacts.                               | Next planned workflow state.                    |
| failed                      | The agent failed due to a technical or execution error.                                        | FAILED or REPAIR_RUNNING depending on context.  |
| blocked                     | The agent cannot continue because required data, package, environment, or approval is missing. | WAITING\_\*\_APPROVAL or FAILED.                |
| requires_approval           | The agent found a risky or strategic decision that needs human review.                         | WAITING\_\*\_APPROVAL.                          |
| completed_with_manual_items | Core technical checks passed but some company-tool or manual gates remain pending.             | Next state only if policy accepts manual items. |

## 11.3 Deterministic Components That Do Not Use the LLM

The following components are deterministic services and do not call the LLM in their normal operation:

- source intake validation;
- version parsing and compatibility lookup;
- workspace topology classification;
- baseline execution;
- command validation and execution;
- lockfile parsing;
- checksum and approval validation;
- state transitions;
- static symbol and template verification;
- artifact persistence;
- runtime selection.

The LLM is reserved for tasks where language understanding or ambiguous diagnosis provides value.

# 12. Common Agent Contract

All agents and deterministic services use a shared, versioned envelope so the orchestrator, backend, UI, and artifact store can process results consistently.

## 12.1 Common Input Envelope

```json
{
  "schema_version": "1.0",
  "run_id": "migration-run-001",
  "stage_id": "angular-18-to-19",
  "source": {
    "type": "local_path | git | archive",
    "location_reference": "backend-managed-reference",
    "branch_or_commit": "main-or-sha",
    "source_read_only": true,
    "source_snapshot_checksum": "sha256:..."
  },
  "workspace": {
    "sandbox_id": "sandbox-run-001",
    "sandbox_path_reference": "backend-managed-reference",
    "sandbox_branch": "migration/angular-run-001"
  },
  "baseline": {
    "qualification_status": "qualified",
    "artifact_checksum": "sha256:..."
  },
  "client_constraints": {
    "preserve_ui": true,
    "preserve_behavior": true,
    "preserve_business_logic": true,
    "preserve_api_contracts": true,
    "preserve_authentication_authorization": true,
    "allow_optional_modernization": false
  },
  "policy": {
    "migration_policy_version": "v1",
    "approved_plan_checksum": "sha256:...",
    "stage_toolchain_profile_checksum": "sha256:...",
    "command_policy_version": "v1"
  },
  "workflow": {
    "current_state": "TRANSFORMATION_RUNNING",
    "state_version": 34,
    "worker_lease_id": "uuid",
    "idempotency_key": "run-stage-action-checksum"
  },
  "allowed_actions": ["read_file", "propose_patch", "request_approved_command"],
  "artifact_locations": {
    "analysis": "runs/{run_id}/global/02_analysis/",
    "planning": "runs/{run_id}/global/03_planning/",
    "stage": "runs/{run_id}/stages/{stage_id}/"
  }
}
```

Agents receive backend-managed references rather than unrestricted filesystem paths or secrets.

## 12.2 Common Output Envelope

```json
{
  "schema_version": "1.0",
  "agent_name": "analysis_agent",
  "run_id": "migration-run-001",
  "stage_id": null,
  "status": "completed",
  "summary": "Angular 18.x application detected and accepted for the configured migration path.",
  "facts": [],
  "proposals": [],
  "artifacts_created": [
    "runs/migration-run-001/global/02_analysis/angular_workspace_analysis.json"
  ],
  "risks": [
    {
      "risk_id": "dependency-peer-conflict-risk",
      "severity": "medium",
      "description": "Some packages may require version alignment during the Angular 19 stage."
    }
  ],
  "requires_human_action": false,
  "next_recommended_state": "WAITING_ANALYSIS_APPROVAL",
  "input_checksum_set": "sha256:...",
  "output_checksum": "sha256:..."
}
```

`facts` are grounded in deterministic evidence. `proposals` are not treated as executed actions.

# 13. Agent Catalog and Responsibility Matrix

| **Agent / Component**            | **Main Responsibility**                                                                                                                                               | **Primary Limitation**                        |
|----------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------|
| AI Assistant                     | Explains the workflow, answers user questions, captures feedback, and converts user decisions into structured instructions.                                           | No direct command execution or code mutation. |
| Eligibility and Constraint Agent | Confirms the source is Angular 11+, rejects AngularJS/pre-11, captures strict parity constraints.                                                                     | Read-only scanning only.                      |
| Analysis Agent                   | Inventories the Angular workspace, dependencies, routes, tests, build config, backend integration points, and risks.                                                  | Read-only analysis only.                      |
| Human Approval Gate 1            | Approves, rejects, or requests modification of the analysis result.                                                                                                   | Backend approval event only.                  |
| Planning Agent                   | Creates the major-by-major upgrade ladder, validation gates, allowed/forbidden changes, repair policy, and rollback strategy.                                         | No mutation.                                  |
| Human Approval Gate 2            | Approves, rejects, or requests modification of the migration plan before sandbox transformation.                                                                      | Backend approval event only.                  |
| Transformation Agent             | Applies approved Angular version upgrades and mandatory compatibility patches in sandbox.                                                                             | Mutates sandbox only.                         |
| Build / Validation Agent         | Runs install, build, type checks, existing tests, existing lint, route inventory, backend config check, and validation reporting.                                     | No automatic repair.                          |
| Repair Agent                     | Fixes low-risk migration-caused technical errors through a controlled repair loop.                                                                                    | Max three attempts; escalates risky changes.  |
| Report Agent                     | Generates final migration evidence report from persisted artifacts.                                                                                                   | No invention; evidence-based only.            |
| Orchestrator                     | Coordinates agent execution and state transitions.                                                                                                                    | Not an LLM worker; workflow controller.       |
| Backend Execution Authority      | Validates and executes commands, enforces sandbox and permission policies.                                                                                            | Only trusted execution layer.                 |
| MCP Context Support              | Optional and company-approved only. Read-only Angular documentation, migration guidance, best practices, and examples for LLM reasoning. No command execution in MVP. |                                               |
| Static symbol verification       | Local deterministic checks using TypeScript/Angular compiler diagnostics, package metadata, and node_modules type definitions where available.                        |                                               |

## 13.1 Deterministic Service Catalog

| Service | Responsibility | Primary limitation |
|---|---|---|
| Source Intake Validator | Canonical path checks, source snapshot, read-only proof, disk and source/target safety. | No migration reasoning or mutation. |
| Workspace Topology Classifier | Identifies projects, libraries, targets, builders, SSR, Nx, and unsupported topologies. | Classification only. |
| Baseline Qualification Service | Reproduces the source install/build/test/lint state and fingerprints known failures. | Does not repair the legacy source. |
| Compatibility Resolver | Produces support level, exact versions, stage ladder, and toolchain profiles from policy. | Deterministic policy lookup only. |
| Toolchain Runtime Manager | Provides the exact isolated runtime for baseline and each stage. | No planning decisions. |
| Command Policy Engine | Validates executable, arguments, paths, environment, network, approval, and limits. | Rejects rather than repairs unsafe requests. |
| Parity Evidence Engine | Builds and compares route, API, config, browser, and bundle manifests. | Does not prove manual visual behavior. |
| Worker Supervisor | Owns process lifecycle, heartbeat, resource limits, cancellation, and cleanup. | No code reasoning. |
| Usage and Cost Collector | Records tokens, latency, retries, quota, and cost. | Observability only. |
| Delivery Service | Creates branch/patch/commit manifests and handover evidence. | Does not approve delivery. |

# 14. Detailed Agent Specifications

## 14.1 AI Assistant Agent

The AI Assistant is the user-facing conversational layer. It helps the user understand the migration, review evidence, request modifications, and approve or reject workflow gates. It must not directly execute commands or modify source code.

### Purpose

- Explain current migration state in simple language.

- Help the user understand risks, validation failures, and repair summaries.

- Capture user feedback and convert it into structured instructions for the relevant agent.

- Submit approval, rejection, modification request, or approval-with-risk decisions through the backend approval endpoint.

### Required Inputs

- User message or UI action.

- Current workflow state from backend state store.

- Latest analysis, plan, validation, repair, or report artifact summaries.

- Available approval options from backend.

- Run ID and current stage ID when applicable.

### Allowed Tools

- Read workflow state summaries.

- Read artifact summaries exposed by backend.

- Create structured modification requests.

- Submit approval decisions through backend approval API.

- Generate human-readable explanations.

### Forbidden Actions / Tools

- Direct npm, ng, git, or shell command execution.

- Direct file mutation.

- Silent approval without explicit user decision.

- Changing migration scope from compatibility to modernization.

### Generated Outputs

- Assistant response message.

- Structured modification request.

- Approval command payload.

- Clarification summary for another agent.

### Generated Artifacts

- 04_workflow_state/user_interaction_events.json

- 04_workflow_state/approval_events.json when approval is submitted

- 03_planning/user_modification_requests.json when plan changes are requested

### Stop / Escalation Rules

- Escalate when the user requests a forbidden transformation.

- Ask for explicit approval when approval is required.

- Refuse to execute commands directly and route action requests through backend.

### Expected UI Output

- Current stage explanation.

- Relevant artifact links.

- Approval/rejection/request-modification options only when backend state allows them.

## 14.2 Eligibility and Constraint Agent

This agent protects the workflow before deep analysis begins. It confirms that the application is in scope and records the strict migration constraints.

### Purpose

- Detect whether the project is Angular.

- Confirm Angular major version is 11 or later.

- Reject AngularJS and pre-Angular-11 projects for this product scope.

- Record client constraints: no UI change, no behavior change, no business logic change, no API contract change, no optional modernization.

### Required Inputs

- Repository path or sandbox read-only copy.

- package.json.

- angular.json if present.

- tsconfig files if present.

- Source scan results for Angular or AngularJS indicators.

- Client-provided target policy and project constraints.

### Allowed Tools

- Read package.json, angular.json, tsconfig, lockfiles, and source files.

- Use grep/ripgrep for framework indicators.

- Parse JSON configuration files.

- Read-only Angular indicator scanner.

### Forbidden Actions / Tools

- Installing dependencies.

- Running migration commands.

- Mutating files.

- Accepting an AngularJS or pre-11 project silently.

### Generated Outputs

- Eligibility decision: accepted, rejected, or unknown.

- Detected framework family and Angular major version.

- Detected AngularJS or unsupported-source indicators.

- Client constraints object.

- Recommended workflow path.

### Generated Artifacts

- 00_job_setup/eligibility_result.json

- 00_job_setup/client_constraints.json

- 00_job_setup/target_version_policy.json

- 00_job_setup/read_only_verification.json

### Stop / Escalation Rules

- Stop if Angular version is below 11.

- Stop if AngularJS indicators dominate.

- Stop if package metadata is missing and version cannot be reasonably determined.

- Stop if source repository cannot be verified read-only.

### Expected UI Output

- Accepted/rejected eligibility decision.

- Detected source version.

- Client constraints summary.

- Reason for rejection if out of scope.

## 14.3 Analysis Agent

The Analysis Agent builds the factual understanding of the Angular application. It does not change code. It inventories versions, dependencies, configuration, routes, tests, environments, backend integration points, and migration risks.

### Purpose

- Inventory Angular framework, Angular CLI, TypeScript, RxJS, Zone.js, Node.js compatibility, and package manager.

- Analyze angular.json, tsconfig, build scripts, environment files, proxy config, routes, tests, and lint setup.

- Detect Angular Material/CDK or UI library usage.

- Detect backend API integration points and auth-sensitive files.

- Generate baseline inventory and risk report before planning.

### Required Inputs

- Eligibility result.

- Client constraints.

- Read-only repository or sandbox workspace.

- package.json and lockfile.

- angular.json and tsconfig files.

- Source directories.

- Existing scripts and environment files.

### Allowed Tools

- Read file tree.

- Parse package.json, lockfiles, angular.json, tsconfig.

- Use grep/ripgrep for routes, services, APIs, decorators, environment references.

- Use TypeScript AST or ts-morph for structured analysis.

- Use Angular compiler/template parser where available.

- Run non-mutating inspection commands through backend if approved.

### Forbidden Actions / Tools

- Running ng update.

- Changing dependencies.

- Applying code patches.

- Modifying tests or configuration.

- Adding new external tools.

### Generated Outputs

- Angular workspace analysis report.

- Dependency and package inventory.

- Route inventory.

- Environment and backend integration inventory.

- Test and lint inventory.

- Risk assessment for planning.

- Baseline capture status.

### Generated Artifacts

- 02_analysis/angular_workspace_analysis.json

- 02_analysis/package_inventory.json

- 02_analysis/dependency_graph.json

- 02_analysis/route_inventory.json

- 02_analysis/environment_inventory.json

- 02_analysis/material_cdk_inventory.json

- 02_analysis/test_inventory.json

- 02_analysis/backend_integration_inventory.json

- global/01_baseline/baseline_route_manifest.json when baseline route evidence is generated

### Stop / Escalation Rules

- Stop if project cannot be analyzed safely.

- Escalate if package metadata is inconsistent.

- Escalate if private packages or registry access are required for deeper analysis.

- Escalate if backend integration is unclear or auth-sensitive areas are detected.

### Expected UI Output

- Detected source stack.

- Main risks.

- Project structure summary.

- Test/lint availability.

- Backend integration summary.

- Approval request for Analysis Gate.

## 14.4 Enhanced Analysis Outputs

To make the architecture more reliable, the Analysis Agent must now produce explicit dependency, install-script, backend-contract, and changed-file sensitivity inventories. These are used by the Planning, Build, Repair, and Report agents.

- 02_analysis/dependency_audit.json

- 02_analysis/private_package_inventory.json

- 02_analysis/package_install_script_audit.json

- global/01_baseline/baseline_api_contract_manifest.json

- 02_analysis/changed_file_sensitivity_rules.json

The Compatibility Resolver, not the Analysis Agent, owns `global/03_planning/compatibility_resolution.json`.

## 14.5 Human Approval Gate 1 - Analysis Approval

This backend gate allows the user to approve, reject, or request modification of the analysis and eligibility result before planning starts.

### Purpose

- Confirm that the detected source version and eligibility are correct.

- Confirm that client constraints are correctly captured.

- Allow the user to stop or request analysis changes before planning.

### Required Inputs

- Eligibility result checksum.

- Analysis report checksum.

- Current workflow state WAITING_ANALYSIS_APPROVAL.

- User decision from UI or AI Assistant.

### Allowed Tools

- Create backend approval event.

- Update workflow state based on decision.

- Record user comment and decision source.

### Forbidden Actions / Tools

- Starting planning without approval.

- Approving a stale artifact checksum.

- Mutating project files.

### Generated Outputs

- Approval decision: approved, rejected, modification_requested, or approved_with_risk.

- Next workflow state.

### Generated Artifacts

- 04_workflow_state/approval_events.json

- 04_workflow_state/migration_run_state.json

### Stop / Escalation Rules

- Stop if decision is rejected.

- Return to Analysis Agent if modification is requested.

- Block if checksum mismatch is detected.

### Expected UI Output

- Approval status.

- Next state: planning, modification requested, or stopped.

## 14.6 Planning Agent

The Planning Agent converts the analysis result into a controlled, approved migration plan. It defines the upgrade ladder, version strategy, allowed changes, forbidden changes, validation gates, repair policy, rollback strategy, and checkpoints.

### Purpose

- Resolve target version policy from client/company constraints.

- Generate a major-by-major upgrade ladder.

- Define per-stage Node.js, TypeScript, Angular CLI, RxJS, and package alignment strategy.

- Define allowed compatibility changes and forbidden modernization changes.

- Define validation gates and repair boundaries.

- Generate approval request for sandbox transformation.

### Required Inputs

- Approved analysis artifacts.

- Client constraints.

- Target Angular policy.

- Detected source versions.

- Dependency and risk inventory.

- Company tool policy and MVP exclusions.

### Allowed Tools

- Read analysis artifacts.

- Use Angular compatibility/version policy resolver.

- Use company-approved version policy source.

- Generate YAML/JSON plans.

- Classify risks and validation gates.

### Forbidden Actions / Tools

- Running ng update.

- Changing package.json.

- Adding tools not approved for the MVP.

- Planning optional modernization as default.

### Generated Outputs

- Migration plan.

- Upgrade ladder.

- Migration units list.

- Allowed and forbidden changes.

- Validation plan.

- Risk assessment.

- Rollback strategy.

- Approval request.

### Generated Artifacts

- 03_planning/migration_plan.yaml

- 03_planning/upgrade_ladder.yaml

- 03_planning/migration_units.yaml

- 03_planning/allowed_and_forbidden_changes.yaml

- 03_planning/risk_assessment.json

- 03_planning/rollback_strategy.md

- 03_planning/approval_request.md

### Stop / Escalation Rules

- Escalate if target version policy is unclear.

- Escalate if required compatibility change conflicts with client constraints.

- Stop if no safe upgrade path can be planned.

- Require approval before transformation.

### Expected UI Output

- Upgrade ladder.

- Planned changes and forbidden changes.

- Validation gates.

- Repair policy.

- Approval request for Plan Gate.

## 14.7 Human Approval Gate 2 - Plan Approval

This gate protects the system before any sandbox mutation starts. The approved plan becomes the command and patch boundary for the Transformation and Repair agents.

### Purpose

- Approve or reject the migration plan.

- Confirm that the plan respects strict parity and MVP tool policy.

- Bind the approved plan by checksum before execution.

### Required Inputs

- Migration plan checksum.

- Upgrade ladder checksum.

- Allowed/forbidden changes checksum.

- Current workflow state WAITING_PLAN_APPROVAL.

- User decision and optional comment.

### Allowed Tools

- Record approval decision.

- Update workflow state to first stage when approved.

- Return to Planning Agent if modifications are requested.

### Forbidden Actions / Tools

- Starting transformation without approval.

- Approving stale or changed plan artifacts.

- Changing the plan during execution without new approval.

### Generated Outputs

- Plan approval event.

- Approved plan checksum.

- Next workflow state and first stage ID.

### Generated Artifacts

- 04_workflow_state/approval_events.json

- 04_workflow_state/migration_run_state.json

- 04_workflow_state/stage_state_history.json

### Stop / Escalation Rules

- Stop if rejected.

- Return to Planning Agent if modification requested.

- Block if checksum mismatch occurs.

### Expected UI Output

- Approval status.

- Start stage button or automatic continuation based on approved mode.

## 14.8 Transformation Agent

The Transformation Agent applies approved technical upgrade actions in the sandbox. It uses official Angular CLI migrations and deterministic patching first. It must not apply optional modernization by default.

### Purpose

- Prepare the stage toolchain according to the approved plan.

- Run approved Angular major upgrade commands stage by stage.

- Apply official Angular migrations required by the stage.

- Align package versions and lockfile only as approved.

- Apply mandatory compatibility patches only when low-risk and in plan.

- Generate a complete patch ledger and diff.

### Required Inputs

- Approved migration plan and checksum.

- Current stage definition.

- Sandbox workspace path.

- Allowed command registry.

- Client constraints.

- Current package and config files.

### Allowed Tools

- Run backend-approved package manager commands in sandbox.

- Run backend-approved Angular CLI commands in sandbox.

- Use deterministic JSON/YAML editors for package.json, angular.json, tsconfig.

- Use TypeScript AST or ts-morph for targeted compatibility patches.

- Use git diff and checkpoint commands in sandbox.

### Forbidden Actions / Tools

- Mutating the original source repository.

- Running commands not present in the approved plan or command registry.

- Applying standalone/signals/control-flow/zoneless migrations by default.

- Changing UI appearance, business logic, API contracts, auth, or state-management design.

- Introducing excluded MVP tools.

### Generated Outputs

- Applied migration command list.

- Changed files list.

- Package/config diff.

- Patch ledger.

- Minimal-diff classification.

- Next state BUILD_RUNNING.

### Generated Artifacts

- 05_sandbox_transform/sandbox_manifest.json

- 05_sandbox_transform/applied_migrations.json

- 05_sandbox_transform/patch_ledger.json

- 05_sandbox_transform/minimal_diff_report.json

- 05_sandbox_transform/package_json_diff.json

- 05_sandbox_transform/angular_json_diff.json

- 05_sandbox_transform/source_diff.patch

### Stop / Escalation Rules

- Stop if approved plan checksum is missing or stale.

- Stop if command is not allowed by backend.

- Escalate if required change may alter business, UI, API, auth, or security behavior.

- Stop if sandbox cannot be verified.

### Expected UI Output

- Current stage transformation summary.

- Commands executed.

- Files changed.

- Optional modernization status: not applied.

- Next validation step.

## 14.9 Build / Validation Agent

The Build / Validation Agent proves whether a migration stage is technically valid. It does not repair. It runs install, build, existing tests, existing lint, route inventory, backend configuration checks, and validation reporting. In the current MVP it must not use Playwright, Cypress, OSV, Snyk, SonarQube, or Semgrep.

### Purpose

- Validate dependency installation.

- Validate Angular/TypeScript build.

- Run existing unit tests only if configured.

- Run existing lint only if configured.

- Inventory routes and backend configuration.

- Generate manual or deferred validation items for browser, visual, security, and quality gates when company-approved tools are unavailable.

- Classify failures and route to Repair Agent when safe.

### Required Inputs

- Current stage state.

- Sandbox workspace path.

- Approved plan and validation gate list.

- package.json scripts.

- angular.json configuration.

- Environment/proxy files.

- Transformation diff and patch ledger.

### Allowed Tools

- Detected package manager: npm, yarn, or pnpm.

- Angular CLI through existing project setup.

- ng version.

- ng build or existing build command.

- npm test / yarn test / pnpm test only if already configured.

- npm run lint / equivalent only if already configured.

- File scanners for routes, environments, proxy config, and package metadata.

- Git diff reader for minimal-diff evidence.

### Forbidden Actions / Tools

- Playwright.

- Cypress.

- OSV scanner.

- Snyk.

- SonarQube.

- Semgrep.

- Adding a new test framework.

- Changing code to make validation pass.

- Marking manual/deferred gates as failed when they are intentionally out of MVP scope.

### Generated Outputs

- Install report.

- Build report.

- Type-check result through build.

- Unit test report or not-configured explanation.

- Lint report or not-configured explanation.

- Route inventory report.

- Backend config check report.

- Manual validation checklist for browser/visual parity.

- Deferred security/quality note.

- Failure classification if any.

- Recommendation: stage completed, repair needed, or human review required.

### Generated Artifacts

- 06_validation/install_report.json

- 06_validation/build_report.json

- 06_validation/lint_report.json

- 06_validation/unit_test_report.json

- 06_validation/route_inventory_validation.json

- 06_validation/backend_config_report.json

- 06_validation/manual_parity_checklist.md

- 06_validation/security_quality_deferred_report.json

- 06_validation/stage_validation_summary.json

### Stop / Escalation Rules

- Send to Repair Agent when failure is low/medium-risk technical compatibility issue.

- Escalate when failure involves API contract, auth, business logic, UI behavior, or security-sensitive behavior.

- Mark browser/visual/security gates as manual/deferred in MVP, not as failed.

- Stop after repeated validation infrastructure failures.

### Expected UI Output

- Passed/failed gates.

- Manual/deferred validation items.

- Failure category.

- Affected files when known.

- Repair or escalation decision.

## 14.10 Repair Agent

The Repair Agent fixes migration-caused technical errors after validation fails. It is limited to low-risk and approved medium-risk compatibility repairs. It must stop after three attempts per stage or when risky behavior changes are required.

### Purpose

- Read failed validation logs and classify the error.

- Identify root cause and impacted files.

- Assign risk level: low, medium, high, or blocked.

- Apply the smallest safe patch in sandbox only.

- Re-run targeted validation through backend.

- Return to Build Agent for full validation when targeted validation passes.

- Escalate risky or unresolved failures.

### Required Inputs

- Failed validation report.

- Build/test/lint logs.

- Current stage ID and repair attempt count.

- Approved plan and repair policy.

- Patch ledger and diff context.

- Client constraints and forbidden changes list.

### Allowed Tools

- Read validation logs and compiler diagnostics.

- Use TypeScript AST or ts-morph for targeted fixes.

- Use Angular template diagnostics for template compatibility fixes.

- Use JSON editor for package/config fixes within approved plan.

- Apply targeted sandbox patches.

- Run targeted validation through backend.

### Forbidden Actions / Tools

- Changing business logic or expected outputs.

- Changing API request/response payloads.

- Changing authentication or authorization logic.

- Changing UI appearance/layout.

- Replacing state management.

- Applying broad rewrites.

- Exceeding three repair attempts per stage.

- Changing tests to hide real behavior changes.

### Generated Outputs

- Repair diagnosis.

- Risk classification.

- Patch strategy.

- Patch result.

- Targeted validation result.

- Full validation handoff decision.

- Escalation request if needed.

### Generated Artifacts

- 07_repair/repair_attempts.json

- 07_repair/repair_diagnosis_reports.json

- 07_repair/repair_patch_ledger.json

- 07_repair/repair_risk_decisions.json

- 07_repair/human_escalation_requests.json

### Stop / Escalation Rules

- Escalate immediately for high-risk or blocked changes.

- Stop after three failed attempts.

- Escalate if expected behavior is unclear.

- Escalate if private package, backend environment, or company tooling is missing.

- Escalate if repair may affect UI, API, auth, security, or business behavior.

### Expected UI Output

- Attempt count: 1/3, 2/3, or 3/3.

- Error category and risk level.

- Patch summary.

- Validation result.

- Escalation reason if blocked.

## 14.11 Report Agent

The Report Agent generates final migration evidence from persisted artifacts. It should not invent results. It summarizes what was analyzed, changed, validated, repaired, accepted, deferred, or left as manual action.

### Purpose

- Generate final evidence report.

- Summarize upgrade ladder and completed stages.

- Summarize changed files and minimal-diff classification.

- Summarize validation gates and manual/deferred items.

- Summarize repair attempts and escalations.

- List unresolved blockers and manual actions.

- Produce client-facing and technical report outputs.

### Required Inputs

- All run artifacts.

- Workflow and stage state history.

- Approval events.

- Patch ledger and git diff.

- Validation reports.

- Repair reports.

- Manual/deferred validation items.

### Allowed Tools

- Read artifact store.

- Read state store.

- Read git diff summaries.

- Generate Markdown, JSON, CSV, or PDF/DOCX report if supported.

- Generate manual action checklist.

### Forbidden Actions / Tools

- Changing migration output.

- Claiming unexecuted validation passed.

- Hiding manual/deferred gates.

- Inventing parity evidence.

### Generated Outputs

- Final migration evidence report.

- Compatibility upgrade summary.

- Manual actions required.

- Unresolved blockers report.

- Client-facing summary.

- Technical appendix.

### Generated Artifacts

- 08_final/final_migration_evidence_report.md

- 08_final/compatibility_upgrade_summary.md

- 08_final/manual_actions_required.md

- 08_final/unresolved_blockers.json

- 08_final/final_report_export.pdf or .docx if enabled

### Stop / Escalation Rules

- Block if required artifacts are missing.

- Mark missing or deferred gates transparently.

- Escalate if final state is inconsistent with stage state history.

### Expected UI Output

- Final status.

- Report download links.

- Manual actions and unresolved risks.

## 14.12 Orchestrator

The Orchestrator is the workflow controller. It may be implemented with LangGraph or another state-machine engine. It is responsible for deciding which agent runs next and for enforcing approval and retry rules.

- Creates and updates migration run state.

- Starts agents only when prerequisites are satisfied.

- Moves workflow through analysis, approval, planning, transformation, build, repair, validation, checkpoint, and report states.

- Prevents transformation before plan approval.

- Prevents next-stage execution before validation is complete.

- Stops automatic repair after three attempts.

- Handles cancel, failure, and resume behavior.

- Makes backend state the source of truth for the frontend.

## 14.13 Backend Execution Authority

The Backend Execution Authority is the trusted execution layer. Agents do not execute shell commands directly. They submit structured action requests, and the backend validates the action against the approved plan, command policy, runtime profile, sandbox policy, current state, and risk policy.

```json
{
  "requested_by": "transformation_agent",
  "action_type": "run_command",
  "executable": "npx",
  "arguments": [
    "ng",
    "update",
    "@angular/core@^19",
    "@angular/cli@^19",
    "--create-commits",
    "--verbose"
  ],
  "shell_enabled": false,
  "working_directory_id": "sandbox-root",
  "environment_profile": "angular-stage-19",
  "stage_id": "angular-18-to-19",
  "timeout_seconds": 1800,
  "approval_scope": "approved_plan_command",
  "approved_plan_checksum": "sha256:...",
  "stage_profile_checksum": "sha256:...",
  "state_version": 34,
  "idempotency_key": "run-stage-command-checksum"
}
```

The authority must:

- validate the executable and every argument;
- reject shell operators, command substitution, and arbitrary command strings;
- validate that execution occurs inside the approved sandbox;
- validate plan, stage profile, approval, state version, and idempotency key;
- apply environment, network, resource, and timeout policies;
- reject forbidden modernization actions and unapproved dependencies;
- persist sanitized command metadata, stdout, stderr, exit code, duration, runtime identity, and generated artifacts;
- return a structured execution result to the requester.

# 15. Workflow State Management

The frontend must not infer progress from local state. Backend state, persisted events, and artifact checksums are the source of truth.

## 15.1 Run and Stage State Families

```text
CREATED
SOURCE_VALIDATION_RUNNING
SOURCE_VALIDATED
WORKSPACE_CLASSIFICATION_RUNNING
BASELINE_RUNNING
BASELINE_QUALIFIED
CLIENT_CONSTRAINTS_CAPTURED
ELIGIBILITY_RUNNING
ANALYSIS_RUNNING
WAITING_ANALYSIS_APPROVAL
PLANNING_RUNNING
WAITING_PLAN_APPROVAL
STAGE_CREATED
TOOLCHAIN_PROFILE_SELECTED
SANDBOX_READY
DEPENDENCY_AUDITED
TRANSFORMATION_RUNNING
STATIC_SYMBOL_CHECK_RUNNING
VALIDATION_RUNNING
REPAIR_RUNNING
WAITING_REPAIR_APPROVAL
REVIEW_READY
STAGE_COMMITTED
STAGE_ROLLED_BACK
DIAGNOSTIC_HOLD
REPORT_RUNNING
DELIVERY_RUNNING
COMPLETED
FAILED
CANCELLED
```

## 15.2 Operational and Recovery States

```text
PAUSE_REQUESTED
PAUSED
RESUMING
CANCEL_REQUESTED
CANCELLING
TIMED_OUT
WORKER_LOST
RECOVERY_RUNNING
ORPHANED
CLEANUP_RUNNING
CLEANUP_FAILED
```

## 15.3 Transition Contract

```json
{
  "event_id": "uuid",
  "event_sequence": 127,
  "idempotency_key": "run-stage-action-checksum",
  "previous_state": "TRANSFORMATION_RUNNING",
  "next_state": "STATIC_SYMBOL_CHECK_RUNNING",
  "expected_state_version": 34,
  "new_state_version": 35,
  "worker_lease_id": "uuid",
  "artifact_transaction_id": "uuid",
  "occurred_at": "ISO-8601"
}
```

Every write validates the expected state version. Duplicate idempotency keys return the original result rather than running the action again.

## 15.4 Worker Ownership and Recovery

- An active action has one worker lease and heartbeat.
- A stale lease moves the run to `WORKER_LOST`.
- Recovery verifies workspace hash, checkpoint, runtime image, policy version, and command history.
- Unsafe or ambiguous recovery moves the run to `DIAGNOSTIC_HOLD`.
- Resume never reruns a completed command without an idempotency decision.

## 15.5 Cancellation Semantics

Cancellation:

1. records `CANCEL_REQUESTED`;
2. stops scheduling new actions;
3. terminates the complete running process tree;
4. preserves stdout, stderr, partial artifacts, and current workspace state;
5. optionally restores the latest safe checkpoint according to policy;
6. generates a partial evidence report;
7. performs cleanup or retention action;
8. transitions to `CANCELLED`.

## 15.6 Approval Semantics

- UI and AI Assistant approvals create the same backend event.
- Approval is bound to artifact checksums, state version, actor, scope, and expiry.
- Auto-approval is a run policy stored before and throughout execution; it is not a frontend checkbox state.
- Enabling auto-approval applies to all eligible future gates in the run until disabled or a non-auto-approvable risk appears.
- A stale approval or changed plan never authorizes execution.

## 15.7 Frontend Display Rules

- Every card, button, attempt number, status, and owner comes from backend state.
- The UI shows technical status, parity status, security assurance, and delivery readiness separately.
- Approval buttons appear only for currently valid approval actions.
- Repair cards show attempt count, risk, patch, validation, and escalation reason.
- Manual and deferred gates remain visible.

# 16. Artifact Model and Audit Trail

Artifacts are the immutable evidence backbone of the factory. They are organized by global run context, migration stage, and repair attempt so evidence is never overwritten.

## 16.1 Canonical Layout

```text
runs/{run_id}/
├── global/
│   ├── 00_setup/
│   │   ├── source_intake_result.json
│   │   ├── source_snapshot_manifest.json
│   │   ├── client_constraints.json
│   │   ├── target_version_policy.json
│   │   ├── browser_support_policy.json
│   │   ├── read_only_verification.json
│   │   └── llm_provider_config_redacted.json
│   ├── 01_baseline/
│   │   ├── workspace_topology.json
│   │   ├── source_toolchain_profile.json
│   │   ├── baseline_install_report.json
│   │   ├── baseline_build_report.json
│   │   ├── baseline_test_report.json
│   │   ├── baseline_lint_report.json
│   │   ├── baseline_route_manifest.json
│   │   ├── baseline_api_contract_manifest.json
│   │   ├── baseline_bundle_metrics.json
│   │   ├── baseline_known_failures.json
│   │   └── baseline_qualification_summary.json
│   ├── 02_analysis/
│   │   ├── angular_workspace_analysis.json
│   │   ├── package_inventory.json
│   │   ├── dependency_graph.json
│   │   ├── dependency_audit.json
│   │   ├── private_package_inventory.json
│   │   ├── package_install_script_audit.json
│   │   ├── route_inventory.json
│   │   ├── environment_inventory.json
│   │   ├── material_cdk_inventory.json
│   │   ├── test_inventory.json
│   │   ├── backend_integration_inventory.json
│   │   └── changed_file_sensitivity_rules.json
│   ├── 03_planning/
│   │   ├── compatibility_resolution.json
│   │   ├── historical_support_decision.json
│   │   ├── migration_plan.yaml
│   │   ├── upgrade_ladder.yaml
│   │   ├── stage_toolchain_profiles.json
│   │   ├── migration_units.yaml
│   │   ├── builder_strategy.yaml
│   │   ├── allowed_and_forbidden_changes.yaml
│   │   ├── risk_assessment.json
│   │   ├── rollback_strategy.md
│   │   └── approval_request.md
│   └── 04_workflow_state/
│       ├── migration_run_state.json
│       ├── state_event_log.jsonl
│       ├── stage_state_history.json
│       ├── agent_execution_history.json
│       ├── approval_events.json
│       ├── rollback_events.json
│       ├── worker_lease_events.json
│       ├── user_interaction_events.json
│       ├── llm_interaction_log_redacted.json
│       └── llm_untrusted_content_events.json
├── stages/
│   ├── angular-18-to-19/
│   │   ├── transform/
│   │   │   ├── sandbox_manifest.json
│   │   │   ├── command_execution_log.jsonl
│   │   │   ├── applied_migrations.json
│   │   │   ├── patch_ledger.json
│   │   │   ├── changed_file_risk_classification.json
│   │   │   ├── minimal_diff_report.json
│   │   │   ├── package_json_diff.json
│   │   │   ├── angular_json_diff.json
│   │   │   └── source_diff.patch
│   │   ├── validation/
│   │   │   ├── install_report.json
│   │   │   ├── static_symbol_check_report.json
│   │   │   ├── build_report.json
│   │   │   ├── lint_report.json
│   │   │   ├── unit_test_report.json
│   │   │   ├── parity_manifest_diff.json
│   │   │   ├── backend_contract_diff.json
│   │   │   ├── bundle_metrics_diff.json
│   │   │   ├── manual_parity_checklist.md
│   │   │   └── stage_validation_summary.json
│   │   ├── repair/
│   │   │   ├── attempt-001/
│   │   │   ├── attempt-002/
│   │   │   └── attempt-003/
│   │   └── checkpoint/
│   │       ├── checkpoint_manifest.json
│   │       └── stage_commit.json
│   ├── angular-19-to-20/
│   └── angular-20-to-21/
├── 09_evaluation/
├── delivery/
│   ├── delivery_manifest.json
│   ├── migration_patch_bundle.patch
│   ├── stage_commit_manifest.json
│   └── handover_checklist.md
└── final/
    ├── final_migration_evidence_report.md
    ├── compatibility_upgrade_summary.md
    ├── manual_actions_required.md
    ├── unresolved_blockers.json
    ├── security_protocol_compliance.md
    ├── llm_usage_and_cost_summary.md
    └── final_report_export.pdf
```

## 16.2 Artifact Envelope

```json
{
  "schema_version": "1.0",
  "artifact_id": "uuid",
  "run_id": "uuid",
  "stage_id": "angular-18-to-19",
  "attempt": 1,
  "producer": "repair_agent",
  "created_at": "ISO-8601",
  "input_artifact_hashes": [],
  "policy_version": "migration-policy-v1",
  "prompt_version": "repair-agent-v3",
  "model_deployment": "deployment-alias-or-null",
  "runtime_image_digest": "sha256:...",
  "content_hash": "sha256:..."
}
```

## 16.3 Artifact Rules

- Artifacts are append-only or versioned; they are never silently overwritten.
- Every approval is bound to exact artifact checksums.
- Every command stores executable, arguments, working directory, sanitized environment profile, runtime identity, exit code, stdout, stderr, duration, timeout, and requester.
- Every patch stores reason, affected files, risk, expected behavior impact, source proposal, validation, and rollback result.
- Raw secrets and unnecessary raw LLM prompts are not stored.
- Final reports are generated only from persisted evidence.
- Retention, deletion, export, and access policies are recorded per run.

# 17. Tooling Policy and MVP Restrictions

Because company security protocol limits external tools, the current MVP must rely only on existing project commands, Angular CLI, package manager commands, file scanners, and internal backend validation. External browser automation and external security/quality scanners are excluded for now.

## 17.1 MVP-Allowed Tools

| **Tool / Capability**         | **Allowed Use**                                                                        |
|-------------------------------|----------------------------------------------------------------------------------------|
| npm / yarn / pnpm             | Install dependencies and run existing project scripts using detected package manager.  |
| Angular CLI                   | Run ng version, ng build, and approved ng update commands through backend.             |
| TypeScript / Angular compiler | Used through ng build and compiler diagnostics.                                        |
| Existing unit test command    | Run only if already configured in package.json.                                        |
| Existing lint command         | Run only if already configured in package.json.                                        |
| File scanners                 | Scan routes, environment files, proxy config, package metadata, and source indicators. |
| JSON/YAML editors             | Apply deterministic config updates only inside approved plan.                          |
| TypeScript AST / ts-morph     | Targeted analysis and low-risk compatibility patches.                                  |
| Git diff/checkpoint           | Generate evidence and stage checkpoints inside sandbox.                                |

## 17.2 Excluded from Current MVP

| **Excluded Tool** | **Current Policy**         |
|-------------------|----------------------------|
| Playwright        | Do not use in current MVP. |
| Cypress           | Do not use in current MVP. |
| OSV scanner       | Do not use in current MVP. |
| Snyk              | Do not use in current MVP. |
| SonarQube         | Do not use in current MVP. |
| Semgrep           | Do not use in current MVP. |

## 17.3 How Excluded Gates Are Reported

- Browser smoke is reported as manual_validation_required for the MVP.

- Visual parity is reported as manual_validation_required for the MVP.

- External security scanning is reported as deferred_company_tool_required for the MVP.

- External quality scanning is reported as deferred_company_tool_required for the MVP.

- These statuses should not fail the MVP automatically unless company policy says the gate is mandatory before delivery.

# 18. Validation Gates and Definition of Done

| **Gate**                         | **MVP Status**          | **Implementation**                                                                                                                                                      |
|----------------------------------|-------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Install validation               | Mandatory               | Run npm install/npm ci or equivalent based on package manager policy.                                                                                                   |
| Angular version check            | Mandatory               | Read package metadata and/or run ng version.                                                                                                                            |
| Build validation                 | Mandatory               | Run existing Angular build command or ng build.                                                                                                                         |
| Type checking                    | Mandatory               | Covered through ng build and Angular compiler diagnostics.                                                                                                              |
| Unit tests                       | Conditional             | Run only if project already has configured test command.                                                                                                                |
| Lint                             | Conditional             | Run only if project already has configured lint command.                                                                                                                |
| Route inventory                  | Mandatory evidence      | Parse Angular route definitions and generate route inventory.                                                                                                           |
| Backend config check             | Mandatory evidence      | Inspect environment files, proxy config, API base URLs, and auth-sensitive config references.                                                                           |
| Browser smoke                    | Manual for MVP          | Generate manual checklist, do not use Playwright/Cypress for now.                                                                                                       |
| Visual parity                    | Manual for MVP          | Generate manual checklist, no automated screenshot tool required for now.                                                                                               |
| Security scan                    | Deferred for MVP        | No OSV/Snyk/SonarQube/Semgrep. Record company-tool-required status.                                                                                                     |
| Quality scan                     | Deferred for MVP        | No SonarQube/Semgrep. Record company-tool-required status.                                                                                                              |
| Static symbol verification       | Mandatory after patches | Run after Transformation Agent or Repair Agent patches before full build validation. Verify imports, symbols, template references, and unapproved dependency additions. |
| Dependency audit                 | Mandatory evidence      | Classify Angular packages, UI libraries, state management, custom builders, private packages, and package risks before planning.                                        |
| Package install script audit     | Mandatory evidence      | Detect preinstall/install/postinstall/prepare scripts and report packages requiring review before install in sandbox.                                                   |
| Backend contract snapshot/diff   | Mandatory evidence      | Capture API base URLs, proxy config, interceptors, auth headers, token/cookie usage, request builders, response mappers, and error handling references.                 |

## 18.1 Stage Definition of Done - MVP

- Install succeeds or environment blocker is documented and approved.

- Angular version is updated for the current stage.

- Build succeeds.

- TypeScript/Angular compiler diagnostics are clean enough for build success.

- Existing tests run successfully, or absence/not-configured status is documented.

- Existing lint runs successfully, or absence/not-configured status is documented.

- Route inventory is generated.

- Backend configuration check is generated.

- Manual browser/visual parity checklist is generated.

- External security/quality gates are marked deferred for company-approved tooling.

- Repair history is recorded.

- Diff is generated and classified as minimal compatibility change.

- Human accepted risk is recorded if any required gate cannot be executed.

## 18.2 Static Symbol Verification Gate

Static Symbol Verification is required after every LLM-generated or Repair Agent patch. It is a cheap deterministic anti-hallucination gate that prevents the system from continuing with nonexistent imports, phantom APIs, invalid template references, or unapproved dependencies.

| **Check**                          | **Expected Result**                                                                                                                 |
|------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| Import resolution                  | All imports introduced or changed by the patch resolve locally.                                                                     |
| Symbol existence                   | All referenced classes, functions, constants, decorators, and members exist.                                                        |
| Angular/RxJS/Material API validity | No phantom APIs or package names are introduced.                                                                                    |
| Template diagnostics               | Changed templates pass Angular compiler/template diagnostics where available.                                                       |
| Dependency approval                | No new dependency or package replacement appears without approved plan or human approval.                                           |
| Changed file sensitivity           | Changed files are classified before auto-continuation.                                                                              |

## 18.3 Validation Status Vocabulary

Validation results must use explicit statuses so unavailable MVP tools are not hidden and are not falsely marked as failures.

passed  
failed  
not_configured  
manual_validation_required  
deferred_company_tool_required  
blocked_by_environment  
accepted_risk

## 18.4 Assurance Decision Rules

- `technical_upgrade_status = passed` requires all mandatory technical gates to pass. An environment blocker may be documented or accepted, but it cannot be reported as a technical pass.
- `functional_parity_status = verified` requires the approved parity procedure to complete. Generating a checklist alone results in `manual_validation_pending`.
- Deferred security or quality tooling remains visible in `security_assurance_status` and does not become `passed`.
- A run may be `completed` as a workflow while delivery readiness remains conditional or blocked.

# 19. Functional Parity Assurance, Browser Support, and Build-System Policy

Strict parity is a delivery objective, not a conclusion produced by a successful compilation. The factory therefore tracks technical validity and parity evidence separately.

## 19.1 Independent Assurance Dimensions

```json
{
  "run_status": "completed",
  "technical_upgrade_status": "passed",
  "functional_parity_status": "manual_validation_pending",
  "security_assurance_status": "deferred_company_tool_required",
  "delivery_readiness": "conditionally_ready"
}
```

Allowed parity statuses:

```text
verified
verified_with_accepted_differences
manual_validation_pending
not_verified
failed
accepted_risk
```

A stage may be technically complete while parity remains pending. Reports and the UI must never collapse these statuses into one generic “completed” label.

## 19.2 Parity Manifest

The baseline and every stage capture and compare, where deterministically possible:

- route paths, redirects, lazy-loading boundaries, guards, and resolvers;
- API base URLs, proxy configuration, HTTP methods, endpoint patterns, request builders, response mappers, and error handling;
- authentication headers, token/cookie behavior, interceptors, and permission references;
- reactive and template-driven form validators;
- translation keys and locale configuration;
- assets, stylesheets, themes, fonts, and global style order;
- service-worker, SSR, prerendering, and hydration configuration;
- build output paths and deployment-relevant files;
- bundle budgets and principal bundle metrics;
- browser polyfills and browser-support policy.

## 19.3 Browser Support Contract

Strict parity means equivalent approved behavior on the agreed target-browser matrix. The project must not assume that the legacy browser matrix and the target Angular browser matrix are identical.

```json
{
  "artifact": "00_job_setup/browser_support_policy.json",
  "legacy_supported_browsers": [],
  "target_angular_supported_browsers": [],
  "client_required_browsers": [],
  "unsupported_client_requirements": [],
  "decision": "approved_target_matrix"
}
```

## 19.4 Build-System Migration Gate

Angular framework migration and Angular build-system migration are separate migration units.

The factory detects `browser`, `browser-esbuild`, `application`, custom builders, SSR builders, and webpack-specific configuration. Migration to `application`, `browser-esbuild`, esbuild, or a new SSR structure is blocked unless the approved plan explicitly contains a builder migration unit.

Add to `forbidden_without_approval`:

```yaml
- build_system_migration
- browser_builder_to_application_builder
- browser_builder_to_browser_esbuild
- custom_builder_replacement
- webpack_to_esbuild_migration
- ssr_builder_consolidation
```

## 19.5 MVP Manual Parity Procedure

Because browser automation is excluded from the current MVP, the report must provide a route-based manual checklist, expected environment, test credentials policy, browser matrix, evidence owner, execution status, observations, screenshots or links when permitted, and explicit sign-off. Until that checklist is completed, parity remains `manual_validation_pending`.

# 20. Dependency Audit, Install Script Audit, and Backend Contract Snapshot

These lightweight checks improve reliability without introducing external security scanners. They rely on package metadata, lockfiles, source scanning, and backend configuration analysis.

## 20.1 Dependency Audit Categories

| **Category**           | **Examples**                                                        |
|------------------------|---------------------------------------------------------------------|
| Angular packages       | @angular/core, @angular/cli, @angular/compiler, @angular/router     |
| Angular ecosystem      | Angular Material/CDK, RxJS, Zone.js                                 |
| Workspace/tooling      | Nx if present, custom builders, test frameworks, lint tools         |
| UI libraries           | PrimeNG, AG Grid, NG Bootstrap, Bootstrap, internal UI kits         |
| State management       | NgRx, Akita, NGXS, services, custom stores                          |
| Enterprise constraints | Private packages, abandoned packages, packages with install scripts |

## 20.2 Dependency Risk Classification

safe  
needs_version_bump  
needs_migration_guide  
requires_approval  
unknown_risk  
blocking

## 20.3 Package Install Script Audit

Before package installation, the system should inspect package metadata and lockfile information where possible to identify packages that define preinstall, install, postinstall, or prepare scripts. These scripts must execute only inside the sandbox and must be reported in the final evidence.

## 20.4 Backend Contract Snapshot

Because the backend remains unchanged in the MVP, the frontend migration must not silently change how the Angular application communicates with the Java/Spring Boot backend. The backend contract snapshot records API-related frontend behavior before migration and compares it after each stage where possible.

- environment API base URLs and proxy configuration

- HTTP interceptors and auth header logic

- token or cookie usage

- API service files and request payload builders

- response mappers and error handling logic

- guards, resolvers, and route-level authorization references

# 21. Repair Policy and Escalation Rules

| **Risk Level** | **Examples**                                                                                                        | **Default Action**                                               |
|----------------|---------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| Low            | Missing import, simple typing fix, required module import, angular.json builder adjustment with no behavior impact. | Repair Agent may auto-apply in sandbox and validate.             |
| Medium         | RxJS operator import change, routing declaration adjustment, dependency alignment with possible side effects.       | Auto-apply only if allowed by approved plan; otherwise escalate. |
| High           | Business logic, calculations, API payload, auth, permissions, security flow, UI behavior.                           | Human approval required before patch. Usually blocked for MVP.   |
| Blocked        | Missing private package, unavailable backend, unclear expected behavior, unknown test expectation.                  | Stop automatic repair and escalate with diagnosis.               |

## 21.1 Automatic Repair Scope

- Missing imports and missing symbols.

- Typing errors caused by TypeScript/framework upgrade.

- Approved dependency alignment inside migration plan.

- Angular configuration and test configuration required for compatibility.

- NgModule declarations, providers, routing configuration, and required imports compatible with current architecture.

- Known deprecated API replacements required for build/runtime compatibility.

- Simple test setup updates when behavior and expected output are unchanged.

## 21.2 Restricted Repair Scope

- Business rules or calculation logic.

- API contracts and payload structure.

- Authentication or authorization logic.

- Payment or permission logic.

- Security-sensitive logic.

- UI appearance or layout changes.

- State-management design changes.

- Any change where behavior preservation cannot be proven.

## 21.3 Rollback Levels

Rollback must be explicit and automated where safe. The system should never continue with a failed patch or unclear repair state.

| **Rollback Level** | **Trigger**                                                                            | **Action**                                                                      |
|--------------------|----------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| Patch rollback     | A Repair Agent or LLM patch fails static symbol verification or targeted validation.   | Undo only the last patch and preserve diagnosis artifacts.                      |
| Stage rollback     | Stage-level dependency alignment or repeated repair attempts leave the stage unstable. | Reset sandbox to the checkpoint created before the current major-version stage. |
| Migration rollback | The migration must be abandoned or restarted from the original baseline.               | Reset to the original read-only input state and preserve evidence.              |
| Diagnostic hold    | The state is useful for human investigation but unsafe to continue automatically.      | Stop automation, preserve failed workspace, and generate blocker report.        |

## 21.4 Auto-Continue and Human Approval Rules

Automatic continuation is allowed only when the stage is low risk and all mandatory technical gates pass. Otherwise, the workflow must wait for human review or accepted risk.

### Auto-Continue Allowed Only When

- Official Angular migration or approved compatibility patch succeeded.

- Static symbol verification passed.

- Install and build passed.

- Existing tests and lint passed or were explicitly not configured.

- Diff is mechanical, config-only, or low-risk compatibility-only.

- No --force flag was used.

- No dependency replacement was made without approval.

- No business, auth, API, routing, form validation, security-sensitive, or UI behavior file changed.

### Human Approval Required When

- --force is needed.

- A dependency replacement is needed.

- Auth, interceptor, guard, permission, routing, form validation, API mapper, or environment behavior changes are involved.

- Material, CSS, theme, layout, or visual behavior files changed.

- Static symbol verification fails.

- Tests fail and expected output is unclear.

- The same error repeats after repair.

- LLM confidence is low or behavior preservation cannot be proven.

## 21.5 Changed-File Risk Classification

| **Risk** | **File Examples**                                                                                                                | **Default Decision**                                              |
|----------|----------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| Low      | package.json, lockfile, angular.json, tsconfig, browserslist, polyfills, test setup                                              | May auto-continue if validation passes.                           |
| Medium   | routing modules, shared modules, RxJS-heavy services, Angular Material module files                                              | Auto-continue only if approved plan allows and validation passes. |
| High     | auth services, interceptors, guards, permissions, API mappers, form validators, calculation/business services, environment files | Human approval required.                                          |
| Blocked  | Files where expected behavior cannot be determined or private package behavior is unknown                                        | Diagnostic hold or escalation.                                    |

# 22. Azure OpenAI LLM Assistance Layer and Per-Agent LLM Access

**Purpose.** Selected migration agents may use an LLM to improve reasoning, diagnosis, planning, explanation, and report generation. The LLM is not the execution authority. The backend remains responsible for command execution, file mutation, validation, rollback, and approval enforcement.

**Default provider and model.** The MVP uses Azure OpenAI API through a backend-controlled LLM Gateway. GPT-5 mini is the main/default model deployment. The deployment name, endpoint, API version, region, authentication method, timeout, and retry policy must be configuration values, not hardcoded in prompts or agents.

**Design principle.** Only agents with an approved LLM use case can ask for LLM assistance, but no agent gets direct access to Azure credentials, shell execution, repository mutation, or approval bypass. LLM output is treated as a proposal that must pass deterministic backend checks before it affects the sandbox.

| **Area**            | **Architecture Decision**                                                                                                                             |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| Provider            | Azure OpenAI API, accessed only through the backend LLM Gateway.                                                                                      |
| Main model          | GPT-5 mini as the default/main deployment for all agents.                                                                                             |
| Configuration       | Endpoint, deployment name, API version, region, quotas, and authentication are environment configuration and must not be hardcoded.                   |
| Agent access        | Only approved LLM-enabled agents can request assistance through structured calls to the LLM Gateway; deterministic services do not call the LLM.                                                                    |
| Execution boundary  | The LLM cannot directly execute npm, ng, git, shell commands, MCP workspace tools, or file mutations.                                                 |
| Validation boundary | LLM outputs that propose patches must pass static symbol verification, build validation, risk classification, and approval policy before progression. |
| Data boundary       | Prompts must send the minimum necessary context. Secrets, tokens, private credentials, and production environment values must be redacted.            |
| Traceability        | All LLM calls are logged with redacted prompts, response summaries, model deployment, timestamps, token usage if available, and artifact references.  |

## 22.1 LLM Gateway Responsibilities

- Centralize all Azure OpenAI API calls for every agent.

- Inject the correct system prompt, agent role, context packet, and output schema.

- Apply prompt-size limits, timeout limits, retry policy, and cost/token budget controls.

- Redact secrets, credentials, tokens, API keys, private environment values, and sensitive headers before sending context to the model.

- Prevent agents from sending entire repositories when targeted snippets, logs, or artifacts are enough.

- Require structured JSON output for agent-to-system decisions such as plan proposal, failure diagnosis, patch proposal, risk classification, and report summary.

- Store redacted LLM interaction logs as audit artifacts without persisting hidden chain-of-thought. Store concise decision summaries instead.

- Support MCP Context Support Mode as optional documentation/context enrichment for the LLM, not as an execution dependency.

## 22.2 Per-Agent LLM Usage Matrix

| **Agent / Component**            | **How GPT-5 mini helps**                                                                                                                        | **LLM output expected**                                                                                  | **Hard boundary**                                                                                                |
|----------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| AI Assistant                     | Explains workflow state, validation failures, approval options, and user feedback in natural language.                                          | User-facing explanation, structured modification request, approval-intent payload.                       | No direct execution, no silent approval, no scope expansion.                                                     |
| Eligibility and Constraint Agent | Helps summarize ambiguous framework indicators and explain why a project is accepted or rejected.                                               | Eligibility rationale summary and unsupported-source explanation.                                        | Eligibility facts must come from project files and deterministic scans, not from the LLM alone.                  |
| Analysis Agent                   | Summarizes workspace findings, detects risk patterns, groups dependencies, explains backend integration risks, and generates readable analysis. | Analysis summary, risk explanations, dependency classification suggestions.                              | No mutation, no dependency changes, no install/update commands from LLM output.                                  |
| Planning Agent                   | Generates the migration plan from compatibility resolver output, company policy, and analysis artifacts.                                        | Upgrade ladder narrative, validation plan, risk model, approval request, rollback strategy.              | Cannot invent unsupported target versions or bypass one-major-at-a-time strategy unless explicitly approved.     |
| Transformation Agent             | Uses LLM only to explain command intent or propose minimal compatibility patch ideas when deterministic tools are insufficient.                 | Action proposal or patch proposal with affected files, reason, and risk level.                           | Backend executes only approved commands. LLM cannot run ng update or mutate files directly.                      |
| Build / Validation Agent         | Classifies build, install, TypeScript, template, test, and lint failures; summarizes logs for the user and Repair Agent.                        | Failure category, root-cause hypothesis, affected files, recommended next state.                         | No repair and no code changes. It only validates and reports.                                                    |
| Repair Agent                     | Diagnoses migration-caused failures and proposes the smallest safe patch.                                                                       | Patch proposal, root cause, risk level, validation command to rerun, fallback/escalation recommendation. | Patch is not trusted until backend patching, static symbol verification, build validation, and risk policy pass. |
| Report Agent                     | Turns persisted artifacts into client-facing and technical reports.                                                                             | Final report narrative, executive summary, manual action checklist.                                      | Cannot claim unexecuted gates passed or invent parity evidence.                                                  |
| Orchestrator                     | May use LLM summaries for operator visibility, but workflow transitions are deterministic state-machine decisions.                              | Optional status summary only.                                                                            | LLM cannot decide state transitions independently of backend state and policy.                                   |
| Backend Execution Authority      | Does not need LLM for execution. It may receive LLM proposals from agents and validate them.                                                    | Validated/rejected action result, execution artifact.                                                    | Backend is the trusted authority, not the LLM.                                                                   |

## 22.3 LLM Call Contract

**Every LLM request should use a structured context packet.** The goal is to make LLM assistance reproducible, reviewable, and safe.

> {  
> "run_id": "migration-run-001",  
> "stage_id": "angular-18-to-19",  
> "agent_name": "repair_agent",  
> "llm_provider": "azure_openai",  
> "model_deployment": "gpt-5-mini",  
> "task_type": "failure_diagnosis_and_patch_proposal",  
> "system_policy": {  
> "strict_parity": true,  
> "minimal_diff": true,  
> "sandbox_only": true,  
> "optional_modernization_allowed": false,  
> "forbidden_changes": \[  
> "business_logic_change",  
> "api_contract_change",  
> "authentication_authorization_change",  
> "ui_redesign",  
> "state_management_replacement"  
> \]  
> },  
> "context": {  
> "compatibility_profile": "artifact://03_planning/compatibility_resolution.json",  
> "stage_toolchain_profile": "artifact://03_planning/stage_toolchain_profiles.json#angular-18-to-19",  
> "failed_gate": "ng_build",  
> "error_excerpt": "redacted compiler/build excerpt",  
> "affected_files_excerpt": \["targeted snippets only"\],  
> "previous_attempts": 1  
> },  
> "required_output_schema": "repair_patch_proposal_v1"  
> }
>
> {  
> "diagnosis": "Missing import caused by stage migration and stricter compilation.",  
> "proposed_patch": {  
> "files": \["src/app/app.routes.ts"\],  
> "change_summary": "Add missing component import only.",  
> "minimal_diff": true,  
> "behavior_change_expected": false  
> },  
> "risk_level": "low",  
> "requires_human_approval": false,  
> "validation_to_rerun": \["static_symbol_check", "ng_build"\],  
> "fallback_plan": "Escalate if the import does not resolve or route behavior changes."  
> }

## 22.4 LLM Security and Governance Rules

- Azure OpenAI credentials must be stored only in backend-managed configuration, Key Vault, environment variables, or an equivalent company-approved secret store.

- The frontend and agents must never receive the raw Azure OpenAI API key, endpoint secret, bearer token, or deployment credentials.

- Before every LLM call, the LLM Gateway must redact secrets, tokens, cookies, Authorization headers, API keys, .env values, private registry credentials, and production URLs when required by policy.

- Agents must send targeted context: relevant file snippets, compiler errors, diffs, and artifact references. They must not send the whole repository by default.

- The LLM must not be used as the sole correctness gate. Deterministic checks such as compatibility resolver, static symbol verification, ng build, test/lint if configured, and backend approval policy remain mandatory.

- LLM-generated patches must be applied by backend patch services only, never directly by the model.

- The system must store redacted LLM call metadata and concise rationale summaries, but it should not store hidden chain-of-thought or sensitive raw prompts unnecessarily.

- If Azure quota, timeout, rate limit, or API availability problems occur, the workflow should stop safely with a diagnostic artifact rather than applying unvalidated changes.

## 22.5 LLM Artifacts

| **Artifact**                                          | **Purpose**                                                                                                                                             |
|-------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| 00_job_setup/llm_provider_config_redacted.json        | Records provider, deployment alias, region/endpoint alias, and policy flags without secrets.                                                            |
| 04_workflow_state/llm_interaction_log_redacted.json   | Audit log of LLM calls with timestamps, agent name, task type, model deployment, token usage if available, artifact references, and redacted summaries. |
| 03_planning/llm_plan_rationale_summary.md             | Human-readable summary of how LLM assistance contributed to the plan, based only on approved artifacts.                                                 |
| 06_validation/llm_failure_classification_summary.json | Optional LLM-assisted classification summary for validation failures.                                                                                   |
| 07_repair/llm_patch_proposals.json                    | Patch proposals created by LLM assistance before backend validation and static checks.                                                                  |
| 08_final/llm_usage_summary.md                         | Final report section documenting where LLM assistance was used and what was validated deterministically.                                                |

## 22.6 Azure OpenAI Configuration Example - Redacted

> {  
> "llm_provider": "azure_openai",  
> "default_model_deployment": "gpt-5-mini",  
> "deployment_alias": "main_reasoning_model",  
> "endpoint_alias": "AZURE_OPENAI_ENDPOINT",  
> "api_version_source": "environment_or_company_config",  
> "auth_mode": "api_key_or_managed_identity_company_policy",  
> "secrets_exposed_to_agents": false,  
> "direct_llm_execution_allowed": false,  
> "prompt_redaction_enabled": true,  
> "store_raw_prompts": false,  
> "store_redacted_interaction_log": true,  
> "max_context_policy": "send_targeted_artifacts_and_snippets_only",  
> "fallback_model_policy": "disabled_by_default_unless_company_approved"  
> }

## 22.7 Efficiency Rules for GPT-5 mini Usage

- Use deterministic scanners first, then send only summarized findings or targeted excerpts to the model.

- Cache reusable LLM outputs such as dependency risk summaries, migration plan rationale, and repeated error classifications by artifact checksum.

- Prefer small task-specific prompts over large generic prompts.

- Use structured JSON outputs to reduce parsing ambiguity and retries.

- For repeated repair attempts, include only the delta from the previous attempt and the latest validation output.

- Do not ask the model to re-read unchanged files when their artifact checksum is unchanged.

- Use GPT-5 mini as the default model for cost and latency control; any larger-model escalation must be an explicit future option and company-approved.

## 22.8 Additional Reference Notes for LLM Integration

- Azure OpenAI API usage, authentication, deployment names, API versions, and availability must follow the company Azure setup and official Microsoft documentation.

- GPT-5 mini is treated as the configured Azure OpenAI deployment for the MVP; the actual deployment name may differ by environment and should be resolved from backend configuration.

- MCP remains a context-support option for the LLM only; it is not an execution dependency and does not replace backend command authority.

- Azure OpenAI REST API reference: https://learn.microsoft.com/en-us/azure/foundry/openai/reference

- Azure OpenAI reasoning models documentation: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning

- OpenAI GPT-5 overview: https://openai.com/gpt-5/

## 22.9 Prompt-Injection and Untrusted-Content Policy

Repository content is always untrusted data. The LLM Gateway separates trusted platform policy from untrusted source excerpts and labels every context segment. Repository text cannot grant permissions, approve actions, change scope, reveal secrets, or create tools.

Schema validation rejects model responses that contain unsupported actions, unknown files, raw shell commands, unapproved dependencies, policy changes, or approval claims.

## 22.10 Model, Prompt, and Schema Versioning

Every LLM call records:

- provider and deployment alias;
- model/version information available from the provider;
- system-prompt version;
- task-prompt version;
- output-schema version;
- policy version;
- context artifact hashes;
- token usage, latency, retries, and estimated cost;
- validation and acceptance result.

A model or prompt change must pass the evaluation promotion gate before becoming the default.

# 23. AI Quality Evaluation and Regression Suite

The migration factory must evaluate model, prompt, policy, and deterministic-rule changes before promoting them.

## 23.1 Fixture Suite

Maintain representative, legally usable test projects such as:

- Angular 11 NgModule application;
- Angular 13 application with Angular Material;
- Angular 15 application with NgRx;
- Angular 17 application using the legacy builder;
- Angular 18 multi-project workspace;
- application with deprecated RxJS patterns;
- application with custom builder;
- application with guards, interceptors, forms, and backend mappings;
- application with deliberate compiler and template failures;
- repository containing prompt-injection text.

## 23.2 Evaluation Metrics

| Metric | Purpose |
|---|---|
| Baseline reproduction rate | Measures whether the factory correctly reproduces the original state. |
| First-pass build rate | Measures how often official migrations pass without AI repair. |
| Repair success rate | Measures how often bounded repair solves migration-caused failures. |
| False-repair rate | Detects unrelated or unnecessary changes. |
| Patch size and sensitivity | Verifies minimal-diff and risk policies. |
| Human escalation rate | Measures autonomy without hiding risk. |
| New regression count | Detects route, contract, configuration, test, or build regressions. |
| Token and cost per stage | Controls LLM efficiency. |
| Retry and rollback rate | Measures workflow stability. |
| Prompt-injection resistance | Verifies that repository content cannot change policy or trigger tools. |

## 23.3 Promotion Gate

A change to model deployment, system prompt, output schema, compatibility catalog, repair rule, command policy, or risk classifier must run against the evaluation suite. Promotion requires stored results and an approved quality threshold.

Artifacts:

```text
09_evaluation/evaluation_run.json
09_evaluation/fixture_results.json
09_evaluation/regression_comparison.json
09_evaluation/promotion_decision.json
```

# 24. Observability, Token Usage, Cost, Quotas, and Operations

Operational observability must cover workflow, worker, command, LLM, cost, and artifact behavior.

## 24.1 Required Metrics

- migration duration by run and stage;
- queue duration;
- command duration and exit-code distribution;
- worker CPU, memory, disk, timeout, cancellation, and cleanup events;
- build, test, lint, repair, rollback, and escalation rates;
- SSE connection and event-delivery failures;
- artifact creation and checksum failures;
- LLM latency, retry, timeout, rate-limit, and quota events;
- input tokens, output tokens, total tokens, and cost by call, agent, stage, and run.

## 24.2 LLM Budget Policy

```json
{
  "llm_budget": {
    "max_input_tokens_per_run": 0,
    "max_output_tokens_per_run": 0,
    "max_cost_usd_per_run": 0,
    "max_repair_cost_usd_per_stage": 0,
    "on_budget_exceeded": "diagnostic_hold"
  }
}
```

Zero in the example means the deployment policy has not yet supplied a value; production execution must not silently interpret it as unlimited.

## 24.3 Quota and Failure Handling

- apply bounded retries with exponential backoff and jitter;
- use per-deployment concurrency limits;
- apply queue backpressure;
- use a circuit breaker during repeated provider failures;
- stop safely without applying unvalidated patches;
- preserve a diagnostic artifact;
- allow human continuation without LLM when the remaining workflow is deterministic.

## 24.4 Authentication

For Azure-hosted deployments, prefer Microsoft Entra ID and managed identity when company policy permits it. API-key authentication remains an environment-specific fallback and never reaches the frontend or agent prompts.

## 24.5 SQLite MVP Boundary

SQLite is limited to a single-host MVP with WAL enabled, configured busy timeout, small transactions, and artifacts stored outside database blobs. Move to PostgreSQL before multiple backend instances, distributed workers, high concurrency, or enterprise multi-user operation.

# 25. API and Schema Examples

## 25.1 Approval Endpoint Payload

```http
POST /migrations/{runId}/approvals
Content-Type: application/json
```

```json
{
  "approval_gate": "analysis | planning | repair | parity | delivery",
  "approved_by": "user-identifier",
  "approval_source": "ui_button | assistant_command",
  "artifact_checksums": ["sha256:..."],
  "state_version": 34,
  "approval_scope": "current_gate",
  "decision": "approved | rejected | modification_requested | approved_with_risk",
  "user_comment": "optional",
  "expires_at": "ISO-8601-or-null"
}
```

## 25.2 Build Failure Report

```json
{
  "gate": "ng_build",
  "status": "failed",
  "category": "angular_template_compile_error",
  "root_cause_summary": "Template references a property not available after stricter compiler checks.",
  "affected_files": [
    "src/app/features/orders/order-list.component.html"
  ],
  "baseline_comparison": "new_migration_failure",
  "repair_attempt": 0,
  "max_repair_attempts": 3,
  "requires_human_review": false,
  "recommended_next_state": "REPAIR_RUNNING"
}
```

## 25.3 MVP Validation Summary

```json
{
  "stage_id": "angular-18-to-19",
  "workflow_stage_status": "completed",
  "technical_upgrade_status": "passed",
  "functional_parity_status": "manual_validation_pending",
  "security_assurance_status": "deferred_company_tool_required",
  "delivery_readiness": "conditionally_ready",
  "gates": {
    "install": "passed",
    "static_symbol_check": "passed",
    "build": "passed",
    "type_check": "passed",
    "unit_tests": "passed",
    "lint": "not_configured",
    "route_manifest_diff": "passed",
    "backend_contract_diff": "passed",
    "browser_smoke": "manual_validation_required",
    "visual_parity": "manual_validation_required",
    "security_scan": "deferred_company_tool_required",
    "quality_scan": "deferred_company_tool_required"
  },
  "excluded_tools": [
    "Playwright",
    "Cypress",
    "OSV",
    "Snyk",
    "SonarQube",
    "Semgrep"
  ],
  "requires_manual_parity_signoff": true
}
```

## 25.4 Repair Attempt Report

```json
{
  "attempt": 1,
  "stage_id": "angular-18-to-19",
  "error_category": "missing_import",
  "impacted_files": ["src/app/app.routes.ts"],
  "diagnosis": "Route configuration references a component without importing it.",
  "repair_strategy": "Add the missing import only; do not change route path or behavior.",
  "risk_level": "low",
  "minimal_diff": true,
  "behavior_change_expected": false,
  "static_symbol_validation": "passed",
  "targeted_validation": "passed",
  "full_validation": "passed",
  "escalated_to_human": false
}
```

## 25.5 Compatibility Resolution Schema

```json
{
  "artifact": "global/03_planning/compatibility_resolution.json",
  "source_family": "angular-18.x",
  "target_family": "angular-21.x",
  "accepted_source_range": ">=11.0.0",
  "support_level": "historical_validated",
  "exact_patch_resolution_required": true,
  "upgrade_ladder": [
    "angular-18-to-19",
    "angular-19-to-20",
    "angular-20-to-21"
  ]
}
```

## 25.6 Static Symbol Check Schema

```json
{
  "artifact": "stages/angular-18-to-19/validation/static_symbol_check_report.json",
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

## 25.7 Security Protocol Compliance Schema

```json
{
  "artifact": "final/security_protocol_compliance.md",
  "source_repository_mutated": false,
  "sandbox_only_mutation": true,
  "structured_command_policy_enforced": true,
  "runtime_isolation_recorded": true,
  "excluded_tools_used": [],
  "excluded_tools_policy": [
    "Playwright",
    "Cypress",
    "OSV",
    "Snyk",
    "SonarQube",
    "Semgrep"
  ],
  "mcp_mode": "disabled_or_context_support_only",
  "manual_or_deferred_gates_documented": true
}
```

# 26. Delivery and Handover

The factory must produce a controlled engineering handover, not only a report.

## 26.1 Delivery Outputs

Depending on company policy, the Delivery Service produces one or more of:

- migration branch;
- patch bundle;
- ordered stage commits;
- pull-request-ready package;
- final source archive;
- dependency and lockfile manifest;
- validation evidence package;
- manual parity checklist;
- unresolved blocker and accepted-risk list;
- rollback instructions.

## 26.2 Delivery Gate

Delivery readiness requires:

- all mandatory technical gates passed;
- final source hash recorded;
- stage commits and provenance available;
- no unapproved dependency or builder change;
- unresolved risks visible;
- parity status explicit;
- security and quality deferrals explicit;
- source repository unchanged;
- cleanup and retention decision recorded.

## 26.3 Pull Request Integration

PR creation is a future integration unless explicitly included in the MVP. When enabled, the factory must not push directly to protected branches. It creates a migration branch and a reviewable PR containing the executive summary, stage history, validation results, changed-file risk classification, manual actions, and evidence links.

# 27. MVP Implementation Recommendation

The first MVP should prove the architecture with a small Angular 18.x application migrated to Angular 21.x. It should not try to implement all enterprise-grade quality and browser automation gates in the first iteration.

## 27.1 Recommended MVP Agent Split

| **MVP Agent**                    | **Build Now?** | **Reason**                                            |
|----------------------------------|----------------|-------------------------------------------------------|
| AI Assistant                     | Yes            | Needed for explanation, user feedback, and approvals. |
| Eligibility and Constraint Agent | Yes            | Protects scope and records strict parity constraints. |
| Analysis Agent                   | Yes            | Needed to understand current Angular app and risks.   |
| Planning Agent                   | Yes            | Needed to generate 18 → 19 → 20 → 21 ladder.    |
| Transformation Agent             | Yes            | Core migration execution in sandbox.                  |
| Build / Validation Agent         | Yes            | Core proof that each stage installs and builds.       |
| Repair Agent                     | Yes, limited   | Only low-risk repairs, max three attempts.            |
| Report Agent                     | Yes            | Needed to prove value and generate final evidence.    |
| Separate Security Agent          | No             | Deferred until company-approved tools are available.  |
| Separate Browser Agent           | No             | Manual/browser parity checklist for MVP.              |
| Separate Test Agent              | No             | Existing tests handled by Build Agent.                |

## 27.2 MVP Stage Flow for Angular 18 → 21

1.  Create migration job and capture client constraints.

2.  Run eligibility and analysis.

3.  Approve analysis.

4.  Generate plan with stages: Angular 18 → 19, 19 → 20, 20 → 21.

5.  Approve plan.

6.  For each stage: transform in sandbox, run validation, repair if needed, checkpoint if valid.

7.  Generate final report with validation results, manual/deferred gates, diff, repair history, and unresolved items.

## 27.3 MVP Success Criteria

- Original source is never mutated.

- Project eligibility is confirmed as Angular 11+.

- Client constraints are recorded before planning.

- A stage-by-stage upgrade ladder is generated and approved.

- Sandbox transformation starts only after plan approval.

- Each stage runs install/build validation.

- Existing tests/lint run if configured.

- Repair Agent performs only low-risk compatibility repairs.

- Risky changes escalate instead of being silently patched.

- Manual/deferred gates are visible in the report.

- Final report includes completed actions, evidence, repair history, remaining risks, and manual blockers.

## 27.4 Security Protocol Compliance in Final Report

The final report must include a dedicated section proving that the migration respected company security constraints and MVP tool exclusions.

- Original repository remained read-only.

- All mutations happened in sandbox.

- No excluded tools were used: Playwright, Cypress, OSV, Snyk, SonarQube, or Semgrep.

- MCP, if used, was used only as context support and not as an execution tool.

- Commands, outputs, diffs, repair attempts, and rollback events were logged.

- Manual and deferred gates are visible and not falsely marked as passed.

## 27.5 Revised MVP Scope Boundary

The first implementation supports one small or medium single-application Angular 18.x workspace migrated to Angular 21.x. The MVP must demonstrate the complete control loop rather than broad workspace compatibility.

Mandatory MVP proof:

- source and target path safety;
- immutable source snapshot;
- baseline installation and build;
- exact stage runtime profiles;
- Angular 18 → 19 → 20 → 21 staged execution;
- structured command policy;
- clean frozen installation after each stage;
- static symbol and template checks;
- build and existing tests/lint;
- bounded repair loop;
- persistent checkpoints and resume;
- cancellation with process-tree termination;
- per-stage immutable evidence;
- separate technical and manual parity status;
- final delivery patch or branch manifest;
- token and cost report.

The MVP does not claim generic Angular 11+ reliability until the historical fixture suite validates additional source-version families.

# 28. Prioritized Implementation Plan

## 28.1 P0 — Required Before Core POC Execution

1. Baseline Qualification Gate.
2. Historical migration support levels and catalog.
3. Operational per-stage runtime manager.
4. Exact-version and frozen-lockfile policy.
5. Builder migration policy.
6. Hardened structured command execution.
7. Per-stage immutable artifact layout.
8. Independent technical and parity statuses.
9. Safe cancellation and process-tree termination.
10. State idempotency and persistent checkpoints.

## 28.2 P1 — Required Before Internal Demonstration

1. Workspace topology classification.
2. Parity manifest and deterministic comparison.
3. Repository prompt-injection protection.
4. Fixture-based AI and migration evaluation suite.
5. Token, cost, retry, quota, and worker telemetry.
6. Worker heartbeat, lease, stale-worker recovery, and resume validation.
7. Browser-support contract.
8. Bundle-size and build-output comparison.
9. Delivery branch or patch generation.
10. Clear auto-approval semantics across all stages.

## 28.3 P2 — Required Before Enterprise Delivery

1. Company-approved browser automation.
2. Company-approved security and quality gates.
3. PostgreSQL and distributed-worker architecture.
4. Authentication, RBAC, and separation of approval duties.
5. Tenant isolation and source-code retention policy.
6. Encryption and artifact-access controls.
7. Pull-request and CI/CD integration.
8. Operational dashboards, alerts, backup, and disaster recovery.
9. Complex workspace, Nx, microfrontend, SSR, and custom-builder support.
10. Controlled modernization modules as separate products.

# 29. Roadmap and Future Extensions

| **Phase** | **Goal**                                      | **Deliverables**                                                                                             |
|-----------|-----------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| Phase 1   | Foundation and eligibility                    | Job creation, Angular 11+ eligibility, client constraints, artifact structure.                               |
| Phase 2   | Workflow state and UI synchronization         | Run state, stage state, approval state, repair state, frontend card contract.                                |
| Phase 3   | Angular 18 → 21 POC                         | Analysis, upgrade ladder, ng update orchestration, build/test gates, final report.                           |
| Phase 4   | Repair Agent MVP                              | Failure classification, risk scoring, controlled repair loop, patch ledger, escalation after three attempts. |
| Phase 5   | Manual parity evidence                        | Route inventory, backend config check, manual browser/visual checklist.                                      |
| Phase 6   | Company-approved quality/security integration | Integrate only tools approved by company security protocol.                                                  |
| Phase 7   | Optional modernization module                 | Standalone/signals/control-flow/build-system modernization as separate client-approved capability.           |

# Appendix A. Example Artifact Schemas

## A.1 eligibility_result.json

> {  
> "detected_family": "angular",  
> "detected_major": 18,  
> "eligible": true,  
> "minimum_supported_source_major": 11,  
> "angularjs_indicators_found": false,  
> "pre_angular_11": false,  
> "recommended_path": "angular_11_plus_compatibility_upgrade"  
> }

## A.2 client_constraints.json

> {  
> "preserve_ui": true,  
> "preserve_behavior": true,  
> "preserve_business_logic": true,  
> "preserve_api_contracts": true,  
> "preserve_authentication_authorization": true,  
> "allow_optional_modernization": false,  
> "allowed_change_policy": "minimum_required_for_compatibility",  
> "approval_required_for_behavior_change": true  
> }

## A.3 upgrade_ladder.yaml

> source_angular_major: 18  
> target_angular_major: 21  
> strategy: one_major_at_a_time  
> stages:  
> - stage_id: angular-18-to-19  
> source_angular_major: 18  
> target_angular_major: 19  
> - stage_id: angular-19-to-20  
> source_angular_major: 19  
> target_angular_major: 20  
> - stage_id: angular-20-to-21  
> source_angular_major: 20  
> target_angular_major: 21

## A.4 allowed_and_forbidden_changes.yaml

> allowed_changes:  
> - package_version_alignment  
> - angular_cli_configuration_update  
> - typescript_rxjs_compatibility_fix  
> - deprecated_api_replacement_required_for_build  
> - angular_material_cdk_alignment_if_present  
> - test_config_update_required_for_validation  
> - backend_proxy_environment_config_preservation  
>   
> forbidden_without_approval:  
> - standalone_migration  
> - signal_api_migration  
> - new_control_flow_migration  
> - inject_function_style_refactor  
> - zoneless_migration  
> - ui_redesign  
> - business_logic_change  
> - api_contract_change  
> - authentication_authorization_change  
> - state_management_replacement  
> - introduction_of_unapproved_external_tools

# Appendix B. Glossary

| **Term**                       | **Definition**                                                                                     |
|--------------------------------|----------------------------------------------------------------------------------------------------|
| Functional parity              | The migrated app behaves like the original app from user, business, API, and route perspectives.   |
| Minimal diff                   | The smallest safe change required for compatibility and validation.                                |
| Sandbox                        | Mutable copy of the project used for transformation and repair. Original source remains read-only. |
| Gate                           | A validation or approval checkpoint that controls workflow progress.                               |
| Manual validation required     | A gate that cannot be automated in MVP and must be checked manually or accepted as risk.           |
| Deferred company tool required | A gate reserved for future integration with approved enterprise tooling.                           |
| Repair attempt                 | One controlled diagnosis-patch-validation cycle by the Repair Agent.                               |
| Backend execution authority    | The trusted service that validates and executes commands on behalf of agents.                      |

# References

The compatibility resolver must use a versioned internal policy built from official sources and company-approved evidence. External documentation is context, not a runtime execution dependency.

- Angular versioning and support policy: https://angular.dev/reference/releases
- Angular Node.js, TypeScript, RxJS, and browser compatibility: https://angular.dev/reference/versions
- Angular update guide: https://angular.dev/update-guide
- Angular CLI `ng update` reference: https://angular.dev/cli/update
- Angular application build-system migration: https://angular.dev/tools/cli/build-system-migration
- npm clean installation (`npm ci`): https://docs.npmjs.com/cli/v11/commands/npm-ci
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- Azure OpenAI REST API reference: https://learn.microsoft.com/en-us/azure/foundry/openai/reference
- Azure OpenAI reasoning models: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning
- Microsoft Entra ID and managed identity for Azure OpenAI: https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/managed-identity
- OpenAI GPT-5 overview: https://openai.com/gpt-5/

## Reference Governance

- Record source URL, retrieval date, content checksum where possible, and policy version.
- Do not resolve production migration decisions from live web content without review and caching.
- Refresh the internal compatibility catalog on an approved schedule.
- Re-run affected fixture migrations after catalog or toolchain updates.
