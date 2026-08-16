"""Candidate workspace promotion service (V2 F22)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.domain.candidate_promotion import CandidatePromotionDecision
from app.domain.workspace_authority import WorkspacePromotionRequest
from app.repositories.models import CandidatePromotionModel, MigrationRunModel, MigrationStageModel
from app.repositories.session import session_scope
from app.services.workspace_authority_service import WorkspaceAuthorityService


class CandidatePromotionError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class CandidatePromotionService:
    """Apply, validate, and atomically promote candidate workspaces (F22)."""

    def __init__(
        self,
        *,
        workspace_authority: WorkspaceAuthorityService | None = None,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._authority = workspace_authority or WorkspaceAuthorityService()
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def _stage_context(self, stage_id: str) -> tuple[str, str, str | None]:
        with self._session_scope() as session:
            stage = session.get(MigrationStageModel, stage_id)
            if stage is None:
                raise CandidatePromotionError("STAGE_NOT_FOUND", f"Migration stage {stage_id} not found")
            run = session.get(MigrationRunModel, stage.run_id)
            return (stage.run_id, stage.source_version_family or "", run.run_root if run else None)

    def validate_candidate(self, workspace: Path, *, run_id: str, stage_id: str) -> CandidatePromotionDecision:
        """Validate a candidate workspace (F22-02).

        Runs deterministic preconditions: the candidate must be inside the run's
        sanctioned root, exist, and contain a package.json.  The candidate is
        an externally-produced workspace (diff application materializes in the
        existing patch-apply authority); this gate validates before promotion.
        """
        stage_run_id, _, run_root = self._stage_context(stage_id)
        if stage_run_id != run_id:
            raise CandidatePromotionError("RUN_ID_MISMATCH", f"stage {stage_id} belongs to run {stage_run_id}, not {run_id}")
        generation = self._next_generation(run_id, stage_id)
        blockers: list[str] = []
        resolved = workspace.resolve(strict=False)
        if not run_root:
            blockers.append("CANDIDATE_NO_RUN_ROOT")
        elif not _within_root(resolved, Path(run_root).resolve(strict=False)):
            blockers.append("CANDIDATE_OUTSIDE_RUN_ROOT")
        # The filesystem is only touched for candidates that pass containment;
        # out-of-root/missing candidates get a sentinel fingerprint (no oracle).
        if not blockers:
            if not resolved.is_dir():
                blockers.append("CANDIDATE_WORKSPACE_MISSING")
            elif not (resolved / "package.json").is_file():
                blockers.append("CANDIDATE_PACKAGE_JSON_MISSING")
        fingerprint = _dir_fingerprint(resolved) if not blockers else "none"
        status = "candidate_ready" if not blockers else "rejected"
        decision = CandidatePromotionDecision(
            run_id=run_id,
            stage_id=stage_id,
            alias=_stage_alias(stage_id),
            candidate_fingerprint=fingerprint,
            generation=generation,
            status=status,
            validated=not blockers,
            blockers=tuple(blockers),
            previous_generation=self._previous_generation(run_id, stage_id),
        )
        return decision.bind_checksum()

    def promote_candidate(self, *, run_id: str, stage_id: str, candidate_path: Path) -> CandidatePromotionDecision:
        """Atomically promote a validated candidate to the next generation (F22-03).

        Uses the workspace authority's monotonic generation guard; a candidate
        that fails validation is rejected and the last-good generation stays
        active (rollback safety, F22-04).
        """
        validation = self.validate_candidate(candidate_path, run_id=run_id, stage_id=stage_id)
        if not validation.validated:
            decision = validation.model_copy(update={"status": "rejected"})
            return decision.bind_checksum()
        alias = _stage_alias(stage_id)
        request = WorkspacePromotionRequest(
            run_id=run_id,
            stage_id=stage_id,
            alias=alias,
            generation=validation.generation,
            workspace_path=str(candidate_path),
            fingerprint=validation.candidate_fingerprint,
        )
        from app.services.workspace_authority_service import WorkspaceAuthorityError

        try:
            self._authority.promote(request)
        except WorkspaceAuthorityError as exc:
            rejected = validation.model_copy(update={"status": "rollback_required", "blockers": (f"PROMOTION_FAILED:{exc.code}",)})
            return rejected.bind_checksum()
        promoted = validation.model_copy(update={"status": "promoted", "validated": True})
        return promoted.bind_checksum()

    def rollback_safety(self, *, run_id: str, stage_id: str) -> CandidatePromotionDecision:
        """Confirm the last-good generation is still active (rollback safety).

        The workspace authority retires superseded generations but the current
        active generation remains intact; a failed promotion never removes it.
        """
        alias = _stage_alias(stage_id)
        active = self._authority.resolve_active(run_id, stage_id, alias)
        if active is None:
            return CandidatePromotionDecision(
                run_id=run_id, stage_id=stage_id, alias=alias,
                candidate_fingerprint="none", generation=1,
                status="rollback_required", blockers=("NO_ACTIVE_WORKSPACE",),
                previous_generation=None,
            ).bind_checksum()
        return CandidatePromotionDecision(
            run_id=run_id, stage_id=stage_id, alias=alias,
            candidate_fingerprint=active.fingerprint, generation=active.generation,
            status="promoted", validated=True, previous_generation=active.generation,
        ).bind_checksum()

    def _next_generation(self, run_id: str, stage_id: str) -> int:
        current = self._authority.current_generation(run_id, stage_id, _stage_alias(stage_id))
        return (current or 0) + 1

    def _previous_generation(self, run_id: str, stage_id: str) -> int | None:
        return self._authority.current_generation(run_id, stage_id, _stage_alias(stage_id))

    def persist(self, decision: CandidatePromotionDecision) -> CandidatePromotionModel:
        with self._session_scope() as session:
            existing = session.scalar(
                select(CandidatePromotionModel).where(
                    CandidatePromotionModel.stage_id == decision.stage_id,
                    CandidatePromotionModel.checksum == decision.checksum,
                )
            )
            if existing is not None:
                return existing
            row = CandidatePromotionModel(
                id="cp-" + hashlib.sha256(f"{decision.stage_id}:{decision.checksum}".encode()).hexdigest()[:24],
                run_id=decision.run_id,
                stage_id=decision.stage_id,
                alias=decision.alias,
                candidate_fingerprint=decision.candidate_fingerprint,
                generation=decision.generation,
                status=decision.status,
                validated=decision.validated,
                blockers=list(decision.blockers),
                previous_generation=decision.previous_generation,
                checksum=decision.checksum,
                created_at=self._now_provider(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def list_stage_promotions(self, stage_id: str) -> list[CandidatePromotionModel]:
        with self._session_scope() as session:
            return list(
                session.scalars(
                    select(CandidatePromotionModel)
                    .where(CandidatePromotionModel.stage_id == stage_id)
                    .order_by(CandidatePromotionModel.created_at.desc())
                ).all()
            )


def _within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _stage_alias(stage_id: str) -> str:
    return f"STAGE_WORKSPACE_{stage_id[:20].upper()}"


def _dir_fingerprint(workspace: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(workspace.rglob("*")):
        if path.is_symlink():
            continue
        if path.is_file() and "node_modules" not in path.parts:
            digest.update(path.relative_to(workspace).as_posix().encode())
            digest.update(b":")
            try:
                digest.update(path.read_bytes()[:4096])
            except OSError:
                pass
            digest.update(b";")
    return "sha256:" + digest.hexdigest()
