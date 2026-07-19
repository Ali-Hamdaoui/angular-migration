"""Tests for G03 domain models - Angular update, transformation evidence, G08 approval."""

import pytest
from app.domain.contracts import RiskLevel
from app.domain.transformation import (
    AngularUpdateCommand,
    AngularUpdateResult,
    AngularUpdateStatus,
    ChangedFileClassification,
    ChangedFileEntry,
    DiffSummary,
    ForbiddenChangeEntry,
    G08ApprovalService,
    G08Decision,
    G08DecisionResult,
    G08EvidencePackage,
    G08EvidencePackageBuilder,
    PackageChangeSummary,
    TargetVersionStatus,
    TargetVersionEvidence,
    TransformationEvidenceResult,
)


class TestAngularUpdateCommand:
    def test_default_executable(self):
        cmd = AngularUpdateCommand(arguments=["ng", "update", "@angular/core@18"])
        assert cmd.executable == "npx"
        assert cmd.argv == ["npx", "ng", "update", "@angular/core@18"]

    def test_shell_disabled_by_default(self):
        cmd = AngularUpdateCommand(arguments=["ng", "update"])
        assert cmd.shell is False


class TestAngularUpdateResult:
    def test_successful_update(self):
        result = AngularUpdateResult(
            run_id="run-1",
            stage_id="stage-1",
            update_status=AngularUpdateStatus.SUCCEEDED,
            target_version_status=TargetVersionStatus.VERIFIED,
            resolved_target_version="18.2.0",
        )
        assert result.update_status == AngularUpdateStatus.SUCCEEDED
        assert result.target_version_status == TargetVersionStatus.VERIFIED
        assert result.resolved_target_version == "18.2.0"

    def test_failed_update(self):
        result = AngularUpdateResult(
            run_id="run-1",
            stage_id="stage-1",
            update_status=AngularUpdateStatus.FAILED,
            target_version_status=TargetVersionStatus.FAILED,
            error_message="ng update failed with exit code 1",
        )
        assert result.update_status == AngularUpdateStatus.FAILED
        assert result.error_message is not None


class TestTargetVersionEvidence:
    def test_all_sources_agree(self):
        evidence = TargetVersionEvidence(
            package_json_version="18.2.0",
            lockfile_version="18.2.0",
            ng_version_output="Angular CLI: 18.2.0",
            resolved_target="18.2.0",
            all_sources_agree=True,
        )
        assert evidence.all_sources_agree
        assert evidence.resolved_target == "18.2.0"

    def test_version_mismatch(self):
        evidence = TargetVersionEvidence(
            package_json_version="18.2.0",
            lockfile_version="18.1.0",
            resolved_target="18.2.0",
            all_sources_agree=False,
            disagreements=["lockfile reports 18.1.0"],
        )
        assert not evidence.all_sources_agree
        assert len(evidence.disagreements) == 1


class TestChangedFileClassification:
    def test_low_risk_file(self):
        entry = ChangedFileEntry(
            file_path="src/app/app.component.ts",
            change_type="modified",
            classification=ChangedFileClassification.LOW_RISK,
            lines_added=10,
            lines_removed=5,
        )
        assert entry.classification == ChangedFileClassification.LOW_RISK
        assert entry.change_type == "modified"

    def test_sensitive_file(self):
        entry = ChangedFileEntry(
            file_path="src/app/auth/login.component.ts",
            change_type="modified",
            classification=ChangedFileClassification.SENSITIVE,
            reason="auth_or_api",
        )
        assert entry.classification == ChangedFileClassification.SENSITIVE

    def test_binary_file(self):
        entry = ChangedFileEntry(
            file_path="assets/logo.png",
            change_type="modified",
            classification=ChangedFileClassification.BINARY,
            is_binary=True,
        )
        assert entry.classification == ChangedFileClassification.BINARY


