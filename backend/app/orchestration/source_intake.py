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
