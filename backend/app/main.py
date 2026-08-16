"""FastAPI application entry point."""

import asyncio
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.errors import error_response
from app.api.router import api_router
from app.core.application import APP_DESCRIPTION, APP_NAME, APP_VERSION
from app.core.config import get_settings
from app.core.database import assert_schema_compatible
from app.repositories.session import check_database_connection, engine, resolved_database_path


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Confirm configured database connectivity before serving API requests."""
    check_database_connection()
    path = resolved_database_path()
    print(f"Backend database: {path or '<non-file database>'}", flush=True)
    assert_schema_compatible(engine, get_settings())
    settings = get_settings()
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=settings.platform_repository_root, capture_output=True, text=True, timeout=2, check=False).stdout.strip()
    except OSError:
        commit = "unavailable"
    endpoint = urlsplit(settings.azure_openai_endpoint or "")
    print({
        "startup_provenance": {
            "commit_sha": commit,
            "repository_root": str(settings.platform_repository_root),
            "database_path": str(path or "<non-file database>"),
            "artifact_root": str(settings.artifact_root),
            "llm_enabled": settings.llm_enabled,
            "endpoint_host": endpoint.hostname,
            "endpoint_path": endpoint.path,
            "deployment_alias": settings.azure_openai_deployment,
            "timeout_seconds": settings.llm_timeout_seconds,
            "retry_count": settings.llm_max_transport_retries,
        }
    }, flush=True)
    from app.api.routes.baseline import get_baseline_install_service
    get_baseline_install_service().reconcile_orphans()
    from app.services.command_executor_service import CommandExecutorService
    CommandExecutorService().recover_command_orphans()
    from app.orchestration.source_intake import default_source_intake_graph, recover_source_intake_jobs
    default_source_intake_graph(get_settings())
    recover_source_intake_jobs()
    from app.services.planning_job_service import recover_planning_jobs
    recover_planning_jobs()
    from app.orchestration.planning import dispatch_due_planning_jobs
    dispatch_due_planning_jobs()
    from app.orchestration.planning_worker import planning_worker_loop
    worker = asyncio.create_task(planning_worker_loop(poll_seconds=settings.planning_worker_poll_seconds))
    try:
        yield
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


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
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return error_response(
        request,
        status_code=exc.status_code,
        error_code=str(detail.get("error_code") or "HTTP_ERROR"),
        message=str(detail.get("message") or exc.detail),
        details=detail.get("details") if isinstance(detail.get("details"), dict) else {},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response(
        request,
        status_code=422,
        error_code="validation_error",
        message="Request validation failed.",
        details={"errors": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(ValidationError)
async def domain_validation_exception_handler(request: Request, exc: ValidationError):
    return error_response(request, status_code=422, error_code="DOMAIN_VALIDATION_FAILED", message="Domain validation failed.", details={"errors": jsonable_encoder(exc.errors())})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return error_response(request, status_code=409, error_code="RESOURCE_CONFLICT", message="The requested resource conflicts with existing durable state.")


app.include_router(api_router)
# FastAPI's lazy nested-router registration requires the run-scoped assistant
# surface to be attached at the application boundary as well as the versioned
# composition root.
