"""Tests for G09 domain models: final assurance (G13), delivery (G14), report (G15)."""

import hashlib
import json

from app.domain.contracts import ArtifactRefDto, ArtifactType
from app.domain.final_assurance import (
    FinalAssuranceSummary,
    G13ApprovalPackage,
    G13ApprovalPackageBuilder,
    G13ApprovalResult,
    G13ApprovalService,
    G13Decision,
)
from app.domain.delivery import (
    DeliveryCandidate,
    G14ApprovalPackage,
    G14ApprovalPackageBuilder,
    G14ApprovalResult,
    G14ApprovalService,
    G14Decision,
)
from app.domain.report import (
    FinalReportRecord,
    G15ApprovalPackage,
    G15ApprovalPackageBuilder,
    G15ApprovalResult,
    G15ApprovalService,
    G15Decision,
)
from datetime import datetime, timezone


def _make_artifact(artifact_id: str = "artifact-test-1") -> ArtifactRefDto:
    return ArtifactRefDto(
        artifact_id=artifact_id,
        run_id="run-test-001",
        stage_id=None,
        artifact_type=ArtifactType.JSON,
        relative_path="test/artifact.json",
        created_at=datetime.now(timezone.utc),
        checksum="sha256:abc" + "0" * 57,
    )


def _make_summary() -> FinalAssuranceSummary:
    return FinalAssuranceSummary(
        run_id="run-test-001",
        candidate_fingerprint="sha256:" + "a" * 64,
        technical_status="passed",
        parity_status="passed",
        source_integrity_status="verified",
        security_status="passed",
        quality_status="passed",
    )


def _make_candidate() -> DeliveryCandidate:
    return DeliveryCandidate(
        delivery_id="delivery-test-1",
        run_id="run-test-001",
        candidate_fingerprint="sha256:" + "b" * 64,
        destination="migrated-app",
        publication_status="candidate_ready",
    )


def _make_report_record() -> FinalReportRecord:
    return FinalReportRecord(
        report_id="report-test-1",
        run_id="run-test-001",
        deterministic_report_checksum="sha256:" + "c" * 64,
        narrative_status="not_requested",
        proof_labels={"assurance_technical": "PROVEN"},
    )


# ─── G13 Final Assurance ────────────────────────────────────────────────


class TestFinalAssuranceSummary:
    def test_valid_summary(self):
        s = _make_summary()
        assert s.run_id == "run-test-001"
        assert s.technical_status == "passed"
        assert s.source_integrity_status == "verified"

    def test_minimal_summary(self):
        s = FinalAssuranceSummary(
            run_id="run-test-001",
            candidate_fingerprint="sha256:" + "a" * 64,
            technical_status="running",
            parity_status="not_evaluated",
            source_integrity_status="pending",
        )
        assert s.technical_status == "running"


class TestG13ApprovalPackageBuilder:
    def test_build_package(self):
        builder = G13ApprovalPackageBuilder()
        summary = _make_summary()
        artifacts = [_make_artifact("art-1"), _make_artifact("art-2")]
        package = builder.build(
            run_id="run-test-001",
            state_version=5,
            actor="test-actor",
            gate_version="g13-v1",
            summary=summary,
            artifacts=artifacts,
        )
        assert package.gate_id == "G13"
        assert package.run_id == "run-test-001"
        assert package.state_version == 5
        assert package.summary.technical_status == "passed"
        assert len(package.artifacts) == 2
        assert package.package_checksum.startswith("sha256:")
        assert package.artifact_set_checksum.startswith("sha256:")

    def test_deterministic_checksum(self):
        builder = G13ApprovalPackageBuilder()
        summary = _make_summary()
        artifacts = [_make_artifact("art-1")]
        p1 = builder.build(run_id="run-test-001", state_version=1, actor="actor1", gate_version="g13-v1", summary=summary, artifacts=artifacts)
        p2 = builder.build(run_id="run-test-001", state_version=1, actor="actor1", gate_version="g13-v1", summary=summary, artifacts=artifacts)
        assert p1.package_checksum == p2.package_checksum
        assert p1.artifact_set_checksum == p2.artifact_set_checksum


