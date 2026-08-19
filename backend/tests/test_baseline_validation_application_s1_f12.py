"""S1-F12 backend target inventory and validation service coverage."""
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.api.baseline_matrix_contracts import BaselineValidationRequest
from app.domain.baseline_matrix import BaselineTargetStatus
from app.repositories.models import Base, BaselineQualificationModel, BaselineValidationModel, MigrationRunModel, WorkflowEventModel
from app.services.baseline_validation_application_service import BaselineValidationApplicationService
NOW = datetime(2026, 7, 16, tzinfo=UTC)
def fixture(tmp_path: Path, scripts=None, angular=None):
    sandbox = tmp_path / "baseline"; sandbox.mkdir()
    (sandbox / "package.json").write_text(json.dumps({"scripts": scripts or {"build": "node --version", "test": "node --version"}}), encoding="utf-8")
    (sandbox / "package-lock.json").write_text('{"lockfileVersion":3}', encoding="utf-8")
    angular = angular or {"version": 1, "projects": {"app": {"projectType": "application"}}}
    (sandbox / "angular.json").write_text(json.dumps(angular), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}"); Base.metadata.create_all(engine); sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as session:
        session.add(MigrationRunModel(id="run-1", run_root=str(tmp_path), status="CREATED", run_phase="BASELINE", phase_status="running", approval_status="approved", repair_status="not_required", state_version=1, artifact_root=str(artifact_root), workspace_aliases={"BASELINE_SANDBOX": str(sandbox)}, created_at=NOW, updated_at=NOW))
        session.add(BaselineQualificationModel(id="baseline-1", run_id="run-1", idempotency_key="baseline", actor="operator", status="qualified", snapshot_id="snapshot-1", sandbox_path=str(sandbox), input_fingerprint="sha256:input", sandbox_fingerprint="sha256:sandbox", package={}, lockfile={}, sources=[], scripts=[], registry={}, blockers=[], warnings=[], authorization_status="authorized", checksum="sha256:baseline", artifact_ids=[], state_version=1, event_sequence=1, created_at=NOW, updated_at=NOW)); session.commit()
    @contextmanager
    def scope():
        with sessions() as session:
            yield session; session.commit()
    return scope, sessions, engine

def test_inventory_and_validation_execute_registered_targets(tmp_path):
    scope, sessions, engine = fixture(tmp_path); service = BaselineValidationApplicationService(scope=scope, now_provider=lambda: NOW)
    inventory = service.get_targets("run-1")
    assert {target["kind"] for target in inventory.targets} == {"build", "test", "lint"}
    result = service.execute("run-1", "build", BaselineValidationRequest(expected_state_version=1, idempotency_key="build-1", actor="operator"))
    assert result.status == "passed"; assert result.results[0]["exit_code"] == 0; assert result.artifact_ids
    with sessions() as session:
        assert session.scalar(select(BaselineValidationModel).where(BaselineValidationModel.run_id == "run-1")) is not None
        assert any(event.event_type == "BASELINE_BUILD_COMPLETED" for event in session.scalars(select(WorkflowEventModel)).all())
    engine.dispose()

def test_missing_lint_is_persisted_as_not_configured(tmp_path):
    scope, sessions, engine = fixture(tmp_path); service = BaselineValidationApplicationService(scope=scope, now_provider=lambda: NOW)
    result = service.execute("run-1", "lint", BaselineValidationRequest(expected_state_version=1, idempotency_key="lint-1", actor="operator"))
    assert result.status == BaselineTargetStatus.SKIPPED_NOT_CONFIGURED.value
    assert result.results[0]["status"] == BaselineTargetStatus.SKIPPED_NOT_CONFIGURED.value
    engine.dispose()


def test_parser_extracts_warnings_counts_and_failed_tests():
    output = "WARNING bundle size\n2 passed, 1 failed\nFAIL should render header"
    assert BaselineValidationApplicationService._warnings(output) == ("WARNING bundle size",)
    assert BaselineValidationApplicationService._test_count(output) == 2
    assert "FAIL should render header" in BaselineValidationApplicationService._failed_tests(output)


def test_parser_prefers_jest_test_count_over_test_suite_count():
    output = "Test Suites: 2 passed, 2 total\nTests:       14 passed, 14 total"

    assert BaselineValidationApplicationService._test_count(output) == 14


def test_parser_karma_success_with_ansi_extracts_count():
    output = (
        "18 08 2026 23:36:24.178:INFO [karma-server]: Karma v5.1.1 server started at http://localhost:9876/\n"
        "Chrome Headless 150.0.0.0 (Windows 10): Executed 0 of 1\x1b[32m SUCCESS\x1b[39m (0 secs / 0 secs)\n"
        "\x1b[1A\x1b[2KChrome Headless 150.0.0.0 (Windows 10): Executed 1 of 1\x1b[32m SUCCESS\x1b[39m (0.009 secs / 0.002 secs)\n"
        "\x1b[32mTOTAL: 1 SUCCESS\x1b[39m\n"
    )

    assert BaselineValidationApplicationService._test_count(output) == 1


