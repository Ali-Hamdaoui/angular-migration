> Original Word header: AI Frontend Migration Factory - Angular Agent Architecture
>
> Original Word footer: Generated architecture design - Angular 11+ strict parity MVP

**AI Frontend Migration Factory**

Angular 11+ Compatibility Migration  
Reliable and Efficient Agent Architecture Design

Scope: Angular 11+ technical upgrade with strict functional parity  
MVP reference: Angular 18.x -\> Angular 21.x, backend unchanged, version-range aware  
LLM provider: Azure OpenAI API, default main model deployment: GPT-5 mini

Prepared for architecture discussion and implementation planning

# Document Control

| **Item**                       | **Decision / Value**                                                                                                                                                                                                                                                                                             |
|--------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Document purpose               | Define the detailed agent architecture, agent contracts, inputs, outputs, artifacts, allowed tools, permissions, validation gates, MCP context policy, dynamic compatibility resolver, static symbol verification, rollback rules, and MVP implementation boundaries for the Angular 11+ Migration Factory.      |
| Primary scope                  | Angular 11 and later only. AngularJS and pre-Angular-11 applications are out of scope.                                                                                                                                                                                                                           |
| Migration objective            | Technical compatibility upgrade with minimum required code changes.                                                                                                                                                                                                                                              |
| Strict parity objective        | Same UI, same behavior, same routes, same API contracts, same business logic, same validation behavior, and same expected outputs unless explicitly approved.                                                                                                                                                    |
| MVP reference target           | Angular 18.x to Angular 21.x as the first reference POC. The workflow must not be hardcoded to Angular 18.2.x; Angular 18.0.x, 18.1.x, and 18.2.x must resolve through the same Angular 18 family profile. Node.js, TypeScript, RxJS, and Angular CLI versions are resolved per stage from compatibility policy. |
| MVP tool exclusions            | Do not use Playwright, Cypress, OSV scanner, Snyk, SonarQube, or Semgrep in the current MVP. Browser, visual, security, and quality gates are manual, deferred, or existing-project-command-only until company-approved tools are available.                                                                     |
| Reliability enhancements added | Compatibility Resolver, Stage Toolchain Profiles, Static Symbol Verification, Dependency Audit, Package Install Script Audit, Backend Contract Snapshot, Changed-File Risk Classification, Rollback Levels, Auto-Continue Rules, and Security Protocol Compliance reporting.                                     |
| MCP policy                     | MCP is optional and disabled by default. If approved, it is used as read-only LLM context support for Angular documentation, migration guidance, best practices, and examples. It is not an execution dependency in the MVP.                                                                                     |
| **LLM provider**               | Azure OpenAI API through a backend-controlled LLM Gateway. API keys, endpoints, deployment names, and API versions are backend configuration and must not be exposed to agents or the frontend.                                                                                                                  |
| **Main LLM model**             | GPT-5 mini is the default/main LLM deployment for all agents. The deployment name must be configurable and environment-specific, not hardcoded inside agent prompts.                                                                                                                                             |
| **LLM access policy**          | Every agent may request LLM assistance, but only through the LLM Gateway. The LLM proposes reasoning, summaries, plans, diagnoses, or patches; backend services remain responsible for execution, mutation, validation, rollback, and approvals.                                                                 |

# Table of Contents

- Appendix B. Glossary

- Appendix A. Example Artifact Schemas

- 19\. Roadmap and Future Extensions

- 18\. MVP Implementation Recommendation

- 17\. API and Schema Examples

- 16\. Repair Policy, Rollback, and Escalation Rules

- 15\. Dependency Audit, Install Script Audit, and Backend Contract Snapshot

- 14\. Validation Gates, Static Symbol Verification, and Definition of Done

- 13\. Tooling Policy and MVP Restrictions

- 12\. Artifact Model and Audit Trail

- 11\. Workflow State Management

- 10\. Detailed Agent Specifications

- 9\. Agent Catalog and Responsibility Matrix

- 8\. Common Agent Contract

- 7\. Agent Execution Model

- 6\. MCP Context Support Policy

- 5\. Target System Architecture

- 4\. Compatibility Resolver and Stage Toolchain Profiles

- 3\. Version-Range Compatibility and Dynamic Version Resolution

- 2\. Architecture Principles

- 1\. Executive Summary

# Executive Summary

This document defines the detailed architecture of the Angular 11+ Compatibility Migration Factory from an agentic execution perspective. The factory is designed to upgrade Angular applications from version 11 or later to a client-approved supported target version while preserving strict functional parity.

The system must not be treated as a generic modernization tool. Its default behavior is compatibility migration only. Any redesign, standalone migration, signals migration, new control-flow migration, state-management replacement, API contract change, authentication change, or business-logic refactor is blocked unless explicitly approved.

The architecture uses a small number of specialized agents. Each agent has a limited responsibility, a controlled input contract, a structured output contract, allowed tools, forbidden actions, generated artifacts, and escalation rules. The backend remains the execution authority: agents can request actions, but the backend validates and executes them inside a sandbox workspace only.

## 1.1 MVP Design Direction

- Use a single Angular 11+ compatibility upgrade path.

- For the current POC, execute Angular 18 -\> 19 -\> 20 -\> 21 as staged upgrades.

- Keep the backend unchanged; only the Angular frontend is in scope.

- Use official Angular CLI and package-manager commands before LLM reasoning.

- Use existing project test and lint commands only if already configured.

- Do not introduce Playwright, Cypress, OSV, Snyk, SonarQube, or Semgrep in the MVP.

- Generate manual/deferred validation items where company-approved tools are not available.

