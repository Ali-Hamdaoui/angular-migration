# AI Frontend Migration Factory

The AI Frontend Migration Factory is a platform for controlled Angular frontend
migrations. Its MVP reference path is Angular 18.x to Angular 21.x, using strict
compatibility and functional-parity rules.

The product is deliberately split into independent workspaces. The frontend
provides the Control Tower experience; the backend is the only execution and
workflow authority. Agents may analyse and propose work, but they never execute
commands or mutate a migration workspace directly.

## Architecture diagram

```text
Control Tower UI (Next.js)
  |
  v
FastAPI Backend / Execution Authority
  |-- State Transition Service (optimistic concurrency, idempotency, leases)
  |-- Ordered Event Store (SSE, replay, deduplication)
  |-- LangGraph Orchestrator (six-phase mock workflow)
  |     |-- Deterministic Components (preflight, snapshot, compatibility, commands)
  |     `-- AI-Assisted Agents (analysis, planning, transformation, repair, report)
  |-- Structured Command Worker (allowlists, runtime profiles, timeout, cancel)
  |-- Artifact Store (immutable, checksum-bound, stage-scoped)
  |-- Workspace / Snapshot / Delivery (source immutable, atomic publication)
  |-- LLM Gateway (Azure OpenAI mock, redaction, usage, cost)
  `-- Observability (run metrics, diagnostics, alerts)
```

## Workspace map

```text
backend/   FastAPI execution authority, orchestration, persistence, artifacts.
frontend/  Next.js Control Tower UI.
shared/    Shared contracts and generated API references.
bundled Angular workspace/ Controlled fixture Angular applications.
scripts/   Developer automation and reproducible local workflows.
docs/      Product, architecture, ADR, setup, and sprint documentation.
tests/     Cross-workspace and end-to-end test suites.
```

## Module ownership

| Module | Owns | Forbidden |
|---|---|---|
| `api/` | HTTP routing, input validation, service delegation | Business logic, repository access, workflow state |
| `domain/` | Canonical contracts and state vocabulary | Service logic, persistence, I/O |
| `state/` | Transition service, optimistic concurrency, idempotency | HTTP routing, LLM calls |
| `events/` | Ordered event persistence and SSE emission | Workflow decisions, command execution |
| `orchestration/` | LangGraph workflow graph and node wiring | Direct DB writes, frontend I/O, command execution |
| `components/` | Deterministic workflow services | LLM calls, importing command-worker internals |
| `agents/` | AI-assisted agent input/output envelopes | Command execution, file mutation, credentials |
| `preflight/` | Path and runtime capability validation | Source mutation, ng update |
| `snapshots/` | Immutable source snapshot | Mutation of original source |
| `workspaces/` | Internal run workspace lifecycle | Publishing to migrated-app directly |
| `checkpoints/` | Resume checkpoint management | Bypassing state transition service |
| `delivery/` | Atomic delivery publication | Publishing incomplete or failed work |
| `artifact_store/` | Immutable, checksum-bound artifact I/O | Overwriting existing artifacts, path traversal |
| `command_execution/` | Structured command worker and supervisor | Raw shell strings, agent-direct execution |
| `llm_gateway/` | Azure OpenAI abstraction, redaction, cost | Exposing credentials, LLM-driven execution |
| `observability/` | Run metrics and diagnostics | Secrets in metrics, blocking state transitions |
| `policies/` | Command allowlists, auto-approval, sensitivity | Hardcoding policies in agents or routers |

## Boundary rules

- Workflow state, approvals, artifact access, sandbox policy, and command
  execution belong to `backend/`.
- The `frontend/` must not implement a workflow state machine or migration
  execution logic.
- Agents and orchestration live behind backend boundaries; they can propose
  actions but cannot bypass backend validation or execution authority.
- Deterministic components and AI-assisted agents are separated in code,
  execution history, and UI labels.
- Fixture Angular applications belong in `bundled Angular workspace/`, never in production
  backend or frontend source trees.
- Reusable contract references belong in `shared/`; avoid duplicating status
  vocabularies across applications.
- The original source remains immutable. All mutation occurs inside an
  internal run workspace.
- Failed or cancelled work is never published as `migrated-app`.

## Delivery status

This repository contains the Sprint 0 workspace skeleton. The FastAPI, Next.js,
contracts, persistence, workflow, and runtime features are introduced by their
subsequent Sprint 0 issues.

## Documentation

- [MVP overview](docs/mvp_overview.md)
- [Workflow specification](docs/workflow.md)
- [Sprint 0 backlog](docs/sprint0.md)
- [Architecture decisions](docs/adr/README.md)
- [Sprint 0 threat overview](docs/threat-overview.md)
- [Code review checklist](docs/code-review-checklist.md)

## Developer setup

Use [docs/developer-setup.md](docs/developer-setup.md) for PowerShell-compatible setup, local startup, quality gates, database commands, mock workflow demos, SSE replay checks, and proxy/certificate troubleshooting.

## Run The Solution Locally

Start the backend and frontend in separate PowerShell terminals:

```powershell
.\scripts\dev-backend.ps1
```

```powershell
.\scripts\dev-frontend.ps1
```

The scripts launch:

- Backend: python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
- Frontend: $env:NEXT_PUBLIC_BACKEND_URL="http://127.0.0.1:8765"
            npm run dev

If you want to validate the full workspace after startup, run:

```powershell
.\scripts\quality.ps1
```
