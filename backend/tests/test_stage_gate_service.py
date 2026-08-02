from pathlib import Path

import pytest

from app.domain.transformation import StageGateDecisionRequest
from app.repositories.models import MigrationPlanModel
from app.services.stage_gate_service import StageGateError, StageGateService
from app.services.transformation_continuation_service import TransformationContinuationService
from tests.test_transformation_continuation import NOW, _create, _session


def _decision(version: int, *, key: str = "g07-approve", fingerprint: str = "sha256:workspace"):
    return StageGateDecisionRequest(
        expected_state_version=version,
        idempotency_key=key,
        package_checksum="sha256:g07-package",
        workspace_fingerprint=fingerprint,
        decision="approve",
        correlation_id="correlation-1",
    )


def test_g07_is_bound_to_state_package_and_workspace_and_wakes_once(tmp_path: Path):
    engine, session = _session(tmp_path)
    continuation = _create(TransformationContinuationService(), session)
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    gate = StageGateService().create(
        session,
        continuation,
        gate_id="G07",
        package_artifact_id="artifact-g07",
        package_checksum="sha256:g07-package",
        artifact_set_checksum="sha256:g07-set",
        workspace_fingerprint="sha256:workspace",
        now=NOW,
    )

    assert continuation.status == "waiting_gate"
    assert gate.expected_state_version == continuation.state_version
    result = StageGateService().decide(
        session, continuation, "G07", _decision(continuation.state_version), actor="operator", now=NOW
    )
    replay = StageGateService().decide(
        session, continuation, "G07", _decision(gate.expected_state_version), actor="operator", now=NOW
    )

    assert result.id == replay.id
    assert continuation.status == "queued"
    assert continuation.current_node == "bootstrap_install"
    assert continuation.wake_sequence == 1
    session.close()
    engine.dispose()


def test_g07_rejects_stale_workspace_fingerprint(tmp_path: Path):
    engine, session = _session(tmp_path)
    continuation = _create(TransformationContinuationService(), session)
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    StageGateService().create(
        session,
        continuation,
        gate_id="G07",
        package_artifact_id="artifact-g07",
        package_checksum="sha256:g07-package",
        artifact_set_checksum="sha256:g07-set",
        workspace_fingerprint="sha256:workspace",
        now=NOW,
    )

    with pytest.raises(StageGateError, match="fingerprint"):
        StageGateService().decide(
            session,
            continuation,
            "G07",
            _decision(continuation.state_version, fingerprint="sha256:stale"),
            actor="operator",
            now=NOW,
        )
    session.close()
    engine.dispose()


def test_create_binds_actual_plan_version_not_literal_one(tmp_path: Path):
    engine, session = _session(tmp_path)
    plan = session.get(MigrationPlanModel, "plan-1")
    plan.version = 2
    session.commit()
    continuation = _create(TransformationContinuationService(), session)
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    gate = StageGateService().create(
        session,
        continuation,
        gate_id="G07",
        package_artifact_id="artifact-g07",
        package_checksum="sha256:g07-package",
        artifact_set_checksum="sha256:g07-set",
        workspace_fingerprint="sha256:workspace",
        now=NOW,
    )

    assert gate.plan_version == 2
    session.close()
    engine.dispose()


def test_decide_rejects_stale_plan_version_and_marks_package_stale(tmp_path: Path):
    engine, session = _session(tmp_path)
    continuation = _create(TransformationContinuationService(), session)
    continuation.status = "running"
    continuation.worker_id = "worker-1"
    gate = StageGateService().create(
        session,
        continuation,
        gate_id="G07",
        package_artifact_id="artifact-g07",
        package_checksum="sha256:g07-package",
        artifact_set_checksum="sha256:g07-set",
        workspace_fingerprint="sha256:workspace",
        now=NOW,
    )
    plan = session.get(MigrationPlanModel, "plan-1")
    plan.version = 2
    session.commit()

    with pytest.raises(StageGateError, match="stale"):
        StageGateService().decide(
            session,
            continuation,
            "G07",
            _decision(continuation.state_version),
            actor="operator",
            now=NOW,
        )

    assert gate.status == "stale"
    assert gate.stale_at == NOW
    session.close()
    engine.dispose()
