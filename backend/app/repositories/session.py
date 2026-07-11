"""SQLAlchemy engine and session factory owned by the backend."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, make_url, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_database_engine(
    database_url: str,
    *,
    sqlite_wal_enabled: bool | None = None,
    sqlite_busy_timeout_ms: int | None = None,
) -> Engine:
    """Create an engine and apply SQLite MVP connection pragmas."""
    settings = get_settings()
    wal_enabled = settings.sqlite_wal_enabled if sqlite_wal_enabled is None else sqlite_wal_enabled
    busy_timeout_ms = (
        settings.sqlite_busy_timeout_ms if sqlite_busy_timeout_ms is None else sqlite_busy_timeout_ms
    )
    url = make_url(database_url)
    connect_args: dict[str, bool] = {}
    if url.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
        if url.database and url.database != ":memory:":
            Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args=connect_args, future=True)

    if url.get_backend_name() == "sqlite":
        is_file_database = bool(url.database and url.database != ":memory:")

        @event.listens_for(engine, "connect")
        def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
            if wal_enabled and is_file_database:
                cursor.execute("PRAGMA journal_mode = WAL")
            cursor.close()

    return engine


engine = create_database_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def check_database_connection() -> None:
    """Verify connectivity without creating or changing workflow records."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional session for backend repositories and services."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
