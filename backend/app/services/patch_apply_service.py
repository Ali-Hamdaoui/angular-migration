"""Deterministic application of one checksum-bound, human-approved repair."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.services.repair_application_service import (
    RepairApplicationError,
    _unified_diff_header_path,
)
from app.services.stage_preparation_primitives import StageSandboxCopier


class PatchApplyService:
    hunk = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    def __init__(self, *, now_provider=None) -> None:
        self._now = now_provider or (lambda: datetime.now(UTC))

    def apply(
        self,
        *,
        proposal: dict[str, object],
        workspace_path: str,
        expected_fingerprint: str,
        run_id: str,
        stage_id: str,
        artifact_root: str,
        attempt_id: str,
        approved_proposal_checksum: str | None = None,
        proposal_artifact_checksum: str | None = None,
    ):
        workspace = Path(workspace_path).resolve(strict=True)
        if (
            approved_proposal_checksum is not None
            and proposal_artifact_checksum != approved_proposal_checksum
        ):
            raise RepairApplicationError("REPAIR_PROPOSAL_STALE", "Approved repair proposal checksum changed")
        if StageSandboxCopier.fingerprint(workspace) != expected_fingerprint:
            raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Repair workspace fingerprint changed")
        prepared = {
            "schema_version": "repair-apply-ledger-v1",
            "attempt_id": attempt_id,
            "proposal_checksum": self._checksum(proposal),
            "pre_fingerprint": expected_fingerprint,
            "status": "prepared",
            "operations": [],
        }
        store = LocalFilesystemArtifactStore(
            Path(artifact_root).parent, fixed_run_root=Path(artifact_root)
        )
        prepared_artifact = self._write(store, run_id, stage_id, attempt_id, "prepared", prepared)
        changes = (
            self._prepare_operations(proposal["operations"], workspace)
            if proposal["proposal_format"] == "operations"
            else self._prepare_unified_diff(str(proposal["unified_diff"]), workspace)
        )
        for change in changes:
            target = workspace / change["path"]
            if change["action"] == "delete":
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.repair-{uuid4().hex[:12]}")
                temporary.write_text(change["content"], encoding="utf-8", newline="")
                os.replace(temporary, target)
            prepared["operations"].append(
                {
                    "path": change["path"],
                    "action": change["action"],
                    "postimage_sha256": (
                        "deleted"
                        if change["action"] == "delete"
                        else "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
                    ),
                }
            )
        prepared["post_fingerprint"] = StageSandboxCopier.fingerprint(workspace)
        prepared["status"] = "applied"
        final = self._write(store, run_id, stage_id, attempt_id, "applied", prepared)
        return prepared_artifact, final, prepared["post_fingerprint"]

    def _prepare_operations(self, operations, workspace: Path):
        changes = []
        for item in operations:
            target = (workspace / item["path"]).resolve(strict=False)
            target.relative_to(workspace)
            if target.exists() and target.is_symlink():
                raise RepairApplicationError("REPAIR_SYMLINK_FORBIDDEN", "Repair target is a symlink")
            action = item["operation"]
            if action == "create_text_file":
                changes.append({"path": item["path"], "action": "write", "content": item["content"]})
                continue
            if not target.is_file():
                raise RepairApplicationError("REPAIR_PREIMAGE_INVALID", "Repair target is missing")
            actual = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != item["preimage_sha256"]:
                raise RepairApplicationError("REPAIR_PREIMAGE_STALE", "Repair preimage changed")
            current = target.read_text(encoding="utf-8")
            if action == "delete_text_file":
                changes.append({"path": item["path"], "action": "delete", "content": ""})
            else:
                old = item["old_text"]
                if current.count(old) != 1:
                    raise RepairApplicationError(
                        "REPAIR_REPLACEMENT_AMBIGUOUS",
                        "Replacement preimage must occur exactly once",
                    )
                changes.append(
                    {
                        "path": item["path"],
                        "action": "write",
                        "content": current.replace(old, item["new_text"], 1),
                    }
                )
        return changes

    def _prepare_unified_diff(self, diff: str, workspace: Path):
        lines = diff.splitlines(keepends=True)
        changes = []
        index = 0
        while index < len(lines):
            if not lines[index].startswith("--- "):
                index += 1
                continue
            old_name = _unified_diff_header_path(lines[index], "a/")
            index += 1
            if index >= len(lines) or not lines[index].startswith("+++ "):
                raise RepairApplicationError("REPAIR_DIFF_INVALID", "Unified diff header is incomplete")
            new_name = _unified_diff_header_path(lines[index], "b/")
            relative = new_name if new_name != "/dev/null" else old_name
            if relative.startswith("/") or ".." in Path(relative).parts:
                raise RepairApplicationError("REPAIR_PATH_ESCAPE", "Unified diff path escapes workspace")
            target = (workspace / relative).resolve(strict=True)
            target.relative_to(workspace)
            original = target.read_text(encoding="utf-8").splitlines(keepends=True)
            output = []
            source_cursor = 0
            index += 1
            while index < len(lines):
                if lines[index].startswith("diff --git "):
                    break
                match = self.hunk.match(lines[index])
                if not match:
                    if lines[index].startswith("--- "):
                        if index + 1 < len(lines) and lines[index + 1].startswith("+++ "):
                            break
                        raise RepairApplicationError(
                            "REPAIR_DIFF_INVALID", "Unified diff header is incomplete"
                        )
                    if lines[index].startswith("+++ "):
                        raise RepairApplicationError(
                            "REPAIR_DIFF_INVALID", "Unified diff header is incomplete"
                        )
                    index += 1
                    continue
                start = int(match.group(1)) - 1
                old_remaining = int(match.group(2) or 1)
                new_remaining = int(match.group(4) or 1)
                output.extend(original[source_cursor:start])
                source_cursor = start
                index += 1
                while index < len(lines) and (old_remaining or new_remaining):
                    line = lines[index]
                    if line.startswith(" "):
                        if source_cursor >= len(original) or original[source_cursor].rstrip("\r\n") != line[1:].rstrip("\r\n"):
                            raise RepairApplicationError(
                                "REPAIR_DIFF_STALE", "Unified diff context no longer matches"
                            )
                        output.append(original[source_cursor])
                        source_cursor += 1
                        old_remaining -= 1
                        new_remaining -= 1
                    elif line.startswith("-"):
                        if source_cursor >= len(original) or original[source_cursor].rstrip("\r\n") != line[1:].rstrip("\r\n"):
                            raise RepairApplicationError(
                                "REPAIR_DIFF_STALE", "Unified diff removal no longer matches"
                            )
                        source_cursor += 1
                        old_remaining -= 1
                    elif line.startswith("+"):
                        output.append(line[1:])
                        new_remaining -= 1
                    elif not line.startswith("\\"):
                        raise RepairApplicationError("REPAIR_DIFF_INVALID", "Unified diff line is invalid")
                    index += 1
                if old_remaining or new_remaining:
                    raise RepairApplicationError("REPAIR_DIFF_INVALID", "Unified diff hunk is incomplete")
            output.extend(original[source_cursor:])
            changes.append({"path": relative, "action": "write", "content": "".join(output)})
        if not changes:
            raise RepairApplicationError("REPAIR_DIFF_INVALID", "Unified diff contains no file changes")
        return changes

    def _write(self, store, run_id, stage_id, attempt_id, suffix, payload):
        return store.write_text_artifact(
            run_id,
            f"05_repairs/attempt-{attempt_id}/apply-{suffix}.json",
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=stage_id,
            created_by="patch-apply-service",
            created_at=self._now(),
            input_hashes={"proposal": str(payload["proposal_checksum"])},
            policy_version="repair-apply-ledger-v1",
        )

    @staticmethod
    def _checksum(value) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
