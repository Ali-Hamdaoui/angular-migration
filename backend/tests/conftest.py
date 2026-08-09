"""Process-wide isolation for tests that import the application session."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile


_TEST_APPLICATION_DATA_ROOT = Path(
    tempfile.mkdtemp(prefix="angular-migration-pytest-")
).resolve()
_TEST_DATABASE = _TEST_APPLICATION_DATA_ROOT / "control-tower-test.db"

# These overrides must exist before pytest imports any application module.
os.environ["APPLICATION_DATA_ROOT"] = str(_TEST_APPLICATION_DATA_ROOT)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE.as_posix()}"
os.environ["LLM_ENABLED"] = "false"


from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_CONFIG = Config(str(_BACKEND_ROOT / "alembic.ini"))
_ALEMBIC_CONFIG.set_main_option(
    "script_location",
    str(_BACKEND_ROOT / "alembic"),
)
_ALEMBIC_CONFIG.set_main_option(
    "sqlalchemy.url",
    os.environ["DATABASE_URL"],
)
command.upgrade(_ALEMBIC_CONFIG, "heads")
