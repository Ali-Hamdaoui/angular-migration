# Angular Migration Control Tower
## Full Authoritative Product, Architecture, Workflow, Security, Governance, and Implementation Specification

**Project:** AI Frontend Migration Factory — Angular Compatibility Migration  
**Document status:** AUTHORITATIVE CONSOLIDATED SPECIFICATION — READY FOR BACKLOG AND IMPLEMENTATION REFINEMENT  
**Document version:** 2.1 — Full  Edition  
**Primary MVP route:** Angular 18.x → Angular 19.x → Angular 20.x → Angular 21.x  
**Long-term product scope:** Angular 11+ → company-approved target Angular family  
**Migration objective:** Technical compatibility upgrade with strict functional-parity controls  
**Backend scope:** Unchanged  
**Orchestration:** LangGraph as an orchestration adapter  
**Authoritative state:** SQLite through the Transition Service  
**Authoritative execution:** Backend CommandExecutor  
**Authoritative evidence:** Filesystem Artifact Store with checksum-bound metadata  
**Default LLM deployment:** GPT-5 mini through the Azure OpenAI LLM Gateway  
**Repair governance:** Proposer LLM → Reviewer LLM → Human Apply/Reject → backend validation and application  

---

> **Expanded-edition note:** Version 2.1 retains the corrected V2.0 architecture and expands it to implementation depth. It deliberately preserves the decisions already fixed for this project: Next.js/React frontend, FastAPI backend, LangGraph as orchestration adapter only, Transition Service as state-transition authority, SQLite as authoritative structured state, one CommandExecutor as execution authority, filesystem Artifact Store as evidence authority, Angular family acceptance, exact runtime resolution before execution, mandatory human approval gates, two-LLM repair governance, and one physical sandbox per migration stage.


# Document Authority and Precedence

This document consolidates the approved project vision, the optimized Angular migration workflow, and the strongest execution and repair mechanisms from the latest technical study.

It is intended to serve as the unified source of truth for:

- product scope;
- Angular version-family support;
- system architecture;
- LangGraph integration;
- workflow and state management;
- human approval gates;
- sandbox and workspace management;
- command execution;
- failure classification;
- two-LLM repair governance;
- validation and functional-parity assurance;
- persistence and artifacts;
- cancellation and recovery;
- API contracts;
- testing;
- backlog refinement;
- implementation sequencing;
- final delivery.

When an older document conflicts with this specification, the following rules apply:

1. Angular version families are accepted, not one exact source patch.
2. Execution still resolves exact versions before mutation.
3. LangGraph coordinates workflow transitions but never owns authoritative state or command execution.
4. The Transition Service validates and persists every legal state transition.
5. SQLite is the authoritative structured state store.
6. The CommandExecutor is the only authoritative external-process execution path.
7. The Artifact Store is the authoritative evidence store.
8. Every migration stage has a dedicated sandbox workspace.
9. Human approval is mandatory throughout the workflow.
10. Only the Proposer LLM authors repair diffs.
11. The Reviewer LLM reviews but never authors or replaces diffs.
12. The backend applies only the exact persisted and approved diff.
13. Repair validation always returns to the normal stage pipeline.
14. Technical success, functional parity, security assurance, and delivery readiness remain independent statuses.
15. The final migrated application is published only after final assurance and delivery gates pass.

---

# Table of Contents

1. Executive Summary  
2. Product Vision  
3. Scope and Non-Goals  
4. Angular Version-Family Policy  
5. Core Principles  
6. User Experience  
7. Target Technology Stack  
8. Unified Architecture  
9. Authority Boundaries  
10. LangGraph Orchestration Contract  
11. Transition Service and State Model  
12. Human Approval Model  
13. Source Intake and Preflight  
14. Source Snapshot and Sandbox Workspace Model  
15. Workspace Topology Classification  
16. Discovery and Baseline Qualification  
17. Compatibility Resolver and Historical Support Catalog  
18. ExecutionProfile  
19. StageExecutionPlan  
20. Structured Command Registry  
21. CommandExecutor  
22. End-to-End Workflow  
23. Stage Lifecycle  
24. Validation and Assurance  
25. Functional-Parity Evidence  
26. Build-System Migration Policy  
27. Changed-File Risk Classification  
28. FailureEvidence and Failure Routing  
29. Two-LLM Repair System  
30. RepairContextPack  
31. Patch Safety and Apply Protocol  
32. Repair Validation and Progress Detection  
33. Cancellation, Recovery, and Resume  
34. Persistence and Database Model  
35. Artifact Store and Directory Layout  
36. SSE and Frontend State Synchronization  
37. AI Assistant  
38. MCP Context Support  
39. LLM Gateway, Token Usage, and Cost  
40. Security and Sandbox Controls  
41. APIs  
42. Observability and Operations  
43. Testing Strategy  
44. MVP Definition of Done  
45. Implementation Sequence  
46. Repository and Git Governance  
47. Future Extensions  
48. Non-Negotiable Rules  
49. Glossary  
50. Reference Governance  
51. External Reference Findings and Policy Consequences  
52. Detailed Product Requirements and User Stories  
53. Detailed Authority and Component Contracts  
54. LangGraph Graph Design and Node Contracts  
55. Transition Service and Approval Transaction Protocol  
56. Detailed Human Approval Gate Catalogue  
57. Angular Family and Exact-Version Resolution Policy  
58. Historical Compatibility Catalogue Contract  
59. Detailed Source, Baseline, and Analysis Contracts  
60. Planning Package and Stage Plan Contract  
61. Stage Sandbox and Storage Lifecycle  
62. Detailed Command and Process Execution Contract  
63. Detailed Validation and Parity Matrix  
64. Two-LLM Repair Governance — Expanded Contract  
65. Persistence, Artifact, and Reconciliation Protocol  
66. Event, SSE, and Frontend Synchronization Contract  
67. API Payload and Error Contract  
68. Security Threat Model and Control Mapping  
69. Windows and Corporate Environment Operating Profile  
70. Operational Runbooks and Failure Procedures  
71. Comprehensive Test Catalogue  
72. Acceptance Criteria and Success Metrics  
73. Delivery Roadmap and Backlog Themes  
74. Architecture Decision Records  
75. Final Traceability and Non-Negotiable Contract  

---

# 1. Executive Summary

The Angular Migration Control Tower is an AI-assisted, evidence-driven migration platform that upgrades Angular applications from Angular 11 or later to a company-approved target Angular family.

The product does not perform generic modernization. Its default purpose is a controlled technical compatibility migration that preserves:

- UI appearance;
- UX behavior;
- business rules;
- routes;
- guards;
- resolvers;
- form-validation behavior;
- API contracts;
- request and response mappings;
- authentication and authorization behavior;
- backend integration;
- deployment-relevant configuration.

The first runtime-proven MVP route is:

```text
Angular 18.x
→ Angular 19.x
→ Angular 20.x
→ Angular 21.x
```

The architecture remains extensible to:

```text
Angular 11+
→ one major version at a time
→ company-approved Angular target family
```

The platform accepts version families. It must not reject Angular 18.0.x merely because the demonstration application used Angular 18.2.x. The source is normalized to an Angular family, while exact patch versions are resolved and locked before execution.

The platform is built around four explicit authorities:

```text
LangGraph
→ coordinates workflow transitions

Transition Service
→ validates legal state changes

SQLite
→ authoritative state

CommandExecutor
→ authoritative execution

Artifact Store
→ authoritative evidence
```

LangGraph is not the state database, command runner, security boundary, or artifact store. It invokes application services and coordinates the graph of work.

Every migration phase is reviewable and approval-gated. Human approval is required for:

- source and preflight acceptance;
- baseline acceptance;
- analysis acceptance;
- feasibility acceptance;
- migration plan acceptance;
- stage start;
- transformation diff acceptance;
- validation acceptance;
- repair Apply or Reject;
- stage completion;
- final assurance;
- delivery and publication.

The repair architecture uses two separate LLM roles:

```text
Real failure
→ deterministic FailureEvidence
→ bounded RepairContextPack
→ Proposer LLM authors one diff
→ Reviewer LLM reviews only
→ human Apply or Reject
→ backend validates and applies exact persisted diff
→ same normal pipeline validates the result
```

Each major-version stage is stored in a dedicated sandbox workspace. The original source remains read-only. Successful stages are cleaned, verified, fingerprinted, and then copied into the next stage sandbox.

The platform reports technical migration success separately from functional-parity status, security assurance, quality assurance, and delivery readiness. A successful build must never be presented as complete proof of functional parity.

---

# 2. Product Vision

The project creates an Angular migration factory that combines:

- official Angular migration tooling;
- deterministic compatibility resolution;
- reproducible execution environments;
- isolated stage workspaces;
- backend-controlled commands;
- full evidence capture;
- human approvals;
- bounded AI diagnosis and repair;
- exact patch governance;
- validation-gated progression;
- final atomic delivery.

The user should experience a simple product flow:

```text
Select source
→ Select output
→ Select target
→ Validate
→ Review baseline and analysis
→ Approve plan
→ Start migration
→ Monitor stages
→ Review every transformation and repair
→ Approve final assurance
→ Publish migrated application
```

Internally, the system enforces:

```text
Safe intake
→ immutable snapshot
→ exact source-compatible runtime
→ deterministic discovery
→ qualified baseline
→ human-approved analysis
→ human-approved feasibility
→ human-approved exact plan
→ isolated stage execution
→ human-reviewed diffs
→ bounded two-LLM repair
→ independent assurance
→ final clean validation
→ human-approved atomic delivery
→ complete evidence report
```

---

# 3. Scope and Non-Goals

## 3.1 Long-Term Product Scope

The product targets Angular applications with:

```text
source Angular major >= 11
```

The target must come from a company-approved target policy.

The system must:

- detect the exact installed source version;
- normalize the source to an Angular family;
- generate the major-by-major migration ladder;
- resolve exact compatible toolchains for each stage;
- classify the support level of every stage;
- stop if no safe path exists.

## 3.2 First MVP Scope

The first implementation proves:

- Angular CLI workspace;
- one primary frontend application;
- npm;
- valid `package-lock.json`;
- Angular 18.x source family;
- Angular 21.x target family;
- Node.js runtime profiles;
- backend unchanged;
- existing configured tests;
- existing configured lint;
- no default modernization;
- one active migration run at a time;
- local filesystem artifact store;
- SQLite state;
- SSE updates;
- Azure OpenAI through a backend gateway.

The MVP must accept source patch variations such as:

```text
18.0.x
18.1.x
18.2.x
```

provided that the Compatibility Resolver can construct a valid profile.

## 3.3 Explicit Non-Goals

The MVP does not perform:

- AngularJS migration;
- Angular 2–10 migration;
- backend migration;
- UI redesign;
- UX redesign;
- business-logic refactoring;
- API-contract redesign;
- authentication redesign;
- authorization redesign;
- state-management replacement;
- automatic standalone conversion;
- automatic signal conversion;
- automatic new control-flow conversion;
- automatic zoneless conversion;
- automatic test-framework replacement;
- silent builder modernization;
- unapproved dependency replacement;
- direct mutation of the original source;
- arbitrary shell execution by the LLM;
- autonomous repair application without human approval.

## 3.4 Excluded MVP Tools

Unless company policy changes, the MVP excludes:

```text
Playwright
Cypress
OSV scanner
Snyk
SonarQube
Semgrep
```

Related statuses must be:

```text
manual_validation_required
```

or:

```text
deferred_company_tool_required
```

They must never be displayed as passed when not executed.

---

# 4. Angular Version-Family Policy

## 4.1 Family Acceptance

The product accepts Angular families:

```text
11.x
12.x
13.x
...
18.x
19.x
20.x
21.x
```

A source version is detected exactly, for example:

```text
18.0.4
18.1.6
18.2.13
```

It is then normalized:

```json
{
  "angular_exact": "18.0.4",
  "angular_family": "18.x",
  "angular_major": 18
}
```

The architecture must not create separate hardcoded workflows for every patch.

## 4.2 Exact Execution Resolution

Family-level planning does not mean range-based execution.

Before stage execution, the system resolves exact approved versions:

```json
{
  "source_angular_exact": "18.0.4",
  "target_angular_exact": "19.approved.patch",
  "angular_cli_exact": "19.approved.patch",
  "typescript_exact": "approved-compatible-version",
  "rxjs_exact": "approved-compatible-version",
  "node_exact": "approved-compatible-version",
  "npm_exact": "approved-version"
}
```

The exact profile is checksum-bound and immutable after approval.

## 4.3 Upgrade Ladder

For a source Angular family `N.x` and target `M.x`, where `M > N`, the route is:

```text
N → N+1 → N+2 → ... → M
```

Examples:

```text
18.x → 19.x → 20.x → 21.x
```

```text
15.x → 16.x → 17.x → 18.x → 19.x → 20.x → 21.x
```

The LLM never invents the major-version ladder.

## 4.4 Support Levels

Each stage receives one of:

| Support level | Meaning |
|---|---|
| `officially_supported` | Current official Angular support and normal update policy cover the transition. |
| `historical_validated` | The stage uses a historical version but has passed the internal regression and fixture suite. |
| `historical_experimental` | Packages and tooling appear available, but internal evidence is incomplete. |
| `blocked` | No approved, reproducible, or sufficiently evidenced path exists. |

The support level is produced by deterministic policy, not by the LLM.

## 4.5 Historical Compatibility Catalog

The catalog stores:

- source family;
- target family;
- known-good CLI versions;
- compatible Node ranges;
- compatible TypeScript ranges;
- compatible RxJS ranges;
- compatible Zone.js ranges;
- package-manager restrictions;
- archived package availability;
- builder behavior;
- known migration issues;
- fixture-suite evidence;
- support level;
- last validation date;
- catalog version;
- checksum.

---

# 5. Core Principles

| Principle | Rule |
|---|---|
| Strict parity intent | Preserve approved behavior, UI, routes, APIs, business rules, and expected outputs. |
| Minimal diff | Apply only the smallest compatibility change required. |
| Compatibility before modernization | Modernization is a separate future workflow. |
| One major at a time | Every Angular major transition is an independent stage. |
| Source immutability | The selected source path is never mutated. |
| Sandbox-only mutation | All mutation occurs in product-owned stage sandboxes. |
| Human-controlled progression | Every major workflow phase and mutation requires human approval. |
| Backend execution authority | Agents propose; backend validates and executes. |
| Deterministic machine truth | Versions, commands, outputs, checksums, state, and gates are deterministic. |
| LangGraph as adapter | LangGraph coordinates; it does not own truth or execution. |
| Validation-gated movement | No stage progresses without evidence and approval. |
| Bounded repair | Repair has context, revision, attempt, time, and cost limits. |
| Exact patch governance | Only the persisted approved diff may be applied. |
| Evidence first | Conclusions derive from persisted evidence. |
| Recoverable execution | Recovery occurs only from proven boundaries. |
| Independent assurance | Technical, parity, security, quality, and delivery statuses are separate. |

---

# 6. User Experience

## 6.1 Main Interfaces

The product has two primary pages:

1. Migration Setup Page
2. Migration Control Tower Page

Supporting views include:

- baseline viewer;
- analysis viewer;
- plan viewer;
- log viewer;
- diff viewer;
- artifact viewer;
- failure evidence viewer;
- repair proposal viewer;
- report viewer;
- AI Assistant panel.

## 6.2 Setup Inputs

| Field | Rule |
|---|---|
| Source application path | Required; read-only from the platform perspective. |
| Target output path | Required; writable and safely separated from source. |
| Target Angular family | Required; company-approved. |
| Migration mode | Defaults to `strict_compatibility`. |
| Runtime overrides | Optional and validated. |
| Command selections | Limited to allowlisted discovered or configured commands. |
| Approval identity | Required for auditable decisions. |

## 6.3 Setup Layout

```text
----------------------------------------------------------------
Angular Migration Factory
----------------------------------------------------------------
Source application:       [__________________________] [Browse]
Target output directory:  [__________________________] [Browse]
Target Angular family:    [Angular 21.x             v]
Migration mode:           [Strict Compatibility      ]
Approval mode:            [Human approval required   ]

[Validate Configuration]
----------------------------------------------------------------
Preflight: Not validated
----------------------------------------------------------------
```

## 6.4 Control Tower Layout

```text
----------------------------------------------------------------
Run: run-001                           Status: Waiting Approval
Phase: Planning                        Target: Angular 21.x
Support: Historical Validated          Approval: Required
----------------------------------------------------------------
Assurance
Technical upgrade: Planning
Functional parity: Not yet assessed
Security assurance: Deferred company tool required
Quality assurance: Deferred company tool required
Delivery readiness: Not ready
----------------------------------------------------------------
Stages
[Pending] 18 → 19
[Pending] 19 → 20
[Pending] 20 → 21
----------------------------------------------------------------
Current workflow
[Passed] Source preflight
[Approved] Source acceptance
[Passed] Baseline
[Approved] Baseline acceptance
[Passed] Analysis
[Waiting Approval] Analysis approval
[Pending] Planning
----------------------------------------------------------------
[Evidence] [Logs] [Diffs] [Artifacts] [AI Assistant] [Cancel]
----------------------------------------------------------------
```

The UI renders backend state only.

---

# 7. Target Technology Stack

## 7.1 Backend

- Python 3.12+
- FastAPI
- Uvicorn
- Pydantic v2
- SQLAlchemy
- Alembic
- SQLite with WAL for MVP
- LangGraph
- Azure OpenAI LLM Gateway
- local filesystem Artifact Store
- Python sandbox execution worker
- Server-Sent Events

## 7.2 Migration Worker Runtime

- Python
- Node.js
- npm
- Angular CLI through `npx`
- Git where available
- exact execution profiles
- corporate proxy and certificate profiles
- process-tree supervision

## 7.3 Frontend

- Node.js
- Next.js
- React
- TypeScript
- CSS Modules
- SSE client
- custom log viewer
- custom unified diff viewer
- Markdown report viewer

## 7.4 Database Boundary

SQLite is permitted for:

- one backend host;
- one active mutating job;
- limited concurrent readers;
- short transactions;
- local MVP operation.

PostgreSQL is required before:

- multiple backend instances;
- distributed workers;
- significant concurrency;
- enterprise multi-user deployment.

---

# 8. Unified Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                    NEXT.JS CONTROL TOWER                     │
│ Setup │ Baseline │ Analysis │ Plan │ Stages │ Repair │ Report│
└───────────────────────────────┬──────────────────────────────┘
                                │ HTTP + SSE
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                      FASTAPI CONTROL PLANE                   │
│ APIs │ Auth/Actor │ Approval │ State Query │ Artifact Access │
└───────────────────────────────┬──────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                  LANGGRAPH ORCHESTRATION ADAPTER             │
│ Coordinates nodes and transition requests                   │
│ Does not own state, execution, or evidence                   │
└───────────────────────────────┬──────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                     TRANSITION SERVICE                       │
│ Validates legal transitions, versions, approvals, checksums  │
└──────────────┬─────────────────────┬─────────────────────────┘
               │                     │
               ▼                     ▼
┌────────────────────────┐  ┌──────────────────────────────────┐
│ SQLite State Store     │  │ JobSupervisor                    │
│ authoritative state    │  │ active worker, cancellation,     │
│ events and approvals   │  │ recovery, execution ownership    │
└────────────────────────┘  └────────────────┬─────────────────┘
                                             ▼
                              ┌───────────────────────────────┐
                              │ Stage Services                │
                              │ WorkspaceManager              │
                              │ CompatibilityResolver         │
                              │ ExecutionProfile Registry     │
                              │ StageExecutionPlan Service    │
                              │ Validation Services           │
                              │ Repair Orchestrator           │
                              └───────────────┬───────────────┘
                                              ▼
                              ┌───────────────────────────────┐
                              │ Command Policy Engine         │
                              │ Structured Command Registry   │
                              └───────────────┬───────────────┘
                                              ▼
                              ┌───────────────────────────────┐
                              │ CommandExecutor               │
                              │ authoritative execution       │
                              └───────────────┬───────────────┘
                                              ▼
                              ┌───────────────────────────────┐
                              │ Stage Sandbox Workspace       │
                              │ npm │ npx ng │ build │ tests  │
                              └───────────────┬───────────────┘
                                              ▼
                              ┌───────────────────────────────┐
                              │ Artifact Store                │
                              │ authoritative evidence        │
                              └───────────────────────────────┘
