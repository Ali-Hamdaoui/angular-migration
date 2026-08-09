from pathlib import Path
import os

from app.repositories.session import resolved_database_path


def test_pytest_never_uses_the_operational_control_tower_database():
    operational_database = (
        Path(os.environ["LOCALAPPDATA"])
        / "AngularMigrationControlTower"
        / "control-tower.db"
    ).resolve()

    assert resolved_database_path() != operational_database
