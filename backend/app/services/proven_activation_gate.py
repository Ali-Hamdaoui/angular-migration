"""Proven Transformer activation gate (V2.3 activation).

The gate verifies that the proven execution layer is structurally complete
before it enables proven-plan writing.  Every check is a real, importable
contract lookup — nothing is assumed present.  A missing prerequisite
returns ``TRANSFORMER_PROVEN_ACTIVATION_BLOCKED`` with the exact missing
items; the writer flag stays False until every check passes.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field


TRANSFORMER_PROVEN_ACTIVATION_BLOCKED = "TRANSFORMER_PROVEN_ACTIVATION_BLOCKED"


class ProvenActivationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProvenActivationReport:
    """Structural readiness result of one activation gate evaluation."""

    passed: bool
    missing: tuple[str, ...] = field(default_factory=tuple)
    enabled_writer: bool = False

    def block_code(self) -> str:
        return None if self.passed else TRANSFORMER_PROVEN_ACTIVATION_BLOCKED


#: Required proven command templates.  Each must resolve in the frozen command
#: catalogue before any proven plan may reference it.
PROVEN_REQUIRED_COMMAND_IDS = frozenset(
    {
        "npm-ci-bootstrap",
        "npm-dependency-tree",
        "angular-version-verify",
        "npm-ci-final",
        "npm-lockfile-generate",
        "npm-script-build-production",
        "npm-script-test-ci",
        "angular-cli-authority-version",
        "angular-update-discovery",
        "angular-migrate-range-v2",
        "angular-migrate-name-v2",
    }
)


class ProvenActivationGate:
    """Structural gate for the proven execution layer.

    Checks, in order:

    1. command templates exist in the frozen catalogue,
    2. graph handlers exist for every proven transition node,
    3. failure routes exist (FailureRoute vocabulary + classifier),
    4. seal flow exists (stage sealing + transformer sealing flow),
    5. recovery handlers exist (stage recovery + replan recovery).

    ``activate()`` flips ``proven_plan_writer_enabled`` only when every check
    passes; a blocked report never flips the flag.
    """

    def verify(self) -> ProvenActivationReport:
        missing: list[str] = []
        if not self._command_templates_exist():
            missing.append("command_templates")
        if not self._graph_handlers_exist():
            missing.append("graph_handlers")
        if not self._failure_routes_exist():
            missing.append("failure_routes")
        if not self._seal_flow_exists():
            missing.append("seal_flow")
        if not self._recovery_handlers_exist():
            missing.append("recovery_handlers")
        return ProvenActivationReport(passed=not missing, missing=tuple(missing))

    def activate(self) -> ProvenActivationReport:
        report = self.verify()
        if report.passed:
            from app.domain.planning import set_proven_plan_writer_enabled

            set_proven_plan_writer_enabled(True)
            return ProvenActivationReport(
                passed=True, enabled_writer=True
            )
        return report

    # -- individual checks -------------------------------------------------

    @staticmethod
    def _command_templates_exist() -> bool:
        try:
            from app.domain.command import TRANSFORMATION_COMMAND_CATALOGUE
        except ImportError:
            return False
        return PROVEN_REQUIRED_COMMAND_IDS.issubset(TRANSFORMATION_COMMAND_CATALOGUE)

    @staticmethod
    def _graph_handlers_exist() -> bool:
        try:
            from app.domain.transformation import PROVEN_TRANSITION_NODES
            from app.orchestration.transformer_graph import PROVEN_ROUTING
        except ImportError:
            return False
        return PROVEN_TRANSITION_NODES.issubset(PROVEN_ROUTING)

    @staticmethod
    def _failure_routes_exist() -> bool:
        try:
            from app.domain.transformation import FailureRoute
            from app.services.failure_evidence_service import FailureEvidenceService
        except ImportError:
            return False
        if not {route.value for route in FailureRoute}:
            return False
        return callable(FailureEvidenceService.classify)

    @staticmethod
    def _seal_flow_exists() -> bool:
        try:
            importlib.import_module("app.services.stage_sealing_service")
            importlib.import_module("app.orchestration.transformer_sealing_flow")
        except ImportError:
            return False
        return True

    @staticmethod
    def _recovery_handlers_exist() -> bool:
        try:
            importlib.import_module("app.services.stage_recovery_service")
            importlib.import_module("app.services.transformation_replan_recovery_service")
        except ImportError:
            return False
        return True