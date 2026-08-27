"""Cleanliness verification and immutable, chain-bound stage output sealing."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.repositories.models import (
    ArtifactMetadataModel,
    CommandExecutionModel,
    MigrationRunModel,
    RepairAttemptModel,
    StageCheckpointModel,
    StageExecutionPlanModel,
    StageGatePackageModel,
    StagePromptRequestModel,
    StageWorkspaceBindingModel,
)
from app.services.stage_preparation_primitives import StageSandboxCopier
from app.services.stage_target_version_service import (
    StageTargetVersionError,
    StageTargetVersionService,
)


class StageSealingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StageSealingService:
    def __init__(self, *, now_provider=None) -> None:
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._target_versions = StageTargetVersionService()

    def context(self, session, continuation) -> dict[str, object]:
        active_command = session.scalar(
            select(CommandExecutionModel.id).where(
                CommandExecutionModel.run_id == continuation.run_id,
                CommandExecutionModel.stage_id == continuation.current_stage_id,
                CommandExecutionModel.status.in_(("queued", "pending", "running")),
            )
        )
        active_prompt = session.scalar(
            select(StagePromptRequestModel.id).where(
                StagePromptRequestModel.stage_id == continuation.current_stage_id,
                StagePromptRequestModel.status.not_in(("decided", "cancelled", "stale")),
            )
        )
        latest_repair = session.scalar(
            select(RepairAttemptModel)
            .where(RepairAttemptModel.stage_id == continuation.current_stage_id)
            .order_by(RepairAttemptModel.attempt_number.desc())
            .limit(1)
        )
        stale_repair_recovery = (
            continuation.current_node in ("promotion_pending", "seal_stage")
            and continuation.last_error_code in ("STAGE_NOT_CLEAN", "TRANSFORMER_WORKFLOW_UNHANDLED_ERROR")
            and latest_repair is not None
            and latest_repair.status in ("blocked", "evidence_frozen")
            and latest_repair.proposal_artifact_id is None
            and latest_repair.review_artifact_id is None
        )
        active_repair = (
            latest_repair.id
            if latest_repair is not None
            and not stale_repair_recovery
            and latest_repair.status
            not in (
                "waiting_g11",
                "validation_passed",
                "completed",
                "rejected",
                "apply_failed",
                "request_changes",
                "superseded",
            )
            else None
        )
        g09 = session.scalar(
            select(StageGatePackageModel)
            .where(
                StageGatePackageModel.stage_id == continuation.current_stage_id,
                StageGatePackageModel.gate_id == "G09",
                StageGatePackageModel.status == "approved",
            )
            .order_by(StageGatePackageModel.gate_version.desc())
        )
        if active_command or active_prompt or active_repair:
            raise StageSealingError(
                "STAGE_NOT_CLEAN", "Commands, prompts, or repairs are still active"
            )
        if g09 is None and active_repair is not None:
            raise StageSealingError("G09_APPROVAL_REQUIRED", "Approved G09 evidence is missing")
        bindings = session.scalars(
            select(StageWorkspaceBindingModel)
            .where(
                StageWorkspaceBindingModel.run_id == continuation.run_id,
                StageWorkspaceBindingModel.stage_id == continuation.current_stage_id,
                StageWorkspaceBindingModel.active.is_(True),
            )
            .order_by(
                StageWorkspaceBindingModel.created_at.desc(),
                StageWorkspaceBindingModel.id.desc(),
            )
        ).all()
        binding = next(
            (
                candidate
                for candidate in bindings
                if Path(candidate.workspace_path).is_dir()
                and StageSandboxCopier.fingerprint(Path(candidate.workspace_path))
                == candidate.workspace_fingerprint
            ),
            bindings[0] if bindings else None,
        )
        if binding is None:
            raise StageSealingError("WORKSPACE_BINDING_MISSING", "Active stage workspace binding is missing")
        run = session.get(MigrationRunModel, continuation.run_id)
        stage_plan = session.get(StageExecutionPlanModel, continuation.stage_plan_id)
        previous = session.scalar(
            select(StageCheckpointModel)
            .where(
                StageCheckpointModel.run_id == continuation.run_id,
                StageCheckpointModel.sealed.is_(True),
            )
            .order_by(StageCheckpointModel.created_at.desc())
            .limit(1)
        )
        evidence = list(
            session.scalars(
                select(ArtifactMetadataModel).where(
                    ArtifactMetadataModel.run_id == continuation.run_id,
                    ArtifactMetadataModel.stage_id == continuation.current_stage_id,
                    ArtifactMetadataModel.immutable.is_(True),
                )
            )
        )
        return {
            "run_id": continuation.run_id,
            "stage_id": continuation.current_stage_id,
            "stage_plan_checksum": continuation.stage_plan_checksum,
            "stage_plan": stage_plan.stage_plan,
            "workspace_path": binding.workspace_path,
            "workspace_fingerprint": binding.workspace_fingerprint,
            "artifact_root": run.artifact_root,
            "stage_root": (run.workspace_aliases or {})["STAGE_SANDBOX"],
            "g09_package_checksum": g09.package_checksum if g09 else None,
            "g09_workspace_fingerprint": g09.workspace_fingerprint if g09 else None,
            "previous_chain_hash": previous.manifest_checksum if previous else "genesis",
            "validation_summary_checksum": self._validation_checksum(
                session, continuation.current_stage_id
            ),
            "evidence_index": [
                {
                    "artifact_id": item.id.removeprefix("metadata-"),
                    "checksum": item.checksum,
                    "relative_path": item.relative_path,
                }
                for item in evidence
            ],
        }

    def verify_cleanliness(self, context: dict[str, object]) -> dict[str, object]:
        workspace = Path(str(context["workspace_path"])).resolve(strict=True)
        observed = StageSandboxCopier.fingerprint(workspace)
        g09_fingerprint = context.get("g09_workspace_fingerprint")
        if observed != context["workspace_fingerprint"] or (
            g09_fingerprint is not None and observed != g09_fingerprint
        ):
            raise StageSealingError(
                "STAGE_WORKSPACE_STALE", "Workspace changed after validation approval"
            )
        forbidden = []
        for item in workspace.rglob("*"):
            relative = item.relative_to(workspace)
            if StageSandboxCopier.is_excluded_path(relative):
                continue
            if item.is_symlink():
                forbidden.append(relative.as_posix() + ":symlink")
            if item.is_file() and any(
                part.startswith(".env") or part.endswith((".pem", ".key", ".pfx"))
                for part in relative.parts
            ):
                forbidden.append(relative.as_posix() + ":secret-path")
        if forbidden:
            raise StageSealingError(
                "STAGE_CLEANLINESS_FAILED", "Forbidden workspace entries: " + ", ".join(forbidden[:8])
            )
        return {
            "schema_version": "stage-cleanliness-v1",
            "run_id": context["run_id"],
            "stage_id": context["stage_id"],
            "workspace_fingerprint": observed,
            "g09_package_checksum": context["g09_package_checksum"],
            "stage_plan_checksum": context["stage_plan_checksum"],
            "validation_summary_checksum": context["validation_summary_checksum"],
            "evidence_index": context["evidence_index"],
            "status": "clean",
        }

    def seal(self, context: dict[str, object], g12_checksum: str):
        workspace = Path(str(context["workspace_path"])).resolve(strict=True)
        target_exact = (context.get("stage_plan") or {}).get("target_exact")
        if target_exact:
            try:
                self._target_versions.verify(
                    workspace,
                    str(target_exact),
                    dict((context.get("stage_plan") or {}).get("target_cohort") or {}),
                )
            except StageTargetVersionError as error:
                raise StageSealingError(error.code, error.message) from error
        stage_root = Path(str(context["stage_root"])).resolve(strict=True)
        sealed_root = stage_root / ".sealed"
        sealed_root.mkdir(parents=True, exist_ok=True)
        target = sealed_root / str(context["stage_id"])
        expected = self._copy_fingerprint(workspace)
        if target.exists():
            if StageSandboxCopier.fingerprint(target) != expected:
                quarantine = sealed_root / f".{target.name}.unregistered-{uuid4().hex[:12]}"
                target.replace(quarantine)
            else:
                report_fingerprint = expected
        if not target.exists():
            report = StageSandboxCopier().copy_atomically(
                workspace, target, registered_root=stage_root
            )
            report_fingerprint = report.fingerprint
        files = self._manifest(target)
        output_payload = {
            "schema_version": "sealed-output-manifest-v1",
            "run_id": context["run_id"],
            "stage_id": context["stage_id"],
            "output_path": str(target),
            "output_fingerprint": report_fingerprint,
            "files": files,
        }
        root = Path(str(context["artifact_root"]))
        store = LocalFilesystemArtifactStore(root.parent, fixed_run_root=root)
        output = store.write_text_artifact(
            str(context["run_id"]),
            f"04_workflow_state/stages/{context['stage_id']}/seal/output-manifest.json",
            json.dumps(output_payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=str(context["stage_id"]),
            created_by="stage-sealing-service",
            created_at=self._now(),
            input_hashes={"g12": g12_checksum},
            policy_version="stage-seal-v1",
        )
        chain_hash = self._checksum(
            {
                "previous_chain_hash": context["previous_chain_hash"],
                "stage_plan_checksum": context["stage_plan_checksum"],
                "g12_package_checksum": g12_checksum,
                "output_manifest_checksum": output.ref.checksum,
                "validation_summary_checksum": context["validation_summary_checksum"],
            }
        )
        seal_payload = {
            **output_payload,
            "previous_chain_hash": context["previous_chain_hash"],
            "chain_hash": chain_hash,
            "g12_package_checksum": g12_checksum,
            "output_manifest_artifact_id": output.ref.artifact_id,
            "output_manifest_checksum": output.ref.checksum,
        }
        seal = store.write_text_artifact(
            str(context["run_id"]),
            f"04_workflow_state/stages/{context['stage_id']}/seal/seal.json",
            json.dumps(seal_payload, sort_keys=True, indent=2),
            ArtifactType.JSON,
            stage_id=str(context["stage_id"]),
            created_by="stage-sealing-service",
            created_at=self._now(),
            input_hashes={"output_manifest": output.ref.checksum},
            policy_version="stage-seal-v1",
        )
        return target, report_fingerprint, chain_hash, output, seal

    @staticmethod
    def _validation_checksum(session, stage_id: str) -> str:
        gate = session.scalar(
            select(StageGatePackageModel)
            .where(
                StageGatePackageModel.stage_id == stage_id,
                StageGatePackageModel.gate_id.in_(("G09", "G11")),
                StageGatePackageModel.status == "approved",
            )
            .order_by(
                (StageGatePackageModel.gate_id == "G09").desc(),
                StageGatePackageModel.gate_version.desc(),
            )
        )
        if gate is not None:
            return gate.artifact_set_checksum
        summary = session.scalar(
            select(ArtifactMetadataModel.checksum)
            .where(
                ArtifactMetadataModel.stage_id == stage_id,
                ArtifactMetadataModel.relative_path.like("%/proven/validation-summary.json"),
            )
            .order_by(ArtifactMetadataModel.created_at.desc())
            .limit(1)
        )
        if summary is None:
            raise StageSealingError(
                "VALIDATION_SUMMARY_MISSING",
                "No approved gate or proven validation summary is available for sealing",
            )
        return summary

    @staticmethod
    def _copy_fingerprint(workspace: Path) -> str:
        temporary = workspace.parent / f".seal-fingerprint-{uuid4().hex[:12]}"
        try:
            report = StageSandboxCopier().copy(
                workspace, temporary, registered_root=workspace.parent
            )
            return report.fingerprint
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    @staticmethod
    def _manifest(root: Path) -> list[dict[str, object]]:
        return [
            {
                "path": item.relative_to(root).as_posix(),
                "size": item.stat().st_size,
                "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
            }
            for item in sorted(path for path in root.rglob("*") if path.is_file())
        ]

    @staticmethod
    def _checksum(value: object) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
