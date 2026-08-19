"""Persistence model package."""

from app.repositories.models.base import Base
from app.repositories.preflight_models import (
    ApprovalGateModel,
    PreflightArtifactMetadataModel,
    PreflightEventModel,
    PreflightModel,
    UserDecisionModel,
)
from app.repositories.g02_models import G02ApprovalModel
from app.repositories.baseline_models import BaselineQualificationModel
from app.repositories.baseline_matrix_models import BaselineValidationModel
from app.repositories.baseline_parity_models import BaselineParityEvidenceModel
from app.repositories.baseline_g03_models import BaselineAssessmentModel, G03ApprovalModel
from app.repositories.discovery_models import DiscoveryEvidenceModel
from app.repositories.parity_baseline_models import ParityBaselineEvidenceModel
from app.repositories.execution_profiles import ExecutionProfileModel
from app.repositories.runtime_evidence import RuntimeExecutionEvidenceModel
from app.repositories.diagnostics_models import FailureDiagnosticPackModel
from app.repositories.stage_runtime_models import StageRuntimeBindingModel
from app.repositories.workspace_generation_models import WorkspaceGenerationModel
from app.repositories.lockfile_evidence_models import LockfileGenerationEvidenceModel
from app.repositories.migration_route_models import MigrationRouteModel
from app.repositories.runtime_certification_models import RuntimeCertificationModel
from app.repositories.project_capability_models import ProjectCapabilityModel
from app.repositories.third_party_compatibility_models import ThirdPartyCompatibilityReportModel
from app.repositories.preflight_check_models import PreflightCheckResultModel
from app.repositories.stage_knowledge_models import StageKnowledgeEntryModel
from app.repositories.v2_planning_models import V2PlanningModel
from app.repositories.failure_intelligence_models import FailureIntelligenceModel
from app.repositories.transformation_replan_models import TransformationReplanRecoveryModel
from app.repositories.proposal_cycle_models import ProposalCycleModel
from app.repositories.candidate_promotion_models import CandidatePromotionModel
from app.repositories.stage_chain_run_models import StageChainRunModel
from app.repositories.stage_validation_seal_models import StageValidationSealModel
from app.repositories.stage_rollback_models import StageRollbackModel
from app.repositories.partial_delivery_models import PartialDeliveryModel
from app.repositories.execution_audit_models import CommandExecutionAuditModel
from app.repositories.retrieval_benchmark_models import RetrievalBenchmarkModel
from app.repositories.catalogue_certification_models import CatalogueCertificationModel
from app.repositories.models.workflow import (
    AgentExecutionModel,
    AssistantConversationModel,
    AssistantLifecycleEventModel,
    AssistantMessageModel,
    ActiveRunClaimModel,
    ApprovalEventModel,
    ApprovalPolicyEventModel,
    ArtifactMetadataModel,
    CommandAuthorizationAuditModel,
    CommandExecutionModel,
    CommandLogChunkModel,
    CommandLogSummaryModel,
    CommandTemplateModel,
    EnvironmentCapabilityModel,
    EnvironmentDiagnosticEventModel,
    FactoryRuntimeModel,
    LlmUsageRecordModel,
    LlmInvocationModel,
    UsageCostRecordModel,
    MigrationRunModel,
    PathValidationModel,
    TargetReservationModel,
    MigrationStageModel,
    RepairAttemptModel,
    RepairFingerprintRecoveryModel,
    RunAssuranceStatusModel,
    StageStepModel,
    StageCheckpointModel,
    StageGateDecisionModel,
    StageGatePackageModel,
    StagePromptRequestModel,
    StageReconstructionRecordModel,
    StageWorkspaceBindingModel,
    SourceAnalysisModel,
    SourceIntakeJobModel,
    PlanningJobModel,
    TransformationContinuationModel,
    SourceSnapshotModel,
    RunEventSequenceModel,
    WorkflowEventModel,
    WorkerLeaseModel,
)
from app.repositories.analysis_models import AnalysisMetadataModel, G04ApprovalModel
from app.repositories.compatibility_models import (
    CompatibilityCatalogueModel,
    CompatibilityResolutionModel,
    G05ApprovalModel,
    RegistrySnapshotModel,
)
from app.repositories.planning_models import (
    ActivePlanVersionModel,
    BuildSystemDecisionModel,
    MigrationPlanModel,
    StageExecutionPlanModel,
)
from app.repositories.planning_review_models import (
    G06DecisionModel,
    G06ApprovalModel,
    PlanApprovalStaleModel,
    PlanRevisionModel,
    PlanningReviewModel,
)