```

---

# 9. Authority Boundaries

## 9.1 LangGraph

LangGraph may:

- coordinate graph nodes;
- request deterministic services;
- branch based on service outcomes;
- pause for approvals;
- resume after persisted approval;
- invoke repair orchestration;
- invoke report generation.

LangGraph must not:

- directly update authoritative state without the Transition Service;
- directly execute shell commands;
- directly mutate files;
- become the artifact store;
- infer approval from frontend state;
- bypass state versions;
- continue after stale approval;
- recreate evidence already owned by services.

## 9.2 Transition Service

The Transition Service owns:

- allowed transition rules;
- state-version checks;
- approval requirements;
- checksum binding;
- idempotency;
- phase/stage/step consistency;
- actor and reason validation;
- transition persistence;
- event emission.

## 9.3 SQLite

SQLite owns:

- current run state;
- current stage state;
- current step state;
- approval status;
- plan revisions;
- command metadata;
- repair lineage;
- event sequence;
- artifact metadata;
- worker leases;
- cancellation state;
- assurance summaries.

## 9.4 CommandExecutor

The CommandExecutor owns:

- exact executable;
- exact argument list;
- exact working directory;
- exact environment profile;
- process creation;
- timeout;
- process-tree cancellation;
- stdout/stderr capture;
- exit status;
- execution timestamps;
- command completion evidence.

## 9.5 Artifact Store

The Artifact Store owns:

- source manifests;
- stage plans;
- command logs;
- diagnostics;
- diffs;
- failure evidence;
- repair context;
- LLM responses;
- patch proposals;
- validation reports;
- final reports;
- export manifests.


---

# 10. LangGraph Orchestration Contract

## 10.1 Role

LangGraph is an orchestration adapter over authoritative services.

A node should:

1. read the authoritative state snapshot;
2. validate prerequisites through application services;
3. call a deterministic or AI-assisted service;
4. receive a structured result;
5. request a legal transition from the Transition Service;
6. stop when human approval is required.

## 10.2 Example Graph

```text
CREATE_RUN
→ PREFLIGHT
→ WAIT_SOURCE_APPROVAL
→ SNAPSHOT
→ WAIT_SNAPSHOT_APPROVAL
→ BASELINE
→ WAIT_BASELINE_APPROVAL
→ DISCOVERY
→ ANALYSIS
→ WAIT_ANALYSIS_APPROVAL
→ FEASIBILITY
→ WAIT_FEASIBILITY_APPROVAL
→ PLANNING
→ WAIT_PLAN_APPROVAL
→ FOR_EACH_STAGE
    → WAIT_STAGE_START_APPROVAL
    → PREPARE_STAGE
    → TRANSFORM
    → WAIT_TRANSFORM_APPROVAL
    → VALIDATE
    → WAIT_VALIDATION_APPROVAL
    → IF_FAILURE
        → BUILD_FAILURE_EVIDENCE
        → PROPOSER
        → REVIEWER
        → WAIT_REPAIR_APPLY
        → APPLY
        → VALIDATE_NORMAL_PIPELINE
        → WAIT_REPAIR_VALIDATION_APPROVAL
    → WAIT_STAGE_COMPLETION_APPROVAL
    → COMPLETE_STAGE
→ FINAL_ASSURANCE
→ WAIT_FINAL_ASSURANCE_APPROVAL
→ DELIVERY_CANDIDATE
→ WAIT_DELIVERY_APPROVAL
→ ATOMIC_PUBLISH
→ REPORT
→ WAIT_REPORT_ACCEPTANCE
```

## 10.3 Checkpointing

LangGraph checkpoints may support orchestration recovery, but they are not the authoritative business state.

On resume, LangGraph must reconcile with:

- SQLite state version;
- worker lease;
- command status;
- workspace fingerprint;
- approval state;
- artifact availability.

## 10.4 Node Contract

Every LangGraph node must declare:

- node purpose;
- required authoritative input state;
- called service;
- expected structured output;
- allowed transition requests;
- approval requirements;
- idempotency behavior;
- retry behavior;
- generated artifacts;
- failure routing.

## 10.5 Forbidden LangGraph Patterns

The implementation must not:

- store critical state only inside graph memory;
- infer completion because a node returned successfully;
- execute commands from node code without the CommandExecutor;
- write workspace files directly from orchestration code;
- treat LangGraph checkpoints as evidence that a command executed;
- continue after an approval gate unless the approval exists in SQLite;
- create competing transition logic inside individual nodes.

---

# 11. Transition Service and State Model

## 11.1 Multidimensional State

Avoid one large overlapping state enum.

### Run Status

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

### Run Phase

```text
preflight
snapshot
baseline
discovery
analysis
feasibility
planning
stage_execution
final_assurance
delivery
reporting
```

### Stage Status

```text
pending
preparing
running
waiting_approval
repairing
passed
passed_with_known_baseline_failures
passed_with_manual_items
rolled_back
failed
cancelled
diagnostic_hold
```

### Step Status

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
interrupted
cancelled
```

### Approval Status

```text
not_required
required
pending
approved
approved_with_comment
rejected
modification_requested
expired
stale
```

### Repair Status

```text
not_active
evidence_building
proposer_running
reviewer_running
revision_required
waiting_human_apply
applying
preflight
validating
succeeded
failed
attempt_limit_reached
```

## 11.2 Transition Record

```json
{
  "event_id": "uuid",
  "event_sequence": 127,
  "run_id": "run-001",
  "stage_id": "angular-18-to-19",
  "previous_state_version": 34,
  "new_state_version": 35,
  "run_status": "waiting_approval",
  "phase": "analysis",
  "stage_status": null,
  "step": "analysis_complete",
  "approval_status": "required",
  "actor": "analysis_service",
  "reason": "Analysis artifacts are complete.",
  "artifact_refs": ["artifact://..."],
  "idempotency_key": "sha256:..."
}
```

## 11.3 Transition Rules

A transition is rejected when:

- state version is stale;
- required approval is missing;
- artifact checksum is missing;
- prerequisite step failed;
- worker lease conflicts;
- stage plan changed after approval;
- current workspace fingerprint differs;
- command is still running;
- cancellation is pending;
- transition is not listed in the state policy.

## 11.4 Transition Atomicity

A step is not marked passed until:

1. required artifacts are finalized;
2. artifact checksums are stored;
3. the state write succeeds;
4. the durable event is appended.

The frontend must never see `passed` before evidence exists.

---

# 12. Human Approval Model

Human approval is mandatory across the workflow.

## 12.1 Approval Gates

| Gate | Required evidence |
|---|---|
| Source acceptance | Preflight and eligibility artifacts |
| Snapshot acceptance | Source manifest and fingerprint |
| Baseline acceptance | Install/build/test/lint baseline evidence |
| Analysis acceptance | Discovery and risk artifacts |
| Feasibility acceptance | Support-level and path decision |
| Plan acceptance | Exact route, profiles, commands, gates, policies |
| Stage start | Current stage plan and input fingerprint |
| Transformation acceptance | Complete stage diff and changed-file risk |
| Validation acceptance | All technical and evidence gates |
| Repair Apply/Reject | Exact Proposer diff and Reviewer decision |
| Repair validation acceptance | Normal-pipeline validation evidence |
| Stage completion | Stage output fingerprint and evidence bundle |
| Final assurance acceptance | Final clean validation and parity status |
| Delivery approval | Delivery candidate manifest and destination |
| Final report acceptance | Report integrity and unresolved items |

## 12.2 Approval Binding

Every approval stores:

- approval ID;
- gate ID;
- run ID;
- stage ID;
- actor;
- decision;
- comment;
- artifact-set checksum;
- state version;
- workspace fingerprint where applicable;
- creation time;
- expiry;
- decision source.

## 12.3 Decisions

```text
approved
approved_with_comment
modification_requested
rejected
```

Core mandatory technical failures cannot be converted to pass through approval.

## 12.4 Approval API

```http
POST /migrations/{runId}/approvals
```

```json
{
  "gate_id": "analysis-approval",
  "artifact_set_checksum": "sha256:...",
  "state_version": 35,
  "decision": "approved",
  "comment": "Analysis accepted."
}
```

## 12.5 Repair Approval

Repair approval is always explicit:

```text
Proposer candidate
→ Reviewer accept
→ exact diff persisted
→ human Apply or Reject
```

The frontend submits identifiers, never an authoritative raw diff.

## 12.6 Approval Expiry and Staleness

An approval becomes stale when:

- source fingerprint changes;
- plan version changes;
- stage input changes;
- artifact-set checksum changes;
- relevant policy changes;
- the gate is superseded by a new failure or repair attempt.

---

# 13. Source Intake and Preflight

## 13.1 Path Safety

Validate:

- source exists;
- source is readable;
- output exists or can be created;
- output is writable;
- source and output are different;
- output is not nested inside source;
- source is not nested inside internal workspaces;
- canonical paths remain within approved roots;
- symlinks and Windows junctions cannot escape;
- protected operating-system paths are blocked;
- sufficient disk exists;
- path length risks are recorded;
- active runs do not claim the same delivery directory.

## 13.2 Project Eligibility

Verify:

- `package.json` exists;
- Angular packages are detected;
- AngularJS indicators are not dominant;
- source Angular major is 11 or later;
- exact `@angular/core` can be resolved;
- Angular CLI version can be resolved or inconsistency recorded;
- package manager is identified;
- lockfile is identified;
- workspace topology is classified;
- target family is approved.

## 13.3 Environment Checks

Verify:

- Git availability when required;
- npm availability;
- source runtime profile availability;
- stage runtime profile candidates;
- registry access;
- private registry authentication availability;
- proxy and certificate configuration;
- SQLite writability;
- Artifact Store writability;
- worker execution permissions;
- Azure OpenAI policy configuration.

## 13.4 Preflight Result

```json
{
  "input_checksum": "sha256:...",
  "status": "passed_with_warnings",
  "source_path_safe": true,
  "target_path_safe": true,
  "angular_detected": true,
  "source_angular_exact": "18.0.4",
  "source_family": "18.x",
  "workspace_topology": "single_application_cli_workspace",
  "package_manager": "npm",
  "lockfile": "package-lock.json",
  "runtime_profiles_available": true,
  "registry_access": "available",
  "blocking_reasons": [],
  "warnings": []
}
```

## 13.5 Preflight Status

```text
passed
passed_with_warnings
blocked
expired
```

A preflight expires when source, target, policy, toolchain, or environment capability changes.

---

# 14. Source Snapshot and Sandbox Workspace Model

## 14.1 Source Immutability

The original source is never mutated.

Before and after the run:

- calculate source manifest;
- calculate source hash;
- compare final source hash;
- report mutation status.

Any mutation is a critical failure.

## 14.2 Physical Stage Sandbox

Each stage receives its own product-owned sandbox:

```text
source-snapshot/
→ angular-18-to-19/workspace/
→ angular-19-to-20/workspace/
→ angular-20-to-21/workspace/
```

The next stage starts only from the cleaned, validated, fingerprinted result of the previous stage.

## 14.3 Sandbox Rules

- never include previous `node_modules`;
- never reuse generated build directories as validation evidence;
- copy only allowed workspace content;
- preserve source, tests, assets, configuration, and lockfile;
- remove transient product-owned files;
- verify cleanliness;
- compute input and output fingerprints.

## 14.4 Copy Optimization

Implementation may use:

- normal copies;
- filesystem reflinks;
- copy-on-write where supported.

The domain model remains a physical stage sandbox regardless of copy optimization.

## 14.5 Optional Product-Owned Git

Git is not required for source eligibility.

The platform may initialize product-owned Git history in sandbox workspaces to support:

- diffs;
- rollback;
- stage commits;
- patch checks;
- final history.

Original source Git history, when present, is captured but not mutated.

## 14.6 Fingerprint Contract

The canonical fingerprint policy must be versioned and record:

- included relative paths;
- excluded generated directories;
- file-content hashes;
- symlink handling;
- path normalization;
- case sensitivity;
- canonicalization version.

---

# 15. Workspace Topology Classification

Classify:

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

MVP policy:

| Topology | MVP decision |
|---|---|
| Single Angular CLI app | Supported |
| App with controlled local libraries | Conditional |
| Multi-app workspace | Detect; human review |
| Publishable library | Detect; human review |
| Nx | Blocked or experimental |
| Microfrontend | Blocked |
| Custom builder | Human review |
| SSR/hybrid | Human review |
| Unknown | Blocked |

The product must never silently accept an unsupported topology.

---

# 16. Discovery and Baseline Qualification

## 16.1 Parallel Discovery

After snapshot creation, independent read-only discovery tasks may run concurrently:

- workspace scan;
- version scan;
- dependency scan;
- lockfile scan;
- lifecycle-script scan;
- route scan;
- backend-integration scan;
- environment/proxy scan;
- test/lint scan;
- builder/deployment scan;
- UI/theme scan;
- state-management scan;
- secret-indicator scan;
- parity-manifest scan.

## 16.2 Deterministic Discovery Services

- Workspace Topology Classifier;
- Version Detector;
- Dependency Inventory Builder;
- Lockfile Inspector;
- Package Lifecycle-Script Auditor;
- Route Inventory Builder;
- Backend Contract Snapshot Builder;
- Build-System Detector;
- Test/Lint Inventory Builder;
- Sensitive-File Policy Loader;
- Browser Policy Resolver;
- Secret Indicator Scanner.

## 16.3 Baseline Sequence

```text
Resolve source runtime
→ validate package metadata and lockfile
→ audit lifecycle scripts
→ clean install
→ dependency-tree verification
→ required builds
→ configured tests
→ configured lint
→ route inventory
→ backend contract snapshot
→ bundle/output evidence
→ known-failure fingerprints
→ baseline report
→ human approval
```

## 16.4 Baseline Status

```text
qualified
qualified_with_known_failures
reproducibility_degraded
blocked_by_environment
blocked_by_project
```

## 16.5 Known Baseline Failures

Known failures receive stable fingerprints.

If project policy permits migration with known baseline failures, stage acceptance requires:

- no new failure fingerprints;
- no changed known failure fingerprints without approval;
- no increased failure count;
- no degradation in mandatory gates.

The status becomes:

```text
passed_with_known_baseline_failures
```

It must not be reported as a clean pass.

## 16.6 User Attestation

User attestation may supplement evidence only when automated baseline execution is blocked.

It must be stored as:

```text
user_attested
```

never:

```text
machine_proven
```

---

# 17. Compatibility Resolver and Historical Support Catalog

## 17.1 Responsibilities

The Compatibility Resolver:

- normalizes exact versions into families;
- generates the major ladder;
- resolves support level;
- resolves compatible runtime candidates;
- resolves exact target patches;
- resolves CLI, TypeScript, RxJS, Zone.js, Node, and npm;
- detects private-package blockers;
- determines builder strategy;
- produces feasibility.

## 17.2 Feasibility Decision

```text
feasible
feasible_with_warnings
requires_manual_preparation
blocked
```

## 17.3 Compatibility Resolution Output

```json
{
  "source_exact": "18.0.4",
  "source_family": "18.x",
  "target_family": "21.x",
  "support_level": "historical_validated",
  "upgrade_ladder": [
    "angular-18-to-19",
    "angular-19-to-20",
    "angular-20-to-21"
  ],
  "warnings": [],
  "blocking_reasons": [],
  "catalog_version": "catalog-v1",
  "checksum": "sha256:..."
}
```

## 17.4 Human Approval

Feasibility requires human approval before planning.

Blocked decisions cannot be approved into execution without a new compatibility policy or environment change.

---

# 18. ExecutionProfile

## 18.1 Purpose

`ExecutionProfile` represents an exact reusable runtime.

## 18.2 Fields

```json
{
  "profile_id": "node-22.12-npm-approved",
  "operating_system": "windows",
  "architecture": "amd64",
  "node_executable": "C:\\Tools\\node\\node.exe",
  "node_exact": "22.12.0",
  "package_manager": "npm",
  "package_manager_executable": "C:\\Tools\\node\\npm.cmd",
  "package_manager_exact": "approved-version",
  "angular_cli_execution": "npx",
  "proxy_profile": "corporate-default",
  "certificate_profile": "company-ca",
  "network_policy": "approved-registries-only",
  "environment_variables": ["PATH", "HTTP_PROXY", "HTTPS_PROXY"],
  "compatibility_catalog_version": "catalog-v1",
  "validated_at": "ISO-8601",
  "checksum": "sha256:..."
}
```

## 18.3 Reuse

One profile may serve multiple stages if compatibility permits.

The exact same profile is reused for:

- normal execution;
- repair revalidation;
- recovery reruns.

## 18.4 Profile Changes

Changing an executable, version, proxy profile, certificate profile, or network policy creates a new ExecutionProfile version and invalidates unexecuted plan approvals.

---

# 19. StageExecutionPlan

## 19.1 Purpose

The plan is the immutable executable contract for one stage.

## 19.2 Fields

```json
{
  "plan_id": "plan-stage-18-19-v1",
  "stage_id": "angular-18-to-19",
  "version": 1,
  "input_fingerprint": "sha256:...",
  "source_angular_exact": "18.0.4",
  "source_family": "18.x",
  "target_angular_exact": "approved-19-patch",
  "target_family": "19.x",
  "execution_profile_id": "node-22.12-npm-approved",
  "commands": {
    "bootstrap_install": "command-registry-reference",
    "angular_update": "command-registry-reference",
    "target_version_check": "command-registry-reference",
    "final_install": "command-registry-reference",
    "builds": ["command-registry-reference"],
    "tests": ["command-registry-reference"],
    "lint": ["command-registry-reference"]
  },
  "build_system_decision_id": "decision-id",
  "validation_policy_version": "validation-v1",
  "repair_policy_version": "repair-v1",
  "created_at": "ISO-8601",
  "checksum": "sha256:..."
}
```

## 19.3 Revisions

A changed command, toolchain, target patch, builder decision, or validation policy creates a new plan revision and requires new human approval.

## 19.4 Planned Versus Actual

The StageExecutionPlan records what is authorized.

`CommandExecution` records prove what actually ran.

A plan is never execution evidence.

---

# 20. Structured Command Registry

## 20.1 No Arbitrary Shell Strings

Commands are templates:

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
  "working_directory_alias": "stage_workspace",
  "timeout_seconds": 1800,
  "network_profile": "approved_registries_only"
}
```

## 20.2 User Selections

Users may select:

- discovered package scripts;
- approved command templates;
- approved executable paths.

Users may not submit unrestricted shell text.

## 20.3 Command Validation

Validate:

- registry membership;
- executable allowlist;
- argument template;
- no shell operators;
- stage and plan match;
- workspace confinement;
- environment allowlist;
- network profile;
- timeout policy;
- required approval;
- idempotency key.

## 20.4 Forbidden by Default

```text
--force
--legacy-peer-deps
arbitrary package installation
unapproved dependency replacement
unapproved builder migration
standalone migration
signals migration
control-flow migration
zoneless migration
shell=true
commands outside sandbox
```

---

# 21. CommandExecutor

## 21.1 Responsibilities

- validate command authorization;
- materialize exact execution profile;
- validate working directory;
- create process;
- stream bounded logs;
- persist full logs;
- track process tree;
- enforce timeout;
- support cancellation;
- store result.

## 21.2 Execution Record

```json
{
  "execution_id": "uuid",
  "idempotency_key": "sha256:...",
  "run_id": "run-001",
  "stage_id": "angular-18-to-19",
  "plan_id": "plan-stage-18-19-v1",
  "command_id": "angular_update_stage",
  "expanded_executable": "npx",
  "expanded_arguments": [],
  "cwd_alias": "stage_workspace",
  "execution_profile_id": "node-22.12-npm-approved",
  "runtime_checksum": "sha256:...",
  "status": "failed",
  "exit_code": 1,
  "stdout_artifact_id": "artifact-id",
  "stderr_artifact_id": "artifact-id",
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601"
}
```

## 21.3 Interactive Command Handling

Commands must run non-interactively where supported.

If an unexpected prompt appears:

```text
capture prompt
→ stop or pause safely
→ create INTERACTIVE_DECISION_REQUIRED evidence
→ wait for human decision
→ revise plan if required
→ rerun from safe boundary
```

No invisible stdin default may be accepted for strategic decisions.

---

# 22. End-to-End Workflow

```text
1. Create preflight request
2. Validate paths and eligibility
3. Human source approval
4. Create immutable snapshot
5. Human snapshot approval
6. Resolve source runtime
7. Run discovery
8. Run baseline qualification
9. Human baseline approval
10. Generate analysis package
11. Human analysis approval
12. Generate feasibility decision
13. Human feasibility approval
14. Generate exact migration plan
15. Human plan approval
16. For each major stage:
    a. Human stage-start approval
    b. Create stage sandbox
    c. Resolve exact profile and plan
    d. Execute transformation
    e. Human transformation-diff approval
    f. Execute validation
    g. Human validation approval
    h. If failure, execute two-LLM repair workflow
    i. Human repair Apply/Reject
    j. Validate through normal pipeline
    k. Human repair-validation approval
    l. Clean and fingerprint stage
    m. Human stage-completion approval
