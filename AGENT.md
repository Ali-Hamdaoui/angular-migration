# AGENT.md — Angular Migration Factory V2 Engineering Contract

This file is the permanent instruction source for any coding agent working in this
repository. It describes the product, the architecture contract, and the strict
engineering workflow. It complements (never replaces) the issue/specification you
are assigned.

## 1. Project overview

**Angular Migration Factory** is an enterprise migration platform that migrates
Angular applications through a governed, stage-based pipeline. The MVP reference
path is **Angular 18 → 21**; V2 generalizes it to **Angular 11 → 21**.

### V2 capability target

The platform must support:

- an **arbitrary source Angular version** (11+)
- an **arbitrary target Angular version** (≤ 21)
- **stage-by-stage adjacent-major upgrades** between source and target
- **runtime binding per stage** (Node/npm/npx + Angular CLI compatibility)
- a **compatibility catalogue** consulted by planning and validation
- **deterministic backend services** as the authority
- **LangGraph workflow orchestration**
- **failure analysis** and a **governed, human-controlled repair workflow**

### Technology stack (repository reality)

| Layer | Technology | Location |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic | `backend/app/` |
| Orchestration | LangGraph | `backend/app/orchestration/` |
| Persistence | SQLite (WAL), authoritative models | `backend/app/repositories/models/workflow.py` |
| Frontend | Next.js / React Control Tower | `frontend/src/` |
| Shared contracts | Typed API references | `shared/` |
| Artifacts | Immutable, checksum-bound filesystem store | `backend/app/artifact_store/`, artifact root from config |
| LLM | Azure OpenAI gateway (redaction, usage, cost) | `backend/app/llm_gateway/` |
| Scripts | Linux dev/validation automation | `scripts/*.sh` |

## 2. Architecture rules (strict)

These are non-negotiable. A change that violates them is rejected regardless of
test results.

- **Source of truth:** SQLite database state + persisted immutable artifacts.
  Never trust in-memory or process-local state as authoritative.
- **Workflow:** LangGraph coordinates execution, interrupts, and resume. It never
  owns business truth, command execution, approvals, evidence, or file mutation.
- **Business logic:** Owned by backend services under `backend/app/services/`
  and the deterministic components under `backend/app/components/`. Routers and
  LangGraph nodes stay thin.
- **Commands:** All external-process execution goes through the command worker
  (`backend/app/command_execution/`). Registered executable + argv, `shell=false`,
  approved workspace alias, exact execution profile, timeout, environment
  allowlist, network policy. No raw shell strings. No agent-direct execution.
- **Artifacts:** Immutable evidence. Register and finalize the SHA-256 before a
  step is persisted as passed. Never overwrite an existing artifact.
- **State transitions:** Only via the transition service
  (`backend/app/state/transition_service.py`) with optimistic concurrency
  (expected state version), idempotency keys, and leases. Never write workflow
  state directly from a router, agent, or command worker.
- **Services:** Clear ownership. Avoid duplicate services, hidden state changes,
  direct database manipulation, and bypassing existing workflow transitions.
- **External source:** Read-only. Never a command working directory or mutation
  target. All mutation happens inside an internal run workspace.
- **No transaction across I/O:** Never hold a database transaction across
  subprocesses, LLM calls, filesystem copies, approval waits, or user interaction.
- **Unconfigured dependencies:** No production mock/fallback silently replaces an
  unconfigured dependency.

### Module ownership map

| Module | Owns | Forbidden |
|---|---|---|
| `api/` | HTTP routing, input validation, service delegation | Business logic, repository access, workflow state |
| `domain/` | Canonical contracts, status vocabularies | Service logic, persistence, I/O |
| `state/` | Transition service, concurrency, idempotency, leases | HTTP routing, LLM calls |
| `events/` | Ordered event persistence, SSE emission | Workflow decisions, command execution |
| `orchestration/` | LangGraph graph wiring | Direct DB writes, command execution |
| `services/` + `components/` | Deterministic business logic | LLM-driven decisions, command internals |
| `repositories/` | Persistence models, session factory | HTTP routing, business decisions |
| `artifact_store/` | Immutable checksum-bound artifact I/O | Overwrites, path traversal |
| `command_execution/` | Structured command worker | Raw shell strings |
| `llm_gateway/` | Azure OpenAI, redaction, usage, cost | Credential exposure, LLM-driven execution |
| `preflight/`, `snapshots/`, `workspaces/`, `delivery/` | Readiness, immutable snapshots, run workspace, atomic delivery | Source mutation, premature publication |
| `frontend/` | Control Tower presentation | Workflow state machine, execution logic |

