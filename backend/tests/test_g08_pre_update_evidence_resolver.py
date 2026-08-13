from types import SimpleNamespace

import pytest

from app.services.g08_pre_update_evidence_resolver import (
    G08PreUpdateEvidenceError,
    G08PreUpdateEvidenceResolver,
)
from app.services.g08_ledger_regeneration_service import G08LedgerRegenerationService


def _checkpoint(checkpoint_id: str, kind: str, fingerprint: str, path: str, **values):
    return SimpleNamespace(
        id=checkpoint_id,
        kind=kind,
        workspace_fingerprint=fingerprint,
        workspace_path=path,
        safe_for_resume=values.get("safe_for_resume", True),
        sealed=values.get("sealed", False),
    )


def test_first_11_to_12_stage_uses_immutable_baseline_as_pre_update_evidence():
    angular_checkpoint = _checkpoint(
        "pre-angular-11", "pre_angular_update", "sha256:angular-11", "live-stage"
    )

    evidence = G08PreUpdateEvidenceResolver.resolve_records(
        stage_order=1,
        baseline_path="sealed-baseline-angular-11",
        angular_checkpoint=angular_checkpoint,
        pre_bootstrap=None,
        previous_stage=None,
        sealed_source=None,
    )

    assert evidence.path == "sealed-baseline-angular-11"
    assert evidence.checkpoint_id == "pre-angular-11"
    assert evidence.fingerprint == "sha256:angular-11"


@pytest.mark.parametrize(
    ("stage_order", "source_major", "target_major"),
    [(2, 12, 13), (3, 13, 14)],
)
def test_successor_stage_automatically_uses_previous_sealed_output_only(
    stage_order: int, source_major: int, target_major: int
):
    fingerprint = f"sha256:angular-{source_major}"
    live_path = f"live-transformed-angular-{target_major}"
    angular_checkpoint = _checkpoint(
        f"pre-angular-{source_major}", "pre_angular_update", fingerprint, live_path
    )
    pre_bootstrap = _checkpoint("pre-bootstrap", "pre_bootstrap", fingerprint, live_path)
    sealed = _checkpoint(
        f"sealed-angular-{source_major}",
        "sealed_output",
        fingerprint,
        f"immutable-angular-{source_major}",
        sealed=True,
    )

    evidence = G08PreUpdateEvidenceResolver.resolve_records(
        stage_order=stage_order,
        baseline_path="must-not-be-used",
        angular_checkpoint=angular_checkpoint,
        pre_bootstrap=pre_bootstrap,
        previous_stage=SimpleNamespace(status="sealed"),
        sealed_source=sealed,
    )

    assert evidence.path == f"immutable-angular-{source_major}"
    assert evidence.path != live_path
    assert evidence.checkpoint_id == f"sealed-angular-{source_major}"


def test_successor_stage_fails_closed_when_sealed_lineage_does_not_match():
    with pytest.raises(
        G08PreUpdateEvidenceError,
        match="previous immutable sealed output",
    ):
        G08PreUpdateEvidenceResolver.resolve_records(
            stage_order=2,
            baseline_path="baseline",
            angular_checkpoint=_checkpoint(
                "pre-angular", "pre_angular_update", "sha256:live", "live"
            ),
            pre_bootstrap=_checkpoint(
                "pre-bootstrap", "pre_bootstrap", "sha256:sealed", "live"
            ),
            previous_stage=SimpleNamespace(status="sealed"),
            sealed_source=_checkpoint(
                "sealed", "sealed_output", "sha256:sealed", "immutable", sealed=True
            ),
        )


def test_g08_regeneration_only_rebuilds_ledger_and_preserves_prior_execution_evidence():
    calls = []

    class EvidenceSpy:
        def migration_ledger(self, before, after, **values):
            calls.append((before, after, values))
            return {"changed_file_count": 1, "changed_files": [{}], "unattributed_files": []}

        def build(self, *args, **kwargs):  # pragma: no cover - a call is the failure
            raise AssertionError("version verification must not be rerun")

    service = G08LedgerRegenerationService()
    service._evidence = EvidenceSpy()

    ledger = service._regenerate_ledger(
        {
            "baseline_path": "immutable-angular-13",
            "workspace_path": "live-angular-14",
            "angular_execution_id": "successful-angular-update",
            "checkpoint_fingerprint": "sha256:angular-13",
        },
        "sha256:angular-14",
    )

    assert ledger["changed_file_count"] == 1
    assert calls == [
        (
            "immutable-angular-13",
            "live-angular-14",
            {
                "angular_execution_id": "successful-angular-update",
                "expected_pre_fingerprint": "sha256:angular-13",
                "expected_post_fingerprint": "sha256:angular-14",
            },
        )
    ]
