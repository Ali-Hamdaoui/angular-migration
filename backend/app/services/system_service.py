"""System metadata service."""

from app.core.application import APP_NAME, APP_VERSION
from app.core.config import get_settings
from app.domain.system import HealthResponse, VersionResponse


def get_health_status() -> HealthResponse:
    return HealthResponse(status="ok")


def get_version_info() -> VersionResponse:
    settings = get_settings()
    return VersionResponse(name=APP_NAME, version=APP_VERSION, environment=settings.app_env)