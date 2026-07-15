"""Single authority for the externally-owned migration workspace layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class WorkspaceLayoutError(ValueError):
    """Raised when a registered layout would leave its output root."""


@dataclass(frozen=True)
class MigrationWorkspaceLayout:
    output_root: Path
    migrated_app: Path
    migration_factory_root: Path
    metadata_root: Path
    run_root: Path
    source_snapshot: Path
    baseline_sandbox: Path
    stage_sandbox_root: Path
    repair_sandbox_root: Path
    final_assurance_sandbox: Path
    delivery_candidate: Path
    artifact_root: Path
    log_root: Path
    report_root: Path
    temporary_root: Path

    def aliases(self) -> dict[str, str]:
        return {"OUTPUT_ROOT": str(self.output_root), "MIGRATED_APP": str(self.migrated_app), "MIGRATION_FACTORY_ROOT": str(self.migration_factory_root), "RUN_ROOT": str(self.run_root), "SOURCE_SNAPSHOT": str(self.source_snapshot), "BASELINE_SANDBOX": str(self.baseline_sandbox), "STAGE_SANDBOX": str(self.stage_sandbox_root), "REPAIR_SANDBOX": str(self.repair_sandbox_root), "FINAL_ASSURANCE_SANDBOX": str(self.final_assurance_sandbox), "DELIVERY_CANDIDATE": str(self.delivery_candidate), "ARTIFACT_ROOT": str(self.artifact_root), "LOG_ROOT": str(self.log_root), "REPORT_ROOT": str(self.report_root), "TEMPORARY_ROOT": str(self.temporary_root)}


class MigrationWorkspaceLayoutService:
    """Derive every migration path from the registered external output root."""

    layout_version = "external-output-layout-v1"

    def __init__(self, *, platform_repository_root: Path | None = None) -> None:
        self._repository_root = platform_repository_root.resolve() if platform_repository_root else None

    def for_run(self, resolved_output_root: str | Path, run_id: str) -> MigrationWorkspaceLayout:
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise WorkspaceLayoutError("run ID is not a safe path component")
        output = Path(resolved_output_root).expanduser().resolve(strict=False)
        if self._repository_root and self._contains(self._repository_root, output):
            raise WorkspaceLayoutError("output root must not overlap the platform repository")
        factory = output / ".migration-factory"
        run = factory / "runs" / run_id
        layout = MigrationWorkspaceLayout(output, output / "migrated-app", factory, factory / "metadata", run, run / "source-snapshot", run / "baseline-sandbox", run / "stage-sandboxes", run / "repair-sandboxes", run / "final-assurance-sandbox", run / "delivery-candidate", run / "artifacts", run / "logs", run / "reports", run / "temporary")
        for path in layout.aliases().values():
            self._assert_contained(Path(path), output)
        return layout

    @staticmethod
    def _contains(root: Path, candidate: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False

    def _assert_contained(self, candidate: Path, root: Path) -> None:
        if not self._contains(root, candidate.resolve(strict=False)):
            raise WorkspaceLayoutError("workspace alias escapes the output root")

