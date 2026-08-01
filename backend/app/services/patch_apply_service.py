"""Deterministic application of one checksum-bound, human-approved repair."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from contextlib import ExitStack, contextmanager
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

_workspace_lock_guard = threading.Lock()
_workspace_locks: dict[str, threading.RLock] = {}
_workspace_lock_state = threading.local()


@contextmanager
def workspace_apply_lock(workspace: Path):
    """Serialize repair filesystem verification/mutation per workspace."""
    import msvcrt

    key = str(workspace.resolve())
    held = getattr(_workspace_lock_state, "held", set())
    if key in held:
        yield
        return
    with _workspace_lock_guard:
        lock = _workspace_locks.setdefault(key, threading.RLock())
    with lock:
        lock_path = workspace.parent / f".{workspace.name}.transformer-repair.apply.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        try:
            os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            held.add(key)
            _workspace_lock_state.held = held
            yield
        finally:
            held.discard(key)
            _workspace_lock_state.held = held
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            os.close(fd)


@contextmanager
def _target_apply_lock(target: Path):
    """Hold an OS file lock while checking and changing one target."""
    import msvcrt

    if target.exists():
        fd = os.open(target, os.O_RDWR | getattr(os, "O_BINARY", 0))
        lock_path = target
    else:
        lock_path = target.with_name(f".{target.name}.transformer-repair.target.lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        os.lseek(fd, 0, os.SEEK_SET)
        yield fd, lock_path is target
    finally:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        os.close(fd)


def _fingerprint_with_locked_targets(root: Path, locked_targets: dict[str, tuple[int, bool]]) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative_path = path.relative_to(root).as_posix()
        relative = relative_path.encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        locked = locked_targets.get(relative_path)
        if locked is None or not locked[1]:
            content = path.read_bytes()
        else:
            fd = locked[0]
            os.lseek(fd, 0, os.SEEK_SET)
            content = os.read(fd, os.fstat(fd).st_size)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


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
        mutation_started_callback=None,
    ):
        workspace = Path(workspace_path).resolve(strict=True)
        with workspace_apply_lock(workspace):
            return self._apply_locked(
                proposal=proposal,
                workspace=workspace,
                expected_fingerprint=expected_fingerprint,
                run_id=run_id,
                stage_id=stage_id,
                artifact_root=artifact_root,
                attempt_id=attempt_id,
                approved_proposal_checksum=approved_proposal_checksum,
                proposal_artifact_checksum=proposal_artifact_checksum,
                mutation_started_callback=mutation_started_callback,
            )

    def _apply_locked(
        self,
        *,
        proposal,
        workspace,
        expected_fingerprint,
        run_id,
        stage_id,
        artifact_root,
        attempt_id,
        approved_proposal_checksum,
        proposal_artifact_checksum,
        mutation_started_callback,
    ):
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
        originals = {
            change["path"]: (workspace / change["path"]).read_bytes()
            for change in changes
            if (workspace / change["path"]).is_file()
        }
        with ExitStack() as target_locks:
            locked_targets = {}
            for change in changes:
                target = workspace / change["path"]
                if not target.parent.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                locked_targets.setdefault(
                    change["path"], target_locks.enter_context(_target_apply_lock(target))
                )
            try:
                mutation_started = False
                for change in changes:
                    target = workspace / change["path"]
                    target_fd, target_exists = locked_targets[change["path"]]
                    expected = change.get("preimage_sha256")
                    if expected == "absent":
                        if target.exists():
                            raise RepairApplicationError("REPAIR_PREIMAGE_STALE", "Repair create target appeared before mutation")
                        if not mutation_started and mutation_started_callback is not None:
                            mutation_started_callback()
                            mutation_started = True
                        try:
                            fd = os.open(
                                target,
                                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                            )
                        except FileExistsError as error:
                            raise RepairApplicationError("REPAIR_PREIMAGE_STALE", "Repair create target appeared before mutation") from error
                        with os.fdopen(fd, "w", encoding="utf-8", newline="") as created:
                            created.write(change["content"])
                    else:
                        if not target_exists:
                            raise RepairApplicationError("REPAIR_PREIMAGE_STALE", "Repair target disappeared before mutation")
                        os.lseek(target_fd, 0, os.SEEK_SET)
                        current_bytes = os.read(target_fd, os.fstat(target_fd).st_size)
                        actual = "sha256:" + hashlib.sha256(current_bytes).hexdigest()
                        if actual != expected:
                            raise RepairApplicationError("REPAIR_PREIMAGE_STALE", "Repair preimage changed before mutation")
                        if not mutation_started and mutation_started_callback is not None:
                            mutation_started_callback()
                            mutation_started = True
                        if change["action"] == "delete":
                            target.unlink()
                        else:
                            encoded = change["content"].encode("utf-8")
                            os.lseek(target_fd, 0, os.SEEK_SET)
                            os.ftruncate(target_fd, 0)
                            os.write(target_fd, encoded)
                    if change["action"] == "delete":
                        postimage = "deleted"
                    elif expected == "absent":
                        postimage = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
                    else:
                        os.lseek(target_fd, 0, os.SEEK_SET)
                        postimage = "sha256:" + hashlib.sha256(
                            os.read(target_fd, os.fstat(target_fd).st_size)
                        ).hexdigest()
                    prepared["operations"].append(
                        {
                            "path": change["path"],
                            "action": change["action"],
                            "postimage_sha256": postimage,
                        }
                    )
                prepared["post_fingerprint"] = _fingerprint_with_locked_targets(
                    workspace, locked_targets
                )
                prepared["status"] = "applied"
                final = self._write(store, run_id, stage_id, attempt_id, "applied", prepared)
            except Exception:
                for change in changes:
                    target = workspace / change["path"]
                    original = originals.get(change["path"])
                    if original is None:
                        if target.exists():
                            target.unlink()
                    elif target.exists():
                        target_fd, _ = locked_targets[change["path"]]
                        os.lseek(target_fd, 0, os.SEEK_SET)
                        os.ftruncate(target_fd, 0)
                        os.write(target_fd, original)
                    else:
                        temporary = target.with_name(f".{target.name}.repair-rollback-{uuid4().hex[:12]}")
                        temporary.write_bytes(original)
                        os.replace(temporary, target)
                raise
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
                changes.append({"path": item["path"], "action": "write", "content": item["content"], "preimage_sha256": "absent"})
                continue
            if not target.is_file():
                raise RepairApplicationError("REPAIR_PREIMAGE_INVALID", "Repair target is missing")
            actual = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != item["preimage_sha256"]:
                raise RepairApplicationError("REPAIR_PREIMAGE_STALE", "Repair preimage changed")
            current = target.read_text(encoding="utf-8")
            if action == "delete_text_file":
                changes.append({"path": item["path"], "action": "delete", "content": "", "preimage_sha256": actual})
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
                        "preimage_sha256": actual,
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
            changes.append({
                "path": relative,
                "action": "write",
                "content": "".join(output),
                "preimage_sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
            })
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
