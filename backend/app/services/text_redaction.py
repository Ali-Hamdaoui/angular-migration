"""Shared, dependency-free text redaction for logs and diagnostics.

Kept outside the LLM gateway so deterministic services (command worker,
diagnostics) can redact without importing the LLM subsystem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("authorization_header", re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[A-Za-z0-9._~+/=-]{12,}")),
    ("api_key", re.compile(r"(?i)((api[_-]?key|x-api-key|subscription-key)\s*[:=]\s*)[A-Za-z0-9._~+/=-]{12,}")),
    ("env_secret", re.compile(r"(?im)^([A-Z0-9_]*(SECRET|TOKEN|PASSWORD|PRIVATE[_-]?KEY|REGISTRY)[A-Z0-9_]*\s*=\s*).+$")),
    ("npm_token", re.compile(r"(?i)(_authToken\s*=\s*)[A-Za-z0-9._~+/=-]{12,}")),
    ("connection_string", re.compile(r"(?i)((AccountKey|SharedAccessKey|Password)=)[^;\s]+")),
    ("production_url", re.compile(r"https://(?:prod|production|api)\.[A-Za-z0-9.-]+")),
)


@dataclass(frozen=True)
class RedactResult:
    redacted_text: str
    redaction_count: int
    redaction_types: list[str] = field(default_factory=list)


def _replacement(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 1:
        return f"{match.group(1)}[REDACTED]"
    return "[REDACTED]"


def redact_text(text: str) -> RedactResult:
    """Return text safe for logs/LLM context by redacting known secret shapes."""
    redacted = text
    redaction_types: list[str] = []
    total = 0
    for redaction_type, pattern in _REDACTION_PATTERNS:
        redacted, count = pattern.subn(lambda match: _replacement(match), redacted)
        if count:
            redaction_types.append(redaction_type)
            total += count
    return RedactResult(
        redacted_text=redacted,
        redaction_count=total,
        redaction_types=redaction_types,
    )
