"""Application service that builds an immutable RepairContextPack from failure evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from app.domain.failure import FailureEvidence, FailureDiagnostic
from app.domain.repair_context import (
    ContextBudgetTracker,
    ContextSegment,
    ContextSegmentType,
    RepairContextPack,
    RepairContextStatus,
    SecretSanitizer,
    SelectionPriority,
)


class RepairContextPackBuilderError(ValueError):
    """Raised when the context pack cannot be constructed."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


SELECTION_POLICY_VERSION = "repair-selection-v1"


class RepairContextPackBuilder:
    """Compose an immutable RepairContextPack from failure evidence and workspace context.

    Steps:
      1. Validate inputs (non-empty evidence required)
      2. Select relevant workspace files based on failure diagnostics
      3. Include prior-attempt segments if provided
      4. Sanitise secret content
      5. Bind segment-level checksums
      6. Compute pack-level content checksum
      7. Enforce token budget → INSUFFICIENT if exceeded
      8. Return frozen RepairContextPack
    """

    def __init__(
        self,
        *,
        sanitizer: SecretSanitizer | None = None,
        budget_tracker: ContextBudgetTracker | None = None,
        selection_policy_version: str = SELECTION_POLICY_VERSION,
    ) -> None:
        self._sanitizer = sanitizer or SecretSanitizer()
        self._budget_tracker = budget_tracker or ContextBudgetTracker()
        self._selection_policy_version = selection_policy_version

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        failure_evidence: FailureEvidence,
        workspace_files: list[dict],
        prior_attempts: list[dict] | None = None,
        token_budget: int | None = None,
    ) -> RepairContextPack:
        """Build a RepairContextPack from failure evidence and workspace context.

        Parameters
        ----------
        failure_evidence:
            Immutable evidence record with diagnostics to drive file selection.
        workspace_files:
            List of dicts with keys ``path`` and ``content`` (and optionally
            ``priority``) representing available source files in the workspace.
        prior_attempts:
            Optional list of dicts describing previous repair attempts. Each dict
            should have at least ``attempt_number`` and ``diagnosis`` keys.
        token_budget:
            Optional cap on total estimated tokens. If exceeded the pack is
            returned with ``INSUFFICIENT`` status.

        Returns
        -------
        RepairContextPack with all fields populated.

        Raises
        ------
        RepairContextPackBuilderError
            If ``failure_evidence`` has no diagnostics.
        """
        if not failure_evidence or not failure_evidence.diagnostics:
            raise RepairContextPackBuilderError(
                "NO_EVIDENCE",
                "At least one diagnostic is required to build a context pack.",
            )

        # Phase 1 – gather segments
        segments: list[ContextSegment] = []

        # Failure-evidence segments from diagnostics
        segments.extend(self._build_diagnostic_segments(failure_evidence.diagnostics))

        # Relevant file segments
        relevant = self._select_relevant_files(
            failure_evidence.diagnostics, workspace_files
        )
        for file_entry in relevant:
            priority = SelectionPriority(
                file_priority=file_entry.get("priority", 50),
            )
            segment = self._build_file_segment(file_entry, priority)
            segments.append(segment)

        # Prior-attempt segments
        if prior_attempts:
            segments.extend(self._include_prior_attempts(prior_attempts))

        # Phase 2 — sanitize and bind checksums
        segments = self._sanitize_segments(segments)
        segments = self._bind_checksums(segments)

        # Phase 3 — sort by priority
        segments = self._select_by_priority(segments)

        # Phase 4 — enforce budget
        sanitization_checksum = self._compute_sanitization_checksum(segments)
        content_checksum = self._compute_content_checksum(segments)

        if token_budget is not None:
            self._budget_tracker = ContextBudgetTracker(max_tokens=token_budget)
            try:
                for seg in segments:
                    self._budget_tracker.add_segment(seg)
            except ValueError:
                # Budget exceeded — return INSUFFICIENT
                return RepairContextPack(
                    context_pack_id=f"ctx-{uuid4().hex[:12]}",
                    failure_id=failure_evidence.failure_id,
                    stage_id=failure_evidence.stage_id,
                    repair_attempt=1,
                    workspace_fingerprint=failure_evidence.workspace_fingerprint,
                    selection_policy_version=self._selection_policy_version,
                    sanitization_checksum=sanitization_checksum,
                    content_checksum=content_checksum,
                    segments=segments,
                    token_budget=token_budget,
                    status=RepairContextStatus.INSUFFICIENT,
                )

        return RepairContextPack(
            context_pack_id=f"ctx-{uuid4().hex[:12]}",
            failure_id=failure_evidence.failure_id,
            stage_id=failure_evidence.stage_id,
            repair_attempt=1,
            workspace_fingerprint=failure_evidence.workspace_fingerprint,
            selection_policy_version=self._selection_policy_version,
            sanitization_checksum=sanitization_checksum,
            content_checksum=content_checksum,
            segments=segments,
            token_budget=token_budget,
            status=RepairContextStatus.FINALIZED,
        )

    # ------------------------------------------------------------------
    # Segment building helpers
    # ------------------------------------------------------------------

    def _build_diagnostic_segments(
        self, diagnostics: list[FailureDiagnostic]
    ) -> list[ContextSegment]:
        """Create one FAILURE_EVIDENCE segment per diagnostic entry."""
        segments: list[ContextSegment] = []
        for diag in diagnostics:
            content = diag.message
            if diag.code:
                content = f"[{diag.code}] {content}"
            if diag.file_path:
                content = f"{diag.file_path}:{diag.line_number or '?'} — {content}"
            checksum = self._compute_segment_checksum(content)
            segments.append(
                ContextSegment(
                    segment_type=ContextSegmentType.FAILURE_EVIDENCE,
                    file_path=diag.file_path,
                    content=content[:16000],
                    reason=f"Diagnostic: {diag.message[:120]}",
                    checksum=checksum,
                    redacted=False,
                    line_start=diag.line_number,
                    line_end=diag.line_number,
                )
            )
        return segments

    def _build_file_segment(
        self,
        file_entry: dict[str, Any],
        priority: SelectionPriority,
    ) -> ContextSegment:
        """Create a SOURCE_FILE segment from a workspace file entry."""
        file_path = file_entry.get("path", "unknown")
        content = file_entry.get("content", "")
        reason = file_entry.get("reason", f"File referenced by failure diagnostics")

        max_chars = (
            priority.full_file_max_chars
            if len(content) <= priority.full_file_max_chars
            else priority.excerpt_max_chars
        )
        truncated = content[:max_chars]
        checksum = self._compute_segment_checksum(truncated)

        return ContextSegment(
            segment_type=ContextSegmentType.SOURCE_FILE,
            file_path=file_path,
            content=truncated,
            reason=reason,
            checksum=checksum,
            redacted=False,
        )

    # ------------------------------------------------------------------
    # Selection and ordering
    # ------------------------------------------------------------------

    def _select_by_priority(
        self, segments: list[ContextSegment],
    ) -> list[ContextSegment]:
        """Order segments so that FAILURE_EVIDENCE comes first, then files, etc."""
        priority_order: dict[ContextSegmentType, int] = {
            ContextSegmentType.FAILURE_EVIDENCE: 0,
            ContextSegmentType.DIAGNOSTIC_EXCERPT: 1,
            ContextSegmentType.SOURCE_FILE: 2,
            ContextSegmentType.DEPENDENCY_INFO: 3,
            ContextSegmentType.PRIOR_ATTEMPT: 4,
            ContextSegmentType.SYSTEM_PROMPT: 5,
        }
        return sorted(segments, key=lambda s: priority_order.get(s.segment_type, 99))

    def _select_relevant_files(
        self,
        failure_diagnostics: list[FailureDiagnostic],
        available_files: list[dict],
    ) -> list[dict]:
        """Return workspace files whose paths appear in failure diagnostics.

        Files are annotated with a ``priority`` score based on how many
        diagnostics reference them.
        """
        referenced_paths: dict[str, int] = {}
        for diag in failure_diagnostics:
            if diag.file_path:
                referenced_paths[diag.file_path] = (
                    referenced_paths.get(diag.file_path, 0) + 1
                )

        selected: list[dict] = []
        for f in available_files:
            path = f.get("path", "")
            if path in referenced_paths:
                f["priority"] = min(100, referenced_paths[path] * 20)
                f["reason"] = f"Referenced by {referenced_paths[path]} diagnostic(s)"
                selected.append(f)

        # Sort by descending priority (most-referenced first)
        selected.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return selected

    def _include_prior_attempts(self, attempts: list[dict]) -> list[ContextSegment]:
        """Build PRIOR_ATTEMPT segments from previous repair attempts."""
        segments: list[ContextSegment] = []
        for attempt in attempts:
            attempt_num = attempt.get("attempt_number", "?")
            diagnosis = attempt.get("diagnosis", "") or attempt.get("summary", "")
            content = diagnosis[:16000] if diagnosis else "No diagnosis recorded."
            checksum = self._compute_segment_checksum(content)
            segments.append(
                ContextSegment(
                    segment_type=ContextSegmentType.PRIOR_ATTEMPT,
                    file_path=None,
                    content=content,
                    reason=f"Prior attempt #{attempt_num}",
                    checksum=checksum,
                    redacted=False,
                )
            )
        return segments

    # ------------------------------------------------------------------
    # Checksum utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_segment_checksum(content: str) -> str:
        """Return a ``sha256:`` prefixed hex digest of *content*."""
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _bind_checksums(self, segments: list[ContextSegment]) -> list[ContextSegment]:
        """Recompute and attach checksums for every segment."""
        bound: list[ContextSegment] = []
        for seg in segments:
            updated = seg.model_copy(
                update={"checksum": self._compute_segment_checksum(seg.content)},
            )
            bound.append(updated)
        return bound

    @staticmethod
    def _compute_content_checksum(segments: list[ContextSegment]) -> str:
        """Compute a single pack-level content checksum over all segment content."""
        raw = json.dumps(
            [s.model_dump(mode="json") for s in segments],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    # ------------------------------------------------------------------
    # Sanitization
    # ------------------------------------------------------------------

    def _sanitize_segments(
        self, segments: list[ContextSegment],
    ) -> list[ContextSegment]:
        """Run each segment through SecretSanitizer and set redacted flag."""
        sanitized: list[ContextSegment] = []
        for seg in segments:
            clean, report = self._sanitizer.sanitize(seg.content)
            sanitized.append(
                seg.model_copy(
                    update={
                        "content": clean,
                        "redacted": report["redacted"],
                    },
                )
            )
        return sanitized

    def _compute_sanitization_checksum(
        self, segments: list[ContextSegment],
    ) -> str:
        """Compute a checksum over sanitized content for audit trail."""
        combined = "".join(s.content for s in segments)
        return "sha256:" + hashlib.sha256(combined.encode("utf-8")).hexdigest()
