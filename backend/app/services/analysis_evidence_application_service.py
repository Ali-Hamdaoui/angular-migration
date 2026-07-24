"""Persistence and API projection for the S2-F04 Analysis/G04 boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.api.analysis_contracts import AnalysisResponse, G04DecisionResponse
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.analysis import AnalysisPackage, AnalysisRequest, G04Decision, G04DecisionRequest
from app.domain.contracts import ArtifactType, WorkflowEventType
from app.repositories.models import (
    AnalysisMetadataModel,
    ArtifactMetadataModel,
    G04ApprovalModel,
    G03ApprovalModel,
    LlmInvocationModel,
    MigrationRunModel,
    UsageCostRecordModel,
)
from app.repositories.session import session_scope
from app.services.analysis_application_service import AnalysisAgentService, AnalysisApplicationError, AnalysisArtifact
from app.state.transition_service import StateTransitionService, TransitionRequest, TransitionError, StaleStateVersionError


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
        request = AnalysisRequest(
            run_id=run_id,
            expected_state_version=payload.expected_state_version,
            idempotency_key=payload.idempotency_key,
            actor=actor,
            prerequisite_artifacts=payload.prerequisite_artifacts,
            workspace_fingerprint=payload.workspace_fingerprint,
            plan_version=payload.plan_version,
            correlation_id=payload.correlation_id,
        )
        request_checksum = self._checksum(request.model_dump(mode="json"))
        with self.scope() as session:
            existing = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.idempotency_key == request.idempotency_key))
            if existing:
                if existing.request_checksum != request_checksum:
                    raise AnalysisEvidenceError("IDEMPOTENCY_KEY_REUSED", "Idempotency key was used with a different payload.", 409)
                return self._analysis_dto(session, existing, replay=True)
            run = self._authorized_run(session, run_id, actor)
            self._require_state(run, request.expected_state_version)
            if session.scalar(select(G03ApprovalModel).where(G03ApprovalModel.run_id == run_id, G03ApprovalModel.status == "approved")) is None:
                raise AnalysisEvidenceError("G03_APPROVAL_REQUIRED", "An approved G03 baseline boundary is required.", 409)
            self._require_registered_artifacts(session, run_id, request)
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
                invocation_id=invocation.id, artifact_ids=[], artifact_checksums={}, package=None,
                state_version=started.next_state_version, event_sequence=started.event_sequence,
                created_at=now, updated_at=now,
            )
            session.add(row)
            session.flush()

        deployment = None
        try:
            agent = self._agent(run_id, request)
            deployment = getattr(getattr(agent, "gateway", None), "deployment_name", None)
            if deployment:
                with self.scope() as session:
                    row = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.idempotency_key == request.idempotency_key))
                    session.get(LlmInvocationModel, row.invocation_id).deployment_alias = deployment
                with self.scope() as session:
                    run = session.get(MigrationRunModel, run_id)
                    transition = self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_STARTED, "analysis proposer LLM invocation started", {"invocation_id": row.invocation_id})
                    invocation = session.get(LlmInvocationModel, row.invocation_id)
                    invocation.state_version = transition.next_state_version; invocation.event_sequence = transition.event_sequence
            package = agent.generate(request)
            if deployment:
                with self.scope() as session:
                    run = session.get(MigrationRunModel, run_id)
                    transition = self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_COMPLETED, "analysis proposer LLM invocation completed", {"invocation_id": row.invocation_id})
                    invocation = session.get(LlmInvocationModel, row.invocation_id)
                    invocation.state_version = transition.next_state_version; invocation.event_sequence = transition.event_sequence
        except AnalysisApplicationError as error:
            if deployment:
                with self.scope() as session:
                    run = session.get(MigrationRunModel, run_id)
                    self._transition(session, run, request, WorkflowEventType.LLM_INVOCATION_FAILED, "analysis proposer LLM invocation failed", {"invocation_id": row.invocation_id, "error_code": error.code})
            return self._fail(run_id, request, request_checksum, error.code, error.details)
        except Exception:
            return self._fail(run_id, request, request_checksum, "ANALYSIS_DEPENDENCY_FAILED")
        return self._complete(run_id, request, request_checksum, package)

    def get(self, run_id: str, actor: str) -> AnalysisResponse | None:
        with self.scope() as session:
            run = self._authorized_run(session, run_id, actor)
            row = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id).order_by(AnalysisMetadataModel.created_at.desc()))
            return self._analysis_dto(session, row) if row else None

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
            transition = self._transition(session, run, domain_request, event_type, "G04 decision recorded")
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
        return AnalysisAgentService(gateway=AzureOpenAILLMGateway(settings=get_settings(), registry=registry), artifact_reader=lambda artifact_id: self._read_artifact(store, artifact_id))

    @staticmethod
    def _read_artifact(store, artifact_id):
        stored = store.read_artifact_by_id(artifact_id)
        return AnalysisArtifact(stored.ref.artifact_id, stored.ref.checksum, stored.content)

    def _complete(self, run_id, request, request_checksum, package):
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id)
            row = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.idempotency_key == request.idempotency_key))
            invocation = session.get(LlmInvocationModel, row.invocation_id)
            store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            package_json = package.model_dump(mode="json")
            input_manifest = json.dumps({"run_id": run_id, "artifact_ids": [item.artifact_id for item in request.prerequisite_artifacts], "checksums": {item.artifact_id: item.checksum for item in request.prerequisite_artifacts}, "raw_content_stored": False}, sort_keys=True)
            narrative_json = json.dumps(package.narrative.model_dump(mode="json"), sort_keys=True)
            markdown = "# Analysis\n\n" + package.narrative.summary + "\n"
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
            completed = self._transition(session, run, request, WorkflowEventType.ANALYSIS_AGENT_COMPLETED, "analysis proposer completed", {"artifact_ids": ids, "proposer_output_checksum": package.proposer_output_checksum})
            reviewer_started = self._transition(session, run, request, WorkflowEventType.ANALYSIS_REVIEWER_STARTED, "analysis reviewer started", {"proposer_output_checksum": package.proposer_output_checksum})
            reviewer_completed = self._transition(session, run, request, WorkflowEventType.ANALYSIS_REVIEWER_COMPLETED, "analysis reviewer accepted", {"reviewer_output_checksum": package.reviewer_output_checksum, "revision_count": package.revision_count})
            gate_event = self._transition(session, run, request, WorkflowEventType.G04_CREATED, "G04 created", {"artifact_ids": ids, "artifact_set_checksum": package.artifact_set_checksum, "package_checksum": checks[ids[-1]]})
            now = self.now()
            invocation.status = "completed"; invocation.deployment_alias = package.model_provenance.get("provider", "azure-openai"); invocation.prompt_version = package.prompt_version; invocation.schema_version = package.schema_version; invocation.pricing_version = package.usage.get("pricing_version", "unknown"); invocation.retries = package.usage.get("retry_count", 0); invocation.artifact_ids = ids; invocation.artifact_checksums = checks; invocation.state_version = completed.next_state_version; invocation.event_sequence = completed.event_sequence; invocation.completed_at = now
            usage = package.usage
            session.add(UsageCostRecordModel(id="usage-cost-" + uuid4().hex[:12], invocation_id=invocation.id, run_id=run_id, stage_id=None, pricing_version=package.usage.get("pricing_version", "unknown"), input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0), total_tokens=usage.get("total_tokens", 0), input_price_per_million=usage.get("input_price_per_million", 0), output_price_per_million=usage.get("output_price_per_million", 0), input_cost_usd=usage.get("input_cost_usd", 0), output_cost_usd=usage.get("output_cost_usd", 0), total_cost_usd=usage.get("total_cost_usd", 0), created_at=now))
            reviewer_invocation = LlmInvocationModel(id="llm-invocation-" + uuid4().hex[:12], run_id=run_id, stage_id=None, idempotency_key=request.idempotency_key + ":reviewer", request_checksum=package.proposer_output_checksum, input_hashes=[package.artifact_set_checksum, package.proposer_output_checksum], correlation_id=request.correlation_id or uuid4().hex, actor=request.actor, role="phase_reviewer", task_type="analysis_review", provider="azure_openai", deployment_alias=package.reviewer_provenance.get("provider", "azure-openai"), prompt_version=package.reviewer_prompt_version, schema_version=package.reviewer_schema_version, pricing_version=package.reviewer_usage.get("pricing_version", "unknown"), stage="analysis", redacted_summary=None, status="completed", failure_code=None, artifact_ids=ids, artifact_checksums=checks, state_version=reviewer_completed.next_state_version, event_sequence=reviewer_completed.event_sequence, retries=package.reviewer_usage.get("retry_count", 0), latency_ms=None, started_at=now, completed_at=now, created_at=now)
            session.add(reviewer_invocation)
            reviewer_usage = package.reviewer_usage
            session.add(UsageCostRecordModel(id="usage-cost-" + uuid4().hex[:12], invocation_id=reviewer_invocation.id, run_id=run_id, stage_id=None, pricing_version=reviewer_usage.get("pricing_version", "unknown"), input_tokens=reviewer_usage.get("input_tokens", 0), output_tokens=reviewer_usage.get("output_tokens", 0), total_tokens=reviewer_usage.get("total_tokens", 0), input_price_per_million=reviewer_usage.get("input_price_per_million", 0), output_price_per_million=reviewer_usage.get("output_price_per_million", 0), input_cost_usd=reviewer_usage.get("input_cost_usd", 0), output_cost_usd=reviewer_usage.get("output_cost_usd", 0), total_cost_usd=reviewer_usage.get("total_cost_usd", 0), created_at=now))
            row.status = "completed"; row.artifact_ids = ids; row.artifact_checksums = checks; row.package = package_json; row.state_version = gate_event.next_state_version; row.event_sequence = gate_event.event_sequence; row.updated_at = now
            gate = G04ApprovalModel(id="g04-" + uuid4().hex[:12], run_id=run_id, gate_id="G04", gate_version="g04-v1", idempotency_key="gate:" + request.idempotency_key, actor=request.actor, status="pending", decision=None, package_checksum=checks[ids[-1]], artifact_set_checksum=package.artifact_set_checksum, workspace_fingerprint=request.workspace_fingerprint, plan_version=request.plan_version, state_version=gate_event.next_state_version, event_sequence=gate_event.event_sequence, artifact_ids=ids, comment=None, stale_reason=None, created_at=now, updated_at=now)
            session.add(gate); session.flush()
            return self._analysis_dto(session, row)

    def _fail(self, run_id, request, request_checksum, error_code, details=None):
        with self.scope() as session:
            run = session.get(MigrationRunModel, run_id); row = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == run_id, AnalysisMetadataModel.idempotency_key == request.idempotency_key)); invocation = session.get(LlmInvocationModel, row.invocation_id); store = LocalFilesystemArtifactStore(Path(run.artifact_root), fixed_run_root=Path(run.artifact_root))
            artifact = self._artifact(session, store, run_id, "02_analysis/analysis_error_redacted.json", json.dumps({"error_code": error_code, **(details or {}), "raw_provider_error_stored": False}, sort_keys=True), ArtifactType.JSON)
            if error_code.startswith("ANALYSIS_REVIEW"):
                self._transition(session, run, request, WorkflowEventType.ANALYSIS_REVIEWER_FAILED, "analysis reviewer failed", {"error_code": error_code, "artifact_id": artifact.ref.artifact_id})
            transition = self._transition(session, run, request, WorkflowEventType.ANALYSIS_AGENT_FAILED, "analysis agent failed", {"error_code": error_code, "artifact_id": artifact.ref.artifact_id})
            details = details or {}; now = self.now(); row.status = "failed"; row.error_code = error_code; row.artifact_ids = [artifact.ref.artifact_id]; row.artifact_checksums = {artifact.ref.artifact_id: artifact.ref.checksum}; row.state_version = transition.next_state_version; row.event_sequence = transition.event_sequence; row.updated_at = now; invocation.status = "failed"; invocation.failure_code = error_code; invocation.retries = details.get("retry_count", 0); invocation.provider_http_status = details.get("provider_http_status"); invocation.provider_error_code = details.get("provider_error_code"); invocation.sanitized_provider_message = details.get("sanitized_provider_message"); invocation.provider_request_id = details.get("provider_request_id"); invocation.failure_stage = details.get("failure_stage"); invocation.deployment_alias = details.get("resolved_deployment") or invocation.deployment_alias; invocation.artifact_ids = row.artifact_ids; invocation.artifact_checksums = row.artifact_checksums; invocation.state_version = transition.next_state_version; invocation.event_sequence = transition.event_sequence; invocation.completed_at = now
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

    def _require_state(self, run, expected):
        if run.state_version != expected: raise AnalysisEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409)

    def _require_registered_artifacts(self, session, run_id, request):
        rows = {row.id.removeprefix("metadata-"): row for row in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id))}
        for item in request.prerequisite_artifacts:
            if item.artifact_id not in rows: raise AnalysisEvidenceError("PREREQUISITE_ARTIFACT_NOT_FOUND", "A prerequisite artifact is not registered.", 409)
            if rows[item.artifact_id].checksum != item.checksum: raise AnalysisEvidenceError("PREREQUISITE_ARTIFACT_CHECKSUM_MISMATCH", "A prerequisite checksum does not match.", 409)

    def _transition(self, session, run, request, event, reason, payload=None):
        try:
            return StateTransitionService(session).apply_transition(TransitionRequest(run_id=run.id, expected_state_version=run.state_version, idempotency_key=request.idempotency_key + ":" + event.value, event_type=event, actor=request.actor, reason=reason, occurred_at=self.now(), payload=payload))
        except StaleStateVersionError as error:
            raise AnalysisEvidenceError("STALE_STATE_VERSION", "The run state version is stale.", 409) from error
        except TransitionError as error:
            raise AnalysisEvidenceError("ILLEGAL_STATE_TRANSITION", "The requested workflow transition is not legal.", 409) from error

    @staticmethod
    def _checksum(value):
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _analysis_dto(self, session, row, replay=False):
        gate = session.scalar(select(G04ApprovalModel).where(G04ApprovalModel.run_id == row.run_id).order_by(G04ApprovalModel.state_version.desc(), G04ApprovalModel.created_at.desc()))
        return AnalysisResponse(run_id=row.run_id, analysis_id=row.id, status=row.status, package=row.package, artifact_ids=row.artifact_ids, artifact_checksums=row.artifact_checksums, artifact_links={item: f"/api/v1/artifacts/{item}" for item in row.artifact_ids}, package_checksum=gate.package_checksum if gate else None, gate_status=gate.status if gate else "blocked", gate_decision=gate.decision if gate else None, error_code=row.error_code, state_version=row.state_version, event_sequence=row.event_sequence, idempotent_replay=replay)

    @staticmethod
    def _decision_dto(row, replay=False):
        return G04DecisionResponse(run_id=row.run_id, gate_version=row.gate_version, decision=G04Decision(row.decision), status=row.status, accepted=row.status == "approved", package_checksum=row.package_checksum, state_version=row.state_version, event_sequence=row.event_sequence, idempotent_replay=replay)