17. Run final clean assurance
18. Human final-assurance approval
19. Build delivery candidate
20. Human delivery approval
21. Publish atomically
22. Generate final report
23. Human report acceptance
```

---

# 23. Stage Lifecycle

For each stage:

```text
1. Acquire worker lease
2. Verify stage input fingerprint
3. Human stage-start approval
4. Create physical sandbox
5. Activate ExecutionProfile
6. Persist StageExecutionPlan
7. Audit dependencies and lifecycle scripts
8. Run bootstrap clean install
9. Run exact approved ng update
10. Verify target Angular major and exact profile
11. Capture transformation diff
12. Classify changed files
13. Human transformation approval
14. Validate lockfile
15. Run final clean install
16. Run static symbol/template checks
17. Run required builds
18. Run complete configured tests
19. Run configured lint
20. Compare routes and backend integration
21. Build parity evidence
22. Human validation approval
23. Repair if required
24. Clean sandbox
25. Verify cleanliness
26. Compute output fingerprint
27. Human stage-completion approval
28. Copy clean output to next stage
29. Release lease
```


---

# 24. Validation and Assurance

## 24.1 Mandatory Technical Gates

| Gate | Purpose |
|---|---|
| Target version | Prove expected Angular major and exact approved profile |
| Lockfile integrity | Prove metadata and lockfile consistency |
| Clean final install | Prove reproducible dependency installation |
| Static symbol/template check | Detect phantom APIs and invalid references |
| Build | Prove compilation for all required projects/configurations |
| Tests | Prove complete configured required tests |
| Route comparison | Detect structural route changes |
| Backend integration comparison | Detect API/auth/config changes |
| Changed-file risk | Determine human review requirements |
| Stage fingerprint | Bind validated output |

## 24.2 Conditional Gates

- lint;
- library packaging;
- SSR;
- prerender;
- service worker;
- i18n;
- custom approved targets.

## 24.3 Independent Assurance Fields

```json
{
  "technical_upgrade_status": "passed",
  "functional_parity_status": "manual_validation_pending",
  "security_assurance_status": "deferred_company_tool_required",
  "quality_assurance_status": "deferred_company_tool_required",
  "delivery_readiness": "conditionally_ready"
}
```

## 24.4 Proof Labels

Evidence statements use:

```text
PROVEN
INFERRED
NOT_PROVEN
```

These labels supplement assurance fields; they do not replace them.

## 24.5 Validation Status Vocabulary

```text
passed
failed
not_configured
manual_validation_required
deferred_company_tool_required
blocked_by_environment
accepted_risk
skipped_not_applicable
interrupted
cancelled
unknown
```

## 24.6 Core Gate Rule

Human approval may accept evidence and continuation decisions, but it may not rewrite failed core technical evidence into `passed`.

---

# 25. Functional-Parity Evidence

Capture baseline and stage evidence for:

- routes;
- redirects;
- lazy loading;
- guards;
- resolvers;
- API base URLs;
- HTTP methods and endpoint references;
- interceptors;
- auth headers;
- token and cookie references;
- request builders;
- response mappers;
- error handling;
- form validators;
- translations;
- global styles;
- themes;
- assets;
- polyfills;
- service worker;
- SSR/prerender;
- output paths;
- bundle budgets;
- browser policy.

Final manual parity review covers:

- application boot;
- navigation;
- lazy routes;
- login/logout;
- guarded routes;
- forms;
- validation;
- API calls;
- error handling;
- critical pages;
- layout and theme;
- browser console;
- assets and translations.

Possible parity statuses:

```text
verified
verified_with_accepted_differences
manual_validation_pending
failed
not_executed
```

A generated checklist alone results in `manual_validation_pending`.

---

# 26. Build-System Migration Policy

Framework migration and build-system migration are separate concerns.

Classifications:

```text
not_applicable
preserve_existing
required_for_target_compatibility
optional_modernization
custom_builder_requires_review
behavior_sensitive_requires_review
```

Rules:

- preserve builder by default;
- detect Angular CLI builder proposals;
- block optional modernization;
- require human approval for required or behavior-sensitive change;
- capture affected output paths, styles, assets, SSR, deployment, and custom config;
- validate accepted builder changes through the normal pipeline.

Conceptual decision:

```json
{
  "stage_id": "angular-18-to-19",
  "current_builder": "@angular-devkit/build-angular:browser",
  "proposed_builder": null,
  "classification": "preserve_existing",
  "required_for_target_compatibility": false,
  "optional_modernization": false,
  "requires_human_action": false,
  "decision": "preserve_existing"
}
```

---

# 27. Changed-File Risk Classification

| Risk | Examples | Action |
|---|---|---|
| Low | package metadata, lockfile, TypeScript config, mechanical import | Human review still required; normal evidence may suffice |
| Medium | routes, shared modules, RxJS pipelines, Material modules | Human review with targeted evidence |
| High | auth, interceptors, guards, APIs, environments, validators, business logic, styles | Strategic approval required |
| Blocked | unknown behavior, private-package ambiguity, insufficient evidence | Diagnostic hold |

Risk classification never auto-applies a repair in MVP.

Content-aware classification must consider:

- file path;
- file type;
- AST or structural change;
- changed symbols;
- baseline role;
- approved migration unit;
- potential observable impact.

---

# 28. FailureEvidence and Failure Routing

## 28.1 FailureEvidence

Every real failed command produces:

- command execution ID;
- phase;
- exit code;
- raw stdout/stderr;
- normalized diagnostics;
- error codes;
- files and locations;
- tool versions;
- stage plan;
- execution profile;
- workspace fingerprint;
- changed-file list;
- baseline comparison;
- failure fingerprint.

## 28.2 C-Lite Routes

```text
CODE_OR_CONFIG_REPAIR
DEPENDENCY_REPAIR
ENVIRONMENT_OR_USER_ACTION
RETRYABLE_EXTERNAL_FAILURE
UNKNOWN_DIAGNOSIS
```

Detailed metadata remains attached:

```json
{
  "route": "CODE_OR_CONFIG_REPAIR",
  "tool": "angular_compiler",
  "code": "NG8002",
  "risk": "low",
  "baseline_origin": "migration_caused"
}
```

## 28.3 Failure Origin

```text
pre_existing_unchanged
pre_existing_changed
migration_caused
resolved_pre_existing
unknown_origin
```

## 28.4 Parser Registry

MVP parsers:

- npm/package-manager parser;
- Angular CLI parser;
- TypeScript/compiler parser;
- Angular template parser;
- test parser;
- generic process parser.

## 28.5 Environment Failures

Environment failures such as missing executable, permission, authentication, proxy, certificate, or disk issues must not be sent directly to code repair.

---

# 29. Two-LLM Repair System

## 29.1 Roles

### Proposer

The Proposer:

- diagnoses;
- explains root cause;
- proposes the smallest safe repair;
- authors exactly one candidate diff;
- identifies changed files;
- reports risk;
- may request one context expansion.

### Reviewer

The Reviewer:

- evaluates evidence alignment;
- reviews scope;
- checks minimality;
- checks behavioral risk;
- accepts;
- requests revision;
- rejects;
- requests context.

The Reviewer never returns a diff.

## 29.2 Flow

```text
FailureEvidence
→ C-Lite route
→ RepairContextPack v1
→ Proposer candidate
→ Reviewer
    → accept
    → request_revision
    → reject
    → insufficient_context
→ exact accepted Proposer diff persisted
→ human Apply or Reject
→ backend patch safety
→ exact diff applied
→ same normal validation pipeline
```

## 29.3 Limits

| Counter | Limit |
|---|---:|
| LLM transport retries | 2 |
| Invalid output regeneration | 1 |
| Context expansions | 1 per repair attempt |
| Reviewer revision cycles | 2 per repair attempt |
| Applied semantic repair attempts | 3 per stage failure chain |

## 29.4 Proposer Output

```json
{
  "schema_version": "repair_proposer_v1",
  "status": "candidate",
  "summary": "Short diagnosis",
  "root_cause": "Evidence-backed root cause",
  "fix_strategy": "Minimal compatibility repair",
  "evidence_refs": ["diagnostic-001"],
  "proposed_diff": "--- a/file\n+++ b/file\n...",
  "changed_files": ["src/app/example.ts"],
  "risk_notes": [],
  "requested_context": []
}
```

Allowed statuses:

```text
candidate
insufficient_context
not_repairable
```

## 29.5 Reviewer Output

```json
{
  "schema_version": "repair_reviewer_v1",
  "decision": "accept",
  "summary": "The candidate is evidence-aligned and minimal.",
  "evidence_refs": ["diagnostic-001"],
  "critique": [],
  "revision_instructions": [],
  "requested_context": []
}
```

Allowed decisions:

```text
accept
request_revision
reject
insufficient_context
```

The schema must contain no patch or diff field.

---

# 30. RepairContextPack

The pack contains:

- context pack ID;
- schema version;
- failure ID;
- stage ID;
- repair attempt;
- workspace fingerprint;
- failed command;
- diagnostics;
- selected file excerpts;
- full file checksums;
- excerpt checksums;
- selection reasons;
- stage diff summary;
- dependencies;
- previous attempts;
- forbidden changes;
- sanitization record;
- token budget.

Selection priority:

1. diagnostic file;
2. failing test;
3. stack-trace file;
4. component/template pair;
5. changed file;
6. direct import relation;
7. package/config evidence;
8. previous attempt evidence.

Selection reasons include:

```text
DIRECT_DIAGNOSTIC_LOCATION
FAILING_TEST_FILE
STACK_TRACE_LOCATION
COMPONENT_TEMPLATE_PAIR
CHANGED_IN_CURRENT_STAGE
DIRECT_IMPORT_RELATION
DEPENDENCY_METADATA
WORKSPACE_CONFIGURATION
PREVIOUS_ATTEMPT_RELEVANCE
MODEL_REQUESTED_CONTEXT
```

Repository content is explicitly labeled untrusted.

The model cannot freely browse arbitrary filesystem paths.

---

# 31. Patch Safety and Apply Protocol

## 31.1 Proposal Binding

Bind proposal to:

- run;
- stage;
- failure;
- repair attempt;
- context pack;
- Proposer invocation;
- Reviewer decision;
- diff checksum;
- pre-apply workspace fingerprint;
- plan version.

## 31.2 Apply Request

```json
{
  "proposal_id": "proposal-001",
  "diff_checksum": "sha256:...",
  "idempotency_key": "uuid"
}
```

## 31.3 Pre-Apply Validation

Verify:

1. proposal exists;
2. Reviewer accepted;
3. human approved;
4. checksum matches;
5. current fingerprint matches;
6. plan version matches;
7. diff parses;
8. paths are relative;
9. no path escape;
10. applicability dry-run passes;
11. changed files comply with approved scope.

## 31.4 Post-Apply

- apply exact persisted diff;
- calculate post-apply fingerprint;
- persist patch ledger;
- run PatchPreflightValidator;
- return to normal pipeline.

## 31.5 Patch Preflight

Fast checks may include:

- import resolution;
- referenced symbol existence;
- Angular/RxJS/Material API validity;
- obvious phantom packages;
- changed-template diagnostics;
- changed TypeScript diagnostics;
- dependency approval;
- changed-file sensitivity.

Passing preflight does not mean stage acceptance.

---

# 32. Repair Validation and Progress Detection

## 32.1 Earliest Invalidated Boundary

- package or lockfile change → final install → build → full tests;
- source/template/config change → static preflight → build → full tests;
- test-only change → full tests, while preserving valid prior build evidence if fingerprint rules permit;
- uncertainty → choose earlier safer boundary.

## 32.2 No-Progress Rules

Stop or escalate when:

- same patch fingerprint appears twice;
- same failure fingerprint persists twice;
- normalized error set does not improve;
- repair introduces a new failure;
- repair changes high-risk behavior without strategic approval;
- token or cost budget is exhausted.

## 32.3 Fresh Evidence

Failed repair validation creates new FailureEvidence. It does not reuse stale diagnostics.

## 32.4 Patch Rollback

If patch preflight or validation fails:

- preserve attempt evidence;
- rollback the patch if a safe patch checkpoint exists;
- otherwise reconstruct the stage from its clean input;
- create a new failure fingerprint;
- increment semantic repair attempt only after an applied patch fails validation.

---

# 33. Cancellation, Recovery, and Resume

## 33.1 Cancellation

```text
cancel requested
→ persist request
→ stop scheduling
→ signal active command
→ grace period
→ terminate process tree
→ capture partial logs
→ classify workspace safety
→ restore/reconstruct if needed
→ partial report
→ cancelled
```

## 33.2 Recovery Categories

- read-only operation interrupted → rerun;
- copy interrupted → delete destination and recopy;
- build/test interrupted with unchanged fingerprint → rerun;
- `ng update` interrupted → reconstruct stage;
- mutating install interrupted → reconstruct stage;
- patch crash before durable apply → reconstruct stage;
- patch crash after durable apply and fingerprint matches → resume validation;
- waiting approval → resume exact gate;
- completed stage → never rerun automatically.

## 33.3 Worker Lease

Store:

- lease ID;
- worker ID;
- heartbeat;
- expiry;
- execution ID;
- backend instance ID.

Stale ownership enters recovery or diagnostic hold.

## 33.4 Backend Instance Reconciliation

On startup:

```text
find running commands owned by another backend instance
→ mark interrupted
→ evaluate operation category
→ compare fingerprints
→ resume, rerun, or reconstruct from proven boundary
```

A process ID alone is not sufficient proof of command ownership.

---

# 34. Persistence and Database Model

Recommended tables:

- `migration_runs`
- `run_state`
- `stages`
- `stage_state`
- `step_state`
- `transition_events`
- `approvals`
- `preflights`
- `source_snapshots`
- `workspace_fingerprints`
- `compatibility_resolutions`
- `execution_profiles`
- `stage_execution_plans`
- `command_executions`
- `failures`
- `repair_attempts`
- `llm_invocations`
- `repair_proposals`
- `review_decisions`
- `user_decisions`
- `artifacts`
- `worker_leases`
- `assurance_status`
- `usage_records`
- `delivery_records`

Rules:

- WAL mode;
- short transactions;
- no transaction held during commands, LLM calls, or approval waits;
- optimistic state-version checks;
- idempotency keys;
- Artifact Store content outside DB.

## 34.1 Source-of-Truth Matrix

| Entity | Authority |
|---|---|
| Run lifecycle | SQLite |
| Stage lifecycle | SQLite |
| Step lifecycle | SQLite |
| Approval | SQLite |
| Plan metadata | SQLite + immutable artifact |
| Command result metadata | SQLite |
| Raw logs | Artifact Store |
| Workspace code | Sandbox filesystem |
| Failure details | SQLite + Artifact Store |
| Repair context | Artifact Store |
| Proposal diff | Artifact Store + checksum in SQLite |
| Reviewer decision | SQLite |
| Final report | Artifact Store + metadata in SQLite |

---

# 35. Artifact Store and Directory Layout

```text
<target-output-path>/
├── migrated-app/
└── .migration-factory/
    ├── snapshots/
    │   └── <snapshot-id>/
    ├── workspaces/
    │   └── <run-id>/
    │       ├── angular-18-to-19/
    │       │   └── workspace/
    │       ├── angular-19-to-20/
    │       │   └── workspace/
    │       └── angular-20-to-21/
    │           └── workspace/
    └── runs/
        └── <run-id>/
            ├── global/
            │   ├── 00_setup/
            │   ├── 01_baseline/
            │   ├── 02_analysis/
            │   ├── 03_feasibility/
            │   ├── 04_planning/
            │   └── 05_workflow_state/
            ├── stages/
            │   ├── angular-18-to-19/
            │   │   ├── 00_input/
            │   │   ├── 01_transform/
            │   │   ├── 02_validation/
            │   │   ├── 03_repair/
            │   │   │   ├── attempt-001/
            │   │   │   ├── attempt-002/
            │   │   │   └── attempt-003/
            │   │   └── 04_completion/
            │   ├── angular-19-to-20/
            │   └── angular-20-to-21/
            ├── final_assurance/
            ├── delivery/
            └── final_report/
