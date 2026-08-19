from types import SimpleNamespace

import pytest

from app.services.baseline_aware_validation_service import (
    BaselineAwareValidationService,
    BaselineValidationClassification,
)
from app.artifact_store import LocalFilesystemArtifactStore
from app.domain.contracts import ArtifactType
from app.services.validation_runner import ValidationRunner


class FakeSession:
    def __init__(self, values, run, metadata=None):
        self.values = iter(values)
        self.run = run
        self.metadata = metadata or {}

    def scalar(self, _statement):
        return next(self.values)

    def get(self, _model, _run_id):
        if getattr(_model, "__name__", "") == "ArtifactMetadataModel":
            return self.metadata.get(_run_id)
        return self.run


@pytest.fixture
def evidence_factory(tmp_path):
    def build(
        *,
        current_stdout=None,
        current_stderr="",
        baseline_stdout=None,
        baseline_stderr="",
        assessment_status="qualified_with_known_failures",
        approval_package="package",
        assessment_package="package",
    ):
        run_root = tmp_path / "run"
        store = LocalFilesystemArtifactStore(
            run_root.parent,
            fixed_run_root=run_root,
        )
        baseline_stdout = baseline_stdout or (
            "C:/baseline/.migration-factory/runs/run-1/baseline-sandbox/"
            "src/app/app.component.ts:1:2\n"
            "ERROR: 1:2 rule-a baseline issue\n"
        )
        current_stdout = current_stdout or baseline_stdout.replace(
            "baseline-sandbox", "stage-sandboxes/stage-1"
        )
        baseline_stdout_artifact = store.write_text_artifact(
            "run-1", "01_baseline/lint.stdout.log", baseline_stdout, ArtifactType.TEXT_LOG
        )
        baseline_stderr_artifact = store.write_text_artifact(
            "run-1", "01_baseline/lint.stderr.log", baseline_stderr, ArtifactType.TEXT_LOG
        )
        current_stdout_artifact = store.write_text_artifact(
            "run-1", "04_workflow_state/current.stdout.log", current_stdout, ArtifactType.TEXT_LOG
        )
        current_stderr_artifact = store.write_text_artifact(
            "run-1", "04_workflow_state/current.stderr.log", current_stderr, ArtifactType.TEXT_LOG
        )
        run = SimpleNamespace(artifact_root=str(run_root))
        assessment = SimpleNamespace(
            status=assessment_status,
            known_failures=[{"kind": "lint", "origin": "pre-existing"}],
            package_checksum=assessment_package,
            evidence_set_checksum="evidence",
        )
        approval = SimpleNamespace(
            status="approved",
            package_checksum=approval_package,
            evidence_set_checksum="evidence",
        )
        baseline = SimpleNamespace(
            artifact_ids=[
                baseline_stdout_artifact.ref.artifact_id,
                baseline_stderr_artifact.ref.artifact_id,
            ],
            artifact_checksums={
                baseline_stdout_artifact.ref.artifact_id: baseline_stdout_artifact.ref.checksum,
                baseline_stderr_artifact.ref.artifact_id: baseline_stderr_artifact.ref.checksum,
            },
        )
        execution = SimpleNamespace(
            status="failed",
            exit_code=1,
            stdout_artifact_id=current_stdout_artifact.ref.artifact_id,
            stderr_artifact_id=current_stderr_artifact.ref.artifact_id,
            artifact_ids=[
                current_stdout_artifact.ref.artifact_id,
                current_stderr_artifact.ref.artifact_id,
            ],
        )
        metadata = {}
        for stored in (
            baseline_stdout_artifact,
            baseline_stderr_artifact,
            current_stdout_artifact,
            current_stderr_artifact,
        ):
            metadata["metadata-" + stored.ref.artifact_id] = SimpleNamespace(
                immutable=True,
                run_id="run-1",
                relative_path=stored.ref.relative_path,
                checksum=stored.ref.checksum,
            )
        return FakeSession([assessment, approval, baseline], run, metadata), execution

    return build


def classify(factory):
    session, execution = factory
    result = BaselineAwareValidationService().classify(
        session, run_id="run-1", validation_group="lint", execution=execution
    )
    return result, execution


def test_exact_baseline_lint_is_accepted(evidence_factory):
    result, execution = classify(evidence_factory())

    assert result.classification is BaselineValidationClassification.MATCHED_APPROVED_BASELINE
    assert execution.status == "failed"
    assert execution.exit_code == 1


def test_baseline_subset_is_accepted_when_old_debt_is_removed(evidence_factory):
    result, _ = classify(
        evidence_factory(
            baseline_stdout=(
                "C:/baseline/.migration-factory/runs/run-1/baseline-sandbox/"
                "src/app/app.component.ts:1:2\nERROR: 1:2 rule-a baseline issue\n"
                "C:/baseline/.migration-factory/runs/run-1/baseline-sandbox/"
                "src/app/app.component.ts:2:2\nERROR: 2:2 rule-b old issue\n"
            ),
            current_stdout=(
                "C:/stage/.migration-factory/runs/run-1/stage-sandboxes/stage-1/"
                "src/app/app.component.ts:1:2\nERROR: 1:2 rule-a baseline issue\n"
            ),
        )
    )

    assert result.classification is BaselineValidationClassification.MATCHED_APPROVED_BASELINE


