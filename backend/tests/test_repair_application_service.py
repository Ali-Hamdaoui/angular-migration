import hashlib
import json
import shutil
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.artifact_store import LocalFilesystemArtifactStore
from app.core.config import Settings
from app.domain.contracts import AgentKind, ArtifactType, CommandStatus, WorkflowEventType
from app.llm_gateway import (
    AzureGatewayError,
    AzureOpenAILLMGateway,
    LlmFailureCode,
    LlmRequest,
    LlmRole,
    LlmTaskType,
    PromptRegistry,
    PromptSchemaRegistry,
)
from app.llm_gateway.azure_gateway import ProviderTransportResult
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    LlmInvocationModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageWorkspaceBindingModel,
    TransformationContinuationModel,
    WorkflowEventModel,
)
from app.repositories.models.base import Base
from app.services import repair_application_service
from app.services.causal_review import causal_rejection
from app.services.dependency_closure_service import (
    validate_dependency_transition_evidence,
    verify_dependency_transition_state,
    verify_npm_eresolve_attempted_resolution_state,
)
from app.services.failure_evidence_service import FailureEvidenceService
from app.services.repair_application_service import (
    RepairApplicationError,
    RepairApplicationService,
    RepairLlmError,
    RepairProposal,
    RepairProposalCandidate,
    RepairReview,
    RepairReviewCandidate,
    replace_text_once,
    _translate_gateway_failure,
)
from app.services.stage_preparation_primitives import StageSandboxCopier

NOW = datetime(2026, 7, 31, tzinfo=UTC)


def test_proposer_policy_prioritizes_authoritative_existing_files():
    policy = repair_application_service._PROPOSER_SYSTEM_POLICY

    assert "human revision" in policy.lower()
    assert "never use create_text_file for any path listed in current_workspace_files" in policy.lower()
    assert "use replace_text with the exact authoritative preimage" in policy.lower()
    assert "short exact unique substring" in policy.lower()


def test_create_target_retry_feedback_identifies_rejected_path():
    feedback = repair_application_service._semantic_retry_feedback(
        "REPAIR_CREATE_TARGET_EXISTS",
        "create_text_file cannot target existing authoritative path 'jest.config.ts'; use replace_text with its exact preimage.",
    )

    assert "jest.config.ts" in feedback
    assert "replace_text" in feedback


def _proposal(path: Path):
    checksum = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "preimage_sha256": checksum,
                "old_text": "old",
                "new_text": "new",
            }
        ],
        "unified_diff": None,
        "touched_files": ["src/app.ts"],
        "rationale": ["Fix the compiler error."],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }


def _proposal_candidate():
    return {
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app.ts",
                "old_text": "old",
                "new_text": "new",
                "content": None,
            }
        ],
        "unified_diff": None,
        "rationale": ["Fix the compiler error."],
        "risk_level": "low",
        "validation_targets": ["build"],
        "limitations": [],
    }


def _create_candidate(path="src/app.ts", content="new"):
    candidate = _proposal_candidate()
    candidate["operations"][0].update(
        {
            "operation": "create_text_file",
            "path": path,
            "old_text": None,
            "new_text": content,
            "content": content,
        }
    )
    return candidate


def _dependency_transition_candidate(*operations):
    return {
        "proposal_format": "operations",
        "operations": list(operations),
        "unified_diff": None,
        "rationale": ["Perform the governed dependency transition."],
        "risk_level": "medium",
        "validation_targets": ["build", "test"],
        "limitations": [],
    }


def _dependency_transition_operation():
    return {"operation": "dependency_transition", "path": "package.json"}


def _dependency_change_candidate(*, section: str, package: str = "fixture-package", new_version: str = "2.0.0"):
    return {
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "dependency_change",
                "path": "package.json",
                "section": section,
                "package": package,
                "new_version": new_version,
                "old_text": None,
                "new_text": None,
                "content": None,
            }
        ],
        "unified_diff": None,
        "rationale": ["Update the declared dependency version."],
        "risk_level": "low",
        "validation_targets": ["test"],
        "limitations": [],
    }


def _dependency_transition_context(tmp_path: Path):
    from app.services.dependency_closure_service import _COMPATIBLE_REINSTALL_BUNDLES

    (package, target_major), authority = next(iter(_COMPATIBLE_REINSTALL_BUNDLES.items()))
    target_version = next(version for name, version, _ in authority if name == package)
    peer_package = "fixture-peer-dependency"
    package_json = {
        "name": "fixture",
        "devDependencies": {package: "^1.2.3"},
    }
    package_lock = {
        "name": "fixture",
        "lockfileVersion": 3,
        "packages": {
            "": {"devDependencies": {package: "^1.2.3"}},
            f"node_modules/{package}": {
                "version": "1.2.3",
                "peerDependencies": {peer_package: ">=1.0.0 <3.0.0"},
            },
        },
    }
    package_metadata = {
        "name": package,
        "version": "1.2.3",
        "peerDependencies": {peer_package: ">=1.0.0 <3.0.0"},
    }
    (tmp_path / "package.json").write_text(json.dumps(package_json), encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(json.dumps(package_lock), encoding="utf-8")
    package_path = tmp_path / "node_modules" / package
    package_path.mkdir(parents=True)
    (package_path / "package.json").write_text(json.dumps(package_metadata), encoding="utf-8")
    evidence = {
        "normalized_failure": {
            "command_id": "angular-update-exact",
            "exit_code": 1,
            "failure_diagnosis": {
                "kind": "peer_dependency_conflict",
                "package": package,
                "installed_version": "14.1.0",
                "required_ranges": {peer_package: ">=1.0.0 <3.0.0"},
                "proposed_angular_version": f"{target_major}.0.0",
            },
        }
    }
    return {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "failure_evidence_artifact_id": "artifact-failure",
        "checkpoint_id": "checkpoint-1",
        "target_exact": f"{target_major}.0.0",
        "expected_target_version": target_version,
        "segments": [json.dumps(evidence)],
    }


def _npm_attempt_workspace(
    tmp_path: Path,
    *,
    package: str = "fixture-package",
    blocking_dependency: str = "fixture-peer",
    package_intent: str = "^2.0.0",
    attempted_version: str = "2.4.0",
    installed_version: str = "1.4.0",
    required_peer_range: str = ">=2.0.0 <3.0.0",
    installed_peer_range: str = ">=1.0.0 <2.0.0",
    include_package: bool = True,
    include_blocking_dependency: bool = True,
):
    dev_dependencies = {}
    if include_package:
        dev_dependencies[package] = package_intent
    if include_blocking_dependency:
        dev_dependencies[blocking_dependency] = "^1.0.0"
    package_json = {"name": "fixture", "devDependencies": dev_dependencies}
    package_lock = {
        "name": "fixture",
        "lockfileVersion": 3,
        "packages": {
            "": {"devDependencies": dev_dependencies},
            f"node_modules/{package}": {
                "version": installed_version,
                "peerDependencies": {blocking_dependency: installed_peer_range},
            },
        },
    }
    (tmp_path / "package.json").write_text(json.dumps(package_json), encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(json.dumps(package_lock), encoding="utf-8")
    package_path = tmp_path / "node_modules" / package
    package_path.mkdir(parents=True)
    (package_path / "package.json").write_text(
        json.dumps(
            {
                "name": package,
                "version": installed_version,
                "peerDependencies": {blocking_dependency: installed_peer_range},
            }
        ),
        encoding="utf-8",
    )
    return {
        "source": "npm_eresolve_peer_conflict",
        "kind": "peer_dependency_conflict",
        "package": package,
        "package_version": attempted_version,
        "blocking_dependency": blocking_dependency,
        "required_peer_range": required_peer_range,
        "required_ranges": {blocking_dependency: required_peer_range},
    }


def _review_candidate():
    return {
        "decision": "accept",
        "findings": [],
        "policy_checks": ["paths"],
        "risk_assessment": "low",
        "required_validation_targets": ["build"],
        "limitations": [],
    }


def _lockfile_generation_commands():
    return {
        "lockfile_generation": [
            {
                "command_id": "npm-lockfile-generate",
                "template_id": "tpl-npm-lockfile-generate",
                "template_version": 1,
                "parameter_bindings": {},
                "executable": "npm",
                "arguments": [
                    "install",
                    "--package-lock-only",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                ],
                "shell": False,
                "working_directory_alias": "STAGE_WORKSPACE_1",
                "timeout_seconds": 3600,
                "network_profile": "approved-registries-only",
                "runtime_profile_checksum": "sha256:" + "4" * 64,
                "cancellation_policy": "terminate_process_tree",
                "conditional": False,
            }
        ]
    }


def test_proposal_semantics_bind_preimage_and_safe_path(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")
    service = RepairApplicationService(scope=None)
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    assert service.validate_proposal(_proposal(target), context)["risk_level"] == "low"
    escaped = _proposal(target)
    escaped["operations"][0]["path"] = "../outside.ts"
    escaped["touched_files"] = ["../outside.ts"]
    with pytest.raises(RepairApplicationError, match="outside policy"):
        service.validate_proposal(escaped, context)


def test_dependency_change_requires_exact_stage_plan_authority(tmp_path: Path):
    package = tmp_path / "package.json"
    package.write_text('{"dependencies":{"x":"1.0.0"}}', encoding="utf-8")
    proposal = _proposal(package)
    proposal["operations"][0].update(
        {
            "operation": "dependency_change",
            "path": "package.json",
            "old_text": '"x":"1.0.0"',
            "new_text": '"x":"2.0.0"',
        }
    )
    proposal["touched_files"] = ["package.json"]
    context = {
        "workspace_path": str(tmp_path),
        "workspace_binding_alias": "STAGE_WORKSPACE_1",
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "stage_plan_commands": {},
    }
    service = RepairApplicationService(scope=None)

    with pytest.raises(RepairApplicationError) as error:
        service.validate_proposal(proposal, context)
    assert error.value.code == "STAGE_PLAN_COMMAND_AUTHORITY_MISSING"

    context["stage_plan_commands"] = _lockfile_generation_commands()
    assert service.validate_proposal(proposal, context)["operations"][0]["operation"] == (
        "dependency_change"
    )


def test_dependency_section_mismatch_is_specific_in_both_binding_paths(tmp_path: Path):
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps({"devDependencies": {"fixture-package": "1.0.0"}}, indent=2) + "\n",
        encoding="utf-8",
    )
    operation = {
        "operation": "dependency_change",
        "path": "package.json",
        "section": "dependencies",
        "package": "fixture-package",
        "new_version": "2.0.0",
    }
    service = RepairApplicationService(scope=None)

    with pytest.raises(RepairApplicationError) as normalized:
        service._normalize_dependency_operation(operation, package)
    with pytest.raises(RepairApplicationError) as coalesced:
        service._bind_proposal_candidate(
            _dependency_change_candidate(section="dependencies"),
            {
                "workspace_path": str(tmp_path),
                "workspace_binding_alias": "STAGE_WORKSPACE_1",
                "failure_evidence_checksum": "sha256:failure",
                "context_pack_checksum": "sha256:context",
                "stage_plan_commands": _lockfile_generation_commands(),
            },
        )

    for raised in (normalized, coalesced):
        assert raised.value.code == "REPAIR_DEPENDENCY_SECTION_MISMATCH"
        assert "fixture-package" in raised.value.message
        assert "devDependencies" in raised.value.message
        assert "dependencies" in raised.value.message
        assert "1.0.0" in raised.value.message


def test_dependency_multi_section_ambiguity_remains_non_retryable(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"fixture-package": "1.0.0"},
                "devDependencies": {"fixture-package": "1.0.0"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RepairApplicationError) as raised:
        RepairApplicationService(scope=None)._bind_proposal_candidate(
            _dependency_change_candidate(section="dependencies"),
            {
                "workspace_path": str(tmp_path),
                "workspace_binding_alias": "STAGE_WORKSPACE_1",
                "failure_evidence_checksum": "sha256:failure",
                "context_pack_checksum": "sha256:context",
                "stage_plan_commands": _lockfile_generation_commands(),
            },
        )

    assert raised.value.code == "REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS"
    assert "REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS" not in repair_application_service._SEMANTIC_RETRY_CODES


def test_dependency_missing_behavior_remains_unchanged(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"dependencies": {}}', encoding="utf-8")

    with pytest.raises(RepairApplicationError) as raised:
        RepairApplicationService(scope=None)._bind_proposal_candidate(
            _dependency_change_candidate(section="dependencies"),
            {
                "workspace_path": str(tmp_path),
                "workspace_binding_alias": "STAGE_WORKSPACE_1",
                "failure_evidence_checksum": "sha256:failure",
                "context_pack_checksum": "sha256:context",
                "stage_plan_commands": _lockfile_generation_commands(),
            },
        )

    assert raised.value.code == "REPAIR_DEPENDENCY_PACKAGE_MISSING"


def test_dependency_section_mismatch_retry_feedback_and_lineage_are_bounded(tmp_path: Path):
    engine, factory = _database(tmp_path)
    package_json = json.dumps(
        {"name": "fixture", "devDependencies": {"fixture-package": "1.0.0"}},
        indent=2,
    ) + "\n"
    store, attempt_id, _app_ts, _artifacts = _seed_service(
        factory, tmp_path, package_json=package_json
    )
    session = factory()
    plan = session.get(StageExecutionPlanModel, "stage-plan-stage-1")
    plan.stage_plan = {
        "repair_policy": {"max_attempts": 3},
        "commands": _lockfile_generation_commands(),
    }
    session.commit()
    session.close()
    invalid = _dependency_change_candidate(section="dependencies")
    transport = _RecordingTransport(
        [_responses_body(json.dumps(invalid)), _responses_body(json.dumps(invalid))]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as first:
        service.propose(attempt_id)
    assert first.value.code == "REPAIR_DEPENDENCY_SECTION_MISMATCH"
    assert "REPAIR_DEPENDENCY_SECTION_MISMATCH" in repair_application_service._SEMANTIC_RETRY_CODES
    assert "REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS" not in repair_application_service._SEMANTIC_RETRY_CODES
    assert len(transport.calls) == 2

    retry_request = json.loads(transport.calls[1]["payload"]["input"][0]["content"][0]["text"])
    retry_text = "\n".join(
        segment["content"]
        for segment in retry_request["context"]
        if isinstance(segment, dict) and isinstance(segment.get("content"), str)
    )
    for phrase in (
        "The requested dependency exists exactly once in authoritative package.json",
        "Authoritative package: fixture-package",
        "Authoritative section: devDependencies",
        "Authoritative version: 1.0.0",
        "requested section 'dependencies'",
        "Do not move the dependency between package.json sections",
        "Regenerate the repair from the original immutable failure and repository evidence",
        "If dependency_change remains appropriate",
        "Do not fabricate package state, lockfile state, or node_modules state",
    ):
        assert phrase in retry_text

    session = factory()
    base = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
    retry = session.get(LlmInvocationModel, f"{attempt_id}:proposer:semantic-retry-1")
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert base is not None and retry is not None
    assert retry.retries == 1
    assert attempt.proposal_artifact_id is None
    assert attempt.review_artifact_id is None
    assert attempt.g10_gate_package_id is None
    assert base.artifact_ids
    assert retry.artifact_ids
    rejected = next(
        store.read_artifact_by_id(artifact_id)
        for artifact_id in base.artifact_ids
        if store.read_artifact_by_id(artifact_id).ref.relative_path.endswith(
            "rejected-proposer-candidate.json"
        )
    )
    rejected_payload = json.loads(rejected.content)
    assert rejected_payload["semantic_failure_code"] == "REPAIR_DEPENDENCY_SECTION_MISMATCH"
    assert rejected_payload["context_checksum"] == attempt.context_pack_checksum
    assert rejected.ref.artifact_id in base.artifact_checksums
    assert base.artifact_checksums[rejected.ref.artifact_id] == rejected.ref.checksum
    session.close()

    with pytest.raises(RepairApplicationError) as exhausted:
        service.propose(attempt_id)
    assert exhausted.value.code == "REPAIR_SEMANTIC_RETRY_EXHAUSTED"
    assert len(transport.calls) == 2
    engine.dispose()


def test_corrected_dependency_section_binds_and_same_version_is_noop(tmp_path: Path):
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps({"devDependencies": {"fixture-package": "1.0.0"}}, indent=2) + "\n",
        encoding="utf-8",
    )
    context = {
        "workspace_path": str(tmp_path),
        "workspace_binding_alias": "STAGE_WORKSPACE_1",
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "stage_plan_commands": _lockfile_generation_commands(),
    }
    service = RepairApplicationService(scope=None)

    bound = service._bind_proposal_candidate(
        _dependency_change_candidate(section="devDependencies", new_version="2.0.0"),
        context,
    )
    assert bound["operations"][0]["section"] == "devDependencies"
    assert bound["operations"][0]["new_version"] == "2.0.0"

    with pytest.raises(RepairApplicationError) as no_op:
        service._bind_proposal_candidate(
            _dependency_change_candidate(section="devDependencies", new_version="1.0.0"),
            context,
        )
    assert no_op.value.code == "REPAIR_REPLACEMENT_NOOP"


def test_restart_reclassifies_persisted_section_mismatch_into_one_retry(tmp_path: Path):
    engine, factory = _database(tmp_path)
    package_json = json.dumps(
        {"name": "fixture", "devDependencies": {"fixture-package": "1.0.0"}},
        indent=2,
    ) + "\n"
    store, attempt_id, _app_ts, _artifacts = _seed_service(
        factory, tmp_path, package_json=package_json
    )
    session = factory()
    plan = session.get(StageExecutionPlanModel, "stage-plan-stage-1")
    plan.stage_plan = {
        "repair_policy": {"max_attempts": 3},
        "commands": _lockfile_generation_commands(),
    }
    session.commit()
    session.close()

    service = RepairApplicationService(scope=_scope(factory))
    context = service._attempt_context(attempt_id)
    candidate = _dependency_change_candidate(section="dependencies")
    rejected_payload = {
        "attempt_id": attempt_id,
        "candidate": candidate,
        "prompt_version": "prompt-repair-proposer-candidate-v5",
        "schema_version": "schema-registry-v1",
        "candidate_checksum": service._request_checksum(candidate),
        "context_checksum": context["context_pack_checksum"],
        "semantic_failure_code": "REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS",
        "semantic_failure_message": "The requested package has ambiguous dependency entries",
        "provider_request_id": "historical-request",
    }
    rejected = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/rejected-proposer-candidate.json",
        json.dumps(rejected_payload),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-proposer",
        created_at=NOW,
    )
    session = factory()
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + rejected.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=rejected.ref.artifact_type.value,
            relative_path=rejected.ref.relative_path,
            checksum=rejected.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:proposer",
            run_id="run-1",
            stage_id="stage-1",
            idempotency_key=f"{attempt_id}:proposer",
            request_checksum="sha256:historical-request",
            input_hashes=["sha256:failure", context["context_pack_checksum"]],
            correlation_id=f"{attempt_id}:proposer",
            actor="transformer",
            role="repair_proposer",
            task_type="repair_diagnosis",
            provider="azure_openai",
            deployment_alias="azure-openai",
            prompt_version="prompt-repair-proposer-candidate-v5",
            schema_version="schema-registry-v1",
            pricing_version="mvp-pricing-2026-01",
            stage="repair",
            redacted_summary=None,
            status="failed",
            failure_code="REPAIR_DEPENDENCY_PACKAGE_AMBIGUOUS",
            artifact_ids=[rejected.ref.artifact_id],
            artifact_checksums={rejected.ref.artifact_id: rejected.ref.checksum},
            state_version=2,
            event_sequence=0,
            retries=0,
            failure_stage="repair_semantics",
            response_received=True,
            transport_started=True,
            started_at=NOW,
            completed_at=NOW,
            created_at=NOW,
        )
    )
    session.commit()
    session.close()

    transport = _RecordingTransport(
        [_responses_body(json.dumps(candidate)), _responses_body(json.dumps(candidate))]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_DEPENDENCY_SECTION_MISMATCH"
    assert len(transport.calls) == 1
    retry_text = "\n".join(
        segment["content"]
        for segment in json.loads(transport.calls[0]["payload"]["input"][0]["content"][0]["text"])["context"]
        if isinstance(segment, dict) and isinstance(segment.get("content"), str)
    )
    assert "Authoritative package: fixture-package" in retry_text
    assert "Authoritative section: devDependencies" in retry_text
    assert "Authoritative version: 1.0.0" in retry_text

    session = factory()
    retry = session.get(LlmInvocationModel, f"{attempt_id}:proposer:semantic-retry-1")
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert retry is not None
    assert retry.retries == 1
    assert attempt.proposal_artifact_id is None
    assert attempt.review_artifact_id is None
    assert attempt.g10_gate_package_id is None
    session.close()
    engine.dispose()


def test_unified_diff_cannot_modify_package_json(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    candidate = _proposal_candidate()
    candidate.update(
        {
            "proposal_format": "unified_diff",
            "operations": [],
            "unified_diff": (
                "--- a/package.json\n+++ b/package.json\n@@ -1 +1 @@\n"
                "-{\"name\":\"fixture\"}\n+{\"name\":\"updated\"}\n"
            ),
        }
    )
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    with pytest.raises(RepairApplicationError) as error:
        RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)
    assert error.value.code == "REPAIR_DEPENDENCY_OPERATION_REQUIRED"


def test_reviewer_candidate_schema_cannot_author_candidate_content():
    with pytest.raises(ValidationError):
        repair_application_service.RepairReviewCandidate.model_validate(
            {
                "decision": "accept",
                "findings": [],
                "policy_checks": ["paths"],
                "risk_assessment": "low",
                "required_validation_targets": ["build"],
                "limitations": [],
                "operations": [{"operation": "replace_text"}],
            }
        )


def test_reviewer_candidate_schema_rejects_unified_diff_field():
    with pytest.raises(ValidationError):
        repair_application_service.RepairReviewCandidate.model_validate(
            {
                "decision": "accept",
                "findings": [],
                "policy_checks": ["paths"],
                "risk_assessment": "low",
                "required_validation_targets": ["build"],
                "limitations": [],
                "unified_diff": "--- a/src/app.ts\n+++ b/src/app.ts\n",
            }
        )


@pytest.mark.parametrize(
    "failure, expected_code, expected_retryable",
    [
        (
            AzureGatewayError(LlmFailureCode.AUTHORIZATION, "Prompt policy is not registered for this task."),
            "LLM_PROMPT_POLICY_MISSING",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.SCHEMA, "Response schema is not registered."),
            "LLM_SCHEMA_POLICY_MISSING",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.CONFIGURATION, "Azure OpenAI gateway is not fully configured."),
            "LLM_CONFIGURATION_INVALID",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.INVALID_REQUEST, "Azure OpenAI request failed.", provider_status=400),
            "LLM_PROVIDER_BAD_REQUEST",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.AUTHENTICATION, "Azure OpenAI request failed.", provider_status=401),
            "LLM_PROVIDER_AUTH",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.AUTHORIZATION, "Azure OpenAI request failed.", provider_status=403),
            "LLM_PROVIDER_AUTH",
            False,
        ),
        (
            AzureGatewayError(LlmFailureCode.TIMEOUT, "Azure OpenAI request failed.", provider_status=408),
            "LLM_PROVIDER_TIMEOUT",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.RATE_LIMIT, "Azure OpenAI request failed.", provider_status=429),
            "LLM_PROVIDER_RATE_LIMIT",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.SERVER, "Azure OpenAI request failed.", provider_status=500),
            "LLM_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.SERVER, "Azure OpenAI request failed.", provider_status=502),
            "LLM_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.SERVER, "Azure OpenAI request failed.", provider_status=503),
            "LLM_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.SERVER, "Azure OpenAI request failed.", provider_status=504),
            "LLM_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.TIMEOUT, "Azure OpenAI request timed out."),
            "LLM_PROVIDER_TIMEOUT",
            True,
        ),
        (
            AzureGatewayError(LlmFailureCode.TRANSPORT, "Azure OpenAI network request failed.", retryable=True),
            "LLM_TRANSPORT_FAILED",
            True,
        ),
    ],
)
def test_gateway_failure_translation_table(failure, expected_code, expected_retryable):
    translated = _translate_gateway_failure(failure)

    assert isinstance(translated, RepairLlmError)
    assert isinstance(translated, RepairApplicationError)
    assert translated.code == expected_code
    assert translated.retryable is expected_retryable
    assert translated.message == str(failure)
    assert translated.__cause__ is failure
    assert translated.provider_status == failure.provider_status
    assert translated.provider_request_id == failure.provider_request_id
    assert translated.failure_stage == failure.failure_stage
    assert translated.failure_subtype == failure.failure_subtype


