"""Immutable validation failure evidence and deterministic closed-route classification."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from app.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalFilesystemArtifactStore,
    StoredArtifact,
)
from app.domain.contracts import ArtifactType
from app.domain.transformation import FailureRoute
from app.services.dependency_closure_service import (
    installed_dependency_version,
    is_exact_version,
)
from app.services.failure_intelligence_service import FailureIntelligenceService


CONTEXT_PACK_SCHEMA_VERSION = "repair-context-pack-v1"
CONTEXT_PACK_FILES = ("package.json", "angular.json", "tsconfig.json")
CONTEXT_PACK_MAX_FILES = 8
CONTEXT_PACK_MAX_BYTES_PER_FILE = 20_000
CONTEXT_PACK_MAX_TOTAL_BYTES = 100_000
CAUSAL_REPAIR_SCHEMA_VERSION = "causal-repair-lineage-v1"
_TERMINAL_FAILURE_STATUSES = frozenset({"failed", "timed_out", "cancelled", "interrupted"})
_FAILURE_TARGET = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/][^\s:'\"()]+|(?:[A-Za-z0-9_.@-]+[\\/])+[A-Za-z0-9_.@()-]+\.(?:ts|html|scss|json)))(?::\d+(?::\d+)?)?"
)
ANGULAR_DIRTY_WORKSPACE_MESSAGE = (
    "Repository is not clean. Please commit or stash any changes before updating."
)
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ANGULAR_PEER_CONFLICT_MARKERS = (
    "migration failed",
    "eresolve",
    "peer",
    "incompatible",
    "does not support",
    "dependencies are not compatible",
    "requires angular",
)
_NPM_ERROR_PREFIX = r"npm\s+(?:error|ERR!)"
_NPM_PACKAGE_NAME = r"(?:@[a-z0-9_.-]+/[a-z0-9_.-]+|[a-z0-9_.-]+)"
_ANGULAR_PACKAGE_AT_VERSION_RE = re.compile(
    rf"(?<![\w@]){_NPM_PACKAGE_NAME}@[\^~]?\d+\.\d+\.\d+(?:[-\w.]*)?"
)
_ANGULAR_PEER_FROM_RE = re.compile(
    rf"\bfrom\s+({_NPM_PACKAGE_NAME})@[\^~]?\d+\.\d+\.\d+(?:[-\w.]*)?"
)
_ANGULAR_PEER_CONFLICT_RE = re.compile(
    rf'Package\s+"(?P<package>{_NPM_PACKAGE_NAME})"\s+'
    rf'has\s+an\s+incompatible\s+peer\s+dependency\s+to\s+'
    rf'"(?P<peer>{_NPM_PACKAGE_NAME})"\s*'
    rf'\(\s*requires\s+"(?P<required>[^"\r\n]+)"\s*,\s*'
    rf'would\s+install\s+"(?P<proposed>[^"\r\n]+)"\s*\)',
    re.IGNORECASE,
)
_ANGULAR_MISSING_PEER_RE = re.compile(
    rf'Package\s+"(?P<package>{_NPM_PACKAGE_NAME})"\s+'
    rf'has\s+a\s+missing\s+peer\s+dependency\s+of\s+'
    rf'"(?P<peer>{_NPM_PACKAGE_NAME})"\s*@\s*'
    rf'"(?P<required>[^"\r\n]+)"',
    re.IGNORECASE,
)
_ANGULAR_PEER_RANGE_RE = re.compile(
    rf"\bpeer(?:Dependencies| dependency)?\s+({_NPM_PACKAGE_NAME})"
    rf"@[\"']?([\^~><=]?\s*\d+\.\d+\.\d+[^\"'\s]*)"
)
_NPM_ERESOLVE_MARKER_RE = re.compile(
    rf"(?im)^\s*{_NPM_ERROR_PREFIX}\s+(?:code\s+)?ERESOLVE\b"
)
_NPM_ERESOLVE_PEER_CONFLICT_RE = re.compile(
    rf"(?im)^\s*(?:{_NPM_ERROR_PREFIX}\s+)?peer\s+"
    rf"(?P<blocking>{_NPM_PACKAGE_NAME})@"
    rf"(?P<required>\"[^\"\r\n]+\"|'[^'\r\n]+'|[^\s]+)\s+from\s+"
    rf"(?P<package>{_NPM_PACKAGE_NAME})@"
    rf"(?P<version>\d+\.\d+\.\d+(?:[-\w.]*)?)(?=\s|$)"
)


def _installed_version_of(message: str, package: str) -> str | None:
    """Best-effort version adjacent to the package name in the failure message."""
    match = re.search(
        re.escape(package) + r"@[\^~]?\s*(\d+\.\d+\.\d+(?:[-\w.]*)?)", message
    )
    return match.group(1) if match else None


class CausalExecutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _failure_matches_current_route(last_error_code: str | None, failure_code: str | None) -> bool:
    return (
        not last_error_code
        or failure_code == last_error_code
        or last_error_code
        in {"FAILURE_ROUTE_ENVIRONMENT_TRANSIENT", "CAUSAL_EXECUTION_AMBIGUOUS"}
    )


def resolve_causal_failed_execution(session, continuation):
    """Resolve the explicitly bound failed execution; fail closed on ambiguity."""
    from sqlalchemy import select

    from app.repositories.models import CommandExecutionModel, StageStepModel

    def valid(execution):
        return bool(
            execution is not None
            and execution.run_id == continuation.run_id
            and execution.stage_id == continuation.current_stage_id
            and execution.plan_id == continuation.plan_id
            and execution.status in _TERMINAL_FAILURE_STATUSES
            and (execution.exit_code not in (None, 0) or execution.failure_code)
            and execution.result_artifact_id
            and execution.command_log_artifact_id
        )

    waiting = (
        session.get(CommandExecutionModel, continuation.waiting_execution_id)
        if continuation.waiting_execution_id
        else None
    )
    if valid(waiting):
        step = session.scalar(
            select(StageStepModel).where(
                StageStepModel.run_id == continuation.run_id,
                StageStepModel.stage_id == continuation.current_stage_id,
                StageStepModel.execution_id == waiting.id,
            )
        )
        return waiting, step.name if step else None

    failed_steps = session.scalars(
        select(StageStepModel).where(
            StageStepModel.run_id == continuation.run_id,
            StageStepModel.stage_id == continuation.current_stage_id,
            StageStepModel.status == "FAILED",
        )
    ).all()
    step_candidates = [
        (execution, step.name)
        for step in failed_steps
        if step.execution_id
        and valid(execution := session.get(CommandExecutionModel, step.execution_id))
        and (
            _failure_matches_current_route(
                continuation.last_error_code, execution.failure_code
            )
        )
    ]
    if len(step_candidates) == 1:
        return step_candidates[0]
    if len(step_candidates) > 1:
        raise CausalExecutionError(
            "CAUSAL_EXECUTION_AMBIGUOUS",
            "More than one failed stage step matches the current failure authority",
        )

    failed = session.scalars(
        select(CommandExecutionModel).where(
            CommandExecutionModel.run_id == continuation.run_id,
            CommandExecutionModel.stage_id == continuation.current_stage_id,
            CommandExecutionModel.status.in_(tuple(_TERMINAL_FAILURE_STATUSES)),
        )
    ).all()
    failed = [execution for execution in failed if valid(execution)]
    if len(failed) == 1:
        newer_success = session.scalar(
            select(CommandExecutionModel.id).where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
                CommandExecutionModel.plan_id == continuation.plan_id,
                CommandExecutionModel.status == "succeeded",
                CommandExecutionModel.exit_code == 0,
                CommandExecutionModel.requested_at > failed[0].requested_at,
            ).limit(1)
        )
        if newer_success is not None:
            raise CausalExecutionError(
                "CAUSAL_EXECUTION_AMBIGUOUS",
                "A newer successful execution contradicts the unbound failed execution",
            )
        return failed[0], None
    raise CausalExecutionError(
        "CAUSAL_EXECUTION_AMBIGUOUS" if failed else "CAUSAL_EXECUTION_MISSING",
        "Current failure is not bound to one immutable failed command execution",
    )


class FailureTargetResolver:
    """Resolve bounded repository files named by immutable command evidence."""

    MAX_FILES = 4

    @classmethod
    def resolve(cls, workspace: Path, message: str) -> tuple[str, ...]:
        workspace = workspace.resolve(strict=True)
        resolved: list[str] = []
        for match in _FAILURE_TARGET.finditer(message):
            candidate = Path(match.group("path").replace("\\", "/"))
            path = candidate if candidate.is_absolute() else workspace / candidate
            relative = cls._safe_relative(workspace, path)
            if relative and relative not in resolved:
                resolved.append(relative)
            if len(resolved) >= cls.MAX_FILES:
                break
        for relative in tuple(resolved):
            path = Path(relative)
            paired = (
                path.with_name(path.name.removesuffix(".spec.ts") + ".ts")
                if path.name.endswith(".spec.ts")
                else path.with_name(path.stem + ".spec.ts")
                if path.suffix == ".ts"
                else None
            )
            if paired is not None:
                safe = cls._safe_relative(workspace, workspace / paired)
                if safe and safe not in resolved and len(resolved) < cls.MAX_FILES:
                    resolved.append(safe)
        return tuple(resolved)

    @staticmethod
    def _safe_relative(workspace: Path, path: Path) -> str | None:
        try:
            target = path.resolve(strict=True)
            relative = target.relative_to(workspace)
        except (OSError, ValueError):
            return None
        current = workspace
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                return None
        if not target.is_file() or target.suffix.lower() not in {".ts", ".html", ".scss", ".json"}:
            return None
        return relative.as_posix()


class FailureEvidenceService:
    transient_codes: ClassVar[set[str]] = {
        "COMMAND_WORKER_LOST_REQUEUED",
        # Historical drift: the executor emits COMMAND_TIMED_OUT; the legacy
        # COMMAND_TIMEOUT spelling is kept for already-persisted evidence.
        "COMMAND_TIMED_OUT",
        "COMMAND_TIMEOUT",
        "REGISTRY_TIMEOUT",
        "NETWORK_ERROR",
    }
    permanent_codes: ClassVar[set[str]] = {"EXECUTION_PROFILE_NOT_FOUND", "STAGE_WORKSPACE_MISSING"}
    dependency_codes: ClassVar[set[str]] = {
        "DEPENDENCY_PREFLIGHT_BLOCKED",
        "VERSION_VERIFICATION_FAILED",
        "VALIDATION_TARGET_MISSING",
    }
    policy_codes: ClassVar[set[str]] = {
        "VALIDATION_WORKSPACE_MUTATED",
        "VALIDATION_BINDING_STALE",
        "COMMAND_POLICY_REJECTED",
        "STALE_GATE_BINDING",
    }
    non_repairable_codes: ClassVar[set[str]] = {"VALIDATION_EVIDENCE_MISSING", "VALIDATION_INCOMPLETE"}

    @staticmethod
    def is_angular_update_dirty_workspace(evidence: dict[str, object]) -> bool:
        normalized = evidence.get("normalized_failure") or {}
        message = " ".join(str(normalized.get("failure_message") or "").split())
        if message.startswith("Error: "):
            message = message.removeprefix("Error: ")
        return (
            normalized.get("command_id") == "angular-update-exact"
            and normalized.get("command_allows_dirty") is not True
            and ANGULAR_DIRTY_WORKSPACE_MESSAGE in message
        )

    @staticmethod
    def diagnose_angular_update_failure(
        normalized: dict[str, object],
    ) -> dict[str, object] | None:
        """Deterministic peer-conflict diagnosis for a failed Angular update."""
        if str(normalized.get("command_id") or "").startswith("npm-"):
            return FailureEvidenceService.diagnose_npm_eresolve_failure(normalized)
        if normalized.get("command_id") != "angular-update-exact":
            return None
        message = " ".join(str(normalized.get("failure_message") or "").split())
        message = _ANSI_ESCAPE.sub("", message)
        if not message:
            return None
        npm_diagnosis = FailureEvidenceService.diagnose_npm_eresolve_failure(normalized)
        if npm_diagnosis is not None:
            return npm_diagnosis
        lowered = message.lower()
        if not any(marker in lowered for marker in _ANGULAR_PEER_CONFLICT_MARKERS):
            return None
        clean = message
        if clean.startswith("Error: "):
            clean = clean.removeprefix("Error: ")
        if ANGULAR_DIRTY_WORKSPACE_MESSAGE in clean:
            return None
        conflict = _ANGULAR_PEER_CONFLICT_RE.search(clean)
        if conflict is not None:
            peer = conflict.group("peer")
            return {
                "kind": "peer_dependency_conflict",
                "package": conflict.group("package"),
                "installed_version": None,
                "required_ranges": {peer: conflict.group("required").strip()},
                "proposed_angular_version": (
                    conflict.group("proposed").strip()
                    if peer.startswith(("@angular/", "@angular-devkit/"))
                    else None
                ),
            }
        missing = _ANGULAR_MISSING_PEER_RE.search(clean)
        if missing is not None:
            return None
        package: str | None = None
        installed_version: str | None = None
        for match in _ANGULAR_PEER_FROM_RE.finditer(message):
            candidate = match.group(1)
            if not candidate.startswith("@angular/"):
                package = candidate
                installed_version = _installed_version_of(message, candidate)
                break
        if package is None:
            for match in _ANGULAR_PACKAGE_AT_VERSION_RE.finditer(message):
                candidate = match.group(0).rsplit("@", 1)[0]
                if not candidate.startswith("@angular/"):
                    package = candidate
                    installed_version = _installed_version_of(message, candidate)
                    break
        required_ranges: dict[str, str] = {}
        for match in _ANGULAR_PEER_RANGE_RE.finditer(message):
            peer = match.group(1)
            if peer not in required_ranges:
                required_ranges[peer] = match.group(2).strip()
        return {
            "kind": "peer_dependency_conflict",
            "package": package,
            "installed_version": installed_version,
            "required_ranges": required_ranges,
        }

    @staticmethod
    def diagnose_npm_eresolve_failure(
        normalized: dict[str, object],
    ) -> dict[str, object] | None:
        """Parse only npm's persisted ERESOLVE peer-conflict structure."""
        command_id = str(normalized.get("command_id") or "")
        if not (
            command_id.startswith("npm-") or command_id == "angular-update-exact"
        ):
            return None
        message = _ANSI_ESCAPE.sub(
            "", str(normalized.get("failure_message") or "")
        )
        if not _NPM_ERESOLVE_MARKER_RE.search(message):
            return None
        for match in _NPM_ERESOLVE_PEER_CONFLICT_RE.finditer(message):
            required = match.group("required").strip()
            if required[:1] in {"\"", "'"} and required[-1:] == required[:1]:
                required = required[1:-1].strip()
            if not required:
                continue
            blocking = match.group("blocking")
            package = match.group("package")
            package_version = match.group("version")
            return {
                "kind": "peer_dependency_conflict",
                "source": "npm_eresolve_peer_conflict",
                "package": package,
                "blocking_dependency": blocking,
                "package_version": package_version,
                "required_peer_range": required,
                "installed_version": _installed_version_of(message, blocking),
                "required_ranges": {blocking: required},
                "proposed_angular_version": None,
            }
        return None

    @staticmethod
    def normalize_dependency_transition_evidence(
        evidence: object,
    ) -> tuple[object, dict[str, object] | None]:
        """Return evidence with its deterministic transition diagnosis restored."""
        if not isinstance(evidence, dict):
            return evidence, None
        normalized = evidence.get("normalized_failure")
        diagnosis = normalized.get("failure_diagnosis") if isinstance(normalized, dict) else None
        if (
            isinstance(normalized, dict)
            and (
                not isinstance(diagnosis, dict)
                or not isinstance(diagnosis.get("package"), str)
                or not diagnosis.get("required_ranges")
                or (
                    _NPM_ERESOLVE_MARKER_RE.search(
                        str(normalized.get("failure_message") or "")
                    )
                    and diagnosis.get("source") != "npm_eresolve_peer_conflict"
                )
                or (
                    diagnosis.get("source") == "npm_eresolve_peer_conflict"
                    and not is_exact_version(diagnosis.get("installed_version"))
                )
            )
        ):
            reparsed = (
                FailureEvidenceService.diagnose_npm_eresolve_failure(normalized)
                if str(normalized.get("command_id") or "").startswith("npm-")
                else FailureEvidenceService.diagnose_angular_update_failure(normalized)
            )
            if reparsed is not None:
                normalized = {**normalized, "failure_diagnosis": reparsed}
                evidence = {**evidence, "normalized_failure": normalized}
                diagnosis = reparsed
        return evidence, diagnosis if isinstance(diagnosis, dict) else None

    @staticmethod
    def is_angular_update_peer_dependency_conflict(evidence: dict[str, object]) -> bool:
        normalized = evidence.get("normalized_failure") or {}
        diagnosis = normalized.get("failure_diagnosis")
        return (
            normalized.get("command_id") == "angular-update-exact"
            and normalized.get("exit_code") is not None
            and normalized.get("exit_code") != 0
            and isinstance(diagnosis, dict)
            and diagnosis.get("kind") == "peer_dependency_conflict"
            and not FailureEvidenceService.is_angular_update_dirty_workspace(evidence)
        )

    def __init__(self, *, now_provider=None) -> None:
        self._now = now_provider or (lambda: datetime.now(UTC))

    def collect(
        self,
        session,
        continuation,
        *,
        causal_execution,
        causal_step_name: str | None,
        prior_fingerprints: list[str],
    ) -> dict[str, object]:
        from sqlalchemy import select

        from app.repositories.models import (
            MigrationRunModel,
            RepairAttemptModel,
            StageCheckpointModel,
            StageExecutionPlanModel,
            StageWorkspaceBindingModel,
        )

        run = session.get(MigrationRunModel, continuation.run_id)
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        binding = session.scalar(
            select(StageWorkspaceBindingModel).where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
        )
        execution = causal_execution
        output = self._execution_output(session, run, execution)
        normalized = {
            "error_code": continuation.last_error_code,
            "command_id": execution.command_id,
            "exit_code": execution.exit_code,
            "failure_code": execution.failure_code,
            "failure_message": output,
        }
        if normalized["command_id"] == "angular-update-exact" or str(
            normalized["command_id"] or ""
        ).startswith("npm-"):
            if normalized["command_id"] == "angular-update-exact":
                normalized["command_allows_dirty"] = "--allow-dirty" in (execution.arguments or [])
            diagnosis = self.diagnose_angular_update_failure(normalized)
            installed_package = (
                diagnosis.get("blocking_dependency")
                if isinstance(diagnosis, dict)
                and diagnosis.get("source") == "npm_eresolve_peer_conflict"
                else diagnosis.get("package")
                if isinstance(diagnosis, dict)
                else None
            )
            if isinstance(installed_package, str):
                try:
                    diagnosis["installed_version"] = installed_dependency_version(
                        Path(binding.workspace_path), installed_package
                    )
                except ValueError:
                    pass
            normalized["failure_diagnosis"] = diagnosis
        semantic_failure_fingerprint = "sha256:" + hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        causal_kind = self._causal_kind(normalized, causal_step_name)
        latest_attempt = session.scalar(
            select(RepairAttemptModel)
            .where(
                RepairAttemptModel.run_id == continuation.run_id,
                RepairAttemptModel.stage_id == continuation.current_stage_id,
            )
            .order_by(RepairAttemptModel.attempt_number.desc())
            .limit(1)
        )
        previous = self._previous_causal_repair(session, run, latest_attempt)
        same_state = bool(
            previous
            and previous.get("causal_execution_id") == execution.id
            and previous.get("causal_kind") == causal_kind
            and previous.get("workspace_fingerprint") == binding.workspace_fingerprint
            and previous.get("semantic_failure_fingerprint") == semantic_failure_fingerprint
        )
        next_attempt_id = (
            latest_attempt.id
            if same_state
            else f"repair-{continuation.current_stage_id}-{(latest_attempt.attempt_number if latest_attempt else 0) + 1}"
        )
        checkpoint_id = execution.checkpoint_id or session.scalar(
            select(StageCheckpointModel.id)
            .where(
                StageCheckpointModel.run_id == continuation.run_id,
                StageCheckpointModel.stage_id == continuation.current_stage_id,
                StageCheckpointModel.safe_for_resume.is_(True),
            )
            .order_by(StageCheckpointModel.sequence.desc())
            .limit(1)
        )
        if checkpoint_id is None:
            raise CausalExecutionError(
                "CAUSAL_CHECKPOINT_MISSING",
                "Current failed execution has no authoritative stage checkpoint",
            )
        lineage_root = (
            str(previous.get("lineage_root_attempt_id"))
            if same_state and previous and previous.get("lineage_root_attempt_id")
            else next_attempt_id
        )
        causal_repair = {
            "schema_version": CAUSAL_REPAIR_SCHEMA_VERSION,
            "causal_execution_id": execution.id,
            "causal_command_id": execution.command_id,
            "causal_step_name": causal_step_name or execution.command_id,
            "causal_kind": causal_kind,
            "semantic_failure_fingerprint": semantic_failure_fingerprint,
            "workspace_fingerprint": binding.workspace_fingerprint,
            "checkpoint_id": checkpoint_id,
            "parent_attempt_id": latest_attempt.id if latest_attempt and not same_state else (previous or {}).get("parent_attempt_id"),
            "lineage_root_attempt_id": lineage_root,
        }
        causal_repair["causal_state_identity"] = "sha256:" + hashlib.sha256(
            json.dumps(causal_repair, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        failure_fingerprint = causal_repair["causal_state_identity"]
        return {
            "schema_version": "transformer-failure-evidence-v1",
            "run_id": continuation.run_id,
            "stage_id": continuation.current_stage_id,
            "stage_plan_checksum": continuation.stage_plan_checksum,
            "workspace_path": binding.workspace_path,
            "workspace_fingerprint": binding.workspace_fingerprint,
            "artifact_root": run.artifact_root,
            "execution_id": execution.id,
            "command_log_artifact_id": execution.command_log_artifact_id,
            "result_artifact_id": execution.result_artifact_id,
            "normalized_failure": normalized,
            "causal_repair": causal_repair,
            "semantic_failure_fingerprint": semantic_failure_fingerprint,
            "failure_fingerprint": failure_fingerprint,
            "prior_fingerprints": prior_fingerprints,
            "repair_policy": (stage_plan.stage_plan or {}).get("repair_policy") or {},
            "target_cohort": (stage_plan.stage_plan or {}).get("target_cohort") or {},
            "forbidden_change_policy": (stage_plan.stage_plan or {}).get(
                "forbidden_change_policy"
            )
            or {},
        }

    @staticmethod
    def _causal_kind(normalized: dict[str, object], step_name: str | None) -> str:
        intelligence = FailureIntelligenceService()
        if intelligence.is_dependency_incompatible(normalized):
            return "dependency"
        route = intelligence.classify(normalized)
        if route in {FailureRoute.ENVIRONMENT_TRANSIENT, FailureRoute.ENVIRONMENT_PERMANENT}:
            return "environment"
        prefix = str(step_name or "").split("-", 1)[0]
        return {"builds": "build", "tests": "test", "lint": "lint"}.get(prefix, "source")

    @staticmethod
    def _execution_output(session, run, execution) -> str:
        parts = [str(execution.failure_message or "")]
        if run is not None and run.artifact_root:
            store = LocalFilesystemArtifactStore(
                Path(str(run.artifact_root)).parent,
                fixed_run_root=Path(str(run.artifact_root)),
            )
            from app.repositories.models import ArtifactMetadataModel

            for artifact_id in (execution.stdout_artifact_id, execution.stderr_artifact_id):
                metadata = session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id)) if artifact_id else None
                if metadata is None or metadata.run_id != execution.run_id:
                    continue
                try:
                    stored = store.read_artifact(execution.run_id, metadata.relative_path)
                except (ArtifactNotFoundError, ArtifactStoreError, OSError):
                    continue
                if stored.ref.checksum == metadata.checksum:
                    parts.append(stored.content)
        return "\n".join(part for part in parts if part)[-8000:]

    @staticmethod
    def _previous_causal_repair(session, run, attempt) -> dict[str, object] | None:
        if attempt is None or run is None or not run.artifact_root or not attempt.failure_evidence_artifact_id:
            return None
        from app.repositories.models import ArtifactMetadataModel

        metadata = session.get(
            ArtifactMetadataModel, "metadata-" + str(attempt.failure_evidence_artifact_id)
        )
        if metadata is None or metadata.checksum != attempt.failure_evidence_checksum:
            return None
        try:
            stored = LocalFilesystemArtifactStore(
                Path(str(run.artifact_root)).parent,
                fixed_run_root=Path(str(run.artifact_root)),
            ).read_artifact(attempt.run_id, metadata.relative_path)
            payload = json.loads(stored.content)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, TypeError, ValueError):
            return None
        value = payload.get("causal_repair") if isinstance(payload, dict) else None
        return value if isinstance(value, dict) else None

    def classify(self, evidence: dict[str, object]) -> FailureRoute:
        code = str((evidence["normalized_failure"] or {}).get("error_code") or "")
        if evidence["failure_fingerprint"] in evidence["prior_fingerprints"]:
            return FailureRoute.NO_PROGRESS
        if self.is_angular_update_dirty_workspace(evidence):
            return FailureRoute.ANGULAR_UPDATE_COMMAND_POLICY
        if self.is_angular_update_peer_dependency_conflict(evidence):
            return FailureRoute.ANGULAR_UPDATE_PEER_CONFLICT
        intelligence_route = FailureIntelligenceService().classify(evidence)
        if intelligence_route in {
            FailureRoute.DEPENDENCY_INCOMPATIBLE,
            FailureRoute.ENVIRONMENT_TRANSIENT,
            FailureRoute.ENVIRONMENT_PERMANENT,
        }:
            return intelligence_route
        if code in self.transient_codes:
            return FailureRoute.ENVIRONMENT_TRANSIENT
        if code in self.permanent_codes:
            return FailureRoute.ENVIRONMENT_PERMANENT
        if code in self.dependency_codes:
            return FailureRoute.DEPENDENCY_INCOMPATIBLE
        if code == "UNEXPECTED_PROMPT":
            return FailureRoute.UNEXPECTED_PROMPT
        if code in self.policy_codes:
            return FailureRoute.POLICY_VIOLATION
        if code in self.non_repairable_codes:
            return FailureRoute.NON_REPAIRABLE_VALIDATION
        return FailureRoute.REPAIRABLE_SOURCE

    def committed_evidence(
        self,
        session,
        continuation,
        failure_fingerprint: str,
    ) -> tuple[StoredArtifact, StoredArtifact, StoredArtifact] | None:
        """Replay committed failure evidence for an identical classification, else None.

        Returns the (failure, route, context) triple reconstructed from committed
        ``artifact_metadata`` rows and the run-root-bound artifact store only when
        run id, stage id, artifact types, expected paths (including ``__vN``
        versioned siblings written after a crash before commit), and checksums
        all match this failure fingerprint. Any anomaly - missing row, duplicate
        row, missing file, or checksum drift on disk - yields None so callers
        write fresh evidence instead.
        """
        from app.repositories.models import ArtifactMetadataModel, MigrationRunModel

        run = session.get(MigrationRunModel, continuation.run_id)
        if run is None or not run.artifact_root:
            return None
        root = Path(str(run.artifact_root))
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        paths = self._expected_evidence_paths(continuation.current_stage_id, failure_fingerprint)
        replayed: list[StoredArtifact] = []
        for kind in ("failure", "route_artifact", "context"):
            expected = paths[kind]
            rows = session.query(ArtifactMetadataModel).filter_by(
                run_id=continuation.run_id,
                stage_id=continuation.current_stage_id,
                artifact_type=ArtifactType.JSON.value,
            ).all()
            candidates = [row for row in rows if self._is_evidence_sibling(row.relative_path, expected)]
            if len(candidates) != 1:
                return None
            row = candidates[0]
            try:
                stored = store.read_artifact(continuation.run_id, row.relative_path)
            except (ArtifactNotFoundError, ArtifactStoreError, OSError):
                return None
            if (
                stored.ref.artifact_type != ArtifactType.JSON
                or stored.ref.relative_path != row.relative_path
                or stored.ref.checksum != row.checksum
            ):
                return None
            replayed.append(stored)
        return replayed[0], replayed[1], replayed[2]

    @staticmethod
    def _is_evidence_sibling(relative_path: str, expected: str) -> bool:
        """Match the canonical path or a ``__vN`` versioned sibling of it."""
        if relative_path == expected:
            return True
        stem, separator, suffix = relative_path.rpartition(".")
        if not separator:
            return False
        for marker in re.findall(r"__v\d+$", stem):
            return f"{stem[: -len(marker)]}.{suffix}" == expected
        return False

    @staticmethod
    def _expected_evidence_paths(stage_id: str, failure_fingerprint: str) -> dict[str, str]:
        suffix = str(failure_fingerprint)[7:]
        return {
            "failure": f"04_workflow_state/stages/{stage_id}/failures/{suffix}.json",
            "route_artifact": f"04_workflow_state/stages/{stage_id}/failures/{suffix}-route.json",
            "context": f"05_repairs/{stage_id}/{suffix}-context.json",
        }

    def write(self, evidence: dict[str, object], route: FailureRoute):
        root = Path(str(evidence["artifact_root"]))
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        common = {
            "run_id": str(evidence["run_id"]),
            "stage_id": str(evidence["stage_id"]),
            "created_by": "failure-evidence-service",
            "created_at": self._now(),
            "input_hashes": {"stage_plan": str(evidence["stage_plan_checksum"])},
            "policy_version": "transformer-failure-evidence-v1",
        }
        serializable = {key: value for key, value in evidence.items() if key not in {"workspace_path", "artifact_root"}}
        paths = self._expected_evidence_paths(common["stage_id"], evidence["failure_fingerprint"])
        failure = store.write_text_artifact(
            common["run_id"],
            paths["failure"],
            json.dumps(serializable, sort_keys=True, indent=2),
            ArtifactType.JSON,
            **{key: value for key, value in common.items() if key != "run_id"},
        )
        route_artifact = store.write_text_artifact(
            common["run_id"],
            paths["route_artifact"],
            json.dumps(
                {
                    "failure_fingerprint": evidence["failure_fingerprint"],
                    "route": route.value,
                    "classifier_version": "transformer-failure-classifier-v1",
                },
                sort_keys=True,
                indent=2,
            ),
            ArtifactType.JSON,
            **{key: value for key, value in common.items() if key != "run_id"},
        )
        return failure, route_artifact

    def write_context_pack(
        self,
        evidence: dict[str, object],
        failure_checksum: str,
        *,
        max_files: int = CONTEXT_PACK_MAX_FILES,
        max_bytes_per_file: int = CONTEXT_PACK_MAX_BYTES_PER_FILE,
        max_total_bytes: int = CONTEXT_PACK_MAX_TOTAL_BYTES,
        relative_path: str | None = None,
        lineage_from: str | None = None,
        human_revision: dict[str, object] | None = None,
        dependency_bundle: dict[str, object] | None = None,
        dependency_bundle_artifact_id: str | None = None,
        dependency_bundle_checksum: str | None = None,
    ):
        """Write a deterministically bounded, preimage-bound repair context pack.

        Every included file entry carries its exact SHA-256 preimage (``sha256``
        over the file bytes as read), ``size_bytes`` and a ``truncated`` flag.
        Files that are not valid UTF-8 or exceed ``max_bytes_per_file`` become
        checksum-only entries (``content`` is None) mirroring the diff-manifest
        policy for binary/oversized files. Entries are added in sorted path
        order until ``max_files`` or ``max_total_bytes`` is exhausted; paths
        skipped because of either bound are recorded in ``bounds.omitted`` so
        truncation/omission is never silent. ``bounds`` declares the enforced
        limits, the included byte total, and the truncated/omitted paths.
        """
        if max_files < 1 or max_bytes_per_file < 1 or max_total_bytes < 1:
            raise ValueError("repair context pack bounds must be positive")
        workspace = Path(str(evidence["workspace_path"])).resolve(strict=True)
        entries: dict[str, dict[str, object]] = {}
        truncated: list[str] = []
        omitted: list[str] = []
        included_bytes = 0
        failure_targets = FailureTargetResolver.resolve(
            workspace, str((evidence.get("normalized_failure") or {}).get("failure_message") or "")
        )
        for relative in sorted({*CONTEXT_PACK_FILES, *failure_targets}):
            if len(entries) >= max_files:
                omitted.append(relative)
                continue
            path = workspace / relative
            if not path.is_file() or path.is_symlink():
                continue
            entry = self._context_file_entry(relative, path.read_bytes(), max_bytes_per_file)
            contribution = (
                len(entry["content"].encode("utf-8")) if entry["content"] is not None else 0
            )
            if included_bytes + contribution > max_total_bytes:
                omitted.append(relative)
                continue
            entries[relative] = entry
            if entry["truncated"]:
                truncated.append(relative)
            included_bytes += contribution
        payload = {
            "schema_version": CONTEXT_PACK_SCHEMA_VERSION,
            "failure_evidence_checksum": failure_checksum,
            "failure_fingerprint": evidence["failure_fingerprint"],
            "workspace_fingerprint": evidence["workspace_fingerprint"],
            "normalized_failure": evidence["normalized_failure"],
            "causal_repair": evidence["causal_repair"],
            "target_cohort": evidence.get("target_cohort") or {},
            "forbidden_change_policy": evidence["forbidden_change_policy"],
            "file_excerpts": entries,
            "bounds": {
                "max_files": max_files,
                "max_bytes_per_file": max_bytes_per_file,
                "max_total_bytes": max_total_bytes,
                "included_bytes": included_bytes,
                "truncated": truncated,
                "omitted": omitted,
            },
            "untrusted": True,
        }
        if human_revision is not None:
            payload["human_revision"] = human_revision
        # P0-1: hydrate dependency bundle into context for DEPENDENCY_INCOMPATIBLE
        if dependency_bundle is not None:
            # Validate minimal bundle shape before embedding
            if not isinstance(dependency_bundle, dict) or dependency_bundle.get("schema_version") != "dependency-failure-bundle-v1":
                raise ValueError("dependency bundle schema_version must be dependency-failure-bundle-v1")
            # Required fields must match evidence
            if dependency_bundle.get("run_id") != evidence.get("run_id") or dependency_bundle.get("stage_id") != evidence.get("stage_id"):
                raise ValueError("dependency bundle run/stage mismatch")
            payload["dependency_normalization"] = {
                "failure_bundle_schema_version": dependency_bundle.get("schema_version"),
                "failure_bundle_artifact_id": dependency_bundle_artifact_id,
                "failure_bundle_checksum": dependency_bundle_checksum,
                "source_angular_exact": dependency_bundle.get("source_angular_exact"),
                "target_angular_exact": dependency_bundle.get("target_angular_exact"),
                "target_cli_exact": dependency_bundle.get("target_cli_exact"),
                "runtime": {
                    "node_exact": dependency_bundle.get("node_exact"),
                    "npm_exact": dependency_bundle.get("npm_exact"),
                },
                "pre_update": dependency_bundle.get("pre_update"),
                "post_failure": dependency_bundle.get("post_failure"),
                "command": dependency_bundle.get("command"),
                "effective_npm_settings": dependency_bundle.get("effective_npm_settings"),
                "prior_normalization": dependency_bundle.get("prior_normalization"),
            }
        root = Path(str(evidence["artifact_root"]))
        input_hashes = {"failure": failure_checksum}
        if lineage_from is not None:
            input_hashes["recovered_from"] = lineage_from
        return LocalFilesystemArtifactStore(root.parent, fixed_run_root=root).write_text_artifact(
            str(evidence["run_id"]),
            relative_path
            or self._expected_evidence_paths(str(evidence["stage_id"]), evidence["failure_fingerprint"])["context"],
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=str(evidence["stage_id"]),
            created_by="failure-evidence-service",
            created_at=self._now(),
            input_hashes=input_hashes,
            policy_version=CONTEXT_PACK_SCHEMA_VERSION,
        )

    @staticmethod
    def _context_file_entry(
        relative: str, raw: bytes, max_bytes_per_file: int
    ) -> dict[str, object]:
        """One deterministic file entry: exact preimage checksum plus bounded content."""
        checksum = "sha256:" + hashlib.sha256(raw).hexdigest()
        size_bytes = len(raw)
        try:
            content: str | None = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = None
        truncated = content is None or size_bytes > max_bytes_per_file
        return {
            "path": relative,
            "sha256": checksum,
            "size_bytes": size_bytes,
            "truncated": truncated,
            "content": None if truncated else content,
        }


