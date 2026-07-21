"""Boundary for identities asserted by the authenticated control plane."""

from fastapi import Header, HTTPException, status


def authenticated_actor(x_authenticated_actor: str | None = Header(default=None)) -> str:
    """Return a server-derived identity; never accept it in request JSON."""
    if x_authenticated_actor and x_authenticated_actor.strip():
        return x_authenticated_actor.strip()
    # Existing routes retain the local single-operator development projection.
    return "local-operator"


def required_authenticated_actor(x_authenticated_actor: str | None = Header(default=None)) -> str:
    """Strict identity boundary for AMFA-171 protected stage operations."""
    if x_authenticated_actor and x_authenticated_actor.strip():
        return x_authenticated_actor.strip()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication is required")
