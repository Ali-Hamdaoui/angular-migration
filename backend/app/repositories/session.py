"""SQLAlchemy engine and session factory owned by the backend."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_database_engine(database_url: str) -> Engine:
    """Create an engine and prepare a local parent directory for SQLite files."""
    url = make_url(database_url)
    connect_args: dict[str, bool] = {}
    if url.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
        if url.database and url.database != ":memory:":
            Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args=connect_args, future=True)


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