"""Application services for G03 Angular transformation, evidence, and G08 acceptance."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactRefDto, ArtifactType, RiskLevel, WorkflowEventType
from app.domain.transformation import (
    AngularUpdateCommand,
    AngularUpdateResult,
    AngularUpdateStatus,
    ChangedFileClassification,
    ChangedFileEntry,
    DiffSummary,
    ForbiddenChangeEntry,
    G08ApprovalService,
    G08Decision,
    G08DecisionResult,
    G08EvidencePackage,
    G08EvidencePackageBuilder,
    PackageChangeSummary,
    PromptDetectionResult,
    TargetVersionEvidence,
    TargetVersionStatus,
    TransformationEvidenceResult,
    VersionEvidenceSource,
)
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel
from app.repositories.session import session_scope
from app.repositories.transformation_models import (
    AngularUpdateRecordModel,
    G08ApprovalModel,
    TransformationEvidenceModel,
)
from app.state.transition_service import StateTransitionService, TransitionRequest


# ── Shared helpers ────────────────────────────────────────────────────────


class G03ApplicationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _write_evidence(
    store: LocalFilesystemArtifactStore,
    session,
    run_id: str,
    name: str,
    payload: dict,
    stage_id: str | None = None,
    *,
    created_by: str = "g03-service",
    created_at: datetime | None = None,
    input_hashes: dict[str, str] | None = None,
) -> ArtifactRefDto:
    now = created_at or datetime.now(UTC)
    stored = store.write_text_artifact(
        run_id,
        f"stage/{stage_id or 'unknown'}/g03/{name}",
        json.dumps(payload, sort_keys=True, indent=2),
        ArtifactType.JSON,
        created_by=created_by,
        created_at=now,
        input_hashes=input_hashes or {},
    )
    metadata = ArtifactMetadataModel(
        id=f"metadata-{stored.ref.artifact_id}",
        run_id=run_id,
        stage_id=stage_id,
        artifact_type=stored.ref.artifact_type.value,
        relative_path=stored.ref.relative_path,
        checksum=stored.ref.checksum,
        created_at=now,
    )
    session.add(metadata)
    return stored.ref


def _find_event(session, run_id: str, key: str):
    from app.repositories.models import WorkflowEventModel

    return session.scalar(
        select(WorkflowEventModel).where(
            WorkflowEventModel.run_id == run_id,
            WorkflowEventModel.idempotency_key == key,
        )
    )


# ── S3-F07 — Angular Update Service ──────────────────────────────────────


class AngularUpdateApplicationService:
    def __init__(self, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str, stage_id: str):
        with self._scope() as session:
            record = session.scalar(
                select(AngularUpdateRecordModel)
                .where(AngularUpdateRecordModel.run_id == run_id)
                .where(AngularUpdateRecordModel.stage_id == stage_id)
                .order_by(AngularUpdateRecordModel.created_at.desc())
            )
            if record is None:
                return None
            return self._dto(record)

    def start_update(self, run_id: str, stage_id: str, request) -> object:
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            existing_event = _find_event(session, run_id, request.idempotency_key)
            if existing_event:
                record = session.scalar(
                    select(AngularUpdateRecordModel)
                    .where(AngularUpdateRecordModel.run_id == run_id)
                    .order_by(AngularUpdateRecordModel.created_at.desc())
                )
                return self._dto(record, replay=True) if record else None

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError(
                    "STALE_STATE_VERSION",
                    f"run is at version {run.state_version}, expected {request.expected_state_version}",
                    status_code=409,
                )

            command = AngularUpdateCommand(
                arguments=[
                    "ng",
                    "update",
                    f"@angular/core@{request.target_version}",
                    f"@angular/cli@{request.target_version}",
                    "--migrate-only",
                    f"--from={request.source_version}",
                    f"--to={request.target_version}",
                ]
            )

            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=WorkflowEventType.ANGULAR_UPDATE_STARTED,
                    actor=request.actor,
                    reason=f"Angular update {request.source_version} -> {request.target_version} started",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={
                        "source_version": request.source_version,
                        "target_version": request.target_version,
                        "stage_id": stage_id,
                    },
                )
            )

            record_id = f"ang-upd-{uuid4().hex[:12]}"
            record = AngularUpdateRecordModel(
                id=record_id,
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                status=AngularUpdateStatus.RUNNING.value,
                target_version_status=TargetVersionStatus.INCONCLUSIVE.value,
                source_version=request.source_version,
                target_version=request.target_version,
                prompt_detected=PromptDetectionResult.NO_PROMPT.value,
                artifact_ids=[],
                state_version=transition.next_state_version,
                event_sequence=transition.event_sequence,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()

            return self._dto(record)

    def complete_update(
        self,
        run_id: str,
        stage_id: str,
        request,
        *,
        succeeded: bool = True,
        resolved_version: str | None = None,
        error_message: str | None = None,
    ) -> object:
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            record = session.scalar(
                select(AngularUpdateRecordModel)
                .where(AngularUpdateRecordModel.run_id == run_id)
                .where(AngularUpdateRecordModel.stage_id == stage_id)
                .order_by(AngularUpdateRecordModel.created_at.desc())
            )
            if record is None:
                raise G03ApplicationError(
                    "NO_ACTIVE_UPDATE", "No active Angular update for this stage.", status_code=409
                )

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError(
                    "STALE_STATE_VERSION",
                    f"run is at version {run.state_version}, expected {request.expected_state_version}",
                    status_code=409,
                )

            event_type = (
                WorkflowEventType.ANGULAR_UPDATE_COMPLETED
                if succeeded
                else WorkflowEventType.ANGULAR_UPDATE_FAILED
            )

            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=event_type,
                    actor=request.actor,
                    reason=f"Angular update {'completed' if succeeded else 'failed'}",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={
                        "succeeded": succeeded,
                        "resolved_version": resolved_version,
                        "stage_id": stage_id,
                    },
                )
            )

            record.status = AngularUpdateStatus.SUCCEEDED.value if succeeded else AngularUpdateStatus.FAILED.value
            record.resolved_target_version = resolved_version
            record.error_message = error_message
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            record.updated_at = now
            session.flush()

            return self._dto(record)

    def verify_target_version(
        self,
        run_id: str,
        stage_id: str,
        request,
        *,
        evidence: TargetVersionEvidence | None = None,
    ) -> object:
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            record = session.scalar(
                select(AngularUpdateRecordModel)
                .where(AngularUpdateRecordModel.run_id == run_id)
                .where(AngularUpdateRecordModel.stage_id == stage_id)
                .order_by(AngularUpdateRecordModel.created_at.desc())
            )
            if record is None:
                raise G03ApplicationError(
                    "NO_ACTIVE_UPDATE", "No Angular update record for this stage.", status_code=404
                )

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError(
                    "STALE_STATE_VERSION",
                    f"run is at version {run.state_version}, expected {request.expected_state_version}",
                    status_code=409,
                )

            ev = evidence or TargetVersionEvidence(resolved_target="unknown")
            verified = ev.all_sources_agree and ev.resolved_target != "unknown"
            event_type = (
                WorkflowEventType.TARGET_VERSION_VERIFIED
                if verified
                else WorkflowEventType.TARGET_VERSION_FAILED
            )

            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=event_type,
                    actor=request.actor,
                    reason=f"Target version {'verified' if verified else 'mismatch'}",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={
                        "verified": verified,
                        "resolved_target": ev.resolved_target,
                        "stage_id": stage_id,
                    },
                )
            )

            record.target_version_status = TargetVersionStatus.VERIFIED.value if verified else TargetVersionStatus.MISMATCH.value
            record.resolved_target_version = ev.resolved_target
            record.evidence = ev.model_dump(mode="json")
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            record.updated_at = now
            session.flush()

            return self._dto(record)

    def _dto(self, record, *, replay=False):
        from app.api.transformation_contracts import AngularUpdateResponse

        return AngularUpdateResponse(
            run_id=record.run_id,
            stage_id=record.stage_id,
            status=AngularUpdateStatus(record.status),
            target_version_status=TargetVersionStatus(record.target_version_status),
            resolved_target_version=record.resolved_target_version,
            command_execution_id=record.command_execution_id,
            prompt_detected=record.prompt_detected,
            artifact_ids=record.artifact_ids,
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            error_message=record.error_message,
            idempotent_replay=replay,
        )


# ── S3-F08 — Transformation Evidence Service ─────────────────────────────


class TransformationEvidenceApplicationService:
    GATE_VERSION = "g03-evidence-v1"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str, stage_id: str):
        with self._scope() as session:
            record = session.scalar(
                select(TransformationEvidenceModel)
                .where(TransformationEvidenceModel.run_id == run_id)
                .where(TransformationEvidenceModel.stage_id == stage_id)
                .order_by(TransformationEvidenceModel.created_at.desc())
            )
            if record is None:
                return None
            return self._dto(record)

    def generate(self, run_id: str, stage_id: str, request) -> object:
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            existing_event = _find_event(session, run_id, request.idempotency_key)
            if existing_event:
                record = session.scalar(
                    select(TransformationEvidenceModel)
                    .where(TransformationEvidenceModel.run_id == run_id)
                    .order_by(TransformationEvidenceModel.created_at.desc())
                )
                return self._dto(record, replay=True) if record else None

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError(
                    "STALE_STATE_VERSION",
                    f"run is at version {run.state_version}, expected {request.expected_state_version}",
                    status_code=409,
                )

            store = LocalFilesystemArtifactStore(
                Path(run.artifact_root), fixed_run_root=Path(run.artifact_root)
            ) if run.artifact_root else None

            # Build transformation evidence
            diff_result = self._compute_diff_summary(
                Path(request.source_sandbox_path), Path(request.target_sandbox_path)
            )

            package_result = self._compute_package_changes(
                Path(request.source_sandbox_path), Path(request.target_sandbox_path)
            )

            forbidden = self._scan_forbidden_changes(diff_result, package_result)

            evidence_complete = diff_result.total_files_changed > 0
            overall_risk = self._compute_overall_risk(diff_result, forbidden)

            event_type = (
                WorkflowEventType.TRANSFORMATION_EVIDENCE_COMPLETED
                if evidence_complete
                else WorkflowEventType.TRANSFORMATION_EVIDENCE_BLOCKED
            )

            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=event_type,
                    actor=request.actor,
                    reason=f"Transformation evidence {'completed' if evidence_complete else 'blocked'}",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={
                        "evidence_complete": evidence_complete,
                        "overall_risk_level": overall_risk.value,
                        "stage_id": stage_id,
                    },
                )
            )

            artifact_ids: list[str] = []
            if store:
                ref = _write_evidence(
                    store, session, run_id, "transformation_diff_summary.json",
                    diff_result.model_dump(mode="json"),
                    stage_id=stage_id,
                    created_by="transformation-evidence-service",
                    created_at=now,
                    input_hashes={"diff_checksum": diff_result.diff_checksum},
                )
                artifact_ids.append(ref.artifact_id)

                if package_result:
                    ref2 = _write_evidence(
                        store, session, run_id, "package_change_summary.json",
                        package_result.model_dump(mode="json"),
                        stage_id=stage_id,
                        created_by="transformation-evidence-service",
                        created_at=now,
                    )
                    artifact_ids.append(ref2.artifact_id)

                if forbidden:
                    ref3 = _write_evidence(
                        store, session, run_id, "forbidden_changes.json",
                        {"forbidden_changes": [f.model_dump(mode="json") for f in forbidden]},
                        stage_id=stage_id,
                        created_by="transformation-evidence-service",
                        created_at=now,
                    )
                    artifact_ids.append(ref3.artifact_id)

            record_id = f"tev-{uuid4().hex[:12]}"
            record = TransformationEvidenceModel(
                id=record_id,
                run_id=run_id,
                stage_id=stage_id,
                idempotency_key=request.idempotency_key,
                actor=request.actor,
                status="completed" if evidence_complete else "blocked",
                overall_risk_level=overall_risk.value,
                total_files_changed=diff_result.total_files_changed,
                diff_checksum=diff_result.diff_checksum,
                diff_summary=diff_result.model_dump(mode="json"),
                package_change_summary=package_result.model_dump(mode="json") if package_result else None,
                forbidden_changes=[f.model_dump(mode="json") for f in forbidden],
                changed_file_classifications={
                    cf.file_path: cf.classification.value for cf in diff_result.changed_files
                },
                evidence_complete=evidence_complete,
                artifact_ids=artifact_ids,
                state_version=transition.next_state_version,
                event_sequence=transition.event_sequence,
                block_reason=None if evidence_complete else "No changes detected in transformation sandbox",
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()

            return self._dto(record)

    def _compute_diff_summary(self, source_path: Path, target_path: Path) -> DiffSummary:
        """Compute a diff summary by comparing files between source and target sandboxes."""
        changed_files: list[ChangedFileEntry] = []
        total_added = 0
        total_removed = 0
        checksum_input: list[str] = []

        if not source_path.exists() or not target_path.exists():
            return DiffSummary(
                total_files_changed=0,
                total_lines_added=0,
                total_lines_removed=0,
                changed_files=[],
                diff_checksum="sha256:" + "0" * 64,
            )

        source_files = {p.relative_to(source_path): p for p in source_path.rglob("*") if p.is_file()}
        target_files = {p.relative_to(target_path): p for p in target_path.rglob("*") if p.is_file()}
        all_paths = set(source_files) | set(target_files)

        for rel_path in sorted(all_paths):
            sp = source_files.get(rel_path)
            tp = target_files.get(rel_path)
            path_str = str(rel_path)

            if sp and tp:
                try:
                    sc = sp.read_bytes()
                    tc = tp.read_bytes()
                    if sc == tc:
                        continue  # unchanged
                    change_type = "modified"
                    added = max(0, len(tc.splitlines()) - len(sc.splitlines()))
                    removed = max(0, len(sc.splitlines()) - len(tc.splitlines()))
                except OSError:
                    continue
            elif sp and not tp:
                change_type = "deleted"
                added = 0
                try:
                    removed = len(sp.read_text().splitlines())
                except (OSError, UnicodeDecodeError):
                    removed = 0
            else:
                change_type = "added"
                removed = 0
                try:
                    added = len(tp.read_text().splitlines()) if tp else 0
                except (OSError, UnicodeDecodeError):
                    added = 0

            classification = self._classify_file(path_str)
            total_added += added
            total_removed += removed
            checksum_input.append(f"{change_type}:{path_str}:{added}:{removed}")

            changed_files.append(
                ChangedFileEntry(
                    file_path=path_str,
                    change_type=change_type,
                    classification=classification,
                    lines_added=added,
                    lines_removed=removed,
                )
            )

        import hashlib

        diff_checksum = f"sha256:{hashlib.sha256('|'.join(checksum_input).encode()).hexdigest()}"
        files_by_class: dict[str, int] = {}
        for cf in changed_files:
            files_by_class[cf.classification.value] = files_by_class.get(cf.classification.value, 0) + 1

        return DiffSummary(
            total_files_changed=len(changed_files),
            total_lines_added=total_added,
            total_lines_removed=total_removed,
            files_by_classification=files_by_class,
            changed_files=changed_files,
            diff_checksum=diff_checksum,
        )

    def _classify_file(self, path: str) -> ChangedFileClassification:
        path_lower = path.lower()

        # Forbidden: CI/CD pipeline configs
        if any(
            ci in path_lower
            for ci in [
                ".github/workflows/", ".github/actions/",
                ".gitlab-ci.yml", ".circleci/", "azure-pipelines",
                "jenkinsfile", "bitbucket-pipelines",
            ]
        ):
            return ChangedFileClassification.FORBIDDEN

        # Forbidden: Credential and secret files
        if any(
            cred in path_lower
            for cred in [
                ".env", ".envrc",
                "credentials", "secrets",
                ".pem", ".key", ".cert", "id_rsa",
                "service-account", "kubeconfig",
                ".netrc", ".pgpass",
            ]
        ):
            return ChangedFileClassification.FORBIDDEN

        # Forbidden: Security policy configs
        if any(
            sec in path_lower
            for sec in [
                "security", ".htaccess", ".htpasswd",
                "allowed_signers", "snyk", "codeql",
            ]
        ):
            return ChangedFileClassification.FORBIDDEN

        if any(ext in path_lower for ext in [".bin", ".exe", ".dll", ".so", ".dylib", ".png", ".jpg", ".gif", ".ico"]):
            return ChangedFileClassification.BINARY
        if any(gen in path_lower for gen in ["/dist/", "/build/", "/.angular/", "node_modules", "/coverage/"]):
            return ChangedFileClassification.GENERATED
        if any(
            sens in path_lower
            for sens in ["auth", "security", "credential", "secret", "key", "token", "password"]
        ):
            return ChangedFileClassification.SENSITIVE
        if path_lower.endswith("package-lock.json") or path_lower.endswith("yarn.lock"):
            return ChangedFileClassification.MEDIUM_RISK
        if path_lower.endswith(( ".ts", ".js", ".html", ".css", ".scss", ".json", ".py")):
            return ChangedFileClassification.LOW_RISK
        return ChangedFileClassification.MEDIUM_RISK

    def _compute_package_changes(
        self, source_path: Path, target_path: Path
    ) -> PackageChangeSummary | None:
        """Compute package.json changes between source and target."""
        source_pkg = source_path / "package.json"
        target_pkg = target_path / "package.json"

        if not source_pkg.exists() or not target_pkg.exists():
            return None

        try:
            import json as _json

            sp = _json.loads(source_pkg.read_text())
            tp = _json.loads(target_pkg.read_text())
        except (OSError, _json.JSONDecodeError):
            return None

        def _diff_deps(a: dict, b: dict) -> tuple[list[str], list[str], list[dict[str, str]]]:
            a_deps = a or {}
            b_deps = b or {}
            added = [k for k in b_deps if k not in a_deps]
            removed = [k for k in a_deps if k not in b_deps]
            updated = [
                {"name": k, "from": a_deps[k], "to": b_deps[k]}
                for k in a_deps
                if k in b_deps and a_deps[k] != b_deps[k]
            ]
            return added, removed, updated

        deps_added, deps_removed, deps_updated = _diff_deps(
            sp.get("dependencies"), tp.get("dependencies")
        )
        dev_added, dev_removed, dev_updated = _diff_deps(
            sp.get("devDependencies"), tp.get("devDependencies")
        )

        ang_before = None
        ang_after = None
        all_deps = {**(sp.get("dependencies") or {}), **(sp.get("devDependencies") or {})}
        all_tdeps = {**(tp.get("dependencies") or {}), **(tp.get("devDependencies") or {})}
        for dep in ["@angular/core", "@angular/cli"]:
            if dep in all_deps:
                ang_before = all_deps[dep]
            if dep in all_tdeps:
                ang_after = all_tdeps[dep]

        return PackageChangeSummary(
            dependencies_added=deps_added,
            dependencies_removed=deps_removed,
            dependencies_updated=deps_updated,
            dev_dependencies_added=dev_added,
            dev_dependencies_removed=dev_removed,
            dev_dependencies_updated=dev_updated,
            angular_version_before=ang_before,
            angular_version_after=ang_after,
        )

    def _scan_forbidden_changes(
        self, diff: DiffSummary, package: PackageChangeSummary | None
    ) -> list[ForbiddenChangeEntry]:
        forbidden: list[ForbiddenChangeEntry] = []
        for cf in diff.changed_files:
            if cf.classification == ChangedFileClassification.FORBIDDEN:
                forbidden.append(
                    ForbiddenChangeEntry(
                        file_path=cf.file_path,
                        reason="File is classified as forbidden for transformation",
                        risk_level=RiskLevel.CRITICAL,
                    )
                )
            if cf.classification == ChangedFileClassification.SENSITIVE:
                forbidden.append(
                    ForbiddenChangeEntry(
                        file_path=cf.file_path,
                        reason="Sensitive file change detected (auth/security/credentials)",
                        risk_level=RiskLevel.CRITICAL,
                        suggestion="Review manually before approving transformation",
                    )
                )
        if package and package.other_major_changes:
            for change in package.other_major_changes:
                forbidden.append(
                    ForbiddenChangeEntry(
                        file_path="package.json",
                        reason=f"Major package change: {change}",
                        risk_level=RiskLevel.MEDIUM,
                    )
                )
        return forbidden

    def _compute_overall_risk(self, diff: DiffSummary, forbidden: list[ForbiddenChangeEntry]) -> RiskLevel:
        if any(f.risk_level == RiskLevel.CRITICAL for f in forbidden):
            return RiskLevel.CRITICAL
        if any(f.risk_level == RiskLevel.HIGH for f in forbidden):
            return RiskLevel.HIGH
        if diff.total_files_changed > 100:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _dto(self, record, *, replay=False):
        from app.api.transformation_contracts import TransformationEvidenceResponse

        return TransformationEvidenceResponse(
            run_id=record.run_id,
            stage_id=record.stage_id,
            status=record.status,
            overall_risk_level=record.overall_risk_level,
            total_files_changed=record.total_files_changed,
            diff_checksum=record.diff_checksum,
            diff_summary=record.diff_summary,
            package_change=record.package_change_summary,
            migration_list=record.migration_list,
            forbidden_changes=record.forbidden_changes,
            changed_file_classifications=record.changed_file_classifications,
            evidence_complete=record.evidence_complete,
            artifact_ids=record.artifact_ids,
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            block_reason=record.block_reason,
            idempotent_replay=replay,
        )


# ── S3-F09 — G08 Approval Service ────────────────────────────────────────


class G08ApprovalApplicationService:
    GATE_ID = "G08"
    GATE_VERSION = "g08-v1"

    def __init__(self, *, session_scope_factory=session_scope, now_provider=None) -> None:
        self._scope = session_scope_factory
        self._now = now_provider or (lambda: datetime.now(UTC))

    def get(self, run_id: str, stage_id: str, gate_id: str):
        if gate_id != self.GATE_ID:
            return None
        with self._scope() as session:
            record = session.scalar(
                select(G08ApprovalModel)
                .where(G08ApprovalModel.run_id == run_id)
                .where(G08ApprovalModel.stage_id == stage_id)
                .order_by(G08ApprovalModel.created_at.desc())
            )
            return self._dto(record) if record else None

    def initialize(self, run_id: str, stage_id: str, request) -> object:
        if request.gate_id != self.GATE_ID:
            raise G03ApplicationError("GATE_NOT_FOUND", "Only G08 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            existing = session.scalar(
                select(G08ApprovalModel)
                .where(G08ApprovalModel.run_id == run_id)
                .where(G08ApprovalModel.stage_id == stage_id)
                .order_by(G08ApprovalModel.created_at.desc())
            )
            if existing is not None:
                return self._dto(existing, replay=True)

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            record = self._create_pending_record(session, run, stage_id, request.actor, request.idempotency_key, now)
            return self._dto(record)

    def decide(self, run_id: str, stage_id: str, request) -> object:
        if request.gate_id != self.GATE_ID:
            raise G03ApplicationError("GATE_NOT_FOUND", "Only G08 is supported by this endpoint.", status_code=404)
        now = self._now()
        with self._scope() as session:
            run = session.get(MigrationRunModel, run_id)
            if run is None:
                raise G03ApplicationError("RUN_NOT_FOUND", "Migration run does not exist.", status_code=404)

            existing_event = _find_event(session, run_id, request.idempotency_key)
            if existing_event:
                record = session.scalar(
                    select(G08ApprovalModel)
                    .where(G08ApprovalModel.run_id == run_id)
                    .order_by(G08ApprovalModel.created_at.desc())
                )
                if record is None:
                    raise G03ApplicationError("STALE_EVIDENCE", "G08 approval record not found.", status_code=409)
                return self._dto(record, replay=True)

            if run.state_version != request.expected_state_version:
                raise G03ApplicationError("STALE_STATE_VERSION", "The run state version is stale.", status_code=409)

            record = session.scalar(
                select(G08ApprovalModel)
                .where(G08ApprovalModel.run_id == run_id)
                .where(G08ApprovalModel.stage_id == stage_id)
                .order_by(G08ApprovalModel.created_at.desc())
            )

            if record is None:
                record = self._create_pending_record(session, run, stage_id, request.actor, request.idempotency_key, now)

            # Build the package from stored evidence
            transformation_record = session.scalar(
                select(AngularUpdateRecordModel)
                .where(AngularUpdateRecordModel.run_id == run_id)
                .where(AngularUpdateRecordModel.stage_id == stage_id)
                .order_by(AngularUpdateRecordModel.created_at.desc())
            )
            evidence_record = session.scalar(
                select(TransformationEvidenceModel)
                .where(TransformationEvidenceModel.run_id == run_id)
                .where(TransformationEvidenceModel.stage_id == stage_id)
                .order_by(TransformationEvidenceModel.created_at.desc())
            )

            transform_result = AngularUpdateResult(
                run_id=run_id,
                stage_id=stage_id,
                update_status=AngularUpdateStatus(transformation_record.status) if transformation_record else AngularUpdateStatus.FAILED,
                target_version_status=TargetVersionStatus(transformation_record.target_version_status) if transformation_record else TargetVersionStatus.INCONCLUSIVE,
                resolved_target_version=transformation_record.resolved_target_version if transformation_record else None,
            )
            ev_result = TransformationEvidenceResult(
                run_id=run_id,
                stage_id=stage_id,
                diff=DiffSummary(total_files_changed=evidence_record.total_files_changed if evidence_record else 0, total_lines_added=0, total_lines_removed=0, diff_checksum=evidence_record.diff_checksum if evidence_record else "sha256:" + "0" * 64),
                evidence_complete=evidence_record.evidence_complete if evidence_record else False,
                overall_risk_level=RiskLevel(evidence_record.overall_risk_level) if evidence_record else RiskLevel.HIGH,
            )

            result: G08DecisionResult = G08ApprovalService().decide(
                G08EvidencePackage(
                    run_id=run_id,
                    stage_id=stage_id,
                    gate_version=self.GATE_VERSION,
                    state_version=run.state_version,
                    actor=request.actor,
                    transformation_result=transform_result,
                    evidence_result=ev_result,
                    artifact_set_checksum=record.artifact_set_checksum,
                    workspace_fingerprint=record.workspace_fingerprint,
                    package_checksum=record.package_checksum,
                ),
                request.decision,
                comment=request.comment,
            )

            event_type = self._decision_event_type(result.decision)
            transition = StateTransitionService(session).apply_transition(
                TransitionRequest(
                    run_id=run_id,
                    expected_state_version=run.state_version,
                    idempotency_key=request.idempotency_key,
                    event_type=event_type,
                    actor=request.actor,
                    reason=result.reason or f"G08 decision: {result.decision.value}",
                    occurred_at=now,
                    stage_id=stage_id,
                    payload={
                        "package_checksum": record.package_checksum,
                        "decision": result.decision.value,
                        "stage_id": stage_id,
                    },
                )
            )

            record.status = "stale" if result.stale else result.decision.value
            record.decision = result.decision.value
            record.state_version = transition.next_state_version
            record.event_sequence = transition.event_sequence
            record.updated_at = now
            session.flush()
            return self._dto(record)

    def _create_pending_record(self, session, run, stage_id: str, actor: str, idempotency_key: str, now: datetime):
        """Create a pending G08 approval record with evidence package."""
        store = LocalFilesystemArtifactStore(
            Path(run.artifact_root), fixed_run_root=Path(run.artifact_root)
        ) if run.artifact_root else None

        # Collect artifact refs from transformation and evidence records
        transform_record = session.scalar(
            select(AngularUpdateRecordModel)
            .where(AngularUpdateRecordModel.run_id == run.id)
            .where(AngularUpdateRecordModel.stage_id == stage_id)
            .order_by(AngularUpdateRecordModel.created_at.desc())
        )
        evidence_record = session.scalar(
            select(TransformationEvidenceModel)
            .where(TransformationEvidenceModel.run_id == run.id)
            .where(TransformationEvidenceModel.stage_id == stage_id)
            .order_by(TransformationEvidenceModel.created_at.desc())
        )

        artifact_refs: list[ArtifactRefDto] = []
        artifact_ids: list[str] = []

        # Emit G08_CREATED event to get a real event sequence
        creation_transition = StateTransitionService(session).apply_transition(
            TransitionRequest(
                run_id=run.id,
                expected_state_version=run.state_version,
                idempotency_key=f"{idempotency_key}:g08-created",
                event_type=WorkflowEventType.G08_CREATED,
                actor=actor,
                reason="G08 evidence package initialized",
                occurred_at=now,
                stage_id=stage_id,
                payload={"gate_version": self.GATE_VERSION, "stage_id": stage_id},
            ),
        )

        if store:
            # Build G08 evidence index artifact
            g08_payload = {
                "gate_version": self.GATE_VERSION,
                "transform_record_id": transform_record.id if transform_record else None,
                "evidence_record_id": evidence_record.id if evidence_record else None,
                "transform_artifact_ids": (transform_record.artifact_ids or []) if transform_record else [],
                "evidence_artifact_ids": (evidence_record.artifact_ids or []) if evidence_record else [],
            }
            ref = _write_evidence(
                store, session, run.id, f"g08_evidence_index_{stage_id}.json",
                g08_payload,
                stage_id=stage_id,
                created_by="g08-approval-service",
                created_at=now,
            )
            artifact_refs.append(ref)
            artifact_ids.append(ref.artifact_id)

        # Build the evidence package
        transform_result = AngularUpdateResult(
            run_id=run.id, stage_id=stage_id,
            update_status=AngularUpdateStatus(transform_record.status) if transform_record else AngularUpdateStatus.FAILED,
            target_version_status=TargetVersionStatus(transform_record.target_version_status) if transform_record else TargetVersionStatus.INCONCLUSIVE,
            resolved_target_version=transform_record.resolved_target_version if transform_record else None,
        )
        ev_result = TransformationEvidenceResult(
            run_id=run.id, stage_id=stage_id,
            diff=DiffSummary(
                total_files_changed=evidence_record.total_files_changed if evidence_record else 0,
                total_lines_added=0, total_lines_removed=0,
                diff_checksum=evidence_record.diff_checksum if evidence_record else "sha256:" + "0" * 64,
            ),
            evidence_complete=evidence_record.evidence_complete if evidence_record else False,
            overall_risk_level=RiskLevel(evidence_record.overall_risk_level) if evidence_record else RiskLevel.HIGH,
        )

        package = G08EvidencePackageBuilder().build(
            run_id=run.id, stage_id=stage_id,
            state_version=run.state_version, actor=actor,
            gate_version=self.GATE_VERSION,
            transformation_result=transform_result,
            evidence_result=ev_result,
            artifacts=artifact_refs,
            workspace_fingerprint=f"sha256:{uuid4().hex}",
        )

        record = G08ApprovalModel(
            id=f"g08-{uuid4().hex[:12]}",
            run_id=run.id,
            stage_id=stage_id,
            gate_id=self.GATE_ID,
            gate_version=package.gate_version,
            idempotency_key=idempotency_key,
            actor=actor,
            status="pending",
            package_checksum=package.package_checksum,
            artifact_set_checksum=package.artifact_set_checksum,
            workspace_fingerprint=package.workspace_fingerprint,
            state_version=creation_transition.next_state_version,
            event_sequence=creation_transition.event_sequence,
            package=package.model_dump(mode="json"),
            artifact_ids=artifact_ids,
            created_at=now,
            updated_at=now,
        )
        session.add(record)
        session.flush()
        return record

    def _decision_event_type(self, decision: G08Decision) -> WorkflowEventType:
        mapping = {
            G08Decision.APPROVED: WorkflowEventType.G08_APPROVED,
            G08Decision.APPROVED_WITH_COMMENT: WorkflowEventType.G08_APPROVED,
            G08Decision.MODIFICATION_REQUESTED: WorkflowEventType.G08_MODIFICATION_REQUESTED,
            G08Decision.REJECTED: WorkflowEventType.G08_REJECTED,
        }
        return mapping.get(decision, WorkflowEventType.G08_REJECTED)

    def _dto(self, record, *, replay=False):
        from app.api.transformation_contracts import G08ReviewResponse

        return G08ReviewResponse(
            run_id=record.run_id,
            stage_id=record.stage_id,
            gate_id=record.gate_id,
            gate_version=record.gate_version,
            status=record.status,
            decision=record.decision,
            package=record.package,
            package_checksum=record.package_checksum,
            artifact_set_checksum=record.artifact_set_checksum,
            workspace_fingerprint=record.workspace_fingerprint,
            state_version=record.state_version,
            event_sequence=record.event_sequence,
            idempotent_replay=replay,
            stale_reason=record.stale_reason,
            comment=record.comment,
        )