- Persist every analysis, approval, command, patch, validation result, repair attempt, and report artifact.

# Architecture Principles

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

# Version-Range Compatibility and Dynamic Version Resolution

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

# Compatibility Resolver and Stage Toolchain Profiles

The Compatibility Resolver is the component that makes the migration factory reliable across Angular version ranges. It prevents the platform from becoming a static script for one exact version, such as Angular 18.2.x. It receives exact detected versions from the Analysis Agent and converts them into normalized version families, compatibility decisions, and executable stage profiles.

## 4.1 Compatibility Resolver Responsibilities

- Normalize exact detected versions into source families, for example 18.0.4 -\> Angular 18.x.

- Resolve the target Angular family from client policy, company policy, and supported Angular compatibility data.

- Generate the one-major-at-a-time ladder from source major to target major.

- Resolve Node.js, TypeScript, RxJS, Zone.js, Angular CLI, and package manager behavior per stage.

- Generate command plans and validation plans per stage.

- Fail only when no safe compatibility profile exists, not when a patch version was not explicitly listed.

## 4.2 Compatibility Resolution Output

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

## 4.3 Stage Toolchain Profile

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

## 4.4 Stage Toolchain Profile Example

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

# Target System Architecture

The Angular migration factory should reuse the same enterprise operating model as the Spring Boot Migration Factory: a Control Tower UI, a backend execution authority, an orchestrator, a sandbox workspace, an artifact store, and a state store.

> Control Tower UI - \> AI Assistant  
> \|  
> v  
> FastAPI Backend / Execution Authority  
> \|  
> v  
> LangGraph Orchestrator  
> \|  
> v  
> Eligibility + Constraints -\> Analysis -\> Approval -\> Planning -\> Approval  
> \|  
> v  
> For each Angular major stage:  
> Transformation -\> Build/Validation -\> Repair Loop -\> Checkpoint  
> \|  
> v  
> Report Agent -\> Final Evidence Report

## 4.1 Main Components

| **Component**               | **Responsibility**                                                                                                                                            |
|-----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Control Tower UI            | Creates migration jobs, captures environment information, displays backend-driven workflow state, exposes approvals, and provides access to the AI Assistant. |
| AI Assistant                | User-facing conversational layer for explanation, clarification, feedback capture, and approval assistance. It does not execute commands or mutate code.      |
| Backend Execution Authority | Validates structured actions, checks permissions, enforces sandbox-only mutation, executes commands, persists logs, and rejects unsafe requests.              |
| LangGraph Orchestrator      | Coordinates agent sequence, state transitions, approval gates, stage execution, retry limits, repair loops, and escalation.                                   |
| Sandbox Workspace           | The only mutable copy of the application during transformation and repair.                                                                                    |
| Artifact Store              | Stores analysis reports, plans, approvals, diffs, logs, validation reports, repair reports, and final evidence.                                               |
| State Store                 | Stores run state, stage state, current agent, approval status, validation gate status, and repair attempt count. This is the source of truth for the UI.      |

# MCP Context Support Policy

MCP is not an execution dependency in the MVP. It is an optional context-support capability for the LLM. Its role is to provide Angular documentation, migration guidance, best practices, and official examples so the LLM can plan, diagnose, and propose repairs with better context. All execution, patching, validation, rollback, and approval remain controlled by the backend.

## 6.1 MCP Modes

| **Mode**                 | **MVP Policy**                  | **Allowed Use**                                                                                                                            | **Forbidden Use**                                                                                 |
|--------------------------|---------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| MCP Disabled Mode        | Default                         | No MCP server is started. The factory uses backend-controlled commands and local project analysis.                                         | None, because MCP is not used.                                                                    |
| MCP Context Support Mode | Optional, company-approved only | Read-only Angular documentation search, best-practices lookup, migration guidance, official examples, and explanation support for the LLM. | No command execution, no file mutation, no ng update, no build/test/devserver execution.          |
| MCP Workspace Mode       | Future only, not MVP            | Could inspect workspace or run targets only after company approval, readiness probe, and backend authorization.                            | Must not bypass backend authority, approval gates, sandbox policy, or modernization restrictions. |

## 6.2 MCP Security Rules

- MCP is disabled by default unless approved by company security policy.

- The migration factory must work without MCP.

- In the MVP, MCP is read-only context support for the LLM, not a command runner.

- The LLM may use MCP context to propose a diagnosis or patch, but the backend validates and applies any patch.

- MCP must not execute ng update, build, test, lint, devserver, or modernization actions in the MVP.

- Every MCP request and response must be logged as an artifact if MCP is enabled.

## 6.3 MCP Artifact

{  
"artifact": "04_workflow_state/mcp_context_usage_log.json",  
"mode": "disabled \| context_support \| workspace_future",  
"policy_status": "disabled_by_default \| approved_read_only \| blocked",  
"used_for": \["documentation_lookup", "migration_guidance", "repair_reasoning"\],  
"execution_actions_allowed": false  
}

# Agent Execution Model

Each agent is a bounded worker. It receives a structured input, reads only the artifacts it is allowed to read, requests only the actions it is allowed to request, and returns a structured result. The orchestrator decides the next state based on that result.

## 5.1 Agent Permissions Model

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

## 5.2 Agent Result Statuses

| **Status**                  | **Meaning**                                                                                    | **Typical Next State**                          |
|-----------------------------|------------------------------------------------------------------------------------------------|-------------------------------------------------|
| completed                   | The agent finished successfully and produced expected artifacts.                               | Next planned workflow state.                    |
| failed                      | The agent failed due to a technical or execution error.                                        | FAILED or REPAIR_RUNNING depending on context.  |
| blocked                     | The agent cannot continue because required data, package, environment, or approval is missing. | WAITING\_\*\_APPROVAL or FAILED.                |
| requires_approval           | The agent found a risky or strategic decision that needs human review.                         | WAITING\_\*\_APPROVAL.                          |
| completed_with_manual_items | Core technical checks passed but some company-tool or manual gates remain pending.             | Next state only if policy accepts manual items. |

