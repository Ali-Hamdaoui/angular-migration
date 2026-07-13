# Sprint 0 Code Review Checklist

Use this checklist for every Sprint 0 change that touches workflow, execution,
state, artifacts, approvals, LLM use, or delivery.

## Boundary ADRs

- [ ] [ADR-0001](adr/0001-platform-boundaries.md): APIs delegate to services; repositories, agents, and routers do not bypass ownership boundaries.
- [ ] [ADR-0002](adr/0002-state-event-model.md): Backend state is authoritative; events are ordered evidence, not UI-inferred progress.
- [ ] [ADR-0003](adr/0003-structured-command-authority.md): Commands are structured, allowlisted, shell-free, and backend-executed only.
- [ ] [ADR-0004](adr/0004-internal-workspace-atomic-delivery.md): Source remains immutable and `migrated-app` is published only after delivery gates.
- [ ] [ADR-0005](adr/0005-deterministic-components-ai-agents.md): Deterministic components and AI-assisted agents remain separate and correctly labeled.
- [ ] [ADR-0006](adr/0006-untrusted-repository-llm-boundary.md): Repository content is untrusted, secrets are redacted, and LLM output is validated.
- [ ] [ADR-0007](adr/0007-sqlite-mvp-boundary.md): SQLite remains single-host MVP storage with short transactions and external artifacts.

## Required Checks

- [ ] Source immutability is preserved; no code mutates arbitrary user source paths.
- [ ] Backend state changes go through the transition service or documented mock boundary.
- [ ] Command authority cannot be bypassed by UI, agents, LLM output, or repository content.
- [ ] Artifacts are immutable, checksum-bound, and opened by artifact ID or approved relative reference.
- [ ] Approvals are bound to current state, gate, actor, artifact checksums, scope, and expiry.
- [ ] Prompt-injection boundaries are explicit wherever repository text reaches an LLM context.
- [ ] Delivery publication cannot expose failed, cancelled, incomplete, or overwritten output.
- [ ] Tests cover new policy, state, artifact, approval, command, or LLM behavior.
- [ ] Documentation is updated when behavior or boundaries change.
