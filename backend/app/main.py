"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import error_response
from app.api.router import api_router
from app.core.application import APP_DESCRIPTION, APP_NAME, APP_VERSION
from app.core.config import get_settings
from app.repositories.session import check_database_connection


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Confirm configured database connectivity before serving API requests."""
    check_database_connection()
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


app.include_router(api_router)
