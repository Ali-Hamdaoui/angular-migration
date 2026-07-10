"""FastAPI application entry point."""
from fastapi import FastAPI
from app.api.router import api_router
from app.core.application import APP_DESCRIPTION, APP_NAME, APP_VERSION

app = FastAPI(title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION)
app.include_router(api_router)
