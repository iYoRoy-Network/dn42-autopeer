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
    """Application composition root.

    Keep long-lived dependencies wired here so route handlers stay thin: HTTP
    routes enqueue/read jobs, while the background worker performs serialized
    config-repo writes, validation, commits, and optional deployment.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    store = JobStore(settings.database_path)
    peer_service = PeerService(settings)
    job_service = JobService(store)
    metrics_service = MetricsService(
        MetricsConfig(settings.metrics_targets_file, peer_service.repo),
        MetricsClient(settings.metrics_timeout_seconds),
        refresh_seconds=settings.metrics_refresh_seconds,
        max_concurrency=settings.metrics_max_concurrency,
    )
    worker = Worker(store, peer_service)

    app.state.settings = settings
    app.state.peer_service = peer_service
    app.state.job_service = job_service
    app.state.metrics_service = metrics_service
    app.state.worker = worker
    await metrics_service.refresh_once()
    metrics_service.start()
    worker.start()
    try:
        yield
    finally:
        worker.stop()
        await metrics_service.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="iyoroynet-autopeer", version="0.1.0", lifespan=lifespan)
    # Kioubit login stores the verified ASN in a signed cookie-backed session.
    # Dev-header mode does not need this middleware, so it is enabled only when configured.
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