def test_gateway_failure_translation_carries_provider_fields():
    failure = AzureGatewayError(
        LlmFailureCode.SERVER,
        "Azure OpenAI request failed.",
        retryable=True,
        provider_status=503,
        provider_request_id="azure-request-9",
        failure_stage="http_response",
        failure_subtype="HTTP_ERROR_ENVELOPE",
    )

    translated = _translate_gateway_failure(failure)

    assert translated.code == "LLM_PROVIDER_UNAVAILABLE"
    assert translated.retryable is True
    assert translated.provider_status == 503
    assert translated.provider_request_id == "azure-request-9"
    assert translated.failure_stage == "http_response"
    assert translated.failure_subtype == "HTTP_ERROR_ENVELOPE"


def test_proposal_rejects_stale_preimage_duplicate_paths_and_mixed_formats(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")
    service = RepairApplicationService(scope=None)
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    stale = _proposal(target)
    stale["operations"][0]["preimage_sha256"] = "sha256:stale"
    with pytest.raises(RepairApplicationError, match="preimage"):
        service.validate_proposal(stale, context)

    duplicate = _proposal(target)
    duplicate["touched_files"] = ["src/app.ts", "src/app.ts"]
    with pytest.raises(RepairApplicationError, match="unique"):
        service.validate_proposal(duplicate, context)

    mixed = _proposal(target)
    mixed["unified_diff"] = "--- a/src/app.ts\n+++ b/src/app.ts\n"
    with pytest.raises(RepairApplicationError, match="only operations"):
        service.validate_proposal(mixed, context)


def test_mixed_dependency_transition_gets_specific_contract_error(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    candidate = _dependency_transition_candidate(
        _dependency_transition_operation(),
        {"operation": "replace_text", "path": "package.json", "old_text": "", "new_text": ""},
    )
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    with pytest.raises(RepairApplicationError) as raised:
        RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)

    assert raised.value.code == "REPAIR_DEPENDENCY_TRANSITION_NOT_EXCLUSIVE"
    assert raised.value.code != "REPAIR_OPERATION_AMBIGUOUS"


def test_dependency_transition_retry_feedback_requires_exclusive_operation(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    invalid = _dependency_transition_candidate(
        _dependency_transition_operation(),
        {"operation": "replace_text", "path": "package.json", "old_text": "", "new_text": ""},
    )
    valid = _proposal_candidate()
    transport = _RecordingTransport(
        [_responses_body(json.dumps(invalid)), _responses_body(json.dumps(valid))]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    proposal = service.propose(attempt_id)

    assert proposal["operations"][0]["operation"] == "replace_text"
    assert "REPAIR_DEPENDENCY_TRANSITION_NOT_EXCLUSIVE" in repair_application_service._SEMANTIC_RETRY_CODES
    retry_request = json.loads(transport.calls[1]["payload"]["input"][0]["content"][0]["text"])
    retry_text = "\n".join(
        segment["content"]
        for segment in retry_request["context"]
        if isinstance(segment, dict) and isinstance(segment.get("content"), str)
    )
    for phrase in (
        "dependency_transition is exclusive",
        "exactly one operation",
        'operation=\"dependency_transition\"',
        'path=\"package.json\"',
        "Do not emit replace_text",
        "Do not emit dependency_add or dependency_change",
        "Do not emit a package.json unified_diff",
        "backend binds authoritative transition targets",
        "same immutable failure/context evidence",
    ):
        assert phrase in retry_text
    engine.dispose()


def test_corrected_dependency_transition_retry_binds(tmp_path: Path):
    context = _dependency_transition_context(tmp_path)
    bound = RepairApplicationService(scope=None)._bind_proposal_candidate(
        _dependency_transition_candidate(_dependency_transition_operation()), context
    )

    assert bound["operations"][0]["operation"] == "dependency_transition"
    assert bound["operations"][0]["path"] == "package.json"
    assert bound["operations"][0]["checkpoint_id"] == "checkpoint-1"
    assert bound["operations"][0]["target_state"]["target_version"] == context["expected_target_version"]


def test_npm_eresolve_attempted_resolution_allows_candidate_different_from_installed(
    tmp_path: Path,
):
    diagnosis = _npm_attempt_workspace(tmp_path)

    verify_npm_eresolve_attempted_resolution_state(
        tmp_path,
        diagnosis=diagnosis,
    )


def test_installed_state_verification_still_requires_exact_peer_ranges(tmp_path: Path):
    diagnosis = _npm_attempt_workspace(tmp_path)

    verify_dependency_transition_state(
        tmp_path,
        package="fixture-package",
        installed_version="1.4.0",
        peer_ranges={"fixture-peer": ">=1.0.0 <2.0.0"},
    )
    with pytest.raises(ValueError, match="peer ranges do not match"):
        verify_dependency_transition_state(
            tmp_path,
            package=diagnosis["package"],
            installed_version="1.4.0",
            peer_ranges=diagnosis["required_ranges"],
        )


def test_npm_eresolve_missing_package_version_fails_closed(tmp_path: Path):
    diagnosis = _npm_attempt_workspace(tmp_path)
    diagnosis.pop("package_version")

    with pytest.raises(ValueError, match="attempted package version"):
        verify_npm_eresolve_attempted_resolution_state(
            tmp_path,
            diagnosis=diagnosis,
        )


@pytest.mark.parametrize("missing_field", ["blocking_dependency", "required_peer_range", "required_ranges"])
def test_npm_eresolve_missing_blocking_fact_fails_closed(tmp_path: Path, missing_field: str):
    diagnosis = _npm_attempt_workspace(tmp_path)
    diagnosis.pop(missing_field)

    with pytest.raises(ValueError, match="attempted-resolution evidence"):
        verify_npm_eresolve_attempted_resolution_state(
            tmp_path,
            diagnosis=diagnosis,
        )


def test_npm_eresolve_missing_package_intent_fails_closed(tmp_path: Path):
    diagnosis = _npm_attempt_workspace(tmp_path, include_package=False)

    with pytest.raises(ValueError, match="causal package intent"):
        verify_npm_eresolve_attempted_resolution_state(
            tmp_path,
            diagnosis=diagnosis,
        )


def test_current_npm_eresolve_evidence_binds_facts_without_installed_peer_error(tmp_path: Path):
    diagnosis = _npm_attempt_workspace(
        tmp_path,
        package="jest-preset-angular",
        blocking_dependency="@angular-devkit/build-angular",
        package_intent="^13.0.0",
        attempted_version="13.1.6",
        installed_version="16.1.3",
        required_peer_range=">=13.0.0 <18.0.0",
        installed_peer_range=">=16.0.0 <22.0.0",
    )
    evidence = {
        "execution_id": "execution-eresolve",
        "normalized_failure": {
            "command_id": "npm-lockfile-generate",
            "exit_code": 1,
            "failure_diagnosis": diagnosis,
        },
    }
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "failure_evidence_artifact_id": "artifact-failure",
        "checkpoint_id": "checkpoint-1",
        "target_exact": "21.0.0",
        "segments": [json.dumps(evidence)],
    }

    bound = RepairApplicationService(scope=None)._bind_proposal_candidate(
        _dependency_transition_candidate(_dependency_transition_operation()), context
    )

    blocking = bound["operations"][0]["blocking_dependency"]
    assert blocking["package"] == "jest-preset-angular"
    assert blocking["installed_version"] == "16.1.3"
    assert blocking["required_peer_ranges"] == [
        {
            "package": "@angular-devkit/build-angular",
            "version_range": ">=13.0.0 <18.0.0",
        }
    ]


def test_existing_create_target_has_specific_fail_closed_error(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8", newline="")
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    with pytest.raises(RepairApplicationError) as raised:
        RepairApplicationService(scope=None)._bind_proposal_candidate(
            _create_candidate(), context
        )

    assert raised.value.code == "REPAIR_CREATE_TARGET_EXISTS"
    assert "create_text_file" in raised.value.message
    assert "existing" in raised.value.message
    assert "src/app.ts" in raised.value.message


def test_existing_create_target_is_the_only_new_semantic_retry_code():
    assert "REPAIR_CREATE_TARGET_EXISTS" in repair_application_service._SEMANTIC_RETRY_CODES
    assert "REPAIR_OPERATION_AMBIGUOUS" not in repair_application_service._SEMANTIC_RETRY_CODES


def test_duplicate_create_operations_remain_ambiguous_and_non_retryable(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    candidate = _create_candidate()
    candidate["operations"].append(
        {
            "operation": "create_text_file",
            "path": "src/app.ts",
            "old_text": None,
            "new_text": "other",
            "content": "other",
        }
    )
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    with pytest.raises(RepairApplicationError) as raised:
        RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)

    assert raised.value.code == "REPAIR_OPERATION_AMBIGUOUS"
    assert "REPAIR_OPERATION_AMBIGUOUS" not in repair_application_service._SEMANTIC_RETRY_CODES


def test_create_operation_without_text_content_remains_fail_closed(tmp_path: Path):
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }
    candidate = _create_candidate()
    candidate["operations"][0]["content"] = None

    with pytest.raises(RepairApplicationError) as raised:
        RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)

    assert raised.value.code == "REPAIR_OPERATION_AMBIGUOUS"
    assert "REPAIR_OPERATION_AMBIGUOUS" not in repair_application_service._SEMANTIC_RETRY_CODES


def test_create_operation_without_text_content_gets_one_governed_retry(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    invalid = _create_candidate(path="src/new-setup.ts", content=None)
    corrected = _proposal_candidate()
    transport = _RecordingTransport(
        [_responses_body(json.dumps(invalid)), _responses_body(json.dumps(corrected))]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    proposal = service.propose(attempt_id)

    assert proposal["operations"][0]["operation"] == "replace_text"
    assert len(transport.calls) == 2
    engine.dispose()


def test_create_target_retry_hydrates_exact_authoritative_file_and_binds_replace(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    initial = _create_candidate()
    corrected = _proposal_candidate()
    transport = _RecordingTransport(
        [_responses_body(json.dumps(initial)), _responses_body(json.dumps(corrected))]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    session = factory()
    context_artifact_id = session.get(RepairAttemptModel, attempt_id).context_pack_artifact_id
    session.close()
    original_context = store.read_artifact_by_id(context_artifact_id)
    expected_fingerprint = StageSandboxCopier.fingerprint(tmp_path / "workspace")

    proposal = service.propose(attempt_id)

    assert len(transport.calls) == 2
    assert proposal["operations"][0]["operation"] == "replace_text"
    assert proposal["operations"][0]["old_text"] == "old"
    retry_request = json.loads(transport.calls[1]["payload"]["input"][0]["content"][0]["text"])
    retry_text = "\n".join(
        segment["content"]
        for segment in retry_request["context"]
        if isinstance(segment, dict) and isinstance(segment.get("content"), str)
    )
    assert "target already exists" in retry_text
    assert "use replace_text" in retry_text
    assert "exact authoritative preimage" in retry_text
    hydrated = next(
        json.loads(segment["content"])
        for segment in retry_request["context"]
        if isinstance(segment, dict)
        and isinstance(segment.get("content"), str)
        and segment["content"].startswith(
            '{"schema_version": "repair-semantic-retry-context-v1"'
        )
    )
    assert hydrated == {
        "schema_version": "repair-semantic-retry-context-v1",
        "targets": [
            {
                "bom": False,
                "content": "old",
                "final_newline": False,
                "path": "src/app.ts",
                "sha256": "sha256:" + hashlib.sha256(b"old").hexdigest(),
                "size_bytes": 3,
            }
        ],
        "workspace_fingerprint": expected_fingerprint,
    }
    current_context = store.read_artifact_by_id(context_artifact_id)
    assert current_context.ref.checksum == original_context.ref.checksum
    assert current_context.content == original_context.content

    session = factory()
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
    rejected = next(
        store.read_artifact_by_id(artifact_id)
        for artifact_id in invocation.artifact_ids
        if store.read_artifact_by_id(artifact_id).ref.relative_path.endswith(
            "rejected-proposer-candidate.json"
        )
    )
    session.close()
    rejected_payload = json.loads(rejected.content)
    assert rejected_payload["semantic_failure_code"] == "REPAIR_CREATE_TARGET_EXISTS"
    assert rejected_payload["semantic_retry_context"] == hydrated
    recovered_retry = service._load_semantic_retry_context(service._attempt_context(attempt_id))
    assert recovered_retry["error_code"] == "REPAIR_CREATE_TARGET_EXISTS"
    engine.dispose()


def test_semantic_retry_ignores_valid_missing_create_target(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    workspace = tmp_path / "workspace"
    candidate = _proposal_candidate()
    candidate["operations"].extend(
        [{"operation": "create_text_file", "path": "src/new-setup.ts", "content": "setup"}]
    )
    service = RepairApplicationService(scope=_scope(factory))

    context = service._attempt_context(attempt_id)
    hydrated = service._hydrate_semantic_retry_context(candidate, context)

    assert hydrated is not None
    assert [target["path"] for target in hydrated["payload"]["targets"]] == ["src/app.ts"]
    assert not (workspace / "src" / "new-setup.ts").exists()
    engine.dispose()


def test_create_target_retry_is_bounded_to_one(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    invalid = _create_candidate()
    transport = _RecordingTransport(
        [_responses_body(json.dumps(invalid)), _responses_body(json.dumps(invalid))]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as first:
        service.propose(attempt_id)
    assert first.value.code == "REPAIR_CREATE_TARGET_EXISTS"
    assert len(transport.calls) == 2

    with pytest.raises(RepairApplicationError) as exhausted:
        service.propose(attempt_id)
    assert exhausted.value.code == "REPAIR_SEMANTIC_RETRY_EXHAUSTED"
    assert len(transport.calls) == 2
    engine.dispose()


@pytest.mark.parametrize("target_kind", ["unsafe", "directory", "symlink"])
def test_non_recoverable_create_targets_fail_closed(tmp_path: Path, target_kind: str):
    engine, factory = _database(tmp_path)
    _store, attempt_id, app_ts, _artifacts = _seed_service(factory, tmp_path)
    workspace = tmp_path / "workspace"
    if target_kind == "unsafe":
        path = "../outside.ts"
    elif target_kind == "directory":
        target = workspace / "src" / "existing-dir"
        target.mkdir()
        path = "src/existing-dir"
        _refresh_seed_authority(factory, tmp_path)
    else:
        target = workspace / "src" / "existing-link.ts"
        try:
            target.symlink_to(app_ts)
        except OSError:
            engine.dispose()
            pytest.skip("symlink creation is unavailable in this environment")
        path = "src/existing-link.ts"
        _refresh_seed_authority(factory, tmp_path)

    service = RepairApplicationService(scope=_scope(factory))
    context = service._attempt_context(attempt_id)
    with pytest.raises(RepairApplicationError) as raised:
        service._hydrate_semantic_retry_context(_create_candidate(path), context)

    assert raised.value.code in {
        "REPAIR_REPLACEMENT_CONTEXT_INVALID",
        "REPAIR_WORKSPACE_MISSING",
        "REPAIR_WORKSPACE_STALE",
    }
    engine.dispose()


def test_generic_operation_ambiguity_remains_non_retryable(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    candidate = _proposal_candidate()
    candidate["operations"][0]["path"] = "package.json"
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    with pytest.raises(RepairApplicationError) as raised:
        RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)

    assert raised.value.code == "REPAIR_OPERATION_AMBIGUOUS"
    assert "REPAIR_OPERATION_AMBIGUOUS" not in repair_application_service._SEMANTIC_RETRY_CODES


def test_proposal_rejects_lockfiles_and_binary_targets(tmp_path: Path):
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{}", encoding="utf-8")
    binary = tmp_path / "src" / "image.bin"
    binary.parent.mkdir()
    binary.write_bytes(b"\xff\xfe")
    service = RepairApplicationService(scope=None)
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    lock_proposal = _proposal(lockfile)
    lock_proposal["operations"][0]["path"] = "package-lock.json"
    lock_proposal["touched_files"] = ["package-lock.json"]
    with pytest.raises(RepairApplicationError, match="outside policy"):
        service.validate_proposal(lock_proposal, context)

    binary_proposal = _proposal(binary)
    binary_proposal["operations"][0]["path"] = "src/image.bin"
    binary_proposal["operations"][0]["preimage_sha256"] = (
        "sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    binary_proposal["touched_files"] = ["src/image.bin"]
    with pytest.raises(RepairApplicationError, match="UTF-8"):
        service.validate_proposal(binary_proposal, context)


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'service.db'}")
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


class _RecordingTransport:
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


def _gateway(transport, settings: Settings):
    schema_registry = PromptSchemaRegistry(version=settings.llm_schema_registry_version)
    schema_registry.register("repair_proposer_v1", RepairProposal)
    schema_registry.register("repair_reviewer_v1", RepairReview)
    schema_registry.register("repair_proposer_candidate_v2", RepairProposalCandidate)
    schema_registry.register("repair_reviewer_candidate_v2", RepairReviewCandidate)
    return AzureOpenAILLMGateway(
        settings=settings,
        transport=transport,
        registry=schema_registry,
        prompt_registry=PromptRegistry.defaults(),
    )


def _seed_service(
    factory,
    tmp_path: Path,
    *,
    human_revision: dict | None = None,
    package_json: str = '{"name": "fixture"}',
):
    artifacts = tmp_path / "artifacts"
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    app_ts = workspace / "src" / "app.ts"
    app_ts.write_text("old", encoding="utf-8")
    (workspace / "package.json").write_text(package_json, encoding="utf-8")
    (workspace / "angular.json").write_text('{"project": "fixture"}', encoding="utf-8")
    (workspace / "tsconfig.json").write_text('{"compilerOptions": {}}', encoding="utf-8")
    store = LocalFilesystemArtifactStore(artifacts.parent, fixed_run_root=artifacts)
    attempt_id = "repair-1"
    failure = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/failure-evidence.json",
        json.dumps({"attempt_id": attempt_id, "failure": "compiler", "stage_id": "stage-1"}),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-failure-evidence",
        created_at=NOW,
    )
    evidence = {
        "schema_version": "transformer-failure-evidence-v1",
        "run_id": "run-1",
        "stage_id": "stage-1",
        "stage_plan_checksum": "sha256:stage-plan",
        "workspace_path": str(workspace),
        "workspace_fingerprint": StageSandboxCopier.fingerprint(workspace),
        "artifact_root": str(artifacts),
        "execution_id": "execution-1",
        "command_log_artifact_id": None,
        "result_artifact_id": None,
        "normalized_failure": {
            "error_code": "COMPILATION_FAILED",
            "exit_code": 1,
            "failure_message": "Angular compiler reported an error",
        },
        "failure_fingerprint": "fingerprint-failure",
        "prior_fingerprints": [],
        "repair_policy": {},
        "forbidden_change_policy": {},
    }
    context_kwargs = {}
    if human_revision is not None:
        context_kwargs["human_revision"] = human_revision
    context = FailureEvidenceService().write_context_pack(
        evidence, failure.ref.checksum, **context_kwargs
    )
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
    binding = StageWorkspaceBindingModel(
        id="binding-1",
        run_id="run-1",
        stage_id="stage-1",
        alias="STAGE_WORKSPACE_1",
        workspace_path=str(workspace),
        workspace_fingerprint=StageSandboxCopier.fingerprint(workspace),
        fingerprint_profile_id=repair_application_service.STAGE_FINGERPRINT_PROFILE.profile_id,
        active=True,
        created_at=NOW,
    )
    plan = StageExecutionPlanModel(
        id="stage-plan-stage-1", run_id="run-1", migration_plan_id="plan-1", stage_id="stage-1",
        idempotency_key="plan", request_checksum="sha256:plan", actor="operator",
        correlation_id="corr-1", status="approved", version=1,
        stage_plan={"repair_policy": {"max_attempts": 3}}, checksum="sha256:stage-plan",
        artifact_ids=[], artifact_checksums={}, state_version=1, event_sequence=1,
        created_at=NOW, updated_at=NOW,
    )
    continuation = TransformationContinuationModel(
        id="cont-1", run_id="run-1", current_stage_id="stage-1", thread_id="thread-1",
        status="running", current_node="propose_repair", g06_approval_id="g06-1",
        plan_id="plan-1", plan_checksum="sha256:plan", stage_plan_id=plan.id,
        stage_plan_checksum=plan.checksum, worker_id="worker-1", attempt=1, max_attempts=3,
        lease_expires_at=NOW, idempotency_key="continuation", request_checksum="sha256:continuation",
        state_version=3, created_at=NOW, updated_at=NOW,
    )
    attempt = RepairAttemptModel(
        id=attempt_id,
        run_id="run-1",
        stage_id="stage-1",
        attempt_number=1,
        status="evidence_frozen",
        risk_level="unknown",
        diagnosis="repairable_source; checkpoint=ckpt-pre",
        checkpoint_id="ckpt-pre",
        failure_evidence_artifact_id=failure.ref.artifact_id,
        failure_evidence_checksum=failure.ref.checksum,
        failure_route_artifact_id="artifact-route",
        failure_route_checksum="sha256:route",
        context_pack_artifact_id=context.ref.artifact_id,
        context_pack_checksum=context.ref.checksum,
        proposal_artifact_id=None,
        proposal_checksum=None,
        proposer_invocation_id=None,
        pre_fingerprint=context.ref.checksum,
        failure_fingerprint="fingerprint-failure",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add_all([run, plan, binding, continuation, attempt])
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + failure.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=failure.ref.artifact_type.value,
            relative_path=failure.ref.relative_path,
            checksum=failure.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + context.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=context.ref.artifact_type.value,
            relative_path=context.ref.relative_path,
            checksum=context.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.commit()
    session.close()
    return store, attempt_id, app_ts, artifacts


def _seed_failed_v1_invocation(factory, attempt_id: str):
    session = factory()
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:proposer",
            run_id="run-1",
            stage_id="stage-1",
            idempotency_key=f"{attempt_id}:proposer",
            request_checksum="sha256:legacy-request",
            input_hashes=["sha256:legacy-failure", "schema:legacy-v1"],
            correlation_id=f"{attempt_id}:proposer",
            actor="transformer",
            role="repair_proposer",
            task_type="repair_diagnosis",
            provider="azure_openai",
            deployment_alias="azure-openai",
            prompt_version="prompt-repair-proposer-v1",
            schema_version="schema-registry-v1",
            pricing_version="mvp-pricing-2026-01",
            stage="repair",
            redacted_summary=None,
            status="failed",
            failure_code="LLM_PROVIDER_BAD_REQUEST",
            artifact_ids=[],
            artifact_checksums={},
            state_version=1,
            event_sequence=0,
            retries=0,
            started_at=NOW,
            completed_at=NOW,
            created_at=NOW,
        )
    )
    session.commit()
    session.close()


def _seed_exhausted_semantic_retry(
    factory,
    tmp_path: Path,
    *,
    human_revision: dict | None = None,
    retry_failure_code: str = "REPAIR_REPLACEMENT_MISSING",
):
    store, attempt_id, app_ts, artifacts = _seed_service(
        factory, tmp_path, human_revision=human_revision
    )
    session = factory()
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    attempt = session.get(RepairAttemptModel, attempt_id)
    continuation = session.get(TransformationContinuationModel, "cont-1")
    attempt.pre_fingerprint = binding.workspace_fingerprint
    checkpoint = StageCheckpointModel(
        id="ckpt-pre",
        run_id="run-1",
        stage_id="stage-1",
        kind="pre_repair",
        sequence=1,
        workspace_alias=binding.alias,
        workspace_path=binding.workspace_path,
        workspace_fingerprint=binding.workspace_fingerprint,
        safe_for_resume=True,
        sealed=False,
        state_version=1,
        created_at=NOW,
    )
    attempt.checkpoint_id = checkpoint.id
    continuation.status = "blocked"
    continuation.current_node = "propose_repair"
    continuation.last_error_code = "REPAIR_SEMANTIC_RETRY_EXHAUSTED"
    continuation.last_error_message = "Repair semantic correction retry has already failed"
    continuation.worker_id = None
    continuation.lease_expires_at = None

    for retry_number, suffix in enumerate(("", ":semantic-retry-1")):
        invocation_id = f"{attempt_id}:proposer{suffix}"
        session.add(
            LlmInvocationModel(
                id=invocation_id,
                run_id="run-1",
                stage_id="stage-1",
                idempotency_key=invocation_id,
                request_checksum=f"sha256:request-{retry_number}",
                input_hashes=["sha256:failure", "sha256:context"],
                correlation_id=invocation_id,
                actor="transformer",
                role="repair_proposer",
                task_type="repair_diagnosis",
                provider="azure_openai",
                deployment_alias="azure-openai",
                prompt_version="prompt-repair-proposer-candidate-v2",
                schema_version="schema-registry-v1",
                pricing_version="mvp-pricing-2026-01",
                stage="repair",
                redacted_summary=None,
                status="failed",
                failure_code=(
                    retry_failure_code if retry_number else "REPAIR_REPLACEMENT_MISSING"
                ),
                artifact_ids=[],
                artifact_checksums={},
                state_version=1,
                event_sequence=0,
                retries=retry_number,
                failure_stage="repair_semantics",
                started_at=NOW,
                completed_at=NOW,
                created_at=NOW,
            )
        )
    session.add(checkpoint)
    session.commit()
    session.close()
    return store, attempt_id, app_ts, artifacts


def _refresh_seed_authority(factory, tmp_path: Path):
    fingerprint = StageSandboxCopier.fingerprint(tmp_path / "workspace")
    session = factory()
    session.get(StageWorkspaceBindingModel, "binding-1").workspace_fingerprint = fingerprint
    session.get(RepairAttemptModel, "repair-1").pre_fingerprint = fingerprint
    session.commit()
    session.close()
    return fingerprint


def _recovery_service(factory):
    return RepairApplicationService(scope=_scope(factory), now_provider=lambda: NOW)


def test_recover_exhausted_semantic_retry_creates_one_lineage_bound_child(tmp_path: Path):
    engine, factory = _database(tmp_path)
    store, attempt_id, _app_ts, _artifacts = _seed_exhausted_semantic_retry(factory, tmp_path)
    session = factory()
    parent_before = session.get(RepairAttemptModel, attempt_id)
    old_context = store.read_artifact_by_id(parent_before.context_pack_artifact_id)
    old_context_checksum = parent_before.context_pack_checksum
    session.close()

    result = _recovery_service(factory).recover_exhausted_semantic_retry(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="semantic-recovery-1",
        actor="operator",
    )

    assert result == {
        "attempt_id": "repair-stage-1-2",
        "status": "evidence_frozen",
        "idempotent_replay": False,
    }
    session = factory()
    parent = session.get(RepairAttemptModel, attempt_id)
    child = session.get(RepairAttemptModel, "repair-stage-1-2")
    continuation = session.get(TransformationContinuationModel, "cont-1")
    child_metadata = session.get(
        ArtifactMetadataModel, "metadata-" + child.context_pack_artifact_id
    )
    assert parent.status == "superseded"
    assert parent.completed_at == NOW.replace(tzinfo=None)
    assert child.parent_attempt_id == attempt_id
    assert child.run_id == parent.run_id == "run-1"
    assert child.stage_id == parent.stage_id == "stage-1"
    assert child.attempt_number == parent.attempt_number + 1
    assert child.failure_evidence_artifact_id == parent.failure_evidence_artifact_id
    assert child.failure_evidence_checksum == parent.failure_evidence_checksum
    assert child.failure_route_artifact_id == parent.failure_route_artifact_id
    assert child.failure_route_checksum == parent.failure_route_checksum
    assert child.checkpoint_id == parent.checkpoint_id == "ckpt-pre"
    assert child.pre_fingerprint == parent.pre_fingerprint
    assert child.context_pack_artifact_id != old_context.ref.artifact_id
    new_context = store.read_artifact_by_id(child.context_pack_artifact_id)
    assert new_context.envelope.input_hashes["recovered_from"] == old_context_checksum
    assert child_metadata.immutable is True
    assert continuation.status == "queued"
    assert continuation.current_node == "propose_repair"
    assert continuation.last_error_code is None
    assert continuation.last_error_message is None
    assert continuation.worker_id is None
    assert continuation.lease_expires_at is None
    assert continuation.state_version == 4
    assert continuation.wake_sequence == 1
    session.close()

    old_context_after = store.read_artifact_by_id(old_context.ref.artifact_id)
    assert old_context_after.ref.checksum == old_context.ref.checksum
    assert old_context_after.content == old_context.content
    engine.dispose()


def test_recovery_accepts_legacy_ambiguous_semantic_retry_failure(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_exhausted_semantic_retry(
        factory,
        tmp_path,
        retry_failure_code="REPAIR_OPERATION_AMBIGUOUS",
    )

    result = _recovery_service(factory).recover_exhausted_semantic_retry(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="semantic-recovery-legacy-ambiguous",
        actor="operator",
    )

    assert result["attempt_id"] == "repair-stage-1-2"
    assert result["status"] == "evidence_frozen"
    engine.dispose()


def test_recovery_accepts_exhausted_protocol_retry_failure(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_exhausted_semantic_retry(
        factory,
        tmp_path,
        retry_failure_code="LLM_PROTOCOL_FAILED",
    )
    session = factory()
    retry = session.get(
        LlmInvocationModel,
        f"{attempt_id}:proposer:semantic-retry-1",
    )
    retry.retries = 3
    retry.failure_stage = "response_state_validation"
    session.commit()
    session.close()

    result = _recovery_service(factory).recover_exhausted_semantic_retry(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="semantic-recovery-protocol-failure",
        actor="operator",
    )

    assert result["attempt_id"] == "repair-stage-1-2"
    assert result["status"] == "evidence_frozen"
    engine.dispose()


def test_recovery_child_context_preserves_existing_human_revision(tmp_path: Path):
    engine, factory = _database(tmp_path)
    human_revision = {
        "instruction": "Keep the existing test bootstrap migration intent.",
        "parent_attempt_id": "repair-0",
        "parent_proposal_id": "artifact-parent-proposal",
        "parent_proposal_checksum": "sha256:parent-proposal",
        "previous_proposal": {"operations": []},
        "reviewer_output": {"decision": "request_changes"},
        "grounding_instructions": "Use authoritative workspace files.",
    }
    store, attempt_id, _app_ts, _artifacts = _seed_exhausted_semantic_retry(
        factory, tmp_path, human_revision=human_revision
    )
    session = factory()
    old_context = store.read_artifact_by_id(
        session.get(RepairAttemptModel, attempt_id).context_pack_artifact_id
    )
    session.close()

    _recovery_service(factory).recover_exhausted_semantic_retry(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="semantic-recovery-human-revision",
        actor="operator",
    )

    session = factory()
    child = session.get(RepairAttemptModel, "repair-stage-1-2")
    new_context = store.read_artifact_by_id(child.context_pack_artifact_id)
    assert json.loads(old_context.content)["human_revision"] == human_revision
    assert json.loads(new_context.content)["human_revision"] == human_revision
    assert new_context.envelope.input_hashes["recovered_from"] == old_context.ref.checksum
    session.close()
    engine.dispose()


def test_recovery_child_has_fresh_proposer_identity_and_duplicate_calls_reuse_it(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_exhausted_semantic_retry(factory, tmp_path)
    service = _recovery_service(factory)
    first = service.recover_exhausted_semantic_retry(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="semantic-recovery-duplicate",
        actor="operator",
    )
    replay = service.recover_exhausted_semantic_retry(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="semantic-recovery-duplicate",
        actor="operator",
    )
    different_key = service.recover_exhausted_semantic_retry(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="semantic-recovery-different-key",
        actor="operator",
    )

    assert first["attempt_id"] == replay["attempt_id"] == different_key["attempt_id"]
    assert replay["idempotent_replay"] is True
    assert different_key["idempotent_replay"] is True
    session = factory()
    children = (
        session.query(RepairAttemptModel)
        .filter(RepairAttemptModel.parent_attempt_id == attempt_id)
        .all()
    )
    assert len(children) == 1
    assert children[0].proposer_invocation_id is None
    assert children[0].reviewer_invocation_id is None
    assert session.query(LlmInvocationModel).filter(
        LlmInvocationModel.id.like("repair-stage-1-2:%")
    ).count() == 0
    session.close()
    engine.dispose()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("proposal_artifact_id", "proposal"),
        ("proposal_checksum", "sha256:proposal"),
        ("review_artifact_id", "review"),
        ("review_checksum", "sha256:review"),
        ("g10_gate_package_id", "gate-package"),
        ("apply_ledger_artifact_id", "apply-ledger"),
        ("validation_summary_artifact_id", "validation"),
        ("post_fingerprint", "sha256:post"),
    ],
)
def test_recovery_rejects_proposed_reviewed_or_applied_parent(
    tmp_path: Path, field: str, value: str
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_exhausted_semantic_retry(factory, tmp_path)
    session = factory()
    setattr(session.get(RepairAttemptModel, attempt_id), field, value)
    session.commit()
    session.close()

    with pytest.raises(RepairApplicationError) as raised:
        _recovery_service(factory).recover_exhausted_semantic_retry(
            run_id="run-1",
            attempt_id=attempt_id,
            expected_state_version=3,
            idempotency_key=f"recovery-rejected-{field}",
            actor="operator",
        )
    assert raised.value.code == "REPAIR_RECOVERY_NOT_ELIGIBLE"
    session = factory()
    assert session.query(RepairAttemptModel).count() == 1
    session.close()
    engine.dispose()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "request_changes"),
        ("current_node", "review_repair"),
        ("last_error_code", "REPAIR_REPLACEMENT_MISSING"),
    ],
)
def test_recovery_rejects_wrong_parent_or_continuation_state(
    tmp_path: Path, field: str, value: str
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_exhausted_semantic_retry(factory, tmp_path)
    session = factory()
    target = (
        session.get(RepairAttemptModel, attempt_id)
        if field == "status"
        else session.get(TransformationContinuationModel, "cont-1")
    )
    setattr(target, field, value)
    session.commit()
    session.close()

    with pytest.raises(RepairApplicationError) as raised:
        _recovery_service(factory).recover_exhausted_semantic_retry(
            run_id="run-1",
            attempt_id=attempt_id,
            expected_state_version=3,
            idempotency_key=f"recovery-state-{field}",
            actor="operator",
        )
    assert raised.value.code == "REPAIR_RECOVERY_NOT_ELIGIBLE"
    engine.dispose()


def test_recovery_requires_persisted_semantic_retry_evidence(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_exhausted_semantic_retry(factory, tmp_path)
    session = factory()
    session.delete(session.get(LlmInvocationModel, f"{attempt_id}:proposer:semantic-retry-1"))
    session.commit()
    session.close()

    with pytest.raises(RepairApplicationError) as raised:
        _recovery_service(factory).recover_exhausted_semantic_retry(
            run_id="run-1",
            attempt_id=attempt_id,
            expected_state_version=3,
            idempotency_key="recovery-no-retry-evidence",
            actor="operator",
        )
    assert raised.value.code == "REPAIR_RECOVERY_NOT_ELIGIBLE"
    engine.dispose()


def test_recovery_respects_repair_budget(tmp_path: Path, monkeypatch):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_exhausted_semantic_retry(factory, tmp_path)
    monkeypatch.setattr(
        repair_application_service,
        "repair_budget",
        lambda *args, **kwargs: {
            "consumed_attempts": 3,
            "consumed_applied": 2,
            "max_attempts": 3,
            "max_applied": 2,
        },
    )

    with pytest.raises(RepairApplicationError) as raised:
        _recovery_service(factory).recover_exhausted_semantic_retry(
            run_id="run-1",
            attempt_id=attempt_id,
            expected_state_version=3,
            idempotency_key="recovery-budget-exhausted",
            actor="operator",
        )
    assert raised.value.code == "REPAIR_LOOP_EXHAUSTED"
    session = factory()
    assert session.query(RepairAttemptModel).count() == 1
    session.close()
    engine.dispose()


def test_proposer_candidate_schema_rejects_backend_authority_fields():
    for field, value in (
        ("failure_evidence_checksum", "sha256:attacker"),
        ("context_pack_checksum", "sha256:attacker"),
        ("touched_files", ["src/other.ts"]),
        ("command", "npm test"),
    ):
        with pytest.raises(ValidationError):
            RepairProposalCandidate.model_validate({**_proposal_candidate(), field: value})

    operation = _proposal_candidate()
    operation["operations"][0]["preimage_sha256"] = "sha256:attacker"
    with pytest.raises(ValidationError):
        RepairProposalCandidate.model_validate(operation)


def test_propose_persists_failed_row_for_schema_failure_after_transport(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    out_of_vocabulary = _proposal_candidate()
    out_of_vocabulary["operations"] = [{"operation": "modify_file", "path": "src/app.ts"}]
    body = _responses_body(json.dumps(out_of_vocabulary))
    transport = _RecordingTransport(
        [
            ProviderTransportResult(
                body=body,
                provider_request_id="azure-request-schema-1",
                provider_status=200,
                response_content_type="application/json",
                response_bytes=len(json.dumps(body)),
                response_sha256=hashlib.sha256(json.dumps(body).encode()).hexdigest(),
                response_kind="json",
            )
        ]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairLlmError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "LLM_SCHEMA_VALIDATION_FAILED"
    assert len(transport.calls) == 1
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.idempotency_key == f"{attempt_id}:proposer"
    assert invocation.status == "failed"
    assert invocation.failure_code == "LLM_SCHEMA_VALIDATION_FAILED"
    assert invocation.failure_stage == "schema_validation"
    assert invocation.transport_started is True
    assert invocation.response_received is True
    assert invocation.provider_request_id == "azure-request-schema-1"
    assert invocation.provider_http_status == 200
    assert invocation.response_sha256 is not None
    session.close()
    engine.dispose()


def test_proposer_bounds_post_bind_schema_failure_with_semantic_retry(tmp_path: Path, monkeypatch):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    transport = _RecordingTransport(
        [
            _responses_body(json.dumps(_proposal_candidate())),
            _responses_body(json.dumps(_proposal_candidate())),
        ]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    original = service._coalesce_operations
    calls = 0

    def overflow_once(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        if calls == 0:
            result[0]["provenance"] = [
                {"key": f"evidence-{index}", "value": "x"} for index in range(33)
            ]
        calls += 1
        return result

    monkeypatch.setattr(service, "_coalesce_operations", overflow_once)

    proposal = service.propose(attempt_id)

    assert proposal["touched_files"] == ["src/app.ts"]
    assert len(transport.calls) == 2
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert {row.idempotency_key for row in invocations} == {
        f"{attempt_id}:proposer",
        f"{attempt_id}:proposer:semantic-retry-1",
    }
    session.close()
    engine.dispose()


def test_repair_runtime_uses_v2_candidates_and_binds_authority_fields(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, app_ts, _artifacts = _seed_service(factory, tmp_path)
    transport = _RecordingTransport(
        [
            _responses_body(json.dumps(_proposal_candidate())),
            _responses_body(json.dumps(_review_candidate())),
        ]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    proposal = service.propose(attempt_id)
    review = service.review(attempt_id)

    formats = [call["payload"]["text"]["format"] for call in transport.calls]
    assert [item["name"] for item in formats] == [
        "repair_proposer_candidate_v2",
        "repair_reviewer_candidate_v2",
    ]
    assert "failure_evidence_checksum" not in formats[0]["schema"]["properties"]
    assert "proposal_checksum" not in formats[1]["schema"]["properties"]
    session = factory()
    assert proposal["failure_evidence_checksum"] == session.get(RepairAttemptModel, attempt_id).failure_evidence_checksum
    assert proposal["context_pack_checksum"] == session.get(RepairAttemptModel, attempt_id).context_pack_checksum
    session.close()
    assert proposal["touched_files"] == ["src/app.ts"]
    assert proposal["operations"][0]["preimage_sha256"] == (
        "sha256:" + hashlib.sha256(app_ts.read_bytes()).hexdigest()
    )

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    invocations = {item.id: item for item in session.query(LlmInvocationModel).all()}
    assert review["proposal_checksum"] == attempt.proposal_checksum
    assert invocations[f"{attempt_id}:proposer"].prompt_version == (
        "prompt-repair-proposer-candidate-v2"
    )
    assert invocations[f"{attempt_id}:reviewer"].prompt_version == (
        "prompt-repair-reviewer-candidate-v2"
    )
    assert invocations[f"{attempt_id}:proposer"].schema_version == "schema-registry-v1"
    assert invocations[f"{attempt_id}:reviewer"].schema_version == "schema-registry-v1"
    session.close()
    engine.dispose()


def test_repair_runtime_binds_unified_diff_touched_files(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    proposal = _proposal_candidate()
    proposal.update(
        {
            "proposal_format": "unified_diff",
            "operations": [],
            "unified_diff": "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n--- text\n+++ text\n",
        }
    )
    transport = _RecordingTransport([_responses_body(json.dumps(proposal))])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    bound = service.propose(attempt_id)

    assert bound["operations"] == []
    assert bound["touched_files"] == ["src/app.ts"]
    engine.dispose()


def test_repair_runtime_rejects_incomplete_unified_diff_hunk(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    proposal = _proposal_candidate()
    proposal.update(
        {
            "proposal_format": "unified_diff",
            "operations": [],
            "unified_diff": "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1,2 +1,2 @@\n-old\n+new\n",
        }
    )
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport([_responses_body(json.dumps(proposal))]),
            _azure_settings(tmp_path),
        ),
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_DIFF_INVALID"
    assert not (artifacts / f"05_repairs/attempt-{attempt_id}/proposal.json").exists()
    engine.dispose()


@pytest.mark.parametrize(
    ("unified_diff", "expected_code"),
    [
        (
            "+++ b/src/app.ts\n@@ -1 +1 @@\n-old\n+new\n",
            "REPAIR_DIFF_INVALID",
        ),
        (
            "--- /forbidden\n+++ b/src/app.ts\n@@ -1 +1 @@\n-old\n+new\n",
            "REPAIR_PATH_FORBIDDEN",
        ),
    ],
)
def test_unified_diff_requires_safe_paired_headers(
    tmp_path: Path, unified_diff: str, expected_code: str
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    candidate = _proposal_candidate()
    candidate.update(
        {
            "proposal_format": "unified_diff",
            "operations": [],
            "unified_diff": unified_diff,
        }
    )
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport([_responses_body(json.dumps(candidate))]),
            _azure_settings(tmp_path),
        ),
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == expected_code
    session = factory()
    assert session.get(RepairAttemptModel, attempt_id).proposal_artifact_id is None
    session.close()
    engine.dispose()


@pytest.mark.parametrize("proposal_format", ["operations", "unified_diff"])
def test_candidate_binding_canonicalizes_paths_targets_and_preimages(
    tmp_path: Path, proposal_format: str
):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_text("old", encoding="utf-8")
    candidate = _proposal_candidate()
    candidate["validation_targets"] = ["build", "test", "build"]
    if proposal_format == "operations":
        candidate["operations"][0]["path"] = "src/./app.ts"
    else:
        candidate.update(
            {
                "proposal_format": "unified_diff",
                "operations": [],
                "unified_diff": "--- a/src/./app.ts\n+++ b/src/./app.ts\n@@ -1 +1 @@\n-old\n+new\n",
            }
        )
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:attempt-failure",
        "context_pack_checksum": "sha256:attempt-context",
    }

    bound = RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)

    assert bound["failure_evidence_checksum"] == "sha256:attempt-failure"
    assert bound["context_pack_checksum"] == "sha256:attempt-context"
    assert bound["touched_files"] == ["src/app.ts"]
    assert bound["validation_targets"] == ["build", "test"]
    if proposal_format == "operations":
        assert bound["operations"][0]["path"] == "src/app.ts"
        assert bound["operations"][0]["preimage_sha256"] == (
            "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
        )


def test_unknown_proposer_target_persists_only_linked_failure_artifact(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    candidate = _proposal_candidate()
    candidate["validation_targets"] = ["deploy"]
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport([_responses_body(json.dumps(candidate))]),
            _azure_settings(tmp_path),
        ),
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "LLM_SCHEMA_VALIDATION_FAILED"
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
    assert attempt.proposal_artifact_id is None
    assert len(invocation.artifact_ids) == 1
    assert invocation.artifact_checksums == {
        invocation.artifact_ids[0]: session.get(
            ArtifactMetadataModel, "metadata-" + invocation.artifact_ids[0]
        ).checksum
    }
    session.close()
    inventory = {
        path.name for path in (artifacts / "05_repairs" / f"attempt-{attempt_id}").glob("*.json")
    }
    assert "proposal.json" not in inventory
    assert "propose-error.json" in inventory
    engine.dispose()


def test_failed_replay_retains_all_immutable_failure_artifact_links(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    candidate = _proposal_candidate()
    candidate["validation_targets"] = ["deploy"]
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport(
                [
                    _responses_body(json.dumps(candidate)),
                    _responses_body(json.dumps(candidate)),
                ]
            ),
            _azure_settings(tmp_path),
        ),
    )

    for _ in range(2):
        with pytest.raises(RepairApplicationError) as raised:
            service.propose(attempt_id)
        assert raised.value.code == "LLM_SCHEMA_VALIDATION_FAILED"

    session = factory()
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
    assert len(invocation.artifact_ids) == 2
    assert len(set(invocation.artifact_ids)) == 2
    assert set(invocation.artifact_checksums) == set(invocation.artifact_ids)
    assert {
        session.get(ArtifactMetadataModel, "metadata-" + artifact_id).relative_path
        for artifact_id in invocation.artifact_ids
    } == {
        f"05_repairs/attempt-{attempt_id}/propose-error.json",
        f"05_repairs/attempt-{attempt_id}/propose-error__v2.json",
    }
    session.close()
    engine.dispose()


def test_failed_then_successful_proposer_replay_retains_failure_evidence(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    invalid = _proposal_candidate()
    invalid["validation_targets"] = ["deploy"]
    valid = _proposal_candidate()
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport(
                [_responses_body(json.dumps(invalid)), _responses_body(json.dumps(valid))]
            ),
            _azure_settings(tmp_path),
        ),
    )

    with pytest.raises(RepairApplicationError):
        service.propose(attempt_id)
    proposal = service.propose(attempt_id)
    assert service.propose(attempt_id) == proposal

    session = factory()
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
    assert len(invocation.artifact_ids) == 2
    assert set(invocation.artifact_checksums) == set(invocation.artifact_ids)
    assert {
        session.get(ArtifactMetadataModel, "metadata-" + artifact_id).relative_path
        for artifact_id in invocation.artifact_ids
    } == {
        f"05_repairs/attempt-{attempt_id}/propose-error.json",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
    }
    session.close()
    engine.dispose()


def test_dependency_transition_semantic_retry_remains_bounded(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    invalid = _dependency_transition_candidate(
        _dependency_transition_operation(),
        {"operation": "replace_text", "path": "package.json", "old_text": "", "new_text": ""},
    )
    transport = _RecordingTransport(
        [_responses_body(json.dumps(invalid)), _responses_body(json.dumps(invalid))]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as first:
        service.propose(attempt_id)
    assert first.value.code == "REPAIR_DEPENDENCY_TRANSITION_NOT_EXCLUSIVE"
    assert len(transport.calls) == 2

    with pytest.raises(RepairApplicationError) as exhausted:
        service.propose(attempt_id)
    assert exhausted.value.code == "REPAIR_SEMANTIC_RETRY_EXHAUSTED"
    assert len(transport.calls) == 2
    engine.dispose()


def test_missing_replace_target_hydrates_authoritative_retry_context(tmp_path: Path):
    engine, factory = _database(tmp_path)
    store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    initial = _proposal_candidate()
    initial["operations"][0]["old_text"] = "old\n"
    corrected = _proposal_candidate()
    transport = _RecordingTransport(
        [_responses_body(json.dumps(initial)), _responses_body(json.dumps(corrected))]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    context_artifact_id = attempt.context_pack_artifact_id
    session.close()
    original_context = store.read_artifact_by_id(context_artifact_id)

    proposal = service.propose(attempt_id)

    assert len(transport.calls) == 2
    assert proposal["operations"][0]["old_text"] == "old"
    retry_request = json.loads(transport.calls[1]["payload"]["input"][0]["content"][0]["text"])
    retry_segments = retry_request["context"]
    retry_text = "\n".join(
        segment["content"]
        for segment in retry_segments
        if isinstance(segment, dict) and isinstance(segment.get("content"), str)
    )
    assert "The requested replace_text target was not present in the authoritative" in retry_text
    assert "Regenerate old_text from that authoritative content." in retry_text
    hydrated = next(
        json.loads(segment["content"])
        for segment in retry_segments
        if isinstance(segment, dict)
        and isinstance(segment.get("content"), str)
        and segment["content"].startswith('{"schema_version": "repair-semantic-retry-context-v1"')
    )
    assert hydrated["targets"] == [
        {
            "bom": False,
            "content": "old",
            "final_newline": False,
            "path": "src/app.ts",
            "sha256": "sha256:" + hashlib.sha256(b"old").hexdigest(),
            "size_bytes": 3,
        }
    ]

    current_context = store.read_artifact_by_id(context_artifact_id)
    assert current_context.ref.checksum == original_context.ref.checksum
    assert current_context.content == original_context.content

    session = factory()
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
    rejected = next(
        store.read_artifact_by_id(artifact_id)
        for artifact_id in invocation.artifact_ids
        if store.read_artifact_by_id(artifact_id).ref.relative_path.endswith(
            "rejected-proposer-candidate.json"
        )
    )
    session.close()
    rejected_payload = json.loads(rejected.content)
    assert rejected_payload["candidate"]["operations"][0]["old_text"] == "old\n"
    engine.dispose()


def test_null_replace_preimage_hydrates_authoritative_retry_context(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    initial = _proposal_candidate()
    initial["operations"][0]["old_text"] = None
    transport = _RecordingTransport(
        [_responses_body(json.dumps(initial)), _responses_body(json.dumps(_proposal_candidate()))]
    )
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    proposal = service.propose(attempt_id)

    assert proposal["operations"][0]["old_text"] == "old"
    retry_request = json.loads(transport.calls[1]["payload"]["input"][0]["content"][0]["text"])
    hydrated = next(
        json.loads(segment["content"])
        for segment in retry_request["context"]
        if isinstance(segment, dict)
        and isinstance(segment.get("content"), str)
        and segment["content"].startswith('{"schema_version": "repair-semantic-retry-context-v1"')
    )
    assert hydrated["targets"][0]["content"] == "old"
    assert hydrated["targets"][0]["path"] == "src/app.ts"
    engine.dispose()


def test_hydrated_exact_preimage_without_final_newline_binds(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_bytes(b"old")
    candidate = _proposal_candidate()
    candidate["operations"][0]["old_text"] = "old"
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    bound = RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)

    assert bound["operations"][0]["old_text"] == "old"
    assert bound["operations"][0]["preimage_sha256"] == (
        "sha256:" + hashlib.sha256(b"old").hexdigest()
    )


def test_replace_text_null_preimage_is_rejected_without_none_coercion(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_bytes(b"old")
    candidate = _proposal_candidate()
    candidate["operations"][0]["old_text"] = None
    context = {
        "workspace_path": str(tmp_path),
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
    }

    with pytest.raises(RepairApplicationError) as raised:
        RepairApplicationService(scope=None)._bind_proposal_candidate(candidate, context)

    assert raised.value.code == "REPAIR_REPLACEMENT_PREIMAGE_REQUIRED"
    assert raised.value.message == (
        "replace_text requires a non-empty old_text copied from authoritative "
        "repository content; null or missing preimages are forbidden."
    )
    assert "None" not in raised.value.message


def test_strict_replacement_matcher_still_rejects_incorrect_preimage():
    with pytest.raises(RepairApplicationError) as raised:
        replace_text_once("old", "old\n", "new")

    assert raised.value.code == "REPAIR_REPLACEMENT_MISSING"
    assert raised.value.message == (
        "Replacement preimage must occur exactly once; found zero matches"
    )


def test_replace_preimage_failure_identifies_authoritative_path(tmp_path: Path):
    target = tmp_path / "src" / "app.ts"
    target.parent.mkdir()
    target.write_text("actual", encoding="utf-8", newline="")
    candidate = _proposal_candidate()
    candidate["operations"][0]["old_text"] = "wrong"

    with pytest.raises(RepairApplicationError) as raised:
        RepairApplicationService(scope=None)._bind_proposal_candidate(
            candidate,
            {
                "workspace_path": str(tmp_path),
                "failure_evidence_checksum": "sha256:failure",
                "context_pack_checksum": "sha256:context",
            },
        )

    assert raised.value.code == "REPAIR_REPLACEMENT_MISSING"
    assert "src/app.ts" in raised.value.message


def test_unknown_reviewer_target_persists_no_review_artifact(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    review = _review_candidate()
    review["required_validation_targets"] = ["deploy"]
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(
            _RecordingTransport(
                [
                    _responses_body(json.dumps(_proposal_candidate())),
                    _responses_body(json.dumps(review)),
                ]
            ),
            _azure_settings(tmp_path),
        ),
    )
    service.propose(attempt_id)

    with pytest.raises(RepairApplicationError) as raised:
        service.review(attempt_id)

    assert raised.value.code == "LLM_SCHEMA_VALIDATION_FAILED"
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    invocation = session.get(LlmInvocationModel, f"{attempt_id}:reviewer")
    assert attempt.review_artifact_id is None
    assert len(invocation.artifact_ids) == 1
    session.close()
    inventory = {
        path.name for path in (artifacts / "05_repairs" / f"attempt-{attempt_id}").glob("*.json")
    }
    assert "review.json" not in inventory
    assert "review-error.json" in inventory
    engine.dispose()


def test_review_binds_immutable_active_proposal_artifact_checksum(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    transport = _RecordingTransport([
        _responses_body(json.dumps(_proposal_candidate())),
        _responses_body(json.dumps(_review_candidate())),
    ])
    service = RepairApplicationService(
        scope=_scope(factory),
        gateway=_gateway(transport, _azure_settings(tmp_path)),
    )
    service.propose(attempt_id)
    calls_before_review = len(transport.calls)
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.proposal_checksum = "sha256:stale-row-value"
    session.commit()
    session.close()

    with pytest.raises(RepairApplicationError) as raised:
        service.review(attempt_id)
    assert raised.value.code == "REPAIR_ARTIFACT_RECOVERY_FAILED"
    assert len(transport.calls) == calls_before_review

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    assert attempt.review_artifact_id is None
    assert session.get(LlmInvocationModel, f"{attempt_id}:reviewer") is None
    session.close()
    inventory = {
        path.name for path in (artifacts / "05_repairs" / f"attempt-{attempt_id}").glob("*.json")
    }
    assert "review.json" not in inventory
    engine.dispose()

def test_v1_persisted_proposal_and_review_artifacts_still_recover(tmp_path: Path):
    engine, factory = _database(tmp_path)
    store, attempt_id, app_ts, artifacts = _seed_service(factory, tmp_path)
    session = factory()
    seeded_attempt = session.get(RepairAttemptModel, attempt_id)
    proposal_payload = _proposal(app_ts)
    proposal_payload["failure_evidence_checksum"] = seeded_attempt.failure_evidence_checksum
    proposal_payload["context_pack_checksum"] = seeded_attempt.context_pack_checksum
    session.close()
    proposal = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(proposal_payload),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-proposal-v1",
        created_at=NOW,
    )
    review_payload = {
        "proposal_checksum": proposal.ref.checksum,
        "decision": "accept",
        "findings": [],
        "policy_checks": ["paths"],
        "risk_assessment": "low",
        "required_validation_targets": ["build"],
        "limitations": [],
    }
    review = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/review.json",
        json.dumps(review_payload),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-review-v1",
        created_at=NOW,
    )
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.proposal_artifact_id = proposal.ref.artifact_id
    attempt.proposal_checksum = proposal.ref.checksum
    attempt.review_artifact_id = review.ref.artifact_id
    attempt.review_checksum = review.ref.checksum
    for role, stored in (("proposer", proposal), ("reviewer", review)):
        session.add(
            LlmInvocationModel(
                id=f"{attempt_id}:{role}",
                run_id="run-1",
                stage_id="stage-1",
                idempotency_key=f"{attempt_id}:{role}",
                request_checksum="sha256:v1-request",
                input_hashes=[attempt.failure_evidence_checksum, attempt.context_pack_checksum],
                correlation_id=f"{attempt_id}:{role}",
                actor="transformer",
                role=f"repair_{role}",
                task_type="repair_diagnosis" if role == "proposer" else "repair_review",
                provider="azure_openai",
                deployment_alias="azure-openai",
                prompt_version=f"repair-{role}-v1",
                schema_version="schema-registry-v1",
                pricing_version="mvp-pricing-2026-01",
                stage="repair",
                status="completed",
                artifact_ids=[stored.ref.artifact_id],
                artifact_checksums={stored.ref.artifact_id: stored.ref.checksum},
                state_version=1,
                event_sequence=0,
                retries=0,
                transport_started=True,
                started_at=NOW,
                completed_at=NOW,
                created_at=NOW,
            )
        )
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
    context = {
        "attempt_id": attempt_id,
        "run_id": "run-1",
        "stage_id": "stage-1",
        "artifact_root": str(artifacts),
    }
    service = RepairApplicationService(scope=_scope(factory))

    assert service._recover_completed(context, role="proposer") == proposal_payload
    assert service._recover_completed(context, role="reviewer") == review_payload
    engine.dispose()


def test_replayed_v1_invocation_refreshes_v2_provenance_for_success_and_failure(
    tmp_path: Path, monkeypatch
):
    for name, response, expected_status in (
        ("success", _responses_body(json.dumps(_proposal_candidate())), "completed"),
        (
            "failure",
            AzureGatewayError(LlmFailureCode.INVALID_REQUEST, "Azure OpenAI request failed."),
            "failed",
        ),
    ):
        case_path = tmp_path / name
        case_path.mkdir()
        engine, factory = _database(case_path)
        _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, case_path)
        _seed_failed_v1_invocation(factory, attempt_id)
        settings = _azure_settings(case_path).model_copy(
            update={"llm_schema_registry_version": "repair-schema-registry-v2"}
        )
        monkeypatch.setattr("app.services.repair_application_service.get_settings", lambda: settings)
        service = RepairApplicationService(
            scope=_scope(factory), gateway=_gateway(_RecordingTransport([response]), settings)
        )

        if expected_status == "completed":
            service.propose(attempt_id)
        else:
            with pytest.raises(RepairLlmError):
                service.propose(attempt_id)

        session = factory()
        invocation = session.get(LlmInvocationModel, f"{attempt_id}:proposer")
        assert invocation.status == expected_status
        assert invocation.prompt_version == "prompt-repair-proposer-candidate-v2"
        assert invocation.schema_version == "repair-schema-registry-v2"
        attempt = session.get(RepairAttemptModel, attempt_id)
        assert invocation.input_hashes[:2] == [attempt.failure_evidence_checksum, attempt.context_pack_checksum]
        assert invocation.input_hashes[2].startswith("schema:")
        assert "legacy" not in " ".join(invocation.input_hashes)
        session.close()
        engine.dispose()


def test_pre_transport_disabled_failure_persists_without_transport(tmp_path: Path, monkeypatch):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    disabled = _azure_settings(tmp_path).model_copy(update={"llm_enabled": False})
    monkeypatch.setattr(
        "app.services.repair_application_service.get_settings", lambda: disabled
    )
    service = RepairApplicationService(scope=_scope(factory), gateway=None)

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_LLM_DISABLED"
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.status == "failed"
    assert invocation.failure_code == "REPAIR_LLM_DISABLED"
    assert invocation.failure_stage == "local"
    assert invocation.transport_started is False
    assert invocation.response_received is False
    assert invocation.provider_request_id is None
    assert invocation.provider_http_status is None
    assert invocation.response_sha256 is None
    assert invocation.prompt_version == "prompt-repair-proposer-candidate-v2"
    assert invocation.schema_version == "schema-registry-v1"
    session.close()
    engine.dispose()


def test_semantic_failure_persists_repair_semantics_stage_without_proposal_artifact(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, app_ts, artifacts = _seed_service(factory, tmp_path)
    mixed = _proposal_candidate()
    mixed["unified_diff"] = "--- a/src/app.ts\n+++ b/src/app.ts\n"
    transport = _RecordingTransport([_responses_body(json.dumps(mixed))])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_PROPOSAL_FORMAT_INVALID"
    session = factory()
    invocations = session.query(LlmInvocationModel).all()
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.status == "failed"
    assert invocation.failure_code == "REPAIR_PROPOSAL_FORMAT_INVALID"
    assert invocation.failure_stage == "repair_semantics"
    assert invocation.transport_started is True
    assert invocation.response_received is True
    assert invocation.provider_request_id is None
    assert invocation.provider_http_status is None
    session.close()
    inventory = sorted(
        str(path.relative_to(artifacts)).replace("\\", "/")
        for path in artifacts.rglob("*")
        if path.is_file()
    )
    assert f"05_repairs/attempt-{attempt_id}/proposal.json" not in inventory
    assert f"05_repairs/attempt-{attempt_id}/propose-error.json" in inventory
    engine.dispose()


def test_recover_completed_failed_returns_none_and_uncertain_transport_raises(
    tmp_path: Path,
):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    context = {
        "attempt_id": attempt_id,
        "run_id": "run-1",
        "stage_id": "stage-1",
        "artifact_root": str(artifacts),
    }
    session = factory()
    session.add(
        LlmInvocationModel(
            id=f"{attempt_id}:proposer",
            run_id="run-1",
            stage_id="stage-1",
            idempotency_key=f"{attempt_id}:proposer",
            request_checksum="sha256:request",
            input_hashes=["sha256:failure", "sha256:context"],
            correlation_id=f"{attempt_id}:proposer",
            actor="transformer",
            role="repair_proposer",
            task_type="repair_diagnosis",
            provider="azure_openai",
            deployment_alias="azure-openai",
            prompt_version="repair-proposer-v1",
            schema_version="schema-registry-v1",
            pricing_version="mvp-pricing-2026-01",
            stage="repair",
            redacted_summary=None,
            status="failed",
            failure_code="LLM_PROVIDER_BAD_REQUEST",
            artifact_ids=[],
            artifact_checksums={},
            state_version=1,
            event_sequence=0,
            retries=0,
            started_at=NOW,
            created_at=NOW,
        )
    )
    session.commit()
    session.close()
    service = RepairApplicationService(scope=_scope(factory))

    assert service._recover_completed(context, role="proposer") is None

    session = factory()
    invocation = session.query(LlmInvocationModel).one()
    invocation.status = "in_progress"
    invocation.transport_started = True
    session.commit()
    session.close()
    with pytest.raises(RepairApplicationError) as raised:
        service._recover_completed(context, role="proposer")
    assert raised.value.code == "REPAIR_INVOCATION_UNCERTAIN"
    engine.dispose()


def test_child_attempt_authority_snapshot_binds_parent_review_lineage(tmp_path: Path):
    """A child attempt's authority snapshot durably carries the parent review refs.

    RED until the fix: parent_review_artifact_id/parent_review_checksum are not
    part of the context or the authority snapshot, and a tampered parent review
    reference is not detected by the fresh-authority re-read.
    """
    engine, factory = _database(tmp_path)
    store, attempt_id, app_ts, _artifacts = _seed_service(factory, tmp_path)
    proposal = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(_proposal(app_ts), sort_keys=True),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-proposal",
        created_at=NOW,
    )
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.proposal_artifact_id = proposal.ref.artifact_id
    attempt.proposal_checksum = proposal.ref.checksum
    attempt.proposer_invocation_id = f"{attempt_id}:proposer"
    attempt.parent_attempt_id = "repair-parent"
    attempt.parent_review_artifact_id = "artifact-parent-review"
    attempt.parent_review_checksum = "sha256:parent-review"
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + proposal.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=proposal.ref.artifact_type.value,
            relative_path=proposal.ref.relative_path,
            checksum=proposal.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    session.commit()
    session.close()

    service = RepairApplicationService(scope=_scope(factory))
    context = service._attempt_context(attempt_id, include_proposal=True)
    assert context["parent_review_artifact_id"] == "artifact-parent-review"
    assert context["parent_review_checksum"] == "sha256:parent-review"
    assert context["authority_snapshot"]["parent_review_artifact_id"] == "artifact-parent-review"
    assert context["authority_snapshot"]["parent_review_checksum"] == "sha256:parent-review"

    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    attempt.parent_review_checksum = "sha256:tampered"
    session.commit()
    session.close()
    with pytest.raises(RepairApplicationError) as raised:
        service._assert_fresh_authority(context, role="reviewer", include_proposal=True)
    assert raised.value.code == "REPAIR_REVIEW_STALE"
    engine.dispose()


def _tamper_context_pack(artifacts: Path, factory, *, mutate, sort_keys: bool = True) -> None:
    """Rewrite the bound context pack keeping envelope/metadata checksums consistent."""
    session = factory()
    attempt = session.get(RepairAttemptModel, "repair-1")
    row = session.get(ArtifactMetadataModel, "metadata-" + attempt.context_pack_artifact_id)
    relative_path = row.relative_path
    session.close()
    context_path = artifacts / relative_path
    payload = json.loads(context_path.read_text(encoding="utf-8"))
    mutate(payload)
    context_path.write_text(
        json.dumps(payload, indent=2, sort_keys=sort_keys), encoding="utf-8"
    )
    content_hash = "sha256:" + hashlib.sha256(context_path.read_bytes()).hexdigest()
    sidecar = artifacts / f"{relative_path}.meta.json"
    envelope = json.loads(sidecar.read_text(encoding="utf-8"))
    envelope["content_hash"] = content_hash
    sidecar.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
    session = factory()
    row = session.get(ArtifactMetadataModel, row.id)
    row.checksum = content_hash
    attempt = session.get(RepairAttemptModel, "repair-1")
    attempt.context_pack_checksum = content_hash
    session.commit()
    session.close()


def _reorder_file_excerpts(payload) -> None:
    entries = payload["file_excerpts"]
    first = entries.pop("package.json")
    payload["file_excerpts"] = {"package.json": first, **entries}


@pytest.mark.parametrize(
    "mutate, sort_keys",
    [
        (
            lambda payload: payload["file_excerpts"]["package.json"].update(
                {"sha256": "sha256:" + "0" * 64}
            ),
            True,
        ),
        (
            lambda payload: payload["file_excerpts"]["package.json"].update({"size_bytes": 0}),
            True,
        ),
        (lambda payload: payload["bounds"].update({"max_total_bytes": 1}), True),
        (_reorder_file_excerpts, False),
    ],
)
def test_tampered_context_pack_rejected_at_use_time(tmp_path: Path, mutate, sort_keys):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, artifacts = _seed_service(factory, tmp_path)
    _tamper_context_pack(artifacts, factory, mutate=mutate, sort_keys=sort_keys)
    transport = _RecordingTransport([])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )

    with pytest.raises(RepairApplicationError) as raised:
        service.propose(attempt_id)

    assert raised.value.code == "REPAIR_CONTEXT_INVALID"
    assert transport.calls == []
    session = factory()
    assert session.query(LlmInvocationModel).count() == 0
    session.close()
    engine.dispose()


def _force_evidence() -> dict:
    return {
        "normalized_failure": {
            "error_code": "DEPENDENCY_PREFLIGHT_BLOCKED",
            "failure_message": "npm ERR! ERESOLVE unable to resolve dependency tree",
            "failure_diagnosis": {
                "kind": "peer_dependency_conflict",
                "package": "@angular/core",
                "required_ranges": ["^19.0.0"],
            },
        }
    }


def _generic_executable_evidence() -> dict:
    return {
        "normalized_failure": {
            "error_code": "BUILD_FAILED",
            "failure_message": "TypeScript compilation failed",
        }
    }


def _transition_operation(**overrides) -> dict:
    operation = {
        "operation": "dependency_transition",
        "path": "package.json",
        "strategy": "detach_update_reattach",
        "repair_kind": "dependency_transition",
        "blocking_dependency": {"package": "@angular/core", "version": "18.2.0"},
        "target_state": {"package": "@angular/core", "target_major": 19},
    }
    operation.update(overrides)
    return operation


def test_causal_force_check_ignores_force_mention_in_rationale() -> None:
    proposal = {
        "operations": [_transition_operation()],
        "rationale": ["This repair does not bypass forbidden policies (for example using --force)"],
        "limitations": [],
    }
    assert causal_rejection(_force_evidence(), proposal) is None


def test_causal_force_check_ignores_force_mention_in_limitations() -> None:
    proposal = {
        "operations": [_transition_operation()],
        "rationale": ["Complete dependency transition"],
        "limitations": ["This sequence avoids using --force"],
    }
    assert causal_rejection(_force_evidence(), proposal) is None


def test_causal_force_check_rejects_executable_force_in_operation() -> None:
    proposal = {
        "operations": [
            {
                "operation": "replace_text",
                "path": "package.json",
                "new_text": "npm install --force",
                "old_text": "old",
            }
        ],
        "rationale": ["Update dependencies"],
        "limitations": [],
    }
    rejection = causal_rejection(_force_evidence(), proposal)
    assert rejection is not None
    assert rejection.code == "CAUSAL_REJECTION_FORCE"


def test_causal_force_check_allows_removing_force_via_replace_text() -> None:
    proposal = {
        "operations": [
            {
                "operation": "replace_text",
                "path": "package.json",
                "old_text": "ng update --force",
                "new_text": "ng update",
            }
        ],
        "rationale": ["Drop the --force flag"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_force_check_rejects_force_introduced_in_new_text() -> None:
    proposal = {
        "operations": [
            {
                "operation": "replace_text",
                "path": "package.json",
                "old_text": "ng update",
                "new_text": "ng update --force",
            }
        ],
        "rationale": ["Update dependencies"],
        "limitations": [],
    }
    rejection = causal_rejection(_generic_executable_evidence(), proposal)
    assert rejection is not None
    assert rejection.code == "CAUSAL_REJECTION_FORCE"


def test_causal_force_check_allows_diff_removing_force() -> None:
    proposal = {
        "operations": [],
        "touched_files": ["package.json"],
        "unified_diff": (
            "--- a/package.json\n"
            "+++ b/package.json\n"
            "@@ -1,3 +1,3 @@\n"
            ' "scripts": {\n'
            '-  "migrate": "ng update --force"\n'
            '+  "migrate": "ng update"\n'
            ' }'
        ),
        "rationale": ["Remove --force from the migrate script"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_force_check_rejects_diff_adding_force() -> None:
    proposal = {
        "operations": [],
        "touched_files": ["package.json"],
        "unified_diff": (
            "--- a/package.json\n"
            "+++ b/package.json\n"
            "@@ -1,3 +1,3 @@\n"
            ' "scripts": {\n'
            '-  "migrate": "ng update"\n'
            '+  "migrate": "ng update --force"\n'
            ' }'
        ),
        "rationale": ["Update dependencies"],
        "limitations": [],
    }
    rejection = causal_rejection(_generic_executable_evidence(), proposal)
    assert rejection is not None
    assert rejection.code == "CAUSAL_REJECTION_FORCE"


def test_causal_force_check_allows_source_comment_mentioning_force() -> None:
    proposal = {
        "operations": [
            {
                "operation": "replace_text",
                "path": "src/app/example.ts",
                "old_text": "// old",
                "new_text": "// never use --force during Angular migration",
            }
        ],
        "rationale": ["Add a migration note"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_force_check_allows_documentation_content_mentioning_force() -> None:
    proposal = {
        "operations": [
            {
                "operation": "create_text_file",
                "path": "docs/usage-guide",
                "content": "Do not use ng update --force during the migration",
            }
        ],
        "rationale": ["Document the migration policy"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_force_check_allows_diff_comment_mentioning_force() -> None:
    proposal = {
        "operations": [],
        "touched_files": ["src/app/example.ts"],
        "unified_diff": (
            "--- a/src/app/example.ts\n"
            "+++ b/src/app/example.ts\n"
            "@@ -1,3 +1,3 @@\n"
            ' "migrate": "ng update"\n'
            "+ // Never use --force here\n"
        ),
        "rationale": ["Add a comment"],
        "limitations": [],
    }
    assert causal_rejection(_generic_executable_evidence(), proposal) is None


def test_causal_dependency_transition_validation_unchanged() -> None:
    proposal = {
        "operations": [_transition_operation()],
        "rationale": ["Complete dependency transition"],
        "limitations": [],
    }
    assert causal_rejection(_force_evidence(), proposal) is None


def _seed_uncertain_reviewer(factory, tmp_path: Path):
    store, attempt_id, app_ts, artifacts = _seed_service(factory, tmp_path)
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    plan = session.get(StageExecutionPlanModel, "stage-plan-stage-1")
    continuation = session.get(TransformationContinuationModel, "cont-1")
    proposal = _proposal(app_ts)
    proposal["failure_evidence_checksum"] = attempt.failure_evidence_checksum
    proposal["context_pack_checksum"] = attempt.context_pack_checksum
    stored = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/proposal.json",
        json.dumps(proposal, sort_keys=True, indent=2),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-proposer",
        created_at=NOW,
    )
    diagnostic = store.write_text_artifact(
        "run-1",
        f"05_repairs/attempt-{attempt_id}/review-error.json",
        json.dumps({"code": "LLM_PROVIDER_TIMEOUT", "response_received": False}),
        ArtifactType.JSON,
        stage_id="stage-1",
        attempt_id=attempt_id,
        created_by="repair-reviewer",
        created_at=NOW,
    )
    checkpoint = StageCheckpointModel(
        id="checkpoint-pre-repair",
        run_id="run-1",
        stage_id="stage-1",
        kind="pre_repair",
        sequence=1,
        workspace_alias="STAGE_WORKSPACE_1",
        workspace_path=binding.workspace_path,
        workspace_fingerprint=binding.workspace_fingerprint,
        safe_for_resume=True,
        sealed=True,
        state_version=1,
        created_at=NOW,
    )
    session.add(checkpoint)
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
    session.add(
        ArtifactMetadataModel(
            id="metadata-" + diagnostic.ref.artifact_id,
            run_id="run-1",
            stage_id="stage-1",
            artifact_type=diagnostic.ref.artifact_type.value,
            relative_path=diagnostic.ref.relative_path,
            checksum=diagnostic.ref.checksum,
            created_at=NOW,
            finalized_at=NOW,
            immutable=True,
        )
    )
    attempt.status = "proposed"
    attempt.checkpoint_id = checkpoint.id
    attempt.proposal_artifact_id = stored.ref.artifact_id
    attempt.proposal_checksum = stored.ref.checksum
    attempt.pre_fingerprint = binding.workspace_fingerprint
    attempt.updated_at = NOW
    continuation.status = "blocked"
    continuation.current_node = "review_repair"
    continuation.worker_id = None
    continuation.lease_expires_at = None
    continuation.last_error_code = "REPAIR_INVOCATION_UNCERTAIN"
    continuation.last_error_message = "Repair LLM invocation outcome is uncertain"
    continuation.state_version = 3
    old_key = f"{attempt_id}:reviewer"
    old = LlmInvocationModel(
        id=old_key,
        run_id="run-1",
        stage_id="stage-1",
        idempotency_key=old_key,
        request_checksum="sha256:original-review-request",
        input_hashes=[attempt.failure_evidence_checksum, attempt.context_pack_checksum],
        correlation_id=old_key,
        actor="transformer",
        role="repair_reviewer",
        task_type="repair_review",
        provider="azure_openai",
        deployment_alias="azure-openai",
        prompt_version="prompt-repair-reviewer-candidate-v2",
        schema_version="schema-registry-v1",
        pricing_version="mvp-pricing-2026-01",
        stage="repair",
        redacted_summary=None,
        status="in_progress",
        failure_code="LLM_PROVIDER_TIMEOUT",
        artifact_ids=[diagnostic.ref.artifact_id],
        artifact_checksums={diagnostic.ref.artifact_id: diagnostic.ref.checksum},
        state_version=1,
        event_sequence=0,
        retries=0,
        transport_started=True,
        response_received=None,
        started_at=NOW,
        completed_at=None,
        created_at=NOW,
    )
    session.add(old)
    session.commit()
    session.close()
    return store, attempt_id, stored.ref.checksum, old_key, artifacts


def test_uncertain_reviewer_recovery_is_explicit_and_idempotent(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, proposal_checksum, old_key, _artifacts = _seed_uncertain_reviewer(factory, tmp_path)
    service = RepairApplicationService(scope=_scope(factory))

    with pytest.raises(RepairApplicationError) as blocked:
        service._recover_completed(
            service._attempt_context(attempt_id, include_proposal=True),
            role="reviewer",
            schema_name=service.reviewer_schema,
            task_type=LlmTaskType.REPAIR_REVIEW,
            schema=RepairReviewCandidate,
        )
    assert blocked.value.code == "REPAIR_INVOCATION_UNCERTAIN"

    result = service.recover_uncertain_invocation(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="operator-recovery-1",
        actor="operator",
        reason="Provider outcome cannot be reconstructed from durable evidence.",
    )
    assert result["old_invocation_key"] == old_key
    assert result["new_invocation_key"] == f"{attempt_id}:reviewer:recovery-1"
    assert result["proposal_checksum"] == proposal_checksum
    assert result["idempotent_replay"] is False

    session = factory()
    abandoned = session.get(LlmInvocationModel, old_key)
    successor = session.get(LlmInvocationModel, f"{attempt_id}:reviewer:recovery-1")
    attempt = session.get(RepairAttemptModel, attempt_id)
    continuation = session.get(TransformationContinuationModel, "cont-1")
    events = session.query(WorkflowEventModel).filter_by(run_id="run-1").all()
    assert abandoned.status == "uncertain_abandoned"
    assert abandoned.completed_at is not None
    assert abandoned.request_checksum == "sha256:original-review-request"
    assert abandoned.idempotency_key == old_key
    assert abandoned.failure_code == "LLM_PROVIDER_TIMEOUT"
    assert len(abandoned.artifact_ids) == 1
    assert successor.status == "in_progress"
    assert successor.transport_started is False
    assert successor.idempotency_key == f"{attempt_id}:reviewer:recovery-1"
    assert successor.request_checksum == abandoned.request_checksum
    assert attempt.reviewer_invocation_id == successor.id
    assert attempt.proposal_checksum == proposal_checksum
    assert continuation.status == "queued"
    assert continuation.current_node == "review_repair"
    assert continuation.last_error_code is None
    recovery_events = [event for event in events if event.event_type == WorkflowEventType.REPAIR_INVOCATION_RECOVERED.value]
    assert len(recovery_events) == 1
    payload = recovery_events[0].payload
    assert payload["old_invocation_key"] == old_key
    assert payload["new_invocation_key"] == successor.idempotency_key
    assert payload["proposal_checksum"] == proposal_checksum
    assert payload["operator_actor"] == "operator"
    assert payload["recovery_request_idempotency_key"] == "operator-recovery-1"
    assert payload["reason"].startswith("Provider outcome")
    session.close()

    replay = service.recover_uncertain_invocation(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="operator-recovery-2",
        actor="operator",
        reason="Provider outcome cannot be reconstructed from durable evidence.",
    )
    assert replay["idempotent_replay"] is True
    assert replay["new_invocation_key"] == f"{attempt_id}:reviewer:recovery-1"
    session = factory()
    assert session.query(LlmInvocationModel).filter(LlmInvocationModel.id.like(f"{attempt_id}:reviewer:recovery-%")).count() == 1
    session.close()
    engine.dispose()


def test_uncertain_reviewer_recovery_rejects_invalid_state_without_mutation(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_uncertain_reviewer(factory, tmp_path)
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    continuation.last_error_code = "OTHER_ERROR"
    session.commit()
    session.close()
    service = RepairApplicationService(scope=_scope(factory))

    with pytest.raises(RepairApplicationError) as raised:
        service.recover_uncertain_invocation(
            run_id="run-1",
            attempt_id="repair-1",
            expected_state_version=3,
            idempotency_key="operator-recovery-1",
            actor="operator",
            reason="operator recovery",
        )
    assert raised.value.code == "REPAIR_RECOVERY_NOT_ELIGIBLE"
    session = factory()
    assert session.get(LlmInvocationModel, "repair-1:reviewer").status == "in_progress"
    assert session.get(RepairAttemptModel, "repair-1").reviewer_invocation_id is None
    session.close()
    engine.dispose()


def _set_uncertain_reviewer_waiter(
    factory,
    *,
    execution_id: str,
    status: str,
    run_id: str = "run-1",
    stage_id: str | None = "stage-1",
) -> None:
    session = factory()
    continuation = session.get(TransformationContinuationModel, "cont-1")
    execution = CommandExecutionModel(
        id=execution_id,
        run_id=run_id,
        stage_id=stage_id,
        executable="node",
        arguments=["--version"],
        status=status,
        requested_at=NOW,
        finished_at=NOW if status not in {
            CommandStatus.QUEUED.value,
            CommandStatus.PENDING.value,
            CommandStatus.RUNNING.value,
        } else None,
    )
    session.add(execution)
    continuation.waiting_execution_id = execution_id
    session.commit()
    session.close()


def test_uncertain_reviewer_recovery_terminal_failed_waiter_allows_eligibility(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_uncertain_reviewer(factory, tmp_path)
    _set_uncertain_reviewer_waiter(
        factory,
        execution_id="terminal-failed-waiter",
        status=CommandStatus.FAILED.value,
    )
    service = RepairApplicationService(scope=_scope(factory))

    result = service.recover_uncertain_invocation(
        run_id="run-1",
        attempt_id="repair-1",
        expected_state_version=3,
        idempotency_key="operator-recovery-1",
        actor="operator",
        reason="terminal failed waiter is historical",
    )

    assert result["idempotent_replay"] is False
    engine.dispose()


def test_uncertain_reviewer_recovery_terminal_succeeded_waiter_allows_eligibility(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_uncertain_reviewer(factory, tmp_path)
    _set_uncertain_reviewer_waiter(
        factory,
        execution_id="terminal-succeeded-waiter",
        status=CommandStatus.SUCCEEDED.value,
    )
    service = RepairApplicationService(scope=_scope(factory))

    result = service.recover_uncertain_invocation(
        run_id="run-1",
        attempt_id="repair-1",
        expected_state_version=3,
        idempotency_key="operator-recovery-1",
        actor="operator",
        reason="terminal succeeded waiter is historical",
    )

    assert result["idempotent_replay"] is False
    engine.dispose()


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(CommandStatus.QUEUED.value, id="queued"),
        pytest.param(CommandStatus.PENDING.value, id="pending"),
        pytest.param(CommandStatus.RUNNING.value, id="running"),
    ],
)
def test_uncertain_reviewer_recovery_active_waiter_blocks(tmp_path: Path, status: str):
    engine, factory = _database(tmp_path)
    _seed_uncertain_reviewer(factory, tmp_path)
    _set_uncertain_reviewer_waiter(
        factory,
        execution_id=f"active-{status}-waiter",
        status=status,
    )
    service = RepairApplicationService(scope=_scope(factory))

    with pytest.raises(RepairApplicationError) as raised:
        service.recover_uncertain_invocation(
            run_id="run-1",
            attempt_id="repair-1",
            expected_state_version=3,
            idempotency_key="operator-recovery-1",
            actor="operator",
            reason="active waiter must retain ownership",
        )

    assert raised.value.code == "REPAIR_RECOVERY_NOT_ELIGIBLE"
    engine.dispose()


@pytest.mark.parametrize(
    "waiter_case",
    [
        pytest.param("missing", id="missing"),
        pytest.param("wrong_run", id="wrong-run"),
        pytest.param("wrong_continuation", id="wrong-continuation"),
        pytest.param("malformed", id="malformed"),
    ],
)
def test_uncertain_reviewer_recovery_nonexistent_or_mismatched_waiter_fails_closed(
    tmp_path: Path, waiter_case: str
):
    engine, factory = _database(tmp_path)
    _seed_uncertain_reviewer(factory, tmp_path)
    if waiter_case == "missing":
        session = factory()
        session.get(TransformationContinuationModel, "cont-1").waiting_execution_id = "missing-waiter"
        session.commit()
        session.close()
    else:
        _set_uncertain_reviewer_waiter(
            factory,
            execution_id=f"{waiter_case}-waiter",
            status=CommandStatus.SUCCEEDED.value,
            run_id="other-run" if waiter_case == "wrong_run" else "run-1",
            stage_id=None if waiter_case == "malformed" else (
                "other-stage" if waiter_case == "wrong_continuation" else "stage-1"
            ),
        )
    service = RepairApplicationService(scope=_scope(factory))

    with pytest.raises(RepairApplicationError) as raised:
        service.recover_uncertain_invocation(
            run_id="run-1",
            attempt_id="repair-1",
            expected_state_version=3,
            idempotency_key="operator-recovery-1",
            actor="operator",
            reason="malformed or mismatched waiter must fail closed",
        )

    assert raised.value.code == "REPAIR_RECOVERY_NOT_ELIGIBLE"
    engine.dispose()


def test_uncertain_reviewer_recovery_null_waiter_retains_eligibility(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _seed_uncertain_reviewer(factory, tmp_path)
    service = RepairApplicationService(scope=_scope(factory))

    result = service.recover_uncertain_invocation(
        run_id="run-1",
        attempt_id="repair-1",
        expected_state_version=3,
        idempotency_key="operator-recovery-1",
        actor="operator",
        reason="null waiter retains existing eligibility",
    )

    assert result["idempotent_replay"] is False
    session = factory()
    assert session.get(TransformationContinuationModel, "cont-1").waiting_execution_id is None
    session.close()
    engine.dispose()


def test_uncertain_proposer_recovery_allocates_next_generation_after_prior_recovery(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    session = factory()
    attempt = session.get(RepairAttemptModel, attempt_id)
    # A proposer can be marked proposed before its proposal artifact is durable;
    # uncertain-invocation recovery must still accept this proposal-less state.
    attempt.status = "proposed"
    binding = session.get(StageWorkspaceBindingModel, "binding-1")
    continuation = session.get(TransformationContinuationModel, "cont-1")
    checkpoint = StageCheckpointModel(
        id="checkpoint-pre-repair",
        run_id="run-1",
        stage_id="stage-1",
        kind="pre_repair",
        sequence=1,
        workspace_alias="STAGE_WORKSPACE_1",
        workspace_path=binding.workspace_path,
        workspace_fingerprint=binding.workspace_fingerprint,
        safe_for_resume=True,
        sealed=True,
        state_version=1,
        created_at=NOW,
    )
    checkpoint_snapshot = tmp_path / "checkpoint-snapshot"
    shutil.copytree(binding.workspace_path, checkpoint_snapshot)
    checkpoint.workspace_path = str(checkpoint_snapshot)
    old_key = f"{attempt_id}:proposer"
    session.add(checkpoint)
    session.add(
        LlmInvocationModel(
            id=old_key,
            run_id="run-1",
            stage_id="stage-1",
            idempotency_key=old_key,
            request_checksum="sha256:original-proposer-request",
            input_hashes=[attempt.failure_evidence_checksum, attempt.context_pack_checksum],
            correlation_id=old_key,
            actor="transformer",
            role="repair_proposer",
            task_type="repair_diagnosis",
            provider="azure_openai",
            deployment_alias="azure-openai",
            prompt_version="prompt-repair-proposer-candidate-v5",
            schema_version="schema-registry-v1",
            pricing_version="mvp-pricing-2026-01",
            stage="repair",
            status="in_progress",
            failure_code="LLM_PROVIDER_TIMEOUT",
            artifact_ids=[],
            artifact_checksums={},
            state_version=1,
            event_sequence=0,
            retries=3,
            transport_started=True,
            response_received=None,
            started_at=NOW,
            completed_at=None,
            created_at=NOW,
        )
    )
    attempt.checkpoint_id = checkpoint.id
    attempt.pre_fingerprint = binding.workspace_fingerprint
    continuation.status = "blocked"
    continuation.current_node = "propose_repair"
    continuation.worker_id = None
    continuation.lease_expires_at = None
    continuation.last_error_code = "REPAIR_INVOCATION_UNCERTAIN"
    continuation.last_error_message = "Repair provider transport started without a response"
    session.commit()
    session.close()
    service = RepairApplicationService(scope=_scope(factory))

    first = service.recover_uncertain_invocation(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=3,
        idempotency_key="operator-recovery-1",
        actor="operator",
        reason="First proposer recovery",
    )
    assert first["new_invocation_key"] == f"{attempt_id}:proposer:recovery-1"

    session = factory()
    successor = session.get(LlmInvocationModel, first["new_invocation_key"])
    continuation = session.get(TransformationContinuationModel, "cont-1")
    successor.transport_started = True
    successor.failure_code = "LLM_PROVIDER_TIMEOUT"
    successor.retries = 5
    continuation.status = "blocked"
    continuation.current_node = "propose_repair"
    continuation.worker_id = None
    continuation.lease_expires_at = None
    continuation.last_error_code = "REPAIR_INVOCATION_UNCERTAIN"
    continuation.last_error_message = "Repair provider transport started without a response"
    continuation.state_version += 1
    expected_state_version = continuation.state_version
    session.commit()
    session.close()

    second = service.recover_uncertain_invocation(
        run_id="run-1",
        attempt_id=attempt_id,
        expected_state_version=expected_state_version,
        idempotency_key="operator-recovery-2",
        actor="operator",
        reason="Second proposer recovery after another timeout",
    )
    assert second["idempotent_replay"] is False
    assert second["new_invocation_key"] == f"{attempt_id}:proposer:recovery-2"
    engine.dispose()


class _RetrievalTransport:
    def __init__(self, result):
        self.result = result
        self.post_calls = 0
        self.get_calls = []

    def request(self, **kwargs):
        self.post_calls += 1
        raise AssertionError("retrieval must not issue a new POST")

    def retrieve_response(self, **kwargs):
        self.get_calls.append(kwargs)
        return self.result


def _review_response_body(*, provider_response_id: str, status: str = "completed"):
    body = _responses_body(
        json.dumps(
            {
                "decision": "accept",
                "findings": [],
                "policy_checks": ["policy-ok"],
                "risk_assessment": "low",
                "required_validation_targets": ["build"],
                "limitations": [],
            }
        )
    )
    body["id"] = provider_response_id
    body["status"] = status
    return body


def _review_request(settings: Settings) -> LlmRequest:
    return LlmRequest(
        request_id="attempt:reviewer",
        run_id="run-1",
        stage_id="stage-1",
        agent_kind=AgentKind.REPAIR,
        task_type=LlmTaskType.REPAIR_REVIEW,
        role=LlmRole.REPAIR_REVIEWER,
        system_policy="Review only.",
        context=[],
        response_schema="repair_reviewer_candidate_v2",
    )


def test_synchronous_response_id_is_persistable_and_retrieval_does_not_post(tmp_path: Path):
    settings = _azure_settings(tmp_path)
    body = _review_response_body(provider_response_id="resp-1")
    transport = _RecordingTransport([ProviderTransportResult(body=body, provider_response_id="resp-1")])
    response = _gateway(transport, settings).complete(_review_request(settings))
    assert response.provider_response_id == "resp-1"

    retrieval_transport = _RetrievalTransport(
        ProviderTransportResult(body=_review_response_body(provider_response_id="resp-1"), provider_response_id="resp-1")
    )
    gateway = _gateway(retrieval_transport, settings)
    retrieved = gateway.retrieve_response(_review_request(settings), provider_response_id="resp-1")
    assert retrieved.provider_response_id == "resp-1"
    assert retrieval_transport.post_calls == 0
    assert retrieval_transport.get_calls[0]["response_id"] == "resp-1"


@pytest.mark.parametrize(
    "body, expected_subtype",
    [
        (_review_response_body(provider_response_id="resp-1", status="in_progress"), "PROVIDER_RESPONSE_PENDING"),
        ({"status": "completed", "output": []}, "PROVIDER_RESPONSE_ID_MISSING"),
        (_review_response_body(provider_response_id="other"), "PROVIDER_RESPONSE_ID_MISMATCH"),
    ],
)
def test_response_retrieval_is_fail_closed_without_duplicate_post(tmp_path: Path, body, expected_subtype):
    settings = _azure_settings(tmp_path)
    transport = _RetrievalTransport(ProviderTransportResult(body=body, provider_response_id=body.get("id")))
    gateway = _gateway(transport, settings)
    with pytest.raises(AzureGatewayError) as raised:
        gateway.retrieve_response(_review_request(settings), provider_response_id="resp-1")
    assert raised.value.failure_subtype == expected_subtype
    assert transport.post_calls == 0


def test_completed_provider_response_id_is_persisted_on_normal_reviewer_path(tmp_path: Path):
    engine, factory = _database(tmp_path)
    _store, attempt_id, _app_ts, _artifacts = _seed_service(factory, tmp_path)
    proposal_body = _responses_body(json.dumps(_proposal_candidate()))
    review_body = _responses_body(json.dumps(_review_candidate()))
    review_body["id"] = "resp-review-1"
    transport = _RecordingTransport([proposal_body, review_body])
    service = RepairApplicationService(
        scope=_scope(factory), gateway=_gateway(transport, _azure_settings(tmp_path))
    )
    service.propose(attempt_id)
    service.review(attempt_id)
    session = factory()
    reviewer = session.get(LlmInvocationModel, f"{attempt_id}:reviewer")
    assert reviewer.provider_response_id == "resp-review-1"
    session.close()
    engine.dispose()
