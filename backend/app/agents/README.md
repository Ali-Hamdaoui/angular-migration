# Agents

Owns AI-assisted agent interfaces, registries, and mock agent implementations.

Agents may analyze context and propose structured actions, explanations,
patches, or reports. They must not execute commands, mutate files directly,
access secret-bearing configuration, bypass policy checks, or become
deterministic platform services.

## Bounded Interface

All agents receive `AgentInputEnvelope` and return `AgentOutputEnvelope` from
`app.domain.contracts`. The shared envelope is used by:

- `AnalysisAgent`
- `PlanningAgent`
- `TransformationAgent`
- `BuildValidationAgent`
- `RepairAgent`
- `ReportAgent`
- `AssistantAgent`

The mock registry also includes `EligibilityAgent` as a Sprint 0 setup helper.
It follows the same no-mutation contract.

Agent inputs include backend-owned run state, allowed action vocabulary,
artifact locations, client constraints, the approved plan checksum when
available, and explicit `UntrustedContextRef` entries for future repository,
comment, diff, or log excerpts. Repository content must remain data, not policy.

Agent outputs may include summaries, risk entries, artifact references,
`ActionProposalDto`, and `PatchProposalDto`. Outputs may recommend a next state,
but they cannot transition workflow state, authorize execution, approve gates,
or apply patches. Command proposals must reference a registered action ID and
remain subject to backend command policy.

## Proposal Schemas

`ActionProposalDto` records a proposed action type, rationale, and optional
registered action ID. A `run_approved_command` proposal is invalid without that
registered action ID.

`PatchProposalDto` records target files, rationale, risk, expected behavior
impact, and requested validation gates. Patch proposals are advisory only; the
backend must validate and apply any accepted patch through deterministic checks.