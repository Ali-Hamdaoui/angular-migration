"""SQLAlchemy declarative base for backend persistence models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class shared by all persisted backend-owned state."""