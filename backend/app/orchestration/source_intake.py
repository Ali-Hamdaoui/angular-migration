"""Durable source-intake dispatch and recovery boundary.

The HTTP request only persists and queues work.  Filesystem operations and
approval-package construction happen in this worker after the transaction has
committed, so a disconnected browser cannot interrupt the workflow.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import select

from app.api.baseline_contracts import BaselineInstallAuthorizationRequest, BaselineInstallRequest, BaselinePrequalifyRequest, BaselineWorkspaceRequest
from app.api.baseline_g03_contracts import BaselineQualifyRequest
from app.api.baseline_matrix_contracts import BaselineValidationRequest
from app.api.execution_profile_contracts import ExecutionProfileResolveRequest
from app.api.g02_initialization import G02PackageInitializationRequest
from app.domain.contracts import RunStatus, WorkflowEventType
from app.domain.snapshot import CreateSourceSnapshotRequest
from app.repositories.models import ExecutionProfileModel, G02ApprovalModel, MigrationRunModel, SourceIntakeJobModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.services.g02_application_service import G02ApprovalApplicationService
from app.services.baseline_application_service import BaselineApplicationService
from app.services.baseline_g03_application_service import BaselineG03ApplicationService
from app.services.baseline_install_application_service import BaselineInstallApplicationService
from app.services.baseline_validation_application_service import BaselineValidationApplicationService
from app.services.execution_profile_application_service import ExecutionProfileApplicationService
from app.services.source_snapshot_application_service import SourceSnapshotApplicationService
from app.state.transition_service import StateTransitionService, TransitionRequest


class SourceIntakeGraph(Protocol):
    def start(self, *, run_id: str, thread_id: str) -> None:
        """Dispatch source intake for an already-queued authoritative run."""


class SourceIntakeDispatcher:
    """Process durable source-intake jobs and recover them after restart."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="source-intake")
        self._lock = threading.Lock()
        self._submitted: set[str] = set()
        self._worker_id = f"source-intake-{os.getpid()}"

    def start(self, *, run_id: str, thread_id: str) -> None:
        with self._lock:
            if run_id in self._submitted:
                return
            self._submitted.add(run_id)
        try:
            self._executor.submit(self._run, run_id, thread_id)
        except Exception:
            with self._lock:
                self._submitted.discard(run_id)
            raise

    def recover(self) -> int:
        """Re-dispatch jobs left queued, running, or waiting at restart."""
        with session_scope() as session:
            jobs = list(session.scalars(select(SourceIntakeJobModel).where(SourceIntakeJobModel.status.in_({"queued", "running", "waiting_g02", "waiting_runtime_selection"}))))
            # A new backend instance owns recovery.  Requeue work owned by a
            # previous process before dispatching it; the unique run job and
            # idempotency keys keep the resumed steps from creating a second
            # authoritative snapshot or approval package.
            for job in jobs:
                if job.status == "running" and job.worker_id != self._worker_id:
                    job.status = "queued"
                    job.started_at = None
        for job in jobs:
            self.start(run_id=job.run_id, thread_id=job.thread_id)
        return len(jobs)

    def _run(self, run_id: str, thread_id: str) -> None:
        try:
            job = self._claim(run_id)
            if job is None:
                return
            with session_scope() as session:
                run = session.get(MigrationRunModel, run_id)
                if run is None:
                    return
                StateTransitionService(session).append_audit_event(
                    run_id=run_id,
                    idempotency_key=f"{job.idempotency_key}:started",
                    event_type=WorkflowEventType.SOURCE_INTAKE_STARTED,
                    actor=job.actor,
                    reason="durable source-intake worker started",
                    occurred_at=datetime.now(UTC),
                    payload={"job_id": job.id, "worker_id": self._worker_id, "attempt": job.attempt},
                )
                expected_version = run.state_version

            snapshot = SourceSnapshotApplicationService(self._settings).create(
                run_id,
                CreateSourceSnapshotRequest(
                    expected_state_version=expected_version,
                    idempotency_key=f"{job.idempotency_key}:snapshot",
                    actor=job.actor,
                ),
            )
            if snapshot.status.value != "created":
                self._fail(job.id, "SNAPSHOT_CREATION_FAILED", snapshot.error_message or "Source snapshot was not created.")
                return

            with session_scope() as session:
                run = session.get(MigrationRunModel, run_id)
                if run is None:
                    return
                job_row = session.get(SourceIntakeJobModel, job.id)
                if job_row is not None:
                    job_row.snapshot_id = snapshot.snapshot_id
                    job_row.state_version = run.state_version
                StateTransitionService(session).append_audit_event(
                    run_id=run_id,
                    idempotency_key=f"{job.idempotency_key}:completed",
                    event_type=WorkflowEventType.SOURCE_INTAKE_COMPLETED,
                    actor=job.actor,
                    reason="source snapshot and validation evidence finalized",
                    occurred_at=datetime.now(UTC),
                    payload={"job_id": job.id, "snapshot_id": snapshot.snapshot_id, "artifact_count": len(snapshot.artifacts)},
                )
                expected_version = run.state_version

            g02 = G02ApprovalApplicationService()
            g02.initialize(run_id, G02PackageInitializationRequest(
                expected_state_version=expected_version,
                idempotency_key=f"{job.idempotency_key}:g02",
                actor=job.actor,
            ))
            self._set_status(job.id, "waiting_g02")
            self._wait_for_g02(job.id, run_id)
        except Exception as error:
            self._fail(job.id if "job" in locals() and job is not None else None, type(error).__name__, str(error))
        finally:
            with self._lock:
                self._submitted.discard(run_id)

    def _wait_for_g02(self, job_id: str, run_id: str) -> None:
        """Keep the durable job observable while the mandatory human gate waits."""
        while True:
            rejected = False
            with session_scope() as session:
                job = session.get(SourceIntakeJobModel, job_id)
                run = session.get(MigrationRunModel, run_id)
                if job is None or run is None or job.status in {"failed", "cancelled"}:
                    return
                if run.status == "CANCELLED":
                    job.status = "cancelled"
                    job.finished_at = datetime.now(UTC)
                    return
                approval = session.scalar(select(G02ApprovalModel).where(
                    G02ApprovalModel.run_id == run_id,
                    G02ApprovalModel.status.in_({"approved", "approved_with_comment"}),
                ).order_by(G02ApprovalModel.updated_at.desc()))
                if approval is not None:
                    actor = job.actor
                    break
                rejected = session.scalar(select(WorkflowEventModel).where(
                    WorkflowEventModel.run_id == run_id,
                    WorkflowEventModel.event_type == WorkflowEventType.G02_REJECTED.value,
                ))
                if rejected is not None:
                    rejected = True
            if rejected:
                self._fail(job_id, "G02_REJECTED", "G02 source-integrity approval was rejected.")
                return
            threading.Event().wait(0.5)
        self._continue_after_g02(job_id, run_id, actor)

    def _continue_after_g02(self, job_id: str, run_id: str, actor: str) -> None:
        """Run the approved source boundary through runtime and baseline checks."""
        with session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                return
            source_angular, source_typescript, source_rxjs = self._source_versions(run)
            expected_version = run.state_version

        profiles = ExecutionProfileApplicationService()
        resolution = profiles.resolve(run_id, ExecutionProfileResolveRequest(
            expected_state_version=expected_version,
            idempotency_key=f"intake-{job_id}:runtime",
            actor=actor,
            source_angular_exact=source_angular,
            source_typescript_exact=source_typescript,
            source_rxjs_exact=source_rxjs,
            validated_at=datetime.now(UTC),
        ))
        if resolution.status == "blocked":
            self._fail(job_id, "RUNTIME_PROFILE_BLOCKED", "; ".join(resolution.blockers))
            return
        if resolution.status == "selection_required":
            self._set_status(job_id, "waiting_runtime_selection")
            if not self._wait_for_profile(run_id, job_id):
                return
        with session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))
            if run is None or profile is None or not profile.selected_profile_id or not profile.selected_checksum:
                self._fail(job_id, "EXECUTION_PROFILE_REQUIRED", "A checksum-bound runtime profile is required.")
                return
            expected_version = run.state_version
            profile_id, profile_checksum = profile.selected_profile_id, profile.selected_checksum

        baseline = BaselineApplicationService(
            g02_service=G02ApprovalApplicationService(),
            execution_profile_service=profiles,
        )
        workspace = baseline.create_workspace(run_id, BaselineWorkspaceRequest(
            expected_state_version=expected_version,
            idempotency_key=f"intake-{job_id}:baseline-workspace",
            actor=actor,
        ))
        prequalified = baseline.prequalify(run_id, BaselinePrequalifyRequest(
            expected_state_version=workspace.state_version,
            idempotency_key=f"intake-{job_id}:baseline-prequalify",
            actor=actor,
        ))
        if prequalified.blockers:
            self._fail(job_id, "BASELINE_PREQUALIFICATION_BLOCKED", "; ".join(prequalified.blockers))
            return
        authorized = prequalified
        if prequalified.authorization_status != "authorized":
            authorized = baseline.authorize_install(run_id, BaselineInstallAuthorizationRequest(
                expected_state_version=prequalified.state_version,
                idempotency_key=f"intake-{job_id}:baseline-authorize",
                actor=actor,
                decision="authorize",
                comment="Automatically authorized after clean baseline prequalification.",
            ))

        installer = BaselineInstallApplicationService()
        installation = installer.accept(run_id, BaselineInstallRequest(
            expected_state_version=authorized.state_version,
            idempotency_key=f"intake-{job_id}:npm-ci",
            actor=actor,
            runtime_profile_id=profile_id,
            runtime_checksum=profile_checksum,
        ))
        while installation.status in {"pending", "running", "queued"}:
            threading.Event().wait(0.5)
            installation = installer.get(run_id, installation.execution_id)
            if installation is None:
                self._fail(job_id, "BASELINE_INSTALL_LOST", "The baseline installation record disappeared.")
                return
        if installation.status != "succeeded":
            self._fail(job_id, "BASELINE_INSTALL_FAILED", "; ".join(installation.blockers) or "npm ci failed.")
            return

        validation = BaselineValidationApplicationService()
        targets = validation.get_targets(run_id)
        prerequisite_ids = list(installation.artifact_ids)
        for kind in ("build", "test", "lint"):
            configured = [target for target in targets.targets if target.get("kind") == kind]
            if not configured:
                continue
            result = validation.execute(run_id, kind, BaselineValidationRequest(
                expected_state_version=self._current_version(run_id),
                idempotency_key=f"intake-{job_id}:{kind}",
                actor=actor,
                prerequisite_artifact_ids=prerequisite_ids,
            ))
            prerequisite_ids.extend(result.artifact_ids)
            if result.status not in {"passed", "skipped_not_configured", "skipped_not_applicable"}:
                self._fail(job_id, f"BASELINE_{kind.upper()}_FAILED", f"Baseline {kind} did not pass.")
                return

        qualification = BaselineG03ApplicationService().qualify(run_id, BaselineQualifyRequest(
            expected_state_version=self._current_version(run_id),
            idempotency_key=f"intake-{job_id}:g03",
            actor=actor,
            prerequisite_artifact_ids=prerequisite_ids,
            prerequisite_artifact_checksums={},
        ))
        if qualification.blockers:
            self._fail(job_id, "G03_BLOCKED", "; ".join(qualification.blockers))
            return
        with session_scope() as session:
            job = session.get(SourceIntakeJobModel, job_id)
            run = session.get(MigrationRunModel, run_id)
            if job is not None and run is not None:
                job.status = "completed"
                job.finished_at = datetime.now(UTC)
                job.state_version = run.state_version

    def _wait_for_profile(self, run_id: str, job_id: str) -> bool:
        while True:
            with session_scope() as session:
                job = session.get(SourceIntakeJobModel, job_id)
                profile = session.scalar(select(ExecutionProfileModel).where(ExecutionProfileModel.run_id == run_id).order_by(ExecutionProfileModel.updated_at.desc()))
                if job is None or job.status in {"failed", "cancelled"}:
                    return False
                if profile is not None and profile.status == "selected":
                    return True
            threading.Event().wait(0.5)

    @staticmethod
    def _current_version(run_id: str) -> int:
        with session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise RuntimeError("migration run disappeared")
            return run.state_version

    @staticmethod
    def _source_versions(run: MigrationRunModel) -> tuple[str, str | None, str | None]:
        values = {
            "angular": run.source_angular_version,
            "typescript": None,
            "rxjs": None,
        }
        snapshot_path = (run.workspace_aliases or {}).get("SOURCE_SNAPSHOT")
        if snapshot_path:
            snapshot_root = Path(snapshot_path)
            package_path = snapshot_root / "package.json"
            if not package_path.is_file():
                package_path = next((path for path in snapshot_root.rglob("package.json") if path.is_file()), None)
            if package_path:
                try:
                    package = json.loads(package_path.read_text(encoding="utf-8"))
                    dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
                    values["angular"] = values["angular"] or str(dependencies.get("@angular/core", ""))
                    values["typescript"] = str(dependencies.get("typescript")) if dependencies.get("typescript") else None
                    values["rxjs"] = str(dependencies.get("rxjs")) if dependencies.get("rxjs") else None
                except (OSError, ValueError, TypeError):
                    pass
        if not values["angular"]:
            raise RuntimeError("Angular source version could not be determined from the approved snapshot")
        return str(values["angular"]), values["typescript"], values["rxjs"]

    def _claim(self, run_id: str) -> SourceIntakeJobModel | None:
        with session_scope() as session:
            job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == run_id))
            if job is None or job.status not in {"queued", "waiting_g02", "waiting_runtime_selection"}:
                return None
            job.status = "running"
            job.attempt += 1
            job.worker_id = self._worker_id
            job.started_at = datetime.now(UTC)
            return job

    def _set_status(self, job_id: str, status: str) -> None:
        with session_scope() as session:
            job = session.get(SourceIntakeJobModel, job_id)
            if job is not None:
                job.status = status

    def _fail(self, job_id: str | None, code: str, message: str) -> None:
        if job_id is None:
            return
        with session_scope() as session:
            job = session.get(SourceIntakeJobModel, job_id)
            if job is None:
                return
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            job.last_error_code = code
            job.last_error_message = message[:4000]
            run = session.get(MigrationRunModel, job.run_id)
            if run is not None:
                StateTransitionService(session).apply_transition(TransitionRequest(
                    run_id=run.id,
                    expected_state_version=run.state_version,
                    idempotency_key=f"{job.idempotency_key}:failed:{job.attempt}",
                    event_type=WorkflowEventType.SOURCE_INTAKE_FAILED,
                    next_run_status=RunStatus.FAILED,
                    actor=job.actor,
                    reason="durable source-intake worker failed",
                    occurred_at=datetime.now(UTC),
                    payload={"job_id": job.id, "error_code": code, "message": message[:1000]},
                ))


_dispatcher: SourceIntakeDispatcher | None = None


def default_source_intake_graph(settings) -> SourceIntakeGraph:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SourceIntakeDispatcher(settings)
    return _dispatcher


def recover_source_intake_jobs() -> int:
    if _dispatcher is None:
        return 0
    return _dispatcher.recover()