```

Artifact rules:

- immutable;
- checksum-bound;
- schema-versioned;
- stage-scoped;
- attempt-scoped;
- no silent overwrite;
- atomic write and rename;
- DB registration after checksum;
- sensitive raw evidence marked accordingly.

## 35.1 Artifact Envelope

```json
{
  "schema_version": "1.0",
  "artifact_id": "uuid",
  "artifact_type": "stage_validation_summary",
  "run_id": "run-001",
  "stage_id": "angular-18-to-19",
  "attempt": null,
  "producer": "validation_service",
  "created_at": "ISO-8601",
  "policy_version": "migration-policy-v1",
  "input_artifact_hashes": [],
  "content_hash": "sha256:..."
}
```

---

# 36. SSE and Frontend State Synchronization

## 36.1 SSE Endpoint

```http
GET /migrations/{runId}/events
Last-Event-ID: 126
```

## 36.2 Recovery

1. frontend loads state snapshot;
2. opens SSE from latest sequence;
3. backend replays retained events;
4. frontend ignores duplicate or older events;
5. if replay unavailable, refresh snapshot.

## 36.3 Backend Source of Truth

UI receives:

- run status;
- phase;
- stage;
- step;
- approvals;
- commands;
- repair status;
- validation;
- assurance;
- cancellation;
- report readiness.

The frontend never advances state locally.

## 36.4 Log Streaming

- stream bounded chunks through SSE;
- persist complete logs as artifacts;
- use sequence IDs;
- maintain bounded frontend buffer;
- support stored log pagination and search.

---

# 37. AI Assistant

The Assistant answers:

- what is happening;
- why approval is required;
- what changed;
- why a command failed;
- what the Proposer suggested;
- what the Reviewer decided;
- which tests passed;
- what remains manual;
- token and cost usage;
- whether resume is safe.

The Assistant may:

- read state;
- read approved artifacts;
- explain decisions;
- create structured approval intent only when the user explicitly decides.

It may not:

- execute commands;
- mutate files;
- silently approve;
- invent evidence;
- expose secrets;
- bypass the Transition Service.

Approval through chat must use the same backend approval API and checksum validation as a UI button.

---

# 38. MCP Context Support

Modes:

```text
disabled
context_support
workspace_future
```

MVP default:

```text
disabled
```

Allowed context-support uses:

- Angular documentation;
- official migration guidance;
- approved internal knowledge;
- repair-context enrichment.

Forbidden:

- commands;
- installs;
- builds;
- tests;
- file mutation;
- Git mutation;
- approval;
- state transition.

MCP use must be logged as evidence when enabled.

---

# 39. LLM Gateway, Token Usage, and Cost

All LLM calls pass through the backend gateway.

Store:

- run;
- stage;
- role;
- task;
- provider;
- deployment;
- prompt version;
- schema version;
- input artifact hashes;
- input tokens;
- output tokens;
- total tokens;
- latency;
- retries;
- status;
- input cost;
- output cost;
- total cost.

Configured MVP price assumption:

```text
Input:  $0.25 per 1,000,000 tokens
Output: $2.00 per 1,000,000 tokens
```

Historical runs preserve the pricing values used at creation.

The gateway:

- sanitizes secrets;
- enforces context budget;
- validates structured output;
- stores redacted summaries;
- never stores hidden chain-of-thought;
- distinguishes transport retries from semantic repair attempts.

Budget actions:

```text
continue
warn
block_new_llm_calls
use_deterministic_fallback
diagnostic_hold
require_approval
```

Budget exhaustion never authorizes an unvalidated patch.

---

# 40. Security and Sandbox Controls

## 40.1 Execution Controls

- non-administrator worker where possible;
- sandbox path confinement;
- canonical path checks;
- symlink/junction escape prevention;
- process-tree tracking;
- timeout;
- disk threshold;
- environment allowlist;
- scoped credentials;
- network allowlist;
- source immutability verification;
- separate workspaces per run and stage.

## 40.2 Local MVP Terminology

When OS-level isolation is not implemented, the system must call the environment:

```text
controlled local execution sandbox
```

It must not claim strong containment equivalent to a container or microVM.

## 40.3 Lifecycle Scripts

Classify:

```text
allowed
allowed_in_restricted_sandbox
requires_review
blocked
unknown
```

Human approval is required before sensitive scripts execute.

## 40.4 Secret Handling

Redact:

- Azure keys;
- registry tokens;
- Authorization headers;
- cookies;
- passwords;
- `.npmrc` secrets;
- environment secrets.

Raw artifacts are sensitive local evidence and must be protected.

## 40.5 Prompt-Injection Boundary

Repository files, comments, Markdown, logs, package metadata, and compiler output are untrusted data.

They cannot:

- grant permission;
- approve a gate;
- alter policy;
- request secrets;
- authorize a command;
- change migration scope.

---

# 41. APIs

## 41.1 Preflight

```http
POST /migration-preflights
GET /migration-preflights/{id}
```

## 41.2 Runs

```http
POST /migrations
GET /migrations/{runId}
POST /migrations/{runId}/start
POST /migrations/{runId}/cancel
POST /migrations/{runId}/resume
```

## 41.3 State and Events

```http
GET /migrations/{runId}/state
GET /migrations/{runId}/events
```

## 41.4 Approvals

```http
GET /migrations/{runId}/approvals/pending
POST /migrations/{runId}/approvals
```

## 41.5 Stages

```http
GET /migrations/{runId}/stages
GET /migrations/{runId}/stages/{stageId}
GET /migrations/{runId}/stages/{stageId}/plan
GET /migrations/{runId}/stages/{stageId}/commands
GET /migrations/{runId}/stages/{stageId}/failures
```

## 41.6 Repair

```http
GET /migrations/{runId}/repair-proposals
GET /migrations/{runId}/repair-proposals/{proposalId}
POST /migrations/{runId}/repair-proposals/{proposalId}/apply
POST /migrations/{runId}/repair-proposals/{proposalId}/reject
```

## 41.7 Artifacts and Reports

```http
GET /migrations/{runId}/artifacts
GET /migrations/{runId}/artifacts/{artifactId}
GET /migrations/{runId}/report
POST /migrations/{runId}/delivery/publish
```

No API accepts arbitrary filesystem paths for artifact retrieval.

## 41.8 State Snapshot Example

```json
{
  "run_id": "run-001",
  "status": "waiting_approval",
  "phase": "planning",
  "state_version": 35,
  "latest_event_sequence": 127,
  "current_stage_id": null,
  "current_step": "plan_review",
  "approval": {
    "gate_id": "plan-approval",
    "status": "pending"
  },
  "assurance": {
    "technical_upgrade": "not_started",
    "functional_parity": "not_assessed",
    "security": "deferred_company_tool_required",
    "delivery_readiness": "not_ready"
  }
}
```

---

# 42. Observability and Operations

Track:

- run duration;
- stage duration;
- step duration;
- queue time;
- command duration;
- exit codes;
- worker heartbeats;
- cancellation latency;
- repair attempts;
- reviewer revisions;
- rollbacks;
- artifact size;
- SSE reconnects;
- SQLite contention;
- input tokens;
- output tokens;
- LLM cost;
- cache hits;
- approvals;
- approval wait time;
- manual items;
- source mutation status.

Alerts:

- lost worker heartbeat;
- disk threshold;
- source mutation;
- repeated timeout;
- Azure quota issue;
- state/artifact inconsistency;
- stuck approval;
- orphan workspace;
- failed artifact checksum;
- repeated no-progress repair.

Operational caches may include:

| Cache | Key | Rule |
|---|---|---|
| Discovery | source hash + scanner + policy | Reuse only on exact match |
| Compatibility | exact source + target policy + catalog | Immutable after plan approval |
| Package download | registry and package manager profile | Download optimization only |
| LLM result | model + prompt + schema + artifact hashes | Exact input match only |

---

# 43. Testing Strategy

## 43.1 Primary Seam

Test through:

```text
FastAPI application
+ temporary SQLite
+ temporary Artifact Store
+ fake CommandExecutor
+ fake Proposer
+ fake Reviewer
```

## 43.2 Critical Tests

1. source remains unchanged;
2. Angular 18.0.x and 18.2.x normalize to 18.x;
3. exact stage versions are resolved before execution;
4. LangGraph cannot bypass Transition Service;
5. stale state version rejects transition;
6. missing approval blocks progression;
7. every stage has its own sandbox;
8. stage copy excludes `node_modules`;
9. same ExecutionProfile is reused in repair validation;
10. command outside registry is rejected;
11. raw shell override is rejected;
12. baseline known failure is not classified as migration-caused;
13. `ERESOLVE` routes to dependency repair;
14. environment failure does not generate source patch;
15. Reviewer schema cannot contain a diff;
16. stale diff checksum blocks Apply;
17. stale workspace fingerprint blocks Apply;
18. path escape blocks Apply;
19. repair returns to normal pipeline;
20. duplicate patch fingerprint is rejected;
21. no-progress failure escalates;
22. interrupted `ng update` reconstructs stage;
23. waiting approval survives restart;
24. browser disconnect does not cancel;
25. final publication occurs only after approval;
26. final report distinguishes assurance statuses;
27. manual/deferred gates are not marked passed;
28. final source integrity check passes;
29. stage artifacts cannot overwrite another stage;
30. approval records are checksum-bound.

## 43.3 Runtime Proof

Prove:

```text
Angular 18.x
→ 19.x
→ 20.x
→ 21.x
```

including at least one real repair:

```text
failure
→ FailureEvidence
→ Proposer
→ Reviewer
→ human Apply
→ exact diff
→ normal pipeline
→ pass or fresh failure
```

## 43.4 LangGraph Tests

Prove:

- nodes request transitions rather than writing state directly;
- graph resume reconciles with SQLite;
- approval pause resumes exact gate;
- stale graph checkpoint cannot override newer SQLite state;
- node retry does not duplicate command execution;
- cancellation prevents future node scheduling.

---

# 44. MVP Definition of Done

The MVP is complete when:

1. Source and output paths are safely validated.
2. Angular source family is normalized dynamically.
3. Exact source and target versions are persisted.
4. Source snapshot and immutability proof exist.
5. One sandbox exists per stage.
6. LangGraph coordinates but does not own state.
7. Transition Service enforces every state change.
8. SQLite is authoritative state.
9. Artifact Store is authoritative evidence.
10. CommandExecutor is authoritative execution.
11. Human approval is enforced at every defined gate.
12. Baseline evidence is captured.
13. Known baseline failures are fingerprinted.
14. Support level is visible.
15. Exact ExecutionProfiles are resolved.
16. Exact StageExecutionPlans are approved.
17. Structured command policy is enforced.
18. Angular 18.x → 19.x → 20.x → 21.x runs one major at a time.
19. All mandatory technical gates execute.
20. Every transformation diff receives human approval.
21. Two-LLM repair governance works.
22. Reviewer cannot author a diff.
23. Backend applies only exact persisted diff.
24. Repair validation reuses normal pipeline.
25. No-progress repair detection works.
26. Cancellation terminates process tree.
27. Recovery uses proven boundaries.
28. Final clean assurance runs.
29. Human approves final assurance.
30. Human approves delivery.
31. Migrated app is published atomically.
32. Final report includes all approvals, evidence, costs, and unresolved items.

---

# 45. Implementation Sequence

## Phase 1 — Foundation

- repository skeleton;
- FastAPI;
- Next.js;
- SQLAlchemy;
- Alembic;
- SQLite WAL;
- Artifact Store;
- health endpoints;
- configuration.

## Phase 2 — State and Orchestration

- multidimensional state models;
- Transition Service;
- transition policy;
- approvals;
- events;
- LangGraph adapter;
- reconciliation.

## Phase 3 — Source and Workspace

- preflight;
- path safety;
- eligibility;
- snapshot;
- manifest;
- fingerprints;
- physical stage sandbox manager.

## Phase 4 — Discovery and Baseline

- version detection;
- topology;
- dependency inventory;
- lifecycle scripts;
- routes;
- backend integration;
- baseline execution;
- failure fingerprints.

## Phase 5 — Compatibility and Planning

- historical catalog;
- family normalization;
- exact version resolution;
- ExecutionProfile;
- StageExecutionPlan;
- build-system decision;
- human plan approval.

## Phase 6 — Command Execution

- structured registry;
- Command Policy Engine;
- CommandExecutor;
- process controller;
- log streaming;
- cancellation;
- worker lease.

## Phase 7 — Stage Pipeline

- bootstrap install;
- exact Angular update;
- version verification;
- final install;
- static checks;
- build;
- tests;
- lint;
- parity evidence;
- stage approvals.

## Phase 8 — Failure and Repair

- FailureEvidence;
- parsers;
- C-Lite;
- risk classification;
- RepairContextPack;
- LLM Gateway;
- Proposer;
- Reviewer;
- proposal persistence;
- human Apply/Reject;
- patch safety;
- normal-pipeline continuation.

## Phase 9 — Recovery and Delivery

- startup reconciliation;
- recovery policies;
- final assurance;
- delivery candidate;
- atomic publication;
- final report.

## Phase 10 — Runtime Proof

- representative Angular 18.x application;
- full 18 → 21 path;
- repair cycle;
- cancellation;
- restart;
- final evidence package.

---

# 46. Repository and Git Governance

Repository:

```text
angular-migration
```

Branches:

- `main`: protected final version;
- `dev`: stable integration branch;
- one branch per issue.

Workflow:

```text
checkout dev
→ fetch
→ pull latest dev
→ create issue branch
→ review docs and issue
→ implement
→ logical commits
→ push issue branch
→ validate
→ merge into dev
→ return to dev
→ fetch and pull
```

Codex must:

- read this specification;
- read the relevant Sprint document;
- avoid invention;
- stop on missing critical information;
- preserve strict compatibility scope;
- use clear logical commits;
- never push directly to `main`.

---

# 47. Future Extensions

- Angular 11–17 validated fixture paths;
- npm plus yarn/pnpm;
- Nx;
- multiple applications;
- libraries;
- microfrontends;
- SSR/hybrid;
- company-approved browser automation;
- company-approved security and quality tools;
- PostgreSQL;
- distributed workers;
- stronger container or microVM isolation;
- RBAC;
- multi-user approvals;
- pull-request integration;
- CI/CD;
- risk-based repair auto-apply after sufficient evidence;
- separate modernization products.

---

# 48. Non-Negotiable Rules

1. Original source is never mutated.
2. Angular families are supported; workflows are not hardcoded to 18.2.x.
3. Exact versions are resolved before execution.
4. One major version is migrated at a time.
5. Every stage has a dedicated sandbox.
6. LangGraph coordinates only.
7. Transition Service validates state transitions.
8. SQLite is authoritative state.
9. CommandExecutor is authoritative execution.
10. Artifact Store is authoritative evidence.
11. Human approval is mandatory at every defined gate.
12. Every mutation is backend-authorized.
13. No arbitrary shell command is accepted.
14. Official Angular tooling runs before AI repair.
15. Only the Proposer authors a repair diff.
16. Reviewer never authors a patch.
17. Human Apply or Reject is mandatory for repairs.
18. Only exact persisted diff is applied.
19. Repair uses the same normal pipeline.
20. Failed repair produces fresh evidence.
21. No repeated equivalent patch.
22. No progress causes escalation.
23. Technical success does not prove functional parity.
24. Manual and deferred gates remain visible.
25. Final application is published only after final assurance and human delivery approval.
26. Reports never claim unexecuted checks passed.
27. Recovery occurs only from proven state.
28. Source integrity is verified at completion, cancellation, and failure.

---

# 49. Glossary

| Term | Definition |
|---|---|
| Angular family | Major-version family such as `18.x`. |
| Exact version | Resolved patch version used for execution. |
| ExecutionProfile | Exact reusable Node/npm/environment runtime profile. |
| StageExecutionPlan | Approved immutable executable contract for one stage. |
| Transition Service | Application service that validates and persists legal state transitions. |
| CommandExecutor | Sole trusted external-process execution component. |
| Artifact Store | Filesystem evidence store with checksum metadata. |
| Sandbox | Product-owned writable stage workspace. |
| FailureEvidence | Structured evidence created from a real failed command. |
| C-Lite | Five-route top-level failure classification model. |
| RepairContextPack | Bounded model-visible context derived from evidence. |
| Proposer | LLM role that diagnoses and authors the repair diff. |
| Reviewer | LLM role that reviews without authoring a diff. |
| Workspace fingerprint | Hash of canonical migration-relevant workspace state. |
| Approval gate | Human decision bound to state and evidence checksums. |
| Functional parity | Preservation of approved observable application behavior. |
| Atomic publication | Final output appears only after complete delivery succeeds. |

---

# 50. Reference Governance

Compatibility and execution policy must be maintained from:

- official Angular release policy;
- official Angular version compatibility tables;
- official Angular Update Guide;
- official Angular CLI command documentation;
- official Angular build-system migration guidance;
- official npm clean-install behavior;
- approved company security and tooling policies;
- internal historical migration fixture evidence.

Rules:

- external compatibility information is cached into a versioned internal catalog;
- source URL, retrieval date, and policy version are recorded;
- approved plans never change because a new package was published later;
- catalog changes require fixture revalidation;
- model, prompt, schema, repair policy, and command-policy changes require regression testing;
- historical support claims require stored evidence.

---

# Final Product Contract

The Angular Migration Control Tower must operate as:

```text
Human selects source and target
→ deterministic preflight
→ human approval
→ immutable source snapshot
→ human approval
→ baseline and discovery
→ human approval
→ exact family-aware compatibility plan
→ human approval
→ LangGraph coordinates stage workflow
→ Transition Service validates movement
→ SQLite stores authoritative state
→ CommandExecutor runs authorized commands
→ Artifact Store preserves evidence
→ each stage executes in its own sandbox
→ every transformation is reviewed and approved
→ failures create deterministic evidence
→ Proposer authors
→ Reviewer reviews
→ human applies or rejects
→ backend applies exact persisted patch
→ same normal pipeline validates
→ human approves stage completion
→ final clean assurance
→ human approves delivery
→ migrated app is published atomically
→ final evidence report is generated
```

The platform should remain simple for the user, deterministic and strict internally, honest about what is proven, and uncompromising about source safety, human authority, execution reproducibility, state integrity, and evidence quality.

---

# Part II — Detailed Implementation Contracts

The sections below expand the core architecture into implementation-grade contracts. They are normative unless explicitly labeled as guidance. They do not replace Sections 1–50; they clarify how those decisions must be implemented without weakening the existing safety, approval, evidence, or strict-parity rules.

# 51. External Reference Findings and Policy Consequences

## 51.1 Angular release and migration policy

The implementation must maintain a versioned internal compatibility catalogue derived from official Angular sources. External documentation is evidence used to update policy; it is not queried opportunistically during an already approved stage in a way that silently changes the execution plan.

The following policy consequences are locked:

1. A migration spanning more than one Angular major is decomposed into consecutive major transitions.
2. The high-level route is deterministic and generated by the backend, not by an LLM.
3. The accepted product input is an Angular family such as `18.x`, not a single hardcoded patch such as `18.2.7`.
4. The actual source patch is detected and recorded.
5. The target family is resolved to an exact approved patch before a stage can start.
6. Node.js, TypeScript, RxJS, Zone.js, Angular CLI, and builder compatibility are resolved from the catalogue for each transition.
7. The catalogue is versioned, checksummed, and bound to the approved stage plan.
8. A catalogue update cannot mutate a stage plan already approved by the user.
9. Angular 21.x is the approved first MVP target family, not the latest Angular release.
10. Angular 22 and future versions are outside the first MVP proof route unless the product owner creates a new approved target policy.

## 51.2 Angular CLI update policy

Official Angular update tooling remains the authoritative first migration mechanism. The planning layer may use a family-oriented form to explain the route, but executable commands must be exact and immutable.

Conceptual planning representation:

```text
Angular 18.x → Angular 19.x
```

Executable plan representation:

```text
resolved target core: 19.a.b
resolved target cli:  19.c.d
approved argv: [npx, -p, @angular/cli@19.c.d, ng, update,
                @angular/cli@19.c.d, @angular/core@19.a.b,
                --allow-dirty=false, --interactive=false]
```

The exact syntax may differ depending on the package-manager strategy, but the following remain mandatory:

- no accidental global CLI dependency;
- no unapproved patch drift;
- no silent `--force`;
- no silent `--legacy-peer-deps`;
- no unresolved interactive prompts;
- complete command evidence;
- exact runtime identity.

## 51.3 Build-system migration consequence

Angular build-system migrations may be optional even when offered during a framework update. Therefore, the migration factory must treat builder changes as a first-class decision, not as an invisible CLI side effect.

The default policy is:

```text
preserve current builder and output behavior
unless the change is required for target compatibility
and explicitly approved by the human reviewer
```

When a builder change is proposed, the plan must expose:

- current builder;
- proposed builder;
- whether the change is required or optional;
- output-directory impact;
- asset-processing impact;
- styles and scripts impact;
- SSR/prerender impact;
- custom-builder compatibility;
- deployment assumptions;
- rollback strategy;
- additional validation gates.

## 51.4 LangGraph consequence

LangGraph provides useful graph execution, interrupts, streaming, and checkpoint mechanisms. This project deliberately limits its authority.

LangGraph checkpoint data may be used as a reconstructible orchestration cache, but it is not the business source of truth. The authoritative state remains the SQLite domain model written through the Transition Service.

The separation is intentional:

```text
LangGraph checkpoint
= graph execution convenience and resume hint

SQLite domain state
= approved run, stage, step, approval, command, and repair truth
```

On conflict, SQLite wins. The graph must reconstruct itself from SQLite and registered artifacts.

## 51.5 SSE consequence

SSE is appropriate for one-way server-to-browser updates such as state changes, log notifications, approval requests, and report readiness. SSE is not durable by itself.

Therefore:

- every important event is persisted before emission;
- every event has a monotonic job-scoped sequence number;
- the browser reconnects with its last received event ID;
- the backend can replay missing durable events;
- log chunks may be transiently streamed, but durable log artifacts remain in the Artifact Store;
- the frontend reloads an authoritative state snapshot after a replay gap or schema mismatch.

## 51.6 SQLite WAL consequence

SQLite WAL is suitable for the first single-host, one-active-run MVP. It allows readers and the writer to operate with improved concurrency, but it remains a same-host storage design.

The project therefore locks these constraints:

- database and WAL files reside on local storage, not a network share;
- FastAPI is the sole application writer;
- transactions are short;
- no transaction remains open during a command, LLM request, filesystem copy, or approval wait;
- large logs and diffs are not stored as database blobs;
- multi-host workers require a later migration to PostgreSQL or another server database.

## 51.7 Structured LLM output consequence

Azure OpenAI structured outputs should be used where supported for the Proposer and Reviewer contracts. JSON schema adherence reduces parsing ambiguity, but structured syntax alone is not sufficient.

Every model output passes:

```text
provider/schema validation
→ Pydantic validation
→ semantic domain validation
→ security validation
→ proposal lineage binding
```

A valid JSON object is rejected when, for example:

- the diff is empty;
- a changed path escapes the sandbox;
- the changed-file list does not match the diff;
- the proposal references stale evidence;
- the Reviewer returns a patch field;
- required evidence references are missing;
- the model requests forbidden capabilities.

# 52. Detailed Product Requirements and User Stories

## 52.1 Product-level requirements

The product shall:

1. Accept a readable local Angular workspace whose exact source version belongs to an approved Angular family.
2. Treat the original source as immutable throughout the full run lifecycle.
3. Accept a user-selected output directory that is path-safe and separate from the source and internal data root.
4. Detect the source Angular family and exact version.
5. Detect Angular CLI, TypeScript, RxJS, Zone.js, Node.js, npm, lockfile, projects, builders, scripts, tests, lint, routes, and backend-integration indicators.
6. Resolve a one-major-at-a-time route.
7. Resolve exact executable versions at each stage.
8. Create an immutable source snapshot and a dedicated physical sandbox for every major transition.
9. Establish the strongest executable baseline available before migration.
10. Require human approval after each defined workflow phase.
11. Execute only backend-registered commands.
12. Capture complete command and artifact evidence.
13. Use official Angular tooling before LLM repair.
14. Classify failures deterministically before invoking an LLM.
15. Use separate Proposer and Reviewer LLM roles.
16. Require human Apply or Reject for each accepted repair proposal.
17. Apply only the exact persisted backend proposal.
18. Reuse the normal validation pipeline after repair.
19. Prevent repeated or no-progress repair loops.
20. Produce independent technical, parity, security, quality, and delivery statuses.
21. Recover only from proven states.
22. Publish the final migrated application atomically only after final assurance and delivery approval.
23. Produce a final evidence report and token/cost report.

## 52.2 Source and setup user stories

1. As a developer, I can select an Angular 18.0.x, 18.1.x, or 18.2.x application without the factory being hardcoded to one patch line.
2. As a developer, I can see the exact detected version even though the route is expressed by family.
3. As a developer, I can select a target Angular family approved by company policy.
4. As a developer, I can choose a separate destination for the final migrated application.
5. As a developer, I can see why a path is rejected before the migration starts.
6. As a developer, I can see whether my source is a Git repository or a plain folder.
7. As a developer, I can migrate a plain folder without allowing the product to mutate it.
8. As a developer, I can review discovered runtimes and select among approved runtime candidates.
9. As a developer, I can see detected, selected, and required values separately.
10. As a developer, I can approve or reject the source qualification package.

## 52.3 Baseline and analysis user stories

11. As a developer, I can see whether baseline install, build, tests, and lint were machine-executed, blocked, not configured, or user-attested.
12. As a developer, I can see pre-existing failures separately from migration-caused failures.
13. As a developer, I can approve a known-failure baseline only through an explicit policy decision.
14. As a developer, I can review the workspace topology and know whether it is within the MVP support envelope.
15. As a developer, I can review dependency, private-package, lifecycle-script, route, builder, test, lint, and backend-integration inventories.
16. As a developer, I can see which findings are facts and which are AI interpretations.
17. As a developer, I must approve the completed analysis package before feasibility evaluation continues.
18. As a product owner, I can distinguish `officially_supported`, `historical_validated`, `historical_experimental`, and `blocked` paths.

## 52.4 Planning user stories

19. As a developer, I can see every planned stage before mutation starts.
20. As a developer, I can see the exact Stage 1 runtime and commands before approving the plan.
21. As a developer, I can see later stages as family-level plans that are finalized from actual prior-stage output.
22. As a developer, I can see allowed and forbidden changes.
23. As a developer, I can see whether a builder change is required, optional, sensitive, or blocked.
24. As a developer, I can reject optional modernization while still proceeding with compatibility migration.
25. As a developer, I can review validation gates and manual/deferred items.
26. As a developer, I can request a plan modification and receive a new version rather than mutating an approved plan silently.
27. As a developer, I must approve each plan version before it becomes executable.

## 52.5 Stage execution user stories

28. As a developer, I can see a separate sandbox for every Angular major transition.
29. As a developer, I can see the input fingerprint and exact execution profile for the current stage.
30. As a developer, I must approve the stage start package.
31. As a developer, I can observe live command progress without the browser owning the process.
32. As a developer, refreshing the browser does not cancel the job.
33. As a developer, I can cancel the migration explicitly and receive a partial evidence report.
34. As a developer, I can inspect the complete transformation diff before validation is accepted.
35. As a developer, I must approve the transformation evidence before the workflow crosses the configured gate.
36. As a developer, I can review build, tests, lint, routes, backend integration, and changed-file risk evidence.
37. As a developer, I must approve validation and stage completion separately.

## 52.6 Repair user stories

38. As a developer, I can see the real failed command, exit code, diagnostics, and logs.
39. As a developer, I can see whether the failure is code/config, dependency, environment/user action, retryable external, or unknown.
40. As a developer, I am not shown an application patch for a missing executable or registry authentication problem.
41. As a developer, I can see which files and evidence the Proposer received.
42. As a developer, I can see the Proposer diagnosis, strategy, exact diff, risk notes, and model identity.
43. As a developer, I can see the independent Reviewer decision and critique.
44. As a developer, I know the Reviewer did not author a hidden replacement patch.
45. As a developer, I can Apply or Reject the exact persisted proposal.
46. As a developer, a stale workspace prevents an old proposal from being applied.
47. As a developer, a patch that escapes the sandbox is rejected.
48. As a developer, a failed repair creates fresh evidence and a new attempt lineage.
49. As a developer, repeated equivalent patches are blocked.
50. As a developer, the system stops and escalates when attempts do not improve the error set.

## 52.7 Delivery and reporting user stories

51. As a developer, I can see technical success independently from parity, security, quality, and delivery statuses.
52. As a developer, I can see `PROVEN`, `INFERRED`, and `NOT_PROVEN` labels on report claims.
53. As a developer, I must approve the final clean assurance evidence.
54. As a developer, I can review the delivery manifest before publication.
55. As a developer, the `migrated-app` directory appears only after successful atomic publication.
56. As a lead, I can inspect all approvals, commands, failures, repairs, fingerprints, and unresolved risks.
57. As a lead, I can see total input tokens, output tokens, total tokens, and estimated cost.
58. As an auditor, I can verify that the original source remained unchanged.
59. As an auditor, I can trace every final file to a stage output and approved repair lineage.
60. As a future maintainer, I can extend the compatibility catalogue without redesigning the workflow kernel.

# 53. Detailed Authority and Component Contracts

## 53.1 Authority matrix

| Concern | Authoritative owner | Non-authoritative participants |
|---|---|---|
| Workflow coordination | LangGraph adapter | UI, service callers |
| Legal state transition | Transition Service | LangGraph nodes |
| Current structured state | SQLite | LangGraph checkpoint, UI cache |
| External command execution | CommandExecutor | LangGraph, agents, UI |
| Process termination | ProcessController | JobSupervisor |
| Workspace mutation | WorkspaceManager and PatchApplyService | LLMs, UI |
| Evidence content | Artifact Store | SQLite metadata references |
| Approval decision | Human decision persisted by Approval Service | Reviewer recommendation |
| Repair diff authorship | Proposer LLM | Reviewer, human, UI |
| Repair acceptance review | Reviewer LLM | Proposer |
| Patch application authorization | Human + backend policy | LLMs |
| Compatibility truth | Versioned Compatibility Catalogue | LLM explanation |
| Final delivery | Delivery Service | UI trigger |

## 53.2 JobSupervisor contract

**Purpose**

Own the lifecycle of the one active MVP run and coordinate graph execution, command ownership, cancellation, lease state, and startup reconciliation.

**Inputs**

- run ID;
- requested operation: start, resume, cancel, reconcile;
- current authoritative state version;
- authenticated user action;
- policy version.

**Outputs**

- accepted or rejected control result;
- active worker lease;
- durable events;
- graph invocation or cancellation signal;
- recovery action.

**Allowed capabilities**

- invoke LangGraph;
- acquire/release leases;
- call ProcessController;
- request transitions;
- read artifacts and state.

**Forbidden actions**

- direct state mutation outside Transition Service;
- direct shell execution;
- unregistered filesystem mutation;
- approval fabrication.

**Stop conditions**

- conflicting active lease;
- stale state version;
- cancellation requested;
- unrecoverable integrity mismatch;
- required approval missing.

## 53.3 Transition Service contract

**Purpose**

Validate every domain transition against state version, prerequisites, approvals, fingerprints, evidence, policy, and lease ownership.

**Required behavior**

1. Load the current domain aggregate in a short transaction.
2. Compare expected state version.
3. Validate transition policy.
4. Validate required approval and artifact bindings.
5. Write the new state.
6. Append a durable transition event.
7. Commit atomically.
8. Return the new state version.

**Forbidden behavior**

- accepting a graph checkpoint as proof;
- marking a step complete before artifacts exist;
- changing multiple unrelated aggregates without a defined transaction contract;
- holding a transaction during external work.

## 53.4 WorkspaceManager contract

**Purpose**

Own source snapshots, stage sandbox creation, copy-forward, cleanup, reconstruction, quarantine, and final export preparation.

**Inputs**

- canonical source path;
- data root;
- run ID and stage ID;
- copy policy;
- exclusion policy;
- expected source fingerprint;
- target destination.

**Outputs**

- workspace manifest;
- copy report;
- cleanliness report;
- fingerprint;
- quarantine reference;
- export candidate.

**Forbidden actions**

- mutate the original source;
- follow links outside allowed roots;
- copy an unvalidated stage forward;
- trust an interrupted destination;
- delete user-owned paths outside the product data root.

## 53.5 CompatibilityResolver contract

**Purpose**

Resolve family-level migration intent into a feasible stage route and exact executable constraints.

**Inputs**

- exact current workspace versions;
- source and target families;
- compatibility catalogue version;
- available runtime inventory;
- workspace topology;
- dependency and builder findings;
- company policy.

**Outputs**

- support level;
- route;
- blockers;
- runtime candidates;
- exact version candidate set;
- required approvals;
- validation implications.

**Forbidden actions**

- choose versions through LLM opinion;
- silently relax peer constraints;
- claim historical support without fixtures;
- change an approved catalogue version mid-stage.

## 53.6 Artifact Service contract

**Purpose**

Persist immutable evidence using atomic file creation, checksum calculation, metadata registration, access control, and reconciliation.

**Artifact creation protocol**

```text
serialize to temporary file
→ flush and close
→ calculate SHA-256
→ atomically rename to final path
→ register metadata in SQLite
→ emit ARTIFACT_REGISTERED
```

**Forbidden actions**

- overwrite an immutable artifact;
- expose arbitrary filesystem paths through an artifact API;
- register a file before finalization;
- treat a missing file as valid evidence.

## 53.7 Approval Service contract

**Purpose**

Persist human decisions bound to a gate, state version, artifact-set checksum, plan version, and workspace fingerprint.

**Behavior**

- decisions are append-only;
- modifications create new decisions, not in-place history edits;
- a gate is satisfied only by the latest valid decision;
- stale approvals remain visible but are not executable;
- rejection and modification requests stop progression;
- approval comments are evidence, not replacements for technical gates.

## 53.8 Validation Service contract

**Purpose**

Execute or aggregate the normal stage validation plan and produce independent assurance results.

**Forbidden actions**

- mutate source code;
- run different commands for repair without a plan revision;
- mark manual checks as passed;
- collapse all assurance into one boolean.

## 53.9 Delivery Service contract

**Purpose**

Create a clean delivery candidate from the final validated sandbox and publish it atomically after human approval.

**Required evidence**

- final stage output fingerprint;
- final clean-install/build/test evidence;
- source-integrity evidence;
- unresolved-risk list;
- delivery manifest;
- destination validation;
- delivery approval.

# 54. LangGraph Graph Design and Node Contracts

## 54.1 Graph role

LangGraph models the workflow order and coordinates service calls. It must remain thin. A graph node should not contain large domain algorithms, direct SQL writes, subprocess execution, or uncontrolled filesystem code.

Preferred pattern:

```text
node receives run_id + expected_state_version
→ reads authoritative state through application service
→ invokes one bounded use case
→ use case writes artifacts
→ use case requests legal transition
→ node returns routing outcome
```

## 54.2 Recommended top-level graph

```text
load_run
→ preflight
→ wait_source_approval
→ snapshot
→ wait_snapshot_approval
→ baseline
→ wait_baseline_approval
→ analysis
→ wait_analysis_approval
→ feasibility
→ wait_feasibility_approval
→ planning
→ wait_plan_approval
→ stage_loop
→ final_assurance
→ wait_final_assurance_approval
→ delivery_candidate
→ wait_delivery_approval
→ publish
→ report
→ wait_report_acceptance
→ complete
```

## 54.3 Stage subgraph

```text
prepare_stage
→ wait_stage_start_approval
→ create_sandbox
→ resolve_stage_profile
→ lock_stage_plan
→ dependency_audit
→ bootstrap_install
→ angular_update
→ target_verification
→ capture_transform_diff
→ wait_transform_approval
→ final_install
→ static_checks
→ builds
→ tests
→ conditional_checks
→ parity_evidence
→ wait_validation_approval
→ if failure: repair_subgraph
→ cleanup
→ fingerprint
→ wait_stage_completion_approval
→ copy_forward
```

## 54.4 Repair subgraph

```text
capture_failure
→ classify_failure
→ route_environment_or_retry_or_repair
→ build_context
→ proposer
→ validate_proposer
→ reviewer
→ reviewer_decision
   ├── request_revision → proposer
   ├── insufficient_context → bounded_context_expansion
   ├── reject → human escalation
   └── accept → persist_proposal
