# ADR-0001: Platform Boundaries and Dependency Direction

## Status

Accepted for Sprint 0.

## Context

The migration factory combines HTTP APIs, state, orchestration, deterministic
services, AI-assisted agents, command execution, artifacts, workspaces, delivery,
and UI. If these boundaries blur, later migration work can bypass safety rules.

## Decision

The backend is the trusted execution authority and source of truth. API routers
are adapters, domain models define contracts, services coordinate behavior,
repositories persist data, orchestration wires workflow nodes, deterministic
components perform rule-bound work, and agents only propose bounded outputs.

Allowed dependency direction examples:

- API routers call application services.
- Orchestration nodes call state, event, artifact, workspace, command, and policy services.
- Agents depend on domain envelopes and agent registries.
- Repositories depend on storage models and sessions.

Forbidden shortcuts:

- Routers update workflow state directly.
- Agents import command execution workers or secret-bearing configuration.
- Frontend code infers workflow progress or executes migration operations.
- Repositories emit SSE or decide approval behavior.
- LangGraph nodes write database rows directly instead of using services.

## Rationale

The split keeps trust boundaries reviewable and makes unsafe behavior visible in
code review. It also lets later Sprint 0 issues add real services without moving
business logic out of routers or agents.

## Consequences

New modules must document ownership and forbidden responsibilities. A change
that crosses boundaries must update this ADR or add a new ADR before merging.
