from pydantic import BaseModel, ConfigDict

class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: str

class VersionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    version: str
    environment: str