class TestG13ApprovalService:
    def test_approve(self):
        builder = G13ApprovalPackageBuilder()
        package = builder.build(run_id="run-test-001", state_version=1, actor="actor1", gate_version="g13-v1", summary=_make_summary())
        result = G13ApprovalService().decide(package, G13Decision.APPROVED)
        assert result.decision == G13Decision.APPROVED
        assert not result.stale

    def test_reject(self):
        builder = G13ApprovalPackageBuilder()
        package = builder.build(run_id="run-test-001", state_version=1, actor="actor1", gate_version="g13-v1", summary=_make_summary())
        result = G13ApprovalService().decide(package, G13Decision.REJECTED, comment="failing checks")
        assert result.decision == G13Decision.REJECTED
        assert result.reason == "failing checks"

    def test_approved_with_comment_requires_comment(self):
        builder = G13ApprovalPackageBuilder()
        package = builder.build(run_id="run-test-001", state_version=1, actor="actor1", gate_version="g13-v1", summary=_make_summary())
        import pytest
        with pytest.raises(ValueError, match="approved_with_comment requires a non-empty comment"):
            G13ApprovalService().decide(package, G13Decision.APPROVED_WITH_COMMENT)


# ─── G14 Delivery ───────────────────────────────────────────────────────


class TestG14ApprovalPackageBuilder:
    def test_build_package(self):
        builder = G14ApprovalPackageBuilder()
        candidate = _make_candidate()
        package = builder.build(
            run_id="run-test-001",
            state_version=3,
            actor="actor1",
            gate_version="g14-v1",
            candidate=candidate,
        )
        assert package.gate_id == "G14"
        assert package.run_id == "run-test-001"
        assert package.candidate.delivery_id == "delivery-test-1"
        assert package.candidate.publication_status == "candidate_ready"
        assert package.package_checksum.startswith("sha256:")

    def test_deterministic(self):
        builder = G14ApprovalPackageBuilder()
        candidate = _make_candidate()
        p1 = builder.build(run_id="run-test-001", state_version=2, actor="same", gate_version="g14-v1", candidate=candidate)
        p2 = builder.build(run_id="run-test-001", state_version=2, actor="same", gate_version="g14-v1", candidate=candidate)
        assert p1.package_checksum == p2.package_checksum


class TestG14ApprovalService:
    def test_approve(self):
        builder = G14ApprovalPackageBuilder()
        package = builder.build(run_id="run-test-001", state_version=1, actor="actor1", gate_version="g14-v1", candidate=_make_candidate())
        result = G14ApprovalService().decide(package, G14Decision.APPROVED)
        assert result.decision == G14Decision.APPROVED

    def test_modification_requested(self):
        builder = G14ApprovalPackageBuilder()
        package = builder.build(run_id="run-test-001", state_version=1, actor="actor1", gate_version="g14-v1", candidate=_make_candidate())
        result = G14ApprovalService().decide(package, G14Decision.MODIFICATION_REQUESTED, comment="update destination")
        assert result.decision == G14Decision.MODIFICATION_REQUESTED
        assert result.reason == "update destination"


# ─── G15 Report ─────────────────────────────────────────────────────────


class TestG15ApprovalPackageBuilder:
    def test_build_package(self):
        builder = G15ApprovalPackageBuilder()
        report = _make_report_record()
        package = builder.build(
            run_id="run-test-001",
            state_version=7,
            actor="actor1",
            gate_version="g15-v1",
            report=report,
        )
        assert package.gate_id == "G15"
        assert package.run_id == "run-test-001"
        assert package.report.report_id == "report-test-1"
        assert package.report.deterministic_report_checksum.startswith("sha256:")
        assert "assurance_technical" in package.report.proof_labels

    def test_deterministic(self):
        builder = G15ApprovalPackageBuilder()
        report = _make_report_record()
        p1 = builder.build(run_id="run-test-001", state_version=4, actor="same", gate_version="g15-v1", report=report)
        p2 = builder.build(run_id="run-test-001", state_version=4, actor="same", gate_version="g15-v1", report=report)
        assert p1.package_checksum == p2.package_checksum


class TestG15ApprovalService:
    def test_approve(self):
        builder = G15ApprovalPackageBuilder()
        package = builder.build(run_id="run-test-001", state_version=1, actor="actor1", gate_version="g15-v1", report=_make_report_record())
        result = G15ApprovalService().decide(package, G15Decision.APPROVED)
        assert result.decision == G15Decision.APPROVED

    def test_approve_with_comment(self):
        builder = G15ApprovalPackageBuilder()
        package = builder.build(run_id="run-test-001", state_version=1, actor="actor1", gate_version="g15-v1", report=_make_report_record())
        result = G15ApprovalService().decide(package, G15Decision.APPROVED_WITH_COMMENT, comment="looks good")
        assert result.decision == G15Decision.APPROVED_WITH_COMMENT
        assert result.reason == "looks good"
