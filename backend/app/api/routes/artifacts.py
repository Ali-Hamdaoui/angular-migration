"""Artifact read endpoints backed by the local filesystem artifact store."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.artifact_store.local_store import ArtifactNotFoundError, ArtifactStoreError, LocalFilesystemArtifactStore
from app.core.config import get_settings
from app.domain.contracts import ArtifactRefDto, ArtifactType

router = APIRouter(tags=["artifacts"])


class ArtifactContentResponse(BaseModel):
    artifact: ArtifactRefDto
    content: str
    created_by: str | None = None


def get_artifact_store() -> LocalFilesystemArtifactStore:
    return LocalFilesystemArtifactStore(get_settings().artifact_root)


@router.get("/migrations/{run_id}/artifacts", response_model=list[ArtifactRefDto], summary="List run artifacts")
def list_run_artifacts(run_id: str) -> list[ArtifactRefDto]:
    try:
        return get_artifact_store().list_artifacts(run_id)
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact run identifier") from exc


@router.get(
    "/migrations/{run_id}/artifacts/{artifact_path:path}",
    response_model=ArtifactContentResponse,
    summary="Open a stored artifact",
)
def read_run_artifact(run_id: str, artifact_path: str) -> ArtifactContentResponse:
    try:
        stored_artifact = get_artifact_store().read_artifact(run_id, artifact_path)
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact path") from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    return ArtifactContentResponse(
        artifact=stored_artifact.ref,
        content=stored_artifact.content,
        created_by=stored_artifact.created_by,
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactRefDto, summary="Open artifact metadata by ID")
def read_artifact_metadata(artifact_id: str) -> ArtifactRefDto:
    return ArtifactRefDto(
        artifact_id=artifact_id,
        run_id="mock-run-angular-18-to-21",
        stage_id=None,
        artifact_type=ArtifactType.MARKDOWN,
        relative_path="mock/artifact-metadata-only.md",
        created_at=datetime.now(UTC),
        checksum="mock-artifact-checksum",
    )
