"""Legacy fingerprint authority recovery (pre-profile-identity fingerprints).

RED against the base SHA, GREEN after the runtime correction:

Persisted workspace fingerprints that predate fingerprint-profile identity
cannot be compared against the live workspace under the current canonical
profile, so the repair runtime incorrectly blocks with
REPAIR_WORKSPACE_STALE.  The recovery must:

  * identify the supported legacy fingerprint profile deterministically from
    the attempt's historical pre-repair checkpoint;
  * succeed only when the stored legacy hash matches that checkpoint under
    the legacy profile AND the live workspace matches the checkpoint under
    the current canonical profile;
  * CAS-bind the attempt to the checkpoint, migrate the binding to the
    current fingerprint + profile identity, and persist an explicit
    legacy -> current lineage row;
  * fail closed with REPAIR_WORKSPACE_STALE on real drift, unknown or
    ambiguous legacy profiles, and never weaken current-profile checks.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings
from app.domain.contracts import ArtifactType
from app.domain.transformation import FailureRoute
from app.llm_gateway import (
    AzureOpenAILLMGateway,
    PromptRegistry,
    PromptSchemaRegistry,
)
from app.orchestration.transformer_graph import TransformerOrchestrator
from app.repositories.models import (
    ArtifactMetadataModel,
    MigrationRunModel,
    RepairAttemptModel,
    RepairFingerprintRecoveryModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
)
from app.repositories.models.base import Base
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.repair_application_service import (
    RepairApplicationError,
    RepairApplicationService,
    RepairProposalCandidate,
    RepairReviewCandidate,
)
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.stage_execution_application_service import StageExecutionApplicationService
from app.services.transformer_stage_service import TransformerStageService
from app.services.workspace_fingerprint import (
    SOURCE_CONFIG_FINGERPRINT_PROFILE,
    STAGE_FINGERPRINT_PROFILE,
    WORKSPACE_FINGERPRINT_SOURCE_CONFIG_PROFILE_ID,
    WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID,
)

NOW = datetime(2026, 8, 2, tzinfo=UTC)
FINGERPRINT = "sha256:" + "f" * 64

VOLATILE_FILES = {
    "src/app.ts": "old",
    "package.json": '{"name":"fixture"}',
    "angular.json": "{}",
    "node_modules/@angular/core/index.js": "core",
    "dist/main.js": "built",
    ".angular/cache/cache-1": "cache",
}

NO_VOLATILE_FILES = {
    "src/app.ts": "old",
    "package.json": '{"name":"fixture"}',
}


def _database(tmp_path: Path, *, timeout: float | None = None):
    connect_args = {"timeout": timeout} if timeout is not None else {}
    engine = create_engine(
        f"sqlite:///{tmp_path / 'state.db'}", connect_args=connect_args
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _scope(factory):
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

    return scope


def _azure_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        artifact_root=tmp_path / "runs",
        workspace_root=tmp_path / "workspaces",
        snapshot_root=tmp_path / "snapshots",
        delivery_root=tmp_path / "delivery",
        sandbox_root=tmp_path / "sandboxes",
        llm_enabled=True,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_deployment="gpt-5-mini-private",
        azure_openai_api_version="2025-04-01-preview",
        azure_openai_api_key=SecretStr("super-secret-api-key"),
        llm_input_price_per_million_tokens=0.25,
        llm_output_price_per_million_tokens=2.0,
    )


class _FakeAzureTransport:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _responses_body(text: str) -> dict[str, object]:
    message = {
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    }
    reasoning = {"type": "reasoning", "content": [], "summary": []}
    return {
        "status": "completed",
        "output": [reasoning, message],
        "usage": {"input_tokens": 11, "output_tokens": 71, "total_tokens": 82},
    }


def _proposal_candidate(app_ts: Path) -> dict[str, object]:
    return {
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "old_text": "old",
                "new_text": "new",
            }
        ],
        "unified_diff": None,
        "rationale": ["Fix the compiler error."],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }


def _gateway(transport, settings: Settings):
    schema_registry = PromptSchemaRegistry()
    schema_registry.register("repair_proposer_candidate_v2", RepairProposalCandidate)
    schema_registry.register("repair_reviewer_candidate_v2", RepairReviewCandidate)
    return AzureOpenAILLMGateway(
        settings=settings,
        transport=transport,
        registry=schema_registry,
        prompt_registry=PromptRegistry.defaults(),
    )


def _orchestrator(factory, *, repair_service):
    return TransformerOrchestrator(
        scope=_scope(factory),
        stage_service=TransformerStageService(scope=_scope(factory), now_provider=lambda: NOW),
        gate_service=SimpleNamespace(_validate_repair_lineage=lambda *args, **kwargs: None),
        transformation_evidence=MagicMock(),
        prompt_explainer=MagicMock(),
        validation_runner=MagicMock(),
        failure_evidence=MagicMock(),
        repair_service=repair_service,
        patch_service=MagicMock(),
        sealing_flow=MagicMock(),
    )


def _seed_legacy_authority(
    factory,
    tmp_path: Path,
    *,
    files: dict[str, str] | None = None,
    drift: bool = False,
    unknown_legacy_hash: bool = False,
    ambiguous_profile: bool = False,
    legacy_pack: bool = False,
    blocked: bool = False,
):
    """Seed a production-shaped legacy repair authority.

    The workspace and the historical pre-repair checkpoint are byte-identical
    trees (so they match under the current canonical profile), while every
    PERSISTED fingerprint was computed by a legacy scope/profile before
    profile identity existed:

      * binding.workspace_fingerprint: a stale legacy hash that matches no
        profile (the runtime currently blocks on it);
      * checkpoint.workspace_fingerprint / attempt.pre_fingerprint: the
        legacy source-config scope digest of the checkpoint tree.
    """
    files = dict(files or VOLATILE_FILES)
    if ambiguous_profile:
        files = dict(NO_VOLATILE_FILES)
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    checkpoint_dir = tmp_path / "stages" / "ckpt-pre"
    workspace.mkdir(parents=True)
    checkpoint_dir.mkdir(parents=True)
    for relative, content in files.items():
        (workspace / relative).parent.mkdir(parents=True, exist_ok=True)
        (checkpoint_dir / relative).parent.mkdir(parents=True, exist_ok=True)
        (workspace / relative).write_text(content, encoding="utf-8")
        (checkpoint_dir / relative).write_text(content, encoding="utf-8")
    live_fingerprint = STAGE_FINGERPRINT_PROFILE.fingerprint(workspace)
    legacy_fingerprint = SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint(checkpoint_dir)

    app_ts = workspace / "src" / "app.ts"
    evidence = {
        "schema_version": "transformer-failure-evidence-v1",
        "run_id": "run-1",
        "stage_id": "stage-1",
        "stage_plan_checksum": "sha256:stage-plan",
        "workspace_path": str(workspace),
        "workspace_fingerprint": legacy_fingerprint,
        "artifact_root": str(artifacts),
        "execution_id": "execution-1",
        "command_log_artifact_id": None,
        "result_artifact_id": None,
        "normalized_failure": {
            "error_code": "COMPILATION_FAILED",
            "exit_code": 1,
            "failure_message": "Angular compiler reported an error",
        },
        "failure_fingerprint": FINGERPRINT,
        "prior_fingerprints": [],
        "repair_policy": {},
        "forbidden_change_policy": {},
    }
    evidence_service = FailureEvidenceService()
    failure, route_artifact = evidence_service.write(evidence, FailureRoute.REPAIRABLE_SOURCE)
    context = evidence_service.write_context_pack(evidence, failure.ref.checksum)

    session = factory()
    run = MigrationRunModel(
        id="run-1",
        status="STAGE_CREATED",
        run_phase="FEASIBILITY_PLANNING",
        phase_status="completed",
        state_version=7,
        run_root=str(tmp_path),
        artifact_root=str(artifacts),
        workspace_aliases={"STAGE_SANDBOX": str(tmp_path)},
        created_at=NOW,
        updated_at=NOW,
    )
    plan = StageExecutionPlanModel(
        id="stage-plan-1",
        run_id="run-1",
        migration_plan_id="plan-1",
        stage_id="stage-1",
        idempotency_key="plan",
        request_checksum="sha256:plan",
        actor="operator",
        correlation_id="corr-1",
        status="approved",
        version=1,
        stage_plan={"repair_policy": {"max_attempts": 3}, "forbidden_change_policy": {}},
        checksum="sha256:stage-plan",
        artifact_ids=[],
        artifact_checksums={},
        state_version=1,
        event_sequence=1,
        created_at=NOW,
        updated_at=NOW,
    )
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-1",
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(workspace),
        workspace_fingerprint="sha256:" + "a" * 64,
        active=True,
        created_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1",
        run_id="run-1",
        current_stage_id="stage-1",
        thread_id="thread-1",
        status="blocked" if blocked else "running",
        current_node="propose_repair",
        g06_approval_id="g06-1",
        plan_id="plan-1",
        plan_checksum="sha256:plan",
        stage_plan_id="stage-plan-1",
        stage_plan_checksum="sha256:stage-plan",
        worker_id=None if blocked else "worker-1",
        attempt=1,
        max_attempts=3,
        lease_expires_at=None if blocked else NOW + timedelta(seconds=120),
        idempotency_key="continuation",
        request_checksum="sha256:continuation",
        state_version=3,
        last_error_code="REPAIR_WORKSPACE_STALE" if blocked else None,
        last_error_message="Repair workspace fingerprint changed" if blocked else None,
        created_at=NOW,
        updated_at=NOW,
    )
    attempt = RepairAttemptModel(
        id="repair-1",
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=1,
        state_version=1,
        status="evidence_frozen",
        risk_level="unknown",
        diagnosis="repairable_source",
        checkpoint_id=None,
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        failure_route_artifact_id=route_artifact.ref.artifact_id,
        failure_route_checksum=route_artifact.ref.checksum,
        context_pack_artifact_id=context.ref.artifact_id,
        context_pack_checksum=context.ref.checksum,
        proposal_artifact_id=None,
        proposal_checksum=None,
        proposer_invocation_id=None,
        pre_fingerprint=legacy_fingerprint,
        failure_fingerprint=FINGERPRINT,
        created_at=NOW,
        updated_at=NOW,
    )
    checkpoint_fingerprint = (
        "sha256:" + "7" * 64
        if unknown_legacy_hash
        else legacy_fingerprint
    )
    checkpoint = StageCheckpointModel(
        id="ckpt-pre",
        run_id="run-1",
        stage_id="stage-1",
        kind="pre_repair",
        sequence=1,
        workspace_alias="STAGE_WORKSPACE_1",
        workspace_path=str(checkpoint_dir),
        workspace_fingerprint=checkpoint_fingerprint,
        safe_for_resume=True,
        sealed=False,
        state_version=3,
        created_at=NOW,
    )
    session.add_all([run, plan, binding, continuation, attempt, checkpoint])
    for stored in (failure, context):
        session.add(
            ArtifactMetadataModel(
                id="metadata-" + stored.ref.artifact_id,
                run_id="run-1",
                stage_id="stage-1",
                artifact_type=stored.ref.artifact_type.value,
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
                created_at=NOW,
                finalized_at=NOW,
                immutable=True,
            )
        )
    session.commit()
    session.close()

    if drift:
        (workspace / "src" / "app.ts").write_text("mutated", encoding="utf-8")

    if legacy_pack:
        _strip_context_bounds(factory, artifacts, context)

    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    return SimpleNamespace(
        store=store,
        attempt_id=attempt.id,
        app_ts=app_ts,
        artifacts=artifacts,
        workspace=workspace,
        checkpoint_dir=checkpoint_dir,
        live_fingerprint=live_fingerprint,
        legacy_fingerprint=legacy_fingerprint,
        checkpoint_id=checkpoint.id,
        failure=failure,
        context=context,
    )


def _strip_context_bounds(factory, artifacts: Path, context) -> None:
    """Rewrite the context pack as a legacy pre-bounds artifact (bounds missing)."""
    path = artifacts / context.ref.relative_path
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy.pop("bounds")
    legacy_bytes = json.dumps(legacy, sort_keys=True, indent=2).encode("utf-8")
    path.write_bytes(legacy_bytes)
    old_checksum = "sha256:" + hashlib.sha256(legacy_bytes).hexdigest()
    sidecar = path.with_name(path.name + ".meta.json")
    sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
    sidecar_data["content_hash"] = old_checksum
    sidecar_data["checksum"] = old_checksum
    sidecar.write_text(json.dumps(sidecar_data, indent=2), encoding="utf-8")
    session = factory()
    attempt = session.get(RepairAttemptModel, "repair-1")
    context_row = session.get(ArtifactMetadataModel, "metadata-" + context.ref.artifact_id)
    attempt.context_pack_checksum = old_checksum
    context_row.checksum = old_checksum
    session.commit()
    session.close()


def _service(factory, tmp_path: Path, transport=None):
    gateway = None
    if transport is not None:
        gateway = _gateway(transport, _azure_settings(tmp_path))
    return RepairApplicationService(scope=_scope(factory), gateway=gateway)


def test_legacy_authority_recovers_unchanged_workspace(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path)
    service = _service(factory, tmp_path)

    result = service.recover_legacy_fingerprint_authority(seed.attempt_id)

    assert result["recovered"] is True
    session = factory()
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.workspace_fingerprint == seed.live_fingerprint
    assert binding.fingerprint_profile_id == WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID
    assert binding.last_verified_fingerprint == seed.live_fingerprint
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.checkpoint_id == seed.checkpoint_id
    assert attempt.state_version == 2
    assert "authority_recovered_from" in attempt.diagnosis
    lineage = session.query(RepairFingerprintRecoveryModel).all()
    assert len(lineage) == 1
    assert lineage[0].attempt_id == seed.attempt_id
    assert lineage[0].checkpoint_id == seed.checkpoint_id
    assert lineage[0].legacy_profile_id == WORKSPACE_FINGERPRINT_SOURCE_CONFIG_PROFILE_ID
    assert lineage[0].legacy_fingerprint == seed.legacy_fingerprint
    assert lineage[0].current_profile_id == WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID
    assert lineage[0].current_fingerprint == seed.live_fingerprint
    session.close()
    engine.dispose()


def test_legacy_recovery_live_workspace_equals_checkpoint_under_current_profile(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path)
    assert (
        STAGE_FINGERPRINT_PROFILE.fingerprint(seed.workspace)
        == STAGE_FINGERPRINT_PROFILE.fingerprint(seed.checkpoint_dir)
    )
    service = _service(factory, tmp_path)

    service.recover_legacy_fingerprint_authority(seed.attempt_id)

    session = factory()
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.workspace_fingerprint == STAGE_FINGERPRINT_PROFILE.fingerprint(seed.workspace)
    session.close()
    engine.dispose()


def test_legacy_recovery_real_drift_keeps_repair_workspace_stale(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path, drift=True)
    service = _service(factory, tmp_path)

    with pytest.raises(RepairApplicationError) as raised:
        service.recover_legacy_fingerprint_authority(seed.attempt_id)

    assert raised.value.code == "REPAIR_WORKSPACE_STALE"
    session = factory()
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.workspace_fingerprint == "sha256:" + "a" * 64
    assert binding.fingerprint_profile_id is None
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.checkpoint_id is None
    assert session.query(RepairFingerprintRecoveryModel).count() == 0
    session.close()
    engine.dispose()


def test_legacy_recovery_unknown_legacy_profile_fails_closed(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path, unknown_legacy_hash=True)
    service = _service(factory, tmp_path)

    with pytest.raises(RepairApplicationError) as raised:
        service.recover_legacy_fingerprint_authority(seed.attempt_id)

    assert raised.value.code == "REPAIR_WORKSPACE_STALE"
    session = factory()
    assert session.get(StageWorkspaceBindingModel, "binding-1").fingerprint_profile_id is None
    session.close()
    engine.dispose()


def test_legacy_recovery_ambiguous_legacy_profile_fails_closed(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path, ambiguous_profile=True)
    assert (
        SOURCE_CONFIG_FINGERPRINT_PROFILE.fingerprint(seed.checkpoint_dir)
        == STAGE_FINGERPRINT_PROFILE.fingerprint(seed.checkpoint_dir)
    )
    service = _service(factory, tmp_path)

    with pytest.raises(RepairApplicationError) as raised:
        service.recover_legacy_fingerprint_authority(seed.attempt_id)

    assert raised.value.code == "REPAIR_WORKSPACE_STALE"
    session = factory()
    assert session.get(StageWorkspaceBindingModel, "binding-1").fingerprint_profile_id is None
    assert session.get(RepairAttemptModel, seed.attempt_id).checkpoint_id is None
    session.close()
    engine.dispose()


def test_legacy_recovery_cas_binds_repair_attempt_checkpoint(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path)
    service = _service(factory, tmp_path)

    service.recover_legacy_fingerprint_authority(seed.attempt_id)
    session = factory()
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.checkpoint_id == "ckpt-pre"
    assert attempt.state_version == 2
    assert "authority_recovered_from=workspace-fingerprint-v1:source-config" in attempt.diagnosis
    assert attempt.pre_fingerprint == seed.legacy_fingerprint
    session.close()

    service.recover_legacy_fingerprint_authority(seed.attempt_id)
    session = factory()
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.checkpoint_id == "ckpt-pre"
    assert attempt.state_version == 2
    assert session.query(RepairFingerprintRecoveryModel).count() == 1
    session.close()
    engine.dispose()


def test_legacy_recovery_preserves_historical_hashes_and_checkpoints(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path)
    session = factory()
    checkpoint_before = session.get(StageCheckpointModel, "ckpt-pre")
    checkpoint_state = checkpoint_before.state_version
    checkpoint_path = checkpoint_before.workspace_path
    context_checksum = session.get(RepairAttemptModel, seed.attempt_id).context_pack_checksum
    session.close()
    service = _service(factory, tmp_path)

    service.recover_legacy_fingerprint_authority(seed.attempt_id)

    session = factory()
    checkpoint = session.get(StageCheckpointModel, "ckpt-pre")
    assert checkpoint.workspace_fingerprint == seed.legacy_fingerprint
    assert checkpoint.state_version == checkpoint_state
    assert checkpoint.workspace_path == checkpoint_path
    assert checkpoint.kind == "pre_repair"
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.pre_fingerprint == seed.legacy_fingerprint
    assert attempt.failure_evidence_checksum == seed.failure.ref.checksum
    assert attempt.context_pack_checksum == context_checksum
    session.close()
    engine.dispose()


def test_legacy_recovery_persists_recovery_lineage(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path)
    service = _service(factory, tmp_path)

    service.recover_legacy_fingerprint_authority(seed.attempt_id)

    session = factory()
    lineage = session.query(RepairFingerprintRecoveryModel).one()
    assert lineage.run_id == "run-1"
    assert lineage.stage_id == "stage-1"
    assert lineage.attempt_id == seed.attempt_id
    assert lineage.checkpoint_id == "ckpt-pre"
    assert lineage.legacy_profile_id == WORKSPACE_FINGERPRINT_SOURCE_CONFIG_PROFILE_ID
    assert lineage.legacy_fingerprint == seed.legacy_fingerprint
    assert lineage.current_profile_id == WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID
    assert lineage.current_fingerprint == seed.live_fingerprint
    assert lineage.recovered_at is not None
    session.close()
    engine.dispose()


def test_legacy_recovery_is_idempotent(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path)
    service = _service(factory, tmp_path)

    first = service.recover_legacy_fingerprint_authority(seed.attempt_id)
    second = service.recover_legacy_fingerprint_authority(seed.attempt_id)

    assert first["recovered"] is True
    assert second["recovered"] is False
    session = factory()
    assert session.query(RepairFingerprintRecoveryModel).count() == 1
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.fingerprint_profile_id == WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID
    assert binding.workspace_fingerprint == seed.live_fingerprint
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.checkpoint_id == "ckpt-pre"
    assert attempt.state_version == 2
    session.close()
    engine.dispose()


def test_legacy_recovery_concurrent_workers_create_one_result(tmp_path: Path):
    engine, factory = _database(tmp_path, timeout=30)
    seed = _seed_legacy_authority(factory, tmp_path)
    barrier = threading.Barrier(2)
    outcomes: list[dict[str, object]] = []
    errors: list[Exception] = []

    def worker() -> None:
        service = _service(factory, tmp_path)
        barrier.wait()
        try:
            outcomes.append(service.recover_legacy_fingerprint_authority(seed.attempt_id))
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sum(1 for outcome in outcomes if outcome["recovered"]) == 1
    session = factory()
    assert session.query(RepairFingerprintRecoveryModel).count() == 1
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.fingerprint_profile_id == WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID
    assert binding.workspace_fingerprint == seed.live_fingerprint
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.checkpoint_id == "ckpt-pre"
    assert attempt.state_version == 2
    session.close()
    engine.dispose()


def test_bounded_context_created_only_after_authority_recovery(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path, legacy_pack=True)
    session = factory()
    legacy_pack_checksum = session.get(RepairAttemptModel, seed.attempt_id).context_pack_checksum
    session.close()
    transport = _FakeAzureTransport(
        [_responses_body(json.dumps(_proposal_candidate(seed.app_ts)))]
    )
    service = _service(factory, tmp_path, transport=transport)

    service.recover_legacy_fingerprint_authority(seed.attempt_id)
    session = factory()
    replacement_count = session.query(ArtifactMetadataModel).filter(
        ArtifactMetadataModel.relative_path.contains("-context-recovered.json")
    ).count()
    session.close()
    assert replacement_count == 0

    service._recover_legacy_context_pack(seed.attempt_id)
    session = factory()
    replacements = session.query(ArtifactMetadataModel).filter(
        ArtifactMetadataModel.relative_path.contains("-context-recovered.json")
    ).all()
    assert len(replacements) == 1
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.context_pack_artifact_id != seed.context.ref.artifact_id
    session.close()
    replacement = seed.store.read_artifact("run-1", replacements[0].relative_path)
    assert "bounds" in json.loads(replacement.content)
    assert replacement.envelope.input_hashes["recovered_from"] == legacy_pack_checksum
    assert len(transport.calls) == 0
    engine.dispose()


def test_no_proposer_transport_starts_before_recovery_completes(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path)
    transport = _FakeAzureTransport(
        [_responses_body(json.dumps(_proposal_candidate(seed.app_ts)))]
    )
    service = _service(factory, tmp_path, transport=transport)

    service.propose(seed.attempt_id)

    assert len(transport.calls) == 1
    session = factory()
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.fingerprint_profile_id == WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID
    assert binding.workspace_fingerprint == seed.live_fingerprint
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.checkpoint_id == "ckpt-pre"
    assert attempt.proposal_artifact_id is not None
    session.close()
    engine.dispose()


def test_failed_recovery_blocks_transport_with_repair_workspace_stale(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path, drift=True)
    transport = _FakeAzureTransport(
        [_responses_body(json.dumps(_proposal_candidate(seed.app_ts)))]
    )
    service = _service(factory, tmp_path, transport=transport)

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(seed.attempt_id)

    assert raised.value.code == "REPAIR_WORKSPACE_STALE"
    assert transport.calls == []
    session = factory()
    assert session.query(RepairFingerprintRecoveryModel).count() == 0
    assert session.query(ArtifactMetadataModel).filter(
        ArtifactMetadataModel.relative_path.contains("-context-recovered.json")
    ).count() == 0
    session.close()
    engine.dispose()


def test_graph_advance_recovers_legacy_authority_then_queues_review_repair(tmp_path: Path):
    engine, factory = _database(tmp_path)
    seed = _seed_legacy_authority(factory, tmp_path)
    transport = _FakeAzureTransport(
        [_responses_body(json.dumps(_proposal_candidate(seed.app_ts)))]
    )
    service = _service(factory, tmp_path, transport=transport)
    orchestrator = _orchestrator(factory, repair_service=service)

    orchestrator.advance("cont-1", "worker-1")

    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    assert continuation.current_node == "review_repair"
    assert continuation.status == "queued"
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    assert binding.fingerprint_profile_id == WORKSPACE_FINGERPRINT_STAGE_PROFILE_ID
    attempt = session.get(RepairAttemptModel, seed.attempt_id)
    assert attempt.checkpoint_id == "ckpt-pre"
    assert attempt.proposal_artifact_id is not None
    assert len(transport.calls) == 1
    session.close()
    engine.dispose()
