from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.domain.path_validation import PathValidationRequest
from app.services.path_validation_service import PathValidationService


def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        artifact_root=tmp_path / "runs",
        workspace_root=tmp_path / "workspaces",
        snapshot_root=tmp_path / "snapshots",
        delivery_root=tmp_path / "delivery",
        sandbox_root=tmp_path / "sandboxes",
        allowed_source_roots=[tmp_path / "sources"],
        allowed_target_roots=[tmp_path / "targets"],
        minimum_free_disk_bytes=0,
    )


def test_validate_canonicalizes_paths_and_fingerprints_source(tmp_path):
    source = tmp_path / "sources" / "project"
    target_root = tmp_path / "targets"
    source.mkdir(parents=True)
    target_root.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")

    service = PathValidationService(
        settings(tmp_path),
        now_provider=lambda: datetime(2026, 7, 14, tzinfo=UTC),
    )
    result = service.validate(
        PathValidationRequest(
            source_path=str(source / "."), target_output_path=str(target_root / ".." / "targets" / "out"), idempotency_key="path-1"
        )
    )

    assert result.snapshot.status == "passed"
    assert result.snapshot.source_path == str(source.resolve())
    assert result.snapshot.target_parent_path == str((target_root / "out").resolve())
    assert result.snapshot.generated_output_name == "project-angular-21"
    assert result.snapshot.resolved_output_root == str((target_root / "out" / "project-angular-21").resolve())
    assert result.snapshot.source_fingerprint is not None
    assert result.snapshot.target_reservation_eligible is True


def test_validate_blocks_overlap_network_and_internal_paths(tmp_path):
    source = tmp_path / "sources" / "project"
    source.mkdir(parents=True)
    internal_target = tmp_path / "runs" / "output"
    service = PathValidationService(settings(tmp_path))

    result = service.validate(
        PathValidationRequest(
            source_path=str(source),
            target_output_path=str(source / "nested"),
            idempotency_key="path-2",
        )
    )

    assert result.snapshot.status == "blocked"
    assert "OUTPUT_ROOT_INSIDE_SOURCE" in result.snapshot.blockers

def test_validate_previews_a_future_output_root_without_creating_directories(tmp_path):
    source = tmp_path / "sources" / "project"
    target_parent = tmp_path / "targets"
    source.mkdir(parents=True)
    target_parent.mkdir()

    result = PathValidationService(settings(tmp_path)).validate(
        PathValidationRequest(
            source_path=str(source),
            target_parent_path=str(target_parent),
            idempotency_key="future-output-preview",
        )
    )

    output = Path(result.snapshot.resolved_output_root)
    assert result.snapshot.status == "passed"
    assert output == target_parent / "project-angular-21"
    assert not output.exists()
    assert not (output / ".migration-factory").exists()
    assert not (output / "migrated-app").exists()

def test_validate_blocks_paths_outside_the_configured_target_root(tmp_path: Path):
    source = tmp_path / "external-source" / "angular-app"
    target_parent = tmp_path / "external-targets"
    source.mkdir(parents=True)
    target_parent.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")
    service = PathValidationService(
        Settings(
            _env_file=None,
            artifact_root=tmp_path / "artifacts",
            workspace_root=tmp_path / "workspaces",
            snapshot_root=tmp_path / "snapshots",
            delivery_root=tmp_path / "delivery",
            sandbox_root=tmp_path / "sandboxes",
            platform_repository_root=tmp_path / "platform-repository",
            allowed_source_roots=[tmp_path / "legacy-source-root"],
            allowed_target_roots=[tmp_path / "legacy-target-root"],
            minimum_free_disk_bytes=0,
        )
    )

    result = service.validate(
        PathValidationRequest(
            source_path=str(source),
            target_parent_path=str(target_parent),
            idempotency_key="external-paths",
        )
    )

    assert result.snapshot.status == "blocked"
    assert "TARGET_PARENT_OUTSIDE_ALLOWED_ROOTS" in result.snapshot.blockers
    assert "OUTPUT_ROOT_OUTSIDE_ALLOWED_ROOTS" in result.snapshot.blockers


def test_validate_allows_nested_target_and_rejects_sibling_prefix(tmp_path: Path):
    source = tmp_path / "sources" / "angular-app"
    target_root = tmp_path / "targets"
    source.mkdir(parents=True)
    target_root.mkdir()
    service = PathValidationService(Settings(_env_file=None, artifact_root=tmp_path / "artifacts", workspace_root=tmp_path / "workspaces", snapshot_root=tmp_path / "snapshots", delivery_root=tmp_path / "delivery", sandbox_root=tmp_path / "sandboxes", allowed_target_roots=[target_root], minimum_free_disk_bytes=0))

    nested = service.validate(PathValidationRequest(source_path=str(source), target_parent_path=str(target_root / "nested"), idempotency_key="nested"))
    sibling = service.validate(PathValidationRequest(source_path=str(source), target_parent_path=str(tmp_path / "targets-sibling"), idempotency_key="sibling"))

    assert "TARGET_PARENT_OUTSIDE_ALLOWED_ROOTS" not in nested.snapshot.blockers
    assert "TARGET_PARENT_OUTSIDE_ALLOWED_ROOTS" in sibling.snapshot.blockers