# Common Agent Contract

All agents should use a shared input and output envelope so the orchestrator, backend, UI, and artifact store can handle agent responses consistently.

## 6.1 Common Input Envelope

> {  
> "run_id": "migration-run-001",  
> "stage_id": "angular-18-to-19",  
> "repository_source": {  
> "source_repo_url": "...",  
> "source_branch": "main",  
> "source_read_only": true  
> },  
> "workspace": {  
> "sandbox_path": "/sandbox/runs/migration-run-001/app",  
> "sandbox_branch": "migration/angular-run-001"  
> },  
> "client_constraints": {  
> "preserve_ui": true,  
> "preserve_behavior": true,  
> "preserve_business_logic": true,  
> "preserve_api_contracts": true,  
> "preserve_authentication_authorization": true,  
> "allow_optional_modernization": false  
> },  
> "approved_plan_checksum": "sha256:...",  
> "current_workflow_state": "TRANSFORMATION_RUNNING",  
> "allowed_actions": \["read_file", "run_approved_command"\],  
> "artifact_locations": {  
> "analysis": "runs/{run_id}/02_analysis/",  
> "planning": "runs/{run_id}/03_planning/",  
> "validation": "runs/{run_id}/06_validation/"  
> }  
> }

## 6.2 Common Output Envelope

> {  
> "agent_name": "analysis_agent",  
> "run_id": "migration-run-001",  
> "stage_id": null,  
> "status": "completed",  
> "summary": "Angular 18.x application detected and accepted for Angular 11+ compatibility migration.",  
> "artifacts_created": \[  
> "runs/migration-run-001/02_analysis/angular_workspace_analysis.json"  
> \],  
> "risks": \[  
> {  
> "risk_id": "dependency-peer-conflict-risk",  
> "severity": "medium",  
> "description": "Some packages may require version alignment during Angular 19 stage."  
> }  
> \],  
> "requires_human_action": false,  
> "next_recommended_state": "WAITING_ANALYSIS_APPROVAL"  
> }

# Agent Catalog and Responsibility Matrix

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

# Detailed Agent Specifications

## 8.1 AI Assistant Agent

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

## 8.2 Eligibility and Constraint Agent

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

## 8.3 Analysis Agent

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

- 01_baseline/baseline_routes.json when baseline route inventory is generated

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

## 8.3.1 Enhanced Analysis Outputs

To make the architecture more reliable, the Analysis Agent must now produce explicit dependency, install-script, backend-contract, and changed-file sensitivity inventories. These are used by the Planning, Build, Repair, and Report agents.

- 02_analysis/dependency_audit.json

- 02_analysis/private_package_inventory.json

- 02_analysis/package_install_script_audit.json

- 01_baseline/backend_contract_snapshot.json

- 02_analysis/changed_file_sensitivity_rules.json

- 03_planning/compatibility_resolution.json

## 8.4 Human Approval Gate 1 - Analysis Approval

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

## 8.5 Planning Agent

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

## 8.6 Human Approval Gate 2 - Plan Approval

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

## 8.7 Transformation Agent

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

## 8.8 Build / Validation Agent

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

## 8.9 Repair Agent

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

## 8.10 Report Agent

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

## 8.9 Orchestrator

The Orchestrator is the workflow controller. It may be implemented with LangGraph or another state-machine engine. It is responsible for deciding which agent runs next and for enforcing approval and retry rules.

- Creates and updates migration run state.

- Starts agents only when prerequisites are satisfied.

- Moves workflow through analysis, approval, planning, transformation, build, repair, validation, checkpoint, and report states.

- Prevents transformation before plan approval.

- Prevents next-stage execution before validation is complete.

- Stops automatic repair after three attempts.

- Handles cancel, failure, and resume behavior.

- Makes backend state the source of truth for the frontend.

## 8.10 Backend Execution Authority

The Backend Execution Authority is the trusted execution layer. Agents do not directly execute commands. They submit structured action requests. The backend validates the action against the approved plan, command registry, sandbox policy, and risk policy before executing it.

> {  
> "requested_by": "transformation_agent",  
> "action_type": "run_command",  
> "command": "npx ng update @angular/core@19 @angular/cli@19",  
> "working_directory": "/sandbox/runs/run-001/app",  
> "stage_id": "angular-18-to-19",  
> "requires_approval": true,  
> "approved_plan_checksum": "sha256:..."  
> }

- Validate command is allowed for the current stage.

- Validate command runs only inside sandbox workspace.

- Validate plan approval checksum.

- Reject forbidden modernization actions.

- Persist command, stdout, stderr, exit code, duration, and generated artifacts.

- Return structured execution result to the requesting agent.

# Workflow State Management

The frontend must not infer workflow progress from local component state or displayed cards. Every visible card, button, status, repair attempt number, and approval action must come from the backend state store.

## 9.0 Enhanced Stage States

The stage model should expose finer-grained state transitions so the Control Tower can show exactly where the migration is blocked and which component owns the next action.

STAGE_CREATED  
TOOLCHAIN_PROFILE_SELECTED  
SANDBOX_READY  
DEPENDENCY_AUDITED  
MCP_CONTEXT_POLICY_RESOLVED  
TRANSFORMATION_RUNNING  
STATIC_SYMBOL_CHECK_RUNNING  
VALIDATION_RUNNING  
VALIDATION_PASSED  
REVIEW_READY  
STAGE_COMMITTED  
STAGE_ROLLED_BACK  
DIAGNOSTIC_HOLD

