"""Dynamic stage-chain orchestrator service (V2 F12)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.stage_orchestration import StageChainStateRecord, StageRunRecord
from app.repositories.models import MigrationRunModel, StageChainRunModel
from app.repositories.session import session_scope
from app.services.migration_route_service import MigrationRouteService
from app.services.runtime_certification_service import RuntimeCertificationService


class StageOrchestrationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StageChainOrchestrator:
    """Durable, resumable orchestration of an arbitrary stage chain (F12)."""

    def __init__(
        self,
        *,
        route_service: MigrationRouteService | None = None,
        certification_service: RuntimeCertificationService | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._route = route_service or MigrationRouteService()
        self._certification = certification_service or RuntimeCertificationService()
        self._last_gate_reason = ""
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def start_chain(self, run_id: str) -> StageChainStateRecord:
        """Initialize the durable chain state from the routed plan (F12-01).

        Materializes real run-owned MigrationStageModel rows so per-stage gates
        (certification, families) resolve against authoritative stage state.
        """
        from app.repositories.models import MigrationStageModel

        with self._session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise StageOrchestrationError("RUN_NOT_FOUND", f"Migration run {run_id} not found")
        route = self._route.compute_for_run(run_id)
        stages = []
        with self._session_scope() as session:
            for stage in route.stages:
                stage_id = _stage_id(run_id, stage.stage_order)
                if session.get(MigrationStageModel, stage_id) is None:
                    session.add(
                        MigrationStageModel(
                            id=stage_id,
                            run_id=run_id,
                            stage_order=stage.stage_order,
                            source_version_family=stage.source_family,
                            target_version_family=stage.target_family,
                            source_angular_version=f"{stage.source_major}.0.0",
                            target_angular_version=f"{stage.target_major}.0.0",
                            status="planned",
                            created_at=self._now_provider(),
                        )
                    )
                stages.append(
                    StageRunRecord(
                        stage_order=stage.stage_order,
                        stage_id=stage_id,
                        source_major=stage.source_major,
                        target_major=stage.target_major,
                    )
                )
            session.commit()
        state = StageChainStateRecord(
            run_id=run_id,
            source_major=route.source_major,
            target_major=route.target_major,
            catalogue_version=route.catalogue_version,
            status="created",
            stages=tuple(stages),
        ).bind_checksum()
        with self._session_scope() as session:
            existing = session.scalar(
                select(StageChainRunModel).where(
                    StageChainRunModel.run_id == run_id,
                    StageChainRunModel.checksum == state.checksum,
                )
            )
            if existing is not None:
                return self._from_model(existing)
            session.add(
                StageChainRunModel(
                    id="scr-" + hashlib.sha256(f"{run_id}:{state.checksum}".encode()).hexdigest()[:24],
                    run_id=run_id,
                    source_major=state.source_major,
                    target_major=state.target_major,
                    catalogue_version=state.catalogue_version,
                    status=state.status,
                    stages=[s.model_dump(mode="json") for s in state.stages],
                    checksum=state.checksum,
                    created_at=self._now_provider(),
                    updated_at=self._now_provider(),
                )
            )
            session.commit()
        return state

    def advance(self, run_id: str) -> StageChainStateRecord:
        """Advance to the next pending stage, applying per-stage gates (F12-02).

        The certification gate (F11) must pass before a stage runs; a failed
        gate marks the stage failed and routes the chain to repair (F12-03).
        """
        state = self._current_state(run_id)
        if state.status in {"completed", "failed", "repairing"}:
            return state
        next_stage = next((s for s in state.stages if s.status == "pending"), None)
        if next_stage is None:
            updated = [s.model_copy(update={"status": "sealed"}) for s in state.stages]
            new_state = state.model_copy(update={"status": "completed", "stages": tuple(updated)}).bind_checksum()
            return self._persist_state(run_id, new_state)
        stage_id = next_stage.stage_id
        from app.services.runtime_certification_service import RuntimeCertificationError
        from app.services.stage_runtime_service import StageRuntimeError

        try:
            self._certification.enforce_stage_certification(stage_id)
            gate_passed = True
        except (RuntimeCertificationError, StageRuntimeError) as exc:
            gate_passed = False
            self._last_gate_reason = exc.message
        status = "running" if gate_passed else "failed"
        failure_code = None if gate_passed else f"STAGE_GATE_NOT_PASSED:{self._last_gate_reason}"
        updated_stages = tuple(
            s.model_copy(update={"status": status, "gate_passed": gate_passed, "failure_code": failure_code})
            if s.stage_order == next_stage.stage_order
            else s
            for s in state.stages
        )
        chain_status = "running" if gate_passed else "repairing"
        new_state = state.model_copy(update={"status": chain_status, "stages": updated_stages}).bind_checksum()
        return self._persist_state(run_id, new_state)

    def mark_stage_failed(self, run_id: str, stage_order: int, failure_code: str) -> StageChainStateRecord:
        """Route a stage failure into the repair lifecycle (F12-03)."""
        state = self._current_state(run_id)
        if not any(s.stage_order == stage_order for s in state.stages):
            raise StageOrchestrationError("STAGE_ORDER_NOT_IN_CHAIN", f"stage order {stage_order} is not in the chain")
        updated_stages = tuple(
            s.model_copy(update={"status": "failed", "failure_code": failure_code})
            if s.stage_order == stage_order
            else s
            for s in state.stages
        )
        new_state = state.model_copy(update={"status": "repairing", "stages": updated_stages}).bind_checksum()
        return self._persist_state(run_id, new_state)

    def resume(self, run_id: str) -> StageChainStateRecord:
        """Durably resume the chain at the next incomplete stage (F12-04)."""
        state = self._current_state(run_id)
        if state.status in {"completed", "repairing"}:
            return state
        if state.status == "failed":
            # repair lifecycle resolves the failure; the chain re-enters running.
            new_state = state.model_copy(update={"status": "running"}).bind_checksum()
            return self._persist_state(run_id, new_state)
        return state

    def current_state(self, run_id: str) -> StageChainStateRecord:
        return self._current_state(run_id)

    def _current_state(self, run_id: str) -> StageChainStateRecord:
        with self._session_scope() as session:
            row = session.scalar(
                select(StageChainRunModel)
                .where(StageChainRunModel.run_id == run_id)
                .order_by(StageChainRunModel.updated_at.desc())
                .limit(1)
            )
            if row is None:
                raise StageOrchestrationError("CHAIN_NOT_STARTED", f"no chain started for run {run_id}")
            return self._from_model(row)

    def _persist_state(self, run_id: str, state: StageChainStateRecord) -> StageChainStateRecord:
        with self._session_scope() as session:
            row = session.scalar(
                select(StageChainRunModel)
                .where(StageChainRunModel.run_id == run_id)
                .order_by(StageChainRunModel.updated_at.desc())
                .limit(1)
            )
            if row is None:
                raise StageOrchestrationError("CHAIN_NOT_STARTED", f"no chain started for run {run_id}")
            row.status = state.status
            row.stages = [s.model_dump(mode="json") for s in state.stages]
            row.checksum = state.checksum
            row.updated_at = self._now_provider()
            session.commit()
            session.refresh(row)
            return self._from_model(row)

    @staticmethod
    def _from_model(row: StageChainRunModel) -> StageChainStateRecord:
        state = StageChainStateRecord(
            run_id=row.run_id,
            source_major=row.source_major,
            target_major=row.target_major,
            catalogue_version=row.catalogue_version,
            status=row.status,
            stages=tuple(StageRunRecord(**s) for s in (row.stages or [])),
        )
        return state.bind_checksum()


def _stage_id(run_id: str, stage_order: int) -> str:
    return f"stage-{run_id}-{stage_order}"
