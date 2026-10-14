"""Ponto de entrada da aplicação FastAPI."""

from fastapi import FastAPI

from app.api.routes import health


def create_app() -> FastAPI:
    app = FastAPI(title="BoardHub API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.include_router(health.router, prefix="/api/v1")
    return app


app = create_app()
