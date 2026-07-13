"""Secret redaction helpers for LLM-bound context and logs."""

import re

from app.llm_gateway.contracts import PromptRedactionResult

_REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("authorization_header", re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[A-Za-z0-9._~+/=-]{12,}")),
    ("api_key", re.compile(r"(?i)((api[_-]?key|x-api-key|subscription-key)\s*[:=]\s*)[A-Za-z0-9._~+/=-]{12,}")),
    ("env_secret", re.compile(r"(?im)^([A-Z0-9_]*(SECRET|TOKEN|PASSWORD|PRIVATE[_-]?KEY|REGISTRY)[A-Z0-9_]*\s*=\s*).+$")),
    ("npm_token", re.compile(r"(?i)(_authToken\s*=\s*)[A-Za-z0-9._~+/=-]{12,}")),
    ("connection_string", re.compile(r"(?i)((AccountKey|SharedAccessKey|Password)=)[^;\s]+")),
    ("production_url", re.compile(r"https://(?:prod|production|api)\.[A-Za-z0-9.-]+")),
)


def redact_prompt_text(text: str) -> PromptRedactionResult:
    """Return text safe for mock LLM logging and future provider submission."""
    redacted = text
    redaction_types: list[str] = []
    total = 0
    for redaction_type, pattern in _REDACTION_PATTERNS:
        redacted, count = pattern.subn(lambda match: _replacement(match), redacted)
        if count:
            redaction_types.append(redaction_type)
            total += count
    return PromptRedactionResult(
        redacted_text=redacted,
        redaction_count=total,
        redaction_types=redaction_types,
    )


def _replacement(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 1:
        return f"{match.group(1)}[REDACTED]"
    return "[REDACTED]"