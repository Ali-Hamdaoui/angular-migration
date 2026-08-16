"""Tests for F27 Secure Execution Evolution.

F27-01: command policy generalized for V2 command classes (fail-closed on
ungoverned classes).
F27-02: least-privilege execution environment (no ambient env leak).
F27-03: immutable, hash-chained execution audit trail.
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.command_execution.worker import WorkerSupervisor
from app.domain.command import CommandClass, command_class_for
from app.domain.execution_audit import ExecutionAuditEvent
from app.main import app
from app.repositories.execution_audit_models import CommandExecutionAuditModel
from app.repositories.models import MigrationRunModel
from app.repositories.session import session_scope
from app.services.execution_audit_service import ExecutionAuditError, ExecutionAuditTrailService

NOW = datetime.now(UTC)
client = TestClient(app)


def _seed_run(run_id: str) -> None:
    with session_scope() as session:
        session.add(MigrationRunModel(id=run_id, status="CREATED", run_phase="initialized",
                                      source_version_family="angular-11.x", target_version_family="angular-14.x",
                                      created_at=NOW, updated_at=NOW))
        session.commit()


# ---------- F27-01: generalized command class governance ----------

def test_every_v2_command_id_has_governed_class():
    from app.domain.command import (
        ANGULAR_UPDATE_V2_RENDERER,
        ANGULAR_UPDATE_V3_RENDERER,
        DEFAULT_COMMAND_TEMPLATES,
        NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER,
        NPM_DEPENDENCY_INSTALL_RENDERER,
        NPM_DEPENDENCY_UNINSTALL_RENDERER,
    )
    ids = {t.command_id for t in DEFAULT_COMMAND_TEMPLATES}
    ids.update({
        ANGULAR_UPDATE_V2_RENDERER.command_id,
        ANGULAR_UPDATE_V3_RENDERER.command_id,
        NPM_DEPENDENCY_INSTALL_RENDERER.command_id,
        NPM_DEPENDENCY_UNINSTALL_RENDERER.command_id,
        NPM_ANGULAR_LOCKFILE_NORMALIZE_RENDERER.command_id,
    })
    for command_id in ids:
        assert command_class_for(command_id) is not CommandClass.UNGOVERNED, command_id


def test_unknown_command_is_ungoverned():
    assert command_class_for("rm-rf-home") is CommandClass.UNGOVERNED
    assert command_class_for("") is CommandClass.UNGOVERNED
    assert command_class_for(None) is CommandClass.UNGOVERNED


def test_governance_check_in_policy_engine_fails_closed():
    from sqlalchemy import select

    from app.repositories.models import CommandTemplateModel
    from app.services.command_registry_service import CommandPolicyEngineService

    run_id = f"run-f27-{uuid4().hex[:8]}"
    _seed_run(run_id)
    engine = CommandPolicyEngineService()
    with session_scope() as session:
        engine.registry.seed_defaults(session)
        request = _policy_request(run_id, command_id="totally-unknown-command", executable="npx", arguments=["evil"])
        result = engine.validate(session, request)
        assert result.decision == "rejected"
        assert any("COMMAND_CLASS_UNGOVERNED" in r for r in result.reasons)


def _policy_request(run_id: str, **overrides):
    from app.domain.contracts import CommandPolicyValidateRequestDto

    values = {
        "run_id": run_id, "expected_state_version": 1, "command_id": "python-version", "template_id": "tpl-python-version",
        "template_version": 1, "executable": "python", "arguments": ["--version"], "cwd_alias": "run_workspace",
        "working_directory_alias": "run_workspace", "working_directory": "/tmp", "network_profile": "none",
        "cancellation_policy": "terminate_process_tree", "timeout_seconds": 300,
        "idempotency_key": f"auth-{uuid4().hex[:8]}", "requested_by": "test",
    }
    values.update(overrides)
    return CommandPolicyValidateRequestDto(**values)


# ---------- F27-02: least-privilege execution ----------

def test_empty_allowlist_forwards_no_ambient_env():
    ambient = WorkerSupervisor._build_safe_environment(())
    assert ambient == {"PATH": os.environ["PATH"]} or ("PATH" in ambient and len(ambient) == 1)


def test_empty_allowlist_blocks_secrets_even_if_requested():
    os.environ["F27_TEST_SECRET_TOKEN"] = "super-secret"
    try:
        environment = WorkerSupervisor._build_safe_environment(("F27_TEST_SECRET_TOKEN",))
        assert "F27_TEST_SECRET_TOKEN" not in environment
    finally:
        os.environ.pop("F27_TEST_SECRET_TOKEN", None)


def test_explicit_allowlist_grants_exactly_listed_vars():
    os.environ["F27_NODE_OPTIONS_TEST"] = "--max-old-space-size=512"
    try:
        environment = WorkerSupervisor._build_safe_environment(("PATH", "F27_NODE_OPTIONS_TEST"))
        assert set(environment) == {"PATH", "F27_NODE_OPTIONS_TEST"}
    finally:
        os.environ.pop("F27_NODE_OPTIONS_TEST", None)


def test_overrides_are_applied_even_with_empty_allowlist():
    environment = WorkerSupervisor._build_safe_environment((), overrides={"CUSTOM_OVERRIDE": "x"})
    assert environment.get("CUSTOM_OVERRIDE") == "x"
    assert "CUSTOM_OVERRIDE" not in {k for k in os.environ}


# ---------- F27-03: immutable audit trail ----------

def test_audit_chain_binds_and_verifies():
    run_id = f"run-f27-{uuid4().hex[:8]}"
    _seed_run(run_id)
    service = ExecutionAuditTrailService()
    first = service.append(run_id=run_id, event=ExecutionAuditEvent.EXECUTION_QUEUED,
                           command_id="python-version", execution_id="exec-1", actor="tester",
                           executable="python", arguments=["--version"], reason="queued")
    assert first.prev_checksum == ExecutionAuditTrailService.GENESIS
    second = service.append(run_id=run_id, event=ExecutionAuditEvent.EXECUTION_SUCCEEDED,
                            command_id="python-version", execution_id="exec-1", actor="tester",
                            executable="python", arguments=["--version"], reason="done")
    assert second.prev_checksum == first.checksum
    verification = service.verify_trail(run_id)
    assert verification["intact"] is True
    assert verification["entries"] == 2
    assert verification["verified"] == 2


def test_audit_trail_detects_tampering():
    run_id = f"run-f27-{uuid4().hex[:8]}"
    _seed_run(run_id)
    service = ExecutionAuditTrailService()
    service.append(run_id=run_id, event=ExecutionAuditEvent.EXECUTION_QUEUED, command_id="python-version")
    with session_scope() as session:
        row = session.query(CommandExecutionAuditModel).filter_by(run_id=run_id).first()
        row.reason = "tampered"
        session.commit()
    verification = service.verify_trail(run_id)
    assert verification["intact"] is False
    assert verification["first_broken_entry"] == row.id


def test_audit_append_unknown_run_raises():
    service = ExecutionAuditTrailService()
    try:
        service.append(run_id="run-missing", event=ExecutionAuditEvent.EXECUTION_QUEUED, command_id="python-version")
        assert False, "expected RUN_NOT_FOUND"
    except ExecutionAuditError as exc:
        assert exc.code == "RUN_NOT_FOUND"


def test_audit_api_list_and_verify():
    run_id = f"run-f27-{uuid4().hex[:8]}"
    _seed_run(run_id)
    service = ExecutionAuditTrailService()
    service.append(run_id=run_id, event=ExecutionAuditEvent.AUTHORIZATION_ACCEPTED,
                   command_id="python-version", executable="python", arguments=["--version"], reason="accepted")

    listed = client.get(f"/runs/{run_id}/execution-audit-trail")
    assert listed.status_code == 200
    assert len(listed.json()["entries"]) == 1
    assert listed.json()["entries"][0]["command_class"] == "version_verify"
    assert listed.json()["entries"][0]["event"] == "authorization_accepted"

    verified = client.get(f"/runs/{run_id}/execution-audit-trail/verify")
    assert verified.status_code == 200
    assert verified.json()["intact"] is True
    assert verified.json()["verified"] == 1


def test_audit_api_unknown_run_404():
    response = client.get("/runs/run-missing/execution-audit-trail")
    assert response.status_code == 404
    assert response.json()["error_code"] == "RUN_NOT_FOUND"


def test_policy_rejection_writes_audit_entry():
    from app.services.command_registry_service import CommandPolicyEngineService

    run_id = f"run-f27-{uuid4().hex[:8]}"
    _seed_run(run_id)
    engine = CommandPolicyEngineService()
    with session_scope() as session:
        engine.registry.seed_defaults(session)
        result = engine.validate(session, _policy_request(run_id, command_id="totally-unknown-command"))
        assert result.decision == "rejected"
        session.commit()
    with session_scope() as session:
        entry = session.query(CommandExecutionAuditModel).filter_by(run_id=run_id).first()
        assert entry is not None
        assert entry.event == "authorization_rejected"
        assert entry.command_class == "ungoverned"
