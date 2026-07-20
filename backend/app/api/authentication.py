"""Boundary for identities asserted by the authenticated control plane."""

from fastapi import Header, HTTPException

from app.repositories.models import MigrationRunModel


def authenticated_actor(x_authenticated_actor: str | None = Header(default=None)) -> str:
    """Return a server-derived identity; never accept it in request JSON."""
    if x_authenticated_actor and x_authenticated_actor.strip():
        return x_authenticated_actor.strip()
    # Local development is a single-operator control plane.
    return "local-operator"


def authorize_run(session, run_id: str, actor: str) -> MigrationRunModel:
    """Authorize an authenticated actor for one persisted migration run."""
    run = session.get(MigrationRunModel, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Migration run does not exist.")
    if run.actor and run.actor != actor:
        raise HTTPException(
            status_code=403,
            detail="Authenticated actor is not authorized for this run.",
        )
    return run
