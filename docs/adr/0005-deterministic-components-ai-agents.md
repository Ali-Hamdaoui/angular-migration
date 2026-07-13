# ADR-0005: Deterministic Components Versus AI Agents

## Status

Accepted for Sprint 0.

## Context

The factory uses AI assistance, but many tasks are deterministic platform
responsibilities. Treating all workflow work as agents would make policy and
execution decisions harder to audit.

## Decision

Deterministic components own rule-bound facts and enforcement: preflight,
compatibility resolution, snapshots, command validation, static checks,
checkpoints, delivery, metrics, and artifact persistence. AI-assisted agents may
summarize, diagnose ambiguity, propose patches, produce reports, and help users
understand state through structured envelopes.

Forbidden shortcuts:

- Calling the LLM for basic version parsing or policy decisions that are deterministic.
- Presenting deterministic gates as autonomous LLM decisions.
- Letting agents execute commands, mutate files, approve gates, or change policy.
- Letting LLM output become workflow state without backend validation.

## Rationale

Deterministic-first execution reduces cost and risk while preserving useful AI
assistance for ambiguity, explanation, planning narrative, diagnosis, and report
composition.

## Consequences

The UI and event history must label deterministic components and AI-assisted
agents separately. Agent tests must prove outputs are proposals, not execution.
