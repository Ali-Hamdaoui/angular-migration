"""Classify validation failures against approved immutable baseline evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select

from app.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalFilesystemArtifactStore,
)
from app.repositories.models import (
    BaselineAssessmentModel,
    BaselineValidationModel,
    CommandExecutionModel,
    ArtifactMetadataModel,
    G03ApprovalModel,
    MigrationRunModel,
)


class BaselineValidationClassification(StrEnum):
    MATCHED_APPROVED_BASELINE = "matched_approved_baseline"
    NEW_FAILURE = "new_failure"
    MIXED_FAILURE = "mixed_failure"
    NO_APPROVED_BASELINE = "no_approved_baseline"
    EVIDENCE_INVALID = "evidence_invalid"


@dataclass(frozen=True)
class LintSignature:
    relative_path: str
    severity: str
    rule: str
    message: str


@dataclass(frozen=True)
class BaselineValidationResult:
    classification: BaselineValidationClassification
    current_signatures: tuple[LintSignature, ...] = ()
    baseline_signatures: tuple[LintSignature, ...] = ()
    reason: str = ""

    @property
    def is_accepted(self) -> bool:
        return self.classification is BaselineValidationClassification.MATCHED_APPROVED_BASELINE


class BaselineAwareValidationService:
    """Read-only authority for preserving approved baseline validation debt."""

    _DIAGNOSTIC = re.compile(
        r"^(ERROR|WARNING):\s+\d+:\d+\s+(\S+)\s+(.+?)\s*$",
        re.IGNORECASE,
    )
    _FILE = re.compile(r"(?:^|/)src/(.+?):\d+:\d+\s*$", re.IGNORECASE)

    def classify(
        self,
        session,
        *,
        run_id: str,
        validation_group: str,
        execution: CommandExecutionModel | None,
    ) -> BaselineValidationResult:
        if validation_group != "lint":
            return BaselineValidationResult(
                BaselineValidationClassification.NEW_FAILURE,
                reason="Only lint baseline debt is eligible for this classifier",
            )
        if execution is None or execution.status != "failed" or execution.exit_code == 0:
            return BaselineValidationResult(
                BaselineValidationClassification.EVIDENCE_INVALID,
                reason="Current lint execution is missing or not a nonzero failure",
            )
        authority = self._approved_baseline(session, run_id)
        if authority is None:
            return BaselineValidationResult(
                BaselineValidationClassification.NO_APPROVED_BASELINE,
                reason="No approved G03 known-failure baseline is available",
            )
        run, baseline = authority
        try:
            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root).parent,
                fixed_run_root=Path(run.artifact_root),
            )
            current_text = self._execution_text(session, store, run_id, execution)
            baseline_text = self._baseline_text(session, store, run_id, baseline)
            current = self._signatures(current_text)
            approved = self._signatures(baseline_text)
        except (ArtifactNotFoundError, ArtifactStoreError, OSError, ValueError) as error:
            return BaselineValidationResult(
                BaselineValidationClassification.EVIDENCE_INVALID,
                reason=f"Lint evidence could not be read: {type(error).__name__}",
            )
        if not current or not approved:
            return BaselineValidationResult(
                BaselineValidationClassification.EVIDENCE_INVALID,
                tuple(current),
                tuple(approved),
                "Canonical lint signatures are missing",
            )
        current_set = set(current)
        approved_set = set(approved)
        if current_set <= approved_set:
            classification = BaselineValidationClassification.MATCHED_APPROVED_BASELINE
            reason = "Current lint signatures are a subset of approved baseline signatures"
        elif current_set & approved_set:
            classification = BaselineValidationClassification.MIXED_FAILURE
            reason = "Current lint output contains both approved and new signatures"
        else:
            classification = BaselineValidationClassification.NEW_FAILURE
            reason = "Current lint output contains no approved baseline signature"
        return BaselineValidationResult(
            classification,
            tuple(sorted(current_set, key=self._signature_key)),
            tuple(sorted(approved_set, key=self._signature_key)),
            reason,
        )

    def _approved_baseline(self, session, run_id: str):
        assessment = session.scalar(
            select(BaselineAssessmentModel)
            .where(BaselineAssessmentModel.run_id == run_id)
            .order_by(BaselineAssessmentModel.updated_at.desc())
            .limit(1)
        )
        approval = session.scalar(
            select(G03ApprovalModel)
            .where(
                G03ApprovalModel.run_id == run_id,
                G03ApprovalModel.status == "approved",
            )
            .order_by(G03ApprovalModel.updated_at.desc())
            .limit(1)
        )
        if (
            assessment is None
            or approval is None
            or assessment.status != "qualified_with_known_failures"
            or approval.package_checksum != assessment.package_checksum
            or approval.evidence_set_checksum != assessment.evidence_set_checksum
            or not any(
                item.get("kind") == "lint"
                and item.get("origin") == "pre-existing"
                for item in assessment.known_failures or []
                if isinstance(item, dict)
            )
        ):
            return None
        baseline = session.scalar(
            select(BaselineValidationModel)
            .where(
                BaselineValidationModel.run_id == run_id,
                BaselineValidationModel.kind == "lint",
            )
            .order_by(BaselineValidationModel.updated_at.desc())
            .limit(1)
        )
        run = session.get(MigrationRunModel, run_id)
        if baseline is None or run is None or not baseline.artifact_ids:
            return None
        return run, baseline

    @staticmethod
    def _read_bound_artifact(session, store, run_id, artifact_id, expected_checksum=None):
        metadata = session.get(ArtifactMetadataModel, "metadata-" + str(artifact_id))
        if (
            metadata is None
            or not metadata.immutable
            or metadata.run_id != run_id
            or (expected_checksum is not None and metadata.checksum != expected_checksum)
        ):
            raise ValueError("artifact metadata is missing, mutable, or checksum-bound incorrectly")
        stored = store.read_artifact(run_id, metadata.relative_path)
        if (
            stored.ref.artifact_id != artifact_id
            or stored.ref.run_id != run_id
            or stored.ref.checksum != metadata.checksum
        ):
            raise ValueError("artifact metadata does not match immutable artifact")
        return stored

    @classmethod
    def _execution_text(cls, session, store, run_id, execution) -> str:
        artifact_ids = [execution.stdout_artifact_id, execution.stderr_artifact_id]
        if not all(artifact_ids) or not set(artifact_ids).issubset(
            set(getattr(execution, "artifact_ids", None) or [])
        ):
            raise ValueError("current lint stdout/stderr evidence is incomplete")
        return "\n".join(
            cls._read_bound_artifact(session, store, run_id, item).content
            for item in artifact_ids
        )

    @classmethod
    def _baseline_text(cls, session, store, run_id, baseline) -> str:
        contents = []
        for artifact_id in baseline.artifact_ids or []:
            stored = cls._read_bound_artifact(
                session,
                store,
                run_id,
                artifact_id,
                (getattr(baseline, "artifact_checksums", None) or {}).get(artifact_id),
            )
            if stored.ref.relative_path.endswith((".stdout.log", ".stderr.log")):
                contents.append(stored.content)
        if len(contents) < 2:
            raise ValueError("baseline lint stdout/stderr evidence is incomplete")
        return "\n".join(contents)

    def _signatures(self, text: str) -> tuple[LintSignature, ...]:
        current_file: str | None = None
        signatures: list[LintSignature] = []
        for raw_line in text.replace("\\", "/").splitlines():
            line = raw_line.strip()
            file_match = self._FILE.search(line)
            if file_match:
                current_file = "src/" + file_match.group(1)
                continue
            diagnostic = self._DIAGNOSTIC.match(line)
            if diagnostic is None or current_file is None:
                continue
            signatures.append(
                LintSignature(
                    relative_path=current_file,
                    severity=diagnostic.group(1).lower(),
                    rule=diagnostic.group(2),
                    message=" ".join(diagnostic.group(3).split()),
                )
            )
        return tuple(dict.fromkeys(signatures))

    @staticmethod
    def _signature_key(signature: LintSignature):
        return (
            signature.relative_path,
            signature.severity,
            signature.rule,
            signature.message,
        )