def test_parser_karma_zero_tests_returns_zero():
    output = "Chrome Headless 150.0.0.0 (Windows 10): Executed 0 of 0\x1b[32m SUCCESS\x1b[39m (0.004 secs / 0 secs)\n\x1b[32mTOTAL: 0 SUCCESS\x1b[39m\n"

    assert BaselineValidationApplicationService._test_count(output) == 0


def test_parser_karma_failed_extracts_count():
    output = "Chrome Headless 150.0.0.0 (Windows 10): Executed 2 of 2\x1b[31m FAILED\x1b[39m (0.1 secs / 0.1 secs)\n\x1b[31mTOTAL: 2 FAILED\x1b[39m\n"

    assert BaselineValidationApplicationService._test_count(output) == 2


def test_parser_karma_mixed_success_and_failed_sums_all():
    output = "\x1b[32mTOTAL: 1 SUCCESS\x1b[39m, \x1b[31m2 FAILED\x1b[39m\n"

    assert BaselineValidationApplicationService._test_count(output) == 3


def test_parser_karma_executed_fallback_without_total():
    output = "Chrome Headless 150.0.0.0 (Windows 10): Executed 0 of 3\x1b[32m SUCCESS\x1b[39m (0 secs / 0 secs)\n\x1b[1A\x1b[2KChrome Headless 150.0.0.0 (Windows 10): Executed 3 of 3\x1b[32m SUCCESS\x1b[39m (0.123 secs / 0.004 secs)\n"

    assert BaselineValidationApplicationService._test_count(output) == 3


def test_parser_unknown_output_returns_none():
    assert BaselineValidationApplicationService._test_count("some random output\nno tests here") is None


def test_cancel_sets_active_matrix_event():
    import threading
    service = BaselineValidationApplicationService()
    event = threading.Event(); service._ACTIVE[("run-1", "test")] = event
    service.get = lambda *_args: "running"  # type: ignore[method-assign]
    assert service.cancel("run-1", "test") == "running"
    assert event.is_set()
    service._ACTIVE.pop(("run-1", "test"), None)


