"""Opt-in proof of the real Angular 18 start-to-G03 workflow.

The test deliberately requires an external fixture and an explicitly enabled
runtime. It never creates a fake compatible profile or replaces the command
worker. Generate a small Angular 18 workspace outside this repository, set
``AMF_ANGULAR18_SOURCE`` and ``AMF_ANGULAR18_TARGET_PARENT``, optionally set
``AMF_ANGULAR18_RUNTIME_ROOT`` to a compatible existing Node installation,
then run with ``AMF_RUN_ANGULAR18_INTEGRATION=1``.
"""

from __future__ import annotations

import hashlib
import os
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.g02_contracts import G02DecisionRequest
from app.core.config import Settings
from app.domain.g02 import G02Decision
from app.domain.preflight import PreflightSnapshot
from app.domain.system import RefreshEnvironmentRequest
from app.orchestration.source_intake import SourceIntakeDispatcher
from app.repositories.models import (
    ApprovalGateModel,
    Base,
    BaselineAssessmentModel,
    EnvironmentCapabilityModel,
    G02ApprovalModel,
    MigrationRunModel,
    PreflightModel,
    SourceIntakeJobModel,
    WorkflowEventModel,
)
from app.repositories import session as repository_session
from app.services.environment_diagnostics_application_service import EnvironmentDiagnosticsApplicationService
from app.services.g02_application_service import G02ApprovalApplicationService
from app.services.migration_run_service import CreateRunRequest, MigrationRunService


