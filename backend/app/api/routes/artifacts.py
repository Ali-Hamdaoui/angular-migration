"""Artifact read endpoints backed by the local filesystem artifact store."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.artifact_store.local_store import ArtifactNotFoundError, ArtifactStoreError, LocalFilesystemArtifactStore
from app.core.config import get_settings
from app.domain.contracts import ArtifactRefDto

router = APIRouter(prefix="/migrations", tags=["artifacts"])


class ArtifactContentResponse(BaseModel):
    artifact: ArtifactRefDto
    content: str
    created_by: str | None = None


def get_artifact_store() -> LocalFilesystemArtifactStore:
    return LocalFilesystemArtifactStore(get_settings().artifact_root)


@router.get("/{run_id}/artifacts", response_model=list[ArtifactRefDto], summary="List run artifacts")
def list_run_artifacts(run_id: str) -> list[ArtifactRefDto]:
    try:
        return get_artifact_store().list_artifacts(run_id)
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact run identifier") from exc


@router.get(
    "/{run_id}/artifacts/{artifact_path:path}",
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