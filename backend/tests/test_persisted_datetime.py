from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.datetime import PersistedTimestampError, normalize_persisted_utc


def test_naive_sqlite_timestamp_is_contractually_utc():
    value = normalize_persisted_utc(datetime(2026, 7, 25, 12, 0))
    assert value == datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def test_aware_utc_and_non_utc_values_preserve_the_instant():
    instant = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    assert normalize_persisted_utc(instant) == instant
    assert normalize_persisted_utc(datetime(2026, 7, 25, 14, 0, tzinfo=timezone(timedelta(hours=2)))) == instant


def test_none_is_explicit_and_invalid_values_have_a_typed_error():
    assert normalize_persisted_utc(None) is None
    with pytest.raises(PersistedTimestampError, match="PERSISTED_TIMESTAMP_INVALID"):
        normalize_persisted_utc("not-a-datetime")  # type: ignore[arg-type]
