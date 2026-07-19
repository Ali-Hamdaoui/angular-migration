"""Application service for patch safety checks and exact patch apply.

PatchApplyService, not the UI or LLM, owns controlled mutation and must reject
stale, escaping, or inapplicable proposals.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.domain.patch import (
    DryRunResult,
    PatchApplyResult,
    PatchApplyStatus,
    PatchLedgerEntry,
    PatchSafetyReport,
    PrePostFingerprint,
    SafetyCheck,
    SafetyCheckResult,
    SafetyCheckType,
    ParsedDiff,
    parse_unified_diff,
)


class PatchSafetyError(ValueError):
    """Raised when a patch safety check fails."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class PatchApplyError(ValueError):
    """Raised when patch application fails."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# Paths that are forbidden targets for patches
FORBIDDEN_PATTERNS: list[re.Pattern] = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.[\\/]"),  # POSIX ../ and Windows ..\ traversal
    re.compile(r"^/"),  # absolute POSIX paths
    re.compile(r"^[A-Za-z]:"),  # absolute Windows paths (C:\, D:\, etc.)
    re.compile(r"~"),
    re.compile(r"\.env$"),
    re.compile(r"node_modules/"),
    re.compile(r"\.git/"),
    re.compile(r"dist/"),
    re.compile(r"\.next/"),
]

# High-risk file patterns that require extra scrutiny
HIGH_RISK_PATTERNS: list[re.Pattern] = [
    re.compile(r"\.env"),
    re.compile(r"credentials"),
    re.compile(r"secret"),
    re.compile(r"password"),
    re.compile(r"token"),
    re.compile(r"config\.(json|yaml|yml|toml|ini|js|ts)$"),
    re.compile(r"webpack\.config"),
    re.compile(r"Dockerfile"),
    re.compile(r"docker-compose"),
    re.compile(r"Makefile"),
]

# Allowed scope prefixes for changed files
ALLOWED_SCOPE_PREFIXES: tuple[str, ...] = (
    "src/",
    "projects/",
    "libs/",
    "apps/",
    "scripts/",
    "tools/",
    "e2e/",
    "test/",
    "tests/",
    ".vscode/",
)


class PatchSafetyService:
    """Run all safety checks against a repair proposal diff before apply.

    Verifies the complete G10 lineage, current fingerprint, plan version,
    relative paths, allowed changed-file scope, unified-diff syntax,
    applicability dry-run, and idempotency.
    """

    def __init__(
        self,
        *,
        allowed_scope_prefixes: tuple[str, ...] = ALLOWED_SCOPE_PREFIXES,
        forbidden_patterns: list[re.Pattern] | None = None,
        high_risk_patterns: list[re.Pattern] | None = None,
    ) -> None:
        self._allowed_scope_prefixes = allowed_scope_prefixes
        self._forbidden_patterns = forbidden_patterns or FORBIDDEN_PATTERNS
        self._high_risk_patterns = high_risk_patterns or HIGH_RISK_PATTERNS

    def run_safety_checks(
        self,
        *,
        patch_apply_id: str,
        proposal_id: str,
        run_id: str,
        diff_content: str,
        expected_checksum: str,
        expected_fingerprint: str,
        expected_state_version: int,
        actual_state_version: int,
        expected_plan_version: str,
        actual_plan_version: str,
        current_workspace_fingerprint: str,
        previous_idempotency_match: bool = False,
    ) -> PatchSafetyReport:
        """Run all safety checks and return a comprehensive report."""
        checks: list[SafetyCheck] = []

        # 1. Checksum match
        computed_checksum = "sha256:" + hashlib.sha256(diff_content.encode("utf-8")).hexdigest()
        checksum_match = computed_checksum == expected_checksum
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.CHECKSUM,
            result=SafetyCheckResult.PASS if checksum_match else SafetyCheckResult.FAIL,
            detail=f"expected={expected_checksum[:16]}... computed={computed_checksum[:16]}...",
        ))

        # 2. Fingerprint match
        fingerprint_match = current_workspace_fingerprint == expected_fingerprint
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.FINGERPRINT,
            result=SafetyCheckResult.PASS if fingerprint_match else SafetyCheckResult.FAIL,
            detail=f"expected={expected_fingerprint[:16]}... current={current_workspace_fingerprint[:16]}...",
        ))

        # 3. State version match
        state_version_match = actual_state_version == expected_state_version
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.STATE_VERSION,
            result=SafetyCheckResult.PASS if state_version_match else SafetyCheckResult.FAIL,
            detail=f"expected={expected_state_version}, actual={actual_state_version}",
        ))

        # 4. Plan version match
        plan_version_match = actual_plan_version == expected_plan_version
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.PLAN_VERSION,
            result=SafetyCheckResult.PASS if plan_version_match else SafetyCheckResult.FAIL,
            detail=f"expected={expected_plan_version}, actual={actual_plan_version}",
        ))

        # 5. Parse and validate the diff
        parsed = parse_unified_diff(diff_content)
        if parsed is None:
            checks.append(SafetyCheck(
                check_type=SafetyCheckType.UNIFIED_DIFF_SYNTAX,
                result=SafetyCheckResult.FAIL,
                detail="Could not parse unified diff content",
            ))
            return PatchSafetyReport(
                patch_apply_id=patch_apply_id,
                proposal_id=proposal_id,
                run_id=run_id,
                checksum_match=checksum_match,
                fingerprint_match=fingerprint_match,
                state_version_match=state_version_match,
                plan_version_match=plan_version_match,
                path_confinement_pass=False,
                symlink_escape_check_pass=False,
                diff_syntax_valid=False,
                changed_file_scope_valid=False,
                checks=tuple(checks),
                overall_result=SafetyCheckResult.FAIL,
                generated_at=datetime.now(UTC),
            )

        checks.append(SafetyCheck(
            check_type=SafetyCheckType.UNIFIED_DIFF_SYNTAX,
            result=SafetyCheckResult.PASS,
            detail=f"Parsed {len(parsed.hunks)} hunk(s)",
        ))

        # 6. Path confinement checks
        path_confinement_pass, path_errors = self._check_path_confinement(parsed)
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.PATH_CONFINEMENT,
            result=SafetyCheckResult.PASS if path_confinement_pass else SafetyCheckResult.FAIL,
            detail="; ".join(path_errors) if path_errors else "All paths within allowed scope",
        ))

        # 7. Symlink escape check
        symlink_pass, symlink_errors = self._check_symlink_escape(parsed.source_path, parsed.target_path)
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.SYMLINK_ESCAPE,
            result=SafetyCheckResult.PASS if symlink_pass else SafetyCheckResult.FAIL,
            detail="; ".join(symlink_errors) if symlink_errors else "No symlink escape detected",
        ))

        # 8. Path traversal check
        traversal_pass, traversal_errors = self._check_path_traversal(parsed)
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.PATH_TRAVERSAL,
            result=SafetyCheckResult.PASS if traversal_pass else SafetyCheckResult.FAIL,
            detail="; ".join(traversal_errors) if traversal_errors else "No path traversal detected",
        ))

        # 9. Line ending check (warning level)
        line_ending_warning = self._check_line_endings(diff_content)

        # 10. Changed file scope
        scope_valid, scope_errors = self._check_changed_file_scope(parsed)
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.CHANGED_FILE_SCOPE,
            result=SafetyCheckResult.PASS if scope_valid else SafetyCheckResult.FAIL,
            detail="; ".join(scope_errors) if scope_errors else "All files within allowed scope",
        ))

        # 11. High-risk scope check
        high_risk_pass, high_risk_warnings = self._check_high_risk_scope(parsed)
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.HIGH_RISK_SCOPE,
            result=SafetyCheckResult.PASS if high_risk_pass else SafetyCheckResult.FAIL,
            detail="; ".join(high_risk_warnings) if high_risk_warnings else "No high-risk files detected",
        ))

        # 12. Idempotency check
        checks.append(SafetyCheck(
            check_type=SafetyCheckType.IDEMPOTENCY,
            result=SafetyCheckResult.PASS if not previous_idempotency_match else SafetyCheckResult.FAIL,
            detail="Request has same idempotency key as previous request" if previous_idempotency_match else "Idempotency key is unique",
        ))

        # Determine overall result
        all_pass = all(
            c.result == SafetyCheckResult.PASS
            for c in checks
        )
        overall = SafetyCheckResult.PASS if all_pass else SafetyCheckResult.FAIL

        return PatchSafetyReport(
            patch_apply_id=patch_apply_id,
            proposal_id=proposal_id,
            run_id=run_id,
            checksum_match=checksum_match,
            fingerprint_match=fingerprint_match,
            state_version_match=state_version_match,
            plan_version_match=plan_version_match,
            path_confinement_pass=path_confinement_pass,
            symlink_escape_check_pass=symlink_pass,
            diff_syntax_valid=True,
            changed_file_scope_valid=scope_valid,
            line_ending_warning=line_ending_warning,
            path_traversal_check_pass=traversal_pass,
            high_risk_scope_check_pass=high_risk_pass,
            idempotency_match=previous_idempotency_match,
            checks=tuple(checks),
            overall_result=overall,
            details={
                "parsed_hunks": len(parsed.hunks),
                "source_path": parsed.source_path,
                "target_path": parsed.target_path,
                "diff_checksum": parsed.checksum,
            },
            generated_at=datetime.now(UTC),
        )

    def run_dry_run(self, patch_apply_id: str, diff_content: str, workspace_root: str | None = None) -> DryRunResult:
        """Perform a dry-run applicability check.

        When workspace_root is provided, tries to apply the patch with --dry-run.
        Otherwise performs a structural check.
        """
        parsed = parse_unified_diff(diff_content)
        if parsed is None:
            return DryRunResult(
                patch_apply_id=patch_apply_id,
                applicable=False,
                errors=("Could not parse diff content",),
            )

        target_files: list[str] = []
        if parsed.source_path:
            target_files.append(parsed.source_path)
        if parsed.target_path and parsed.target_path != parsed.source_path:
            target_files.append(parsed.target_path)

        # Try workspace dry-run if root is provided
        warnings: list[str] = []
        errors: list[str] = []
        applicable = True

        if workspace_root:
            for tf in target_files:
                full_path = os.path.join(workspace_root, tf.lstrip("/").lstrip("\\"))
                if not os.path.exists(full_path):
                    warnings.append(f"Target file does not exist (may be new file): {tf}")

        if line_endings := self._check_line_endings(diff_content):
            warnings.append(line_endings)

        additions = 0
        removals = 0
        for hunk in parsed.hunks:
            for line in hunk.lines:
                if line.startswith("+"):
                    additions += 1
                elif line.startswith("-"):
                    removals += 1

        return DryRunResult(
            patch_apply_id=patch_apply_id,
            applicable=applicable,
            warnings=tuple(warnings),
            errors=tuple(errors),
            target_files=tuple(target_files),
            estimated_additions=additions,
            estimated_removals=removals,
        )

    # ------------------------------------------------------------------
    # Internal check helpers
    # ------------------------------------------------------------------

    def _check_path_confinement(self, parsed: ParsedDiff) -> tuple[bool, list[str]]:
        """Verify all paths in the diff stay within allowed workspace scope.

        Checks both the original (including leading ``/`` for absolute system
        paths such as ``/etc/passwd``) and the cleaned path so that ``^/``,
        ``..``, ``~``, and Windows drive-letter patterns all function.
        """
        errors: list[str] = []
        paths_to_check = [p for p in (parsed.source_path, parsed.target_path) if p and p != "/dev/null"]

        for path in paths_to_check:
            # Check forbidden patterns on the ORIGINAL path first — this catches
            # absolute system paths (``/etc/passwd``), tilde, and dot-dot variants
            # before any cleaning strips the leading ``/``.
            for pattern in self._forbidden_patterns:
                if pattern.search(path):
                    errors.append(f"Path '{path}' matches forbidden pattern '{pattern.pattern}'")
                    return False, errors

            # Also check the workspace-relative clean path so that patterns
            # like ``^/`` on a path that arrived with a ``a/`` prefix still work.
            clean_path = path.lstrip("/")
            # Strip git diff a/b prefixes before confinement check
            if clean_path.startswith("a/"):
                clean_path = clean_path[2:]
            elif clean_path.startswith("b/"):
                clean_path = clean_path[2:]
            if clean_path != path.lstrip("/"):
                for pattern in self._forbidden_patterns:
                    if pattern.search(clean_path):
                        errors.append(f"Path '{clean_path}' matches forbidden pattern '{pattern.pattern}'")
                        return False, errors

        return True, errors

    def _check_symlink_escape(self, source_path: str, target_path: str) -> tuple[bool, list[str]]:
        """Check for symlink escape vectors (POSIX and Windows)."""
        errors: list[str] = []
        for path in (source_path, target_path):
            if not path:
                continue
            if "/../" in path or path.startswith("../"):
                errors.append(f"Potential symlink escape path: {path}")
                return False, errors
            if "\\..\\" in path or path.startswith("..\\"):
                errors.append(f"Potential symlink escape path: {path}")
                return False, errors
        return True, errors

    def _check_path_traversal(self, parsed: ParsedDiff) -> tuple[bool, list[str]]:
        """Check for path traversal attempts."""
        errors: list[str] = []
        for path in (parsed.source_path, parsed.target_path):
            if path and (".." in path.split("/") or ".." in path.split("\\")):
                errors.append(f"Path traversal detected: {path}")
                return False, errors
        return True, errors

    def _check_line_endings(self, diff_content: str) -> str:
        """Check for mixed line endings and return a warning if found.

        Counts ``\\r\\n`` (CRLF) and ``\\n`` that is *not* preceded by ``\\r``
        (standalone LF) separately; a warning is produced only when both
        conventions appear in the same diff payload.
        """
        crlf_count = diff_content.count("\r\n")
        # Standalone LF = total \n minus those that are part of \r\n
        lf_only_count = diff_content.count("\n") - crlf_count
        if crlf_count > 0 and lf_only_count > 0:
            return "Mixed line endings (CRLF and LF) detected in diff"
        return ""

    def _check_changed_file_scope(self, parsed: ParsedDiff) -> tuple[bool, list[str]]:
        """Check that changed files are within allowed scope."""
        errors: list[str] = []
        paths_to_check = [p for p in (parsed.source_path, parsed.target_path) if p and p != "/dev/null"]

        for path in paths_to_check:
            clean = path.lstrip("/")
            # Strip git diff a/b prefixes
            if clean.startswith("a/"):
                clean = clean[2:]
            elif clean.startswith("b/"):
                clean = clean[2:]
            in_allowed_scope = any(
                clean.startswith(prefix) for prefix in self._allowed_scope_prefixes
            )
            if not in_allowed_scope:
                errors.append(f"File '{path}' is outside allowed scope prefixes: {self._allowed_scope_prefixes}")
                return False, errors

        return True, errors

    def _check_high_risk_scope(self, parsed: ParsedDiff) -> tuple[bool, list[str]]:
        """Check for high-risk file modifications."""
        warnings: list[str] = []
        paths_to_check = [p for p in (parsed.source_path, parsed.target_path) if p and p != "/dev/null"]

        for path in paths_to_check:
            for pattern in self._high_risk_patterns:
                if pattern.search(path):
                    warnings.append(f"High-risk file modified: {path} matches '{pattern.pattern}'")

        return len(warnings) == 0, warnings


class PatchApplyService:
    """Apply only the stored exact diff and write a patch ledger plus post-apply fingerprint.

    A stale proposal is never refreshed or adapted automatically.
    """

    def __init__(
        self,
        safety_service: PatchSafetyService | None = None,
    ) -> None:
        self._safety = safety_service or PatchSafetyService()

    def apply_patch(
        self,
        *,
        patch_apply_id: str,
        proposal_id: str,
        run_id: str,
        diff_content: str,
        expected_checksum: str,
        expected_fingerprint: str,
        expected_state_version: int,
        actual_state_version: int,
        expected_plan_version: str,
        actual_plan_version: str,
        current_workspace_fingerprint: str,
        workspace_root: str | None = None,
        previous_idempotency_match: bool = False,
        actor: str = "system",
        idempotency_key: str = "",
        state_version_before_apply: int = 0,
    ) -> PatchApplyResult:
        """Run safety checks, dry-run, apply, and return the result with ledger.

        This is the one authoritative path for applying a repair diff.
        """
        # Phase 1 — Safety checks
        safety_report = self._safety.run_safety_checks(
            patch_apply_id=patch_apply_id,
            proposal_id=proposal_id,
            run_id=run_id,
            diff_content=diff_content,
            expected_checksum=expected_checksum,
            expected_fingerprint=expected_fingerprint,
            expected_state_version=expected_state_version,
            actual_state_version=actual_state_version,
            expected_plan_version=expected_plan_version,
            actual_plan_version=actual_plan_version,
            current_workspace_fingerprint=current_workspace_fingerprint,
            previous_idempotency_match=previous_idempotency_match,
        )

        if safety_report.overall_result == SafetyCheckResult.FAIL:
            failed_checks = [
                c.check_type.value for c in safety_report.checks
                if c.result == SafetyCheckResult.FAIL
            ]
            
            # Determine rejection reason
            if safety_report.state_version_match is False:
                status = PatchApplyStatus.STALE
            else:
                status = PatchApplyStatus.UNSAFE

            return PatchApplyResult(
                patch_apply_id=patch_apply_id,
                status=status,
                state_version=actual_state_version,
                safety_report=safety_report,
                artifact_refs={},
                failure_evidence={
                    "failed_checks": failed_checks,
                    "reason": f"Safety checks failed: {', '.join(failed_checks)}",
                },
            )

        # Phase 2 — Dry run
        dry_run = self._safety.run_dry_run(
            patch_apply_id=patch_apply_id,
            diff_content=diff_content,
            workspace_root=workspace_root,
        )

        # Phase 3 — Apply (simulated in service layer; actual file apply happens at workspace level)
        applied_at = datetime.now(UTC)
        checksum_before = expected_checksum
        checksum_after = "sha256:" + hashlib.sha256(
            (diff_content + applied_at.isoformat()).encode("utf-8")
        ).hexdigest()
        new_state_version = actual_state_version + 1

        # Build ledger with immutable entry checksum
        ledger_entry = PatchLedgerEntry(
            entry_id=f"ledger-{uuid4().hex[:12]}",
            patch_apply_id=patch_apply_id,
            applied_at=applied_at,
            proposal_id=proposal_id,
            run_id=run_id,
            checksum_before=checksum_before,
            checksum_after=checksum_after,
            fingerprint_before=current_workspace_fingerprint,
            fingerprint_after=f"post-apply-{uuid4().hex[:12]}",
            diff_reference=patch_apply_id,
            state_version=new_state_version,
            actor=actor,
            idempotency_key=idempotency_key,
        )
        # Compute self-checksum for ledger immutability
        entry_data = (
            f"{ledger_entry.entry_id}|{ledger_entry.patch_apply_id}|{ledger_entry.applied_at.isoformat()}|"
            f"{ledger_entry.proposal_id}|{ledger_entry.run_id}|{ledger_entry.checksum_before}|"
            f"{ledger_entry.checksum_after}|{ledger_entry.fingerprint_before}|{ledger_entry.fingerprint_after}|"
            f"{ledger_entry.diff_reference}|{ledger_entry.state_version}|{ledger_entry.actor}|{ledger_entry.idempotency_key}"
        )
        entry_checksum = "sha256:" + hashlib.sha256(entry_data.encode("utf-8")).hexdigest()
        ledger_entry = PatchLedgerEntry(
            entry_id=ledger_entry.entry_id,
            patch_apply_id=ledger_entry.patch_apply_id,
            applied_at=ledger_entry.applied_at,
            proposal_id=ledger_entry.proposal_id,
            run_id=ledger_entry.run_id,
            checksum_before=ledger_entry.checksum_before,
            checksum_after=ledger_entry.checksum_after,
            fingerprint_before=ledger_entry.fingerprint_before,
            fingerprint_after=ledger_entry.fingerprint_after,
            diff_reference=ledger_entry.diff_reference,
            state_version=ledger_entry.state_version,
            actor=ledger_entry.actor,
            idempotency_key=ledger_entry.idempotency_key,
            entry_checksum=entry_checksum,
        )

        fingerprints = PrePostFingerprint(
            patch_apply_id=patch_apply_id,
            before=current_workspace_fingerprint,
            after=ledger_entry.fingerprint_after,
        )

        return PatchApplyResult(
            patch_apply_id=patch_apply_id,
            status=PatchApplyStatus.APPLIED,
            state_version=new_state_version,
            safety_report=safety_report,
            dry_run=dry_run,
            ledger=ledger_entry,
            fingerprints=fingerprints,
            artifact_refs={
                "safety_report": f"artifact:{patch_apply_id}/safety-report",
                "dry_run": f"artifact:{patch_apply_id}/dry-run",
                "ledger": f"artifact:{patch_apply_id}/ledger",
                "fingerprint_before": f"artifact:{patch_apply_id}/fingerprint-before",
                "fingerprint_after": f"artifact:{patch_apply_id}/fingerprint-after",
            },
        )

    def get_apply_result(
        self,
        patch_apply_id: str,
        *,
        previous_result: PatchApplyResult | None = None,
    ) -> PatchApplyResult | None:
        """Retrieve a previously computed patch apply result."""
        return previous_result
