"""Tests for S4-F03-I01: RepairContextPack domain and builder service."""

from __future__ import annotations

import re

import pytest

from app.domain.failure import (
    FailureDiagnostic,
    FailureEvidence,
    FailureOrigin,
    FailureStatus,
    DiagnosticParserType,
)
from app.domain.repair_context import (
    ContextBudgetTracker,
    ContextSegment,
    ContextSegmentType,
    ForbiddenActionPolicy,
    RepairContextPack,
    RepairContextStatus,
    SecretSanitizer,
    SelectionPriority,
)
from app.services.repair_context_builder import (
    RepairContextPackBuilder,
    RepairContextPackBuilderError,
    SELECTION_POLICY_VERSION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHA256_PLACEHOLDER = "sha256:0000000000000000000000000000000000000000000000000000000000000000"


def _make_evidence(
    *,
    failure_id: str = "failure-001",
    stage_id: str = "stage-18-to-19",
    n_diagnostics: int = 2,
) -> FailureEvidence:
    """Return a minimal FailureEvidence with *n_diagnostics* items."""
    diagnostics: list[FailureDiagnostic] = []
    for i in range(n_diagnostics):
        diagnostics.append(
            FailureDiagnostic(
                message=f"Error #{i + 1}: something failed",
                code=f"ERR{i:03d}",
                file_path=f"src/app/component{i}.ts",
                line_number=i * 10 + 1,
                severity="error",
                parser_type=DiagnosticParserType.TYPESCRIPT,
                parser_confidence=0.9,
            )
        )
    return FailureEvidence(
        failure_id=failure_id,
        run_id="run-test-001",
        stage_id=stage_id,
        execution_id="exec-001",
        failure_fingerprint=_SHA256_PLACEHOLDER,
        origin=FailureOrigin.MIGRATION_CAUSED,
        diagnostics=diagnostics,
        workspace_fingerprint=_SHA256_PLACEHOLDER,
        status=FailureStatus.FINALIZED,
    )


def _make_workspace_files() -> list[dict]:
    """Return sample workspace file entries."""
    return [
        {
            "path": "src/app/component0.ts",
            "content": "export class Component0 {\n  title = 'hello';\n}\n",
        },
        {
            "path": "src/app/component1.ts",
            "content": "export class Component1 {\n  count = 42;\n}\n",
        },
        {
            "path": "src/app/unrelated.ts",
            "content": "export const UNRELATED = true;\n",
        },
    ]


def _make_prior_attempts() -> list[dict]:
    return [
        {"attempt_number": 1, "diagnosis": "Fixed import path typo, rebuild triggered."},
    ]


# ===================================================================
# Domain model tests
# ===================================================================


class TestContextSegmentType:
    def test_all_values_present(self):
        values = {v.value for v in ContextSegmentType}
        expected = {
            "diagnostic_excerpt",
            "failure_evidence",
            "source_file",
            "dependency_info",
            "prior_attempt",
            "system_prompt",
        }
        assert values == expected


class TestContextSegment:
    def test_minimal_valid(self):
        seg = ContextSegment(
            segment_type=ContextSegmentType.SOURCE_FILE,
            content="some content",
            reason="test",
            checksum=_SHA256_PLACEHOLDER,
        )
        assert seg.segment_type == ContextSegmentType.SOURCE_FILE
        assert seg.content == "some content"
        assert seg.redacted is False
        assert seg.line_start is None
        assert seg.line_end is None

    def test_rejects_long_content(self):
        with pytest.raises(Exception):
            ContextSegment(
                segment_type=ContextSegmentType.SOURCE_FILE,
                content="x" * 16001,
                reason="too long",
                checksum=_SHA256_PLACEHOLDER,
            )

    def test_line_end_must_not_precede_start(self):
        with pytest.raises(ValueError, match="line_end must be >= line_start"):
            ContextSegment(
                segment_type=ContextSegmentType.SOURCE_FILE,
                content="content",
                reason="test",
                checksum=_SHA256_PLACEHOLDER,
                line_start=10,
                line_end=5,
            )


class TestSelectionPriority:
    def test_defaults(self):
        sp = SelectionPriority(file_priority=50)
        assert sp.file_priority == 50
        assert sp.excerpt_max_chars == 4000
        assert sp.full_file_max_chars == 16000

    def test_rejects_out_of_range(self):
        with pytest.raises(Exception):
            SelectionPriority(file_priority=0)
        with pytest.raises(Exception):
            SelectionPriority(file_priority=101)


class TestRepairContextPack:
    def test_minimal_valid_pack(self):
        pack = RepairContextPack(
            context_pack_id="ctx-abc123",
            failure_id="failure-001",
            stage_id="stage-18-to-19",
            repair_attempt=1,
            workspace_fingerprint=_SHA256_PLACEHOLDER,
            selection_policy_version="v1",
            sanitization_checksum=_SHA256_PLACEHOLDER,
            content_checksum=_SHA256_PLACEHOLDER,
            segments=[
                ContextSegment(
                    segment_type=ContextSegmentType.FAILURE_EVIDENCE,
                    content="error occurred",
                    reason="diagnostic excerpt",
                    checksum=_SHA256_PLACEHOLDER,
                ),
            ],
        )
        assert pack.status == RepairContextStatus.FINALIZED
        assert pack.token_budget is None

    def test_empty_segments_rejected(self):
        with pytest.raises(Exception):
            RepairContextPack(
                context_pack_id="ctx-abc",
                failure_id="failure-001",
                stage_id="stage-18-to-19",
                repair_attempt=1,
                workspace_fingerprint=_SHA256_PLACEHOLDER,
                selection_policy_version="v1",
                sanitization_checksum=_SHA256_PLACEHOLDER,
                content_checksum=_SHA256_PLACEHOLDER,
                segments=[],
            )

    def test_insufficient_requires_budget(self):
        with pytest.raises(Exception, match="INSUFFICIENT status requires a token_budget"):
            RepairContextPack(
                context_pack_id="ctx-abc",
                failure_id="failure-001",
                stage_id="stage-18-to-19",
                repair_attempt=1,
                workspace_fingerprint=_SHA256_PLACEHOLDER,
                selection_policy_version="v1",
                sanitization_checksum=_SHA256_PLACEHOLDER,
                content_checksum=_SHA256_PLACEHOLDER,
                segments=[
                    ContextSegment(
                        segment_type=ContextSegmentType.FAILURE_EVIDENCE,
                        content="err",
                        reason="diag",
                        checksum=_SHA256_PLACEHOLDER,
                    ),
                ],
                status=RepairContextStatus.INSUFFICIENT,
            )

    def test_stale_status_accepted(self):
        pack = RepairContextPack(
            context_pack_id="ctx-xyz",
            failure_id="failure-002",
            stage_id="stage-19-to-20",
            repair_attempt=2,
            workspace_fingerprint=_SHA256_PLACEHOLDER,
            selection_policy_version="v1",
            sanitization_checksum=_SHA256_PLACEHOLDER,
            content_checksum=_SHA256_PLACEHOLDER,
            segments=[
                ContextSegment(
                    segment_type=ContextSegmentType.FAILURE_EVIDENCE,
                    content="old failure",
                    reason="stale",
                    checksum=_SHA256_PLACEHOLDER,
                ),
            ],
            status=RepairContextStatus.STALE,
        )
        assert pack.status == RepairContextStatus.STALE


class TestSecretSanitizer:
    def test_no_secrets_passthrough(self):
        sanitizer = SecretSanitizer()
        clean, report = sanitizer.sanitize("Hello, this is harmless text.")
        assert clean == "Hello, this is harmless text."
        assert report["redacted"] is False

    def test_redacts_api_key(self):
        sanitizer = SecretSanitizer()
        clean, report = sanitizer.sanitize("api_key = sk-1234567890abcdef")
        assert "[REDACTED]" in clean
        assert report["redacted"] is True
        assert report["counts"]["api_keys_tokens"] > 0

    def test_redacts_bearer_token(self):
        sanitizer = SecretSanitizer()
        clean, report = sanitizer.sanitize("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        assert "[REDACTED]" in clean
        assert report["redacted"] is True

    def test_redacts_password(self):
        sanitizer = SecretSanitizer()
        clean, report = sanitizer.sanitize("connection: password=supersecret123")
        assert "[REDACTED]" in clean
        assert report["redacted"] is True

    def test_redacts_private_key(self):
        sanitizer = SecretSanitizer()
        content = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA...\n"
            "-----END RSA PRIVATE KEY-----"
        )
        clean, report = sanitizer.sanitize(content)
        assert "[REDACTED]" in clean
        assert report["redacted"] is True

    def test_redacts_url_credentials(self):
        sanitizer = SecretSanitizer()
        clean, report = sanitizer.sanitize("https://user:pass@example.com/data")
        assert "[REDACTED]" in clean
        assert report["redacted"] is True

    def test_redacts_ip_address(self):
        sanitizer = SecretSanitizer()
        clean, report = sanitizer.sanitize("Server at 192.168.1.1 is down")
        assert "[REDACTED]" in clean
        assert report["redacted"] is True

    def test_multiple_secrets_reported(self):
        sanitizer = SecretSanitizer()
        content = "api_key = sk-1234567890abcdef\npassword=pass\n192.168.1.1"
        clean, report = sanitizer.sanitize(content)
        assert report["redacted"] is True
        assert sum(report["counts"].values()) >= 3


class TestContextBudgetTracker:
    def test_add_segment_tracks_tokens(self):
        tracker = ContextBudgetTracker(max_tokens=100)
        seg = ContextSegment(
            segment_type=ContextSegmentType.SOURCE_FILE,
            content="hello world",  # 11 chars → ~2 tokens
            reason="test",
            checksum=_SHA256_PLACEHOLDER,
        )
        cost = tracker.add_segment(seg)
        assert cost > 0
        assert tracker.total_tokens() == cost

    def test_budget_exceeded_raises(self):
        tracker = ContextBudgetTracker(max_tokens=10)
        seg = ContextSegment(
            segment_type=ContextSegmentType.SOURCE_FILE,
            content="x" * 80,  # 80 chars → 20 tokens → exceeds 10
            reason="test",
            checksum=_SHA256_PLACEHOLDER,
        )
        with pytest.raises(ValueError, match="exceed"):
            tracker.add_segment(seg)

    def test_can_add_segment(self):
        tracker = ContextBudgetTracker(max_tokens=100)
        seg = ContextSegment(
            segment_type=ContextSegmentType.SOURCE_FILE,
            content="x" * 40,  # 40 chars → 10 tokens
            reason="test",
            checksum=_SHA256_PLACEHOLDER,
        )
        assert tracker.can_add_segment(seg) is True
        tracker.add_segment(seg)
        assert tracker.can_add_segment() is True
        big = ContextSegment(
            segment_type=ContextSegmentType.SOURCE_FILE,
            content="x" * 400,
            reason="test",
            checksum=_SHA256_PLACEHOLDER,
        )
        assert tracker.can_add_segment(big) is False

    def test_default_max_tokens(self):
        tracker = ContextBudgetTracker()
        assert tracker.max_tokens == 32000


class TestForbiddenActionPolicy:
    def test_default_forbidden_actions(self):
        policy = ForbiddenActionPolicy()
        assert "edit_source" in policy.forbidden_actions
        assert "execute_command" in policy.forbidden_actions
        assert "access_network" in policy.forbidden_actions
        assert "read_arbitrary_file" in policy.forbidden_actions

    def test_is_action_forbidden(self):
        policy = ForbiddenActionPolicy()
        assert policy.is_action_forbidden("edit_source") is True
        assert policy.is_action_forbidden("read_file") is False

    def test_custom_forbidden_actions(self):
        policy = ForbiddenActionPolicy(forbidden_actions=["delete_file", "send_email"])
        assert policy.is_action_forbidden("delete_file") is True
        assert policy.is_action_forbidden("edit_source") is False

    def test_forbidden_actions_immutable(self):
        policy = ForbiddenActionPolicy()
        forbidden = policy.forbidden_actions
        forbidden.append("new_action")
        assert "new_action" not in policy.forbidden_actions


# ===================================================================
# Builder tests
# ===================================================================


class TestRepairContextPackBuilder:
    def test_happy_path_builds_valid_pack(self):
        """Evidence + files + prior attempts → valid RepairContextPack."""
        evidence = _make_evidence(n_diagnostics=2)
        files = _make_workspace_files()
        attempts = _make_prior_attempts()

        builder = RepairContextPackBuilder()
        pack = builder.build(evidence, files, attempts)

        assert isinstance(pack, RepairContextPack)
        assert pack.context_pack_id.startswith("ctx-")
        assert pack.failure_id == evidence.failure_id
        assert pack.stage_id == evidence.stage_id
        assert pack.repair_attempt == 1
        assert pack.workspace_fingerprint == evidence.workspace_fingerprint
        assert pack.selection_policy_version == SELECTION_POLICY_VERSION
        assert pack.status == RepairContextStatus.FINALIZED
        assert len(pack.segments) >= 2  # at least diagnostics + files

    def test_checksum_binding_on_segments(self):
        """Segments have valid sha256: checksums."""
        evidence = _make_evidence(n_diagnostics=1)
        files = _make_workspace_files()

        builder = RepairContextPackBuilder()
        pack = builder.build(evidence, files)

        for seg in pack.segments:
            assert seg.checksum.startswith("sha256:")
            assert len(seg.checksum) == 71  # "sha256:" + 64 hex chars
            # Verify checksum matches content
            expected = builder._compute_segment_checksum(seg.content)
            assert seg.checksum == expected

    def test_content_checksum_pack_level(self):
        """Pack-level content_checksum matches segment content."""
        evidence = _make_evidence(n_diagnostics=2)
        files = _make_workspace_files()

        builder = RepairContextPackBuilder()
        pack = builder.build(evidence, files)

        assert pack.content_checksum.startswith("sha256:")
        expected = builder._compute_content_checksum(pack.segments)
        assert pack.content_checksum == expected

    def test_sanitization_redacts_secrets(self):
        """SecretSanitizer redacts secrets in segments."""
        evidence = _make_evidence(n_diagnostics=1)
        files = [
            {
                "path": "src/app/component0.ts",
                "content": "const api_key = 'sk-1234567890abcdef';",
            },
        ]

        builder = RepairContextPackBuilder()
        pack = builder.build(evidence, files)

        file_segments = [s for s in pack.segments if s.segment_type == ContextSegmentType.SOURCE_FILE]
        assert len(file_segments) >= 1
        seg = file_segments[0]
        assert "[REDACTED]" in seg.content
        assert seg.redacted is True

    def test_token_budget_insufficient(self):
        """Tight token budget → INSUFFICIENT status."""
        evidence = _make_evidence(n_diagnostics=2)
        files = _make_workspace_files()

        builder = RepairContextPackBuilder()
        # Very small budget so any content will exceed it
        pack = builder.build(evidence, files, token_budget=1)

        assert pack.status == RepairContextStatus.INSUFFICIENT
        assert pack.token_budget == 1

    def test_forbidden_actions_list(self):
        """ForbiddenActionPolicy returns correct forbidden list."""
        policy = ForbiddenActionPolicy()
        assert policy.is_action_forbidden("edit_source") is True
        assert policy.is_action_forbidden("execute_command") is True
        assert policy.is_action_forbidden("access_network") is True
        assert policy.is_action_forbidden("read_arbitrary_file") is True
        # Actions not in the forbidden list
        assert policy.is_action_forbidden("read_file") is False
        assert policy.is_action_forbidden("propose_patch") is False

    def test_empty_input_raises(self):
        """No evidence → ValueError."""
        builder = RepairContextPackBuilder()
        with pytest.raises(RepairContextPackBuilderError) as exc:
            builder.build(None, [])  # type: ignore[arg-type]
        assert "NO_EVIDENCE" in str(exc.value.code) or "NO_EVIDENCE" in str(
            exc.value
        )

    def test_evidence_without_diagnostics_raises(self):
        """Evidence with zero diagnostics → ValueError."""
        evidence = FailureEvidence.model_construct(  # bypass validation for edge case
            failure_id="failure-001",
            run_id="run-test-001",
            stage_id="stage-18-to-19",
            execution_id="exec-001",
            failure_fingerprint=_SHA256_PLACEHOLDER,
            origin=FailureOrigin.MIGRATION_CAUSED,
            diagnostics=[],
            workspace_fingerprint=_SHA256_PLACEHOLDER,
            status=FailureStatus.FINALIZED,
        )
        builder = RepairContextPackBuilder()
        with pytest.raises(RepairContextPackBuilderError, match="(?i)at least one diagnostic"):
            builder.build(evidence, [])

    def test_workspace_file_selection_by_diagnostic_path(self):
        """Only files referenced in diagnostics are selected."""
        evidence = _make_evidence(n_diagnostics=2)
        # Both diagnostics reference component0.ts and component1.ts
        files = _make_workspace_files()  # includes unrelated.ts

        builder = RepairContextPackBuilder()
        pack = builder.build(evidence, files)

        # Only component0.ts and component1.ts should appear
        file_paths = {
            s.file_path
            for s in pack.segments
            if s.segment_type == ContextSegmentType.SOURCE_FILE
        }
        assert "src/app/component0.ts" in file_paths
        assert "src/app/component1.ts" in file_paths
        assert "src/app/unrelated.ts" not in file_paths

    def test_prior_attempt_included(self):
        """Prior attempt segments appear in the pack."""
        evidence = _make_evidence(n_diagnostics=1)
        files = _make_workspace_files()
        attempts = _make_prior_attempts()

        builder = RepairContextPackBuilder()
        pack = builder.build(evidence, files, prior_attempts=attempts)

        prior_segments = [
            s for s in pack.segments if s.segment_type == ContextSegmentType.PRIOR_ATTEMPT
        ]
        assert len(prior_segments) == 1
        assert "Fixed import" in prior_segments[0].content

    def test_pack_is_frozen(self):
        """RepairContextPack is immutable (frozen=True)."""
        evidence = _make_evidence(n_diagnostics=1)
        files = _make_workspace_files()

        builder = RepairContextPackBuilder()
        pack = builder.build(evidence, files)

        with pytest.raises(Exception):
            pack.failure_id = "changed"  # type: ignore[misc]

    def test_diagnostic_segment_content_includes_code_and_path(self):
        """Diagnostic segments encode code/file/line info."""
        evidence = _make_evidence(n_diagnostics=1)
        builder = RepairContextPackBuilder()
        pack = builder.build(evidence, [])

        diag_segments = [
            s for s in pack.segments
            if s.segment_type == ContextSegmentType.FAILURE_EVIDENCE
        ]
        assert len(diag_segments) == 1
        assert "[ERR000]" in diag_segments[0].content
        assert "component0.ts" in diag_segments[0].content

    def test_sanitization_checksum_computed(self):
        """Pack has a valid sanitization_checksum."""
        evidence = _make_evidence(n_diagnostics=2)
        files = _make_workspace_files()

        builder = RepairContextPackBuilder()
        pack = builder.build(evidence, files)

        assert pack.sanitization_checksum.startswith("sha256:")
        assert len(pack.sanitization_checksum) == 71
