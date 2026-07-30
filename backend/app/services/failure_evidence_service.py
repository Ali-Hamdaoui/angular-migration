"""Immutable validation failure evidence and deterministic closed-route classification."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.domain.transformation import FailureRoute


class FailureEvidenceService:
    transient_codes = {
        "COMMAND_WORKER_LOST_REQUEUED",
        "COMMAND_TIMEOUT",
        "REGISTRY_TIMEOUT",
        "NETWORK_ERROR",
    }
    permanent_codes = {"EXECUTION_PROFILE_NOT_FOUND", "STAGE_WORKSPACE_MISSING"}
    dependency_codes = {
        "DEPENDENCY_PREFLIGHT_BLOCKED",
        "VERSION_VERIFICATION_FAILED",
        "VALIDATION_TARGET_MISSING",
    }
    policy_codes = {
        "VALIDATION_WORKSPACE_MUTATED",
        "VALIDATION_BINDING_STALE",
        "COMMAND_POLICY_REJECTED",
        "STALE_GATE_BINDING",
    }
    non_repairable_codes = {"VALIDATION_EVIDENCE_MISSING", "VALIDATION_INCOMPLETE"}

    def __init__(self, *, now_provider=None) -> None:
        self._now = now_provider or (lambda: datetime.now(UTC))

    def collect(self, session, continuation, *, prior_fingerprints: list[str]) -> dict[str, object]:
        from sqlalchemy import select

        from app.repositories.models import (
            CommandExecutionModel,
            MigrationRunModel,
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
        execution = session.scalar(
            select(CommandExecutionModel)
            .where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
            )
            .order_by(CommandExecutionModel.requested_at.desc())
            .limit(1)
        )
        normalized = {
            "error_code": continuation.last_error_code,
            "command_id": execution.command_id if execution else None,
            "exit_code": execution.exit_code if execution else None,
            "failure_code": execution.failure_code if execution else None,
            "failure_message": (execution.failure_message or "")[:2000] if execution else None,
        }
        failure_fingerprint = "sha256:" + hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "schema_version": "transformer-failure-evidence-v1",
            "run_id": continuation.run_id,
            "stage_id": continuation.current_stage_id,
            "stage_plan_checksum": continuation.stage_plan_checksum,
            "workspace_path": binding.workspace_path,
            "workspace_fingerprint": binding.workspace_fingerprint,
            "artifact_root": run.artifact_root,
            "execution_id": execution.id if execution else None,
            "command_log_artifact_id": execution.command_log_artifact_id if execution else None,
            "result_artifact_id": execution.result_artifact_id if execution else None,
            "normalized_failure": normalized,
            "failure_fingerprint": failure_fingerprint,
            "prior_fingerprints": prior_fingerprints,
            "repair_policy": (stage_plan.stage_plan or {}).get("repair_policy") or {},
            "forbidden_change_policy": (stage_plan.stage_plan or {}).get(
                "forbidden_change_policy"
            )
            or {},
        }

    def classify(self, evidence: dict[str, object]) -> FailureRoute:
        code = str((evidence["normalized_failure"] or {}).get("error_code") or "")
        if evidence["failure_fingerprint"] in evidence["prior_fingerprints"]:
            return FailureRoute.NO_PROGRESS
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
        failure = store.write_text_artifact(
            common["run_id"],
            f"04_workflow_state/stages/{common['stage_id']}/failures/{evidence['failure_fingerprint'][7:]}.json",
            json.dumps(serializable, sort_keys=True, indent=2),
            ArtifactType.JSON,
            **{key: value for key, value in common.items() if key != "run_id"},
        )
        route_artifact = store.write_text_artifact(
            common["run_id"],
            f"04_workflow_state/stages/{common['stage_id']}/failures/{evidence['failure_fingerprint'][7:]}-route.json",
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

    def write_context_pack(self, evidence: dict[str, object], failure_checksum: str):
        workspace = Path(str(evidence["workspace_path"])).resolve(strict=True)
        excerpts = {}
        for relative in ("package.json", "angular.json", "tsconfig.json"):
            path = workspace / relative
            if path.is_file() and not path.is_symlink():
                excerpts[relative] = path.read_text(encoding="utf-8", errors="replace")[:20_000]
        payload = {
            "schema_version": "repair-context-pack-v1",
            "failure_evidence_checksum": failure_checksum,
            "failure_fingerprint": evidence["failure_fingerprint"],
            "workspace_fingerprint": evidence["workspace_fingerprint"],
            "normalized_failure": evidence["normalized_failure"],
            "forbidden_change_policy": evidence["forbidden_change_policy"],
            "file_excerpts": excerpts,
            "untrusted": True,
        }
        root = Path(str(evidence["artifact_root"]))
        return LocalFilesystemArtifactStore(root.parent, fixed_run_root=root).write_text_artifact(
            str(evidence["run_id"]),
            f"05_repairs/{evidence['stage_id']}/{evidence['failure_fingerprint'][7:]}-context.json",
            json.dumps(payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=str(evidence["stage_id"]),
            created_by="failure-evidence-service",
            created_at=self._now(),
            input_hashes={"failure": failure_checksum},
            policy_version="repair-context-pack-v1",
        )
