"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError

from app.api.errors import error_response
from app.api.router import api_router
from app.core.application import APP_DESCRIPTION, APP_NAME, APP_VERSION
from app.core.config import get_settings
from app.repositories.session import check_database_connection


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Confirm configured database connectivity before serving API requests."""
    check_database_connection()
    from app.api.routes.baseline import get_baseline_install_service
    try:
        get_baseline_install_service().reconcile_orphans()
    except OperationalError:
        # Older test/development databases may predate the command columns.
        pass
    yield


settings = get_settings()
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return error_response(
        request,
        status_code=exc.status_code,
        error_code="http_error",
        message=str(exc.detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response(
        request,
        status_code=422,
        error_code="validation_error",
        message="Request validation failed.",
        details={"errors": exc.errors()},
    )


@app.exception_handler(ValidationError)
async def domain_validation_exception_handler(request: Request, exc: ValidationError):
    return error_response(request, status_code=422, error_code="DOMAIN_VALIDATION_FAILED", message="Domain validation failed.", details={"errors": exc.errors()})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return error_response(request, status_code=409, error_code="RESOURCE_CONFLICT", message="The requested resource conflicts with existing durable state.")


app.include_router(api_router)