@pytest.mark.parametrize(
    "extra,expected",
    [
        ("ERROR: 2:2 rule-new new issue\n", BaselineValidationClassification.MIXED_FAILURE),
        (
            "C:/stage/src/app/other.ts:3:4\nERROR: 3:4 rule-new new issue\n",
            BaselineValidationClassification.MIXED_FAILURE,
        ),
    ],
)
def test_new_or_mixed_lint_failure_is_rejected(evidence_factory, extra, expected):
    result, _ = classify(
        evidence_factory(
            current_stdout=(
                "C:/stage/.migration-factory/runs/run-1/stage-sandboxes/stage-1/"
                "src/app/app.component.ts:1:2\nERROR: 1:2 rule-a baseline issue\n"
                + extra
            )
        )
    )

    assert result.classification is expected


def test_unqualified_baseline_fails_closed(evidence_factory):
    result, _ = classify(evidence_factory(assessment_status="qualified"))

    assert result.classification is BaselineValidationClassification.NO_APPROVED_BASELINE


def test_missing_baseline_evidence_fails_closed(evidence_factory):
    session, execution = evidence_factory()
    assessment = SimpleNamespace(
        status="qualified_with_known_failures",
        known_failures=[{"kind": "lint", "origin": "pre-existing"}],
        package_checksum="package",
        evidence_set_checksum="evidence",
    )
    approval = SimpleNamespace(
        status="approved", package_checksum="package", evidence_set_checksum="evidence"
    )
    session.values = iter(
        [assessment, approval, SimpleNamespace(artifact_ids=["artifact-missing"])]
    )

    result = BaselineAwareValidationService().classify(
        session, run_id="run-1", validation_group="lint", execution=execution
    )

    assert result.classification is BaselineValidationClassification.EVIDENCE_INVALID


def test_baseline_artifact_checksum_mismatch_fails_closed(evidence_factory):
    session, execution = evidence_factory()
    baseline_id = next(
        key for key in session.metadata if key != "metadata-" + execution.stdout_artifact_id
    )
    session.metadata[baseline_id].checksum = "sha256:corrupt"

    result = BaselineAwareValidationService().classify(
        session, run_id="run-1", validation_group="lint", execution=execution
    )

    assert result.classification is BaselineValidationClassification.EVIDENCE_INVALID


def test_stale_g03_package_fails_closed(evidence_factory):
    result, _ = classify(evidence_factory(approval_package="stale-package"))

    assert result.classification is BaselineValidationClassification.NO_APPROVED_BASELINE


def test_non_lint_failure_is_never_baseline_accepted(evidence_factory):
    session, execution = evidence_factory()
    result = BaselineAwareValidationService().classify(
        session, run_id="run-1", validation_group="build", execution=execution
    )

    assert result.classification is BaselineValidationClassification.NEW_FAILURE


class _RecoverySession:
    def __init__(self, step, execution):
        self.step = step
        self.execution = execution
        self.marked = 0

    def scalars(self, _statement):
        return iter([self.step] if self.step.status == "FAILED" else [])

    def get(self, _model, _execution_id):
        return self.execution


def test_known_baseline_recovery_does_not_create_repair_attempt():
    step = SimpleNamespace(name="lint-0", status="FAILED", execution_id="exec-1")
    execution = SimpleNamespace(id="exec-1")
    session = _RecoverySession(step, execution)
    continuation = SimpleNamespace(run_id="run-1", current_stage_id="stage-1")
    runner = ValidationRunner()
    runner._is_known_baseline_failure = lambda *_args: True

    def mark(_session, _continuation, recovered_step, _execution):
        session.marked += 1
        recovered_step.status = "PASSED"

    runner._mark_known_baseline_step = mark

    assert runner.resume_known_baseline_failures(session, continuation) is True
    assert session.marked == 1
    assert step.status == "PASSED"


def test_known_baseline_recovery_is_idempotent():
    step = SimpleNamespace(name="lint-0", status="FAILED", execution_id="exec-1")
    execution = SimpleNamespace(id="exec-1")
    session = _RecoverySession(step, execution)
    continuation = SimpleNamespace(run_id="run-1", current_stage_id="stage-1")
    runner = ValidationRunner()
    runner._is_known_baseline_failure = lambda *_args: True
    calls = []

    def mark(_session, _continuation, recovered_step, _execution):
        calls.append(recovered_step.name)
        recovered_step.status = "PASSED"

    runner._mark_known_baseline_step = mark

    assert runner.resume_known_baseline_failures(session, continuation) is True
    assert runner.resume_known_baseline_failures(session, continuation) is False
    assert calls == ["lint-0"]
