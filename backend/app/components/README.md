# Components

Owns deterministic workflow components such as preflight checks, compatibility
resolution, snapshots, command request construction, static checks, checkpoints,
and delivery verification.

Components may request trusted services but must not call LLMs, execute commands
directly, import command-worker internals, or mutate source projects outside the
internal workspace boundary.

## Bounded Interface

All deterministic services are represented by `DeterministicComponentType`,
`ComponentInputEnvelope`, `ComponentOutputEnvelope`, and
`DeterministicComponentContract` in `app.domain.contracts`.

Sprint 0 defines bounded contracts for:

- `SourceIntakeValidator`
- `SnapshotService`
- `WorkspaceTopologyClassifier`
- `CompatibilityResolver`
- `ToolchainRuntimeManager`
- `CommandPolicyEngine`
- `BaselineQualificationService`
- `StaticSymbolGate`
- `ParityEvidenceEngine`
- `CheckpointService`
- `ArtifactService`
- `WorkerSupervisor`
- `DeliveryService`

Component contracts reject LLM access and direct command execution. Components
return deterministic status and artifact references; they do not produce AI
action proposals or patch proposals.

## Execution History

Deterministic executions are recorded as `ComponentExecutionDto` in
`component_executions`. AI-assisted calls are recorded separately as
`AgentExecutionDto` in `agent_executions`. The UI must label these histories
separately so deterministic gates are not represented as LLM decisions.