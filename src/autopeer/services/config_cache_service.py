from __future__ import annotations

import asyncio
from contextlib import suppress

from autopeer.adapters.repository import ConfigRepository


class ConfigCacheService:
    """Periodically refresh the repository's in-memory configuration snapshot."""

    def __init__(self, repository: ConfigRepository, *, refresh_seconds: float = 30.0):
        self.repository = repository
        self.refresh_seconds = refresh_seconds
        self._task: asyncio.Task[None] | None = None
        self._refresh_lock = asyncio.Lock()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._refresh_loop(), name="autopeer-config-cache")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def refresh_once(self) -> None:
        if self._refresh_lock.locked():
            return
        async with self._refresh_lock:
            await asyncio.to_thread(self.repository.refresh_snapshot)

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self.refresh_seconds)
            await self.refresh_once()