class TestDiffSummary:
    def test_summary_counts(self):
        entries = [
            ChangedFileEntry(
                file_path="file1.ts", change_type="modified",
                classification=ChangedFileClassification.LOW_RISK,
                lines_added=5, lines_removed=3,
            ),
            ChangedFileEntry(
                file_path="file2.ts", change_type="added",
                classification=ChangedFileClassification.LOW_RISK,
                lines_added=20, lines_removed=0,
            ),
        ]
        summary = DiffSummary(
            total_files_changed=2,
            total_lines_added=25,
            total_lines_removed=3,
            files_by_classification={"low_risk": 2},
            changed_files=entries,
            diff_checksum="sha256:abc123",
        )
        assert summary.total_files_changed == 2
        assert summary.total_lines_added == 25
        assert summary.total_lines_removed == 3


class TestPackageChangeSummary:
    def test_angular_version_tracking(self):
        pkg = PackageChangeSummary(
            dependencies_added=["@angular/material@15.0.0"],
            dependencies_removed=["@angular/material@14.0.0"],
            angular_version_before="~14.2.0",
            angular_version_after="^15.0.0",
        )
        assert pkg.angular_version_before == "~14.2.0"
        assert pkg.angular_version_after == "^15.0.0"
        assert "@angular/material@15.0.0" in pkg.dependencies_added

    def test_empty_changes(self):
        pkg = PackageChangeSummary()
        assert pkg.dependencies_added == []
        assert pkg.angular_version_before is None


class TestForbiddenChangeEntry:
    def test_critical_forbidden(self):
        entry = ForbiddenChangeEntry(
            file_path="src/app/auth/secret.ts",
            reason="Sensitive file change detected",
            risk_level=RiskLevel.CRITICAL,
        )
        assert entry.risk_level == RiskLevel.CRITICAL


