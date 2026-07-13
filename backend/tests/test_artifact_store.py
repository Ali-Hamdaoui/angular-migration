"""Tests for the local filesystem artifact store and artifact routes."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.artifact_store.local_store import (
    ARTIFACT_LAYOUT,
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalFilesystemArtifactStore,
)
from app.domain.contracts import ArtifactType
from app.main import app


def test_store_creates_canonical_run_layout(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")

    run_root = store.ensure_run_layout("mock-run-angular-18-to-21")

    assert run_root == tmp_path / "runs" / "mock-run-angular-18-to-21"
    assert all((run_root / folder).is_dir() for folder in ARTIFACT_LAYOUT)
    assert (run_root / "repair_attempts").is_dir()
    assert (run_root / "final_assurance").is_dir()
    assert (run_root / "delivery").is_dir()


def test_store_writes_lists_and_reads_artifacts(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")

    stored = store.write_text_artifact(
        "mock-run-angular-18-to-21",
        "03_planning/mock_plan.md",
        "# Mock plan\n",
        ArtifactType.MARKDOWN,
        stage_id="angular-18-to-19",
        created_by="planning-agent",
        input_hashes={"source": "sha256:source"},
    )

    listed = store.list_artifacts("mock-run-angular-18-to-21")
    reopened = store.read_artifact("mock-run-angular-18-to-21", stored.ref.relative_path)
    reopened_by_id = store.read_artifact_by_id(stored.ref.artifact_id)

    assert stored.ref.checksum.startswith("sha256:")
    assert stored.ref.artifact_id.startswith("artifact-")
    assert stored.ref.relative_path == "03_planning/mock_plan.md"
    assert stored.created_by == "planning-agent"
    assert stored.envelope is not None
    assert stored.envelope.schema_version == 1
    assert stored.envelope.producer == "planning-agent"
    assert stored.envelope.content_type == "text/markdown"
    assert stored.envelope.input_hashes == {"source": "sha256:source"}
    assert stored.envelope.content_hash == stored.ref.checksum
    assert listed == [stored.ref]
    assert reopened.ref == stored.ref
    assert reopened_by_id.ref == stored.ref
    assert reopened.content == "# Mock plan\n"
    assert reopened.created_by == "planning-agent"
    assert (tmp_path / "runs" / "mock-run-angular-18-to-21" / "03_planning" / "mock_plan.md.meta.json").is_file()


def test_store_never_silently_replaces_existing_artifact_content(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")

    first = store.write_text_artifact("mock-run", "08_final/report.md", "first\n", ArtifactType.MARKDOWN)
    second = store.write_text_artifact("mock-run", "08_final/report.md", "second\n", ArtifactType.MARKDOWN)

    assert first.ref.artifact_id != second.ref.artifact_id
    assert first.ref.relative_path == "08_final/report.md"
    assert second.ref.relative_path == "08_final/report__v2.md"
    assert store.read_artifact_by_id(first.ref.artifact_id).content == "first\n"
    assert store.read_artifact_by_id(second.ref.artifact_id).content == "second\n"


def test_repair_attempt_artifacts_have_independent_directories(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")

    first = store.write_text_artifact(
        "mock-run",
        "repair_attempts/angular-18-to-19/attempt-1/diagnosis.json",
        '{"attempt":1}\n',
        ArtifactType.JSON,
        stage_id="angular-18-to-19",
        attempt_id="attempt-1",
    )
    second = store.write_text_artifact(
        "mock-run",
        "repair_attempts/angular-18-to-19/attempt-2/diagnosis.json",
        '{"attempt":2}\n',
        ArtifactType.JSON,
        stage_id="angular-18-to-19",
        attempt_id="attempt-2",
    )

    assert first.envelope is not None
    assert second.envelope is not None
    assert first.envelope.attempt_id == "attempt-1"
    assert second.envelope.attempt_id == "attempt-2"
    assert first.ref.relative_path != second.ref.relative_path


@pytest.mark.parametrize(
    ("run_id", "relative_path"),
    [
        ("../escape", "03_planning/mock_plan.md"),
        ("mock-run-angular-18-to-21", "../escape.md"),
        ("mock-run-angular-18-to-21", "/absolute.md"),
        ("mock-run-angular-18-to-21", r"nested\\windows-path.md"),
    ],
)
def test_store_rejects_path_traversal(tmp_path: Path, run_id: str, relative_path: str) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")

    with pytest.raises(ArtifactStoreError):
        store.write_text_artifact(run_id, relative_path, "content", ArtifactType.MARKDOWN)


def test_store_rejects_symlink_escape_attempts(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")
    run_root = store.ensure_run_layout("mock-run")
    outside = tmp_path / "outside"
    outside.mkdir()
    symlink = run_root / "03_planning" / "escape"
    try:
        os.symlink(outside, symlink, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable in this environment: {exc}")

    with pytest.raises(ArtifactStoreError):
        store.write_text_artifact("mock-run", "03_planning/escape/hidden.md", "content", ArtifactType.MARKDOWN)


def test_store_raises_for_missing_artifacts(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")

    with pytest.raises(ArtifactNotFoundError):
        store.read_artifact("mock-run-angular-18-to-21", "03_planning/missing.md")

    with pytest.raises(ArtifactNotFoundError):
        store.read_artifact_by_id("artifact-missing")


def test_store_raises_for_directory_artifact_paths(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")
    store.ensure_run_layout("mock-run-angular-18-to-21")

    with pytest.raises(ArtifactNotFoundError):
        store.read_artifact("mock-run-angular-18-to-21", "03_planning")


def test_artifact_routes_list_and_open_store_records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")
    stored = store.write_text_artifact(
        "mock-run-angular-18-to-21",
        "08_final/final_report.md",
        "Final report content",
        ArtifactType.MARKDOWN,
        stage_id="08_final",
        created_by="report-agent",
    )
    monkeypatch.setattr("app.api.routes.artifacts.get_artifact_store", lambda: store)

    client = TestClient(app)

    list_response = client.get("/migrations/mock-run-angular-18-to-21/artifacts")
    read_response = client.get(f"/migrations/mock-run-angular-18-to-21/artifacts/{stored.ref.relative_path}")
    read_by_id_response = client.get(f"/artifacts/{stored.ref.artifact_id}")

    assert list_response.status_code == 200
    assert list_response.json()[0]["relative_path"] == "08_final/final_report.md"
    assert read_response.status_code == 200
    assert read_by_id_response.status_code == 200
    body = read_response.json()
    assert body["artifact"]["relative_path"] == "08_final/final_report.md"
    assert body["content"] == "Final report content"
    assert body["created_by"] == "report-agent"
    assert read_by_id_response.json() == body