def validate_context_pack(payload: object) -> None:
    """Fail-closed structural validation of a repair context pack.

    Verifies the bounds block, deterministic (sorted) entry ordering, per-file
    and total byte budgets, and that every non-truncated entry's content
    preimage matches its declared SHA-256. Raises ``ValueError`` with a stable
    message on the first violation so callers fail closed.
    """
    if not isinstance(payload, dict):
        raise ValueError("repair context pack must be a JSON object")
    if payload.get("schema_version") != CONTEXT_PACK_SCHEMA_VERSION:
        raise ValueError("repair context pack schema_version is not supported")
    causal = payload.get("causal_repair")
    if not isinstance(causal, dict) or causal.get("schema_version") != CAUSAL_REPAIR_SCHEMA_VERSION:
        raise ValueError("repair context pack causal repair lineage is missing")
    required_causal = {
        "causal_execution_id",
        "causal_command_id",
        "causal_step_name",
        "causal_kind",
        "semantic_failure_fingerprint",
        "workspace_fingerprint",
        "checkpoint_id",
        "parent_attempt_id",
        "lineage_root_attempt_id",
        "causal_state_identity",
    }
    if set(causal) != required_causal | {"schema_version"}:
        raise ValueError("repair context pack causal repair lineage fields are invalid")
    if causal.get("causal_kind") not in {"dependency", "build", "test", "lint", "source", "environment"}:
        raise ValueError("repair context pack causal kind is invalid")
    bounds = payload.get("bounds")
    if not isinstance(bounds, dict):
        raise ValueError("repair context pack bounds block is missing")
    max_files = bounds.get("max_files")
    max_bytes_per_file = bounds.get("max_bytes_per_file")
    max_total_bytes = bounds.get("max_total_bytes")
    if not all(
        isinstance(value, int) and value >= 1 for value in (max_files, max_bytes_per_file, max_total_bytes)
    ):
        raise ValueError("repair context pack bounds limits are invalid")
    included_bytes = bounds.get("included_bytes")
    if not isinstance(included_bytes, int) or included_bytes < 0:
        raise ValueError("repair context pack included_bytes is invalid")
    for key in ("truncated", "omitted"):
        value = bounds.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"repair context pack bounds {key} list is invalid")
        if value != sorted(value) or len(set(value)) != len(value):
            raise ValueError(f"repair context pack bounds {key} list is not deterministic")
    excerpts = payload.get("file_excerpts")
    if not isinstance(excerpts, dict):
        raise ValueError("repair context pack file_excerpts is invalid")
    if list(excerpts.keys()) != sorted(excerpts.keys()):
        raise ValueError("repair context pack file entries are not sorted by path")
    if len(excerpts) > max_files:
        raise ValueError("repair context pack exceeds max_files bound")
    recomputed_bytes = 0
    truncated_paths: list[str] = []
    for relative, entry in excerpts.items():
        if not isinstance(entry, dict):
            raise ValueError(f"repair context pack entry {relative} is invalid")
        if entry.get("path") != relative:
            raise ValueError(f"repair context pack entry {relative} path mismatch")
        checksum = entry.get("sha256")
        if not isinstance(checksum, str) or not checksum.startswith("sha256:"):
            raise ValueError(f"repair context pack entry {relative} preimage checksum is missing")
        size_bytes = entry.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError(f"repair context pack entry {relative} size_bytes is invalid")
        content = entry.get("content")
        if entry.get("truncated") != (content is None):
            raise ValueError(f"repair context pack entry {relative} truncation flag is inconsistent")
        if content is None:
            truncated_paths.append(relative)
            continue
        if not isinstance(content, str):
            raise ValueError(f"repair context pack entry {relative} content is invalid")
        encoded = content.encode("utf-8")
        if size_bytes != len(encoded):
            raise ValueError(f"repair context pack entry {relative} size_bytes mismatch")
        if size_bytes > max_bytes_per_file:
            raise ValueError(f"repair context pack entry {relative} exceeds per-file bound")
        if "sha256:" + hashlib.sha256(encoded).hexdigest() != checksum:
            raise ValueError(f"repair context pack entry {relative} preimage checksum mismatch")
        recomputed_bytes += len(encoded)
    if recomputed_bytes != included_bytes:
        raise ValueError("repair context pack included_bytes mismatch")
    if included_bytes > max_total_bytes:
        raise ValueError("repair context pack exceeds total byte budget")
    if bounds["truncated"] != truncated_paths:
        raise ValueError("repair context pack bounds truncated list mismatch")
