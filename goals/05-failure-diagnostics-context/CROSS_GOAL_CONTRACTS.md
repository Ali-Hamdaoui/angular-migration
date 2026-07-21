# Cross-Goal Contracts — G05

## Consumes

- `goals/shared/contracts/command_execution_record.schema.json`
- `goals/shared/contracts/stage_validation_summary.schema.json`
- `goals/shared/contracts/artifact_ref.schema.json`
- `goals/shared/contracts/durable_event_envelope.schema.json`

## Provides

- `goals/shared/contracts/failure_evidence.schema.json`
- `goals/shared/contracts/failure_route.schema.json`
- `goals/shared/contracts/repair_context_pack.schema.json`

Do not change a frozen schema unilaterally. Record a proposed compatible change in evidence with affected owners/consumers. If an upstream implementation is unavailable, define a local consuming port and test fake; do not create a second upstream production service.
