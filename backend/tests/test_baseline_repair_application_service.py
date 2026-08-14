from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.baseline_repair_contracts import BaselineRepairRequest
from app.repositories.models import (
    Base,
    BaselineAssessmentModel,
    BaselineQualificationModel,
    G03ApprovalModel,
    MigrationRunModel,
    SourceSnapshotModel,
)
from app.services.baseline_repair_application_service import (
    BaselineRepairApplicationError,
    BaselineRepairApplicationService,
    RECIPE_ID,
    SPEC_CONTENT,
    SPEC_PATH,
)
from app.services.patch_apply_service import PatchApplyService
from app.services.workspace_fingerprint import (
    PLANNING_FINGERPRINT_PROFILE,
    SOURCE_CONFIG_FINGERPRINT_PROFILE,
    workspace_fingerprint_v1,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _seed(tmp_path, *, comment=None, package_checksum=None):
    snapshot = tmp_path / "source-snapshot"
    sandbox = tmp_path / "baseline"
    artifact_root = tmp_path / "artifacts"
    (snapshot / "src" / "app").mkdir(parents=True)
    (sandbox / "src" / "app").mkdir(parents=True)
    artifact_root.mkdir(parents=True)

    source_files = {
        "src/app/app.component.ts": "export class AppComponent {}\n",
        "src/main.ts": "import './app/app.component';\n",
        "package.json": '{"scripts": {"test": "ng test"}}',
        "angular.json": '{"projects": {}}',
    }
    for relative, content in source_files.items():
        (snapshot / relative).write_text(content, encoding="utf-8")
        (sandbox / relative).write_text(content, encoding="utf-8")

    for relative in ("node_modules/.package-lock.json", "dist/portal/main.js", ".angular/cache/x.bin"):
        generated = sandbox / relative
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("generated", encoding="utf-8")

    package_checksum = package_checksum or ("sha256:" + "a" * 64)
    snapshot_id = "snapshot-1"
    comment = comment if comment is not None else f"Please apply {RECIPE_ID}"

    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(
            id="run-1", run_root=str(tmp_path), status="CREATED", run_phase="BASELINE",
            phase_status="running", approval_status="approved", repair_status="not_required",
            state_version=1, artifact_root=str(artifact_root),
            workspace_aliases={"BASELINE_SANDBOX": str(sandbox), "SOURCE_SNAPSHOT": str(snapshot)},
            created_at=NOW, updated_at=NOW,
        ))
        session.add(SourceSnapshotModel(
            id=snapshot_id, run_id="run-1", idempotency_key="snapshot", actor="operator",
            status="created", source_path=str(snapshot), snapshot_path=str(snapshot),
            policy_version="source-snapshot-policy-v1", file_count=4, total_size_bytes=0,
            exclusions=[], git_metadata={}, artifact_ids=[], state_version=1, event_sequence=1,
            created_at=NOW, updated_at=NOW,
        ))
        session.add(BaselineQualificationModel(
            id="baseline-1", run_id="run-1", idempotency_key="baseline", actor="operator",
            status="qualified", snapshot_id=snapshot_id, sandbox_path=str(sandbox),
            input_fingerprint="sha256:" + "b" * 64,
            sandbox_fingerprint=PLANNING_FINGERPRINT_PROFILE.fingerprint(sandbox),
            package={}, lockfile={}, sources=[], scripts=[], registry={}, blockers=[], warnings=[],
            authorization_status="authorized", checksum="sha256:" + "b" * 64, artifact_ids=[],
            state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW,
        ))
        assessment_fingerprint = workspace_fingerprint_v1(sandbox)
        session.add(BaselineAssessmentModel(
            id="assessment-1", run_id="run-1", idempotency_key="assess", actor="operator",
            status="blocked_by_environment", policy="strict_clean",
            policy_version="baseline-qualification-v1", blockers=["BASELINE_REQUIRED_TEST_NOT_PROVEN"],
            warnings=[], known_failures=[], evidence_confidence={},
            evidence_set_checksum="sha256:" + "d" * 64, sandbox_fingerprint=assessment_fingerprint,
            execution_profile_checksum="sha256:" + "e" * 64, source_artifact_ids=[], artifact_ids=[],
            artifact_checksums={}, parity_binding={}, package_checksum=package_checksum,
            state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW,
        ))
        session.add(G03ApprovalModel(
            id="g03-1", run_id="run-1", gate_id="G03", gate_version="g03-v1",
            idempotency_key="g03", actor="operator", status="modification_requested",
            decision="modification_requested", package_checksum=package_checksum,
            evidence_set_checksum="sha256:" + "d" * 64, qualification_status="blocked_by_environment",
            policy_version="baseline-qualification-v1", state_version=1, event_sequence=1,
            sandbox_fingerprint=assessment_fingerprint, execution_profile_checksum="sha256:" + "e" * 64,
            package={}, artifact_ids=[], comment=comment, created_at=NOW, updated_at=NOW,
        ))
        session.commit()

    @contextmanager
    def scope():
        with sessions() as session:
            yield session
            session.commit()

    return scope, sessions, engine, snapshot, sandbox, artifact_root, package_checksum, assessment_fingerprint


def _request(package_checksum):
    return BaselineRepairRequest(
        expected_state_version=1, idempotency_key="repair-1", actor="operator",
        recipe_id=RECIPE_ID, g03_package_checksum=package_checksum,
    )


