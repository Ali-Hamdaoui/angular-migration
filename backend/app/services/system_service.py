from app.core.application import APP_ENVIRONMENT, APP_NAME, APP_VERSION
from app.domain.system import HealthResponse, VersionResponse

def get_health_status() -> HealthResponse:
    return HealthResponse(status="ok")

def get_version_info() -> VersionResponse:
    return VersionResponse(name=APP_NAME, version=APP_VERSION, environment=APP_ENVIRONMENT)
