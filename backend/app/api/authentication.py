"""Boundary for identities asserted by the authenticated control plane."""

from fastapi import Header


def authenticated_actor(x_authenticated_actor: str | None = Header(default=None)) -> str:
    """Return a server-derived identity; never accept it in request JSON."""
    if x_authenticated_actor and x_authenticated_actor.strip():
        return x_authenticated_actor.strip()
    # Local development is a single-operator control plane.
    return "local-operator"
