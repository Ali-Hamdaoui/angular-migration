"""Unified migration failure envelope (V2.3 error normalization).

Every failure that crosses the backend execution boundary is normalized into
one ``MigrationFailureEnvelope`` so consumers (runner, repair governance,
qualification) never re-parse raw command output.  Each envelope binds the
owning phase/category, the exact failed command identity, bounded stdout/
stderr, workspace and runtime context, and an evidence checksum over the
immutable failure facts.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from app.domain.contracts import ContractModel


class FailureCategory(str, Enum):
    INSTALL = "install"
    ANGULAR_UPDATE = "angular_update"
    BUILD = "build"
    TEST = "test"
    DISCOVERY = "discovery"
    LOCK_RESOLUTION = "lock_resolution"
    MIGRATION = "migration"
    VALIDATION = "validation"
    PROMOTION = "promotion"
    SEAL = "seal"
    ENVIRONMENT = "environment"
    UNKNOWN = "unknown"


class FailureOwner(str, Enum):
    """Every failure has exactly one owner; never the whole LLM by default."""

    DEPENDENCY = "dependency"
    ANGULAR_MIGRATION = "angular_migration"
    SOURCE_TRANSFORMATION = "source_transformation"
    VALIDATION = "validation"
    LOCK_RESOLVER = "lock_resolver"
    PLATFORM_RECOVERY = "platform_recovery"
    DETERMINISTIC_REPAIR = "deterministic_repair"
    MAIN_REPAIR_LLM = "main_repair_llm"
    HUMAN = "human"


#: Ownership table (V2.3): INSTALL -> dependency owner, ANGULAR UPDATE ->
#: angular migration owner, BUILD -> source/transformation owner, TEST ->
#: validation owner.  Anything unclassified keeps the category owner and
#: never routes to the LLM without an explicit classification.
CATEGORY_OWNER: dict[str, FailureOwner] = {
    FailureCategory.INSTALL.value: FailureOwner.DEPENDENCY,
    FailureCategory.ANGULAR_UPDATE.value: FailureOwner.ANGULAR_MIGRATION,
    FailureCategory.BUILD.value: FailureOwner.SOURCE_TRANSFORMATION,
    FailureCategory.TEST.value: FailureOwner.VALIDATION,
    FailureCategory.DISCOVERY.value: FailureOwner.ANGULAR_MIGRATION,
    FailureCategory.LOCK_RESOLUTION.value: FailureOwner.LOCK_RESOLVER,
    FailureCategory.MIGRATION.value: FailureOwner.ANGULAR_MIGRATION,
    FailureCategory.VALIDATION.value: FailureOwner.VALIDATION,
    FailureCategory.PROMOTION.value: FailureOwner.SOURCE_TRANSFORMATION,
    FailureCategory.SEAL.value: FailureOwner.PLATFORM_RECOVERY,
    FailureCategory.ENVIRONMENT.value: FailureOwner.PLATFORM_RECOVERY,
    FailureCategory.UNKNOWN.value: FailureOwner.HUMAN,
}

#: Phase vocabulary mirrors the proven graph's macro phases.
FAILURE_PHASES = frozenset(
    {
        "baseline",
        "discovery",
        "lock_resolution",
        "materialization",
        "migration_execution",
        "validation",
        "promotion",
        "repair",
        "seal",
    }
)


def _checksum(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _bounded(value: str | None, limit: int = 200_000) -> str:
    if not value:
        return ""
    return value if len(value) <= limit else value[:limit]


class MigrationFailureEnvelope(ContractModel):
    """One normalized migration failure crossing the execution boundary.

    ``evidence_checksum`` binds the deterministic failure facts (category,
    phase, code, command identity, bounded streams, workspace identity,
    runtime identity); it never binds wall-clock timestamps so identical
    failures replay with identical evidence.
    """

    schema_version: str = "migration-failure-envelope-v1"
    category: FailureCategory
    phase: str
    code: str
    message: str
    command_id: str | None = None
    execution_id: str | None = None
    stdout: str = ""
    stderr: str = ""
    workspace: str | None = None
    runtime: str | None = None
    recoverable: bool = False
    repair_allowed: bool = False
    owner: FailureOwner | None = None
    evidence_checksum: str | None = None

    @classmethod
    def create(
        cls,
        *,
        category: FailureCategory,
        phase: str,
        code: str,
        message: str,
        command_id: str | None = None,
        execution_id: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        workspace: str | None = None,
        runtime: str | None = None,
        recoverable: bool = False,
        repair_allowed: bool = False,
        owner: FailureOwner | None = None,
    ) -> "MigrationFailureEnvelope":
        if phase not in FAILURE_PHASES and phase != "unknown":
            raise ValueError(f"unknown failure phase: {phase}")
        resolved_owner = owner or CATEGORY_OWNER.get(category.value, FailureOwner.HUMAN)
        envelope = cls(
            category=category,
            phase=phase,
            code=code,
            message=message,
            command_id=command_id,
            execution_id=execution_id,
            stdout=_bounded(stdout),
            stderr=_bounded(stderr),
            workspace=workspace,
            runtime=runtime,
            recoverable=recoverable,
            repair_allowed=repair_allowed,
            owner=resolved_owner,
        )
        facts = {
            "category": envelope.category.value,
            "phase": envelope.phase,
            "code": envelope.code,
            "command_id": envelope.command_id,
            "execution_id": envelope.execution_id,
            "stdout": envelope.stdout,
            "stderr": envelope.stderr,
            "workspace": envelope.workspace,
            "runtime": envelope.runtime,
            "recoverable": envelope.recoverable,
            "repair_allowed": envelope.repair_allowed,
            "owner": envelope.owner.value,
        }
        return envelope.model_copy(update={"evidence_checksum": _checksum(facts)})

    def with_owner(self, owner: FailureOwner) -> "MigrationFailureEnvelope":
        """Rebind the failure owner (used by the classifier decision ladder)."""
        return self.model_copy(update={"owner": owner})


class FailureBundle(ContractModel):
    """Bounded LLM input for a classified failure (Phase 7).

    Never contains the complete workspace or uncontrolled logs: only the
    envelope, a bounded set of relevant relative file paths, and the bounded
    migration context.
    """

    schema_version: str = "failure-bundle-v1"
    envelope: MigrationFailureEnvelope
    relevant_files: tuple[str, ...] = ()
    file_contents: tuple[tuple[str, str], ...] = ()  # (relative_path, bounded content)
    migration_context: dict[str, str] = {}
    bundle_checksum: str | None = None

    @classmethod
    def create(
        cls,
        *,
        envelope: MigrationFailureEnvelope,
        relevant_files: tuple[str, ...] = (),
        file_contents: tuple[tuple[str, str], ...] = (),
        migration_context: dict[str, str] | None = None,
    ) -> "FailureBundle":
        bounded_files = tuple(
            (path, _bounded(content, limit=50_000))
            for path, content in file_contents
        )
        bundle = cls(
            envelope=envelope,
            relevant_files=tuple(sorted(set(relevant_files))),
            file_contents=bounded_files,
            migration_context=dict(migration_context or {}),
        )
        facts = {
            "envelope": envelope.model_dump(mode="json"),
            "relevant_files": bundle.relevant_files,
            "migration_context": bundle.migration_context,
        }
        return bundle.model_copy(update={"bundle_checksum": _checksum(facts)})


def envelope_from_execution(
    *,
    category: FailureCategory,
    phase: str,
    code: str,
    message: str,
    command_id: str | None = None,
    execution_id: str | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    workspace: str | None = None,
    runtime: str | None = None,
) -> MigrationFailureEnvelope:
    """Normalize one command failure into a checksum-bound envelope.

    Repair is allowed only when the failure is classified as recoverable AND
    the category owner is a deterministic repair surface (dependency, angular
    migration, source transformation, lock resolver).  Everything else must
    escalate through the classifier before any repair is allowed.
    """
    owner = CATEGORY_OWNER.get(category.value, FailureOwner.HUMAN)
    repair_surface = owner in {
        FailureOwner.DEPENDENCY,
        FailureOwner.ANGULAR_MIGRATION,
        FailureOwner.SOURCE_TRANSFORMATION,
        FailureOwner.LOCK_RESOLVER,
    }
    return MigrationFailureEnvelope.create(
        category=category,
        phase=phase,
        code=code,
        message=message,
        command_id=command_id,
        execution_id=execution_id,
        stdout=stdout,
        stderr=stderr,
        workspace=workspace,
        runtime=runtime,
        recoverable=True,
        repair_allowed=repair_surface,
    )