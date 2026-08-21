"""Persistence and API projection for the S2-F04 Analysis/G04 boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.api.analysis_contracts import AnalysisCreateRequest, AnalysisResponse, G04DecisionResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.core.datetime import normalize_persisted_utc
from app.domain.analysis import AnalysisArtifactInput, AnalysisPackage, AnalysisRequest, G04Decision, G04DecisionRequest
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.llm_gateway import AzureGatewayError, LlmRole
from app.repositories.models import (
    AnalysisMetadataModel,
    ArtifactMetadataModel,
    G04ApprovalModel,
    G03ApprovalModel,
    DiscoveryEvidenceModel,
    LlmInvocationModel,
    MigrationRunModel,
    PlanningJobModel,
    UsageCostRecordModel,
    SourceIntakeJobModel,
)
from app.repositories.session import session_scope
from app.repositories.parity_baseline_models import ParityBaselineEvidenceModel
from app.services.analysis_application_service import AnalysisAgentService, AnalysisApplicationError, AnalysisArtifact
from app.services.planning_job_service import PLANNING_JOB_NONTERMINAL_STATES
from app.state.transition_service import StateTransitionService, TransitionRequest, TransitionError, StaleStateVersionError
from app.domain.contracts import RunStatus


class AnalysisEvidenceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


class AnalysisEvidenceApplicationService:
    """Store immutable analysis evidence and append-only G04 decisions."""

    def __init__(self, *, session_scope_factory=session_scope, analysis_agent=None, now_provider=None) -> None:
        self.scope = session_scope_factory
        self.analysis_agent = analysis_agent
        self.now = now_provider or (lambda: datetime.now(UTC))

    def generate(self, run_id: str, payload, actor: str) -> AnalysisResponse:
        with self.scope() as session:
            run = self._authorized_run(session, run_id, actor)
            g03 = self._approved_g03(session, run_id)
            workspace_fingerprint = self._authoritative_workspace_fingerprint(
                g03,
                payload.workspace_fingerprint,
            )
            canonical = self._canonical_inputs(session, run_id, payload.prerequisite_artifacts)
            request = AnalysisRequest(
                run_id=run_id, expected_state_version=payload.expected_state_version,
                idempotency_key=payload.idempotency_key, actor=actor,
                prerequisite_artifacts=canonical,
                workspace_fingerprint=workspace_fingerprint,
                plan_version=payload.plan_version, correlation_id=payload.correlation_id,
            )
            request_checksum = self._checksum(request.model_dump(mode="json"))
            existing = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.idempotency_key == payload.idempotency_key))
            if existing:
                if existing.request_checksum != request_checksum:
                    raise AnalysisEvidenceError("IDEMPOTENCY_KEY_REUSED", "Idempotency key was used with a different payload.", 409)
                return self._analysis_dto(session, existing, replay=True)
            if run.state_version != payload.expected_state_version:
                raise AnalysisEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409)
            started = self._transition(session, run, request, WorkflowEventType.ANALYSIS_AGENT_STARTED, "analysis agent started")
            now = self.now()
            invocation = LlmInvocationModel(
                id="llm-invocation-" + uuid4().hex[:12], run_id=run_id, stage_id=None,
                idempotency_key=request.idempotency_key, request_checksum=request_checksum,
                input_hashes=[item.checksum for item in request.prerequisite_artifacts],
                correlation_id=request.correlation_id or uuid4().hex, actor=actor,
                role="phase_proposer", task_type="analysis_summary", provider="azure_openai",
                deployment_alias="pending", prompt_version="analysis_agent_v1",
                schema_version="analysis-schema-registry-v1", pricing_version="unknown",
                stage="analysis", redacted_summary=None, status="in_progress", failure_code=None,
                artifact_ids=[], artifact_checksums={}, state_version=started.next_state_version,
                event_sequence=started.event_sequence, retries=0, latency_ms=None,
                started_at=now, completed_at=None, created_at=now,
            )
            session.add(invocation)
            row = AnalysisMetadataModel(
                id="analysis-" + uuid4().hex[:12], run_id=run_id, idempotency_key=request.idempotency_key,
                request_checksum=request_checksum, actor=actor, status="in_progress",
                artifact_set_checksum=request.artifact_set_checksum,
                prerequisite_artifact_ids=[item.artifact_id for item in request.prerequisite_artifacts],
                workspace_fingerprint=request.workspace_fingerprint, plan_version=request.plan_version,
                invocation_id=invocation.id, proposer_invocation_id=invocation.id, reviewer_invocation_id=None, failed_invocation_id=None, artifact_ids=[], artifact_checksums={}, package=None,
                state_version=started.next_state_version, event_sequence=started.event_sequence,
                correlation_id=request.correlation_id or invocation.correlation_id,
                created_at=now, updated_at=now,
            )
            session.add(row)
            session.flush()

        deployment = None
        try:
            agent = self._agent(run_id, request)
            agent.invocation_hooks = {
                "before_invocation": lambda **data: self._on_analysis_invocation_before(run_id, request, data),
                "after_invocation": lambda **data: self._on_analysis_invocation_after(run_id, request, data),
                "failed_invocation": lambda **data: self._on_analysis_invocation_failed(run_id, request, data),
            }
            deployment = getattr(getattr(agent, "gateway", None), "deployment_name", None)
            if deployment:
                with self.scope() as session:
                    row = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.idempotency_key == request.idempotency_key))
                    session.get(LlmInvocationModel, row.invocation_id).deployment_alias = deployment
            package = agent.generate(request)
        except AnalysisApplicationError as error:
            if deployment and error.details.get("failure_stage") != "phase_reviewer":
                with self.scope() as session:
                    run = session.get(MigrationRunModel, run_id)
                    self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_FAILED, "analysis proposer LLM invocation failed", {"invocation_id": row.invocation_id, "error_code": error.code})
            return self._fail(run_id, request, request_checksum, error.code, error.details)
        except AzureGatewayError as error:
            details = {"failure_stage": "configuration", "sanitized_provider_message": str(error), "retry_count": error.retry_count}
            with self.scope() as session:
                run = session.get(MigrationRunModel, run_id)
                row = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.idempotency_key == request.idempotency_key))
                invocation = session.get(LlmInvocationModel, row.invocation_id)
                transition = self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_FAILED, "analysis LLM configuration blocked", {"invocation_id": invocation.id, "error_code": "LLM_CONFIGURATION_BLOCKED"})
                invocation.status = "blocked"; invocation.failure_code = "LLM_CONFIGURATION_BLOCKED"; invocation.failure_stage = "configuration"; invocation.sanitized_provider_message = "Azure OpenAI configuration is incomplete."; invocation.state_version = transition.next_state_version; invocation.event_sequence = transition.event_sequence; invocation.completed_at = self.now()
            return self._fail(run_id, request, request_checksum, "LLM_CONFIGURATION_BLOCKED", details)
        except Exception:
            return self._fail(run_id, request, request_checksum, "ANALYSIS_DEPENDENCY_FAILED")
        return self._complete(run_id, request, request_checksum, package)

    def get(self, run_id: str, actor: str) -> AnalysisResponse | None:
        with self.scope() as session:
            run = self._authorized_run(session, run_id, actor)
            row = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id).order_by(AnalysisMetadataModel.created_at.desc()))
            return self._analysis_dto(session, row) if row else None

    def retry(self, run_id: str, payload, actor: str) -> AnalysisResponse:
        """Create a new append-only Analysis attempt from retry-eligible evidence."""
        with self.scope() as session:
            run = self._authorized_run(session, run_id, actor)
            if run.state_version != payload.expected_state_version:
                raise AnalysisEvidenceError("STALE_STATE_VERSION", "The Analysis retry state version is stale.", 409)
            old = session.get(AnalysisMetadataModel, payload.failed_analysis_id)
            if old is None or old.run_id != run_id:
                raise AnalysisEvidenceError("ANALYSIS_ATTEMPT_NOT_FOUND", "The referenced Analysis attempt does not belong to this run.", 404)
            existing = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.idempotency_key == payload.idempotency_key))
            if existing is not None:
                return self._analysis_dto(session, existing, replay=True)
            if old.status != "failed" or not old.retryable:
                raise AnalysisEvidenceError("ANALYSIS_RETRY_NOT_ELIGIBLE", "The referenced Analysis attempt is not retry-eligible.", 409)
            gate = session.scalar(select(G04ApprovalModel).where(G04ApprovalModel.run_id == run_id, G04ApprovalModel.gate_id == "G04", G04ApprovalModel.status.in_({"pending", "approved", "approved_with_comment"})))
            if gate is not None:
                raise AnalysisEvidenceError("ANALYSIS_RETRY_NOT_ELIGIBLE", "A current G04 gate prevents another Analysis attempt.", 409)
            job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == run_id, SourceIntakeJobModel.status == "waiting_retry"))
            if job is not None:
                job.status = "running"
                job.finished_at = None
        request = AnalysisCreateRequest(
            expected_state_version=payload.expected_state_version,
            idempotency_key=payload.idempotency_key,
            prerequisite_artifacts=[],
            workspace_fingerprint=old.workspace_fingerprint,
            plan_version=old.plan_version,
            correlation_id=f"analysis-retry:{run_id}:{payload.idempotency_key}",
        )
        result = self.generate(run_id, request, actor)
        with self.scope() as session:
            job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == run_id, SourceIntakeJobModel.status == "running"))
            if job is not None and result.status == "completed":
                job.status = "completed"
                job.finished_at = self.now()
                job.state_version = result.state_version
        return result

    def decide_g04(self, run_id: str, payload, actor: str) -> G04DecisionResponse:
        with self.scope() as session:
            run = self._authorized_run(session, run_id, actor)
            old = session.scalar(select(G04ApprovalModel).where(G04ApprovalModel.run_id == run_id, G04ApprovalModel.idempotency_key == payload.idempotency_key))
            request_checksum = self._checksum({**payload.model_dump(mode="json"), "actor": actor, "run_id": run_id})
            if old:
                if old.stale_reason and old.stale_reason != request_checksum:
                    raise AnalysisEvidenceError("IDEMPOTENCY_KEY_REUSED", "Idempotency key was used with a different payload.", 409)
                return self._decision_dto(old, replay=True)
            if run.state_version != payload.expected_state_version:
                raise AnalysisEvidenceError("STALE_STATE_VERSION", "The G04 decision state version is stale.", 409)
            analysis = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.status == "completed").order_by(AnalysisMetadataModel.created_at.desc()))
            gate = session.scalar(select(G04ApprovalModel).where(G04ApprovalModel.run_id == run_id, G04ApprovalModel.gate_id == "G04").order_by(G04ApprovalModel.state_version.desc(), G04ApprovalModel.created_at.desc()))
            if analysis is None or gate is None or gate.status != "pending":
                raise AnalysisEvidenceError("G04_NOT_PENDING", "G04 is not available for a decision.", 409)
            if payload.gate_version != gate.gate_version or payload.package_checksum != gate.package_checksum:
                self._record_stale_gate(session, run, gate, payload, actor, "package_checksum_changed")
                raise AnalysisEvidenceError("STALE_ANALYSIS_PACKAGE", "The G04 package binding is stale.", 409)
            if payload.workspace_fingerprint != gate.workspace_fingerprint or payload.plan_version != gate.plan_version:
                self._record_stale_gate(session, run, gate, payload, actor, "workspace_or_plan_binding_changed")
                raise AnalysisEvidenceError("STALE_ANALYSIS_BINDING", "The G04 workspace or plan binding is stale.", 409)
            try:
                self._verify_package_integrity(run, gate)
            except AnalysisEvidenceError:
                self._record_stale_gate(session, run, gate, payload, actor, "package_integrity_failed")
                raise
            package = analysis.package or {}
            domain_request = AnalysisRequest(
                run_id=run_id, expected_state_version=payload.expected_state_version,
                idempotency_key=analysis.idempotency_key, actor=actor,
                prerequisite_artifacts=package.get("deterministic_input_artifacts", []),
                workspace_fingerprint=analysis.workspace_fingerprint, plan_version=analysis.plan_version,
            )
            decision = G04DecisionRequest(
                expected_state_version=payload.expected_state_version, gate_version=payload.gate_version,
                package_checksum=payload.package_checksum,
                workspace_fingerprint=payload.workspace_fingerprint,
                plan_version=payload.plan_version,
                decision=payload.decision, comment=payload.comment,
            )
            try:
                result = self._agent(run_id, domain_request).decide_g04(domain_request, AnalysisPackage.model_validate(package), decision)
            except (AnalysisApplicationError, TypeError) as error:
                code = getattr(error, "code", "STALE_ANALYSIS_PACKAGE")
                raise AnalysisEvidenceError(code, str(error), 409) from error
            event_type = {G04Decision.APPROVE: WorkflowEventType.G04_APPROVED, G04Decision.APPROVE_WITH_COMMENT: WorkflowEventType.G04_APPROVED, G04Decision.REQUEST_MODIFICATION: WorkflowEventType.G04_MODIFICATION_REQUESTED, G04Decision.REJECT: WorkflowEventType.G04_REJECTED}[payload.decision]
            transition = self._transition(
                session,
                run,
                domain_request,
                event_type,
                "G04 decision recorded",
                next_run_status=RunStatus.PLANNING_RUNNING if event_type == WorkflowEventType.G04_APPROVED else None,
                next_run_phase="FEASIBILITY_PLANNING" if event_type == WorkflowEventType.G04_APPROVED else None,
                next_phase_status="running" if event_type == WorkflowEventType.G04_APPROVED else None,
                next_approval_status="approved" if event_type == WorkflowEventType.G04_APPROVED else None,
            )
            now = self.now()
            row = G04ApprovalModel(
                id="g04-" + uuid4().hex[:12], run_id=run_id, gate_id="G04", gate_version=gate.gate_version,
                idempotency_key=payload.idempotency_key, actor=actor, status=result.review_status,
                decision=payload.decision.value, package_checksum=gate.package_checksum,
                artifact_set_checksum=analysis.artifact_set_checksum, workspace_fingerprint=analysis.workspace_fingerprint,
                plan_version=analysis.plan_version, state_version=transition.next_state_version,
                event_sequence=transition.event_sequence, artifact_ids=gate.artifact_ids,
                comment=payload.comment, stale_reason=request_checksum, created_at=now, updated_at=now,
            )
            session.add(row)
            if event_type == WorkflowEventType.G04_APPROVED:
                active_job = session.scalar(
                    select(PlanningJobModel)
                    .where(
                        PlanningJobModel.run_id == run_id,
                        PlanningJobModel.status.in_(PLANNING_JOB_NONTERMINAL_STATES),
                    )
                    .order_by(PlanningJobModel.created_at.desc())
                )
                if active_job is None:
                    session.add(
                        PlanningJobModel(
                            id=f"planning-{run_id}",
                            run_id=run_id,
                            thread_id=f"planning:{run_id}",
                            status="queued_after_g04",
                            current_step="resolving_feasibility",
                            actor=actor,
                            worker_id=None,
                            attempt=0,
                            lease_expires_at=None,
                            idempotency_key=f"planning-after-g04:{run_id}:{payload.package_checksum}",
                            correlation_id=analysis.correlation_id or f"planning:{run_id}",
                            last_error_code=None,
                            last_error_stage=None,
                            retryable=None,
                            state_version=transition.next_state_version,
                            created_at=now,
                            started_at=None,
                            updated_at=now,
                            completed_at=None,
                        )
                    )
            session.flush()
            return self._decision_dto(row)

    def _agent(self, run_id: str, request: AnalysisRequest):
        if self.analysis_agent is not None:
            return self.analysis_agent
        from app.core.config import get_settings
        from app.llm_gateway.azure_gateway import AzureOpenAILLMGateway
        from app.services.analysis_application_service import AnalysisGatewayNarrative, AnalysisGatewayReview
        from app.artifact_store import LocalFilesystemArtifactStore
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id)
            store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
        from app.llm_gateway.azure_gateway import PromptSchemaRegistry
        registry = PromptSchemaRegistry(version=get_settings().llm_schema_registry_version)
        registry.register("analysis_narrative_v1", AnalysisGatewayNarrative)
        registry.register("analysis_review_v1", AnalysisGatewayReview)
        settings = get_settings()
        return AnalysisAgentService(gateway=AzureOpenAILLMGateway(settings=settings, registry=registry), artifact_reader=lambda artifact_id: self._read_artifact(store, artifact_id), proposer_max_output_tokens=settings.analysis_proposer_max_output_tokens, reviewer_max_output_tokens=settings.analysis_reviewer_max_output_tokens)

    def _on_analysis_invocation_before(self, run_id, request, data):
        if data.get("role") is LlmRole.PHASE_PROPOSER:
            with self.scope() as session:
                run = session.get(MigrationRunModel, run_id)
                row = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.idempotency_key == request.idempotency_key))
                invocation = session.get(LlmInvocationModel, row.invocation_id)
                transition = self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_STARTED, "analysis proposer LLM invocation started", {"invocation_id": invocation.id, "role": "phase_proposer", "attempt": data.get("revision", 0), "revision": data.get("revision", 0)})
                invocation.state_version = transition.next_state_version; invocation.event_sequence = transition.event_sequence
            return
        if data.get("role") is not LlmRole.PHASE_REVIEWER:
            return
        revision = data.get("revision", 0)
        llm_request = data["request"]
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id)
            row = self._require_analysis_row(session, run_id=run_id, idempotency_key=request.idempotency_key)
            proposer_checksum = self._checksum(json.loads(llm_request.context[-1].content))
            self._transition(session, run, request, WorkflowEventType.ANALYSIS_AGENT_COMPLETED, "analysis proposer completed", {"proposer_output_checksum": proposer_checksum})
            reviewer_started = self._transition(session, run, request, WorkflowEventType.ANALYSIS_REVIEWER_STARTED, "analysis reviewer started", {"proposer_output_checksum": proposer_checksum, "role": "phase_reviewer", "attempt": revision, "revision": revision})
            now = self.now()
            invocation = LlmInvocationModel(id="llm-invocation-" + uuid4().hex[:12], run_id=run_id, stage_id=None, idempotency_key=f"{request.idempotency_key}:reviewer:{revision}", request_checksum=self._checksum(llm_request.model_dump(mode="json")), input_hashes=[request.artifact_set_checksum, proposer_checksum], correlation_id=request.correlation_id or uuid4().hex, actor=request.actor, role="phase_reviewer", task_type="analysis_review", provider="azure_openai", deployment_alias="pending", prompt_version="analysis_reviewer_v1", schema_version="analysis-schema-registry-v1", pricing_version="unknown", stage="analysis", redacted_summary=None, status="in_progress", failure_code=None, artifact_ids=[], artifact_checksums={}, state_version=reviewer_started.next_state_version, event_sequence=reviewer_started.event_sequence, retries=0, latency_ms=None, started_at=now, completed_at=None, created_at=now)
            session.add(invocation)
            row.reviewer_invocation_id = invocation.id
            started = self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_STARTED, "analysis reviewer LLM invocation started", {"invocation_id": invocation.id, "role": "phase_reviewer", "attempt": revision, "revision": revision})
            invocation.state_version = started.next_state_version; invocation.event_sequence = started.event_sequence

    def _on_analysis_invocation_after(self, run_id, request, data):
        role = data.get("role")
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id)
            row = self._require_analysis_row(session, run_id=run_id, idempotency_key=request.idempotency_key)
            if role is LlmRole.PHASE_PROPOSER:
                invocation = session.get(LlmInvocationModel, row.invocation_id)
                transition = self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_COMPLETED, "analysis proposer LLM invocation completed", {"invocation_id": invocation.id, "role": "phase_proposer"})
                finished = self.now(); response = data.get("response"); invocation.status = "completed"; invocation.completed_at = finished; invocation.latency_ms = self._latency_ms(finished, invocation.started_at); invocation.provider_request_id = getattr(response, "provider_request_id", None); invocation.deployment_alias = getattr(response, "model_deployment_alias", invocation.deployment_alias); invocation.prompt_version = getattr(response, "prompt_version", None) or invocation.prompt_version; invocation.schema_version = getattr(response, "schema_version", None) or invocation.schema_version; invocation.pricing_version = getattr(response, "pricing_version", None) or invocation.pricing_version; invocation.state_version = transition.next_state_version; invocation.event_sequence = transition.event_sequence
            elif role is LlmRole.PHASE_REVIEWER:
                revision = data.get("revision", 0)
                invocation = session.scalar(select(LlmInvocationModel).where(LlmInvocationModel.run_id == run_id, LlmInvocationModel.idempotency_key == f"{request.idempotency_key}:reviewer:{revision}"))
                transition = self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_COMPLETED, "analysis reviewer LLM invocation completed", {"invocation_id": invocation.id, "role": "phase_reviewer"})
                finished = self.now(); response = data.get("response"); invocation.status = "completed"; invocation.completed_at = finished; invocation.latency_ms = self._latency_ms(finished, invocation.started_at); invocation.provider_request_id = getattr(response, "provider_request_id", None); invocation.deployment_alias = getattr(response, "model_deployment_alias", invocation.deployment_alias); invocation.prompt_version = getattr(response, "prompt_version", None) or invocation.prompt_version; invocation.schema_version = getattr(response, "schema_version", None) or invocation.schema_version; invocation.pricing_version = getattr(response, "pricing_version", None) or invocation.pricing_version; invocation.state_version = transition.next_state_version; invocation.event_sequence = transition.event_sequence
                completed = self._transition(session, run, request, WorkflowEventType.ANALYSIS_REVIEWER_COMPLETED, "analysis reviewer completed", {"invocation_id": invocation.id})
                invocation.state_version = completed.next_state_version; invocation.event_sequence = completed.event_sequence

    def _on_analysis_invocation_failed(self, run_id, request, data):
        role = data.get("role")
        if role is not LlmRole.PHASE_REVIEWER:
            return
        revision = data.get("revision", 0)
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id)
            row = self._require_analysis_row(session, run_id=run_id, idempotency_key=request.idempotency_key)
            invocation = session.scalar(select(LlmInvocationModel).where(LlmInvocationModel.run_id == run_id, LlmInvocationModel.idempotency_key == f"{request.idempotency_key}:reviewer:{revision}"))
            if invocation:
                error = data.get("error")
                code = getattr(error, "code", None)
                transition = self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_FAILED, "analysis reviewer LLM invocation failed", {"invocation_id": invocation.id, "role": "phase_reviewer", "attempt": revision, "revision": revision, "error_code": getattr(code, "value", None) or "LLM_PROVIDER_FAILED"})
                invocation.status = "failed"; invocation.failure_code = getattr(code, "value", None) or "LLM_PROVIDER_FAILED"; invocation.failure_subtype = getattr(error, "failure_subtype", None); invocation.failure_stage = "phase_reviewer"; invocation.completed_at = self.now(); invocation.state_version = transition.next_state_version; invocation.event_sequence = transition.event_sequence

    @staticmethod
    def _read_artifact(store, artifact_id):
        stored = store.read_artifact_by_id(artifact_id)
        return AnalysisArtifact(stored.ref.artifact_id, stored.ref.checksum, stored.content)

    def _complete(self, run_id, request, request_checksum, package):
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id)
            row = self._require_analysis_row(session, run_id=run_id, idempotency_key=request.idempotency_key)
            invocation = session.get(LlmInvocationModel, row.invocation_id)
            store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            package_json = package.model_dump(mode="json")
            discovery = session.scalar(select(DiscoveryEvidenceModel).where(DiscoveryEvidenceModel.run_id == run_id, DiscoveryEvidenceModel.status == "completed").order_by(DiscoveryEvidenceModel.created_at.desc()))
            parity = session.scalar(select(ParityBaselineEvidenceModel).where(ParityBaselineEvidenceModel.run_id == run_id, ParityBaselineEvidenceModel.status == "completed").order_by(ParityBaselineEvidenceModel.created_at.desc()))
            g03 = session.scalar(select(G03ApprovalModel).where(G03ApprovalModel.run_id == run_id, G03ApprovalModel.status == "approved").order_by(G03ApprovalModel.updated_at.desc()))
            input_manifest = json.dumps({"run_id": run_id, "discovery_evidence_id": discovery.id if discovery else None, "parity_evidence_id": parity.id if parity else None, "baseline_g03_evidence_id": g03.id if g03 else None, "artifact_ids": [item.artifact_id for item in request.prerequisite_artifacts], "checksums": {item.artifact_id: item.checksum for item in request.prerequisite_artifacts}, "artifact_set_checksum": request.artifact_set_checksum, "workspace_source_snapshot_identity": run.workspace_aliases, "prompt_versions": {"proposer": "analysis_agent_v1", "reviewer": "analysis_reviewer_v1"}, "schema_versions": {"proposer": "analysis-schema-registry-v1", "reviewer": "analysis-schema-registry-v1"}, "raw_content_stored": False}, sort_keys=True)
            narrative_json = json.dumps(package.narrative.model_dump(mode="json"), sort_keys=True)
            markdown = "\n".join([
                "# Analysis", "", package.narrative.summary, "",
                "## Scope and limitations", "This report interprets registered deterministic discovery and parity evidence. It does not author patches, approve G04, or establish unsupported project truth.", "",
                "## Deterministic evidence overview", f"Input artifact set: `{package.artifact_set_checksum}`", f"Artifacts: {len(package.deterministic_input_artifacts)}", "",
                "## Risk groups", *(f"- {risk.get('name', 'risk')}: {risk.get('description', '')}" for risk in package.narrative.risk_groups), "",
                "## Unresolved questions", *(f"- {question}" for question in package.narrative.unresolved_questions), "",
                f"**Confidence:** {package.narrative.evidence_confidence}", f"**Recommended next action:** {package.narrative.recommended_next_action}", "",
                "## Reviewer", f"Decision: {package.reviewer.decision.value}", *(f"- {note}" for note in package.reviewer.notes), "",
                "## Provenance", f"Proposer: {package.model_provenance}", f"Reviewer: {package.reviewer_provenance}", f"Prompt/schema: {package.prompt_version} / {package.schema_version}", "",
                "## Usage", f"Proposer: {package.usage}", f"Reviewer: {package.reviewer_usage}",
            ]) + "\n"
            usage_json = json.dumps(package.usage, sort_keys=True)
            proposer_json = json.dumps({"narrative": package.narrative.model_dump(mode="json"), "proposer_output_checksum": package.proposer_output_checksum}, sort_keys=True)
            reviewer_json = json.dumps({"review": package.reviewer.model_dump(mode="json"), "reviewer_output_checksum": package.reviewer_output_checksum}, sort_keys=True)
            final_json = json.dumps({"narrative": package.narrative.model_dump(mode="json"), "review": package.reviewer.model_dump(mode="json"), "proposer_output_checksum": package.proposer_output_checksum, "reviewer_output_checksum": package.reviewer_output_checksum, "revision_count": package.revision_count}, sort_keys=True)
            package_json_text = json.dumps({"package": package_json, "gate_id": "G04", "gate_version": "g04-v1", "artifact_set_checksum": package.artifact_set_checksum, "final_reviewed_analysis_checksum": self._checksum(json.loads(final_json))}, sort_keys=True)
            artifacts = [
                self._artifact(session, store, run_id, "02_analysis/model_input_manifest.json", input_manifest, ArtifactType.JSON),
                self._artifact(session, store, run_id, "02_analysis/structured_response.json", narrative_json, ArtifactType.JSON),
                self._artifact(session, store, run_id, "02_analysis/proposer_output.json", proposer_json, ArtifactType.JSON),
                self._artifact(session, store, run_id, "02_analysis/reviewer_output.json", reviewer_json, ArtifactType.JSON),
                self._artifact(session, store, run_id, "02_analysis/final_reviewed_analysis.json", final_json, ArtifactType.JSON),
                self._artifact(session, store, run_id, "02_analysis/human_analysis.md", markdown, ArtifactType.MARKDOWN),
                self._artifact(session, store, run_id, "02_analysis/usage_cost.json", usage_json, ArtifactType.JSON),
                self._artifact(session, store, run_id, "02_analysis/g04_package.json", package_json_text, ArtifactType.JSON),
            ]
            ids = [item.ref.artifact_id for item in artifacts]
            checks = {item.ref.artifact_id: item.ref.checksum for item in artifacts}
            gate_event = self._transition(session, run, request, WorkflowEventType.G04_CREATED, "G04 created", {"artifact_ids": ids, "artifact_set_checksum": package.artifact_set_checksum, "package_checksum": checks[ids[-1]]})
            now = self.now()
            invocation.status = "completed"; invocation.deployment_alias = package.model_provenance.get("provider", "azure-openai"); invocation.prompt_version = package.prompt_version; invocation.schema_version = package.schema_version; invocation.pricing_version = package.usage.get("pricing_version", "unknown"); invocation.retries = package.usage.get("retry_count", 0); invocation.artifact_ids = ids; invocation.artifact_checksums = checks; invocation.state_version = gate_event.next_state_version; invocation.event_sequence = gate_event.event_sequence; invocation.completed_at = now
            usage = package.usage
            session.add(UsageCostRecordModel(id="usage-cost-" + uuid4().hex[:12], invocation_id=invocation.id, run_id=run_id, stage_id=None, pricing_version=package.usage.get("pricing_version", "unknown"), input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0), total_tokens=usage.get("total_tokens", 0), input_price_per_million=usage.get("input_price_per_million", 0), output_price_per_million=usage.get("output_price_per_million", 0), input_cost_usd=usage.get("input_cost_usd", 0), output_cost_usd=usage.get("output_cost_usd", 0), total_cost_usd=usage.get("total_cost_usd", 0), created_at=now))
            reviewer_invocation = session.scalar(select(LlmInvocationModel).where(LlmInvocationModel.run_id == run_id, LlmInvocationModel.idempotency_key == f"{request.idempotency_key}:reviewer:{package.revision_count}"))
            if reviewer_invocation:
                reviewer_invocation.artifact_ids = ids; reviewer_invocation.artifact_checksums = checks; reviewer_invocation.pricing_version = package.reviewer_usage.get("pricing_version", "unknown"); reviewer_invocation.state_version = gate_event.next_state_version; reviewer_invocation.event_sequence = gate_event.event_sequence
            reviewer_usage = package.reviewer_usage
            if reviewer_invocation and session.scalar(select(UsageCostRecordModel).where(UsageCostRecordModel.invocation_id == reviewer_invocation.id)) is None:
                session.add(UsageCostRecordModel(id="usage-cost-" + uuid4().hex[:12], invocation_id=reviewer_invocation.id, run_id=run_id, stage_id=None, pricing_version=reviewer_usage.get("pricing_version", "unknown"), input_tokens=reviewer_usage.get("input_tokens", 0), output_tokens=reviewer_usage.get("output_tokens", 0), total_tokens=reviewer_usage.get("total_tokens", 0), input_price_per_million=reviewer_usage.get("input_price_per_million", 0), output_price_per_million=reviewer_usage.get("output_price_per_million", 0), input_cost_usd=reviewer_usage.get("input_cost_usd", 0), output_cost_usd=reviewer_usage.get("output_cost_usd", 0), total_cost_usd=reviewer_usage.get("total_cost_usd", 0), created_at=now))
            row.status = "completed"; row.artifact_ids = ids; row.artifact_checksums = checks; row.package = package_json; row.state_version = gate_event.next_state_version; row.event_sequence = gate_event.event_sequence; row.updated_at = now
            gate = G04ApprovalModel(id="g04-" + uuid4().hex[:12], run_id=run_id, gate_id="G04", gate_version="g04-v1", idempotency_key="gate:" + request.idempotency_key, actor=request.actor, status="pending", decision=None, package_checksum=checks[ids[-1]], artifact_set_checksum=package.artifact_set_checksum, workspace_fingerprint=request.workspace_fingerprint, plan_version=request.plan_version, state_version=gate_event.next_state_version, event_sequence=gate_event.event_sequence, artifact_ids=ids, comment=None, stale_reason=None, created_at=now, updated_at=now)
            session.add(gate); session.flush()
            return self._analysis_dto(session, row)

    def _fail(self, run_id, request, request_checksum, error_code, details=None):
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id); row = self._require_analysis_row(session, run_id=run_id, idempotency_key=request.idempotency_key); store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            artifact = self._artifact(session, store, run_id, "02_analysis/analysis_error_redacted.json", json.dumps({"error_code": error_code, **(details or {}), "raw_provider_error_stored": False}, sort_keys=True), ArtifactType.JSON)
            if error_code.startswith("ANALYSIS_REVIEW") or (details or {}).get("failure_stage") == "phase_reviewer":
                self._transition(session, run, request, WorkflowEventType.ANALYSIS_REVIEWER_FAILED, "analysis reviewer failed", {"error_code": error_code, "artifact_id": artifact.ref.artifact_id})
            transition = self._transition(session, run, request, WorkflowEventType.ANALYSIS_AGENT_FAILED, "analysis phase failed", {"error_code": error_code, "artifact_id": artifact.ref.artifact_id, "role": (details or {}).get("failure_stage")})
            details = details or {}; now = self.now(); row.status = "failed"; row.error_code = error_code; row.cause_code = details.get("cause_code") or (error_code if error_code.startswith("LLM_") else None); row.failure_subtype = details.get("failure_subtype"); row.failure_stage = details.get("failure_stage"); row.failure_origin = details.get("failure_origin"); row.technical_stage = details.get("technical_stage"); row.transport_started = details.get("transport_started"); row.provider_request_id = details.get("provider_request_id"); row.retryable = details.get("retryable", False); row.failed_at = now; row.artifact_ids = [artifact.ref.artifact_id]; row.artifact_checksums = {artifact.ref.artifact_id: artifact.ref.checksum}; row.state_version = transition.next_state_version; row.event_sequence = transition.event_sequence; row.updated_at = now
            failed_id = row.reviewer_invocation_id if details.get("failure_stage") == "phase_reviewer" else row.proposer_invocation_id
            row.failed_invocation_id = failed_id
            invocation = session.get(LlmInvocationModel, failed_id) if failed_id else None
            if invocation is not None:
                invocation.status = "failed"; invocation.failure_code = row.cause_code or error_code; invocation.failure_subtype = details.get("failure_subtype"); invocation.retries = details.get("retry_count", 0); invocation.provider_http_status = details.get("provider_http_status"); invocation.provider_error_code = details.get("provider_error_code"); invocation.sanitized_provider_message = details.get("sanitized_provider_message"); invocation.provider_request_id = details.get("provider_request_id"); invocation.failure_stage = details.get("failure_stage"); invocation.transport_exception_type = details.get("transport_exception_type"); invocation.endpoint_host = details.get("endpoint_host"); invocation.endpoint_path = details.get("endpoint_path"); invocation.retryable = details.get("retryable", False); invocation.response_received = details.get("response_received"); invocation.response_content_type = details.get("response_content_type"); invocation.response_bytes = details.get("response_bytes"); invocation.response_sha256 = details.get("response_sha256"); invocation.response_kind = details.get("response_kind"); invocation.transport_started = details.get("transport_started"); invocation.deployment_alias = details.get("resolved_deployment") or invocation.deployment_alias; invocation.artifact_ids = row.artifact_ids; invocation.artifact_checksums = row.artifact_checksums; invocation.state_version = transition.next_state_version; invocation.event_sequence = transition.event_sequence; invocation.completed_at = now
            if details.get("failure_stage") == "phase_reviewer":
                reviewer = session.get(LlmInvocationModel, row.reviewer_invocation_id) if row.reviewer_invocation_id else None
                if reviewer is not None:
                    reviewer.status = "failed"; reviewer.failure_code = error_code; reviewer.failure_subtype = details.get("failure_subtype"); reviewer.provider_http_status = details.get("provider_http_status"); reviewer.provider_error_code = details.get("provider_error_code"); reviewer.sanitized_provider_message = details.get("sanitized_provider_message"); reviewer.provider_request_id = details.get("provider_request_id"); reviewer.failure_stage = "phase_reviewer"; reviewer.artifact_ids = row.artifact_ids; reviewer.artifact_checksums = row.artifact_checksums; reviewer.completed_at = now; reviewer.latency_ms = self._latency_ms(now, reviewer.started_at); row.failed_invocation_id = reviewer.id
            session.flush(); return self._analysis_dto(session, row)

    def _artifact(self, session, store, run_id, path, content, artifact_type):
        artifact = store.write_text_artifact(run_id, path, content, artifact_type, created_by="analysis-evidence", input_hashes={"artifact_set": "analysis"}, policy_version="s2-f04-i02")
        session.add(ArtifactMetadataModel(id="metadata-" + artifact.ref.artifact_id, run_id=run_id, stage_id=None, artifact_type=artifact.ref.artifact_type.value, relative_path=artifact.ref.relative_path, checksum=artifact.ref.checksum, created_at=artifact.ref.created_at))
        return artifact

    def _verify_package_integrity(self, run, gate) -> None:
        try:
            store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            package_id = gate.artifact_ids[-1]
            if store.read_artifact_by_id(package_id).ref.checksum != gate.package_checksum:
                raise AnalysisEvidenceError("G04_PACKAGE_INTEGRITY_FAILED", "The G04 package checksum no longer matches stored evidence.", 409)
        except AnalysisEvidenceError:
            raise
        except Exception as error:
            raise AnalysisEvidenceError("G04_PACKAGE_INTEGRITY_FAILED", "The G04 package evidence is unavailable or invalid.", 409) from error

    def _record_stale_gate(self, session, run, gate, payload, actor, reason) -> None:
        """Append a stale record and durable event; never mutate the old decision."""
        request = AnalysisRequest(run_id=run.id, expected_state_version=run.state_version, idempotency_key=payload.idempotency_key + ":stale", actor=actor, prerequisite_artifacts=[{"artifact_id": "stale-marker", "checksum": "sha256:" + "0" * 64}])
        transition = self._transition(session, run, request, WorkflowEventType.G04_STALE, "G04 binding marked stale", {"reason": reason, "gate_version": gate.gate_version})
        now = self.now()
        session.add(G04ApprovalModel(id="g04-" + uuid4().hex[:12], run_id=run.id, gate_id="G04", gate_version=gate.gate_version, idempotency_key="stale:" + payload.idempotency_key, actor=actor, status="stale", decision="stale", package_checksum=gate.package_checksum, artifact_set_checksum=gate.artifact_set_checksum, workspace_fingerprint=gate.workspace_fingerprint, plan_version=gate.plan_version, state_version=transition.next_state_version, event_sequence=transition.event_sequence, artifact_ids=gate.artifact_ids, comment=None, stale_reason=reason, created_at=now, updated_at=now))
        session.flush()
        session.commit()

    def require_approved_g04(self, run_id: str, *, expected_state_version: int, workspace_fingerprint: str | None, plan_version: str | None, actor: str) -> G04ApprovalModel:
        """Guard any downstream protected transition with the active G04 package bindings."""
        with self.scope() as session:
            run = self._authorized_run(session, run_id, actor)
            if run.state_version != expected_state_version:
                raise AnalysisEvidenceError("STALE_STATE_VERSION", "The protected transition state version is stale.", 409)
            gate = session.scalar(select(G04ApprovalModel).where(G04ApprovalModel.run_id == run_id, G04ApprovalModel.gate_id == "G04").order_by(G04ApprovalModel.state_version.desc(), G04ApprovalModel.created_at.desc()))
            if gate is None or gate.status != "approved":
                raise AnalysisEvidenceError("G04_APPROVAL_REQUIRED", "An approved current G04 gate is required before protected progression.", 409)
            if gate.workspace_fingerprint != workspace_fingerprint or gate.plan_version != plan_version:
                raise AnalysisEvidenceError("G04_STALE", "The approved G04 bindings no longer match protected progression.", 409)
            self._verify_package_integrity(run, gate)
            return gate

    def _authorized_run(self, session, run_id, actor):
        run = session.get(MigrationRunModel, run_id)
        if run is None: raise AnalysisEvidenceError("RUN_NOT_FOUND", "Migration run does not exist.", 404)
        if run.actor and run.actor != actor: raise AnalysisEvidenceError("RUN_NOT_AUTHORIZED", "Authenticated actor is not authorized for this run.", 403)
        return run

    def _require_analysis_row(self, session, *, run_id: str, idempotency_key: str) -> AnalysisMetadataModel:
        row = session.scalar(select(AnalysisMetadataModel).where(
            AnalysisMetadataModel.run_id == run_id,
            AnalysisMetadataModel.idempotency_key == idempotency_key,
        ))
        if row is None:
            raise AnalysisEvidenceError(
                "ANALYSIS_METADATA_NOT_FOUND",
                "The authoritative Analysis attempt metadata is missing.",
                409,
            )
        return row

    def _require_state(self, run, expected):
        if run.state_version != expected: raise AnalysisEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409)

    def _require_registered_artifacts(self, session, run_id, request):
        rows = {row.id.removeprefix("metadata-"): row for row in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id))}
        for item in request.prerequisite_artifacts:
            if item.artifact_id not in rows: raise AnalysisEvidenceError("PREREQUISITE_ARTIFACT_NOT_FOUND", "A prerequisite artifact is not registered.", 409)
            if rows[item.artifact_id].checksum != item.checksum: raise AnalysisEvidenceError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite checksum does not match.", 409)

    def _canonical_inputs(self, session, run_id: str, client_items):
        discovery = session.scalar(select(DiscoveryEvidenceModel).where(DiscoveryEvidenceModel.run_id == run_id, DiscoveryEvidenceModel.status == "completed").order_by(DiscoveryEvidenceModel.created_at.desc()))
        parity = session.scalar(select(ParityBaselineEvidenceModel).where(ParityBaselineEvidenceModel.run_id == run_id, ParityBaselineEvidenceModel.status.in_(("captured", "completed"))).order_by(ParityBaselineEvidenceModel.created_at.desc()))
        if discovery is None:
            raise AnalysisEvidenceError("DISCOVERY_NOT_COMPLETED", "Discovery evidence is not complete.", 409)
        if parity is None:
            raise AnalysisEvidenceError("PARITY_BASELINE_NOT_COMPLETED", "Parity baseline evidence is not complete.", 409)
        g03 = session.scalar(select(G03ApprovalModel).where(G03ApprovalModel.run_id == run_id, G03ApprovalModel.status == "approved").order_by(G03ApprovalModel.updated_at.desc()))
        ids = sorted(set((discovery.artifact_ids or []) + (parity.artifact_ids or []) + ((g03.artifact_ids or []) if g03 else [])))
        metadata = {item.id.removeprefix("metadata-"): item for item in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id))}
        if not ids or any(item_id not in metadata for item_id in ids):
            raise AnalysisEvidenceError("REQUIRED_ANALYSIS_ARTIFACT_MISSING", "Canonical deterministic analysis evidence is incomplete.", 409)
        run = session.get(MigrationRunModel, run_id)
        store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root)) if run else None
        for item_id in ids:
            try:
                stored = store.read_artifact_by_id(item_id) if store else None
                if stored is None or stored.ref.checksum != metadata[item_id].checksum:
                    raise AnalysisEvidenceError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "Stored artifact content does not match registered evidence.", 409)
            except AnalysisEvidenceError:
                raise
            except Exception as error:
                raise AnalysisEvidenceError("REQUIRED_ANALYSIS_ARTIFACT_MISSING", "A canonical analysis artifact is not retrievable.", 409) from error
        canonical = [AnalysisArtifactInput(artifact_id=item_id, checksum=metadata[item_id].checksum) for item_id in ids]
        if client_items:
            try:
                client_items = [AnalysisArtifactInput.model_validate(item) for item in client_items]
            except Exception as error:
                raise AnalysisEvidenceError("ANALYSIS_INPUT_SET_MISMATCH", "The client artifact list is invalid.", 409) from error
            for item in client_items:
                if item.artifact_id in metadata and item.checksum != metadata[item.artifact_id].checksum:
                    raise AnalysisEvidenceError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite checksum does not match.", 409)
            client = sorted((item.artifact_id, item.checksum) for item in client_items)
            server = sorted((item.artifact_id, item.checksum) for item in canonical)
            if client != server:
                raise AnalysisEvidenceError("ANALYSIS_INPUT_SET_MISMATCH", "The client artifact list does not match server-derived evidence.", 409)
        return canonical

    @staticmethod
    def _approved_g03(session, run_id: str) -> G03ApprovalModel:
        gate = session.scalar(
            select(G03ApprovalModel)
            .where(G03ApprovalModel.run_id == run_id, G03ApprovalModel.status == "approved")
            .order_by(G03ApprovalModel.updated_at.desc())
        )
        if gate is None:
            raise AnalysisEvidenceError(
                "G03_APPROVAL_REQUIRED",
                "An approved G03 baseline boundary is required.",
                409,
            )
        if not gate.sandbox_fingerprint:
            raise AnalysisEvidenceError(
                "G03_WORKSPACE_FINGERPRINT_MISSING",
                "The approved G03 package has no baseline sandbox fingerprint.",
                409,
            )
        return gate

    @staticmethod
    def _authoritative_workspace_fingerprint(
        gate: G03ApprovalModel,
        supplied_fingerprint: str | None,
    ) -> str:
        authoritative = gate.sandbox_fingerprint
        if supplied_fingerprint is not None and supplied_fingerprint != authoritative:
            raise AnalysisEvidenceError(
                "ANALYSIS_WORKSPACE_FINGERPRINT_MISMATCH",
                "The supplied workspace fingerprint does not match the approved G03 baseline.",
                409,
            )
        return authoritative

    def _transition(self, session, run, request, event, reason, payload=None, **state_changes):
        try:
            semantic = payload or {}
            role = semantic.get("role", "analysis")
            invocation = semantic.get("invocation_id", "")
            # Same semantic phase delivery replays; independent proposer and
            # reviewer events never collide merely because they share a type.
            key = f"{request.idempotency_key}:analysis:{role}:{invocation}:{event.value}"
            return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=run.state_version, idempotency_key=key, event_type=event, actor=request.actor, reason=reason, occurred_at=self.now(), payload=payload, **state_changes))
        except StaleStateVersionError as error:
            raise AnalysisEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409) from error
        except TransitionError as error:
            raise AnalysisEvidenceError("ILLEGAL_STATE_TRANSITION", "The requested workflow transition is not legal.", 409) from error

    @staticmethod
    def _checksum(value):
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _latency_ms(finished: datetime, started: datetime | None) -> int | None:
        normalized_started = normalize_persisted_utc(started)
        normalized_finished = normalize_persisted_utc(finished)
        if normalized_started is None or normalized_finished is None:
            return None
        return max(0, int((normalized_finished - normalized_started).total_seconds() * 1000))

    def _analysis_dto(self, session, row, replay=False):
        gate = session.scalar(select(G04ApprovalModel).where(G04ApprovalModel.run_id == row.run_id).order_by(G04ApprovalModel.state_version.desc(), G04ApprovalModel.created_at.desc()))
        attempts = session.scalars(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == row.run_id).order_by(AnalysisMetadataModel.created_at.asc())).all()
        history = [{"attempt_id": item.id, "status": item.status, "error_code": item.error_code, "cause_code": item.cause_code, "failure_subtype": item.failure_subtype, "failure_stage": item.failure_stage, "retryable": bool(item.retryable), "correlation_id": item.correlation_id, "failed_at": item.failed_at.isoformat() if item.failed_at else None} for item in attempts]
        return AnalysisResponse(run_id=row.run_id, analysis_id=row.id, status=row.status, package=row.package, artifact_ids=row.artifact_ids, artifact_checksums=row.artifact_checksums, artifact_links={item: f"/api/v1/artifacts/{item}" for item in row.artifact_ids}, package_checksum=gate.package_checksum if gate else None, gate_status=gate.status if gate else "blocked", gate_decision=gate.decision if gate else None, error_code=row.error_code, cause_code=row.cause_code, failure_subtype=row.failure_subtype, failure_stage=row.failure_stage, retryable=bool(row.retryable), correlation_id=row.correlation_id, proposer_invocation_id=row.proposer_invocation_id, reviewer_invocation_id=row.reviewer_invocation_id, failed_invocation_id=row.failed_invocation_id, failure_origin=getattr(row, "failure_origin", None), technical_stage=getattr(row, "technical_stage", None), transport_started=getattr(row, "transport_started", None), provider_request_id=getattr(row, "provider_request_id", None), attempt_history=history, state_version=row.state_version, event_sequence=row.event_sequence, idempotent_replay=replay)

    @staticmethod
    def _decision_dto(row, replay=False):
        return G04DecisionResponse(run_id=row.run_id, gate_version=row.gate_version, decision=G04Decision(row.decision), status=row.status, accepted=row.status == "approved", package_checksum=row.package_checksum, state_version=row.state_version, event_sequence=row.event_sequence, idempotent_replay=replay)