→ wait_human_apply_reject
→ patch_safety
→ apply_exact_diff
→ patch_preflight
→ resume_normal_pipeline
→ wait_repair_validation_approval
```

## 54.5 Node input contract

Every node receives a small serializable state containing references, not heavy evidence:

```json
{
  "run_id": "run-001",
  "expected_state_version": 42,
  "current_stage_id": "stage-001",
  "current_step": "analysis",
  "pending_gate_id": null,
  "last_transition_id": "transition-041",
  "routing_hint": null
}
```

Logs, diffs, source files, model responses, and reports stay in the Artifact Store and are referenced by IDs.

## 54.6 Node output contract

```json
{
  "run_id": "run-001",
  "new_state_version": 43,
  "outcome": "waiting_approval",
  "next_route": "wait_analysis_approval",
  "artifact_refs": ["artifact-analysis-summary"],
  "transition_id": "transition-042"
}
```

## 54.7 Interrupt and approval behavior

LangGraph may pause at an approval node, but the durable approval truth is not the interrupt payload. The resume sequence is:

1. User submits decision through FastAPI.
2. Approval Service validates and persists the decision.
3. Transition Service advances or rejects the gate state.
4. JobSupervisor resumes the graph with the new authoritative state version.
5. The node reloads state and routes accordingly.

A direct graph resume payload must never bypass the approval API.

## 54.8 Graph checkpoint policy

Allowed:

- store minimal graph routing state;
- resume a graph thread after process restart;
- aid debugging;
- support human-in-the-loop pauses.

Not allowed:

- treat graph checkpoint fields as authoritative approval;
- store unredacted source code or secrets;
- use checkpoint writes instead of Transition Service writes;
- infer a completed command solely from graph position;
- resume a mutating command halfway through.

## 54.9 Graph reconstruction

On startup or checkpoint loss:

```text
load authoritative run aggregate from SQLite
→ inspect active commands and leases
→ reconcile artifacts and workspaces
→ determine proven recovery boundary
→ create/recreate graph thread state
→ resume from the corresponding node
```

## 54.10 LangGraph testing requirements

Tests must prove:

- nodes call services rather than writing state directly;
- stale state versions are rejected;
- missing approval cannot be bypassed by graph input;
- graph restart reconstructs from SQLite;
- graph checkpoint loss does not lose business state;
- cancelled runs do not schedule new commands;
- stage loop uses actual previous-stage output;
- repair flow returns to the normal pipeline.

# 55. Transition Service and Approval Transaction Protocol

## 55.1 Domain aggregate boundaries

The Transition Service operates on explicit aggregates rather than a single oversized mutable run object.

Recommended aggregates:

- `MigrationRun` — global lifecycle, phase, active stage, cancellation, final status;
- `MigrationStage` — current major transition, input/output fingerprints, stage status;
- `WorkflowStep` — analysis, planning, transformation, validation, repair, delivery steps;
- `ApprovalGate` — required evidence, state, expiry, current decision;
- `CommandExecution` — external command lifecycle;
- `RepairChain` — failure and attempt lineage;
- `DeliveryRecord` — candidate, approval, publication, export fingerprint.

A transition command identifies the aggregate, expected version, requested transition, actor, prerequisites, and idempotency key.

## 55.2 Transition command example

```json
{
  "aggregate_type": "migration_stage",
  "aggregate_id": "stage-18-to-19",
  "expected_version": 18,
  "transition": "validation_completed_to_waiting_approval",
  "actor_type": "validation_service",
  "actor_id": "validation-service",
  "reason": "All configured automated validation commands completed.",
  "artifact_refs": [
    "artifact-stage-validation-summary",
    "artifact-route-comparison",
    "artifact-backend-comparison"
  ],
  "required_fingerprint": "sha256:stage-current-state",
  "idempotency_key": "sha256:transition-payload"
}
```

## 55.3 Transition validation order

The Transition Service validates in this order:

1. authenticate and authorize actor;
2. validate schema;
3. load aggregate and lock for short update;
4. compare expected version;
5. detect prior idempotent result;
6. verify current status and phase;
7. verify prerequisite steps;
8. verify required command outcomes;
9. verify required artifacts exist and match checksums;
10. verify required workspace fingerprint;
11. verify lease and backend instance ownership when applicable;
12. verify approval gate rules;
13. execute transition policy;
14. persist new aggregate state and version;
15. append durable event;
16. commit;
17. return resulting state snapshot.

## 55.4 Optimistic concurrency

Every mutable aggregate has a monotonically increasing version. The UI, LangGraph, and background services pass the version they observed. A stale request receives a conflict response and must reload.

This prevents:

- duplicate stage starts;
- approval of an obsolete artifact set;
- applying an old repair;
- marking the wrong stage completed;
- the UI overwriting newer backend state;
- two workers owning the same command.

## 55.5 Idempotency

Idempotency keys are mandatory for:

- run start;
- cancellation;
- approval submission;
- command scheduling;
- patch Apply;
- copy-forward;
- final publication;
- report generation.

A repeated request with the same key returns the original result. A repeated key with a different payload is rejected as an integrity violation.

## 55.6 Approval transaction

An approval is accepted only when its binding still matches the active gate.

Binding fields:

- run ID;
- stage ID when applicable;
- gate ID and gate version;
- current aggregate version;
- plan ID and plan version;
- artifact-set checksum;
- workspace fingerprint;
- proposal checksum for repair;
- policy version;
- user identity;
- decision timestamp.

Approval flow:

```text
UI loads gate package
→ user reviews artifacts
→ UI submits identifiers + observed checksums/version
→ Approval Service reloads authoritative package
→ validates staleness and permissions
→ appends UserDecision
→ Transition Service advances gate or records rejection/modification request
→ durable event emitted
→ LangGraph resumes from authoritative state
```

## 55.7 Approval modification requests

`modification_requested` does not mutate the prior artifact in place. The owning service creates a new artifact version and a new gate version.

Examples:

- analysis findings need clarification;
- plan command needs correction;
- transformation diff contains forbidden modernization;
- repair proposal needs another Proposer revision;
- final report omits a required manual item.

## 55.8 Approval rejection

A rejection must specify the configured consequence:

- return to previous editable phase;
- place run in diagnostic hold;
- cancel run;
- mark stage failed;
- abandon repair proposal;
- deny delivery.

The product must not guess the consequence from a free-text comment.

## 55.9 Core gate non-bypass rule

A human may approve a workflow artifact or accept a documented risk, but cannot rewrite machine evidence.

Examples:

- a failed build remains failed;
- a missing test suite remains `not_configured`;
- a blocked registry remains `blocked_by_environment`;
- a manual browser check remains `manual_validation_required` until recorded;
- a stale patch remains stale;
- a target version mismatch remains failed.

# 56. Detailed Human Approval Gate Catalogue

## 56.1 Gate principles

Every gate is a first-class persistent entity. A gate defines:

- purpose;
- entry criteria;
- evidence package;
- allowed decisions;
- required role;
- expiry/staleness rules;
- approval consequence;
- rejection consequence;
- next legal transitions.

Human approval is mandatory at every gate listed below. The first MVP does not auto-approve gates.

## 56.2 G01 — Source and path acceptance

**Purpose:** Confirm that the selected application and target paths are correct and that the product may create its internal run structure.

**Evidence:**

- canonical source path;
- canonical target path;
- overlap/nesting analysis;
- source classification;
- detected Angular family and exact version;
- source type;
- eligibility warnings;
- available disk space;
- read/write probe results.

**Approver action:** approve, request modification, or reject.

**Stale when:** either path, detected source identity, or eligibility result changes.

## 56.3 G02 — Immutable snapshot acceptance

**Purpose:** Confirm the exact source baseline that will be preserved.

**Evidence:**

- source manifest;
- file count and size;
- exclusions;
- source fingerprint;
- Git metadata when available;
- copy integrity report;
- source read-only verification.

**Stale when:** source fingerprint or snapshot changes.

## 56.4 G03 — Baseline acceptance

**Purpose:** Confirm the known pre-migration state.

**Evidence:**

- exact versions;
- install/build/test/lint results;
- known baseline failures;
- route inventory;
- backend-integration snapshot;
- package and lifecycle-script inventory;
- evidence confidence level;
- user attestation where automation was blocked.

**Policy:** A user-attested baseline cannot be labeled machine proven.

## 56.5 G04 — Analysis acceptance

**Purpose:** Confirm discovery facts, risks, and support-envelope classification.

**Evidence:**

- workspace topology;
- project inventory;
- builder inventory;
- dependencies and private packages;
- test/lint inventory;
- SSR/PWA/i18n indicators;
- auth/API/form/routing sensitivity inventory;
- unresolved unknowns;
- Analysis Agent interpretation separated from deterministic facts.

## 56.6 G05 — Feasibility acceptance

**Purpose:** Decide whether the requested route may proceed.

**Evidence:**

- support level;
- stage ladder;
- historical compatibility evidence;
- runtime availability;
- blockers;
- required manual actions;
- excluded capabilities;
- expected manual/deferred gates.

**Decisions:** approve, approve with documented experimental risk, request modification, reject.

## 56.7 G06 — Migration plan acceptance

**Purpose:** Lock the execution contract.

**Evidence:**

- route;
- exact Stage 1 profile and commands;
- candidate later-stage profiles;
- command registry entries;
- builder decisions;
- allowed and forbidden changes;
- validation plan;
- repair budgets;
- rollback/recovery policy;
- artifact layout;
- delivery strategy.

## 56.8 G07 — Stage-start acceptance

**Purpose:** Confirm the current stage input and exact plan.

**Evidence:**

- stage input fingerprint;
- previous stage output reference;
- exact current versions;
- selected ExecutionProfile;
- exact StageExecutionPlan;
- current compatibility-catalogue version;
- current sandbox destination;
- pending risks.

## 56.9 G08 — Transformation acceptance

**Purpose:** Review official Angular migration output before accepting the transformation boundary.

**Evidence:**

- `ng update` commands and outputs;
- package and lockfile diff;
- source/config diff;
- migrations executed;
- builder changes;
- changed-file risk classification;
- forbidden-modernization scan;
- target-version preliminary verification.

**Policy:** Any unexpected auth, business, route, API, or visual-style change requires explicit explanation and may be rejected.

## 56.10 G09 — Validation acceptance

**Purpose:** Review all stage validation evidence.

**Evidence:**

- exact version result;
- final clean install;
- build matrix;
- complete configured tests;
- lint and conditional targets;
- route comparison;
- backend-integration comparison;
- changed-file risk;
- parity evidence;
- manual/deferred checklist;
- unresolved failures.

## 56.11 G10 — Repair proposal Apply/Reject

**Purpose:** Authorize a specific reviewed LLM patch.

**Evidence:**

- failure evidence;
- context selection summary;
- Proposer output;
- Reviewer output;
- exact persisted diff;
- changed-file risk;
- proposal checksum;
- expected pre-apply fingerprint;
- prior attempts and error delta.

**Allowed decisions:** Apply, Reject, or request a Proposer revision through the governed flow.

## 56.12 G11 — Repair validation acceptance

**Purpose:** Confirm the result of the applied patch through the normal pipeline.

**Evidence:**

- post-apply fingerprint;
- patch preflight;
- commands rerun;
- build/test results;
- error delta;
- new failure evidence if unsuccessful;
- rollback status.

## 56.13 G12 — Stage-completion acceptance

**Purpose:** Seal the stage output.

**Evidence:**

- stage validation summary;
- cleanup report;
- cleanliness verification;
- output fingerprint;
- full artifact index;
- accepted risks and manual items;
- copy-forward readiness.

## 56.14 G13 — Final assurance acceptance

**Purpose:** Confirm the clean final candidate independently of stage-local transient state.

**Evidence:**

- final frozen clean install;
- exact final version inventory;
- all production builds;
- complete configured tests;
- conditional lint/SSR/PWA/i18n builds;
- route and backend comparisons;
- source-integrity proof;
- final parity and assurance statuses.

## 56.15 G14 — Delivery acceptance

**Purpose:** Authorize publication to the user-selected output.

**Evidence:**

- delivery candidate fingerprint;
- destination safety check;
- file manifest;
- exclusion list;
- overwrite policy;
- unresolved manual/deferred items;
- atomic publication plan.

## 56.16 G15 — Final report acceptance

**Purpose:** Confirm that the run record is complete and honest.

**Evidence:**

- final report;
- artifact index;
- token and cost summary;
- unresolved blockers;
- manual actions;
- proof labels;
- delivery location and fingerprint.

# 57. Angular Family and Exact-Version Resolution Policy

## 57.1 Family-oriented product input

The product accepts major families:

```text
11.x, 12.x, 13.x, ... 21.x
```

The MVP eligibility policy accepts source family `18.x` and target family `21.x`. Examples of eligible source metadata include:

- `18.0.0`;
- `18.0.7`;
- `18.1.4`;
- `18.2.0`;
- `18.2.13`.

Eligibility is determined by family and support policy, not by equality to a demonstration patch.

## 57.2 Exact source detection

The SourceAnalyzer records:

- declared `@angular/core` range;
- installed/resolved version when trustworthy;
- lockfile resolution;
- Angular CLI declared and resolved versions;
- workspace local CLI result when safely executable;
- confidence and conflict indicators.

When metadata disagree, the system does not silently choose one. It produces a version-conflict finding for human review.

## 57.3 Exact target resolution

Before each stage, the resolver determines an exact target set:

- `@angular/core` exact version;
- `@angular/cli` exact version;
- `@angular-devkit/build-angular` exact version;
- TypeScript exact compatible version/range policy;
- RxJS exact compatible version/range policy;
- Zone.js policy;
- Angular Material/CDK exact versions when present;
- Node.js and npm exact executable versions.

The resolution uses:

1. approved family target;
2. compatibility catalogue;
3. package-registry metadata captured at resolution time;
4. company package allowlist;
5. private-package constraints;
6. stage input actual state;
7. previous fixture evidence.

## 57.4 Resolution lock

The resolution artifact contains:

```json
{
  "catalogue_version": "angular-compat-2026-07-14",
  "resolution_timestamp": "2026-07-14T09:00:00+01:00",
  "source": {
    "family": "18.x",
    "exact_core": "18.2.13",
    "exact_cli": "18.2.14"
  },
  "target": {
    "family": "19.x",
    "exact_core": "19.2.17",
    "exact_cli": "19.2.18"
  },
  "runtime_profile_id": "node-22.12.0-npm-10.9.0",
  "registry_snapshot_checksum": "sha256:...",
  "resolution_checksum": "sha256:..."
}
```

Numbers above are illustrative and must come from the approved catalogue and registry snapshot at runtime.

## 57.5 Patch drift prevention

After approval:

- ranges are not re-resolved;
- registry updates do not alter the stage;
- a new exact version requires a StageExecutionPlan revision;
- the revision invalidates dependent approvals;
- the prior plan remains in history;
- the user approves the revised package.

## 57.6 Version verification after update

A stage does not pass because `package.json` contains a desired range. Verification must use multiple evidence sources where possible:

- package manifest;
- lockfile;
- package-manager resolution tree;
- local Angular CLI version output;
- installed package metadata;
- builder package versions.

Mismatch is a failed core gate.

# 58. Historical Compatibility Catalogue Contract

## 58.1 Purpose

The long-term product target covers Angular 11+ even when official support windows have expired. The factory therefore requires an internal historical catalogue backed by fixtures and evidence.

## 58.2 Support levels

```text
officially_supported
historical_validated
historical_experimental
blocked
```

**Officially supported:** The stage falls within current official support and has current compatibility policy.

**Historical validated:** Official support may have expired, but the exact stage profile and commands have passed the internal fixture suite.

**Historical experimental:** A plausible historical route exists, but runtime fixture evidence is incomplete. Mandatory feasibility approval and prominent risk reporting are required.

**Blocked:** Required runtime, package, registry, builder, or evidence is unavailable or prohibited.

## 58.3 Catalogue entry

```yaml
stage_family: angular-15.x-to-16.x
support_level: historical_validated
source_constraints:
  angular_core: ">=15.0.0 <16.0.0"
