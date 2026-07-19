"""Artifact read endpoints backed by the local filesystem artifact store."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.artifact_store.local_store import ArtifactNotFoundError, ArtifactStoreError, LocalFilesystemArtifactStore
from app.repositories.models import ArtifactMetadataModel, MigrationRunModel
from app.repositories.preflight_models import PreflightArtifactMetadataModel, PreflightModel
from app.core.config import get_settings
from app.repositories.session import session_scope
from app.domain.contracts import ArtifactRefDto
from app.api.authentication import authenticated_actor

router = APIRouter(tags=["artifacts"])


class ArtifactContentResponse(BaseModel):
    artifact: ArtifactRefDto
    content: str
    created_by: str | None = None


def _authorize_run(session, run_id: str, actor: str) -> None:
    run = session.get(MigrationRunModel, run_id)
    if run is not None and run.actor and run.actor != actor:
        raise HTTPException(status_code=403, detail='Authenticated actor is not authorized for this run.')


def _authorize_preflight(session, preflight_id: str, actor: str) -> None:
    preflight = session.get(PreflightModel, preflight_id)
    if preflight is not None and getattr(preflight, 'actor', None) and preflight.actor != actor:
        raise HTTPException(status_code=403, detail='Authenticated actor is not authorized for this preflight.')

def get_artifact_store(run_id: str) -> LocalFilesystemArtifactStore:
    with session_scope() as session:
        run = session.get(MigrationRunModel, run_id)
        if run is None or not run.artifact_root:
            raise ArtifactNotFoundError(run_id)
        root = Path(run.artifact_root).resolve()
    return LocalFilesystemArtifactStore(root, fixed_run_root=root)
@router.get("/migrations/{run_id}/artifacts", response_model=list[ArtifactRefDto], summary="List run artifacts")
def list_run_artifacts(run_id: str, actor: str = Depends(authenticated_actor)) -> list[ArtifactRefDto]:
    try:
        with session_scope() as session:
            _authorize_run(session, run_id, actor)
        return get_artifact_store(run_id).list_artifacts(run_id)
    except ArtifactStoreError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact run identifier") from exc


@router.get(
    "/migrations/{run_id}/artifacts/{artifact_path:path}",
    response_model=ArtifactContentResponse,
    summary="Open a stored artifact by run path",
)
def read_run_artifact(run_id: str, artifact_path: str, actor: str = Depends(authenticated_actor)) -> ArtifactContentResponse:
    try:
        with session_scope() as session:
            _authorize_run(session, run_id, actor)
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
def read_artifact_by_id(artifact_id: str, actor: str = Depends(authenticated_actor)) -> ArtifactContentResponse:
    try:
        with session_scope() as session:
            metadata = session.get(ArtifactMetadataModel, f"metadata-{artifact_id}")
            if metadata is not None:
                run = session.get(MigrationRunModel, metadata.run_id)
                if run is None or not run.artifact_root:
                    raise ArtifactNotFoundError(artifact_id)
                _authorize_run(session, run.id, actor)
                root = Path(run.artifact_root).resolve()
            else:
                preflight_metadata = session.get(PreflightArtifactMetadataModel, f"metadata-{artifact_id}")
                if preflight_metadata is None or session.get(PreflightModel, preflight_metadata.preflight_id) is None:
                    raise ArtifactNotFoundError(artifact_id)
                _authorize_preflight(session, preflight_metadata.preflight_id, actor)
                root = (get_settings().artifact_root / "preflights" / preflight_metadata.preflight_id).resolve()
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
