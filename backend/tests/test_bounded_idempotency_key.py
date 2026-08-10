"""Regression tests for bounded backend-generated command-policy idempotency keys.

Covers the lockfile-generation liveliness bug where a composed idempotency
key longer than 128 chars escaped the CommandPolicyValidateRequestDto contract
as a raw pydantic.ValidationError and left the continuation RUNNING forever.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.contracts import CommandPolicyValidateRequestDto
from app.repositories.models import (
    Base,
    MigrationPlanModel,
    MigrationRunModel,
    StageExecutionPlanModel,
)
from app.services.stage_execution_application_service import (
    StageExecutionApplicationService,
    StageExecutionError,
    bounded_idempotency_key,
)
from app.services.command_registry_service import CommandPolicyError
from app.services.stage_preparation_application_service import StagePreparationResult

# Current-run IDs are fixture-only; production code is run-agnostic.
STAGE_ID = "repair-angular-20-to-21--8d11392bbcf3cd45-3"
CONTINUATION_ID = "transform-3c95c37557ba"
ATTEMPT_ID = f"repair-{STAGE_ID}-3"
RUN_ID = "run-d3d0222baf58"


def _raw_lockfile_key(
    stage_id=STAGE_ID,
    continuation_id=CONTINUATION_ID,
    attempt_id=ATTEMPT_ID,
):
    return f"{continuation_id}:{stage_id}:command:{attempt_id}:lockfile_generation"


def test_short_key_preserved_unchanged():
    raw = "transform-3c95c37557ba:repair-angular-20-to-21--8d11392bbcf3cd45-3:command:initial:target_version_check"
    assert len(raw) < 128
    assert bounded_idempotency_key(raw) == raw


def test_long_key_bounded():
    raw = _raw_lockfile_key()
    assert len(raw) > 128
    assert len(bounded_idempotency_key(raw)) <= 128


def test_long_key_deterministic():
    raw = _raw_lockfile_key()
    assert bounded_idempotency_key(raw) == bounded_idempotency_key(raw)


def test_long_keys_with_shared_prefix_stay_distinct():
    raw_a = _raw_lockfile_key(attempt_id=ATTEMPT_ID + "x")
    raw_b = _raw_lockfile_key(attempt_id=ATTEMPT_ID + "y")
    assert raw_a[:100] == raw_b[:100]
    assert bounded_idempotency_key(raw_a) != bounded_idempotency_key(raw_b)


def test_current_failure_shape_accepted_by_dto():
    bounded = bounded_idempotency_key(_raw_lockfile_key())
    dto = CommandPolicyValidateRequestDto(
        run_id=RUN_ID,
        expected_state_version=1,
        command_id="npm-lockfile-generate",
        executable="npm",
        idempotency_key=bounded,
    )
    assert dto.idempotency_key == bounded
    assert len(dto.idempotency_key) <= 128


def _service_and_seed(tmp_path: Path, *, timeout_seconds: int, policy_engine=None):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    @contextmanager
    def scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    command_ref = {
        "command_id": "npm-lockfile-generate",
        "template_id": "tpl-npm-lockfile-generate",
        "template_version": 1,
        "executable": "npm",
        "arguments": ["install", "--package-lock-only"],
        "network_profile": "approved-registries-only",
        "timeout_seconds": timeout_seconds,
    }
    with factory() as session:
        session.add(MigrationRunModel(
            id=RUN_ID, status="WAITING_STAGE_PREPARATION", run_phase="STAGED_MIGRATION",
            phase_status="waiting_approval", approval_status="approved", repair_status="not_required",
            state_version=1, actor="operator", run_root=str(tmp_path), artifact_root=str(tmp_path),
            workspace_aliases={}, created_at=now, updated_at=now,
        ))
        session.add(MigrationPlanModel(
            id="plan-1", run_id=RUN_ID, idempotency_key="plan-1", request_checksum="sha256:" + "4" * 64,
            actor="operator", status="approved", version=1, plan={}, checksum="sha256:" + "3" * 64,
            artifact_ids=[], artifact_checksums={}, state_version=1, event_sequence=1,
            created_at=now, updated_at=now,
        ))
        session.add(StageExecutionPlanModel(
            id="stage-plan-1", run_id=RUN_ID, migration_plan_id="plan-1", stage_id=STAGE_ID,
            idempotency_key="stage-plan-1", request_checksum="sha256:" + "5" * 64, actor="operator",
            status="approved", version=1,
            stage_plan={
                "execution_profile_id": "profile-1",
                "commands": {"lockfile_generation": [command_ref]},
            },
            checksum="sha256:" + "6" * 64, artifact_ids=[], artifact_checksums={},
            state_version=1, event_sequence=1, created_at=now, updated_at=now,
        ))
        session.commit()
        run = session.get(MigrationRunModel, RUN_ID)
        plan = session.get(MigrationPlanModel, "plan-1")
        stage = session.get(StageExecutionPlanModel, "stage-plan-1")
    service = StageExecutionApplicationService(scope=scope, policy_engine=policy_engine)
    preparation = StagePreparationResult("STAGE_WORKSPACE_1", str(workspace), "fp", 0, False)
    request = SimpleNamespace(idempotency_key=f"{CONTINUATION_ID}:{STAGE_ID}:command:{ATTEMPT_ID}")
    return service, run, plan, stage, preparation, request


def test_invalid_internal_policy_request_becomes_domain_error(tmp_path: Path):
    service, run, plan, stage, preparation, request = _service_and_seed(
        tmp_path, timeout_seconds=0
    )
    with _session(service) as session:
        with pytest.raises(StageExecutionError) as excinfo:
            service._authorize_and_queue_first_command(
                session, run, plan, stage, preparation, request, "transformer",
                group="lockfile_generation",
            )
    assert excinfo.value.code == "COMMAND_POLICY_REQUEST_INVALID"
    assert "timeout_seconds" in excinfo.value.message


def test_long_key_bounded_before_policy_dto(tmp_path: Path):
    capturing = _CapturingPolicyEngine()
    service, run, plan, stage, preparation, request = _service_and_seed(
        tmp_path, timeout_seconds=300, policy_engine=capturing
    )
    with _session(service) as session:
        with pytest.raises(StageExecutionError):
            service._authorize_and_queue_first_command(
                session, run, plan, stage, preparation, request, "transformer",
                group="lockfile_generation",
            )
    bounded = bounded_idempotency_key(f"{request.idempotency_key}:lockfile_generation")
    assert capturing.captured.idempotency_key == bounded
    assert len(capturing.captured.idempotency_key) <= 128


class _CapturingPolicyEngine:
    def __init__(self):
        self.captured = None

    def validate(self, session, policy_request):
        self.captured = policy_request
        raise StageExecutionError("CAPTURED", "captured before policy decision")


class _RejectingPolicyEngine:
    def validate(self, session, policy_request):
        raise CommandPolicyError(
            "IDEMPOTENCY_KEY_REUSED",
            "The idempotency key is already bound to a different request payload.",
        )


def test_command_policy_error_is_translated_at_stage_execution_boundary(tmp_path: Path):
    service, run, plan, stage, preparation, request = _service_and_seed(
        tmp_path, timeout_seconds=300, policy_engine=_RejectingPolicyEngine()
    )

    with _session(service) as session:
        with pytest.raises(StageExecutionError) as raised:
            service._authorize_and_queue_first_command(
                session,
                run,
                plan,
                stage,
                preparation,
                request,
                "transformer",
                group="lockfile_generation",
            )

    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert raised.value.message == (
        "The idempotency key is already bound to a different request payload."
    )


@contextmanager
def _session(service):
    with service._scope() as session:
        yield session
