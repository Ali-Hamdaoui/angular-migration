"""Durable post-G04 planning dispatcher."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.api.planning_contracts import PlanCreateRequest
from app.api.planning_review_contracts import PlanningExplanationApiRequest
from app.repositories.models import ActivePlanVersionModel, CompatibilityResolutionModel, G05ApprovalModel, MigrationPlanModel, MigrationRunModel, PlanningJobModel, StageExecutionPlanModel
from app.domain.contracts import WorkflowEventType
from app.repositories.session import session_scope
from app.services.artifact_binding import canonical_artifact_references
from app.services.compatibility_application_service import CompatibilityResolver
from app.services.compatibility_evidence_application_service import CompatibilityEvidenceApplicationService
from app.services.planning_evidence_application_service import PlanningEvidenceApplicationService
from app.services.planning_input_resolver import PlanningInputResolutionError, PlanningInputResolver
from app.services.planning_job_service import PlanningFailureDisposition, claim_planning_job, classify_planning_failure
from app.services.planning_review_evidence_application_service import PlanningReviewEvidenceApplicationService
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider
from app.services.project_planning_resolver import ProjectPlanningResolutionError, ProjectPlanningResolver
from app.services.workspace_integrity_service import WorkspaceIntegrityError, WorkspaceIntegrityService
from app.state.transition_service import StateTransitionService, TransitionRequest


def _mark_retry(job_id: str, *, disposition: PlanningFailureDisposition, stage: str, diagnostic=None, scope=session_scope) -> None:
    with scope() as session:
        job = session.get(PlanningJobModel, job_id)
        if job is not None:
            run = session.get(MigrationRunModel, job.run_id)
            if run is None:
                return
            now = datetime.now(UTC)
            terminal = disposition.terminal or job.attempt >= job.max_attempts
            job.status = "technical_failed" if terminal else "waiting_retry"
            job.current_step = stage
            job.last_error_code = disposition.code
            job.last_error_message = disposition.public_message or None
            job.last_error_stage = stage
            job.retryable = disposition.retryable and not terminal
            job.first_failed_at = job.first_failed_at or now
            job.terminal_failed_at = now if terminal else None
            job.next_attempt_at = None if terminal else now + timedelta(seconds=min(300, 2 ** max(0, job.attempt - 1)))
            job.lease_expires_at = None
            job.worker_id = None
            job.updated_at = now
            artifact_id, diagnostic_payload = PlanningEvidenceApplicationService(scope=scope).record_failure(session, run, job, disposition=disposition, stage=stage, diagnostic=diagnostic)
            transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run.id,
                expected_state_version=run.state_version,
                idempotency_key=f"planning-failure:{job.id}:{job.attempt}",
                event_type=WorkflowEventType.PLANNING_INPUT_RESOLUTION_FAILED,
                actor=job.actor,
                reason="planning input resolution failed",
                occurred_at=now,
                payload={"job_id": job.id, "planning_stage": stage, "attempt": job.attempt, "failure_code": disposition.code, "retryable": disposition.retryable and not disposition.terminal, "diagnostic_artifact_id": artifact_id, "correlation_id": job.correlation_id, "resulting_planning_job_state": job.status},
            ))
            final_event_type = WorkflowEventType.PLANNING_RETRY_SCHEDULED if not terminal else WorkflowEventType.PLANNING_FAILED
            final_transition = StateTransitionService(session).apply_transition(TransitionRequest(
                run_id=run.id,
                expected_state_version=transition.next_state_version,
                idempotency_key=f"planning-outcome:{job.id}:{job.attempt}",
                event_type=final_event_type,
                actor=job.actor,
                reason="planning retry scheduled" if not terminal else "planning failed before plan creation",
                occurred_at=now,
                payload={"job_id": job.id, "planning_stage": stage, "attempt": job.attempt, "failure_code": disposition.code, "retryable": disposition.retryable and not terminal, "diagnostic_artifact_id": artifact_id, "correlation_id": job.correlation_id, "resulting_planning_job_state": job.status},
            ))
            job.state_version = final_transition.next_state_version


def _error_details(error: Exception) -> tuple[str, str]:
    return getattr(error, "code", type(error).__name__), getattr(error, "message", str(error))


def resolve_feasibility_step(job_id: str, *, scope=session_scope) -> None:
    now = datetime.now(UTC)
    with scope() as session:
        job = session.get(PlanningJobModel, job_id)
        run = session.get(MigrationRunModel, job.run_id) if job else None
        if job is None or run is None:
            raise ValueError("PLANNING_JOB_NOT_FOUND" if job is None else "RUN_NOT_FOUND")
        actor, expected_state_version = job.actor, run.state_version
    try:
        with scope() as session:
            payload = PlanningInputResolver().resolve(session, run.id, actor=actor, expected_state_version=expected_state_version, idempotency_key=f"feasibility:auto:{job_id}", now=now)
        result = CompatibilityEvidenceApplicationService(resolver=CompatibilityResolver(CompatibilityCatalogueProvider().load())).resolve(run.id, payload, actor)
        with scope() as session:
            job = session.get(PlanningJobModel, job_id)
            job.status = "waiting_g05" if result.status != "blocked" else "completed_blocked"
            job.current_step = "waiting_g05" if result.status != "blocked" else "resolving_feasibility"
            job.last_error_code = None if result.status != "blocked" else "FEASIBILITY_BLOCKED"
            job.last_error_message = None
            job.last_error_stage = None
            job.retryable = False
            job.attempt = 0
            job.lease_expires_at = None
            job.worker_id = None
            job.updated_at = datetime.now(UTC)
    except PlanningInputResolutionError as error:
        _mark_retry(job_id, disposition=classify_planning_failure(error), stage="resolving_feasibility", diagnostic=getattr(error, "details", None), scope=scope)
    except Exception as error:
        _mark_retry(job_id, disposition=classify_planning_failure(error), stage="resolving_feasibility", diagnostic=getattr(error, "details", None), scope=scope)


def _approved_plan_request(job_id: str, *, scope=session_scope):
    with scope() as session:
        job = session.get(PlanningJobModel, job_id)
        run = session.get(MigrationRunModel, job.run_id) if job else None
        resolution = session.scalar(select(CompatibilityResolutionModel).where(CompatibilityResolutionModel.run_id == run.id).order_by(CompatibilityResolutionModel.created_at.desc())) if run else None
        gate = session.scalar(select(G05ApprovalModel).where(G05ApprovalModel.run_id == run.id, G05ApprovalModel.status == "approved").order_by(G05ApprovalModel.created_at.desc())) if run else None
        if job is None:
            raise ValueError("PLANNING_JOB_NOT_FOUND")
        if run is None:
            raise ValueError("RUN_NOT_FOUND")
        if resolution is None:
            raise ValueError("COMPATIBILITY_RESOLUTION_NOT_FOUND")
        if gate is None:
            raise ValueError("G05_APPROVAL_NOT_FOUND")
        package = resolution.package
        route = package.get("route") or []
        profile = package.get("selected_profile") or {}
        prerequisites = canonical_artifact_references({"artifact_id": item, "checksum": (gate.prerequisite_artifact_checksums or {}).get(item)} for item in (gate.prerequisite_artifact_ids or []))
        workspace = (run.workspace_aliases or {}).get("BASELINE_SANDBOX") or (run.workspace_aliases or {}).get("SOURCE_SNAPSHOT")
        return job.id, run.id, job.actor, run.state_version, resolution, gate, route, profile, prerequisites, workspace


def generate_plan_step(job_id: str, *, scope=session_scope) -> None:
    try:
        _, run_id, actor, expected_state_version, resolution, gate, route, profile, prerequisites, workspace = _approved_plan_request(job_id, scope=scope)
        if not workspace:
            raise PlanningInputResolutionError("PLANNING_WORKSPACE_EVIDENCE_MISSING", "No persisted baseline workspace is available for project-aware planning.")
        if not gate.workspace_fingerprint:
            raise PlanningInputResolutionError("PLANNING_WORKSPACE_FINGERPRINT_MISSING", "The approved G05 package has no physical workspace fingerprint.")
        try:
            integrity = WorkspaceIntegrityService().verify(workspace, expected_fingerprint=gate.workspace_fingerprint or "")
        except WorkspaceIntegrityError as error:
            raise PlanningInputResolutionError(error.code, "The G05-approved workspace changed before planning.", details=error) from error
        try:
            project_inputs = ProjectPlanningResolver().resolve(workspace)
        except ProjectPlanningResolutionError as error:
            raise PlanningInputResolutionError(error.code, "Project-aware planning inputs could not be resolved.", details=error.cause) from error
        if not project_inputs.build_targets:
            raise PlanningInputResolutionError("PLANNING_BUILD_TARGET_MISSING", "No supported build target is configured.")
        selection = profile.get("project_selection") or profile.get("selected_project") or resolution.package.get("project_selection") or {}
        try:
            selected_target = project_inputs.select_build_target(project_name=selection.get("project_name"), target_name=selection.get("build_target"))
        except ProjectPlanningResolutionError as error:
            raise PlanningInputResolutionError(error.code, "An explicit, unambiguous Angular project/build target selection is required.", details=error) from error
        builder = selected_target.builder
        physical_fingerprint = integrity.actual_fingerprint
        plan = PlanningEvidenceApplicationService(scope=scope).create(run_id, PlanCreateRequest(
            expected_state_version=expected_state_version,
            idempotency_key=f"plan:auto:{run_id}:{gate.package_checksum}",
            source_exact=resolution.source_exact,
            source_family=resolution.source_family,
            target_family=resolution.target_family,
            catalogue_version=resolution.catalogue_version,
            input_fingerprint=physical_fingerprint,
            evidence_set_checksum=gate.artifact_set_checksum,
            input_workspace_fingerprint=physical_fingerprint,
            execution_profile_id=profile.get("profile_id", ""),
            stage_route=[(item["source_family"], item["target_family"], item["stage_id"], item["target_angular_exact"], item.get("target_cli_exact", item["target_angular_exact"])) for item in route],
            target_cli_exact=route[0].get("target_cli_exact") if route else None,
            builder=builder,
            prerequisite_artifacts=list(prerequisites),
            correlation_id=f"planning:{run_id}",
        ), actor)
        with scope() as session:
            job = session.get(PlanningJobModel, job_id)
            job.status = "running_planning_review"
            job.current_step = "running_planning_review"
            job.state_version = plan.state_version
            job.attempt = 0
            job.lease_expires_at = None
            job.worker_id = None
            job.last_error_code = job.last_error_message = job.last_error_stage = None
            job.retryable = False
            job.updated_at = datetime.now(UTC)
    except Exception as error:
        _mark_retry(job_id, disposition=classify_planning_failure(error), stage="generating_plan", diagnostic=getattr(error, "details", None), scope=scope)


def run_planning_review_step(job_id: str, *, scope=session_scope) -> None:
    try:
        _, run_id, actor, expected_state_version, _, gate, _, _, prerequisites, _ = _approved_plan_request(job_id, scope=scope)
        with scope() as session:
            pointer = session.scalar(select(ActivePlanVersionModel).where(ActivePlanVersionModel.run_id == run_id, ActivePlanVersionModel.scope == "migration"))
            plan = session.get(MigrationPlanModel, pointer.migration_plan_id) if pointer else None
            stage = session.get(StageExecutionPlanModel, pointer.stage_plan_id) if pointer and pointer.stage_plan_id else session.scalar(select(StageExecutionPlanModel).where(StageExecutionPlanModel.migration_plan_id == plan.id).order_by(StageExecutionPlanModel.version.desc())) if plan else None
        if plan is None or stage is None:
            raise ValueError("MIGRATION_PLAN_NOT_FOUND")
        PlanningReviewEvidenceApplicationService(scope=scope).explain(run_id, PlanningExplanationApiRequest(
            expected_state_version=expected_state_version,
            idempotency_key=f"review:auto:{run_id}:{plan.checksum}",
            plan=plan.plan,
            stage_plan=stage.stage_plan,
            artifact_set_checksum=gate.artifact_set_checksum,
            prerequisite_artifacts=list(prerequisites),
            plan_version=int(plan.plan["version"]),
            correlation_id=f"planning:{run_id}",
        ), actor)
    except Exception as error:
        _mark_retry(job_id, disposition=classify_planning_failure(error), stage="running_planning_review", diagnostic=getattr(error, "details", None), scope=scope)


def dispatch_planning_job(run_id: str, *, worker_id: str = "planning-worker", scope=session_scope) -> None:
    job_id = claim_planning_job(run_id, worker_id, scope=scope)
    if job_id is None:
        return
    with scope() as session:
        job = session.get(PlanningJobModel, job_id)
        step = job.current_step if job else None
    if step == "resolving_feasibility" or step == "recovery":
        resolve_feasibility_step(job_id, scope=scope)
    elif step == "generating_plan":
        generate_plan_step(job_id, scope=scope)
    elif step == "running_planning_review":
        run_planning_review_step(job_id, scope=scope)
    else:
        _mark_retry(job_id, disposition=PlanningFailureDisposition("INVALID_PLANNING_STAGE", False, True, "The planning job has no executable current step."), stage=step or "unknown", scope=scope)


def dispatch_after_g05(run_id: str, *, worker_id: str = "http-planning-dispatcher", scope=session_scope) -> None:
    """Mark the durable continuation executable; a worker performs the stage."""
    with scope() as session:
        job = session.scalar(select(PlanningJobModel).where(PlanningJobModel.run_id == run_id, PlanningJobModel.status == "waiting_g05").order_by(PlanningJobModel.created_at.desc()))
        if job is not None:
            job.status = "generating_plan"
            job.current_step = "generating_plan"
            job.updated_at = datetime.now(UTC)


def dispatch_due_planning_jobs(*, worker_id: str = "planning-worker") -> int:
    """Consume persisted queued and due retry jobs after startup/recovery."""
    now = datetime.now(UTC)
    with session_scope() as session:
        run_ids = list(session.scalars(select(MigrationRunModel.id).join(PlanningJobModel, PlanningJobModel.run_id == MigrationRunModel.id).where(PlanningJobModel.status.in_({"queued_after_g04", "resolving_feasibility", "generating_plan", "running_planning_review", "waiting_retry"}), (PlanningJobModel.next_attempt_at.is_(None)) | (PlanningJobModel.next_attempt_at <= now))).all())
    for run_id in run_ids:
        dispatch_planning_job(run_id, worker_id=worker_id)
    return len(run_ids)
