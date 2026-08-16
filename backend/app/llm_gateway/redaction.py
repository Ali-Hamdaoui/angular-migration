"""Secret redaction helpers for LLM-bound context and logs.

Thin facade over the shared dependency-free redaction so LLM consumers keep
their ``PromptRedactionResult``-typed API while CLI/diagnostics/services can
redact without importing this subsystem.
"""

from app.llm_gateway.contracts import PromptRedactionResult
from app.services.text_redaction import redact_text


def redact_prompt_text(text: str) -> PromptRedactionResult:
    """Return text safe for mock LLM logging and future provider submission."""
    redacted = redact_text(text)
    return PromptRedactionResult(
        redacted_text=redacted.redacted_text,
        redaction_count=redacted.redaction_count,
        redaction_types=redacted.redaction_types,
    )
