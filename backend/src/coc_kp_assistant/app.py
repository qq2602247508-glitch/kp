from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .api.routes import router
from .config import Settings, get_settings
from .infrastructure.database import create_database_engine, create_session_factory


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    ruleset: str


class ReadinessResponse(BaseModel):
    ready: bool
    database: str
    ruleset: str


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    engine = create_database_engine(active_settings.database_url)
    session_factory = create_session_factory(engine)

    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = active_settings
    app.state.rules_service = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=active_settings.app_name,
            version=active_settings.app_version,
            ruleset="coc7e",
        )

    @app.get("/api/v1/readiness", response_model=ReadinessResponse)
    def readiness() -> ReadinessResponse:
        try:
            with session_factory() as session:
                session.execute(text("SELECT 1")).scalar_one()
        except SQLAlchemyError:
            return ReadinessResponse(ready=False, database="unavailable", ruleset="coc7e")
        return ReadinessResponse(ready=True, database="ready", ruleset="coc7e")

    app.include_router(router)
    return app


app = create_app()
