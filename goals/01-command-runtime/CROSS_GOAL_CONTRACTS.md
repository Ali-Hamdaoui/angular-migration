# Cross-Goal Contracts — G01

## Consumes

- `goals/shared/contracts/approved_stage_plan.schema.json`
- `goals/shared/contracts/artifact_ref.schema.json`
- `goals/shared/contracts/durable_event_envelope.schema.json`

## Provides

- `goals/shared/contracts/command_authorization.schema.json`
- `goals/shared/contracts/command_execution_record.schema.json`

Do not change a frozen schema unilaterally. Record a proposed compatible change in evidence with affected owners/consumers. If an upstream implementation is unavailable, define a local consuming port and test fake; do not create a second upstream production service.