## 9.1 Core Run States

| **State**                                         | **Meaning**                                            |
|---------------------------------------------------|--------------------------------------------------------|
| CREATED                                           | Migration job created.                                 |
| CLIENT_CONSTRAINTS_CAPTURED                       | Strict parity and scope constraints recorded.          |
| ELIGIBILITY_RUNNING / ELIGIBILITY_FAILED          | Eligibility validation is running or failed.           |
| ANALYSIS_RUNNING / ANALYSIS_COMPLETED             | Analysis is running or finished.                       |
| WAITING_ANALYSIS_APPROVAL                         | Human decision required after analysis.                |
| PLANNING_RUNNING / PLANNING_COMPLETED             | Planning is running or finished.                       |
| WAITING_PLAN_APPROVAL                             | Human decision required before sandbox transformation. |
| STAGE_RUNNING                                     | A migration stage is active.                           |
| TRANSFORMATION_RUNNING                            | Approved stage transformation is running.              |
| BUILD_RUNNING / BUILD_FAILED                      | Build/validation is running or failed.                 |
| REPAIR_RUNNING / REPAIR_COMPLETED / REPAIR_FAILED | Repair loop status.                                    |
| WAITING_REPAIR_APPROVAL                           | Risky or blocked repair needs human decision.          |
| VALIDATION_RUNNING                                | Final gate validation is running.                      |
| STAGE_COMPLETED                                   | Stage passed validation or accepted risk was recorded. |
| REPORT_RUNNING                                    | Final report is being generated.                       |
| COMPLETED / FAILED / CANCELLED                    | Terminal states.                                       |

## 9.2 Stage State Schema

> {  
> "stage_id": "angular-18-to-19",  
> "stage_order": 1,  
> "source_angular_major": 18,  
> "target_angular_major": 19,  
> "stage_type": "compatibility_upgrade",  
> "status": "running",  
> "current_agent": "build_validation_agent",  
> "repair_attempts": 0,  
> "max_repair_attempts": 3,  
> "requires_approval": false,  
> "validation_gates": \["install", "build", "unit_tests_if_configured", "lint_if_configured"\],  
> "manual_gates": \["browser_smoke", "visual_parity"\],  
> "deferred_gates": \["external_security_scan", "external_quality_scan"\],  
> "started_at": "...",  
> "completed_at": null  
> }

## 9.3 Frontend Display Rules

- Every card status must come from backend state.

- Approve buttons appear only in waiting approval states.

- Stage cards must show source and target Angular major version.

- Repair cards must show attempt count and risk level.

- Manual/deferred validation gates should be shown clearly, not hidden.

- A stage is completed only when validation passes or accepted risk is recorded.

- AI Assistant approvals and UI button approvals must create the same backend approval record.

# Artifact Model and Audit Trail

Artifacts are the evidence backbone of the migration factory. They make the system reviewable, auditable, and safe for consulting/client delivery.

> runs/{run_id}/  
> 00_job_setup/  
> eligibility_result.json  
> client_constraints.json  
> target_version_policy.json  
> read_only_verification.json  
>   
> 01_baseline/  
> baseline_run_report.json  
> baseline_routes.json  
> baseline_test_report.json  
> manual_baseline_notes.md  
>   
> 02_analysis/  
> angular_workspace_analysis.json  
> package_inventory.json  
> dependency_graph.json  
> route_inventory.json  
> environment_inventory.json  
> material_cdk_inventory.json  
> test_inventory.json  
> backend_integration_inventory.json  
>   
> 03_planning/  
> migration_plan.yaml  
> upgrade_ladder.yaml  
> migration_units.yaml  
> allowed_and_forbidden_changes.yaml  
> risk_assessment.json  
> rollback_strategy.md  
> approval_request.md  
>   
> 04_workflow_state/  
> migration_run_state.json  
> stage_state_history.json  
> agent_execution_history.json  
> approval_events.json  
> user_interaction_events.json  
>   
> 05_sandbox_transform/  
> sandbox_manifest.json  
> applied_migrations.json  
> patch_ledger.json  
> minimal_diff_report.json  
> package_json_diff.json  
> angular_json_diff.json  
> source_diff.patch  
>   
> 06_validation/  
> install_report.json  
> build_report.json  
> lint_report.json  
> unit_test_report.json  
> route_inventory_validation.json  
> backend_config_report.json  
> manual_parity_checklist.md  
> security_quality_deferred_report.json  
> stage_validation_summary.json  
>   
> 07_repair/  
> repair_attempts.json  
> repair_diagnosis_reports.json  
> repair_patch_ledger.json  
> repair_risk_decisions.json  
> human_escalation_requests.json  
>   
> 08_final/  
> final_migration_evidence_report.md  
> compatibility_upgrade_summary.md  
> manual_actions_required.md  
> unresolved_blockers.json

## 10.1 Artifact Rules

- Every artifact must include run_id and timestamp.

- Every artifact used for approval must be checksum-bound.

- Every command execution must store command, working directory, exit code, stdout, stderr, duration, and agent requester.

- Every patch must include affected files, reason, risk level, expected behavior impact, and validation result.

- Every manual/deferred validation gate must be visible in the final report.

- No final report should claim a gate passed if it was not executed.

## Additional Reliability Artifacts

The following artifacts are added to strengthen auditability, security, and repair safety:

| **Artifact**                                               | **Owner**                   | **Purpose**                                                                                                |
|------------------------------------------------------------|-----------------------------|------------------------------------------------------------------------------------------------------------|
| 03_planning/compatibility_resolution.json                  | Compatibility Resolver      | Explains exact-version detection, normalized version families, target selection, and upgrade ladder.       |
| 03_planning/stage_toolchain_profiles.json                  | Planning Agent              | Defines per-stage Node, TypeScript, RxJS, Angular CLI, command plan, validation plan, and rollback point.  |
| 02_analysis/dependency_audit.json                          | Analysis Agent              | Classifies dependencies as safe, needs bump, needs guide, unknown risk, blocking, or approval-required.    |
| 02_analysis/package_install_script_audit.json              | Analysis/Build Agent        | Reports preinstall/install/postinstall/prepare scripts before dependency installation in sandbox.          |
| 01_baseline/backend_contract_snapshot.json                 | Analysis Agent              | Captures frontend/backend contract signals before migration.                                               |
| 06_validation/static_symbol_check_report.json              | Build/Validation Agent      | Checks imports, symbols, Angular/RxJS/Material APIs, templates, and unapproved dependencies after patches. |
| 05_sandbox_transform/changed_file_risk_classification.json | Transformation/Repair Agent | Classifies changed files by risk level before auto-continuation or escalation.                             |
| 04_workflow_state/rollback_events.json                     | Orchestrator                | Records patch rollback, stage rollback, migration rollback, and diagnostic hold events.                    |
| 08_final/security_protocol_compliance.md                   | Report Agent                | Documents that excluded tools were not used and sandbox/security rules were respected.                     |

# Tooling Policy and MVP Restrictions

Because company security protocol limits external tools, the current MVP must rely only on existing project commands, Angular CLI, package manager commands, file scanners, and internal backend validation. External browser automation and external security/quality scanners are excluded for now.

## 11.1 MVP-Allowed Tools

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

## 11.2 Excluded from Current MVP

| **Excluded Tool** | **Current Policy**         |
|-------------------|----------------------------|
| Playwright        | Do not use in current MVP. |
| Cypress           | Do not use in current MVP. |
| OSV scanner       | Do not use in current MVP. |
| Snyk              | Do not use in current MVP. |
| SonarQube         | Do not use in current MVP. |
| Semgrep           | Do not use in current MVP. |

## 11.3 How Excluded Gates Are Reported

- Browser smoke is reported as manual_validation_required for the MVP.

- Visual parity is reported as manual_validation_required for the MVP.

- External security scanning is reported as deferred_company_tool_required for the MVP.

- External quality scanning is reported as deferred_company_tool_required for the MVP.

- These statuses should not fail the MVP automatically unless company policy says the gate is mandatory before delivery.

# Validation Gates and Definition of Done

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
| Changed-file risk classification | Mandatory after diff    | Classify changed files as low, medium, high, or blocked based on path and sensitivity.                                                                                  |
| Backend contract snapshot/diff   | Mandatory evidence      | Capture API base URLs, proxy config, interceptors, auth headers, token/cookie usage, request builders, response mappers, and error handling references.                 |

## 12.1 Stage Definition of Done - MVP

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

## Static Symbol Verification Gate

Static Symbol Verification is required after every LLM-generated or Repair Agent patch. It is a cheap deterministic anti-hallucination gate that prevents the system from continuing with nonexistent imports, phantom APIs, invalid template references, or unapproved dependencies.

| **Check**                          | **Expected Result**                                                                                                                 |
|------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| Import resolution                  | All imports introduced or changed by the patch resolve locally.                                                                     |
| Symbol existence                   | All referenced classes, functions, constants, decorators, and members exist.                                                        |
| Angular/RxJS/Material API validity | No phantom APIs or package names are introduced.                                                                                    |
| Template diagnostics               | Changed templates pass Angular compiler/template diagnostics where available.                                                       |
| Dependency approval                | No new dependency or package replacement appears without approved plan or human approval.                                           |
| Changed file sensitivity           | Changed files are classified before auto-continuation.                                                                              |
| Compatibility Resolver             | Architecture component that normalizes exact versions into version families and generates compatible stage profiles.                |
| Stage Toolchain Profile            | Per-stage definition of Node.js, TypeScript, RxJS, Angular CLI, package manager, commands, validation gates, and rollback point.    |
| Static Symbol Verification         | Deterministic gate that checks imports, symbols, APIs, template references, and dependencies after AI or repair patches.            |
| MCP Context Support Mode           | Optional read-only mode where MCP gives Angular documentation and migration guidance context to the LLM without executing commands. |
| Diagnostic hold                    | Safe stop state that preserves the failed workspace for human investigation and produces a blocker report.                          |
| Changed-file risk classification   | Risk assessment based on which files changed and how sensitive those files are to behavior, auth, API, UI, or security.             |

## Validation Status Vocabulary

Validation results must use explicit statuses so unavailable MVP tools are not hidden and are not falsely marked as failures.

passed  
failed  
not_configured  
manual_validation_required  
deferred_company_tool_required  
blocked_by_environment  
accepted_risk

# Dependency Audit, Install Script Audit, and Backend Contract Snapshot

These lightweight checks improve reliability without introducing external security scanners. They rely on package metadata, lockfiles, source scanning, and backend configuration analysis.

## 15.1 Dependency Audit Categories

| **Category**           | **Examples**                                                        |
|------------------------|---------------------------------------------------------------------|
| Angular packages       | @angular/core, @angular/cli, @angular/compiler, @angular/router     |
| Angular ecosystem      | Angular Material/CDK, RxJS, Zone.js                                 |
| Workspace/tooling      | Nx if present, custom builders, test frameworks, lint tools         |
| UI libraries           | PrimeNG, AG Grid, NG Bootstrap, Bootstrap, internal UI kits         |
| State management       | NgRx, Akita, NGXS, services, custom stores                          |
| Enterprise constraints | Private packages, abandoned packages, packages with install scripts |