def test_baseline_test_recipe_is_exact_and_patch_engine_applies_it(tmp_path: Path):
    workspace = tmp_path / "baseline"
    artifact_root = tmp_path / "artifacts" / "run-1"
    (workspace / "src" / "app").mkdir(parents=True)
    artifact_root.mkdir(parents=True)
    (workspace / "src" / "app" / "app.component.ts").write_text("export class AppComponent {}\n", encoding="utf-8")
    proposal = BaselineRepairApplicationService._proposal("run-1", "attempt-1", "sha256:" + "a" * 64)

    PatchApplyService().apply(
        proposal=proposal, workspace_path=str(workspace),
        expected_fingerprint=SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint(workspace),
        run_id="run-1", stage_id=None, artifact_root=str(artifact_root), attempt_id="attempt-1",
    )

    assert proposal["recipe_id"] == RECIPE_ID
    assert proposal["operations"] == [{"operation": "create_text_file", "path": SPEC_PATH, "content": SPEC_CONTENT}]
    assert (workspace / SPEC_PATH).read_text(encoding="utf-8") == SPEC_CONTENT


def test_baseline_repair_contract_rejects_unproven_recipe():
    with pytest.raises(ValidationError):
        BaselineRepairRequest(
            expected_state_version=1, idempotency_key="repair", actor="operator",
            recipe_id="SOMETHING-ELSE", g03_package_checksum="sha256:" + "a" * 64,
        )


def test_approved_source_fingerprint_ignores_snapshot_metadata_but_detects_source_change(tmp_path: Path):
    snapshot, baseline = tmp_path / "snapshot", tmp_path / "baseline"
    for root in (snapshot, baseline):
        (root / "src").mkdir(parents=True)
        (root / "src" / "main.ts").write_text("stable\n", encoding="utf-8")
    (snapshot / "source-manifest.json").write_text("{}", encoding="utf-8")
    (snapshot / "snapshot-fingerprint.json").write_text("{}", encoding="utf-8")

    assert BaselineRepairApplicationService._approved_source_fingerprint(snapshot) == BaselineRepairApplicationService._approved_source_fingerprint(baseline)
    (baseline / "src" / "main.ts").write_text("changed\n", encoding="utf-8")
    assert BaselineRepairApplicationService._approved_source_fingerprint(snapshot) != BaselineRepairApplicationService._approved_source_fingerprint(baseline)


def test_legitimate_lifecycle_repair_is_accepted(tmp_path):
    scope, _sessions, engine, _snapshot, sandbox, _artifacts, package_checksum, assessment_fingerprint = _seed(tmp_path)
    try:
        assert PLANNING_FINGERPRINT_PROFILE.fingerprint(sandbox) != assessment_fingerprint
        service = BaselineRepairApplicationService(scope=scope, now_provider=lambda: NOW)
        response = service.apply("run-1", _request(package_checksum))
        assert response.status == "applied"
        assert response.recipe_id == RECIPE_ID
        assert (sandbox / SPEC_PATH).read_text(encoding="utf-8") == SPEC_CONTENT
    finally:
        engine.dispose()


def test_post_g03_source_mutation_fails_closed(tmp_path):
    scope, _sessions, engine, _snapshot, sandbox, _artifacts, package_checksum, _afp = _seed(tmp_path)
    try:
        (sandbox / "src" / "app" / "app.component.ts").write_text("export class AppComponent { hacked }\n", encoding="utf-8")
        service = BaselineRepairApplicationService(scope=scope, now_provider=lambda: NOW)
        with pytest.raises(BaselineRepairApplicationError) as error:
            service.apply("run-1", _request(package_checksum))
        assert error.value.code == "BASELINE_REPAIR_WORKSPACE_STALE"
    finally:
        engine.dispose()


def test_post_g03_generated_file_mutation_fails_closed(tmp_path):
    scope, _sessions, engine, _snapshot, sandbox, _artifacts, package_checksum, _afp = _seed(tmp_path)
    try:
        (sandbox / "dist" / "portal" / "main.js").write_text("tampered", encoding="utf-8")
        service = BaselineRepairApplicationService(scope=scope, now_provider=lambda: NOW)
        with pytest.raises(BaselineRepairApplicationError) as error:
            service.apply("run-1", _request(package_checksum))
        assert error.value.code == "BASELINE_REPAIR_WORKSPACE_STALE"
    finally:
        engine.dispose()


def test_stale_g03_package_fails_closed(tmp_path):
    scope, _sessions, engine, _snapshot, _sandbox, _artifacts, _package_checksum, _afp = _seed(tmp_path)
    try:
        service = BaselineRepairApplicationService(scope=scope, now_provider=lambda: NOW)
        with pytest.raises(BaselineRepairApplicationError) as error:
            service.apply("run-1", _request("sha256:" + "f" * 64))
        assert error.value.code == "BASELINE_REPAIR_PACKAGE_STALE"
    finally:
        engine.dispose()


def test_missing_recipe_authorization_fails_closed(tmp_path):
    scope, _sessions, engine, _snapshot, _sandbox, _artifacts, package_checksum, _afp = _seed(tmp_path, comment="please just make the build pass")
    try:
        service = BaselineRepairApplicationService(scope=scope, now_provider=lambda: NOW)
        with pytest.raises(BaselineRepairApplicationError) as error:
            service.apply("run-1", _request(package_checksum))
        assert error.value.code == "BASELINE_REPAIR_RECIPE_NOT_APPROVED"
    finally:
        engine.dispose()
