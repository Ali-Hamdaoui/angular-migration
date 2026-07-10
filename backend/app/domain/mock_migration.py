"""Temporary mock DTO; AMF-S0-05 replaces it with shared contracts."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class MockMigrationStageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    stage_id: str
    source_angular_version: str
    target_angular_version: str
    status: str

class MockMigrationRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str
    status: str
    source_angular_version: str
    target_angular_version: str
    created_at: datetime
    stages: list[MockMigrationStageResponse] = Field(min_length=1)
