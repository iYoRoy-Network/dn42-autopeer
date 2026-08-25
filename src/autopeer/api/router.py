from __future__ import annotations

from fastapi import APIRouter

from autopeer.api.routes import admin, auth, health, jobs, metrics, peers

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(auth.router, prefix="/api/v1", tags=["auth"])
router.include_router(peers.router, prefix="/api/v1", tags=["peers"])
router.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
router.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
router.include_router(admin.router, prefix="/api/v1", tags=["admin"])
