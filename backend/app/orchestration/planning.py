"""Durable post-G04 planning dispatcher."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.api.planning_contracts import PlanCreateRequest
from app.api.planning_review_contracts import PlanningExplanationApiRequest
from app.repositories.models import CompatibilityResolutionModel, G05ApprovalModel, MigrationRunModel, PlanningJobModel
from app.repositories.session import session_scope
from app.services.artifact_binding import canonical_artifact_references
from app.services.compatibility_application_service import CompatibilityResolver
from app.services.compatibility_evidence_application_service import CompatibilityEvidenceApplicationService
from app.services.planning_evidence_application_service import PlanningEvidenceApplicationService
from app.services.planning_input_resolver import PlanningInputResolutionError, PlanningInputResolver
from app.services.planning_job_service import claim_planning_job
from app.services.planning_review_evidence_application_service import PlanningReviewEvidenceApplicationService
from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider


def _mark_retry(job_id: str, *, code: str, stage: str, message: str = "", scope=session_scope) -> None:
    with scope() as session:
        job = session.get(PlanningJobModel, job_id)
        if job is not None:
            now = datetime.now(UTC)
            terminal = job.attempt >= job.max_attempts
            job.status = "technical_failed" if terminal else "waiting_retry"
            job.current_step = stage
            job.last_error_code = code
            job.last_error_message = message[:4000] or None
            job.last_error_stage = stage
            job.retryable = not terminal
            job.first_failed_at = job.first_failed_at or now
            job.terminal_failed_at = now if terminal else None
            job.next_attempt_at = None if terminal else now + timedelta(seconds=min(300, 2 ** max(0, job.attempt - 1)))
            job.lease_expires_at = None
            job.worker_id = None
            job.updated_at = now


def dispatch_planning_job(run_id: str, *, worker_id: str = "http-planning-dispatcher", scope=session_scope) -> None:
    job_id = claim_planning_job(run_id, worker_id, scope=scope)
    if job_id is None:
        return
    now = datetime.now(UTC)
    try:
        with scope() as session:
            job = session.get(PlanningJobModel, job_id)
            run = session.get(MigrationRunModel, run_id)
            if job is None or run is None:
                return
            job.status = "resolving_feasibility"
            job.current_step = "resolving_feasibility"
            job.updated_at = now
            expected_state_version = run.state_version
            actor = job.actor
        with scope() as session:
            payload = PlanningInputResolver().resolve(session, run_id, actor=actor, expected_state_version=expected_state_version, idempotency_key=f"feasibility:auto:{job_id}", now=now)
        result = CompatibilityEvidenceApplicationService(resolver=CompatibilityResolver(CompatibilityCatalogueProvider().load())).resolve(run_id, payload, actor)
        with scope() as session:
            job = session.get(PlanningJobModel, job_id)
            if job is not None:
                job.status = "waiting_g05" if result.status != "blocked" else "completed_blocked"
                job.current_step = "waiting_g05" if result.status != "blocked" else "resolving_feasibility"
                job.last_error_code = None if result.status != "blocked" else "FEASIBILITY_BLOCKED"
                job.retryable = False
                job.lease_expires_at = None
                job.worker_id = None
                job.updated_at = datetime.now(UTC)
    except PlanningInputResolutionError as error:
        _mark_retry(job_id, code=error.code, stage="resolving_feasibility", message=error.message, scope=scope)
    except Exception as error:
        _mark_retry(job_id, code=type(error).__name__, stage="resolving_feasibility", message=str(error), scope=scope)


def dispatch_after_g05(run_id: str, *, worker_id: str = "http-planning-dispatcher", scope=session_scope) -> None:
    """Resume after G05 using the persisted resolution and approved bundle."""
    with scope() as session:
        job = session.scalar(select(PlanningJobModel).where(PlanningJobModel.run_id == run_id, PlanningJobModel.status == "generating_plan").order_by(PlanningJobModel.created_at.desc()))
        run = session.get(MigrationRunModel, run_id)
        resolution = session.scalar(select(CompatibilityResolutionModel).where(CompatibilityResolutionModel.run_id == run_id).order_by(CompatibilityResolutionModel.created_at.desc()))
        gate = session.scalar(select(G05ApprovalModel).where(G05ApprovalModel.run_id == run_id, G05ApprovalModel.status == "approved").order_by(G05ApprovalModel.created_at.desc()))
        if job is None or run is None or resolution is None or gate is None:
            return
        actor = job.actor
        job_id = job.id
        expected_state_version = run.state_version
        package = resolution.package
        route = package.get("route") or []
        profile = package.get("selected_profile") or {}
        prerequisites = canonical_artifact_references({"artifact_id": item, "checksum": (gate.prerequisite_artifact_checksums or {}).get(item)} for item in (gate.prerequisite_artifact_ids or []))
    try:
        plan = PlanningEvidenceApplicationService(scope=scope).create(run_id, PlanCreateRequest(
            expected_state_version=expected_state_version,
            idempotency_key=f"plan:auto:{run_id}:{gate.package_checksum}",
            source_exact=resolution.source_exact,
            source_family=resolution.source_family,
            target_family=resolution.target_family,
            catalogue_version=resolution.catalogue_version,
            input_fingerprint=gate.artifact_set_checksum,
            execution_profile_id=profile.get("profile_id", ""),
            stage_route=[(item["source_family"], item["target_family"], item["stage_id"], item["target_angular_exact"], item.get("target_cli_exact", item["target_angular_exact"])) for item in route],
            target_cli_exact=route[0].get("target_cli_exact") if route else None,
            builder="@angular-devkit/build-angular:application",
            prerequisite_artifacts=list(prerequisites),
            correlation_id=f"planning:{run_id}",
        ), actor)
        with scope() as session:
            job = session.get(PlanningJobModel, job_id)
            if job is not None:
                job.status = "running_planning_review"
                job.current_step = "running_planning_review"
                job.state_version = plan.state_version
                job.lease_expires_at = None
                job.worker_id = None
                job.updated_at = datetime.now(UTC)
        PlanningReviewEvidenceApplicationService(scope=scope).explain(run_id, PlanningExplanationApiRequest(
            expected_state_version=plan.state_version,
            idempotency_key=f"review:auto:{run_id}:{plan.plan_checksum}",
            plan=plan.plan,
            stage_plan=plan.stage_plan,
            artifact_set_checksum=gate.artifact_set_checksum,
            prerequisite_artifacts=list(prerequisites),
            plan_version=int(plan.plan["version"]),
            correlation_id=f"planning:{run_id}",
        ), actor)
    except Exception as error:
        _mark_retry(job_id, code=type(error).__name__, stage="generating_plan", message=str(error), scope=scope)


def dispatch_due_planning_jobs(*, worker_id: str = "planning-worker") -> int:
    """Consume persisted queued and due retry jobs after startup/recovery."""
    now = datetime.now(UTC)
    with session_scope() as session:
        run_ids = list(session.scalars(select(MigrationRunModel.id).join(PlanningJobModel, PlanningJobModel.run_id == MigrationRunModel.id).where(PlanningJobModel.status.in_({"queued_after_g04", "waiting_retry"}), (PlanningJobModel.next_attempt_at.is_(None)) | (PlanningJobModel.next_attempt_at <= now))).all())
    for run_id in run_ids:
        dispatch_planning_job(run_id, worker_id=worker_id)
    return len(run_ids)