def _tree_fingerprint(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.mark.skipif(
    os.getenv("AMF_RUN_ANGULAR18_INTEGRATION") != "1",
    reason="set AMF_RUN_ANGULAR18_INTEGRATION=1 with an external Angular 18 fixture to run",
)
def test_real_angular18_start_to_g03_preserves_external_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_value = os.getenv("AMF_ANGULAR18_SOURCE", "").strip()
    target_parent_value = os.getenv("AMF_ANGULAR18_TARGET_PARENT", "").strip()
    if not source_value or not target_parent_value:
        pytest.skip("AMF_ANGULAR18_SOURCE and AMF_ANGULAR18_TARGET_PARENT must point to existing external directories")
    source = Path(source_value).expanduser().resolve()
    target_parent = Path(target_parent_value).expanduser().resolve()
    if not source.is_dir() or not target_parent.is_dir():
        pytest.skip("AMF_ANGULAR18_SOURCE and AMF_ANGULAR18_TARGET_PARENT must point to existing external directories")

    runtime_root = os.getenv("AMF_ANGULAR18_RUNTIME_ROOT")
    if runtime_root:
        monkeypatch.setenv("PATH", str(Path(runtime_root).resolve()) + os.pathsep + os.environ.get("PATH", ""))

    before_source = _tree_fingerprint(source)
    data_root = tmp_path / "control-tower-data"
    settings = Settings(
        _env_file=None,
        application_data_root=data_root,
        database_url=f"sqlite:///{(data_root / 'integration.db').as_posix()}",
        artifact_root=data_root / "artifacts",
        workspace_root=data_root / "workspaces",
        snapshot_root=data_root / "snapshots",
        delivery_root=data_root / "delivery",
        sandbox_root=data_root / "sandboxes",
        allowed_source_roots=[source.parent],
        allowed_target_roots=[target_parent],
        minimum_free_disk_bytes=0,
    )
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    original_session_local = repository_session.SessionLocal
    repository_session.SessionLocal = sessions

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    try:
        # Environment readiness is gathered through the same authoritative
        # command probes used by production, so an incompatible runtime is a
        # real blocker rather than a test fixture substitution.
        diagnostics = EnvironmentDiagnosticsApplicationService(settings, session_scope_factory=scope)
        environment = diagnostics.refresh(RefreshEnvironmentRequest(idempotency_key="angular18-integration-environment", actor="integration-test"))
        if environment.snapshot.status == "blocked" and "RUNTIME_NODE_NPM_NPX_UNAVAILABLE" in environment.snapshot.blockers:
            pytest.skip("the configured machine has no complete Node/npm/npx runtime for this integration")
        if any(item.version and item.version.startswith("v24.") for item in environment.snapshot.runtimes if item.name == "node"):
            pytest.skip("Node 24 is intentionally incompatible with the Angular 18 baseline policy")

        now = datetime.now(UTC)
        input_checksum = "sha256:angular18-integration-input"
        artifact_checksum = "sha256:angular18-integration-artifacts"
        output_root = target_parent / "angular18-control-tower-output"
        preflight = PreflightSnapshot(
            preflight_id="angular18-integration-preflight",
            gate_id="G01",
            gate_version="g01-v1",
            state_version=1,
            status="passed",
            created_at=now,
            expires_at=now + timedelta(hours=2),
            input_checksum=input_checksum,
            artifact_set_checksum=artifact_checksum,
            target_angular_family="19.x",
            migration_mode="strict-functional-parity",
            source_path=str(source),
            target_parent_path=str(target_parent),
            generated_output_name=output_root.name,
            resolved_output_root=str(output_root),
            target_output_path=str(output_root),
            approval_status="approved",
        )
        with scope() as session:
            session.add(PreflightModel(
                id=preflight.preflight_id,
                idempotency_key="angular18-integration-preflight-key",
                actor="integration-test",
                gate_id="G01",
                gate_version="g01-v1",
                state_version=1,
                status="passed",
                input_checksum=input_checksum,
                artifact_set_checksum=artifact_checksum,
                expires_at=preflight.expires_at,
                binding={},
                snapshot=preflight.model_dump(mode="json"),
                created_at=now,
            ))
            session.add(ApprovalGateModel(
                id="angular18-integration-g01",
                preflight_id=preflight.preflight_id,
                gate_id="G01",
                gate_version="g01-v1",
                status="approved",
                state_version=2,
                input_checksum=input_checksum,
                artifact_set_checksum=artifact_checksum,
                expires_at=preflight.expires_at,
                created_at=now,
            ))

        dispatcher = SourceIntakeDispatcher(settings)
        service = MigrationRunService(settings, session_scope_factory=scope, graph=dispatcher, now_provider=lambda: now)
        created = service.create(CreateRunRequest(
            preflight_id=preflight.preflight_id,
            input_checksum=input_checksum,
            artifact_set_checksum=artifact_checksum,
            idempotency_key="angular18-integration-create",
            actor="integration-test",
            client_constraints={"preserve_ui": True},
        ))
        started = service.start(run_id=created.run_id, expected_state_version=created.state_version, idempotency_key="angular18-integration-start", actor="integration-test")
        assert started.job_id

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            with scope() as session:
                approval = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == created.run_id))
                job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == created.run_id))
                if approval is not None or (job is not None and job.status == "failed"):
                    break
            time.sleep(0.5)
        with scope() as session:
            approval = session.scalar(select(G02ApprovalModel).where(G02ApprovalModel.run_id == created.run_id))
            job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == created.run_id))
            assert job is not None and job.status != "failed", job.last_error_message if job else "intake job missing"
            assert approval is not None, "G02 did not become available after source intake"

        decided = G02ApprovalApplicationService(session_scope_factory=scope).decide(created.run_id, G02DecisionRequest(
            expected_state_version=approval.state_version,
            idempotency_key="angular18-integration-g02-approval",
            actor="integration-test",
            decision=G02Decision.APPROVED,
            gate_id="G02",
        ))
        assert decided.status in {"approved", "approved_with_comment"}

        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            with scope() as session:
                assessment = session.scalar(select(BaselineAssessmentModel).where(BaselineAssessmentModel.run_id == created.run_id))
                job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == created.run_id))
                if assessment is not None or (job is not None and job.status == "failed"):
                    break
            time.sleep(1)
        with scope() as session:
            assessment = session.scalar(select(BaselineAssessmentModel).where(BaselineAssessmentModel.run_id == created.run_id))
            job = session.scalar(select(SourceIntakeJobModel).where(SourceIntakeJobModel.run_id == created.run_id))
            assert job is not None and job.status != "failed", job.last_error_message if job else "intake job missing"
            assert assessment is not None and assessment.status in {"qualified", "qualified_with_known_failures"}
            events = list(session.scalars(select(WorkflowEventModel).where(WorkflowEventModel.run_id == created.run_id)))
            event_types = {event.event_type for event in events}
            assert {"SOURCE_INTAKE_COMPLETED", "G02_APPROVED", "BASELINE_INSTALL_SUCCEEDED", "G03_CREATED"} <= event_types
            assert session.scalar(select(EnvironmentCapabilityModel)) is not None

        assert _tree_fingerprint(source) == before_source
    finally:
        repository_session.SessionLocal = original_session_local
        engine.dispose()
