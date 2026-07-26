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
import json
import os
import re
import shutil
import subprocess
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


def _validate_external_angular18_fixture(source: Path) -> None:
    package_path = source / "package.json"
    workspace_path = source / "angular.json"
    lockfile_path = source / "package-lock.json"
    shrinkwrap_path = source / "npm-shrinkwrap.json"
    if not package_path.is_file() or not workspace_path.is_file() or not (lockfile_path.is_file() or shrinkwrap_path.is_file()):
        pytest.fail("The configured Angular 18 fixture must contain package.json, angular.json, and package-lock.json or npm-shrinkwrap.json.")
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
        lockfile = json.loads((lockfile_path if lockfile_path.is_file() else shrinkwrap_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        pytest.fail(f"The configured Angular 18 fixture metadata is not valid JSON: {error}")
    dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    required = {
        "@angular/core": r"^(?:\^|~|>=)?18\.",
        "@angular/cli": r"^(?:\^|~|>=)?18\.",
        "typescript": r"^(?:\^|~|>=)?5\.[45]\.",
        "rxjs": r"^(?:\^|~|>=)?(?:6\.|7\.)",
    }
    for name, pattern in required.items():
        value = dependencies.get(name)
        if not isinstance(value, str) or re.match(pattern, value) is None:
            pytest.fail(f"The configured fixture must declare a compatible {name} version; found {value!r}.")
    if not isinstance(lockfile, dict) or not isinstance(lockfile.get("lockfileVersion"), int):
        pytest.fail("The configured Angular 18 fixture lockfile must contain a numeric lockfileVersion.")
    projects = workspace.get("projects") if isinstance(workspace, dict) else None
    if not isinstance(projects, dict) or not projects:
        pytest.fail("The configured Angular 18 fixture must define at least one Angular workspace project.")
    if not any(isinstance(project, dict) and isinstance(project.get("architect", project.get("targets", {})), dict) for project in projects.values()):
        pytest.fail("The configured Angular 18 fixture must define Angular Architect/target configuration.")


def _generate_external_angular18_fixture(destination: Path) -> Path:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        pytest.fail("AMF_ANGULAR18_GENERATE_FIXTURE=1 requires an existing npx executable.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        npx,
        "--yes",
        "@angular/cli@18.2.12",
        "new",
        "angular18-baseline",
        "--directory",
        str(destination),
        "--routing",
        "--style",
        "css",
        "--package-manager",
        "npm",
        "--skip-git",
        "--defaults",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as error:
        pytest.fail(f"The pinned Angular 18 fixture generator could not complete: {error}")
    if result.returncode != 0:
        pytest.fail(f"The pinned Angular 18 fixture generator failed with exit code {result.returncode}: {result.stderr[-4000:]}")
    _validate_external_angular18_fixture(destination)
    return destination


@pytest.mark.skipif(
    os.getenv("AMF_RUN_ANGULAR18_INTEGRATION") != "1",
    reason="set AMF_RUN_ANGULAR18_INTEGRATION=1 with an external Angular 18 fixture to run",
)
def test_real_angular18_start_to_g03_preserves_external_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_value = os.getenv("AMF_ANGULAR18_SOURCE", "").strip()
    target_parent_value = os.getenv("AMF_ANGULAR18_TARGET_PARENT", "").strip()
    generate_fixture = os.getenv("AMF_ANGULAR18_GENERATE_FIXTURE") == "1"
    if not target_parent_value or (not source_value and not generate_fixture):
        pytest.skip("Set AMF_ANGULAR18_SOURCE or AMF_ANGULAR18_GENERATE_FIXTURE=1, plus AMF_ANGULAR18_TARGET_PARENT")
    target_parent = Path(target_parent_value).expanduser().resolve()
    if not target_parent.is_dir():
        pytest.fail("AMF_ANGULAR18_TARGET_PARENT must point to an existing external directory")
    source = Path(source_value).expanduser().resolve() if source_value else (tmp_path / "external-angular18-baseline").resolve()
    if source_value:
        if not source.is_dir():
            pytest.fail("AMF_ANGULAR18_SOURCE must point to an existing external directory")
        _validate_external_angular18_fixture(source)

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

        if generate_fixture:
            source = _generate_external_angular18_fixture(source)

        before_source = _tree_fingerprint(source)
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
