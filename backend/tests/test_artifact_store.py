"""Tests for the local filesystem artifact store and artifact routes."""

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


def test_store_writes_lists_and_reads_artifacts(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")

    stored = store.write_text_artifact(
        "mock-run-angular-18-to-21",
        "03_planning/mock_plan.md",
        "# Mock plan\n",
        ArtifactType.MARKDOWN,
        stage_id="03_planning",
        created_by="planning-agent",
    )

    listed = store.list_artifacts("mock-run-angular-18-to-21")
    reopened = store.read_artifact("mock-run-angular-18-to-21", "03_planning/mock_plan.md")

    assert stored.ref.checksum is not None
    assert stored.ref.checksum.startswith("sha256:")
    assert stored.ref.relative_path == "03_planning/mock_plan.md"
    assert stored.created_by == "planning-agent"
    assert listed == [stored.ref]
    assert reopened.ref == stored.ref
    assert reopened.content == "# Mock plan\n"
    assert reopened.created_by == "planning-agent"
    assert (tmp_path / "runs" / "mock-run-angular-18-to-21" / "03_planning" / "mock_plan.md.meta.json").is_file()


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


def test_store_raises_for_missing_artifacts(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")

    with pytest.raises(ArtifactNotFoundError):
        store.read_artifact("mock-run-angular-18-to-21", "03_planning/missing.md")


def test_store_raises_for_directory_artifact_paths(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")
    store.ensure_run_layout("mock-run-angular-18-to-21")

    with pytest.raises(ArtifactNotFoundError):
        store.read_artifact("mock-run-angular-18-to-21", "03_planning")

def test_artifact_routes_list_and_open_store_records(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path / "runs")
    store.write_text_artifact(
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
    read_response = client.get("/migrations/mock-run-angular-18-to-21/artifacts/08_final/final_report.md")

    assert list_response.status_code == 200
    assert list_response.json()[0]["relative_path"] == "08_final/final_report.md"
    assert read_response.status_code == 200
    body = read_response.json()
    assert body["artifact"]["relative_path"] == "08_final/final_report.md"
    assert body["content"] == "Final report content"
    assert body["created_by"] == "report-agent"
