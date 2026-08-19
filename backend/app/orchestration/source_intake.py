"""Durable source-intake dispatch and recovery boundary.

The HTTP request only persists and queues work.  Filesystem operations and
approval-package construction happen in this worker after the transaction has
committed, so a disconnected browser cannot interrupt the workflow.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sqlalchemy import func, select

from app.api.baseline_contracts import BaselineInstallAuthorizationRequest, BaselineInstallRequest, BaselinePrequalifyRequest, BaselineWorkspaceRequest
from app.api.baseline_g03_contracts import BaselineQualifyRequest
from app.api.baseline_matrix_contracts import BaselineValidationRequest
from app.api.baseline_parity_contracts import BaselineParityCaptureRequest
from app.api.execution_profile_contracts import ExecutionProfileResolveRequest
from app.api.g02_initialization import G02PackageInitializationRequest
from app.api.discovery_contracts import DiscoveryCaptureRequest
from app.domain.contracts import RunStatus, WorkflowEventType
from app.domain.snapshot import CreateSourceSnapshotRequest
from app.repositories.models import AnalysisMetadataModel, ArtifactMetadataModel, DiscoveryEvidenceModel, ExecutionProfileModel, G02ApprovalModel, G03ApprovalModel, MigrationRunModel, SourceIntakeJobModel, WorkflowEventModel
from app.repositories.session import session_scope
from app.services.g02_application_service import G02ApprovalApplicationService
from app.services.baseline_application_service import BaselineApplicationService
from app.services.baseline_g03_application_service import BaselineG03ApplicationService
from app.services.baseline_install_application_service import BaselineInstallApplicationService
from app.services.baseline_validation_application_service import BaselineValidationApplicationService
from app.services.baseline_parity_application_service import BaselineParityApplicationService
from app.services.execution_profile_application_service import ExecutionProfileApplicationService
from app.services.discovery_evidence_application_service import DiscoveryEvidenceApplicationService
from app.services.parity_baseline_evidence_application_service import ParityBaselineEvidenceApplicationService
from app.api.analysis_contracts import AnalysisCreateRequest
from app.services.analysis_evidence_application_service import AnalysisEvidenceApplicationService
from app.api.parity_baseline_contracts import ParityBaselineCaptureRequest
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
        self._continuing: set[str] = set()
        self._worker_id = f"source-intake-{os.getpid()}"

    def start(self, *, run_id: str, thread_id: str) -> None:
        # Submission is intentionally not de-duplicated in memory. Multiple
        # callbacks may enqueue the same durable job; _claim() atomically moves
        # exactly one queued/waiting row to running and every other worker exits.
        self._executor.submit(self._run, run_id, thread_id)

    def resume_after_g03(self, run_id: str) -> None:
        thread_id = None
        with session_scope() as session:
            job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == run_id, SourceIntakeJobModel.status == "waiting_g03"))
            if job is not None:
                thread_id = job.thread_id
            else:
                thread_id = self._rearm_stranded_after_g03(session, run_id)
        if thread_id is not None:
            self.start(run_id=run_id, thread_id=thread_id)

    def _rearm_stranded_after_g03(self, session, run_id: str) -> str | None:
        """Re-arm the narrow post-restart stranded source-intake condition.

        Only a failed job whose last_error_code is exactly G03_APPROVAL_REQUIRED
        (the signature of the pre-approval recover() defect) is recoverable here,
        and only when an approved current G03 exists, the run is BASELINE_QUALIFIED,
        and no active continuation job already represents the post-G03 work.
        Returns the thread_id to dispatch, or None when the run is not stranded.
        """
        run = session.get(MigrationRunModel, run_id)
        if run is None or run.status != RunStatus.BASELINE_QUALIFIED.value:
            return None
        approval = session.scalar(select(G03ApprovalModel).where(
            G03ApprovalModel.run_id == run_id,
            G03ApprovalModel.status == "approved",
        ).order_by(G03ApprovalModel.updated_at.desc()))
        if approval is None:
            return None
        active = session.scalar(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == run_id,
            SourceIntakeJobModel.status.in_({
                "queued", "running", "waiting_g02",
                "waiting_runtime_selection", "waiting_g03", "waiting_baseline_retry",
            }),
        ))
        if active is not None:
            return None
        latest = session.scalar(select(SourceIntakeJobModel).where(
            SourceIntakeJobModel.run_id == run_id,
        ).order_by(SourceIntakeJobModel.attempt.desc(), SourceIntakeJobModel.queued_at.desc()))
        if (
            latest is None
            or latest.status != "failed"
            or latest.last_error_code != "G03_APPROVAL_REQUIRED"
        ):
            return None
        rearm = SourceIntakeJobModel(
            id=f"intake-{uuid4().hex[:12]}",
            run_id=run_id,
            thread_id=latest.thread_id,
            status="waiting_g03",
            actor=latest.actor,
            idempotency_key=f"{latest.idempotency_key}:rearm-g03",
            attempt=latest.attempt + 1,
            queued_at=datetime.now(UTC),
            state_version=run.state_version,
        )
        session.add(rearm)
        StateTransitionService(session).append_audit_event(
            run_id=run_id,
            idempotency_key=f"{rearm.idempotency_key}:queued",
            event_type=WorkflowEventType.SOURCE_INTAKE_QUEUED,
            actor=rearm.actor,
            reason="post-G03 continuation re-armed after pre-approval recovery defect",
            occurred_at=datetime.now(UTC),
            payload={"job_id": rearm.id, "previous_job_id": latest.id, "attempt": rearm.attempt},
        )
        return rearm.thread_id

    def recover(self) -> int:
        """Re-dispatch jobs left queued, running, or waiting at restart.

        waiting_g03 is a dormant human-gate state, not crashed work; it is
        excluded from recovery so a backend restart cannot prematurely
        dispatch the post-G03 continuation before the human approves G03.
        resume_after_g03 is the only legitimate trigger for that continuation.

        A second, narrow pass self-heals runs already stranded by the
        historical pre-approval recovery defect: their latest source-intake
        job failed with G03_APPROVAL_REQUIRED before G03 was approved, so no
        normal UI action can reach resume_after_g03.  Candidate selection is
        intentionally minimal (latest job signature only); the authoritative
        guards in _rearm_stranded_after_g03 decide whether re-arming is
        allowed, so arbitrary failed jobs and unrelated error codes are never
        revived here.
        """
        with session_scope() as session:
            jobs = list(session.scalars(select(SourceIntakeJobModel).where(SourceIntakeJobModel.status.in_({"queued", "running", "waiting_g02", "waiting_runtime_selection", "waiting_baseline_retry", "waiting_retry"}))))
            # A new backend instance owns recovery. Requeue work owned by a
            # previous process before dispatching it; attempt-specific
            # idempotency keys keep resumed steps from creating duplicate
            # authoritative evidence.
            for job in jobs:
                if job.status == "running" and job.worker_id != self._worker_id:
                    analysis = session.scalar(select(AnalysisMetadataModel).where(AnalysisMetadataModel.run_id == job.run_id).order_by(AnalysisMetadataModel.created_at.desc()))
                    if analysis is not None and analysis.status == "failed":
                        job.status = "waiting_retry" if bool(analysis.retryable) else "failed"
                        job.started_at = None
                        continue
                    approved = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.run_id == job.run_id, WorkflowEventModel.event_type == WorkflowEventType.G03_APPROVED.value))
                    job.status = "waiting_g03" if approved is not None else "queued"
                    job.started_at = None
        dispatchable = [job for job in jobs if job.status != "waiting_retry"]
        for job in dispatchable:
            self.start(run_id=job.run_id, thread_id=job.thread_id)
        stranded = self._discover_stranded_after_g03()
        for run_id in stranded:
            self.resume_after_g03(run_id)
        return len(dispatchable) + len(stranded)

    def _discover_stranded_after_g03(self) -> list[str]:
        """Candidate run_ids whose latest source-intake job carries the
        historical pre-approval-recovery defect signature.

        Selection applies only the cheap structural guards (run is
        BASELINE_QUALIFIED, an approved current G03 exists, and the latest
        job is failed with last_error_code == G03_APPROVAL_REQUIRED).  The
        authoritative decision remains in _rearm_stranded_after_g03, which
        resume_after_g03 invokes and which re-checks every guard including
        the absence of active continuation work before re-arming.  This only
        decides who to *invite* to self-heal; it never re-arms directly, so
        arbitrary failed jobs and unrelated error codes are never revived.
        """
        with session_scope() as session:
            latest_attempt = (
                select(
                    SourceIntakeJobModel.run_id,
                    func.max(SourceIntakeJobModel.attempt).label("max_attempt"),
                )
                .group_by(SourceIntakeJobModel.run_id)
                .subquery()
            )
            approved_g03 = (
                select(G03ApprovalModel.run_id)
                .where(G03ApprovalModel.status == "approved")
                .group_by(G03ApprovalModel.run_id)
                .subquery()
            )
            return list(session.scalars(
                select(SourceIntakeJobModel.run_id)
                .join(latest_attempt, latest_attempt.c.run_id == SourceIntakeJobModel.run_id)
                .join(MigrationRunModel, MigrationRunModel.id == SourceIntakeJobModel.run_id)
                .join(approved_g03, approved_g03.c.run_id == SourceIntakeJobModel.run_id)
                .where(
                    MigrationRunModel.status == RunStatus.BASELINE_QUALIFIED.value,
                    SourceIntakeJobModel.status == "failed",
                    SourceIntakeJobModel.last_error_code == "G03_APPROVAL_REQUIRED",
                    SourceIntakeJobModel.attempt == latest_attempt.c.max_attempt,
                )
            ))

    def _run(self, run_id: str, thread_id: str) -> None:
        try:
            job = self._claim(run_id)
            if job is None:
                return
            if getattr(job, "_resume_after_g03", False):
                self._continue_after_g03(job.id, run_id, job.actor)
                return
            if getattr(job, "_resume_baseline", False):
                self._continue_after_g02_once(job.id, run_id, job.actor, resume_baseline=True)
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
        with self._lock:
            if run_id in self._continuing:
                return
            self._continuing.add(run_id)
        try:
            self._continue_after_g02_once(job_id, run_id, actor)
        finally:
            with self._lock:
                self._continuing.discard(run_id)

    def _continue_after_g02_once(self, job_id: str, run_id: str, actor: str, *, resume_baseline: bool = False) -> None:
        """Run the approved source boundary through runtime and baseline checks."""
        try:
            G02ApprovalApplicationService().authorize_baseline(run_id)
        except Exception as error:
            self._block(job_id, "G02_STALE" if getattr(error, "code", "") == "STALE_EVIDENCE" else "G02_APPROVAL_REQUIRED", str(error))
            return
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
        if resume_baseline:
            workspace = baseline.get(run_id)
            if workspace is None or workspace.status not in {"workspace_ready", "blocked"}:
                self._fail(job_id, "BASELINE_WORKSPACE_REQUIRED", "The preserved baseline workspace is unavailable for retry.")
                return
        else:
            workspace = baseline.create_workspace(run_id, BaselineWorkspaceRequest(
                expected_state_version=expected_version,
                idempotency_key=f"intake-{job_id}:baseline-workspace",
                actor=actor,
            ))
        prequalified = baseline.prequalify(run_id, BaselinePrequalifyRequest(
            expected_state_version=expected_version if resume_baseline else workspace.state_version,
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
            # A validation result is baseline evidence, not a source-intake
            # failure. Keep collecting the matrix so G03 can classify a
            # blocked/known-failure baseline and create its approval package.
            # In particular, an unsupported Angular target may coexist with a
            # passing package script for the same kind.

        with session_scope() as session:
            metadata = {
                item.id.removeprefix("metadata-"): item.checksum
                for item in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id))
            }
        parity = BaselineParityApplicationService().capture(run_id, BaselineParityCaptureRequest(
            expected_state_version=self._current_version(run_id),
            idempotency_key=f"intake-{job_id}:baseline-parity",
            actor=actor,
            prerequisite_artifact_ids=prerequisite_ids,
            prerequisite_artifact_checksums={item: metadata[item] for item in prerequisite_ids if item in metadata},
        ))
        if parity.status != "captured":
            self._fail(job_id, "BASELINE_PARITY_CAPTURE_FAILED", "Baseline parity evidence was not captured.")
            return
        prerequisite_ids.extend(parity.artifact_ids)
        with session_scope() as session:
            metadata = {
                item.id.removeprefix("metadata-"): item.checksum
                for item in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id))
            }

        qualification = BaselineG03ApplicationService().qualify(run_id, BaselineQualifyRequest(
            expected_state_version=self._current_version(run_id),
            idempotency_key=f"intake-{job_id}:g03",
            actor=actor,
            prerequisite_artifact_ids=prerequisite_ids,
            prerequisite_artifact_checksums={item: metadata[item] for item in prerequisite_ids},
        ))
        if qualification.blockers:
            # G03 owns the baseline decision. Do not overwrite it with a
            # misleading SOURCE_INTAKE_FAILED event; the run remains
            # reviewable with the persisted blockers and evidence.
            with session_scope() as session:
                job = session.get(SourceIntakeJobModel, job_id)
                run = session.get(MigrationRunModel, run_id)
                if job is not None and run is not None:
                    job.status = "waiting_g03"
                    job.finished_at = None
                    job.state_version = run.state_version
            return
        with session_scope() as session:
            job = session.get(SourceIntakeJobModel, job_id)
            run = session.get(MigrationRunModel, run_id)
            if job is not None and run is not None:
                job.status = "waiting_g03"
                job.finished_at = None
                job.state_version = run.state_version

    def _continue_after_g03(self, job_id: str, run_id: str, actor: str) -> None:
        with session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            approval = session.scalar(select(G03ApprovalModel).where(G03ApprovalModel.run_id == run_id, G03ApprovalModel.status == "approved").order_by(G03ApprovalModel.updated_at.desc()))
            if run is None:
                self._fail(job_id, "RUN_NOT_FOUND", "Migration run disappeared before discovery.")
                return
            if approval is None:
                # G03 is not yet approved.  Re-arm the human-gate wait instead
                # of failing the job: discovery must not start before approval,
                # but a premature dispatch (e.g. from a stale recovery path) is
                # a recoverable wait, not a terminal source-intake failure.
                # resume_after_g03 will dispatch once the human approves G03.
                job_row = session.get(SourceIntakeJobModel, job_id)
                if job_row is not None:
                    job_row.status = "waiting_g03"
                    job_row.started_at = None
                return
            metadata = {item.id.removeprefix("metadata-"): item.checksum for item in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id))}
            artifact_ids = tuple(approval.artifact_ids or ())
            expected_version = run.state_version
        request = DiscoveryCaptureRequest(
            expected_state_version=expected_version,
            idempotency_key=f"intake-{job_id}:discovery",
            actor=actor,
            prerequisite_artifact_ids=artifact_ids,
            prerequisite_artifact_checksums={item: metadata[item] for item in artifact_ids if item in metadata},
        )
        discovery = DiscoveryEvidenceApplicationService()
        try:
            discovery_result = discovery.capture(run_id, request)
        except Exception as error:
            # Discovery owns its dependency failures. Do not report scanner,
            # artifact, or workspace failures as a source-intake failure.
            checksum = "sha256:" + hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            discovery_result = discovery.block(run_id, request, checksum, str(error))
        if discovery_result.status != "completed":
            self._fail(job_id, "DISCOVERY_NOT_COMPLETED", "Deterministic discovery evidence was not completed.")
            return
        with session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                self._fail(job_id, "RUN_NOT_FOUND", "Migration run disappeared before discovery parity capture.")
                return
            metadata = {item.id.removeprefix("metadata-"): item.checksum for item in session.scalars(select(ArtifactMetadataModel).where(ArtifactMetadataModel.run_id == run_id))}
            discovery_artifacts = list(discovery_result.artifact_ids)
            parity_request = ParityBaselineCaptureRequest(
                expected_state_version=run.state_version,
                idempotency_key=f"intake-{job_id}:discovery-parity-baseline",
                prerequisite_artifact_ids=discovery_artifacts,
                prerequisite_artifact_checksums={item: metadata[item] for item in discovery_artifacts if item in metadata},
            )
        post_g03_parity = ParityBaselineEvidenceApplicationService().capture(run_id, parity_request, actor=actor)
        if post_g03_parity.status != "completed":
            self._fail(job_id, "DISCOVERY_PARITY_BASELINE_FAILED", "Deterministic discovery parity evidence was not completed.")
            return
        # Analysis is a backend-owned continuation.  The durable parity result
        # supplies the idempotency anchor; the Analysis service derives the
        # canonical artifact set from persisted evidence and never trusts a UI.
        with session_scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                self._fail(job_id, "RUN_NOT_FOUND", "Migration run disappeared before Analysis continuation.")
                return
            analysis_request = AnalysisCreateRequest(
                expected_state_version=run.state_version,
                idempotency_key=f"analysis:{run_id}:{post_g03_parity.evidence_id}:{post_g03_parity.state_version}",
                correlation_id=f"analysis:{run_id}:{post_g03_parity.evidence_id}",
            )
        try:
            analysis_result = AnalysisEvidenceApplicationService().generate(run_id, analysis_request, actor)
        except Exception as error:
            self._fail(job_id, "ANALYSIS_WORKER_FAILURE", "Analysis continuation failed after its durable attempt was recorded.")
            return
        if analysis_result.status != "completed":
            with session_scope() as session:
                job = session.get(SourceIntakeJobModel, job_id)
                run = session.get(MigrationRunModel, run_id)
                if job is not None and run is not None:
                    retryable = bool(getattr(analysis_result, "retryable", False))
                    job.status = "waiting_retry" if retryable else "failed"
                    job.last_error_code = analysis_result.error_code or "ANALYSIS_FAILED"
                    job.last_error_message = "Analysis failed; durable Analysis evidence is available for review."
                    job.finished_at = datetime.now(UTC) if not retryable else None
                    job.state_version = run.state_version
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

                    lock_path = package_path.with_name("package-lock.json")
                    if lock_path.is_file():
                        lock = json.loads(lock_path.read_text(encoding="utf-8"))
                        locked_packages = lock.get("packages", {})
                        locked_angular = locked_packages.get("node_modules/@angular/core", {}).get("version") if isinstance(locked_packages, dict) else None
                        if locked_angular:
                            values["angular"] = str(locked_angular)
                        else:
                            locked_dependencies = lock.get("dependencies", {})
                            locked_angular = locked_dependencies.get("@angular/core", {}).get("version") if isinstance(locked_dependencies, dict) else None
                            if locked_angular:
                                values["angular"] = str(locked_angular)
                except (OSError, ValueError, TypeError):
                    pass
        if not values["angular"]:
            raise RuntimeError("Angular source version could not be determined from the approved snapshot")
        return str(values["angular"]), values["typescript"], values["rxjs"]

    def _claim(self, run_id: str) -> SourceIntakeJobModel | None:
        with session_scope() as session:
            job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == run_id, SourceIntakeJobModel.status.in_({"queued", "waiting_g02", "waiting_runtime_selection", "waiting_g03", "waiting_baseline_retry"})).order_by(SourceIntakeJobModel.queued_at.desc()))
            if job is None:
                return None
            resume_g03 = job.status == "waiting_g03"
            job._resume_after_g03 = resume_g03
            job._resume_baseline = job.status == "waiting_baseline_retry"
            job.status = "running"
            # Attempt is the durable retry identity, not a worker-claim
            # counter. It must remain stable when recovery reclaims a job.
            if job.attempt < 1:
                job.attempt = 1
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
                completed = session.scalar(select(WorkflowEventModel).where(WorkflowEventModel.run_id == run.id, WorkflowEventModel.event_type == WorkflowEventType.SOURCE_INTAKE_COMPLETED.value))
                if completed is not None:
                    event_type = WorkflowEventType.EXECUTION_PROFILE_BLOCKED if code.startswith(("G02_", "RUNTIME_", "EXECUTION_PROFILE_")) else WorkflowEventType.BASELINE_BLOCKED
                    StateTransitionService(session).apply_transition(TransitionRequest(
                        run_id=run.id, expected_state_version=run.state_version,
                        idempotency_key=f"{job.idempotency_key}:blocked:{job.attempt}", event_type=event_type,
                        next_run_status=RunStatus.DIAGNOSTIC_HOLD, next_phase_status="blocked",
                        actor=job.actor, reason="post-intake continuation blocked", occurred_at=datetime.now(UTC),
                        payload={"job_id": job.id, "error_code": code, "message": message[:1000]},
                    ))
                    return
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

    def _block(self, job_id: str | None, code: str, message: str) -> None:
        self._fail(job_id, code, message)


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