target_constraints:
  angular_core: ">=16.0.0 <17.0.0"
runtime_profiles:
  - profile_family: node-18-npm-9
package_manager: npm
command_template_ids:
  - angular-update-core-cli
validation_policy_id: angular-stage-standard-v2
fixture_suite:
  status: passed
  last_run: 2026-06-30
  artifact_refs:
    - artifact://fixtures/angular-15-to-16/report
known_risks:
  - custom-webpack-builders
  - legacy-karma-configuration
policy_version: 4
```

## 58.4 Catalogue governance

A catalogue entry changes only through:

- official-source review;
- internal fixture run;
- review of known migration notes;
- security and company-policy review;
- versioned approval;
- publication of a new catalogue checksum.

The LLM may explain catalogue data but cannot create or promote support status.

# 59. Detailed Source, Baseline, and Analysis Contracts

## 59.1 Source intake sequence

```text
canonicalize paths
→ detect links/junctions
→ verify read access
→ classify Angular workspace
→ detect source family and exact metadata
→ validate target path
→ measure disk requirement
→ create preflight artifact
→ human source approval
```

## 59.2 Path and link controls

The PathPolicy service must:

- use canonical absolute paths;
- normalize Windows drive and case behavior;
- reject source/target equality;
- reject unsafe nesting;
- reject internal data root as user source or target;
- inspect symlinks and junctions;
- prevent copy traversal outside source root;
- detect excessively long paths before mutation;
- record excluded or rejected links;
- avoid following unknown reparse points by default.

## 59.3 Source fingerprint

The source fingerprint is generated from a versioned canonicalization policy. It includes migration-relevant relative paths, file sizes, and content hashes. Generated directories are excluded, but exclusions are explicit and recorded.

Default exclusions:

- `node_modules`;
- `dist`;
- `.angular/cache`;
- `coverage`;
- `.git/objects` where Git metadata is captured separately;
- product temporary files.

## 59.4 Baseline execution workspace

The original source is never used as a command working directory. Baseline commands execute in a product-owned baseline sandbox derived from the immutable snapshot.

This is important because installation may mutate:

- lockfiles;
- package-manager metadata;
- caches;
- generated configuration;
- native package state.

## 59.5 Baseline status model

```text
machine_proven_passed
machine_proven_with_known_failures
blocked_by_environment
not_configured
user_attested_only
unknown
```

## 59.6 Known baseline failure policy

The project must choose one of two explicit policies per run:

### Strict clean baseline

All required baseline tests and builds must pass before migration starts.

### Qualified known-failure baseline

The user may approve known failures when company policy allows. Every failure receives a stable fingerprint. Stage acceptance then requires:

- no new failure fingerprints;
- no changed known-failure fingerprint unless explicitly approved;
- no increased count for a known failure group;
- no severity increase;
- complete disclosure in final reporting.

The stage status is not represented as a clean pass. Use a qualified status such as:

```text
passed_with_approved_baseline_failures
```

## 59.7 Analysis workstreams

Read-only analysis may run in parallel after snapshot approval:

- workspace topology;
- exact versions;
- runtime discovery;
- dependency inventory;
- private package detection;
- lifecycle-script audit;
- builder and target inventory;
- test/lint inventory;
- routes, guards, resolvers;
- backend API and environment integration;
- auth/interceptor/security-sensitive files;
- forms and validation;
- UI libraries and themes;
- state management;
- SSR/PWA/i18n;
- source risk hotspots;
- secrets indicators.

Parallel tasks must not write overlapping artifacts. Each produces an immutable result and a deterministic summary.

## 59.8 AI Analysis Agent

The Analysis Agent receives deterministic findings and may:

- explain implications;
- identify likely migration risks;
- group related findings;
- draft human-readable analysis;
- flag missing evidence.

It may not:

- alter deterministic facts;
- declare support status;
- choose exact versions;
- execute commands;
- modify files;
- bypass analysis approval.

## 59.9 Analysis package

The approval package includes:

- fact inventory;
- AI interpretation;
- risk register;
- evidence confidence;
- unsupported topology findings;
- dependency risks;
- builder decisions required;
- baseline findings;
- unresolved questions;
- recommended feasibility outcome.

# 60. Planning Package and Stage Plan Contract

## 60.1 Planning responsibilities

The deterministic planning layer owns:

- route generation;
- stage IDs;
- compatibility-catalogue bindings;
- runtime candidates;
- command-template resolution;
- validation policy;
- sandbox structure;
- approval gates;
- recovery boundaries;
- artifact expectations.

The Planning Agent may create the explanatory narrative but cannot invent executable truth.

## 60.2 MigrationPlan structure

```yaml
plan_id: plan-run-001-v1
run_id: run-001
source:
  family: 18.x
  exact_core: 18.2.13
target:
  family: 21.x
route:
  - angular-18.x-to-19.x
  - angular-19.x-to-20.x
  - angular-20.x-to-21.x
mode: strict_compatibility
catalogue_version: angular-compat-2026-07-14
stage_plan_strategy: resolve_exact_before_each_stage
approval_policy: mandatory-human-v1
repair_policy: proposer-reviewer-human-v1
command_policy: structured-registry-v1
artifact_policy: immutable-stage-scoped-v1
final_assurance_policy: clean-final-candidate-v1
```

## 60.3 StageExecutionPlan extended schema

```yaml
stage_plan_id: stage-plan-18-to-19-v1
stage_id: stage-18-to-19
plan_version: 1
input:
  sandbox_path_alias: run://run-001/stage-18-to-19/workspace
  fingerprint: sha256:...
versions:
  source_family: 18.x
  source_exact: 18.2.13
  target_family: 19.x
  target_exact: 19.2.x-resolved-value
runtime:
  execution_profile_id: profile-node22-npm10
  compatibility_resolution_id: resolution-001
commands:
  bootstrap_install:
    command_id: npm-ci-bootstrap
    argv: [npm.cmd, ci, --ignore-scripts=false]
  update:
    command_id: angular-update-exact
    argv: [npx.cmd, -p, "@angular/cli@<exact>", ng, update, "@angular/cli@<exact>", "@angular/core@<exact>", --interactive=false]
  target_verify:
    command_id: angular-version-verify
  final_install:
    command_id: npm-ci-final
  builds:
    - command_id: npm-script-build-production
  tests:
    - command_id: npm-script-test-ci
  lint:
    - command_id: npm-script-lint
      conditional: true
validation:
  policy_id: angular-stage-standard-v2
  baseline_comparison_required: true
  route_comparison_required: true
  backend_comparison_required: true
build_system_decision_id: builder-decision-001
forbidden_actions:
  - force_dependency_resolution
  - optional_standalone_migration
  - optional_signals_migration
  - optional_control_flow_migration
  - optional_zoneless_migration
approval_bindings:
  stage_start_gate: gate-...
  transformation_gate: gate-...
  validation_gate: gate-...
  stage_completion_gate: gate-...
```

## 60.4 Plan revision

A revision is required when changing:

- exact version;
- runtime executable;
- package manager;
- command template or arguments;
- builder decision;
- required test/build target;
- validation policy;
- repair budget;
- sandbox path;
- compatibility catalogue version.

Revision flow:

```text
create new immutable plan version
→ calculate checksum
→ mark dependent approvals stale
→ present diff from previous plan
→ human approval
→ activate new plan version
```

## 60.5 Planning quality checks

Before plan approval, verify:

- every stage increments exactly one major;
- Stage 1 exact versions are resolved;
- later stages have approved resolution rules;
- every command references a registered command template;
- every command has a timeout and network policy;
- every mutation points to a stage sandbox alias;
- all required gates exist;
- all expected artifacts have stage-scoped destinations;
- forbidden modernization is explicit;
- rollback and recovery actions are defined;
- final assurance and delivery are included.

# 61. Stage Sandbox and Storage Lifecycle

## 61.1 Physical sandbox rule

Each major transition owns a dedicated physical writable sandbox. The sandbox is not shared with another stage and is never the original source.

For the first MVP:

```text
source-snapshot/
→ stages/angular-18-to-19/workspace/
→ stages/angular-19-to-20/workspace/
→ stages/angular-20-to-21/workspace/
→ final-assurance/workspace/
→ delivery/candidate/
```

## 61.2 Canonical internal layout

```text
data/
└── runs/
    └── <run-id>/
        ├── run.json
        ├── source/
        │   ├── snapshot/
        │   ├── manifest.json
        │   └── fingerprint.json
        ├── baseline/
        │   ├── workspace/
        │   └── artifacts/
        ├── analysis/
        ├── planning/
        ├── stages/
        │   ├── 001-angular-18-to-19/
        │   │   ├── workspace/
        │   │   ├── input/
        │   │   ├── commands/
        │   │   ├── transform/
        │   │   ├── validation/
        │   │   ├── failures/
        │   │   ├── repairs/
        │   │   │   ├── attempt-001/
        │   │   │   ├── attempt-002/
        │   │   │   └── attempt-003/
        │   │   ├── approvals/
        │   │   ├── checkpoint/
        │   │   └── output/
        │   ├── 002-angular-19-to-20/
        │   └── 003-angular-20-to-21/
        ├── final-assurance/
        │   ├── workspace/
        │   └── artifacts/
        ├── delivery/
        │   ├── candidate/
        │   ├── manifest.json
        │   └── publication.json
        ├── report/
        └── quarantine/