## 15.2 Dependency Risk Classification

safe  
needs_version_bump  
needs_migration_guide  
requires_approval  
unknown_risk  
blocking

## 15.3 Package Install Script Audit

Before package installation, the system should inspect package metadata and lockfile information where possible to identify packages that define preinstall, install, postinstall, or prepare scripts. These scripts must execute only inside the sandbox and must be reported in the final evidence.

## 15.4 Backend Contract Snapshot

Because the backend remains unchanged in the MVP, the frontend migration must not silently change how the Angular application communicates with the Java/Spring Boot backend. The backend contract snapshot records API-related frontend behavior before migration and compares it after each stage where possible.

- environment API base URLs and proxy configuration

- HTTP interceptors and auth header logic

- token or cookie usage

- API service files and request payload builders

- response mappers and error handling logic

- guards, resolvers, and route-level authorization references

# Repair Policy and Escalation Rules

| **Risk Level** | **Examples**                                                                                                        | **Default Action**                                               |
|----------------|---------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| Low            | Missing import, simple typing fix, required module import, angular.json builder adjustment with no behavior impact. | Repair Agent may auto-apply in sandbox and validate.             |
| Medium         | RxJS operator import change, routing declaration adjustment, dependency alignment with possible side effects.       | Auto-apply only if allowed by approved plan; otherwise escalate. |
| High           | Business logic, calculations, API payload, auth, permissions, security flow, UI behavior.                           | Human approval required before patch. Usually blocked for MVP.   |
| Blocked        | Missing private package, unavailable backend, unclear expected behavior, unknown test expectation.                  | Stop automatic repair and escalate with diagnosis.               |

## 13.1 Automatic Repair Scope

- Missing imports and missing symbols.

- Typing errors caused by TypeScript/framework upgrade.

- Approved dependency alignment inside migration plan.

- Angular configuration and test configuration required for compatibility.

- NgModule declarations, providers, routing configuration, and required imports compatible with current architecture.

- Known deprecated API replacements required for build/runtime compatibility.

- Simple test setup updates when behavior and expected output are unchanged.

## 13.2 Restricted Repair Scope

- Business rules or calculation logic.

- API contracts and payload structure.

- Authentication or authorization logic.

- Payment or permission logic.

- Security-sensitive logic.

- UI appearance or layout changes.

- State-management design changes.

- Any change where behavior preservation cannot be proven.

## Rollback Levels

Rollback must be explicit and automated where safe. The system should never continue with a failed patch or unclear repair state.

| **Rollback Level** | **Trigger**                                                                            | **Action**                                                                      |
|--------------------|----------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| Patch rollback     | A Repair Agent or LLM patch fails static symbol verification or targeted validation.   | Undo only the last patch and preserve diagnosis artifacts.                      |
| Stage rollback     | Stage-level dependency alignment or repeated repair attempts leave the stage unstable. | Reset sandbox to the checkpoint created before the current major-version stage. |
| Migration rollback | The migration must be abandoned or restarted from the original baseline.               | Reset to the original read-only input state and preserve evidence.              |
| Diagnostic hold    | The state is useful for human investigation but unsafe to continue automatically.      | Stop automation, preserve failed workspace, and generate blocker report.        |

## Auto-Continue and Human Approval Rules

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

## Changed-File Risk Classification

| **Risk** | **File Examples**                                                                                                                | **Default Decision**                                              |
|----------|----------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| Low      | package.json, lockfile, angular.json, tsconfig, browserslist, polyfills, test setup                                              | May auto-continue if validation passes.                           |
| Medium   | routing modules, shared modules, RxJS-heavy services, Angular Material module files                                              | Auto-continue only if approved plan allows and validation passes. |
| High     | auth services, interceptors, guards, permissions, API mappers, form validators, calculation/business services, environment files | Human approval required.                                          |
| Blocked  | Files where expected behavior cannot be determined or private package behavior is unknown                                        | Diagnostic hold or escalation.                                    |

# API and Schema Examples

## 14.1 Approval Endpoint Payload

> POST /migrations/{runId}/approvals  
> {  
> "approval_gate": "analysis \| planning \| repair",  
> "approved_by": "user",  
> "approval_source": "ui_button \| assistant_command",  
> "checksum": "sha256:...",  
> "decision": "approved \| rejected \| modification_requested \| approved_with_risk",  
> "user_comment": "optional"  
> }

## 14.2 Build Failure Report

> {  
> "gate": "ng_build",  
> "status": "failed",  
> "category": "angular_template_compile_error",  
> "root_cause_summary": "Template references a property not available after stricter compiler checks.",  
> "affected_files": \["src/app/features/orders/order-list.component.html"\],  
> "repair_attempt": 0,  
> "max_repair_attempts": 3,  
> "requires_human_review": false,  
> "recommended_next_state": "REPAIR_RUNNING"  
> }

## 14.3 MVP Validation Summary

> {  
> "stage_id": "angular-18-to-19",  
> "validation_status": "passed_with_manual_items",  
> "gates": {  
> "install": "passed",  
> "build": "passed",  
> "type_check": "passed",  
> "unit_tests": "passed_or_not_configured",  
> "lint": "passed_or_not_configured",  
> "route_inventory": "completed",  
> "backend_config_check": "completed",  
> "browser_smoke": "manual_validation_required",  
> "visual_parity": "manual_validation_required",  
> "security_scan": "deferred_company_tool_required",  
> "quality_scan": "deferred_company_tool_required"  
> },  
> "excluded_tools": \["Playwright", "Cypress", "OSV", "Snyk", "SonarQube", "Semgrep"\],  
> "requires_human_review": false  
> }

