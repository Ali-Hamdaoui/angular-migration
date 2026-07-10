"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.application import APP_DESCRIPTION, APP_NAME, APP_VERSION
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)