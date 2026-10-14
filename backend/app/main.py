"""Ponto de entrada da aplicação FastAPI."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import install_middleware
from app.api.routes import (
    academy,
    auth,
    engagement,
    health,
    matches,
    me,
    privacy,
    profile,
    ranking,
)
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.realtime import endpoint as realtime
from app.realtime import notify
from app.services import engagement as engagement_wiring


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="BoardHub API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    install_error_handlers(app)
    install_middleware(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],  # SEC-07: uma única origem, nunca "*"
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    engagement_wiring.register()
    notify.install()
    for router in (health.router, auth.router, me.router, profile.router, matches.router,
                   academy.router, privacy.router, ranking.router, engagement.router,
                   realtime.router):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
