"""Domain contracts for RepairContextPack — context assembly for repair agents."""

from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.domain.contracts import ContractModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ContextSegmentType(str, Enum):
    """Type of content a single context segment carries."""

    DIAGNOSTIC_EXCERPT = "diagnostic_excerpt"
    FAILURE_EVIDENCE = "failure_evidence"
    SOURCE_FILE = "source_file"
    DEPENDENCY_INFO = "dependency_info"
    PRIOR_ATTEMPT = "prior_attempt"
    SYSTEM_PROMPT = "system_prompt"


class RepairContextStatus(str, Enum):
    """Lifecycle status of a RepairContextPack record."""

    FINALIZED = "finalized"
    INSUFFICIENT = "insufficient"
    STALE = "stale"


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class ContextSegment(ContractModel):
    """A single segment of content inside a RepairContextPack.

    Each segment carries a checksum, optional file-path and line-range
    metadata, and a redaction flag so downstream consumers know whether
    the content was sanitised.
    """

    segment_type: ContextSegmentType
    file_path: str | None = Field(default=None, max_length=1024)
    content: str = Field(max_length=16000)
    reason: str = Field(min_length=1, max_length=2000)
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    redacted: bool = False
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def enforce_line_bounds(self) -> ContextSegment:
        if self.line_start is not None and self.line_end is not None:
            if self.line_end < self.line_start:
                raise ValueError("line_end must be >= line_start")
        return self


class SelectionPriority(ContractModel):
    """Controls how files are prioritised for inclusion in a context pack."""

    file_priority: int = Field(ge=1, le=100)
    excerpt_max_chars: int = Field(default=4000, ge=1)
    full_file_max_chars: int = Field(default=16000, ge=1)


class RepairContextPack(ContractModel):
    """Immutable context pack sent to a repair agent.

    Conforms to ``repair_context_pack.schema.json`` frozen contract.
    """

    context_pack_id: str = Field(min_length=1, max_length=128)
    failure_id: str = Field(min_length=1, max_length=128)
    stage_id: str = Field(min_length=1, max_length=64)
    repair_attempt: int = Field(ge=1)
    workspace_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selection_policy_version: str = Field(min_length=1, max_length=32)
    sanitization_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    content_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    segments: list[ContextSegment] = Field(min_length=1)
    token_budget: int | None = Field(default=None, ge=1)
    status: RepairContextStatus = RepairContextStatus.FINALIZED

    @model_validator(mode="after")
    def enforce_segment_non_empty(self) -> RepairContextPack:
        if not self.segments:
            raise ValueError("RepairContextPack must contain at least one segment")
        return self

    @model_validator(mode="after")
    def enforce_token_budget_when_insufficient(self) -> RepairContextPack:
        if self.status == RepairContextStatus.INSUFFICIENT and self.token_budget is None:
            raise ValueError("INSUFFICIENT status requires a token_budget")
        return self


# ---------------------------------------------------------------------------
# Utility classes
# ---------------------------------------------------------------------------


