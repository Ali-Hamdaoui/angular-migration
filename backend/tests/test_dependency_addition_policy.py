"""Focused tests for the dependency_add version-spec policy and post-state verification.

The dependency_add operation binds the LLM's requested registry semver spec as
the approved version spec (no static exact-version authority lookup). The exact
resolved version is observed from the governed lockfile after npm resolution,
never predeclared in Python.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.dependency_closure_service import verify_dependency_add_state
from app.services.dependency_addition_policy import (
    DependencyAdditionIntent,
    DependencyAdditionPolicy,
    DependencyAdditionPolicyError,
)
from app.services.repair_application_service import (
    RepairApplicationError,
    RepairApplicationService,
)


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


def _dependency_add_proposal(package_json: Path, *, new_version: str) -> dict:
    checksum = "sha256:" + hashlib.sha256(package_json.read_bytes()).hexdigest()
    return {
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "proposal_format": "operations",
        "operations": [
            {
                "operation": "dependency_add",
                "path": "package.json",
                "preimage_sha256": checksum,
                "section": "devDependencies",
                "package": "jest-environment-jsdom",
                "new_version": new_version,
            }
        ],
        "unified_diff": None,
        "touched_files": ["package.json"],
        "rationale": ["Add the missing test environment package."],
        "risk_level": "low",
        "validation_targets": ["test"],
        "limitations": [],
    }


def _add_context(tmp_path: Path) -> dict:
    return {
        "workspace_path": str(tmp_path),
        "workspace_binding_alias": "STAGE_WORKSPACE_1",
        "failure_evidence_checksum": "sha256:failure",
        "context_pack_checksum": "sha256:context",
        "stage_plan_commands": _lockfile_generation_commands(),
    }


def test_dependency_add_absent_preserves_approved_version_spec(tmp_path: Path):
    manifest = tmp_path / "package.json"
    manifest.write_text('{"name":"fixture","devDependencies":{}}', encoding="utf-8")
    service = RepairApplicationService(scope=None)

    result = service.validate_proposal(
        _dependency_add_proposal(manifest, new_version="^30.0.0"),
        _add_context(tmp_path),
    )

    operation = result["operations"][0]
    assert operation["operation"] == "dependency_add"
    assert operation["new_version"] == "^30.0.0"
    provenance = {entry["key"]: entry["value"] for entry in operation["provenance"]}
    assert provenance["llm_requested_version"] == "^30.0.0"
    assert provenance["policy_version"] == "dependency-addition-policy-v1"
    bound_manifest = json.loads(operation["new_text"])
    assert bound_manifest["devDependencies"]["jest-environment-jsdom"] == "^30.0.0"


def test_dependency_add_already_present_fails_closed(tmp_path: Path):
    manifest = tmp_path / "package.json"
    manifest.write_text(
        '{"name":"fixture","devDependencies":{"jest-environment-jsdom":"30.4.1"}}',
        encoding="utf-8",
    )
    service = RepairApplicationService(scope=None)

    with pytest.raises(RepairApplicationError) as error:
        service.validate_proposal(
            _dependency_add_proposal(manifest, new_version="^30.0.0"),
            _add_context(tmp_path),
        )
    assert error.value.code == "REPAIR_DEPENDENCY_ALREADY_PRESENT"


@pytest.mark.parametrize(
    "unsafe_spec",
    [
        "file:../foo",
        "https://registry.example.com/pkg.tgz",
        "workspace:*",
        "latest",
        "next",
    ],
)
def test_dependency_add_rejects_non_registry_specs(tmp_path: Path, unsafe_spec: str):
    manifest = tmp_path / "package.json"
    manifest.write_text('{"name":"fixture","devDependencies":{}}', encoding="utf-8")
    service = RepairApplicationService(scope=None)

    with pytest.raises(RepairApplicationError) as error:
        service.validate_proposal(
            _dependency_add_proposal(manifest, new_version=unsafe_spec),
            _add_context(tmp_path),
        )
    assert error.value.code == "REPAIR_DEPENDENCY_VERSION_INVALID"


def _write_post_state(
    workspace: Path,
    *,
    manifest_spec: str,
    lock_spec: str,
    lock_resolved: str,
    installed: str,
) -> None:
    (workspace / "package.json").write_text(
        json.dumps({"name": "fixture", "devDependencies": {"jest-environment-jsdom": manifest_spec}}),
        encoding="utf-8",
    )
    (workspace / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"devDependencies": {"jest-environment-jsdom": lock_spec}},
                    "node_modules/jest-environment-jsdom": {"version": lock_resolved},
                },
            }
        ),
        encoding="utf-8",
    )
    installed_dir = workspace / "node_modules" / "jest-environment-jsdom"
    installed_dir.mkdir(parents=True)
    (installed_dir / "package.json").write_text(
        json.dumps({"name": "jest-environment-jsdom", "version": installed}),
        encoding="utf-8",
    )


def test_dependency_add_verification_agrees_on_observed_exact_version(tmp_path: Path):
    _write_post_state(
        tmp_path,
        manifest_spec="^30.0.0",
        lock_spec="^30.0.0",
        lock_resolved="30.4.1",
        installed="30.4.1",
    )

    report = verify_dependency_add_state(
        tmp_path,
        package="jest-environment-jsdom",
        section="devDependencies",
        approved_version_spec="^30.0.0",
    )

    assert report["agreement"] is True
    assert report["approved_version_spec"] == "^30.0.0"
    assert report["manifest_value"] == "^30.0.0"
    assert report["lockfile_manifest_value"] == "^30.0.0"
    assert report["resolved_exact_version"] == "30.4.1"
    assert report["installed_version"] == "30.4.1"
    assert report["violations"] == []


def test_dependency_add_verification_fails_closed_on_lock_installed_mismatch(tmp_path: Path):
    _write_post_state(
        tmp_path,
        manifest_spec="^30.0.0",
        lock_spec="^30.0.0",
        lock_resolved="30.4.1",
        installed="30.4.2",
    )

    report = verify_dependency_add_state(
        tmp_path,
        package="jest-environment-jsdom",
        section="devDependencies",
        approved_version_spec="^30.0.0",
    )

    assert report["agreement"] is False
    assert report["resolved_exact_version"] == "30.4.1"
    assert report["installed_version"] == "30.4.2"
    assert any("expected lockfile resolved version" in violation for violation in report["violations"])


def test_dependency_add_policy_validates_intent_never_resolves_version():
    intent = DependencyAdditionPolicy().validate(
        package="@angular/core",
        section="dependencies",
        version_spec=">=19.0.0 <20.0.0",
    )
    assert isinstance(intent, DependencyAdditionIntent)
    assert intent.version_spec == ">=19.0.0 <20.0.0"

    with pytest.raises(DependencyAdditionPolicyError):
        DependencyAdditionPolicy().validate(
            package="../escape",
            section="dependencies",
            version_spec="^1.0.0",
        )
