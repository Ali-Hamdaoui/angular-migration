# Cross-Goal Contracts — G08

## Consumes

- `goals/shared/contracts/command_execution_record.schema.json`
- `goals/shared/contracts/sealed_stage_output.schema.json`
- `goals/shared/contracts/patch_apply_ledger.schema.json`
- `goals/shared/contracts/artifact_ref.schema.json`
- `goals/shared/contracts/durable_event_envelope.schema.json`

## Provides

- `goals/shared/contracts/recovery_decision.schema.json`
- `goals/shared/contracts/assistant_answer.schema.json`

Do not change a frozen schema unilaterally. Record a proposed compatible change in evidence with affected owners/consumers. If an upstream implementation is unavailable, define a local consuming port and test fake; do not create a second upstream production service.