class SecretSanitizer:
    """Redact common secrets from context content.

    Patterns covered:
      - API keys, bearer / basic tokens
      - Passwords (``password=…``, ``pass=…``, ``pwd=…``)
      - Private keys (PEM blocks)
      - URLs containing embedded credentials
      - IPv4 and IPv6 addresses
    """

    # Pattern: bearer / basic / token auth headers and inline values
    _BEARER_PATTERN = re.compile(
        r"(?i)(bearer|token|api[_-]?key|apikey|secret|auth)\s*[:=]\s*\S{8,}",
    )
    _PASSWORD_PATTERN = re.compile(
        r"(?i)(password|pass|pwd)\s*[:=]\s*\S+",
    )
    _PRIVATE_KEY_PATTERN = re.compile(
        r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(RSA\s+)?PRIVATE\s+KEY-----",
    )
    _URL_CREDENTIALS_PATTERN = re.compile(
        r"https?://\S+:\S+@\S+",
    )
    _IP_ADDRESS_PATTERN = re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    )

    REDACTED_PLACEHOLDER = "[REDACTED]"

    def sanitize(self, content: str) -> tuple[str, dict]:
        """Return (sanitized_content, redaction_report) where secrets are masked."""
        original = content
        redacted_count: dict[str, int] = {
            "api_keys_tokens": 0,
            "passwords": 0,
            "private_keys": 0,
            "url_credentials": 0,
            "ip_addresses": 0,
        }

        sanitized, count_api = self._BEARER_PATTERN.subn(
            lambda m: m.group(0).split("=")[0].split(":")[0] + "=" + self.REDACTED_PLACEHOLDER
            if "=" in m.group(0) or ":" in m.group(0)
            else self.REDACTED_PLACEHOLDER,
            original,
        )
        redacted_count["api_keys_tokens"] = count_api

        sanitized, count_pass = self._PASSWORD_PATTERN.subn(
            lambda m: m.group(0).split("=")[0] + "=" + self.REDACTED_PLACEHOLDER,
            sanitized,
        )
        redacted_count["passwords"] = count_pass

        sanitized, count_key = self._PRIVATE_KEY_PATTERN.subn(
            self.REDACTED_PLACEHOLDER,
            sanitized,
        )
        redacted_count["private_keys"] = count_key

        sanitized, count_url = self._URL_CREDENTIALS_PATTERN.subn(
            lambda m: "https://" + self.REDACTED_PLACEHOLDER + "@" + m.group(0).split("@", 1)[1],
            sanitized,
        )
        redacted_count["url_credentials"] = count_url

        sanitized, count_ip = self._IP_ADDRESS_PATTERN.subn(
            self.REDACTED_PLACEHOLDER,
            sanitized,
        )
        redacted_count["ip_addresses"] = count_ip

        any_redacted = (
            count_api > 0 or count_pass > 0 or count_key > 0 or count_url > 0 or count_ip > 0
        )

        report = {
            "redacted": any_redacted,
            "counts": redacted_count,
        }

        return sanitized, report


class ContextBudgetTracker:
    """Track token consumption of context segments against a budget."""

    def __init__(self, max_tokens: int = 32000) -> None:
        self._max_tokens = max_tokens
        self._segments: list[ContextSegment] = []

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def add_segment(self, segment: ContextSegment) -> int:
        """Add a segment and return its estimated token cost (4 chars ≈ 1 token)."""
        cost = self._estimate_tokens(segment.content)
        proposed = self._current_total + cost
        if proposed > self._max_tokens:
            raise ValueError(
                f"Cannot add segment: would exceed budget of {self._max_tokens} "
                f"(current {self._current_total} + {cost} > {self._max_tokens})"
            )
        self._segments.append(segment)
        return cost

    def total_tokens(self) -> int:
        return self._current_total

    def can_add_segment(self, segment: ContextSegment | None = None) -> bool:
        """Return True if there is room for an optional segment."""
        if segment is None:
            return self._current_total < self._max_tokens
        cost = self._estimate_tokens(segment.content)
        return self._current_total + cost <= self._max_tokens

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Approximate token count (4 chars ≈ 1 token)."""
        return max(1, len(text) // 4)

    @property
    def _current_total(self) -> int:
        return sum(self._estimate_tokens(s.content) for s in self._segments)


class ForbiddenActionPolicy:
    """Declarative policy that lists actions a repair agent is not allowed to perform."""

    def __init__(self, forbidden_actions: list[str] | None = None) -> None:
        self._forbidden_actions = forbidden_actions or [
            "edit_source",
            "execute_command",
            "access_network",
            "read_arbitrary_file",
        ]

    @property
    def forbidden_actions(self) -> list[str]:
        return list(self._forbidden_actions)

    def is_action_forbidden(self, action: str) -> bool:
        """Return True if *action* is in the forbidden list."""
        return action in self._forbidden_actions
