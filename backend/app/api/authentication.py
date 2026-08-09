"""Boundary for identities asserted by the authenticated control plane."""

from fastapi import Header, HTTPException

from app.repositories.models import MigrationRunModel


def require_authenticated_actor(actor: str | None) -> str:
    """Require a non-blank principal for run-scoped Assistant access."""
    if actor and actor.strip():
        return actor.strip()
    raise HTTPException(
        status_code=401,
        detail={
            "error_code": "assistant_authentication_required",
            "message": "An authenticated actor is required.",
            "details": {},
        },
    )


def authenticated_actor(x_authenticated_actor: str | None = Header(default=None)) -> str:
    """Legacy identity seam retained for non-Assistant compatibility routes."""
    return x_authenticated_actor.strip() if x_authenticated_actor and x_authenticated_actor.strip() else "local-operator"


def assistant_authenticated_actor(x_authenticated_actor: str | None = Header(default=None)) -> str:
    """Resolve the Assistant principal and fail closed when it is absent."""
    return require_authenticated_actor(x_authenticated_actor)


def authorize_run(
    session,
    run_id: str,
    actor: str,
    *,
    forbidden_code: str = "RUN_ACCESS_FORBIDDEN",
) -> MigrationRunModel:
    """Authorize an authenticated actor for one persisted migration run."""
    actor = require_authenticated_actor(actor)
    run = session.get(MigrationRunModel, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "RUN_NOT_FOUND", "message": "Migration run does not exist.", "details": {}},
        )
    if run.actor and run.actor != actor:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": forbidden_code,
                "message": "Authenticated actor is not authorized for this run.",
                "details": {},
            },
        )
    return run
