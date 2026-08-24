import hashlib
import json
from pathlib import Path

import pytest

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.transformation import FailureRoute
from app.services.failure_evidence_service import (
    CONTEXT_PACK_FILES,
    CONTEXT_PACK_MAX_BYTES_PER_FILE,
    CONTEXT_PACK_MAX_FILES,
    CONTEXT_PACK_MAX_TOTAL_BYTES,
    CONTEXT_PACK_SCHEMA_VERSION,
    FailureEvidenceService,
    validate_context_pack,
)
from app.services.failure_evidence_service import _failure_matches_current_route
from app.services import repair_application_service
from app.services.repair_application_service import RepairApplicationError, RepairApplicationService


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("REGISTRY_TIMEOUT", FailureRoute.ENVIRONMENT_TRANSIENT),
        ("EXECUTION_PROFILE_NOT_FOUND", FailureRoute.ENVIRONMENT_PERMANENT),
        ("DEPENDENCY_PREFLIGHT_BLOCKED", FailureRoute.DEPENDENCY_INCOMPATIBLE),
        ("UNEXPECTED_PROMPT", FailureRoute.UNEXPECTED_PROMPT),
        ("VALIDATION_WORKSPACE_MUTATED", FailureRoute.POLICY_VIOLATION),
        ("VALIDATION_EVIDENCE_MISSING", FailureRoute.NON_REPAIRABLE_VALIDATION),
        ("COMPILATION_FAILED", FailureRoute.REPAIRABLE_SOURCE),
    ],
)
def test_classifier_has_closed_deterministic_routes(code, expected):
    evidence = {
        "normalized_failure": {"error_code": code},
        "failure_fingerprint": "sha256:new",
        "prior_fingerprints": [],
    }

    assert FailureEvidenceService().classify(evidence) == expected


def test_chrome_binary_failure_is_environment_transient():
    evidence = {
        "normalized_failure": {
            "error_code": "COMMAND_EXIT_NONZERO",
            "failure_message": (
                'No binary for Chrome browser on your platform. '
                'Please, set "CHROME_BIN" env variable.'
            ),
        },
        "failure_fingerprint": "sha256:chrome",
        "prior_fingerprints": [],
    }

    assert FailureEvidenceService().classify(evidence) == FailureRoute.ENVIRONMENT_TRANSIENT


def test_environment_route_preserves_command_failure_binding():
    assert _failure_matches_current_route(
        "FAILURE_ROUTE_ENVIRONMENT_TRANSIENT", "COMMAND_EXIT_NONZERO"
    )
    assert _failure_matches_current_route(
        "CAUSAL_EXECUTION_AMBIGUOUS", "COMMAND_EXIT_NONZERO"
    )


def test_identical_failure_is_no_progress():
    evidence = {
        "normalized_failure": {"error_code": "COMPILATION_FAILED"},
        "failure_fingerprint": "sha256:same",
        "prior_fingerprints": ["sha256:same"],
    }

    assert FailureEvidenceService().classify(evidence) == FailureRoute.NO_PROGRESS


FINGERPRINT = "sha256:" + "c" * 64