```

## 61.3 Sandbox creation

A sandbox is created only after stage-start approval.

Creation protocol:

1. verify approved input fingerprint;
2. verify destination absent or safely disposable;
3. copy from the approved clean source boundary;
4. apply link and exclusion policy;
5. verify required files;
6. generate sandbox manifest;
7. compute input fingerprint;
8. compare with expected stage input;
9. register artifacts;
10. transition stage to `workspace_ready`.

## 61.4 Copy-forward protocol

Only a completed, cleaned, fingerprinted, and human-approved stage output can become the next stage input.

```text
stage validation passed
→ human validation approval
→ cleanup
→ cleanliness verification
→ output fingerprint
→ human stage-completion approval
→ create next stage sandbox from approved output
→ verify next input fingerprint
```

## 61.5 Copy optimization

The implementation may use:

- streaming file copies;
- platform-supported copy-on-write or reflink;
- hard-link optimization only when mutation isolation remains guaranteed;
- incremental manifest comparison;
- parallel hashing with deterministic ordering.

Optimization must never compromise physical stage isolation. If a hard-link or reflink implementation can cause cross-stage mutation, it is forbidden.

## 61.6 Generated-directory policy

Generated directories are excluded from copy-forward by default:

- `node_modules`;
- `.angular/cache`;
- `dist`;
- `coverage`;
- temporary test output;
- product temporary files;
- package-manager transient state when safe.

The lockfile is preserved. The global npm cache is not wiped.

## 61.7 Cleanup verification

Cleanup success is not inferred from command success. The verifier checks:

- excluded directories are absent;
- required source/config files exist;
- lockfile exists when required;
- no product patch temporary files remain;
- no active command holds workspace files;
- workspace manifest can be generated;
- output fingerprint is stable across repeated calculation;
- no link escapes the sandbox.

## 61.8 Quarantine

Interrupted or integrity-failed workspaces are moved or marked under `quarantine/` when practical. Quarantined workspaces are read-only for normal workflow and retained for forensic review according to retention policy.

## 61.9 Optional product-owned Git

Git is not required for source eligibility, but the product may initialize a local internal repository inside stage workspaces to improve:

- diff generation;
- patch applicability checks;
- rollback of the last repair;
- commit-level stage evidence.

Internal Git must remain an implementation aid. The authoritative evidence still includes filesystem fingerprints and Artifact Store records.

# 62. Detailed Command and Process Execution Contract

## 62.1 Command registry

Every executable action is referenced by a registered command template. The UI, LangGraph, and LLMs never submit raw shell strings.

A registry entry defines:

- command template ID;
- executable resolver;
- argument schema;
- allowed phases;
- working-directory policy;
- environment allowlist;
- network profile;
- timeout;
- cancellation behavior;
- mutation classification;
- recovery category;
- redaction rules;
- allowed exit codes;
- parser family;
- artifact policy.

## 62.2 Structured command request

```json
{
  "command_template_id": "angular-update-exact-v1",
  "run_id": "run-001",
  "stage_id": "stage-18-to-19",
  "execution_plan_id": "stage-plan-v1",
  "execution_profile_id": "profile-node22-npm10",
  "workspace_alias": "stage://stage-18-to-19/workspace",
  "arguments": {
    "cli_version": "<approved-exact-version>",
    "core_version": "<approved-exact-version>",
    "interactive": false
  },
  "expected_workspace_fingerprint": "sha256:...",
  "state_version": 71,
  "idempotency_key": "sha256:..."
}
```

## 62.3 Command authorization

Before execution:

1. load the approved StageExecutionPlan;
2. validate template membership;
3. resolve the executable through ExecutionProfile;
4. validate every argument against schema and allowlist;
5. validate current workflow step;
6. validate approval status;
7. validate workspace alias and canonical path;
8. validate current fingerprint if required;
9. validate network and environment policy;
10. acquire command ownership;
11. persist `COMMAND_QUEUED` and `COMMAND_STARTED`;
12. launch through ProcessController.

## 62.4 Direct process invocation

Prefer structured process invocation with `shell=false`. On Windows, executable resolution may use approved `.exe` or `.cmd` paths. PowerShell is not used as a generic wrapper unless a specific allowlisted command template requires it.

Forbidden patterns:

- concatenating user input into a shell string;
- `cmd /c` with arbitrary content;
- `powershell -Command` with arbitrary content;
- inherited unrestricted environment;
- working directory outside the stage sandbox;
- unbounded command duration;
- invisible stdin prompts.

## 62.5 Environment materialization

The ExecutionProfile builds an explicit environment from:

- approved base environment keys;
- selected Node and npm paths;
- proxy and certificate settings;
- job/stage identifiers;
- temporary directory under the product data root;
- sanitized package-manager config references;
- optional scoped cache path.

Secrets are injected only into the process environment when needed and are not persisted in plain-text artifacts.

## 62.6 Output capture

The executor captures:

- full stdout;
- full stderr;
- combined ordered stream when possible;
- timestamps;
- exit code;
- process ID and process group/job object identity;
- truncation status for UI streams;
- raw artifact locations;
- redacted preview for UI;
- npm debug log discovery.

The UI may receive incremental log chunks, but the final authoritative logs are immutable artifacts.

## 62.7 Interactive prompt handling

Commands must be configured non-interactively whenever supported. If an unexpected prompt occurs:

1. detect no-progress or prompt pattern;
2. capture the prompt;
3. stop or safely terminate the command;
4. mark `interactive_decision_required`;
5. preserve partial evidence;
6. reconstruct the stage if the command was mutating;
7. create a plan revision or explicit decision;
8. rerun from a proven boundary.

The backend must never guess a strategic prompt answer.

## 62.8 Process-tree cancellation

The ProcessController abstracts platform behavior.

Cancellation protocol:

- persist cancel request;
- stop scheduling new commands;
- send graceful termination to the process tree;
- wait a configured grace period;
- force terminate remaining descendants;
- close stream readers;
- persist final output and cancellation reason;
- classify workspace trust based on command mutation category;
- transition run and stage.

## 62.9 Command mutation categories

```text
read_only
reconstructible_copy
validation_only
source_mutating
metadata_mutating
patch_apply
publication
```

The category controls interruption recovery.

## 62.10 Network profiles

Recommended profiles:

- `none` — no network expected;
- `registry_read` — approved package registries only;
- `documentation_read` — approved documentation endpoints;
- `llm_gateway` — Azure OpenAI endpoint only;
- `company_proxy` — company-managed network route.

The MVP may not provide complete network isolation on all local operating systems, but policy and evidence must still record the intended profile and actual configuration.

## 62.11 Command result

```json
{
  "command_execution_id": "cmd-001",
  "status": "failed",
  "exit_code": 1,
  "started_at": "...",
  "ended_at": "...",
  "stdout_artifact_id": "artifact-stdout",
  "stderr_artifact_id": "artifact-stderr",
  "debug_artifact_ids": ["artifact-npm-debug"],
  "command_start_fingerprint": "sha256:...",
  "command_end_fingerprint": "sha256:...",
  "backend_instance_id": "backend-01",
  "process_tree_terminated": true,
  "recovery_category": "source_mutating"
}
```

# 63. Detailed Validation and Parity Matrix

## 63.1 Validation principles

Validation proves specific things. It must not overclaim.

- exact-version verification proves package/runtime identity;
- clean installation proves dependency reproducibility under the selected environment;
- build proves compilation and bundling for configured targets;
- tests prove only the behavior covered by those tests;
- route comparison proves structural route evidence;
- backend comparison proves structural integration evidence;
- manual browser checks provide human-observed runtime evidence;
- none of these alone prove complete semantic equivalence.

## 63.2 Mandatory stage gates

| Gate | Required outcome | Failure consequence |
|---|---|---|
| Target family/exact version | Match approved stage plan | Stage failure |
| Package/lockfile consistency | Valid and reproducible | Dependency failure |
| Final clean install | Pass | Stage failure |
| Required builds | Pass | Stage failure |
| Complete configured required tests | Pass or qualified baseline policy | Stage failure |
| No unvalidated applied repair | True | Cannot complete |
| Cleanup | Pass | Cannot copy forward |
| Cleanliness verification | Pass | Cannot copy forward |
| Output fingerprint | Persisted | Cannot complete |

## 63.3 Build matrix

The plan identifies all required Angular CLI projects and configurations. Examples:

- primary application production build;
- additional application builds when within support scope;
- library builds;
- SSR build;
- prerender;
- service worker/PWA build;
- i18n configurations;
- custom approved build targets.

Unsupported targets are reported as blockers or explicit manual/deferred items; they are not silently omitted.

## 63.4 Test policy

Tests are discovered from:

- `angular.json` targets;
- package scripts;
- project configuration;
- known test config files;
- user-approved command selection.

The complete required suite must run after every stage and after any repair that invalidates test evidence.

Test-focused quick feedback may run first, but cannot replace the full suite.

## 63.5 Test-change governance

Changing tests is high risk when the change modifies expected behavior. Rules:

- test infrastructure compatibility fixes may be proposed;
- imports, setup, runner config, and deprecated API adjustments may be proposed with evidence;
- deleting tests is blocked by default;
- disabling tests is blocked by default;
- weakening assertions is blocked by default;
- changing expected values requires explicit strategic approval and business justification;
- snapshots must not be blindly regenerated;
- Reviewer must identify whether a test change hides a regression.

## 63.6 Route parity evidence

Capture and compare:

- paths;
- redirects;
- wildcard routes;
- lazy-loading declarations;
- components/modules loaded;
- guards;
- resolvers;
- route data and title where detectable;
- authorization indicators.

Classifications:

```text
unchanged
expected_mechanical_change
approved_behavior_sensitive_change
unexpected_sensitive_change
not_proven
```

## 63.7 Backend-integration evidence

Capture and compare:

- environment API roots;
- proxy rules;
- HTTP service endpoint literals;
- methods;
- request builders;
- response mappers;
- interceptors;
- auth headers;
- token/cookie handling;
- error mapping;
- feature flags;
- guards/resolvers using backend data.

Changes to these files are at least medium risk and often high risk.

## 63.8 UI and visual parity

The first MVP excludes automated browser and visual-regression tools due to company policy. Therefore:

- visual parity is `manual_validation_required`;
- browser smoke is `manual_validation_required`;
- a structured checklist is generated;
- screenshots may be attached manually;
- routes and critical flows are prioritized by risk;
- manual evidence remains separate from automated evidence.

## 63.9 Security and quality assurance

Excluded company tools are reported honestly:

- external vulnerability scan: `deferred_company_tool_required`;
- SAST/quality scan: `deferred_company_tool_required`;
- browser E2E: `manual_validation_required` unless company-approved tooling is later added.

## 63.10 Assurance dimensions

```json
{
  "technical_upgrade_status": "passed",
  "functional_parity_status": "manual_validation_required",
  "security_assurance_status": "deferred_company_tool_required",
  "quality_assurance_status": "deferred_company_tool_required",
  "delivery_readiness": "ready_with_disclosed_manual_items"
}
```

## 63.11 Final assurance

After the last stage is approved:

1. create a new final-assurance sandbox from the approved final output;
2. ensure generated directories are absent;
3. run exact clean frozen install;
4. verify exact versions;
5. run all production builds;
6. run complete configured tests;
7. run conditional approved targets;
8. repeat route/backend comparisons;
9. verify source integrity;
10. generate final assurance summary;
11. obtain final-assurance approval.

Only then may delivery preparation begin.

# 64. Two-LLM Repair Governance — Expanded Contract

## 64.1 Repair entry criteria

The repair system starts only from a real persisted `FailureEvidence` object. It does not proactively rewrite code before official migration tooling and validation produce a failure.

Repair is appropriate for:

- TypeScript errors;
- Angular template errors;
- migration configuration errors;
- dependency conflicts with evidence;
- builder/config compatibility errors;
- test setup or application defects caused by the migration;
- limited code compatibility changes.

Repair is not appropriate for:

- missing Node installation;
- registry credentials;
- network outage;
- disk full;
- permission failure;
- unsupported topology;
- unknown business behavior requiring human design;
- prohibited modernization.

## 64.2 FailureEvidence extended schema

```json
{
  "failure_id": "failure-001",
  "run_id": "run-001",
  "stage_id": "stage-18-to-19",
  "phase": "build",
  "command_execution_id": "cmd-build-001",
  "classification": "CODE_OR_CONFIG_REPAIR",
  "classification_confidence": 0.97,
  "origin": "migration_caused",
  "tool": "angular-compiler",
  "primary_code": "NG8002",
  "diagnostics": [
    {
      "code": "NG8002",
      "file": "src/app/example.component.html",
      "line": 12,
      "message": "...",
      "fingerprint": "sha256:..."
    }
  ],
  "stdout_artifact_id": "...",
  "stderr_artifact_id": "...",
  "workspace_fingerprint": "sha256:...",
  "changed_files": ["..."],
  "baseline_comparison": "new_failure",
  "created_at": "..."
}
```

## 64.3 Deterministic parser layer

Parsers extract facts before the LLM:

- npm `ERESOLVE`, `E401`, `E403`, `ETIMEDOUT`, `EACCES`;
- TypeScript diagnostic codes and locations;
- Angular compiler/template diagnostics;
- test names, assertions, stack traces;
- builder/configuration errors;
- generic process failures.

The parser does not invent root cause. It produces normalized evidence and top-level routing.

## 64.4 RepairContextPack construction

Selection order:

1. exact diagnostic files and lines;
2. component/template/style relationship;
3. failing tests and stack-trace files;
4. direct imports and declarations;
5. files changed by the current stage;
6. package/config files relevant to the failure class;
7. previous repair attempts;
8. model-requested bounded expansion.

Every included item records:

- relative path;
- selection reason;
- full-file checksum;
- excerpt checksum if excerpted;
- line range;
- redaction record;
- workspace fingerprint.

## 64.5 Proposer contract

The Proposer alone may return a diff.

Allowed statuses:

```text
candidate
insufficient_context
not_repairable
```

Candidate requirements:

- evidence-backed root cause;
- minimal compatibility fix;
- unified diff;
- changed-file list;
- risk notes;
- validation-impact classification;
- no forbidden modernization;
- no command execution request;
- no approval claim.

## 64.6 Reviewer contract

Allowed decisions:

```text
accept
request_revision
reject
insufficient_context
```

The Reviewer checks:

- evidence alignment;
- minimality;
- API existence;
- dependency compatibility;
- strict-parity risk;
- test-change safety;
- forbidden modernization;
- security-sensitive files;
- whether the proposal hides rather than fixes the failure;
- whether more context is necessary.

The Reviewer schema must not include a patch field.

## 64.7 Repair budgets

| Counter | Default limit | Meaning |
|---|---:|---|
| Transport retries | 2 | Provider/network retry; not semantic attempt |
| Invalid structured-output regeneration | 1 | Schema repair; not semantic attempt |
| Context expansions | 1 per attempt | Backend-governed extra evidence |
| Reviewer revision cycles | 2 per attempt | Proposer revises same candidate lineage |
| Applied semantic attempts | 3 per failure chain | Human-approved patches actually applied |

Limits are policy values and may be lowered for high-risk areas.

## 64.8 No-progress controls

The system calculates:

- normalized error-set fingerprint;
- primary failure fingerprint;
- proposed patch fingerprint;
- changed-file set;
- error count and severity delta.

Stop early when:

- the same patch is proposed again;
- a semantically equivalent patch is proposed;
- the error set is unchanged after an applied attempt;
- a new higher-severity error appears;
- the proposal expands scope without evidence;
- the same root-cause hypothesis failed twice;
- repair budget is exhausted.

## 64.9 Proposal persistence

After Reviewer acceptance:

- persist exact Proposer diff;
- compute SHA-256;
- persist pre-apply workspace fingerprint;
- persist model and prompt provenance;
- persist Reviewer decision;
- persist changed-file risk;
- create human approval gate;
- expose the exact persisted diff.

## 64.10 Apply safety

The backend reloads the proposal and verifies:

- valid proposal status;
- human decision;
- idempotency;
- diff checksum;
- current workspace fingerprint;
- path confinement;
- patch syntax;
- changed files match proposal;
- applicability dry run;
- risk approval;
- plan and policy versions.

The frontend cannot edit and resend the authoritative patch.

## 64.11 Patch preflight

After Apply and before expensive validation, run deterministic checks where feasible:

- TypeScript parse/diagnostic on changed files;
- Angular template diagnostics;
- import resolution;
- referenced package existence;
- no phantom symbols;
- no unapproved dependency additions;
- changed-path and risk reclassification.

Preflight is not authoritative stage validation.

## 64.12 Normal-pipeline continuation

Resume from the earliest invalidated boundary:

- package/lockfile change → final install, build, full tests;
- Angular configuration/builder change → final install if needed, build, full tests, comparisons;
- source/template change → build, full tests, comparisons;
- test-only infrastructure change → full tests and any invalidated build proof;
- uncertainty → choose the earlier safer boundary.

## 64.13 Failed validation

A failed applied repair produces:

- new command evidence;
- new FailureEvidence;
- error delta;
- attempt outcome;
- rollback or reconstruction decision;
- new repair attempt only when budget remains.

# 65. Persistence, Artifact, and Reconciliation Protocol

## 65.1 SQLite ownership

FastAPI persistence services are the only application writers. LangGraph nodes, CLI, frontend, and worker helpers use application repositories rather than direct ad hoc connections.

## 65.2 Recommended tables

- `migration_runs`;
- `migration_stages`;
- `workflow_steps`;
- `approval_gates`;
- `user_decisions`;
- `transitions`;
- `events`;
- `execution_profiles`;
- `compatibility_resolutions`;
- `migration_plans`;
- `stage_execution_plans`;
- `command_executions`;
- `failures`;
- `failure_diagnostics`;
- `repair_chains`;
- `repair_attempts`;
- `llm_invocations`;
- `review_decisions`;
- `repair_proposals`;
- `workspace_fingerprints`;
- `artifacts`;
- `worker_leases`;
- `delivery_records`;
- `usage_cost_records`.

## 65.3 Transaction rules

- enable foreign keys;
- use WAL on local storage;
- use short transactions;
- use optimistic aggregate versions;
- use unique constraints for idempotency keys;
- append transition/event records in the same transaction as state change;
- never stream logs from an open DB transaction;
- never call an LLM from an open transaction;
- never hash or copy large trees from an open transaction.

## 65.4 Artifact metadata

```json
{
  "artifact_id": "artifact-001",
  "run_id": "run-001",
  "stage_id": "stage-18-to-19",
  "step_id": "validation-build",
  "failure_id": null,
  "repair_attempt_id": null,
  "artifact_type": "build_report",
  "relative_path": "stages/001.../validation/build-report.json",
  "sha256": "...",
  "size_bytes": 12450,
  "schema_version": "build-report-v2",
  "sensitivity": "internal",
  "immutable": true,
  "created_at": "..."
}
```

## 65.5 Artifact access

The API accepts artifact IDs, not arbitrary file paths. The service resolves the registered relative path under the run data root and verifies containment before reading.

## 65.6 Reconciliation

Startup and maintenance reconciliation detects:

- temporary artifact files;
- finalized files without DB records;
- DB records with missing files;
- checksum mismatches;
- unregistered stage workspaces;
- stale worker leases;
- commands marked running under an old backend instance;
- delivery candidates without publication records.

Inconsistencies are reported and quarantined. They are never silently repaired by inventing evidence.

## 65.7 Retention

Retention policy distinguishes:

- active run data;
- successful run evidence;
- failed/cancelled forensic workspaces;
- raw sensitive logs;
- redacted human-readable reports;
- LLM raw responses;
- final deliverables.

Deletion is an explicit controlled operation and never part of ordinary stage cleanup.

# 66. Event, SSE, and Frontend Synchronization Contract

## 66.1 Event categories

### Run events

```text
RUN_CREATED
RUN_PREFLIGHT_STARTED
RUN_WAITING_APPROVAL
RUN_STARTED
RUN_CANCEL_REQUESTED
RUN_CANCELLED
RUN_INTERRUPTED
RUN_FAILED
RUN_COMPLETED
```

### Approval events

```text
APPROVAL_GATE_CREATED
APPROVAL_SUBMITTED
APPROVAL_ACCEPTED
APPROVAL_REJECTED
APPROVAL_MODIFICATION_REQUESTED
APPROVAL_MARKED_STALE
```

### Stage events

```text
STAGE_CREATED
STAGE_PLAN_LOCKED
STAGE_SANDBOX_READY
STAGE_STARTED
STAGE_TRANSFORMATION_COMPLETED
STAGE_VALIDATION_COMPLETED
STAGE_WAITING_APPROVAL
STAGE_CLEANUP_COMPLETED
STAGE_COMPLETED
STAGE_FAILED
```

### Command events

```text
COMMAND_QUEUED
COMMAND_STARTED
COMMAND_OUTPUT_AVAILABLE
COMMAND_SUCCEEDED
COMMAND_FAILED
COMMAND_CANCELLED
COMMAND_INTERRUPTED
```

### Repair events

```text
FAILURE_CAPTURED
FAILURE_CLASSIFIED
REPAIR_CONTEXT_CREATED
PROPOSER_COMPLETED
REVIEWER_ACCEPTED
REVIEWER_REQUESTED_REVISION
REVIEWER_REJECTED
REPAIR_PROPOSAL_READY
REPAIR_APPLY_STARTED
REPAIR_APPLIED
PATCH_PREFLIGHT_COMPLETED
REPAIR_VALIDATION_COMPLETED
REPAIR_ATTEMPT_LIMIT_REACHED
```

### Delivery events

```text
FINAL_ASSURANCE_STARTED
FINAL_ASSURANCE_COMPLETED
DELIVERY_CANDIDATE_READY
PUBLICATION_STARTED
PUBLICATION_COMPLETED
REPORT_READY
```

## 66.2 Event envelope

```json
{
  "event_id": 481,
  "schema_version": "migration-event-v2",
  "event_type": "STAGE_WAITING_APPROVAL",
  "run_id": "run-001",
  "stage_id": "stage-18-to-19",
  "state_version": 75,
  "occurred_at": "...",
  "actor": "transition-service",
  "payload": {
    "gate_id": "gate-validation",
    "artifact_refs": ["artifact-stage-validation-summary"]
  }
}
```

## 66.3 SSE delivery

The SSE endpoint:

- authenticates the user;
- accepts `Last-Event-ID`;
- replays durable events after that sequence;
- emits heartbeat events;
- streams new durable events;
- optionally signals new log chunks;
- closes or instructs snapshot reload on unrecoverable gaps.

## 66.4 Frontend store

The Next.js/React frontend maintains a projection store keyed by run ID. It may optimistically show a request as pending, but never changes authoritative lifecycle status until the backend returns or emits the new state version.

## 66.5 Duplicate and out-of-order handling

The client:

- rejects events with an already applied event ID;
- detects gaps;
- applies only increasing state versions;
- reloads full state after schema mismatch;
- does not infer completion from log text;
- does not move one stage based on another stage's event.

## 66.6 Log viewer

The log viewer supports:

- stage and command filters;
- stdout/stderr distinction;
- live tail;
- pause without stopping backend streaming;
- search;
- redacted display;
- link to immutable full artifact;
- indication of dropped transient UI chunks.

# 67. API Payload and Error Contract

## 67.1 General API rules

- version APIs under `/api/v1`;
- use Pydantic v2 models;
- return stable machine-readable error codes;
- include correlation ID;
- include current state version on conflicts;
- require idempotency keys for mutating controls;
- never expose internal absolute artifact paths unnecessarily;
- separate synchronous request acceptance from long-running execution.

## 67.2 Error envelope

```json
{
  "error": {
    "code": "STALE_STATE_VERSION",
    "message": "The run changed since the client loaded it.",
    "correlation_id": "corr-001",
    "details": {
      "expected": 42,
      "actual": 44,
      "reload_required": true
    }
  }
}
```

## 67.3 Path validation API

```http
POST /api/v1/sources/validate-paths
```

Request:

```json
{
  "source_path": "C:\\work\\legacy-angular",
  "target_output_path": "C:\\work\\migration-output"
}
```

Response includes canonical paths, overlap checks, read/write status, link warnings, disk estimate, and eligibility for source analysis.

## 67.4 Source analysis API

```http
POST /api/v1/sources/analyze
```

This starts a read-only analysis request and returns an analysis ID. The frontend polls or subscribes to its events rather than holding one request open.

## 67.5 Run creation

```http
POST /api/v1/runs
```

Request includes:

- approved source analysis ID;
- source path;
- target path;
- target family;
- strict compatibility mode;
- selected runtime preferences;
- package-manager policy;
- user identity and idempotency key.

## 67.6 Approval API

```http
POST /api/v1/runs/{runId}/approvals/{gateId}/decisions
```

```json
{
  "decision": "approved",
  "observed_gate_version": 3,
  "observed_state_version": 72,
  "artifact_set_checksum": "sha256:...",
  "workspace_fingerprint": "sha256:...",
  "comment": "Approved after review.",
  "idempotency_key": "..."
}
```

## 67.7 Repair Apply API

```http
POST /api/v1/runs/{runId}/repair-proposals/{proposalId}/apply
```

```json
{
  "diff_checksum": "sha256:...",
  "expected_workspace_fingerprint": "sha256:...",
  "observed_state_version": 83,
  "idempotency_key": "..."
}
```

The backend does not accept raw diff content.

## 67.8 State snapshot API

```http
GET /api/v1/runs/{runId}/state
```

Response separates dimensions:

```json
{
  "run_id": "run-001",
  "state_version": 84,
  "run_status": "waiting_approval",
  "run_phase": "stage_execution",
  "active_stage_id": "stage-18-to-19",
  "stage_status": "waiting_approval",
  "current_step": "validation",
  "approval_status": "required",
  "repair_status": "not_active",
  "assurance": {
    "technical": "passed",
    "functional_parity": "manual_validation_required",
    "security": "deferred_company_tool_required",
    "quality": "deferred_company_tool_required",
    "delivery": "not_ready"
  },
  "last_event_id": 481
}
```

## 67.9 Cancellation API

Cancellation returns acceptance, not immediate completion. The UI observes subsequent command, stage, and run cancellation events.

# 68. Security Threat Model and Control Mapping

## 68.1 Threat categories

The MVP must consider:

- source-path traversal;
- target-path overwrite;
- symlink/junction escape;
- arbitrary command injection;
- malicious package lifecycle scripts;
- untrusted repository prompt injection;
- secret leakage to LLMs or UI;
- stale approval replay;
- stale repair application;
- artifact tampering;
- frontend state forgery;
- process escape and orphan descendants;
- dependency registry compromise;
- disk exhaustion;
- denial of service through huge logs or context;
- accidental source mutation;
- incomplete publication appearing successful.

## 68.2 Trust boundaries

```text
User input
→ untrusted until validated

Repository content and logs
→ untrusted data, never platform instructions

LLM output
→ untrusted proposal

Frontend state
→ non-authoritative projection

LangGraph checkpoint
→ non-authoritative execution cache

Transition Service + SQLite
→ authoritative structured state boundary

CommandExecutor
→ authoritative execution boundary

