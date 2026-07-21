# Authoritative Architecture

```text
Next.js Control Tower
        │ typed HTTP + durable SSE
        ▼
FastAPI control plane
        │
        ├── application/domain services
        ├── Transition Service ──► SQLite authoritative state/events/approvals
        ├── LangGraph adapter ───► coordination/checkpoints only
        ├── Command policy ──────► CommandExecutor sole process authority
        ├── Workspace services ─► external run/stage sandboxes
        ├── LLM gateway ─────────► bounded Azure roles and invocation ledger
        └── Artifact Store ──────► immutable checksum-bound evidence
```

Non-negotiable authority:

- Deterministic services own facts, versions, plans, commands, validation, fingerprints, state, delivery, and deterministic reports.
- LangGraph coordinates and pauses; it reconciles with SQLite/artifacts.
- The frontend projects backend truth only.
- The source is external/read-only. Mutation occurs only in registered product-owned sandboxes under the approved external output root.
- Human decisions bind G01–G15 to state version, artifact set, plan, and relevant fingerprints.