__all__ = [
    "AnalysisMetadataModel",
    "G04ApprovalModel",
    "CompatibilityCatalogueModel",
    "CompatibilityResolutionModel",
    "RegistrySnapshotModel",
    "G05ApprovalModel",
    "MigrationPlanModel",
    "StageExecutionPlanModel",
    "BuildSystemDecisionModel",
    "ActivePlanVersionModel",
    "PlanRevisionModel",
    "PlanningReviewModel",
    "PlanApprovalStaleModel",
    "G06ApprovalModel",
    "G06DecisionModel",
    'LlmInvocationModel',
    'UsageCostRecordModel',
    "AgentExecutionModel",
    "AssistantConversationModel",
    "AssistantLifecycleEventModel",
    "AssistantMessageModel",
    "ActiveRunClaimModel",
    "ApprovalEventModel",
    "ApprovalPolicyEventModel",
    "ArtifactMetadataModel",
    "Base",
    "G02ApprovalModel",
    "BaselineQualificationModel",
    "BaselineValidationModel",
    "BaselineParityEvidenceModel",
    "BaselineAssessmentModel",
    "DiscoveryEvidenceModel",
    "ParityBaselineEvidenceModel",
    "G03ApprovalModel",
    "ExecutionProfileModel",
    "RuntimeExecutionEvidenceModel",
    "FailureDiagnosticPackModel",
    "StageRuntimeBindingModel",
    "WorkspaceGenerationModel",
    "LockfileGenerationEvidenceModel",
    "MigrationRouteModel",
    "RuntimeCertificationModel",
    "ProjectCapabilityModel",
    "ThirdPartyCompatibilityReportModel",
    "PreflightCheckResultModel",
    "StageKnowledgeEntryModel",
    "V2PlanningModel",
    "FailureIntelligenceModel",
    "TransformationReplanRecoveryModel",
    "ProposalCycleModel",
    "CandidatePromotionModel",
    "StageChainRunModel",
    "StageValidationSealModel",
    "StageRollbackModel",
    "PartialDeliveryModel",
    "CommandExecutionAuditModel",
    "RetrievalBenchmarkModel",
    "CatalogueCertificationModel",
    "CommandAuthorizationAuditModel",
    "CommandExecutionModel",
    "CommandLogChunkModel",
    "CommandLogSummaryModel",
    "CommandTemplateModel",
    "EnvironmentCapabilityModel",
    "EnvironmentDiagnosticEventModel",
    "FactoryRuntimeModel",
    "LlmUsageRecordModel",
    "MigrationRunModel",
    "PathValidationModel",
    "TargetReservationModel",
    "MigrationStageModel",
    "RepairAttemptModel",
    "RepairFingerprintRecoveryModel",
    "RunAssuranceStatusModel",
    "StageStepModel",
    "StageCheckpointModel",
    "StageGateDecisionModel",
    "StageGatePackageModel",
    "StagePromptRequestModel",
    "StageReconstructionRecordModel",
    "StageWorkspaceBindingModel",
    "SourceAnalysisModel",
    "SourceIntakeJobModel",
    "PlanningJobModel",
    "TransformationContinuationModel",
    "SourceSnapshotModel",
    "RunEventSequenceModel",
    "WorkflowEventModel",
    "WorkerLeaseModel",
    "ApprovalGateModel",
    "PreflightArtifactMetadataModel",
    "PreflightEventModel",
    "PreflightModel",
    "UserDecisionModel",
]