def _evidence(tmp_path: Path) -> dict[str, object]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return {
        "schema_version": "transformer-failure-evidence-v1",
        "run_id": "run-1",
        "stage_id": "stage-1",
        "stage_plan_checksum": "sha256:stage-plan",
        "workspace_path": str(workspace),
        "workspace_fingerprint": "sha256:workspace",
        "artifact_root": str(tmp_path / "artifacts"),
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


def _write_pack(tmp_path: Path, evidence: dict[str, object], **bounds):
    context = FailureEvidenceService().write_context_pack(evidence, "sha256:failure", **bounds)
    store = LocalFilesystemArtifactStore(
        Path(str(evidence["artifact_root"])).parent,
        fixed_run_root=Path(str(evidence["artifact_root"])),
    )
    stored = store.read_artifact(str(evidence["run_id"]), context.ref.relative_path)
    return json.loads(stored.content), stored.content


def test_oversized_file_becomes_checksum_only_entry_with_truncation_flag(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    oversized = b"p" * (CONTEXT_PACK_MAX_BYTES_PER_FILE + 1)
    (workspace / "package.json").write_bytes(oversized)
    (workspace / "angular.json").write_text('{"a": 1}', encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence)

    assert pack["bounds"]["max_bytes_per_file"] == CONTEXT_PACK_MAX_BYTES_PER_FILE
    entry = pack["file_excerpts"]["package.json"]
    assert entry["truncated"] is True
    assert entry["content"] is None
    assert entry["size_bytes"] == len(oversized)
    assert entry["sha256"] == "sha256:" + hashlib.sha256(oversized).hexdigest()
    assert pack["bounds"]["truncated"] == ["package.json"]
    assert pack["bounds"]["included_bytes"] == len(b'{"a": 1}')
    small = pack["file_excerpts"]["angular.json"]
    assert small["truncated"] is False
    assert small["content"] == '{"a": 1}'
    assert small["sha256"] == "sha256:" + hashlib.sha256(b'{"a": 1}').hexdigest()


def test_binary_file_is_checksum_only_entry_with_full_preimage(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    binary = b"\xff\xfebinary"
    (workspace / "package.json").write_bytes(binary)

    pack, _ = _write_pack(tmp_path, evidence)

    entry = pack["file_excerpts"]["package.json"]
    assert entry["truncated"] is True
    assert entry["content"] is None
    assert entry["size_bytes"] == len(binary)
    assert entry["sha256"] == "sha256:" + hashlib.sha256(binary).hexdigest()
    assert pack["bounds"]["truncated"] == ["package.json"]


def test_max_files_keeps_budget_ordered_subset_and_records_omitted(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    for name in CONTEXT_PACK_FILES:
        (workspace / name).write_text(f'{{"file": "{name}"}}', encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence, max_files=2)

    assert list(pack["file_excerpts"].keys()) == ["angular.json", "package.json"]
    assert pack["bounds"]["max_files"] == 2
    assert pack["bounds"]["omitted"] == ["tsconfig.json"]
    assert pack["bounds"]["truncated"] == []


def test_total_byte_budget_omits_remaining_excerpts_and_records_omitted(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    for name in CONTEXT_PACK_FILES:
        (workspace / name).write_text("x" * 50, encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence, max_total_bytes=110)

    assert list(pack["file_excerpts"].keys()) == ["angular.json", "package.json"]
    assert pack["bounds"]["included_bytes"] == 100
    assert pack["bounds"]["omitted"] == ["tsconfig.json"]
    assert pack["bounds"]["max_total_bytes"] == 110


def test_deterministic_pack_bytes_for_identical_workspaces(tmp_path: Path):
    first = _evidence(tmp_path / "first")
    second = _evidence(tmp_path / "second")
    for evidence, order in ((first, reversed(CONTEXT_PACK_FILES)), (second, CONTEXT_PACK_FILES)):
        workspace = Path(str(evidence["workspace_path"]))
        for name in order:
            (workspace / name).write_text(f'{{"file": "{name}"}}', encoding="utf-8")

    _, first_content = _write_pack(tmp_path / "first", first)
    _, second_content = _write_pack(tmp_path / "second", second)

    assert first_content == second_content


def test_entry_preimage_matches_file_content_exactly(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    content = '{"name": "fixture"}'
    (workspace / "package.json").write_text(content, encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence)

    entry = pack["file_excerpts"]["package.json"]
    assert entry["size_bytes"] == len(content.encode("utf-8"))
    assert entry["sha256"] == "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert entry["content"] == content


def test_bounds_block_records_limits_and_omission_accounting(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    for name in CONTEXT_PACK_FILES:
        (workspace / name).write_text(f'{{"file": "{name}"}}', encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence)

    assert pack["schema_version"] == CONTEXT_PACK_SCHEMA_VERSION
    assert pack["bounds"] == {
        "max_files": CONTEXT_PACK_MAX_FILES,
        "max_bytes_per_file": CONTEXT_PACK_MAX_BYTES_PER_FILE,
        "max_total_bytes": CONTEXT_PACK_MAX_TOTAL_BYTES,
        "included_bytes": sum(
            len(f'{{"file": "{name}"}}'.encode("utf-8")) for name in CONTEXT_PACK_FILES
        ),
        "truncated": [],
        "omitted": [],
    }
    assert list(pack["file_excerpts"].keys()) == sorted(CONTEXT_PACK_FILES)


def test_normal_workspace_pack_keeps_existing_top_level_shape(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    (workspace / "package.json").write_text('{"name": "fixture"}', encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence)

    assert pack["schema_version"] == "repair-context-pack-v1"
    assert pack["failure_evidence_checksum"] == "sha256:failure"
    assert pack["failure_fingerprint"] == FINGERPRINT
    assert pack["workspace_fingerprint"] == "sha256:workspace"
    assert pack["normalized_failure"] == evidence["normalized_failure"]
    assert pack["forbidden_change_policy"] == {}
    assert pack["untrusted"] is True
    for name, entry in pack["file_excerpts"].items():
        assert set(entry) == {"path", "sha256", "size_bytes", "truncated", "content"}
        assert entry["path"] == name


def test_validate_context_pack_rejects_wrong_preimage_claim(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    (workspace / "package.json").write_text('{"name": "fixture"}', encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence)
    pack["file_excerpts"]["package.json"]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="preimage checksum mismatch"):
        validate_context_pack(pack)


def test_validate_context_pack_rejects_unsorted_entries(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    for name in CONTEXT_PACK_FILES:
        (workspace / name).write_text(f'{{"file": "{name}"}}', encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence)
    items = list(pack["file_excerpts"].items())
    pack["file_excerpts"] = dict(reversed(items))
    with pytest.raises(ValueError, match="not sorted by path"):
        validate_context_pack(pack)


def test_validate_context_pack_rejects_missing_bounds_block(tmp_path: Path):
    evidence = _evidence(tmp_path)
    (workspace := Path(str(evidence["workspace_path"]))).mkdir(parents=True, exist_ok=True)
    (workspace / "package.json").write_text('{"name": "fixture"}', encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence)
    del pack["bounds"]
    with pytest.raises(ValueError, match="bounds block is missing"):
        validate_context_pack(pack)


def test_validate_context_pack_rejects_budget_overflow(tmp_path: Path):
    evidence = _evidence(tmp_path)
    workspace = Path(str(evidence["workspace_path"]))
    (workspace / "package.json").write_text("x" * 50, encoding="utf-8")

    pack, _ = _write_pack(tmp_path, evidence)
    pack["bounds"]["max_total_bytes"] = 25
    with pytest.raises(ValueError, match="total byte budget"):
        validate_context_pack(pack)


def test_npm_eresolve_peer_diagnosis_parses_unscoped_causal_package_and_quoted_range():
    normalized = {
        "command_id": "npm-lockfile-generate",
        "failure_message": (
            "npm error code ERESOLVE\n"
            'npm error peer blocking-package@">=1.0.0 <2.0.0" '
            "from causal-package@3.4.5"
        ),
    }

    diagnosis = FailureEvidenceService.diagnose_angular_update_failure(normalized)

    assert diagnosis == {
        "kind": "peer_dependency_conflict",
        "source": "npm_eresolve_peer_conflict",
        "package": "causal-package",
        "blocking_dependency": "blocking-package",
        "package_version": "3.4.5",
        "required_peer_range": ">=1.0.0 <2.0.0",
        "installed_version": None,
        "required_ranges": {"blocking-package": ">=1.0.0 <2.0.0"},
        "proposed_angular_version": None,
    }


@pytest.mark.parametrize(
    ("blocking", "causal"),
    [
        ("@scope/blocking-package", "causal-package"),
        ("blocking-package", "@scope/causal-package"),
    ],
)
def test_npm_eresolve_peer_diagnosis_parses_scoped_package_names(blocking: str, causal: str):
    normalized = {
        "command_id": "npm-lockfile-generate",
        "failure_message": (
            "npm error code ERESOLVE\n"
            f'npm error peer {blocking}@"^4.0.0 <5.0.0" '
            f"from {causal}@6.7.8"
        ),
    }

    diagnosis = FailureEvidenceService.diagnose_angular_update_failure(normalized)

    assert diagnosis is not None
    assert diagnosis["package"] == causal
    assert diagnosis["blocking_dependency"] == blocking
    assert diagnosis["package_version"] == "6.7.8"
    assert diagnosis["required_peer_range"] == "^4.0.0 <5.0.0"
    assert diagnosis["required_ranges"] == {blocking: "^4.0.0 <5.0.0"}


def test_existing_angular_cli_peer_diagnosis_remains_unchanged():
    normalized = {
        "command_id": "angular-update-exact",
        "failure_message": (
            'Package "blocking-package" has an incompatible peer dependency to '
            '"@angular-devkit/build-angular" (requires ">=13.0.0 <18.0.0", '
            'would install ">=21.0.0")'
        ),
    }

    diagnosis = FailureEvidenceService.diagnose_angular_update_failure(normalized)

    assert diagnosis == {
        "kind": "peer_dependency_conflict",
        "package": "blocking-package",
        "installed_version": None,
        "required_ranges": {"@angular-devkit/build-angular": ">=13.0.0 <18.0.0"},
        "proposed_angular_version": ">=21.0.0",
    }


def test_malformed_npm_eresolve_peer_diagnosis_fails_closed():
    normalized = {
        "command_id": "npm-lockfile-generate",
        "failure_message": 'npm error peer @scope/blocking@">=1.0.0" from incomplete',
    }

    assert FailureEvidenceService.diagnose_angular_update_failure(normalized) is None


def test_multiple_npm_eresolve_diagnostics_choose_first_complete_record_deterministically():
    normalized = {
        "command_id": "npm-lockfile-generate",
        "failure_message": (
            "npm error code ERESOLVE\n"
            'npm error peer first-blocking@">=1.0.0 <2.0.0" from first-causal@1.2.3\n'
            'npm error peer second-blocking@">=3.0.0 <4.0.0" from second-causal@5.6.7'
        ),
    }

    first = FailureEvidenceService.diagnose_angular_update_failure(normalized)
    second = FailureEvidenceService.diagnose_angular_update_failure(normalized)

    assert first == second
    assert first["package"] == "first-causal"
    assert first["blocking_dependency"] == "first-blocking"


def test_dependency_transition_still_rejects_unproven_npm_package(tmp_path: Path):
    service = RepairApplicationService.__new__(RepairApplicationService)
    context = {
        "checkpoint_id": "checkpoint-1",
        "target_exact": "21.0.0",
        "workspace_path": str(tmp_path),
        "failure_evidence_artifact_id": "artifact-failure",
        "segments": [
            json.dumps(
                {
                    "execution_id": "execution-1",
                    "normalized_failure": {
                        "command_id": "npm-lockfile-generate",
                        "exit_code": 1,
                        "failure_message": (
                            "npm error code ERESOLVE\n"
                            "npm error peer @scope/blocking@\">=1.0.0\" from incomplete"
                        ),
                    },
                }
            )
        ],
    }

    with pytest.raises(RepairApplicationError) as raised:
        service._bind_dependency_transition(
            {"operations": [{"operation": "dependency_transition"}]},
            context,
        )

    assert raised.value.code == "REPAIR_DEPENDENCY_EVIDENCE_INVALID"


def test_unproven_dependency_transition_is_bounded_semantic_retry():
    assert "REPAIR_DEPENDENCY_EVIDENCE_INVALID" in repair_application_service._SEMANTIC_RETRY_CODES
    feedback = repair_application_service._semantic_retry_feedback(
        "REPAIR_DEPENDENCY_EVIDENCE_INVALID",
        "field=normalized_failure.failure_diagnosis.package; observed=null",
    )

    assert "does not prove an Angular peer-dependency conflict" in feedback
    assert "smallest causal source or configuration repair" in feedback
