# Cross-Goal Contracts — G10

## Consumes

- `goals/shared/contracts/artifact_ref.schema.json`
- `goals/shared/contracts/durable_event_envelope.schema.json`
- `goals/shared/contracts/approved_stage_plan.schema.json`
- `goals/shared/contracts/command_authorization.schema.json`
- `goals/shared/contracts/command_execution_record.schema.json`
- `goals/shared/contracts/stage_sandbox_ready.schema.json`
- `goals/shared/contracts/transformation_result.schema.json`
- `goals/shared/contracts/stage_validation_summary.schema.json`
- `goals/shared/contracts/sealed_stage_output.schema.json`
- `goals/shared/contracts/failure_evidence.schema.json`
- `goals/shared/contracts/failure_route.schema.json`
- `goals/shared/contracts/repair_context_pack.schema.json`
- `goals/shared/contracts/repair_proposal.schema.json`
- `goals/shared/contracts/repair_review_decision.schema.json`
- `goals/shared/contracts/repair_g10_package.schema.json`
- `goals/shared/contracts/patch_apply_ledger.schema.json`
- `goals/shared/contracts/recovery_decision.schema.json`
- `goals/shared/contracts/assistant_answer.schema.json`
- `goals/shared/contracts/final_assurance_summary.schema.json`
- `goals/shared/contracts/delivery_record.schema.json`
- `goals/shared/contracts/final_report_record.schema.json`

## Provides

- `goals/shared/contracts/goal_completion.schema.json`

Do not change a frozen schema unilaterally. Record a proposed compatible change in evidence with affected owners/consumers. If an upstream implementation is unavailable, define a local consuming port and test fake; do not create a second upstream production service.
