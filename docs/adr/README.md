# Architecture Decision Records

Sprint 0 ADRs freeze the safety and ownership rules that implementation must
not bypass. Each ADR is short, actionable, and linked from the review checklist.

| ADR | Decision |
|---|---|
| [ADR-0001](0001-platform-boundaries.md) | Platform boundaries and dependency direction |
| [ADR-0002](0002-state-event-model.md) | Backend-owned state and ordered events |
| [ADR-0003](0003-structured-command-authority.md) | Structured backend command authority |
| [ADR-0004](0004-internal-workspace-atomic-delivery.md) | Internal workspace and atomic delivery |
| [ADR-0005](0005-deterministic-components-ai-agents.md) | Deterministic components versus AI agents |
| [ADR-0006](0006-untrusted-repository-llm-boundary.md) | Untrusted repository content and LLM boundary |
| [ADR-0007](0007-sqlite-mvp-boundary.md) | SQLite single-host MVP operating boundary |

Use [the code review checklist](../code-review-checklist.md) for every Sprint 0
change that touches execution, state, artifacts, approvals, LLM use, or delivery.