def test_baseline_matrix_api_exposes_inventory_results_and_stable_errors(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.baseline_matrix_contracts import BaselineTargetInventoryResponse, BaselineValidationResponse
    from app.api.routes.baseline_matrix import get_service
    from app.main import app
    import app.main as main_module
    monkeypatch.setattr(main_module, "check_database_connection", lambda: None)
    import app.api.routes.baseline as baseline_routes
    monkeypatch.setattr(baseline_routes, "get_baseline_install_service", lambda: type("Noop", (), {"reconcile_orphans": lambda self: None})())

    target = {"target_id": "script:build", "kind": "build", "project": None, "configuration": None, "command_id": "script__build", "executable": "npm", "arguments": ["run", "build"], "supported": True, "blocker": None}
    inventory = BaselineTargetInventoryResponse(run_id="run-1", targets=[target], package_json_checksum="sha256:package", angular_json_present=False, state_version=1, event_sequence=1)
    response = BaselineValidationResponse(validation_id="validation-1", run_id="run-1", kind="build", status="passed", targets=[target], results=[], artifact_ids=["artifact-1"], artifact_checksums={"artifact-1": "sha256:artifact"}, baseline_checksum="sha256:baseline", state_version=2, event_sequence=3)

    class Stub:
        def get_targets(self, run_id): return inventory
        def get(self, run_id, kind): return response if kind == "build" else None
        def execute(self, run_id, kind, request): return response
        def cancel(self, run_id, kind): return response

    app.dependency_overrides[get_service] = lambda: Stub()
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/runs/run-1/baseline/targets").status_code == 200
            assert client.get("/api/v1/runs/run-1/baseline/build").json()["artifact_checksums"]["artifact-1"] == "sha256:artifact"
            assert client.post("/api/v1/runs/run-1/baseline/builds", json={"expected_state_version": 1, "idempotency_key": "api-build", "actor": "operator"}).status_code == 200
            assert client.get("/api/v1/runs/run-1/baseline/lint").status_code == 404
    finally:
        app.dependency_overrides.pop(get_service, None)

def test_backend_failure_finalizes_failed_result_and_artifacts(tmp_path, monkeypatch):
    scope, sessions, engine = fixture(tmp_path)
    service = BaselineValidationApplicationService(scope=scope, now_provider=lambda: NOW)

    class FailingWorker:
        def run(self, request, *, cancel_event=None):
            raise RuntimeError("worker unavailable")

    monkeypatch.setattr(service, "_worker", lambda *args, **kwargs: FailingWorker())
    result = service.execute("run-1", "build", BaselineValidationRequest(expected_state_version=1, idempotency_key="build-failure", actor="operator"))
    assert result.status == "failed"
    assert result.results[0]["blocker"] == "EXECUTION_ERROR"
    assert result.artifact_checksums
    with sessions() as session:
        record = session.scalar(select(BaselineValidationModel).where(BaselineValidationModel.id == result.validation_id))
        assert record.status == "failed"
    assert not (tmp_path / "baseline" / "mutated").exists()
    engine.dispose()


def test_build_persists_target_and_generated_output_inventories(tmp_path):
    scope, sessions, engine = fixture(tmp_path)
    service = BaselineValidationApplicationService(scope=scope, now_provider=lambda: NOW)
    result = service.execute("run-1", "build", BaselineValidationRequest(expected_state_version=1, idempotency_key="build-artifacts", actor="operator"))
    from app.artifact_store import LocalFilesystemArtifactStore
    paths = {item.relative_path for item in LocalFilesystemArtifactStore(tmp_path / "artifacts", fixed_run_root=tmp_path / "artifacts").list_artifacts("run-1")}
    assert "01_baseline/baseline_target_inventory.json" in paths
    assert "01_baseline/generated_output_inventory.json" in paths
    with sessions() as session:
        record = session.get(BaselineValidationModel, result.validation_id)
        assert record.artifact_checksums
    engine.dispose()

def test_real_fixture_clean_matrix_runs_real_npm_scripts_and_preserves_source(tmp_path):
    scripts = {"build": "node -e \"console.log('clean build passed')\"", "test": "node -e \"console.log('3 tests passed')\"", "lint": "node -e \"console.log('lint passed')\""}
    scope, sessions, engine = fixture(tmp_path, scripts=scripts)
    source_before = {path.relative_to(tmp_path / "baseline"): path.read_bytes() for path in (tmp_path / "baseline").rglob("*") if path.is_file()}
    service = BaselineValidationApplicationService(scope=scope, now_provider=lambda: NOW)
    state = 1
    for kind in ("build", "test", "lint"):
        result = service.execute("run-1", kind, BaselineValidationRequest(expected_state_version=state, idempotency_key=f"clean-{kind}", actor="operator"))
        assert result.status == "passed"
        assert result.results[0]["exit_code"] == 0
        state = result.state_version
    source_after = {path.relative_to(tmp_path / "baseline"): path.read_bytes() for path in (tmp_path / "baseline").rglob("*") if path.is_file()}
    assert source_after == source_before
    engine.dispose()


def test_real_fixture_failing_test_preserves_failed_test_output(tmp_path):
    scripts = {"test": "node -e \"console.log('FAIL Header renders'); process.exit(1)\""}
    scope, sessions, engine = fixture(tmp_path, scripts=scripts)
    service = BaselineValidationApplicationService(scope=scope, now_provider=lambda: NOW)
    result = service.execute("run-1", "test", BaselineValidationRequest(expected_state_version=1, idempotency_key="fixture-failing-test", actor="operator"))
    assert result.status == "failed"
    assert result.results[0]["failed_tests"]
    assert result.results[0]["artifact_ids"]
    engine.dispose()


def test_real_fixture_unsupported_builder_is_blocked_without_execution(tmp_path):
    angular = {"version": 1, "projects": {"app": {"architect": {"build": {"builder": "vendor:custom", "configurations": {"production": {}}}}}}}
    scope, sessions, engine = fixture(tmp_path, scripts={}, angular=angular)
    service = BaselineValidationApplicationService(scope=scope, now_provider=lambda: NOW)
    result = service.execute("run-1", "build", BaselineValidationRequest(expected_state_version=1, idempotency_key="fixture-unsupported-builder", actor="operator"))
    assert result.status == "blocked"
    assert result.results[0]["status"] == "blocked"
    with sessions() as session:
        assert session.scalar(select(BaselineValidationModel).where(BaselineValidationModel.id == result.validation_id)).status == "blocked"
    engine.dispose()


def test_real_fixture_cancellation_finalizes_and_does_not_mutate_source(tmp_path):
    import threading
    import time
    scripts = {"test": "node -e \"setTimeout(() => console.log('finished'), 10000)\""}
    scope, sessions, engine = fixture(tmp_path, scripts=scripts)
    service = BaselineValidationApplicationService(scope=scope, now_provider=lambda: NOW)
    source_before = (tmp_path / "baseline" / "package.json").read_bytes()
    holder = {}
    thread = threading.Thread(target=lambda: holder.setdefault("result", service.execute("run-1", "test", BaselineValidationRequest(expected_state_version=1, idempotency_key="fixture-cancel", actor="operator"))))
    thread.start()
    for _ in range(100):
        if ("run-1", "test") in service._ACTIVE:
            break
        time.sleep(0.05)
    service.cancel("run-1", "test")
    thread.join(timeout=20)
    assert not thread.is_alive()
    assert holder["result"].status == "failed"
    assert holder["result"].results[0]["status"] == "cancelled"
    assert (tmp_path / "baseline" / "package.json").read_bytes() == source_before
    engine.dispose()
