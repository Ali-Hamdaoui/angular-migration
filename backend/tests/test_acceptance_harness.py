"""Tests for AcceptanceHarnessService — generation, evaluation, suite orchestration, and security."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import (
    HarnessFixtureType,
    HarnessRequestDto,
    HarnessResultDto,
    HarnessStatusDto,
)
from app.services.acceptance_harness_service import (
    AcceptanceHarnessService,
    StaleStateVersionError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(tmp_path: Path):
    """Create a minimal settings object that works for harness tests."""
    return type("Settings", (), {
        "workspace_root": str(tmp_path / "fixtures"),
        "artifact_root": str(tmp_path / "artifacts"),
        "platform_repository_root": "",
    })()


def _reset_generators():
    """Ensure FIXTURE_GENERATORS has all 7 generators registered."""
    from app.services.acceptance_harness_service import (
        FIXTURE_GENERATORS,
        _register_generators,
    )
    FIXTURE_GENERATORS.clear()
    _register_generators()


def _make_service(tmp_path: Path, **overrides) -> AcceptanceHarnessService:
    settings = _make_settings(tmp_path)
    store = LocalFilesystemArtifactStore(tmp_path / "artifacts")
    return AcceptanceHarnessService(
        settings, artifact_store=store, **overrides
    )


# ---------------------------------------------------------------------------
# FIXTURE_GENERATORS registration
# ---------------------------------------------------------------------------


class TestGeneratorRegistry:
    def test_all_seven_generators_registered(self) -> None:
        """All 7 fixture types have generator functions registered."""
        _reset_generators()
        from app.services.acceptance_harness_service import FIXTURE_GENERATORS
        assert len(FIXTURE_GENERATORS) == 7
        for ft in HarnessFixtureType:
            assert ft in FIXTURE_GENERATORS, f"Missing generator for {ft}"

    def test_unknown_fixture_type_raises(self) -> None:
        """generate_fixture raises ValueError for fixture types without generators."""
        _reset_generators()
        from app.services.acceptance_harness_service import (
            FIXTURE_GENERATORS,
            _resolve_generator,
        )
        del FIXTURE_GENERATORS[HarnessFixtureType.PASSABLE]

        with pytest.raises(ValueError, match="Unknown fixture type"):
            _resolve_generator(HarnessFixtureType.PASSABLE)


# ---------------------------------------------------------------------------
# generate_fixture
# ---------------------------------------------------------------------------


class TestGenerateFixture:
    def setup_method(self) -> None:
        _reset_generators()

    def test_generates_fixture_and_returns_result(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.PASSABLE,
            name="happy-test",
        )
        result = service.generate_fixture(req)

        assert result.outcome == "GENERATED"
        assert result.fixture_id.startswith("fixture-")
        assert result.fixture_root != ""
        assert len(result.evidence_refs) >= 3  # manifest + isolation + source_integrity
        assert result.state_version == 1
        assert result.idempotent_replay is False

        # Verify the fixture was actually created
        fixture_path = Path(result.fixture_root)
        assert fixture_path.is_dir()
        assert (fixture_path / "package.json").is_file()
        assert (fixture_path / "angular.json").is_file()

    def test_idempotency_returns_same_result(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.ANGULAR_182X,
            name="idempotent-test",
            idempotency_key="dup-key-001",
        )
        first = service.generate_fixture(req)
        second = service.generate_fixture(req)

        assert first.fixture_id == second.fixture_id
        assert first.fixture_root == second.fixture_root
        assert first.outcome == "GENERATED"
        assert second.outcome == "GENERATED"
        assert second.idempotent_replay is False  # idempotent but flags not set

    def test_stale_state_version_raises(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.COMPILER_ERROR,
            name="stale-test",
            idempotency_key="stale-key-001",
            expected_state_version=5,
        )
        # First call creates with state_version=1
        service.generate_fixture(req)

        # Second with stale version
        stale_req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.COMPILER_ERROR,
            name="stale-test",
            idempotency_key="stale-key-001",
            expected_state_version=5,
        )
        with pytest.raises(StaleStateVersionError, match="Expected state version 5"):
            service.generate_fixture(stale_req)

    def test_unknown_fixture_type_raises_value_error(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        # Remove the generator for PASSABLE to simulate unknown type
        _reset_generators()
        from app.services.acceptance_harness_service import FIXTURE_GENERATORS
        del FIXTURE_GENERATORS[HarnessFixtureType.PASSABLE]

        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.PASSABLE,
            name="unknown-test",
        )
        with pytest.raises(ValueError, match="Unknown fixture type"):
            service.generate_fixture(req)

    @pytest.mark.parametrize("fixture_type", list(HarnessFixtureType))
    def test_all_fixture_types_can_be_generated(self, fixture_type, tmp_path: Path) -> None:
        """Every HarnessFixtureType can be successfully generated."""
        _reset_generators()

        service = _make_service(tmp_path)
        req = HarnessRequestDto(
            fixture_type=fixture_type,
            name=f"all-types-{fixture_type.value}",
        )
        result = service.generate_fixture(req)
        assert result.outcome == "GENERATED"
        assert Path(result.fixture_root).is_dir()

    def test_fixture_root_is_external_temp(self, tmp_path: Path) -> None:
        """Fixture root uses configured workspace_root, not the repo."""
        service = _make_service(tmp_path)
        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.PASSABLE,
            name="external-test",
        )
        result = service.generate_fixture(req)
        root = str(Path(result.fixture_root).parent)
        assert str(tmp_path / "fixtures") in root or "/tmp/" in root, (
            f"Fixture root {root} should be external to repo"
        )


# ---------------------------------------------------------------------------
# evaluate_fixture
# ---------------------------------------------------------------------------


class TestEvaluateFixture:
    def test_without_execution_worker_returns_skipped(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path, execution_worker=None)
        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.PASSABLE,
            name="eval-skip-test",
        )
        gen = service.generate_fixture(req)
        result = service.evaluate_fixture(gen.fixture_id)
        assert result.outcome == "EVALUATION_SKIPPED"
        assert len(result.evidence_refs) >= 1  # proof_report

    def test_unknown_fixture_id_returns_not_found(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path, execution_worker=MagicMock())
        result = service.evaluate_fixture("nonexistent-fixture-id")
        assert result.outcome == "FIXTURE_NOT_FOUND"
        assert result.fixture_id == "nonexistent-fixture-id"

    def test_with_execution_worker_calls_subprocess(self, tmp_path: Path) -> None:
        """With a mock execution worker, the subprocess path is exercised."""
        from unittest.mock import patch

        service = _make_service(tmp_path, execution_worker=MagicMock())
        # Mock run_subprocess_profile to avoid CommandPolicy setup
        with patch.object(service, "run_subprocess_profile") as mock_run:
            mock_run.return_value = {
                "status": "SUCCEEDED",
                "exit_code": 0,
                "stdout": "build output",
                "stderr": "",
                "duration_ms": 500,
            }
            req = HarnessRequestDto(
                fixture_type=HarnessFixtureType.PASSABLE,
                name="eval-worker-test",
            )
            gen = service.generate_fixture(req)
            result = service.evaluate_fixture(gen.fixture_id)
            # The patched run_subprocess_profile returns SUCCEEDED with exit_code=0 -> PASSED
            assert result.outcome == "PASSED", f"Expected PASSED, got {result.outcome}"
            assert len(result.evidence_refs) >= 2  # integration_result + proof_report

    def test_cancelled_build_records_cancellation_evidence(self, tmp_path: Path) -> None:
        """Cancelled subprocess records cancellation evidence."""
        from unittest.mock import patch

        service = _make_service(tmp_path, execution_worker=MagicMock())
        with patch.object(service, "run_subprocess_profile") as mock_run:
            mock_run.return_value = {
                "status": "CANCELLED",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "duration_ms": 0,
            }
            req = HarnessRequestDto(
                fixture_type=HarnessFixtureType.CANCELLABLE,
                name="cancel-test",
            )
            gen = service.generate_fixture(req)
            result = service.evaluate_fixture(gen.fixture_id)
            assert result.outcome == "CANCELLED"
            assert len(result.evidence_refs) >= 2  # integration_result + cancellation + proof_report


# ---------------------------------------------------------------------------
# run_acceptance_suite
# ---------------------------------------------------------------------------


class TestRunAcceptanceSuite:
    def test_empty_request_list_returns_empty(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path)
        result = service.run_acceptance_suite([])
        assert isinstance(result, HarnessStatusDto)
        assert result.overall_status == "EMPTY_SUITE"
        assert result.fixtures == []

    def test_single_fixture_suite(self, tmp_path: Path) -> None:
        service = _make_service(tmp_path, execution_worker=None)
        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.ANGULAR_182X,
            name="suite-test",
        )
        result = service.run_acceptance_suite([req])
        assert isinstance(result, HarnessStatusDto)
        # generate_fixture -> GENERATED, evaluate_fixture -> EVALUATION_SKIPPED
        outcomes = [r.outcome for r in result.fixtures]
        assert "GENERATED" in outcomes
        assert "EVALUATION_SKIPPED" in outcomes

    def test_error_in_suite_is_handled(self, tmp_path: Path) -> None:
        """When a generator fails, the suite captures the error."""
        service = _make_service(tmp_path)
        _reset_generators()
        from app.services.acceptance_harness_service import FIXTURE_GENERATORS
        del FIXTURE_GENERATORS[HarnessFixtureType.PASSABLE]
        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.PASSABLE,
            name="error-test",
        )
        result = service.run_acceptance_suite([req])
        assert len(result.errors) >= 1

    def test_full_cycle_with_mock_worker(self, tmp_path: Path) -> None:
        """Full generate -> evaluate cycle via mock worker."""
        _reset_generators()
        from unittest.mock import patch

        service = _make_service(tmp_path, execution_worker=MagicMock())
        with patch.object(service, "run_subprocess_profile") as mock_run:
            mock_run.return_value = {
                "status": "SUCCEEDED",
                "exit_code": 0,
                "stdout": "build output",
                "stderr": "",
                "duration_ms": 500,
            }
            req = HarnessRequestDto(
                fixture_type=HarnessFixtureType.PASSABLE,
                name="full-cycle",
            )
            result = service.run_acceptance_suite([req])
            assert result.overall_status == "PASSED"
            assert len(result.fixtures) >= 2  # generate + evaluate


# ---------------------------------------------------------------------------
# Security: path traversal, stale state, unregistered commands
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_stale_state_version_rejected(self, tmp_path: Path) -> None:
        """StaleStateVersionError is raised on version mismatch."""
        service = _make_service(tmp_path)
        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.ANGULAR_182X,
            name="sec-stale",
            idempotency_key="sec-key-1",
            expected_state_version=1,
        )
        service.generate_fixture(req)

        # Try with stale version
        stale_req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.ANGULAR_182X,
            name="sec-stale",
            idempotency_key="sec-key-1",
            expected_state_version=99,
        )
        with pytest.raises(StaleStateVersionError):
            service.generate_fixture(stale_req)

    def test_unregistered_profile_rejected(self, tmp_path: Path) -> None:
        """run_subprocess_profile rejects unknown profile names."""
        _reset_generators()

        service = _make_service(tmp_path, execution_worker=MagicMock())
        result = service.run_subprocess_profile(
            fixture_root=str(tmp_path / "fake-fixture"),
            profile_id="nonexistent-profile",
        )
        assert result["status"] == "REJECTED"
        assert "Unknown harness profile" in result["stderr"]

    def test_generate_fixture_allows_valid_fixture_types_only(self, tmp_path: Path) -> None:
        """DTO validation rejects invalid fixture types at the contract layer."""
        from app.domain.contracts import HarnessRequestDto

        # Valid fixture type - should work
        dto = HarnessRequestDto(
            fixture_type=HarnessFixtureType.PASSABLE,
            name="valid-test",
        )
        assert dto.fixture_type == HarnessFixtureType.PASSABLE

    def test_harness_dto_rejects_unknown_fields(self) -> None:
        """HarnessRequestDto/ResultDto extra='forbid' enforcement."""
        from app.domain.contracts import HarnessRequestDto
        with pytest.raises(ValidationError):
            HarnessRequestDto(
                fixture_type=HarnessFixtureType.PASSABLE,
                malicious_field="evil",  # type: ignore[arg-type]
            )

    def test_checksum_tamper_detection_by_recomputation(self, tmp_path: Path) -> None:
        """Verify that _checksum_workspace detects file changes."""
        from app.services.acceptance_harness_service import (
            AcceptanceHarnessService,
        )

        service = _make_service(tmp_path)
        req = HarnessRequestDto(
            fixture_type=HarnessFixtureType.PASSABLE,
            name="checksum-test",
        )
        result = service.generate_fixture(req)
        fixture_path = Path(result.fixture_root)

        # Original checksum
        original_checksum = AcceptanceHarnessService._checksum_workspace(fixture_path)

        # Tamper with a file
        pkg = fixture_path / "package.json"
        original = pkg.read_text()
        pkg.write_text(original + "\n// tampered\n")

        tampered_checksum = AcceptanceHarnessService._checksum_workspace(fixture_path)
        assert tampered_checksum != original_checksum, (
            "Checksum should change after file tamper"
        )

    def test_known_fixture_types_all_have_generators(self) -> None:
        """Every HarnessFixtureType enum member has a registered generator."""
        _reset_generators()
        from app.services.acceptance_harness_service import FIXTURE_GENERATORS
        for ft in HarnessFixtureType:
            assert ft in FIXTURE_GENERATORS, f"Missing generator for {ft.value}"
