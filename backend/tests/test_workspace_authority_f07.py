"""Tests for F07 workspace authority: generation registry, active resolver, guarded promotion."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.workspace_authority import WorkspacePromotionRequest, evaluate_promotion
from app.repositories.models import (
    MigrationRunModel,
    MigrationStageModel,
    StageWorkspaceBindingModel,
    WorkspaceGenerationModel,
)
from app.repositories.session import session_scope
from app.services.workspace_authority_service import WorkspaceAuthorityError, WorkspaceAuthorityService

NOW = datetime.now(UTC)


def _seed_run(run_id: str) -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      created_at=NOW, updated_at=NOW))
        session.commit()


def _seed_stage(run_id: str, stage_id: str) -> None:
    with session_scope() as session:
        session.add(MigrationStageModel(id=stage_id, run_id=run_id, stage_order=1,
                                        source_version_family="angular-18.x", target_version_family="angular-19.x",
                                        status="planned", created_at=NOW))
        session.commit()


def _request(run_id: str, alias: str = "STAGE_WORKSPACE_1", generation: int = 1,
             fingerprint: str | None = None, stage_id: str | None = None, **changes) -> WorkspacePromotionRequest:
    values = {
        "run_id": run_id,
        "stage_id": stage_id or f"stage-{run_id}",
        "alias": alias,
        "generation": generation,
        "workspace_path": f"/ws/gen-{generation}",
        "fingerprint": fingerprint or f"fp-{generation}-{uuid4().hex[:8]}",
        "input_fingerprint": None,
    }
    values.update(changes)
    return WorkspacePromotionRequest(**values)


def test_promotion_decision_monotonic_guard():
    first = evaluate_promotion(_request("run", generation=1), None)
    assert first.allowed is True
    second = evaluate_promotion(_request("run", generation=2), 1)
    assert second.allowed is True
    stale = evaluate_promotion(_request("run", generation=1), 2)
    assert stale.allowed is False
    assert "not strictly newer" in stale.reason
    equal = evaluate_promotion(_request("run", generation=2), 2)
    assert equal.allowed is False


def test_promote_first_generation_becomes_active(tmp_path: Path):
    run_id = f"run-f07-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    _seed_run(run_id)
    _seed_stage(run_id, stage_id)
    service = WorkspaceAuthorityService()
    request = _request(run_id, generation=1, stage_id=stage_id)
    decision = service.promote(request)
    assert decision.allowed is True
    assert service.current_generation(run_id, stage_id, "STAGE_WORKSPACE_1") == 1
    active = service.resolve_active(run_id, stage_id, "STAGE_WORKSPACE_1")
    assert active is not None
    assert active.generation == 1
    assert active.fingerprint == request.fingerprint


def test_promote_second_generation_retires_old_active(tmp_path: Path):
    run_id = f"run-f07-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    _seed_run(run_id)
    _seed_stage(run_id, stage_id)
    service = WorkspaceAuthorityService()
    service.promote(_request(run_id, generation=1, stage_id=stage_id))
    service.promote(_request(run_id, generation=2, stage_id=stage_id))
    assert service.current_generation(run_id, stage_id, "STAGE_WORKSPACE_1") == 2
    active = service.resolve_active(run_id, stage_id, "STAGE_WORKSPACE_1")
    assert active is not None and active.generation == 2
    with session_scope() as session:
        generations = session.query(WorkspaceGenerationModel).filter_by(run_id=run_id).all()
        assert {g.status for g in generations} == {"active", "retired"}
        # exactly one active binding and exactly one active generation
        assert session.query(StageWorkspaceBindingModel).filter_by(run_id=run_id, active=True).count() == 1
        assert session.query(WorkspaceGenerationModel).filter_by(run_id=run_id, status="active").count() == 1


def test_promote_stale_generation_rejected(tmp_path: Path):
    run_id = f"run-f07-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    _seed_run(run_id)
    _seed_stage(run_id, stage_id)
    service = WorkspaceAuthorityService()
    service.promote(_request(run_id, generation=3, stage_id=stage_id))
    with pytest.raises(WorkspaceAuthorityError) as exc:
        service.promote(_request(run_id, generation=1))
    assert exc.value.code == "STALE_GENERATION"
    # the active workspace is still generation 3
    active = service.resolve_active(run_id, stage_id, "STAGE_WORKSPACE_1")
    assert active is not None and active.generation == 3


def test_promote_unknown_run_rejected(tmp_path: Path):
    service = WorkspaceAuthorityService()
    with pytest.raises(WorkspaceAuthorityError) as exc:
        service.promote(_request("run-missing", generation=1))
    assert exc.value.code == "RUN_NOT_FOUND"


def test_resolve_active_returns_none_when_stale_active_binding(tmp_path: Path):
    """An old active binding that is not the highest generation must not resolve as active."""
    run_id = f"run-f07-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    _seed_run(run_id)
    _seed_stage(run_id, stage_id)
    service = WorkspaceAuthorityService()
    service.promote(_request(run_id, generation=1, stage_id=stage_id))
    # simulate corruption: a new generation exists but the binding is not promoted
    with session_scope() as session:
        session.add(WorkspaceGenerationModel(
            id=f"gen-manual-{uuid4().hex[:8]}", run_id=run_id, stage_id=stage_id, alias="STAGE_WORKSPACE_1",
            generation=5, workspace_path="/ws/gen-5", fingerprint="fp-5",
            status="prepared", active_binding_id=None, created_at=NOW,
        ))
        session.commit()
    assert service.current_generation(run_id, stage_id, "STAGE_WORKSPACE_1") == 5
    assert service.resolve_active(run_id, stage_id, "STAGE_WORKSPACE_1") is None


def test_stage_scoped_generation_is_isolated(tmp_path: Path):
    run_id = f"run-f07-{uuid4().hex[:8]}"
    stage_id = f"stage-f07-{uuid4().hex[:8]}"
    _seed_run(run_id)
    _seed_stage(run_id, stage_id)
    service = WorkspaceAuthorityService()
    service.promote(_request(run_id, alias="STAGE_WORKSPACE_1", stage_id=stage_id, generation=1))
    # a different stage (None) has no active workspace
    assert service.resolve_active(run_id, "other-stage", "STAGE_WORKSPACE_1") is None
    assert service.resolve_active(run_id, stage_id, "STAGE_WORKSPACE_1") is not None


def test_concurrent_promotions_cannot_activate_two_generations(tmp_path: Path):
    """Two racing promotions must not both become active (RV-F07 concurrency guard)."""
    import threading

    run_id = f"run-f07-{uuid4().hex[:8]}"
    stage_id = f"stage-{run_id}"
    _seed_run(run_id)
    _seed_stage(run_id, stage_id)
    service = WorkspaceAuthorityService()

    barrier = threading.Barrier(2)
    results: list[str] = []

    def promote_generation(generation: int) -> None:
        barrier.wait()
        try:
            service.promote(_request(run_id, generation=generation, stage_id=stage_id))
            results.append(f"ok:{generation}")
        except WorkspaceAuthorityError:
            results.append(f"rejected:{generation}")

    threads = [threading.Thread(target=promote_generation, args=(g,)) for g in (4, 5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert "ok:4" in results or "ok:5" in results
    # only one generation became active; the other was rejected or serialized
    with session_scope() as session:
        active = session.query(WorkspaceGenerationModel).filter_by(
            run_id=run_id, stage_id=stage_id, status="active"
        ).all()
        assert len(active) == 1
        active_gen = active[0].generation
    resolved = service.resolve_active(run_id, stage_id, "STAGE_WORKSPACE_1")
    assert resolved is not None
    assert resolved.generation == active_gen
    # the resolved workspace must match the active generation's own ledger row
    assert resolved.fingerprint == active[0].fingerprint
