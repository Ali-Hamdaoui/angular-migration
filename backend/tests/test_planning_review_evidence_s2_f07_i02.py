from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.planning_review_contracts import (
    G06DecisionApiRequest,
    PlanRevisionApiRequest,
    PlanningExplanationApiRequest,
)
from app.api.routes import planning_review as planning_review_routes
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.planning import PlanGenerationRequest
from app.domain.planning_review import (
    G06Decision,
    PlanningNarrative,
    PlanningPackage,
    PlanningReview,
    PlanningReviewDecision,
)
from app.repositories.models import (
    ActivePlanVersionModel,
    Base,
    BuildSystemDecisionModel,
    G06ApprovalModel,
    MigrationPlanModel,
    MigrationRunModel,
    PlanRevisionModel,
    PlanningReviewModel,
    StageExecutionPlanModel,
    WorkflowEventModel,
)
from app.repositories.session import create_database_engine
from app.services.planning_application_service import PlanningApplicationService
from app.services.planning_review_evidence_application_service import (
    PlanningReviewEvidenceApplicationService,
    PlanningReviewEvidenceError,
)


NOW = datetime(2026, 7, 19, tzinfo=UTC)


def setup(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'review.db'}", sqlite_wal_enabled=False)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    root = tmp_path / "artifacts" / "run-1"
    store = LocalFilesystemArtifactStore(tmp_path / "artifacts", fixed_run_root=root)
    store.ensure_run_layout("run-1")
    generated = PlanningApplicationService().generate(
        PlanGenerationRequest(
            run_id="run-1",
            expected_state_version=1,
            idempotency_key="plan-1",
            actor="operator",
            source_exact="18.2.13",
            source_family="angular-18.x",
            target_family="angular-21.x",
            catalogue_version="catalog-v1",
            input_fingerprint="sha256:" + "1" * 64,
            execution_profile_id="profile-node22-npm10",
            builder="@angular-devkit/build-angular:application",
            target_cli_exact="19.2.0",
            stage_route=(
                ("angular-18.x", "angular-19.x", "stage-18-to-19", "19.2.0"),
                ("angular-19.x", "angular-20.x", "stage-19-to-20", "20.0.0"),
                ("angular-20.x", "angular-21.x", "stage-20-to-21", "21.0.0"),
            ),
        )
    )
    with sessions.begin() as session:
        run = MigrationRunModel(
            id="run-1",
            status="RUNNING",
            run_phase="FEASIBILITY_PLANNING",
            phase_status="running",
            approval_status="approved",
            repair_status="not_required",
            state_version=1,
            actor="operator",
            artifact_root=str(root),
            created_at=NOW,
            updated_at=NOW,
        )
        plan = MigrationPlanModel(
            id=generated.plan.plan_id,
            run_id="run-1",
            idempotency_key="plan-1",
            request_checksum="sha256:" + "a" * 64,
            actor="operator",
            correlation_id=None,
            status="generated",
            version=1,
            plan=generated.plan.model_dump(mode="json"),
            checksum=generated.plan.checksum,
            artifact_ids=[],
            artifact_checksums={},
            state_version=1,
            event_sequence=0,
            created_at=NOW,
            updated_at=NOW,
        )
        stage = StageExecutionPlanModel(
            id=generated.first_stage_plan.stage_plan_id,
            run_id="run-1",
            migration_plan_id=plan.id,
            stage_id=generated.first_stage_plan.stage_id,
            idempotency_key="plan-1",
            request_checksum=plan.request_checksum,
            actor="operator",
            correlation_id=None,
            status="generated",
            version=1,
            stage_plan=generated.first_stage_plan.model_dump(mode="json"),
            checksum=generated.first_stage_plan.checksum,
            artifact_ids=[],
            artifact_checksums={},
            state_version=1,
            event_sequence=0,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add_all(
            [
                run,
                plan,
                stage,
                BuildSystemDecisionModel(
                    id="decision-1",
                    run_id="run-1",
                    stage_plan_id=stage.id,
                    decision_id=generated.first_stage_plan.build_system_decision.decision_id,
                    decision=generated.first_stage_plan.build_system_decision.model_dump(mode="json"),
                    checksum=generated.first_stage_plan.build_system_decision.checksum,
                    created_at=NOW,
                ),
                ActivePlanVersionModel(
                    id="active-1",
                    run_id="run-1",
                    scope="migration",
                    migration_plan_id=plan.id,
                    stage_plan_id=None,
                    version=1,
                    state_version=1,
                    updated_at=NOW,
                ),
                ActivePlanVersionModel(
                    id="active-stage-1",
                    run_id="run-1",
                    scope=stage.stage_id,
                    migration_plan_id=plan.id,
                    stage_plan_id=stage.id,
                    version=1,
                    state_version=1,
                    updated_at=NOW,
                ),
            ]
        )

    def scope():
        from contextlib import contextmanager

        @contextmanager
        def managed():
            session = sessions()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return managed()

    return (
        generated,
        sessions,
        store,
        PlanningReviewEvidenceApplicationService(
            scope=scope, now_provider=lambda: NOW, artifact_store_factory=lambda _run: store
        ),
    )


class FakePlanningAgent:
    def explain(self, request):
        checksum = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    {"plan": request.plan, "stage_plan": request.stage_plan}, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        )
        narrative = PlanningNarrative(
            summary="The deterministic plan is ready for human review.",
            rationale=["The route remains adjacent-major."],
            risks=[],
            unresolved_questions=[],
            deterministic_plan_checksum=checksum,
        )
        proposer_checksum = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(narrative.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        review = PlanningReview(
            decision=PlanningReviewDecision.ACCEPT,
            notes=[],
            policy_concerns=[],
            confidence="high",
            deterministic_plan_checksum=checksum,
            proposer_output_checksum=proposer_checksum,
        )
        usage = {
            "input_tokens": 10,
            "output_tokens": 10,
            "total_tokens": 20,
            "input_price_per_million": 1,
            "output_price_per_million": 1,
            "input_cost_usd": 0.00001,
            "output_cost_usd": 0.00002,
            "total_cost_usd": 0.00003,
            "model_deployment_alias": "test",
            "pricing_version": "test-v1",
        }
        return PlanningPackage(
            run_id=request.run_id,
            plan_version=request.plan_version,
            artifact_set_checksum=request.artifact_set_checksum,
            deterministic_plan_checksum=checksum,
            plan_checksum=request.plan["checksum"],
            stage_plan_checksum=request.stage_plan["checksum"],
            narrative=narrative,
            proposer_output_checksum=proposer_checksum,
            reviewer=review,
            reviewer_output_checksum="sha256:" + "b" * 64,
            usage=usage,
            reviewer_usage=usage,
            workspace_fingerprint=request.workspace_fingerprint,
        )


def test_revision_explanation_and_g06_persist_evidence_and_events(tmp_path):
    generated, sessions, store, service = setup(tmp_path)
    revision = service.revise(
        "run-1",
        PlanRevisionApiRequest(
            expected_state_version=1,
            idempotency_key="revision-1",
            plan=generated.plan.model_dump(mode="json"),
            stage_plan=generated.first_stage_plan.model_dump(mode="json"),
            changes={"execution_profile_id": "profile-node23-npm10"},
            artifact_set_checksum="sha256:" + "2" * 64,
        ),
        "operator",
    )
    service._planning_agent = FakePlanningAgent()
    explanation = service.explain(
        "run-1",
        PlanningExplanationApiRequest(
            expected_state_version=2,
            idempotency_key="explain-1",
            plan=revision.plan,
            stage_plan=revision.stage_plan,
            artifact_set_checksum="sha256:" + "3" * 64,
            plan_version=2,
        ),
        "operator",
    )
    assert explanation.gate_status == "pending"
    assert len(explanation.artifact_ids) == 9
    with sessions() as session:
        assert session.query(PlanRevisionModel).count() == 1
        assert session.query(PlanningReviewModel).one().status == "completed"
        gate = session.query(G06ApprovalModel).one()
        assert gate.status == "pending"
        assert {event.event_type for event in session.query(WorkflowEventModel).all()} == {
            "PLAN_REVISION_CREATED",
            "PLANNING_AGENT_COMPLETED",
            "G06_CREATED",
        }
    decision = service.decide_g06(
        "run-1",
        G06DecisionApiRequest(
            expected_state_version=3,
            idempotency_key="decision-1",
            gate_version=explanation.gate_version,
            package_checksum=explanation.package_checksum,
            artifact_set_checksum=explanation.package["artifact_set_checksum"],
            plan_checksum=explanation.package["plan_checksum"],
            stage_plan_checksum=explanation.package["stage_plan_checksum"],
            decision=G06Decision.APPROVE,
        ),
        "operator",
    )
    assert decision.accepted is True
    assert all(
        store.read_artifact_by_id(item).ref.checksum == explanation.artifact_checksums[item]
        for item in explanation.artifact_ids
    )


def test_revision_and_decision_reject_stale_or_conflicting_requests(tmp_path):
    generated, _, _, service = setup(tmp_path)
    stale = PlanRevisionApiRequest(
        expected_state_version=9,
        idempotency_key="revision-1",
        plan=generated.plan.model_dump(mode="json"),
        stage_plan=generated.first_stage_plan.model_dump(mode="json"),
        changes={"catalogue_version": "catalog-v2"},
        artifact_set_checksum="sha256:" + "2" * 64,
    )
    with pytest.raises(PlanningReviewEvidenceError) as error:
        service.revise("run-1", stale, "operator")
    assert error.value.code == "STALE_STATE_VERSION"
