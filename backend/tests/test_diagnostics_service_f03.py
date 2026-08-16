"""Tests for F03 backend failure diagnostics."""

from datetime import UTC, datetime

import pytest

from app.domain.diagnostics import (
    FailureDiagnosticPack,
    PlatformFault,
    PlatformFaultCategory,
    PlatformFaultSeverity,
)
from app.services.diagnostics_service import (
    bounded_command_output,
    build_diagnostic_pack,
    classify_failure,
    sanitize_traceback,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)


def test_platform_fault_is_typed_and_immutable():
    fault = PlatformFault(
        fault_code="COMMAND_EXIT_NONZERO",
        category=PlatformFaultCategory.COMMAND,
        severity=PlatformFaultSeverity.ERROR,
        message="npm ci failed with exit code 1",
        occurred_at=NOW,
    )
    assert fault.category == PlatformFaultCategory.COMMAND
    with pytest.raises(ValueError):
        fault.fault_code = "other"


def test_classify_failure_uses_error_code_and_details():
    class FakeError(Exception):
        code = "LLM_GATEWAY_TIMEOUT"
        message = "provider timed out"
        details = {"attempt": 3}

    fault = classify_failure(FakeError("x"))
    assert fault.fault_code == "LLM_GATEWAY_TIMEOUT"
    assert fault.category == PlatformFaultCategory.LLM
    assert fault.context == {"attempt": 3}


def test_classify_failure_defaults_for_plain_exception():
    fault = classify_failure(ValueError("boom"))
    assert fault.fault_code == "ValueError"
    assert fault.category == PlatformFaultCategory.UNKNOWN


def test_sanitize_traceback_redacts_secrets_and_ansi():
    raw = "\x1b[31mTraceback:\nAZURE_OPENAI_API_KEY = 4f3a9c1d7e2b8a6f0c5d4e3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a2918\nat 0x7f3ab9c2d0e0\n"
    cleaned = sanitize_traceback(raw)
    assert "\x1b[" not in cleaned
    assert "4f3a9c1d7e2b8a6f0c5d4e3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a2918" not in cleaned
    assert "0x7f3ab9c2d0e0" not in cleaned
    assert "[REDACTED]" in cleaned


def test_sanitize_traceback_bounds_length():
    huge = "x" * 100_000
    cleaned = sanitize_traceback(huge)
    assert len(cleaned) <= 16_100
    assert "truncated" in cleaned


def test_bounded_command_output_limits_and_strips_ansi():
    raw = "\x1b[31m" + "y" * 300_000
    bounded = bounded_command_output(raw)
    assert "\x1b[" not in bounded
    assert len(bounded.encode("utf-8")) <= 200_500
    assert "truncated" in bounded


def test_build_diagnostic_pack_is_checksum_bound():
    fault = PlatformFault(fault_code="TEST", message="test", occurred_at=NOW)
    pack = build_diagnostic_pack(fault=fault, correlation_id="corr-1", created_at=NOW)
    assert pack.checksum.startswith("sha256:")
    assert pack.pack_id
    assert pack.correlation_id == "corr-1"
    # immutable
    with pytest.raises(ValueError):
        pack.pack_id = "other"


def test_build_diagnostic_pack_sanitizes_traceback():
    fault = PlatformFault(fault_code="TEST", message="test", occurred_at=NOW)
    pack = build_diagnostic_pack(
        fault=fault,
        sanitized_traceback="AZURE_OPENAI_API_KEY = 4f3a9c1d7e2b8a6f0c5d4e3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a2918",
        created_at=NOW,
    )
    assert "4f3a9c1d7e2b8a6f0c5d4e3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a2918" not in pack.sanitized_traceback