## 3. V2 migration context

V2 evolves the platform from the fixed **Angular 18 → 21** reference path to a
**flexible 11 → 21** migration factory. In practice this means:

- Source and target Angular versions become inputs, not constants.
- A migration run is a chain of **adjacent-major stages**, each a single
  `ng update` step validated before the next begins.
- Each stage resolves a **runtime binding** — the exact Node/npm/npx (and Angular
  CLI) version certified for that stage — from the installed runtime matrix.
- Runtime/version compatibility is driven by the **compatibility catalogue**, not
  hardcoded assumptions.
- Stage knowledge (expected transforms, validation expectations) is versioned and
  consulted by planning and validation.

When implementing V2 features, prefer generalizing existing 18→21 machinery over
introducing parallel paths. Remove hardcoded 18/21 assumptions only where the
feature requires it; keep backward compatibility with existing runs.

## 4. Coding rules

### Before coding — mandatory analysis

1. Read the issue/specification and its acceptance criteria.
2. Inspect the current implementation (services, routes, models).
3. Search existing services/models/contracts before writing anything new.
4. Understand the API contracts in `backend/app/api/*_contracts.py` and `shared/`.
5. Identify the exact impacted files and the runtime validation required.
6. Do not start coding until the plan and impacted files are clear.

### During coding

- Prefer small, focused changes that follow existing patterns.
- Explicit ownership: every module owns exactly its documented responsibility.
- Clear, cohesive, domain-oriented naming. No generic `utils.py`/`helpers.py`.
- Maintainable over clever: no speculative abstraction, no unnecessary
  frameworks, no duplicated logic, no large unrelated refactors.
- Do not duplicate DTOs, enums, routes, events, templates, or path calculations.
- Respect existing soft size limits: Python ~500 lines/service, functions below
  ~60 logical lines. Existing oversized files are debt; do not refactor them
  unless your task requires it.

## 5. Backend development rules

- Domain/business logic belongs in services; routers stay thin.
- APIs validate input and delegate; they never contain business logic.
- Database access follows the existing repository + session patterns.
- Workflow state changes use the transition service — never direct writes.
- Exceptions are structured. Every important failure carries:
  - a stable **error code**
  - **context** (what failed, where)
  - **correlation information** (run/stage/attempt IDs)
  - **recovery information** (what the operator can do)
- LLM/gateway errors must not leak secrets or raw credentials.

## 6. Failure debugging rules

The system is migration infrastructure; failures must be understandable.

When debugging, collect:

- the exact **command executed**
- the **environment** (OS, Python, Node, npm, Angular version, database)
- the **runtime version** actually used (node/npm exec path + checksum when bound)
- **logs** (bounded, chunked command logs)
- **database state** (run/stage/step/evidence rows)
- **workflow state** (which node/interrupt/resume point)
- **artifacts** produced before the failure

Rules:

- Never hide exceptions. No broad `except: pass`.
- Prefer structured diagnostics (typed faults, diagnostic packs, correlation IDs)
  over raw stack traces only.
- Reproduce with the real runtime before theorizing. Do not guess from code alone.

## 7. LLM integration rules

LLM capabilities in this product are bounded.

**LLM CAN:**

- analyze failures from finalized, sanitized evidence
- propose solutions / candidate diffs (in repair only)
- generate explanations
- suggest changes within a bounded context pack

**LLM CANNOT:**

- become workflow authority
- bypass backend validation or the transition service
- directly modify persistent state
- apply a diff without backend checksum/fingerprint/dry-run validation and human
  approval
- skip runtime validation
- author changes outside the repair proposer boundary

The backend remains the authority. Model output is data, never instructions.
Prompt/schema registry, redaction, provenance, usage, and cost ledger apply.

## 8. Testing strategy

Priority:

1. **Runtime validation** — the real workflow executes against real runtimes and
   produces evidence. This is the final authority.
2. **Integration validation** — services, repositories, API, events/SSE,
   LangGraph nodes/interrupt/resume, Alembic.
3. **Unit tests** — supporting evidence only.

Do not optimize for unit-test count. A feature is complete only when:

