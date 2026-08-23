"""Repair governance classifier (V2.3 Phase 7).

Every failure enters the repair decision ladder through ``FailureClassifier``
and exits with exactly one governed decision.  The ladder is strictly
ordered and each rung must either resolve deterministically or defer to the
next rung:

    1. deterministic repair
    2. Stage Knowledge repair
    3. compatibility catalogue repair
    4. LLM proposer
    5. reviewer
    6. human approval

The LLM proposer only ever receives a bounded ``FailureBundle`` (envelope +
relevant files + migration context) — never the complete workspace or
uncontrolled logs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from app.domain.proven_failure import (
    FailureBundle,
    FailureOwner,
    MigrationFailureEnvelope,
)


class RepairDecision(str, Enum):
    NONE = "none"
    DETERMINISTIC = "deterministic"
    STAGE_KNOWLEDGE = "stage_knowledge"
    CATALOGUE = "catalogue"
    LLM_PROPOSER = "llm_proposer"
    REVIEWER = "reviewer"
    HUMAN_APPROVAL = "human_approval"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class ClassificationResult:
    decision: RepairDecision
    ladder_step: int
    reason: str
    repair_intent: dict[str, object] | None = None
    owner: FailureOwner | None = None
    bundle: FailureBundle | None = None


class FailureClassifier:
    """Deterministic repair-governance ladder (V2.3 Phase 7).

    The classifier is stateless by design: every rung derives its answer from
    the envelope, the supplied deterministic providers, and the bounded
    bundle — never from ambient process state.
    """

    def __init__(
        self,
        *,
        stage_knowledge: object | None = None,
        catalogue: object | None = None,
        llm_proposer=None,
        reviewer=None,
    ) -> None:
        # Lazy import contracts so the classifier is importable without the
        # full backend stack; providers are wired by the service layer.
        self._stage_knowledge = stage_knowledge
        self._catalogue = catalogue
        self._llm_proposer = llm_proposer
        self._reviewer = reviewer

    def classify(
        self,
        *,
        envelope: MigrationFailureEnvelope,
        bundle: FailureBundle | None = None,
        source_major: int | None = None,
        target_major: int | None = None,
        normalized_diagnostics: tuple[dict[str, str], ...] = (),
        observed_capabilities: dict[str, str] | None = None,
        current_preimage_sha256: str | None = None,
    ) -> ClassificationResult:
        # Rung 1: deterministic repair.  Only repair-allowed envelopes whose
        # owner is a deterministic surface qualify; everything else skips.
        if envelope.repair_allowed and envelope.owner in {
            FailureOwner.DEPENDENCY,
            FailureOwner.ANGULAR_MIGRATION,
            FailureOwner.LOCK_RESOLVER,
        }:
            deterministic = self._deterministic_repair(envelope)
            if deterministic is not None:
                return ClassificationResult(
                    RepairDecision.DETERMINISTIC, 1, "deterministic repair resolved the failure", deterministic
                )
        # Rung 2: Stage Knowledge repair (versioned deterministic rules).
        if self._stage_knowledge is not None and source_major and target_major:
            knowledge = self._stage_knowledge_repair(
                envelope,
                source_major=source_major,
                target_major=target_major,
                normalized_diagnostics=normalized_diagnostics,
                observed_capabilities=observed_capabilities or {},
                current_preimage_sha256=current_preimage_sha256,
            )
            if knowledge is not None:
                return ClassificationResult(
                    RepairDecision.STAGE_KNOWLEDGE, 2, "stage knowledge rule matched", knowledge
                )
        # Rung 3: compatibility catalogue repair (cohort/toolchain advice).
        if self._catalogue is not None:
            catalogue_repair = self._catalogue_repair(envelope)
            if catalogue_repair is not None:
                return ClassificationResult(
                    RepairDecision.CATALOGUE, 3, "compatibility catalogue repair", catalogue_repair
                )
        # Rung 4: LLM proposer over the bounded FailureBundle.
        if self._llm_proposer is not None and bundle is not None:
            proposal = self._llm_proposer(bundle)
            if proposal is not None:
                return ClassificationResult(
                    RepairDecision.LLM_PROPOSER, 4, "LLM proposer produced a candidate", proposal, bundle=bundle
                )
        # Rung 5: reviewer.
        if self._reviewer is not None and bundle is not None:
            review = self._reviewer(bundle)
            if review is not None:
                return ClassificationResult(
                    RepairDecision.REVIEWER, 5, "reviewer accepted the repair", review, bundle=bundle
                )
        # Rung 6: human approval.  A repair-allowed envelope escalates to a
        # human decision; a non-repairable envelope escalates with reason.
        if envelope.repair_allowed:
            return ClassificationResult(
                RepairDecision.HUMAN_APPROVAL,
                6,
                "no deterministic repair; human approval required",
                bundle=bundle,
            )
        return ClassificationResult(
            RepairDecision.ESCALATE,
            6,
            "failure is not repairable under the current ladder",
            bundle=bundle,
        )

    # -- rung implementations ------------------------------------------------

    @staticmethod
    def _deterministic_repair(envelope: MigrationFailureEnvelope) -> dict[str, object] | None:
        """Rung 1: deterministic repair table for known failure codes.

        Only exact codes bound to a deterministic surface resolve here; any
        other code defers to later rungs.
        """
        table = {
            "ERESOLVE": {"operation_type": "dependency_manifest_normalization", "reason": "npm peer resolution conflict"},
            "ETARGET": {"operation_type": "target_version_reconciliation", "reason": "requested target not resolvable"},
            "ERESOLVE_OVERRIDABLE": {"operation_type": "peer_conflict_reconciliation", "reason": "overridable peer conflict"},
        }
        return table.get(envelope.code)

    def _stage_knowledge_repair(
        self,
        envelope: MigrationFailureEnvelope,
        *,
        source_major: int,
        target_major: int,
        normalized_diagnostics: tuple[dict[str, str], ...],
        observed_capabilities: dict[str, str],
        current_preimage_sha256: str | None,
    ) -> dict[str, object] | None:
        try:
            from app.services.stage_knowledge_service import StageKnowledgeRegistry

            entry = StageKnowledgeRegistry().entry(source_major, target_major)
            outcome = StageKnowledgeRegistry.evaluate_deterministic_candidate(
                rules=tuple(entry.rules if hasattr(entry, "rules") else ()),
                normalized_diagnostics=normalized_diagnostics,
                observed_capabilities=observed_capabilities,
                current_preimage_sha256=current_preimage_sha256,
                candidate_root_prefix=envelope.workspace or "",
            )
        except Exception:
            return None
        return outcome.get("operation") if outcome.get("outcome") == "MATCH" else None

    def _catalogue_repair(self, envelope: MigrationFailureEnvelope) -> dict[str, object] | None:
        """Rung 3: catalogue-bound repair advice for dependency failures."""
        if envelope.category.value not in {"install", "lock_resolution"}:
            return None
        try:
            from app.services.compatibility_catalogue_provider import CompatibilityCatalogueProvider

            entry = CompatibilityCatalogueProvider().load().entry_for(
                f"angular-{envelope.runtime}" if envelope.runtime else "angular-11.x",
                f"angular-{envelope.phase}" if envelope.phase in {str(i) for i in range(12, 22)} else "angular-12.x",
            )
            if entry is None:
                return None
        except Exception:
            return None
        return {
            "operation_type": "catalogue_reconciliation",
            "advice_source": "compatibility-catalogue",
            "catalogue_entry": entry.catalogue_id,
        }

    @staticmethod
    def bundle_checksum(bundle: FailureBundle) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(bundle.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()