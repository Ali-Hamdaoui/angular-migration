# Angular Migration Factory V2 backend E2E

## Constraints

- Backend-only; the Angular source fixture remains read-only.
- Reuse existing services and the Transformer continuation as the workflow authority.
- Do not add or run tests, create backups, or manually edit the database, artifacts, checkpoints, or stage state.
- Validate with the real governed run only after the implementation review.

## Ownership map

| Responsibility | Existing owner | Disposition |
|---|---|---|
| Planning and stage-plan authority | `PlanningApplicationService`, `StagePlanAuthorityService` | Keep; close incomplete binding gaps |
| Runtime certification | `RuntimeResolutionApplicationService`, `StageRuntimeService` | Keep; require exact certified executable |
| Workspace reconstruction and trust | `WorkspaceAuthorityService`, `StageRecoveryService` | Keep; route all recovery through them |
| Command execution | `CommandExecutorService`, command worker | Keep; preserve durable leases and mutation semantics |
| Failure normalization and semantic diagnosis | `FailureEvidenceService` | Make the single route authority |
| Failure reporting/enrichment | `FailureIntelligenceService` | Remove duplicate route decisions |
| Recovery policy | `StageRecoveryPolicyService` | Keep as decision owner; extend action mapping only where required |
| Recovery execution | `StageRecoveryService` | Keep as side-effect owner |
| Continuation resume | `TransformationContinuationService`, Transformer worker | Keep as scheduler/claimer; no stderr classification |
| LLM diagnosis/proposal/review/application | existing diagnosis, proposer, reviewer, `RepairApplicationService` | Keep; enforce bounded evidence and human gates |
| Validation | `ValidationRunner`, proven validation flow | Keep; aggregate authoritative command facts |
| Gate creation/decisions | `StageGateService`, `TransformerSealingFlow` | Keep; bind current plan/runtime/generation |
| Promotion | `CandidatePromotionService` | Keep; invoke only after approved G12 |
| Sealing | `StageSealingService`, `TransformerSealingFlow` | Keep; seal only the G12-accepted generation |
| Workflow projection | `WorkflowProjectionService` and API projections | Keep as projection; never authorize from `StageStep` status |

## Implementation sequence

1. Finish the backend call graph and inspect all callers of changed methods.
2. Correct the single failure decision path, including generic structural module-resolution evidence.
3. Correct current-plan/current-generation binding and stage-step projection scoping without guessing historical lineage.
4. Correct runtime, G07, workspace trust, recovery dispatch, repair governance, and finalization ordering.
5. Review the diff for incident/run/path-specific policy and duplicate authorities; commit and push `v2.3`.
6. Restart the same backend with the same DB/run/TargetRoot, use current authenticated API contracts, and resume through governed transitions.
7. Repeat diagnosis and generic correction for each new blocker until Angular 21 is sealed or a safety invariant blocks progress.
