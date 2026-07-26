"""Datetime rules for values persisted by the control tower."""

from datetime import UTC, datetime


class PersistedTimestampError(ValueError):
    """Raised when a persisted timestamp cannot be normalized safely."""


def normalize_persisted_utc(value: datetime | None) -> datetime | None:
    """Normalize a repository timestamp to an aware UTC datetime.

    The SQLite persistence contract stores application timestamps in UTC.
    SQLite may therefore return those values without tzinfo on round-trip; a
    naive persisted value is interpreted as UTC only under that contract.
    """
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise PersistedTimestampError("PERSISTED_TIMESTAMP_INVALID")
    try:
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC)
    except (OverflowError, TypeError, ValueError) as error:
        raise PersistedTimestampError("PERSISTED_TIMESTAMP_INVALID") from error