## 14.4 Repair Attempt Report

> {  
> "attempt": 1,  
> "stage": "angular-18-to-19",  
> "error_category": "missing_import",  
> "impacted_files": \["src/app/app.routes.ts"\],  
> "diagnosis": "Route configuration references a component without importing it.",  
> "repair_strategy": "Add missing import only. Do not change route path or behavior.",  
> "risk_level": "low",  
> "minimal_diff": true,  
> "behavior_change_expected": false,  
> "validation_result": "passed",  
> "escalated_to_human": false  
> }

## 14.5 Compatibility Resolution Schema

{  
"artifact": "03_planning/compatibility_resolution.json",  
"source_family": "angular-18.x",  
"target_family": "angular-21.x",  
"accepted_source_range": "\>=11.0.0",  
"exact_patch_supported_by_range": true,  
"upgrade_ladder": \["angular-18-to-19", "angular-19-to-20", "angular-20-to-21"\]  
}

## 14.6 Static Symbol Check Schema

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

## 14.7 Security Protocol Compliance Schema

{  
"artifact": "08_final/security_protocol_compliance.md",  
"source_repository_mutated": false,  
"sandbox_only_mutation": true,  
"excluded_tools_used": \[\],  
"excluded_tools_policy": \["Playwright", "Cypress", "OSV", "Snyk", "SonarQube", "Semgrep"\],  
"mcp_mode": "disabled_or_context_support_only",  
"manual_or_deferred_gates_documented": true  
}

# MVP Implementation Recommendation

The first MVP should prove the architecture with a small Angular 18.x application migrated to Angular 21.x. It should not try to implement all enterprise-grade quality and browser automation gates in the first iteration.

## 15.1 Recommended MVP Agent Split

| **MVP Agent**                    | **Build Now?** | **Reason**                                            |
|----------------------------------|----------------|-------------------------------------------------------|
| AI Assistant                     | Yes            | Needed for explanation, user feedback, and approvals. |
| Eligibility and Constraint Agent | Yes            | Protects scope and records strict parity constraints. |
| Analysis Agent                   | Yes            | Needed to understand current Angular app and risks.   |
| Planning Agent                   | Yes            | Needed to generate 18 -\> 19 -\> 20 -\> 21 ladder.    |
| Transformation Agent             | Yes            | Core migration execution in sandbox.                  |
| Build / Validation Agent         | Yes            | Core proof that each stage installs and builds.       |
| Repair Agent                     | Yes, limited   | Only low-risk repairs, max three attempts.            |
| Report Agent                     | Yes            | Needed to prove value and generate final evidence.    |
| Separate Security Agent          | No             | Deferred until company-approved tools are available.  |
| Separate Browser Agent           | No             | Manual/browser parity checklist for MVP.              |
| Separate Test Agent              | No             | Existing tests handled by Build Agent.                |

## 15.2 MVP Stage Flow for Angular 18 -\> 21

1.  Create migration job and capture client constraints.

2.  Run eligibility and analysis.

3.  Approve analysis.

4.  Generate plan with stages: Angular 18 -\> 19, 19 -\> 20, 20 -\> 21.

5.  Approve plan.

6.  For each stage: transform in sandbox, run validation, repair if needed, checkpoint if valid.

7.  Generate final report with validation results, manual/deferred gates, diff, repair history, and unresolved items.

## 15.3 MVP Success Criteria

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

## Security Protocol Compliance in Final Report

The final report must include a dedicated section proving that the migration respected company security constraints and MVP tool exclusions.

- Original repository remained read-only.

- All mutations happened in sandbox.

- No excluded tools were used: Playwright, Cypress, OSV, Snyk, SonarQube, or Semgrep.

- MCP, if used, was used only as context support and not as an execution tool.

- Commands, outputs, diffs, repair attempts, and rollback events were logged.

- Manual and deferred gates are visible and not falsely marked as passed.

# Roadmap and Future Extensions

| **Phase** | **Goal**                                      | **Deliverables**                                                                                             |
|-----------|-----------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| Phase 1   | Foundation and eligibility                    | Job creation, Angular 11+ eligibility, client constraints, artifact structure.                               |
| Phase 2   | Workflow state and UI synchronization         | Run state, stage state, approval state, repair state, frontend card contract.                                |
| Phase 3   | Angular 18 -\> 21 POC                         | Analysis, upgrade ladder, ng update orchestration, build/test gates, final report.                           |
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

- Source project proposal: Angular 11+ Compatibility Migration and Technical Upgrade - Strict Functional Parity Proposal.

- Current MVP decisions from discussion: external tools Playwright, Cypress, OSV scanner, Snyk, SonarQube, and Semgrep are excluded from current MVP scope.

- Implementation reference points: Angular CLI update workflow, Angular version compatibility policy, internal company security protocol, and backend-controlled sandbox execution.

# Azure OpenAI LLM Assistance Layer and Per-Agent LLM Access

**Purpose.** All migration agents may use an LLM to improve reasoning, diagnosis, planning, explanation, and report generation. The LLM is not the execution authority. The backend remains responsible for command execution, file mutation, validation, rollback, and approval enforcement.

**Default provider and model.** The MVP uses Azure OpenAI API through a backend-controlled LLM Gateway. GPT-5 mini is the main/default model deployment. The deployment name, endpoint, API version, region, authentication method, timeout, and retry policy must be configuration values, not hardcoded in prompts or agents.