- the real workflow executes
- the runtime scenario passes
- evidence is produced (database rows, artifacts, events)

Test rules:

- Never weaken assertions, delete required coverage, or add test-aware production
  branches.
- Never label missing/not-configured checks as passed.
- Run backend tests from the repository root, e.g.
  `PYTHONPATH="$PWD:$PWD/backend" python3 -m pytest backend/tests`.
  Use the project's actual commands when they differ.
- Linux evidence proves only Linux behavior; do not claim it proves Windows
  behavior.

## 9. Runtime validation rules

Every important feature must define a runtime acceptance scenario:

- **Environment:** OS, Python, Node, npm, Angular version, database.
- **Scenario:** exact execution steps.
- **Expected:** API result, database state, artifacts, workflow events.
- **Failure case:** what happens when it breaks (injected failure).
- **Recovery case:** how execution resumes (restart / retry / rollback).

Runtime acceptance is the final authority; unit tests are supporting evidence.

## 10. Git workflow

Branch strategy:

```
main          stable, reviewed, integrated
feature/<name>  one feature branch per feature
```

Rules:

- One feature branch per feature; no mixing unrelated changes.
- Keep commits focused and logically separated.
- Do not commit secrets, databases, artifacts, sandboxes, logs, or generated
  runtime output (these live outside the repository).

Commit format:

```
feat(scope): short description
fix(scope): short description
refactor(scope): short description
docs(scope): short description
chore(scope): short description
```

Each commit message must explain what changed, why, and what validation was
performed. Reference the issue/feature when applicable.

## 11. Pull request workflow

Every PR must include:

- **Objective** — what it solves and why.
- **Implementation summary** — approach and key decisions.
- **Changed files** — with reasons.
- **Architecture impact** — none, or described explicitly.
- **Runtime validation** — command, result, evidence.
- **Risks** — remaining risks and mitigations.

Before merge, verify:

- code review completed (reviewer independent of implementer)
- runtime validation passed
- no unrelated changes included
- documentation updated where contracts/behavior changed

## 12. Conflict resolution

When resolving conflicts:

1. Understand both sides before touching anything.
2. Preserve the architecture authority rules — never "accept ours/theirs"
   blindly for shared services, contracts, or state logic.
3. Re-run validation after resolution (at least the affected tests and, if
   feasible, the runtime scenario).

## 13. Database change rules

Any database change (model + Alembic migration) must document:

- **schema impact** — exact tables/columns added or changed
- **migration path** — the Alembic revision chain, additive and safe on startup
- **compatibility** — existing runs continue to work; old data remains readable
- **existing data impact** — what happens to current rows
- **rollback approach** — how to revert

Rules:

- Follow existing model conventions in `backend/app/repositories/models/`.
- Never modify production database files directly; changes ship as migrations.
- No transaction held across subprocesses/LLM/approval waits.

## 14. File creation rules

Before creating new files:

- Check whether equivalent functionality already exists.
- Check whether an existing component/service can be extended instead.

New files require a clear responsibility and a stated reason. Prefer extending
existing cohesive modules over proliferation.

## 15. Documentation rules

Update documentation when you change:

- architecture
- API contracts
- workflow behavior
- runtime requirements

Documentation reflects final code, not intended design. A documentation defect is
a defect. Keep `docs/`, `README.md`, and this file consistent with reality.

## 16. Standard agent workflow

For every task, follow this sequence:

```
Understand issue → Inspect repository → Plan change →
Implement → Review own work → Run runtime validation →
Commit → Create PR → Address review feedback → Merge
```

Environment and validation notes:

- The VM is a migration runtime laboratory. Runtimes live under
  `~/migration-lab/runtimes/` (Angular CLI 18/19/20/21) and nvm
  (Node 18/20/22/24). Use `scripts/vm-health-check.sh` and
  `scripts/test-node-matrix.sh` to confirm readiness.
- Start the backend with `scripts/dev-backend.sh` (default port 8000, override
  with `DEV_BACKEND_PORT`).
- Validate the active SQLite database with `scripts/check-database.sh`.

## 17. Quality principle

The main objective is a **reliable Angular migration platform**.

Optimize for:

- correctness
- maintainability
- runtime proof
- architecture consistency

Do not optimize for:

- number of commits
- number of tests
- closing issues quickly

Never fake success: report missing dependencies, unproven scenarios, or failed
validation honestly with evidence and the required next action.