Artifact Store
→ authoritative evidence boundary after checksum registration
```

## 68.3 Path controls

- canonicalize before comparison;
- validate containment after resolution;
- reject `..` escape;
- reject absolute patch targets;
- inspect Windows reparse points;
- never accept arbitrary artifact path;
- separate user output from internal data root;
- fail closed on uncertain link behavior.

## 68.4 Command controls

- structured registry only;
- no arbitrary shell;
- executable allowlist;
- argument schema;
- environment allowlist;
- explicit cwd;
- timeout;
- process-tree ownership;
- network profile;
- command and plan checksum binding;
- approval prerequisites.

## 68.5 Lifecycle-script controls

Before `npm ci` or equivalent, inspect project scripts and known package metadata where feasible. Persist risk evidence. The local MVP cannot claim strong isolation from all package scripts; therefore it must:

- run only in a product-owned sandbox;
- minimize inherited secrets;
- use scoped credentials;
- restrict working directory;
- capture child processes;
- document network expectations;
- allow policy to block or require approval for sensitive scripts;
- describe the environment as controlled local execution, not a hardened security sandbox.

## 68.6 LLM and prompt-injection controls

Repository files, README instructions, comments, package metadata, and logs are content, not instructions. System prompts explicitly state this boundary.

LLM context is:

- selected by backend;
- bounded;
- redacted;
- provenance-tagged;
- fingerprint-bound;
- schema-constrained.

LLMs cannot:

- execute tools directly;
- fetch arbitrary files;
- approve gates;
- modify state;
- apply patches;
- reveal backend credentials.

## 68.7 Secret controls

Redact or exclude:

- Azure keys;
- bearer tokens;
- passwords;
- private registry credentials;
- secret `.npmrc` values;
- sensitive environment variables;
- cookies and tokens found in logs.

Raw local artifacts may remain sensitive and are marked accordingly. Human-readable reports use sanitized paths and values.

## 68.8 Approval replay controls

An approval is bound to current state, artifact checksum, plan version, and fingerprint. Reusing the same decision after any bound element changes is rejected.

## 68.9 Artifact integrity

- SHA-256 for immutable artifacts;
- atomic finalization;
- append-only metadata;
- startup reconciliation;
- no silent overwrite;
- report references include artifact IDs and checksums;
- final delivery manifest binds file set and fingerprint.

## 68.10 Publication controls

Final output is created under a temporary destination. After complete copy and verification, the system performs an atomic rename where supported. If atomic rename is not supported across volumes, the Delivery Service uses a fail-closed two-phase publication and does not expose the final `migrated-app` name until verification completes.

# 69. Windows and Corporate Environment Operating Profile

## 69.1 Operating assumptions

The first MVP must work on a Windows developer workstation in a corporate environment where proxy, certificate, registry, filesystem, and endpoint-security restrictions may apply.

The implementation must not assume:

- Unix shell availability;
- unrestricted internet;
- administrative privileges;
- globally installed Angular CLI;
- one globally selected Node version;
- writable system directories;
- permissive antivirus behavior;
- public npm registry access without proxy configuration.

## 69.2 Executable discovery

Discover and validate:

- `node.exe` paths and exact versions;
- `npm.cmd` associated with each Node installation;
- `npx.cmd` associated with each Node installation;
- Git executable when used;
- Python and backend runtime;
- certificate and proxy environment references.

ExecutionProfile must bind related executables from the same runtime installation. The system must not combine `node.exe` from one installation with `npm.cmd` from another unless explicitly validated.

## 69.3 Process management

Windows process-tree cancellation should use a `ProcessController` implementation capable of terminating descendants. PID alone is not sufficient for recovery because PIDs may be reused.

Persist:

- backend instance ID;
- process ID;
- process start time;
- process group/job-object metadata when available;
- command ID;
- command-start fingerprint.

## 69.4 Path behavior

Handle:

- drive letters;
- case-insensitive comparisons;
- UNC paths according to policy;
- long path support;
- invalid Windows filename characters;
- junctions;
- symbolic links;
- locked files;
- antivirus-delayed operations;
- cross-volume rename limitations.

Network shares are not supported for the SQLite database or active stage sandboxes in the first MVP.

## 69.5 Proxy and certificates

The environment analysis must capture, without exposing secrets:

- configured npm registry;
- proxy and HTTPS proxy presence;
- custom CA/certificate file references;
- strict SSL policy;
- authentication requirement;
- registry reachability;
- Azure endpoint reachability.

The product should provide actionable environment findings rather than trying to patch application code for proxy failures.

## 69.6 Private registry behavior

Private registry credentials remain outside LLM context and normal reports. Commands may receive scoped environment/config references. A 401/403 is routed to `ENVIRONMENT_OR_USER_ACTION` unless deterministic evidence proves a package metadata issue.

## 69.7 Endpoint protection and file locks

Copy, cleanup, and rename operations should use bounded retries for transient sharing violations. Repeated file locks produce a clear environment blocker with the path and owning process information when discoverable.

## 69.8 Developer diagnostics

The system health screen should display:

- backend version;
- database location and WAL status;
- data-root free space;
- detected Node/npm profiles;
- registry reachability;
- proxy/certificate status;
- Git availability;
- Azure LLM gateway configuration status;
- active run and worker lease;
- artifact reconciliation warnings.

# 70. Operational Runbooks and Failure Procedures

## 70.1 Run startup runbook

1. Start FastAPI and create a new backend instance ID.
2. Open SQLite and enable foreign keys/WAL.
3. Reconcile stale commands, leases, and artifacts.
4. Validate data-root permissions and disk threshold.
5. Load compatibility catalogue and verify checksum.
6. Validate LLM gateway configuration without exposing secrets.
7. Start SSE event delivery.
8. Resume or reconcile the active run if one exists.
9. Expose health status to the Control Tower.

## 70.2 New migration runbook

1. Validate source and output paths.
2. Analyze source read-only.
3. Create G01 approval package.
4. After approval, create immutable snapshot.
5. Verify source remains unchanged.
6. Create G02 approval package.
7. Run baseline sandbox and discovery.
8. Create G03 and G04 approval packages.
9. Resolve feasibility and support level.
10. Create G05 approval package.
11. Generate migration plan.
12. Create G06 approval package.
13. Start stage loop only after plan approval.

## 70.3 Stage failure runbook

When a command fails:

1. finalize stdout/stderr artifacts;
2. discover debug logs;
3. calculate end fingerprint where safe;
4. persist failed CommandExecution;
5. build FailureEvidence;
6. classify failure;
7. compare with baseline and prior attempts;
8. route environment, retryable external, or repair candidate;
9. transition stage to the appropriate hold or repair state;
10. notify UI through durable event.

## 70.4 Environment blocker runbook

For missing runtime, registry authentication, proxy, certificate, disk, or permission errors:

- do not invoke the Proposer for a source patch;
- preserve evidence;
- provide an actionable remediation checklist;
- wait for user action;
- rerun the failed command only after environment revalidation;
- do not consume a semantic repair attempt.

## 70.5 Repair runbook

1. Build bounded context.
2. Invoke Proposer with strict schema.
3. Validate schema and semantics.
4. If insufficient context, perform at most one governed expansion.
5. Invoke Reviewer.
6. Handle bounded revisions.
7. On accept, persist exact proposal and create G10.
8. On human Apply, verify all bindings.
9. Apply exact diff.
10. Persist post-apply fingerprint.
11. Run patch preflight.
12. Return to normal validation boundary.
13. Create G11 after validation.
14. On failure, calculate progress and either retry, rollback, reconstruct, or escalate.

## 70.6 Cancellation runbook

1. Persist `cancel_requested`.
2. Stop new graph scheduling.
3. Signal ProcessController.
4. Terminate process tree.
5. Finalize logs.
6. Classify active workspace trust.
7. Preserve or quarantine workspace.
8. verify original source integrity.
9. produce partial report.
10. transition stage and run to cancelled.

## 70.7 Backend crash recovery runbook

1. Generate new backend instance ID.
2. Find commands owned by prior instance with active status.
3. Mark them interrupted.
4. Inspect command mutation category.
5. Recompute relevant fingerprints.
6. Reconcile graph checkpoint with SQLite.
7. Reconstruct or rerun from proven boundary.
8. Keep waiting approval gates intact.
9. Resume graph only after Transition Service records recovery state.

## 70.8 Artifact mismatch runbook

When an artifact checksum fails or a registered file is missing:

- mark evidence integrity failure;
- stop dependent progression;
- quarantine affected artifact or workspace;
- attempt deterministic regeneration only when the source state is proven and operation is reproducible;
- create a new artifact rather than overwriting history;
- require reapproval of dependent gates.

## 70.9 Stale proposal runbook

When pre-apply fingerprint or checksum differs:

- mark proposal `stale`;
- do not Apply;
- preserve human decision attempt as rejected by backend integrity policy;
- create new FailureEvidence/context if the failure remains;
- require a new proposal and approval.

## 70.10 Final publication failure runbook

- do not expose partially copied output under the final name;
- preserve delivery candidate and logs;
- mark delivery failed;
- keep final stage completed and final assurance evidence intact;
- allow delivery retry after destination remediation and renewed delivery approval when policy requires.

# 71. Comprehensive Test Catalogue

## 71.1 Testing strategy

Use the highest practical stable seam:

```text
FastAPI application
+ temporary SQLite database
+ temporary product data root
+ fake CommandExecutor
+ fake Proposer and Reviewer
+ real Transition Service
+ real artifact registration
+ LangGraph adapter
```

This proves business behavior without requiring real Angular/npm execution in every test.

## 71.2 Unit tests

### Transition Service

- legal transition succeeds;
- illegal transition fails;
- stale version fails;
- missing prerequisite fails;
- missing artifact fails;
- missing approval fails;
- stale approval fails;
- idempotent retry returns original result;
- same idempotency key with different payload fails;
- state and event commit atomically.

### Compatibility Resolver

- accepts any 18.x patch for MVP source policy;
- rejects Angular 17.x for the first MVP route while preserving long-term architecture;
- generates one-major route;
- selects reusable runtime profile;
- changes profile when compatibility requires;
- blocks unavailable runtime;
- preserves catalogue version;
- exact resolution is immutable after approval.

### Command policy

- raw shell rejected;
- unregistered executable rejected;
- path escape rejected;
- forbidden argument rejected;
- stale plan rejected;
- wrong workspace rejected;
- missing approval rejected;
- allowed structured command accepted.

### Fingerprints

- deterministic ordering;
- exclusion policy versioning;
- content change changes digest;
- generated directory does not change digest when excluded;
- link escape rejected;
- full-file and excerpt checksums distinct.

### Failure parsers

- npm ERESOLVE;
- npm authentication;
- timeout;
- TypeScript diagnostic;
- Angular template diagnostic;
- test failure extraction;
- unknown generic failure.

### Repair contracts

- valid Proposer candidate;
- empty diff rejected;
- mismatched changed-file list rejected;
- path escape rejected;
- insufficient context budget;
- Reviewer diff field rejected;
- revision limit;
- invalid schema retry limit;
- repeated patch fingerprint blocked;
- no-progress rule triggers escalation.

## 71.3 Integration tests

### Source safety

- original folder unchanged after full simulated run;
- baseline executes only in product workspace;
- stage writes confined;
- target overlap rejected;
- junction escape rejected.

### Artifact lifecycle

- atomic artifact creation;
- checksum stored;
- artifact API resolves ID safely;
- orphan temporary file reconciled;
- missing file detected;
- immutable artifact not overwritten.

### SSE

- durable event emitted after transition commit;
- replay from Last-Event-ID;
- duplicate event ignored by client reducer;
- gap triggers snapshot reload;
- browser reconnect does not alter job.

### Approval

- each defined gate blocks progression;
- correct approval resumes graph;
- artifact change invalidates approval;
- plan revision invalidates approval;
- repair Apply uses persisted diff only;
- rejection routes correctly.

### Recovery

- crash during read-only step reruns;
- crash during copy deletes incomplete destination and recopies;
- crash during build with unchanged source reruns;
- crash during `ng update` reconstructs stage;
- crash before durable patch applied reconstructs;
- crash after durable patch with matching fingerprint resumes validation;
- waiting approval survives restart;
- graph checkpoint loss reconstructs from SQLite.

## 71.4 End-to-end simulated workflow

The central acceptance test simulates:

```text
18.0.x source accepted
→ snapshot
→ baseline
→ analysis approval
→ feasibility approval
→ plan approval
→ stage 18→19 start approval
→ official update command fails with NG diagnostic
→ FailureEvidence
→ Proposer candidate
→ Reviewer revision
→ revised candidate accepted
→ human Apply
→ patch preflight
→ normal build/test success
→ validation approval
→ cleanup/fingerprint
→ stage completion approval
→ copy to 19→20
→ remaining stages succeed
→ final assurance approval
→ atomic delivery approval
→ final report acceptance
```

## 71.5 Real subprocess tests

A smaller suite exercises:

- harmless stdout/stderr command;
- timeout;
- cancellation;
- process-tree termination;
- Windows `.cmd` execution;
- environment allowlist;
- working-directory confinement;
- large log handling.

## 71.6 Real Angular fixture suite

Fixtures should include:

- minimal Angular 18.0.x application;
- Angular 18.2.x application;
- routes and guards;
- forms and validators;
- HTTP interceptor and API service;
- Angular Material usage;
- known dependency conflict;
- known template compile failure after update;
- known TypeScript compatibility failure;
- known baseline failure fixture;
- custom builder fixture classified as blocked/review;
- plain-folder and Git-backed variants.

## 71.7 Security tests

- shell injection payload rejected;
- absolute patch path rejected;
- `../` patch rejected;
- symlink/junction escape rejected;
- secret redaction;
- repository prompt injection treated as data;
- stale approval replay rejected;
- stale repair replay rejected;
- arbitrary artifact path rejected;
- frontend cannot forge completion;
- hidden `--force` rejected.

## 71.8 Performance tests

Measure:

- source fingerprint time;
- physical copy time;
- artifact registration throughput;
- SSE event latency;
- SQLite write contention;
- large log streaming;
- context-pack construction;
- stage cleanup and copy-forward.

Performance optimization cannot weaken integrity checks.

# 72. Acceptance Criteria and Success Metrics

## 72.1 Product acceptance

The MVP is accepted when it can migrate a representative Angular 18.x application through 19.x, 20.x, and 21.x using physical stage sandboxes, mandatory approvals, official Angular tooling, two-LLM repair, and final clean assurance.

## 72.2 Architecture acceptance

The implementation must prove:

- LangGraph coordinates but does not directly write authoritative state;
- Transition Service rejects illegal transitions;
- SQLite state survives graph checkpoint loss;
- CommandExecutor is the only external-process path;
- Artifact Store evidence exists before steps pass;
- frontend state is a projection;
- every stage has a distinct sandbox;
- exact versions are locked before stage execution.

## 72.3 Approval acceptance

All G01–G15 gates must:

- be persisted;
- block progression;
- expose evidence;
- support approved/modification/rejected decisions as defined;
- invalidate on binding changes;
- survive restart.

## 72.4 Repair acceptance

Demonstrate:

- code/config repair;
- dependency repair classification;
- environment failure without blind patch;
- Reviewer revision cycle;
- Reviewer rejection;
- stale proposal rejection;
- path-escape rejection;
- failed repair with fresh evidence;
- no-progress early stop;
- same normal validation pipeline.

## 72.5 Delivery acceptance

- final candidate created only from approved final stage output;
- clean final install/build/tests pass;
- final assurance approved;
- delivery manifest and fingerprint generated;
- source integrity verified;
- final output published atomically;
- incomplete publication never appears as final `migrated-app`;
- report includes manual/deferred items.

## 72.6 Success metrics

Track per run and stage:

- total duration;
- active execution time;
- human waiting time;
- command count and duration;
- failure classification distribution;
- repair attempts;
- Reviewer revision count;
- proposal acceptance/rejection rate;
- first-repair validation success rate;
- repeated-patch prevention count;
- cancellation and recovery outcomes;
- copy/fingerprint duration;
- input/output/total tokens;
- estimated LLM cost;
- manual/deferred item count;
- final assurance outcome.

Do not claim productivity improvement until a manual-migration baseline exists.

# 73. Delivery Roadmap and Backlog Themes

## 73.1 Foundation theme

- repository structure;
- FastAPI/Uvicorn;
- Next.js/React/TypeScript;
- configuration;
- SQLite/SQLAlchemy/Alembic;
- Artifact Store;
- health endpoints;
- local launcher.

## 73.2 State and orchestration theme

- domain aggregates;
- Transition Service;
- state versioning;
- durable events;
- approval gates;
- LangGraph adapter;
- graph reconstruction;
- JobSupervisor;
- one-active-run lease.

## 73.3 Source and workspace theme

- path policy;
- source analysis;
- immutable snapshot;
- baseline sandbox;
- stage sandbox manager;
- copy-forward;
- cleanup;
- fingerprints;
- quarantine.

## 73.4 Compatibility theme

- Angular family normalization;
- exact version detection;
- compatibility catalogue;
- runtime inventory;
- ExecutionProfile;
- historical support status;
- exact resolution lock;
- builder decisions.

## 73.5 Execution theme

- command registry;
- CommandExecutor;
- ProcessController;
- Windows support;
- logs and redaction;
- cancellation;
- interactive prompt detection;
- registry/proxy diagnostics.

## 73.6 Baseline and analysis theme

- dependency audit;
- lifecycle-script audit;
- route inventory;
- backend-integration snapshot;
- test/lint discovery;
- analysis package;
- baseline known-failure policy.

## 73.7 Stage pipeline theme

- StageExecutionPlan;
- bootstrap install;
- exact update;
- target verification;
- transformation diff;
- final install;
- build/test/lint;
- parity evidence;
- stage approval packages.

## 73.8 Repair theme

- FailureEvidence;
- parser registry;
- C-Lite routing;
- RepairContextPack;
- Azure LLM Gateway;
- Proposer;
- Reviewer;
- proposal persistence;
- Apply safety;
- patch preflight;
- progress detection.

## 73.9 Recovery and delivery theme

- backend instance reconciliation;
- safe-boundary recovery;
- artifact reconciliation;
- final assurance;
- delivery candidate;
- atomic publication;
- final report;
- token/cost report.

## 73.10 Recommended delivery order

1. Prove state authority and source immutability before real migration execution.
2. Prove command policy and cancellation before `ng update`.
3. Prove one complete simulated stage with approvals.
4. Prove one real 18.x→19.x stage without repair.
5. Add FailureEvidence and deterministic routing.
6. Add two-LLM repair with fake models, then Azure integration.
7. Prove repair on a controlled fixture.
8. Extend through 20.x and 21.x.
9. Add final assurance and delivery.
10. Harden Windows/corporate environment behavior.

# 74. Architecture Decision Records

## ADR-001 — Use LangGraph as orchestration adapter only

**Decision:** LangGraph coordinates nodes, routing, interrupts, and graph execution. It does not own business state, approvals, command execution, or artifacts.

**Reason:** Preserve graph flexibility while avoiding competing sources of truth and unsafe execution coupling.

**Consequence:** Graph nodes remain thin and reconstructible from SQLite.

## ADR-002 — Use Transition Service as the only legal state-transition path

**Reason:** Prevent UI, graph, workers, or agents from creating contradictory states.

**Consequence:** Every transition uses optimistic versioning, prerequisites, and durable events.

## ADR-003 — Accept Angular families and resolve exact versions per stage

**Reason:** The product must accept all supported 18.x applications while maintaining reproducible execution.

**Consequence:** Family route and exact execution are separate concepts.

## ADR-004 — Use physical sandbox per major stage

**Reason:** Clear isolation, recovery boundaries, and auditability.

**Consequence:** Additional disk and copy cost accepted for MVP correctness.

## ADR-005 — Require human approval at every defined phase gate

**Reason:** The current product goal prioritizes control, evidence review, and safety.

**Consequence:** Higher human waiting time is accepted in the first MVP; auto-approval is not part of the authoritative V2.1 workflow.

## ADR-006 — Use two LLM roles for repair

**Reason:** Separate patch authorship from critique and preserve clear lineage.

**Consequence:** Additional token cost and latency are accepted; Reviewer remains non-authoring.

## ADR-007 — Use one normal validation pipeline

**Reason:** Prevent repair-specific environment divergence and duplicate logic.

**Consequence:** Applied patches resume from the earliest invalidated normal boundary.

## ADR-008 — Use SQLite plus filesystem artifacts for local MVP

**Reason:** Appropriate for one host and one active run while keeping large evidence out of the database.

**Consequence:** WAL requires local storage; distributed execution requires later migration.

## ADR-009 — Use Next.js/React frontend and SSE

**Reason:** Preserve the approved frontend stack and provide live one-way updates with durable backend state.

**Consequence:** Browser is a projection and must support replay/snapshot recovery.

## ADR-010 — Preserve strict compatibility and disable modernization by default

**Reason:** The migration objective is parity, not redesign.

**Consequence:** standalone, signals, control flow, zoneless, builder modernization, and dependency replacement require explicit separate decisions.

## ADR-011 — Angular 21.x is an approved target, not the latest version

**Reason:** Angular 22 exists, but the project scope remains the approved 18.x→21.x proof route.

**Consequence:** Documentation and UI must not label Angular 21 as latest.

## ADR-012 — Describe local runtime as controlled execution, not hardened sandbox

**Reason:** A local subprocess workspace does not provide full OS isolation from package lifecycle scripts.

**Consequence:** Maintain a WorkerRuntime abstraction for stronger future container or microVM isolation.

# 75. Final Traceability and Non-Negotiable Contract

## 75.1 Traceability matrix

| Project decision | Implemented by | Proven by |
|---|---|---|
| Angular family support | SourceAnalyzer, CompatibilityResolver | family eligibility tests |
| Exact execution versions | Compatibility catalogue, StageExecutionPlan | resolution and version-verification artifacts |
| LangGraph coordination only | LangGraph adapter | architecture and graph tests |
| Legal state transitions | Transition Service | transition tests and durable events |
| SQLite authority | persistence services | restart and checkpoint-loss tests |
| Command execution authority | CommandExecutor | command-policy tests |
| Evidence authority | Artifact Store | checksum and reconciliation tests |
| Human approval each phase | Approval Service and G01–G15 | gate-blocking tests |
| Stage sandboxes | WorkspaceManager | source-safety and stage-isolation tests |
| Two-LLM repair | Proposer/Reviewer adapters | contract and lineage tests |
| Exact backend Apply | PatchSafetyService | stale/checksum/path tests |
| Normal-pipeline reuse | Validation Service | repair continuation tests |
| Functional parity separation | assurance model | final report tests |
| Final clean assurance | FinalAssuranceService | clean candidate test |
| Atomic delivery | Delivery Service | partial publication tests |

## 75.2 Final non-negotiable rules

1. The original source is never mutated.
2. Angular source eligibility is family-based, not hardcoded to one patch.
3. Exact versions are resolved, approved, and locked before each stage.
4. Migration proceeds one major version at a time.
5. Angular 21.x is the approved MVP target, not the latest Angular release.
6. Every major transition owns a dedicated physical sandbox.
7. LangGraph coordinates workflow only.
8. LangGraph checkpoints are not authoritative business state.
9. Transition Service is the only legal state-transition path.
10. SQLite is authoritative structured state.
11. CommandExecutor is the only external-process execution path.
12. Artifact Store is authoritative evidence after checksum registration.
13. The frontend is a projection only.
14. Human approval is mandatory at every defined G01–G15 gate.
15. Approval never changes failed machine evidence into passed evidence.
16. Every approval is bound to state, artifacts, plan, and fingerprints.
17. Every mutation is confined to a product-owned sandbox.
18. Raw shell commands are forbidden.
19. User command choices are restricted to approved structured templates.
20. Official Angular tooling executes before LLM repair.
21. Optional modernization is disabled by default.
22. Build-system migration is a first-class approved decision.
23. Failures produce raw immutable evidence and deterministic classification.
24. Environment failures do not trigger blind code patches.
25. Only the Proposer authors repair diffs.
26. The Reviewer never authors or replaces a diff.
27. Human Apply or Reject is mandatory for every accepted repair.
28. The backend applies only the exact persisted proposal.
29. Patch checksum, fingerprint, path, risk, and applicability are verified.
30. Patch preflight does not replace normal validation.
31. Repair validation uses the same ExecutionProfile and normal pipeline.
32. Failed repairs create fresh FailureEvidence.
33. Repeated equivalent patches are blocked.
34. No-progress repair chains stop early and escalate.
35. Tests are not weakened merely to obtain green results.
36. Core target/install/build/test gates cannot be bypassed by approval.
37. Technical upgrade, parity, security, quality, and delivery remain separate statuses.
38. Manual and deferred checks are never reported as passed.
39. Recovery occurs only from proven boundaries.
40. Interrupted mutating commands cause reconstruction from approved input.
41. Browser disconnect never cancels the run.
42. Explicit cancellation terminates the process tree and preserves evidence.
43. Final assurance runs in a clean independent sandbox.
44. Delivery is created only from the approved final fingerprint.
45. Final publication is atomic or fail-closed.
46. The original source fingerprint is verified at completion, failure, and cancellation.
47. Reports distinguish `PROVEN`, `INFERRED`, and `NOT_PROVEN`.
48. LLM usage and cost are evidence-based or reported unavailable.
49. Compatibility, prompt, model, schema, and policy changes are versioned.
50. No future framework, agent, plugin, or service may bypass these contracts.

## 75.3 Final authoritative architecture

```text
NEXT.JS / REACT CONTROL TOWER
        │ HTTP actions + SSE projection
        ▼
FASTAPI CONTROL PLANE
        │
        ├── Approval Service
        ├── Transition Service ───────────────► SQLite authoritative state
        ├── Artifact Service ─────────────────► Filesystem authoritative evidence
        ├── LLM Gateway
        └── JobSupervisor
                │
                ▼
        LANGGRAPH ORCHESTRATION ADAPTER
                │ coordinates legal use cases only
                ▼
        APPLICATION SERVICES
        ├── SourceAnalyzer
        ├── BaselineService
        ├── CompatibilityResolver
        ├── StagePlanner
        ├── WorkspaceManager
        ├── ValidationService
        ├── FailureEvidenceBuilder
        ├── RepairOrchestrator
        ├── FinalAssuranceService
        └── DeliveryService
                │
                ▼
        COMMAND POLICY ENGINE
                │
                ▼
        ONE COMMAND EXECUTOR
                │
                ▼
        CONTROLLED LOCAL STAGE SANDBOXES
```

## 75.4 Final product statement

The Angular Migration Control Tower is an evidence-driven compatibility migration factory. It combines official Angular tooling, exact and reproducible stage execution, deterministic state and security controls, dedicated stage sandboxes, mandatory human governance, bounded two-LLM repair, independent assurance reporting, safe recovery, and atomic delivery.

The user experience should remain understandable:

```text
select source and destination
→ review and approve facts
→ review and approve plan
→ approve each controlled migration phase
→ inspect and approve repairs
→ approve final assurance
→ receive a validated migrated application and complete evidence report
```

The internal implementation must remain strict, practical, and honest: no source mutation, no hidden commands, no unreviewed patch, no false pass, no guessed resume, and no final output before the evidence proves that delivery is ready.

---

# Official External Reference Basis — Reviewed 2026-07-14

The implementation policy should be periodically revalidated against the following primary documentation:

- [Angular version compatibility](https://angular.dev/reference/versions)
- [Angular versioning and releases](https://angular.dev/reference/releases)
- [Angular Update Guide](https://angular.dev/update-guide)
- [Angular CLI `ng update`](https://angular.dev/cli/update)
- [Angular build-system migration guidance](https://angular.dev/tools/cli/build-system-migration)
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [FastAPI Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- [SQLite Write-Ahead Logging](https://sqlite.org/wal.html)
- [Azure OpenAI structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)

Reference data must be captured into versioned internal policy artifacts. The live web is not an execution-time source of truth for an already approved stage.
