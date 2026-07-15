"""Artifact read endpoints backed by the local filesystem artifact store."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.artifact_store.local_store import ArtifactNotFoundError, ArtifactStoreError, LocalFilesystemArtifactStore
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel
from app.repositories.session import session_scope
from app.domain.contracts import ArtifactRefDto

router = APIRouter(tags=["artifacts"])


class ArtifactContentResponse(BaseModel):
    artifact: ArtifactRefDto
    content: str
    created_by: str | None = None


def get_artifact_store(run_id: str) -> LocalFilesystemArtifactStore:
    with session_scope() as session:
        run = session.get(MigrationRunModel, run_id)
        if run is None or not run.artifact_root:
            raise ArtifactNotFoundError(run_id)
        root = Path(run.artifact_root).resolve()
    return LocalFilesystemArtifactStore(root, fixed_run_root=root)
@router.get("/migrations/{run_id}/artifacts", response_model=list[ArtifactRefDto], summary="List run artifacts")
def list_run_artifacts(run_id: str) -> list[ArtifactRefDto]:
    try:
        return get_artifact_store(run_id).list_artifacts(run_id)
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact run identifier") from exc


@router.get(
    "/migrations/{run_id}/artifacts/{artifact_path:path}",
    response_model=ArtifactContentResponse,
    summary="Open a stored artifact by run path",
)
def read_run_artifact(run_id: str, artifact_path: str) -> ArtifactContentResponse:
    try:
        stored_artifact = get_artifact_store(run_id).read_artifact(run_id, artifact_path)
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact path") from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    return ArtifactContentResponse(
        artifact=stored_artifact.ref,
        content=stored_artifact.content,
        created_by=stored_artifact.created_by,
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactContentResponse, summary="Open a stored artifact by ID")
def read_artifact_by_id(artifact_id: str) -> ArtifactContentResponse:
    try:
        with session_scope() as session:
            metadata = session.get(ArtifactMetadataModel, f"metadata-{artifact_id}")
            if metadata is None:
                raise ArtifactNotFoundError(artifact_id)
            run = session.get(MigrationRunModel, metadata.run_id)
            if run is None or not run.artifact_root:
                raise ArtifactNotFoundError(artifact_id)
            root = Path(run.artifact_root).resolve()
        stored_artifact = LocalFilesystemArtifactStore(root, fixed_run_root=root).read_artifact_by_id(artifact_id)
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact identifier") from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    return ArtifactContentResponse(
        artifact=stored_artifact.ref,
        content=stored_artifact.content,
        created_by=stored_artifact.created_by,
    )