class TestG08ApprovalService:
    def test_approve_complete_evidence(self):
        pkg = G08EvidencePackage(
            run_id="run-1",
            stage_id="stage-1",
            gate_version="g08-v1",
            state_version=1,
            actor="tester",
            transformation_result=AngularUpdateResult(
                run_id="run-1", stage_id="stage-1",
                update_status=AngularUpdateStatus.SUCCEEDED,
                target_version_status=TargetVersionStatus.VERIFIED,
                resolved_target_version="18.2.0",
            ),
            evidence_result=TransformationEvidenceResult(
                run_id="run-1", stage_id="stage-1",
                diff=DiffSummary(
                    total_files_changed=10, total_lines_added=100,
                    total_lines_removed=50, diff_checksum="sha256:test",
                ),
                evidence_complete=True,
                overall_risk_level=RiskLevel.LOW,
            ),
            artifact_set_checksum="sha256:artifacts",
            workspace_fingerprint="sha256:workspace",
            package_checksum="sha256:package",
        )
        result = G08ApprovalService().decide(pkg, G08Decision.APPROVED)
        assert result.decision == G08Decision.APPROVED
        assert not result.stale

    def test_reject_incomplete_evidence(self):
        pkg = G08EvidencePackage(
            run_id="run-1",
            stage_id="stage-1",
            gate_version="g08-v1",
            state_version=1,
            actor="tester",
            transformation_result=AngularUpdateResult(
                run_id="run-1", stage_id="stage-1",
                update_status=AngularUpdateStatus.FAILED,
                target_version_status=TargetVersionStatus.FAILED,
            ),
            evidence_result=TransformationEvidenceResult(
                run_id="run-1", stage_id="stage-1",
                diff=DiffSummary(
                    total_files_changed=0, total_lines_added=0,
                    total_lines_removed=0, diff_checksum="sha256:none",
                ),
                evidence_complete=False,
                overall_risk_level=RiskLevel.HIGH,
            ),
            artifact_set_checksum="sha256:empty",
            workspace_fingerprint="sha256:empty",
            package_checksum="sha256:empty",
        )
        result = G08ApprovalService().decide(pkg, G08Decision.APPROVED)
        assert result.stale
        assert result.decision == G08Decision.REJECTED
        assert "incomplete" in result.reason

    def test_reject_critical_risk(self):
        pkg = G08EvidencePackage(
            run_id="run-1",
            stage_id="stage-1",
            gate_version="g08-v1",
            state_version=1,
            actor="tester",
            transformation_result=AngularUpdateResult(
                run_id="run-1", stage_id="stage-1",
                update_status=AngularUpdateStatus.SUCCEEDED,
                target_version_status=TargetVersionStatus.VERIFIED,
            ),
            evidence_result=TransformationEvidenceResult(
                run_id="run-1", stage_id="stage-1",
                diff=DiffSummary(
                    total_files_changed=5, total_lines_added=10,
                    total_lines_removed=3, diff_checksum="sha256:test2",
                ),
                evidence_complete=True,
                overall_risk_level=RiskLevel.CRITICAL,
            ),
            artifact_set_checksum="sha256:artifacts2",
            workspace_fingerprint="sha256:workspace2",
            package_checksum="sha256:package2",
        )
        result = G08ApprovalService().decide(pkg, G08Decision.APPROVED)
        assert not result.stale
        assert result.decision == G08Decision.REJECTED
        assert "critical risk" in result.reason

    def test_modification_requested(self):
        pkg = G08EvidencePackage(
            run_id="run-1",
            stage_id="stage-1",
            gate_version="g08-v1",
            state_version=1,
            actor="tester",
            transformation_result=AngularUpdateResult(
                run_id="run-1", stage_id="stage-1",
                update_status=AngularUpdateStatus.SUCCEEDED,
                target_version_status=TargetVersionStatus.VERIFIED,
            ),
            evidence_result=TransformationEvidenceResult(
                run_id="run-1", stage_id="stage-1",
                diff=DiffSummary(
                    total_files_changed=10, total_lines_added=100,
                    total_lines_removed=50, diff_checksum="sha256:test3",
                ),
                evidence_complete=True,
                overall_risk_level=RiskLevel.LOW,
            ),
            artifact_set_checksum="sha256:arts",
            workspace_fingerprint="sha256:ws",
            package_checksum="sha256:pkg",
        )
        result = G08ApprovalService().decide(pkg, G08Decision.MODIFICATION_REQUESTED, comment="Please fix line endings")
        assert result.decision == G08Decision.MODIFICATION_REQUESTED
        assert "Please fix line endings" in result.reason


class TestG08EvidencePackageBuilder:
    def test_checksum_stability(self):
        builder = G08EvidencePackageBuilder()
        transform_result = AngularUpdateResult(
            run_id="run-1", stage_id="stage-1",
            update_status=AngularUpdateStatus.SUCCEEDED,
            target_version_status=TargetVersionStatus.VERIFIED,
            resolved_target_version="18.2.0",
        )
        evidence_result = TransformationEvidenceResult(
            run_id="run-1", stage_id="stage-1",
            diff=DiffSummary(
                total_files_changed=10, total_lines_added=100,
                total_lines_removed=50, diff_checksum="sha256:test",
            ),
            evidence_complete=True,
            overall_risk_level=RiskLevel.LOW,
        )
        pkg1 = builder.build(
            run_id="run-1", stage_id="stage-1",
            state_version=1, actor="tester",
            gate_version="g08-v1",
            transformation_result=transform_result,
            evidence_result=evidence_result,
            workspace_fingerprint="sha256:workspace",
        )
        pkg2 = builder.build(
            run_id="run-1", stage_id="stage-1",
            state_version=1, actor="tester",
            gate_version="g08-v1",
            transformation_result=transform_result,
            evidence_result=evidence_result,
            workspace_fingerprint="sha256:workspace",
        )
        assert pkg1.package_checksum == pkg2.package_checksum
        assert pkg1.artifact_set_checksum == pkg2.artifact_set_checksum
        assert pkg1.gate_id == "G08"
