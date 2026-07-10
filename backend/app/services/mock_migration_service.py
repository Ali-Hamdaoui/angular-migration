"""Read-only static state, not orchestration or persistence."""
from datetime import UTC, datetime
from app.domain.mock_migration import MockMigrationRunResponse, MockMigrationStageResponse

def get_mock_migration_run() -> MockMigrationRunResponse:
    return MockMigrationRunResponse(
        run_id="mock-run-angular-18-to-21", status="mock_ready",
        source_angular_version="18.x", target_angular_version="21.x", created_at=datetime.now(UTC),
        stages=[
            MockMigrationStageResponse(stage_id="angular-18-to-19", source_angular_version="18.x", target_angular_version="19.x", status="pending"),
            MockMigrationStageResponse(stage_id="angular-19-to-20", source_angular_version="19.x", target_angular_version="20.x", status="pending"),
            MockMigrationStageResponse(stage_id="angular-20-to-21", source_angular_version="20.x", target_angular_version="21.x", status="pending"),
        ],
    )
