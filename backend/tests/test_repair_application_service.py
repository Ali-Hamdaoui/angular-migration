import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.repair_application_service import (
    RepairApplicationError,
    RepairApplicationService,
    RepairReview,
)


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


def test_reviewer_schema_cannot_author_candidate_content():
    with pytest.raises(ValidationError):
        RepairReview.model_validate(
            {
                "proposal_checksum": "sha256:proposal",
                "decision": "accept",
                "findings": [],
                "policy_checks": ["paths"],
                "risk_assessment": "low",
                "required_validation_targets": ["build"],
                "limitations": [],
                "operations": [{"operation": "replace_text"}],
            }
        )


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