**Design principle.** Every agent can ask for LLM assistance, but no agent gets direct access to Azure credentials, shell execution, repository mutation, or approval bypass. LLM output is treated as a proposal that must pass deterministic backend checks before it affects the sandbox.

| **Area**            | **Architecture Decision**                                                                                                                             |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| Provider            | Azure OpenAI API, accessed only through the backend LLM Gateway.                                                                                      |
| Main model          | GPT-5 mini as the default/main deployment for all agents.                                                                                             |
| Configuration       | Endpoint, deployment name, API version, region, quotas, and authentication are environment configuration and must not be hardcoded.                   |
| Agent access        | All agents can request LLM assistance through structured calls to the LLM Gateway.                                                                    |
| Execution boundary  | The LLM cannot directly execute npm, ng, git, shell commands, MCP workspace tools, or file mutations.                                                 |
| Validation boundary | LLM outputs that propose patches must pass static symbol verification, build validation, risk classification, and approval policy before progression. |
| Data boundary       | Prompts must send the minimum necessary context. Secrets, tokens, private credentials, and production environment values must be redacted.            |
| Traceability        | All LLM calls are logged with redacted prompts, response summaries, model deployment, timestamps, token usage if available, and artifact references.  |

## LLM Gateway Responsibilities

- Centralize all Azure OpenAI API calls for every agent.

- Inject the correct system prompt, agent role, context packet, and output schema.

- Apply prompt-size limits, timeout limits, retry policy, and cost/token budget controls.

- Redact secrets, credentials, tokens, API keys, private environment values, and sensitive headers before sending context to the model.

- Prevent agents from sending entire repositories when targeted snippets, logs, or artifacts are enough.

- Require structured JSON output for agent-to-system decisions such as plan proposal, failure diagnosis, patch proposal, risk classification, and report summary.

- Store redacted LLM interaction logs as audit artifacts without persisting hidden chain-of-thought. Store concise decision summaries instead.

- Support MCP Context Support Mode as optional documentation/context enrichment for the LLM, not as an execution dependency.

## Per-Agent LLM Usage Matrix

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

## LLM Call Contract

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

## LLM Security and Governance Rules

- Azure OpenAI credentials must be stored only in backend-managed configuration, Key Vault, environment variables, or an equivalent company-approved secret store.

- The frontend and agents must never receive the raw Azure OpenAI API key, endpoint secret, bearer token, or deployment credentials.

- Before every LLM call, the LLM Gateway must redact secrets, tokens, cookies, Authorization headers, API keys, .env values, private registry credentials, and production URLs when required by policy.

- Agents must send targeted context: relevant file snippets, compiler errors, diffs, and artifact references. They must not send the whole repository by default.

- The LLM must not be used as the sole correctness gate. Deterministic checks such as compatibility resolver, static symbol verification, ng build, test/lint if configured, and backend approval policy remain mandatory.

- LLM-generated patches must be applied by backend patch services only, never directly by the model.

- The system must store redacted LLM call metadata and concise rationale summaries, but it should not store hidden chain-of-thought or sensitive raw prompts unnecessarily.

- If Azure quota, timeout, rate limit, or API availability problems occur, the workflow should stop safely with a diagnostic artifact rather than applying unvalidated changes.

## LLM Artifacts

| **Artifact**                                          | **Purpose**                                                                                                                                             |
|-------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| 00_job_setup/llm_provider_config_redacted.json        | Records provider, deployment alias, region/endpoint alias, and policy flags without secrets.                                                            |
| 04_workflow_state/llm_interaction_log_redacted.json   | Audit log of LLM calls with timestamps, agent name, task type, model deployment, token usage if available, artifact references, and redacted summaries. |
| 03_planning/llm_plan_rationale_summary.md             | Human-readable summary of how LLM assistance contributed to the plan, based only on approved artifacts.                                                 |
| 06_validation/llm_failure_classification_summary.json | Optional LLM-assisted classification summary for validation failures.                                                                                   |
| 07_repair/llm_patch_proposals.json                    | Patch proposals created by LLM assistance before backend validation and static checks.                                                                  |
| 08_final/llm_usage_summary.md                         | Final report section documenting where LLM assistance was used and what was validated deterministically.                                                |

## Azure OpenAI Configuration Example - Redacted

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

## Efficiency Rules for GPT-5 mini Usage

- Use deterministic scanners first, then send only summarized findings or targeted excerpts to the model.

- Cache reusable LLM outputs such as dependency risk summaries, migration plan rationale, and repeated error classifications by artifact checksum.

- Prefer small task-specific prompts over large generic prompts.

- Use structured JSON outputs to reduce parsing ambiguity and retries.

- For repeated repair attempts, include only the delta from the previous attempt and the latest validation output.

- Do not ask the model to re-read unchanged files when their artifact checksum is unchanged.

- Use GPT-5 mini as the default model for cost and latency control; any larger-model escalation must be an explicit future option and company-approved.

## Additional Reference Notes for LLM Integration

- Azure OpenAI API usage, authentication, deployment names, API versions, and availability must follow the company Azure setup and official Microsoft documentation.

- GPT-5 mini is treated as the configured Azure OpenAI deployment for the MVP; the actual deployment name may differ by environment and should be resolved from backend configuration.

- MCP remains a context-support option for the LLM only; it is not an execution dependency and does not replace backend command authority.

- Azure OpenAI REST API reference: https://learn.microsoft.com/en-us/azure/foundry/openai/reference

- Azure OpenAI reasoning models documentation: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning

- OpenAI GPT-5 overview: https://openai.com/gpt-5/
