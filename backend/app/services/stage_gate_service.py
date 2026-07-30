"""Durable, fingerprint-bound Transformer gate decisions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.contracts import WorkflowEventType
from app.domain.transformation import StageGateDecisionRequest, StageGateId, TransformationNode
from app.repositories.models import (
    StageGateDecisionModel,
    StageGatePackageModel,
    TransformationContinuationModel,
)
from app.state import StateTransitionService


class StageGateError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_NEXT_NODE = {
    StageGateId.G07.value: TransformationNode.BOOTSTRAP_INSTALL.value,
    StageGateId.G08.value: TransformationNode.FINAL_INSTALL.value,
    StageGateId.G09.value: TransformationNode.CREATE_G12.value,
    StageGateId.G10.value: TransformationNode.APPLY_REPAIR.value,
    StageGateId.G11.value: TransformationNode.CREATE_G09.value,
    StageGateId.G12.value: TransformationNode.SEAL_STAGE.value,
}


class StageGateService:
    def create(
        self,
        session: Session,
        continuation: TransformationContinuationModel,
        *,
        gate_id: str,
        package_artifact_id: str,
        package_checksum: str,
        artifact_set_checksum: str,
        workspace_fingerprint: str,
        now: datetime | None = None,
    ) -> StageGatePackageModel:
        StageGateId(gate_id)
        existing = session.scalar(
            select(StageGatePackageModel).where(
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == gate_id,
                StageGatePackageModel.status == "pending",
            )
        )
        if existing is not None:
            if (
                existing.package_checksum != package_checksum
                or existing.workspace_fingerprint != workspace_fingerprint
            ):
                raise StageGateError("GATE_PACKAGE_CONFLICT", "Pending gate package binding changed")
            return existing
        created_at = now or datetime.now(UTC)
        latest = session.scalar(
            select(StageGatePackageModel.gate_version)
            .where(
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == gate_id,
            )
            .order_by(StageGatePackageModel.gate_version.desc())
            .limit(1)
        )
        package = StageGatePackageModel(
            id=f"gate-package-{uuid4().hex[:12]}",
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            gate_id=gate_id,
            gate_version=(latest or 0) + 1,
            status="pending",
            package_artifact_id=package_artifact_id,
            package_checksum=package_checksum,
            artifact_set_checksum=artifact_set_checksum,
            plan_id=continuation.plan_id,
            plan_version=1,
            stage_plan_id=continuation.stage_plan_id,
            stage_plan_checksum=continuation.stage_plan_checksum,
            workspace_fingerprint=workspace_fingerprint,
            expected_state_version=continuation.state_version + 1,
            created_at=created_at,
        )
        session.add(package)
        continuation.status = "waiting_gate"
        continuation.current_node = f"wait_{gate_id.lower()}"
        continuation.worker_id = None
        continuation.lease_expires_at = None
        continuation.state_version += 1
        continuation.updated_at = created_at
        session.flush()
        StateTransitionService(session).append_audit_event(
            run_id=continuation.run_id,
            idempotency_key=f"{package.id}:created",
            event_type=WorkflowEventType[f"{gate_id}_CREATED"],
            actor="transformer",
            reason=f"{gate_id} evidence package created",
            occurred_at=created_at,
            payload={"stage_id": continuation.current_stage_id, "package_checksum": package_checksum},
        )
        return package

    def decide(
        self,
        session: Session,
        continuation: TransformationContinuationModel,
        gate_id: str,
        request: StageGateDecisionRequest,
        *,
        actor: str,
        observed_workspace_fingerprint: str | None = None,
        now: datetime | None = None,
    ) -> StageGateDecisionModel:
        StageGateId(gate_id)
        checksum = self._checksum(
            {"run_id": continuation.run_id, "gate_id": gate_id, "actor": actor, **request.model_dump(mode="json")}
        )
        existing = session.scalar(
            select(StageGateDecisionModel).where(
                StageGateDecisionModel.run_id == continuation.run_id,
                StageGateDecisionModel.idempotency_key == request.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_checksum != checksum:
                raise StageGateError("IDEMPOTENCY_PAYLOAD_MISMATCH", "Decision key has a different payload")
            return existing
        package = session.scalar(
            select(StageGatePackageModel)
            .where(
                StageGatePackageModel.run_id == continuation.run_id,
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == gate_id,
                StageGatePackageModel.status == "pending",
            )
            .order_by(StageGatePackageModel.gate_version.desc())
        )
        if package is None:
            raise StageGateError("GATE_NOT_PENDING", f"{gate_id} is not pending")
        if (
            continuation.state_version != request.expected_state_version
            or package.expected_state_version != request.expected_state_version
        ):
            raise StageGateError("TRANSFORMATION_STATE_CONFLICT", "Transformer state changed; refresh")
        if (
            package.package_checksum != request.package_checksum
            or package.workspace_fingerprint != request.workspace_fingerprint
            or (
                observed_workspace_fingerprint is not None
                and observed_workspace_fingerprint != package.workspace_fingerprint
            )
        ):
            raise StageGateError("STALE_GATE_BINDING", "Gate package or workspace fingerprint is stale")
        decided_at = now or datetime.now(UTC)
        accepted = request.decision == "approve"
        decision = StageGateDecisionModel(
            id=f"gate-decision-{uuid4().hex[:12]}",
            gate_package_id=package.id,
            run_id=continuation.run_id,
            stage_id=continuation.current_stage_id,
            gate_id=gate_id,
            decision=request.decision,
            actor=actor,
            comment=request.comment,
            idempotency_key=request.idempotency_key,
            request_checksum=checksum,
            expected_state_version=request.expected_state_version,
            package_checksum=request.package_checksum,
            workspace_fingerprint=request.workspace_fingerprint,
            accepted=accepted,
            reason_code=None if accepted else request.decision.upper(),
            created_at=decided_at,
        )
        session.add(decision)
        package.status = "approved" if accepted else "rejected"
        if accepted:
            continuation.status = "queued"
            continuation.current_node = _NEXT_NODE[gate_id]
            continuation.wake_sequence += 1
        else:
            continuation.status = "blocked"
            continuation.last_error_code = f"{gate_id}_{request.decision.upper()}"
            continuation.last_error_message = request.comment or f"{gate_id} was not approved"
        continuation.state_version += 1
        continuation.updated_at = decided_at
        session.flush()
        StateTransitionService(session).append_audit_event(
            run_id=continuation.run_id,
            idempotency_key=f"{request.idempotency_key}:event",
            event_type=WorkflowEventType[
                f"{gate_id}_{'APPROVED' if accepted else 'REJECTED'}"
            ],
            actor=actor,
            reason=f"{gate_id} {request.decision}",
            occurred_at=decided_at,
            payload={"stage_id": continuation.current_stage_id, "decision_id": decision.id},
        )
        return decision

    @staticmethod
    def _checksum(value: object) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()
