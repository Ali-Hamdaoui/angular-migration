"""Deterministic application of one checksum-bound, human-approved repair.

The apply ledger binds the exact approved proposal ARTIFACT checksum
(``proposal_artifact_checksum``, taken by callers from
``RepairAttemptModel.proposal_checksum`` / the stored proposal artifact bytes)
so the ledger identifies the very bytes that were human-approved. When no
artifact checksum is supplied (direct service use), the ledger falls back to
the canonical re-encoding of the proposal dict (``json.dumps(..., sort_keys=True,
separators=(",", ":"))``). The stored-artifact checksum and the canonical
re-encoding are intentionally distinct checksums: they serialize the same
object with different separators/indentation, and no consumer compares the two.
The fallback exists only to give unbound ledger writes a stable identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import tempfile
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
from app.services.workspace_fingerprint import STAGE_FINGERPRINT_PROFILE

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
def _target_namespace_lock(target: Path):
    import msvcrt

    key = hashlib.sha256(str(target.resolve()).encode()).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / f"transformer-repair-target-{key}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        os.lseek(fd, 0, os.SEEK_SET)
        yield
    finally:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        os.close(fd)


@contextmanager
def _target_inode_lock(target: Path):
    import msvcrt

    if not target.exists():
        yield None, False
        return
    fd = os.open(target, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        os.lseek(fd, 0, os.SEEK_SET)
        yield fd, True
    finally:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        os.close(fd)


@contextmanager
def _target_apply_lock(target: Path, *, lock_inode: bool = True):
    """Hold the target namespace and current inode locks together."""
    with _target_namespace_lock(target):
        if lock_inode:
            with _target_inode_lock(target) as locked:
                yield locked
        else:
            yield (None, target.exists())


def _workspace_manifest(root: Path, locked_targets=None) -> dict[str, bytes]:
    manifest = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name.endswith(".transformer-repair.target.lock"):
            continue
        relative = path.relative_to(root).as_posix()
        locked = (locked_targets or {}).get(relative)
        if locked is None or not locked[1] or locked[0] is None:
            content = path.read_bytes()
        else:
            fd = locked[0]
            if os.stat(path).st_ino != os.fstat(fd).st_ino:
                raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Repair target was recreated during apply")
            os.lseek(fd, 0, os.SEEK_SET)
            content = os.read(fd, os.fstat(fd).st_size)
        manifest[relative] = content
    return manifest


def _fingerprint_with_locked_targets(root: Path, locked_targets: dict[str, tuple[int | None, bool]]) -> str:
    return _fingerprint_manifest(_workspace_manifest(root, locked_targets))


def _fingerprint_manifest(manifest: dict[str, bytes]) -> str:
    """Digest a workspace manifest with the canonical stage-tree ordering.

    The digest must be byte-identical with ``STAGE_FINGERPRINT_PROFILE.
    fingerprint`` over the same tree (casefold sort) so the apply pre-check
    and the post-apply fingerprint recorded into the stage binding compare
    apples-to-apples with the persisted binding/checkpoint fingerprint.
    """
    return STAGE_FINGERPRINT_PROFILE.fingerprint_manifest(manifest.items())


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
        initial_manifest = _workspace_manifest(workspace)
        if _fingerprint_manifest(initial_manifest) != expected_fingerprint:
            raise RepairApplicationError("REPAIR_WORKSPACE_STALE", "Repair workspace fingerprint changed")
        prepared = {
            "schema_version": "repair-apply-ledger-v1",
            "attempt_id": attempt_id,
            "proposal_checksum": proposal_artifact_checksum or self._checksum(proposal),
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
        expected_manifest = dict(initial_manifest)
        for change in changes:
            if change["action"] == "delete":
                expected_manifest.pop(change["path"], None)
            else:
                expected_manifest[change["path"]] = change["content"].encode("utf-8")
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
                    change["path"],
                    target_locks.enter_context(
                        _target_apply_lock(target, lock_inode=change["action"] != "delete")
                    ),
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
                        locked_targets[change["path"]] = target_locks.enter_context(
                            _target_inode_lock(target)
                        )
                        target_fd, target_exists = locked_targets[change["path"]]
                    else:
                        if not target_exists:
                            raise RepairApplicationError("REPAIR_PREIMAGE_STALE", "Repair target disappeared before mutation")
                        if target_fd is None:
                            current_bytes = target.read_bytes()
                        else:
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
                    elif expected == "absent" and not target_exists:
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
                post_fingerprint = _fingerprint_with_locked_targets(workspace, locked_targets)
                final_manifest = _workspace_manifest(workspace, locked_targets)
                if final_manifest != expected_manifest:
                    raise RepairApplicationError(
                        "REPAIR_WORKSPACE_STALE",
                        "Workspace changed outside the approved repair",
                    )
                prepared["post_fingerprint"] = post_fingerprint
                prepared["status"] = "applied"
                final = self._write(store, run_id, stage_id, attempt_id, "applied", prepared)
            except Exception:
                target_locks.close()
                for change in changes:
                    target = workspace / change["path"]
                    original = originals.get(change["path"])
                    if original is None:
                        if target.exists():
                            target.unlink()
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
            elif action in {"replace_text", "dependency_change"}:
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
            else:
                raise RepairApplicationError(
                    "REPAIR_OPERATION_INVALID", "Repair operation is unsupported"
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
