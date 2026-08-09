"""Canonical API error handling."""

from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.contracts import ErrorEnvelope

CORRELATION_ID_HEADER = "x-correlation-id"


def get_correlation_id(request: Request) -> str:
    value = request.headers.get(CORRELATION_ID_HEADER)
    return value if value else str(uuid4())


def error_response(
    request: Request,
    *,
    status_code: int,
    error_code: str,
    message: str,
    details: dict[str, object] | None = None,
    correlation_id: str | None = None,
) -> JSONResponse:
    correlation_id = correlation_id or get_correlation_id(request)
    envelope = ErrorEnvelope(
        error_code=error_code,
        message=message,
        correlation_id=correlation_id,
        details=details or {},
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers={CORRELATION_ID_HEADER: correlation_id},
    )
