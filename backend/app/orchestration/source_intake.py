"""Safe production handoff boundary for the source-intake LangGraph."""

from __future__ import annotations

from typing import Protocol


class SourceIntakeGraph(Protocol):
    def start(self, *, run_id: str, thread_id: str) -> None:
        """Start source intake for an already-created authoritative run."""


class UnconfiguredSourceIntakeGraph:
    """Fail-closed default until the JobSupervisor composition root is wired."""

    def start(self, *, run_id: str, thread_id: str) -> None:
        raise RuntimeError("production source-intake graph is not configured")


class DevelopmentSourceIntakeGraph:
    """Development handoff used to exercise the authoritative run UI.

    The real source-intake worker is not part of the local MVP yet. This
    adapter acknowledges the guarded handoff so the durable run can enter its
    source-validation phase without pretending that migration work executed.
    Production continues to use the fail-closed adapter above.
    """

    def start(self, *, run_id: str, thread_id: str) -> None:
        return None


def default_source_intake_graph(settings) -> SourceIntakeGraph:
    """Select the safe local adapter or the fail-closed production boundary."""

    if settings.app_env == "development":
        return DevelopmentSourceIntakeGraph()
    return UnconfiguredSourceIntakeGraph()
