"""Domain models for G07 — exact patch apply, safety checks, and ledger."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PatchApplyStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    APPLIED = "applied"
    STALE = "stale"
    UNSAFE = "unsafe"
    REJECTED = "rejected"
    FAILED = "failed"


class SafetyCheckType(str, Enum):
    CHECKSUM = "checksum"
    FINGERPRINT = "fingerprint"
    STATE_VERSION = "state_version"
    PLAN_VERSION = "plan_version"
    RELATIVE_PATH = "relative_path"
    CHANGED_FILE_SCOPE = "changed_file_scope"
    UNIFIED_DIFF_SYNTAX = "unified_diff_syntax"
    PATH_CONFINEMENT = "path_confinement"
    SYMLINK_ESCAPE = "symlink_escape"
    LINE_ENDING = "line_ending"
    PATH_TRAVERSAL = "path_traversal"
    HIGH_RISK_SCOPE = "high_risk_scope"
    APPLICABILITY_DRY_RUN = "applicability_dry_run"
    IDEMPOTENCY = "idempotency"


class SafetyCheckResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class SafetyCheck:
    check_type: SafetyCheckType
    result: SafetyCheckResult
    detail: str = ""
    severity: str = "error"


@dataclass(frozen=True)
class PatchSafetyReport:
    patch_apply_id: str
    proposal_id: str
    run_id: str
    checksum_match: bool
    fingerprint_match: bool
    state_version_match: bool
    plan_version_match: bool
    path_confinement_pass: bool
    symlink_escape_check_pass: bool
    diff_syntax_valid: bool
    changed_file_scope_valid: bool
    line_ending_warning: str = ""
    path_traversal_check_pass: bool = True
    high_risk_scope_check_pass: bool = True
    idempotency_match: bool = False
    checks: tuple[SafetyCheck, ...] = ()
    overall_result: SafetyCheckResult = SafetyCheckResult.FAIL
    details: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime | None = None


@dataclass(frozen=True)
class DryRunResult:
    patch_apply_id: str
    applicable: bool
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    target_files: tuple[str, ...] = ()
    estimated_additions: int = 0
    estimated_removals: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PatchLedgerEntry:
    entry_id: str
    patch_apply_id: str
    applied_at: datetime
    proposal_id: str
    run_id: str
    checksum_before: str
    checksum_after: str
    fingerprint_before: str
    fingerprint_after: str
    diff_reference: str
    state_version: int
    actor: str
    idempotency_key: str
    entry_checksum: str = ""


@dataclass(frozen=True)
class PrePostFingerprint:
    patch_apply_id: str
    before: str
    after: str


@dataclass(frozen=True)
class PatchApplyResult:
    patch_apply_id: str
    status: PatchApplyStatus
    state_version: int
    safety_report: PatchSafetyReport | None = None
    dry_run: DryRunResult | None = None
    ledger: PatchLedgerEntry | None = None
    fingerprints: PrePostFingerprint | None = None
    artifact_refs: dict[str, str] = field(default_factory=dict)
    failure_evidence: dict[str, Any] | None = None
    idempotent_replay: bool = False


# ---------------------------------------------------------------------------
# Unified diff parsing utilities
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedDiffHunk:
    header: str
    original_start: int
    original_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class ParsedDiff:
    source_path: str
    target_path: str
    hunks: tuple[ParsedDiffHunk, ...]
    raw_diff: str
    checksum: str


def parse_unified_diff(diff_content: str) -> ParsedDiff | None:
    """Parse a unified diff string into a structured representation.

    Returns None if the diff cannot be parsed.
    """
    lines = diff_content.splitlines(keepends=True)
    if not lines:
        return None

    source_path = ""
    target_path = ""
    hunks: list[ParsedDiffHunk] = []
    current_hunk_lines: list[str] = []
    current_header = ""
    orig_start = orig_count = new_start = new_count = 0

    # Reject diffs containing embedded null bytes (binary content indicator)
    if "\x00" in diff_content:
        return None

    for line in lines:
        if line.startswith("--- "):
            source_path = line[4:].rstrip("\n").rstrip("\r")
            # Strip git diff a/ prefix
            if source_path.startswith("a/"):
                source_path = source_path[2:]
        elif line.startswith("+++ "):
            target_path = line[4:].rstrip("\n").rstrip("\r")
            # Strip git diff b/ prefix
            if target_path.startswith("b/"):
                target_path = target_path[2:]
        elif line.startswith("@@"):
            try:
                # Save previous hunk if any
                if current_hunk_lines:
                    hunks.append(ParsedDiffHunk(
                        header=current_header,
                        original_start=orig_start,
                        original_count=orig_count,
                        new_start=new_start,
                        new_count=new_count,
                        lines=tuple(current_hunk_lines),
                    ))
                current_hunk_lines = []
                current_header = line.rstrip("\n").rstrip("\r")
                # Parse @@ -a,b +c,d @@
                parts = line.split("@@")[1].strip().split(" ")
                if len(parts) >= 2:
                    orig_part = parts[0]
                    new_part = parts[1]
                    orig_range = orig_part.lstrip("-")
                    new_range = new_part.lstrip("+")
                    if "," in orig_range:
                        orig_start = int(orig_range.split(",")[0])
                        orig_count = int(orig_range.split(",")[1])
                    else:
                        orig_start = int(orig_range)
                        orig_count = 1
                    if "," in new_range:
                        new_start = int(new_range.split(",")[0])
                        new_count = int(new_range.split(",")[1])
                    else:
                        new_start = int(new_range)
                        new_count = 1
                else:
                    # Malformed @@ line — only one range part
                    return None
            except (ValueError, IndexError):
                # Malformed @@ line — corrupt range or missing @@ markers
                return None
        else:
            current_hunk_lines.append(line)

    # Save last hunk
    if current_hunk_lines:
        hunks.append(ParsedDiffHunk(
            header=current_header,
            original_start=orig_start,
            original_count=orig_count,
            new_start=new_start,
            new_count=new_count,
            lines=tuple(current_hunk_lines),
        ))

    raw_checksum = "sha256:" + hashlib.sha256(diff_content.encode("utf-8")).hexdigest()
    return ParsedDiff(
        source_path=source_path,
        target_path=target_path,
        hunks=tuple(hunks),
        raw_diff=diff_content,
        checksum=raw_checksum,
    )
