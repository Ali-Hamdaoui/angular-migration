"""Stage knowledge provider and registry (V2 F17)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.migration_route import validate_envelope
from app.domain.stage_knowledge import StageKnowledgeEntry, knowledge_entry_for
from app.repositories.models import StageKnowledgeEntryModel
from app.repositories.session import session_scope


class StageKnowledgeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StageKnowledgeRegistry:
    """Seed, version, audit, and query stage knowledge entries (F17-03)."""

    def __init__(
        self,
        *,
        session_scope_factory: Callable[[], AbstractContextManager] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_scope = session_scope_factory or session_scope
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def entry(self, source_major: int, target_major: int) -> StageKnowledgeEntry:
        """Return the stage knowledge entry for a transition (deterministic)."""
        blocker = validate_envelope(source_major, target_major)
        if blocker:
            raise StageKnowledgeError("ENVELOPE_VIOLATION", blocker)
        if target_major != source_major + 1:
            raise StageKnowledgeError("NOT_ADJACENT", "stage knowledge is per adjacent-major transition")
        return knowledge_entry_for(source_major, target_major)

    def entries(self) -> list[StageKnowledgeEntry]:
        return [knowledge_entry_for(major, major + 1) for major in range(11, 21)]

    @staticmethod
    def dependency_dispositions(
        entry: StageKnowledgeEntry,
        capabilities: list | tuple = (),
    ) -> tuple[dict[str, str], ...]:
        """Apply structured stage rules only to observed project capabilities."""
        observed = {
            capability["key"] if isinstance(capability, dict) else capability.key: "present"
            for capability in capabilities
        }
        changes = list(entry.expected_dependency_changes)
        for rule in entry.dependency_rules:
            if observed.get(rule["capability"]) != "present":
                continue
            changes.append(
                {
                    "package": rule["package"],
                    "action": rule["action"],
                    "source": "capability-rule",
                }
            )
        return tuple(changes)

    def persist(self, entry: StageKnowledgeEntry, *, actor: str | None = None, reason: str | None = None) -> StageKnowledgeEntryModel:
        """Persist a knowledge entry version with an audit record (F17-03)."""
        with self._session_scope() as session:
            existing = session.scalar(
                select(StageKnowledgeEntryModel).where(
                    StageKnowledgeEntryModel.source_major == entry.source_major,
                    StageKnowledgeEntryModel.target_major == entry.target_major,
                    StageKnowledgeEntryModel.version == entry.version,
                )
            )
            if existing is not None:
                return existing
            row = StageKnowledgeEntryModel(
                id=_entry_id(entry.source_major, entry.target_major, entry.version),
                source_major=entry.source_major,
                target_major=entry.target_major,
                expected_transforms=list(entry.expected_transforms),
                validation_expectations=list(entry.validation_expectations),
                expected_dependency_changes=[dict(item) for item in entry.expected_dependency_changes],
                dependency_rules=[dict(item) for item in entry.dependency_rules],
                migration_actions=[dict(item) for item in entry.migration_actions],
                known_risks=list(entry.known_risks),
                version=entry.version,
                created_by=actor,
                change_reason=reason,
                notes=entry.notes,
                created_at=self._now_provider(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def list_persisted(self) -> list[StageKnowledgeEntryModel]:
        with self._session_scope() as session:
            return list(session.scalars(select(StageKnowledgeEntryModel).order_by(StageKnowledgeEntryModel.source_major.asc())).all())

    def for_transition(self, source_major: int, target_major: int) -> StageKnowledgeEntryModel | None:
        with self._session_scope() as session:
            return session.scalar(
                select(StageKnowledgeEntryModel).where(
                    StageKnowledgeEntryModel.source_major == source_major,
                    StageKnowledgeEntryModel.target_major == target_major,
                ).order_by(StageKnowledgeEntryModel.version.desc()).limit(1)
            )


def _entry_id(source_major: int, target_major: int, version: int) -> str:
    return "sk-" + hashlib.sha256(f"{source_major}:{target_major}:{version}".encode()).hexdigest()[:24]
