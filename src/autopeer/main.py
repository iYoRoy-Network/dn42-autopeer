from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from autopeer.adapters.metrics import MetricsClient, MetricsConfig
from autopeer.api.router import router
from autopeer.core.config import get_settings
from autopeer.core.logging import configure_logging
from autopeer.db.session import JobStore
from autopeer.services.job_service import JobService
from autopeer.services.metrics_service import MetricsService
from autopeer.services.peer_service import PeerService
from autopeer.services.worker import Worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    store = JobStore(settings.database_path)
    peer_service = PeerService(settings)
    job_service = JobService(store)
    metrics_service = MetricsService(
        MetricsConfig(settings.metrics_targets_file),
        MetricsClient(settings.metrics_timeout_seconds),
    )
    worker = Worker(store, peer_service)

    app.state.settings = settings
    app.state.peer_service = peer_service
    app.state.job_service = job_service
    app.state.metrics_service = metrics_service
    app.state.worker = worker
    worker.start()
    try:
        yield
    finally:
        worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="iyoroynet-autopeer", version="0.1.0", lifespan=lifespan)
    if settings.session_secret:
        app.add_middleware(
            SessionMiddleware,
            secret_key=settings.session_secret,
            same_site="lax",
            https_only=settings.app_env == "prod",
        )
    app.include_router(router)
    return app


app = create_app()
