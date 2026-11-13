"""One dedicated SQLite worker; no database work blocks Discord's event loop."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from .database import Database


class AsyncDatabase:
    def __init__(self, path, *, busy_timeout_ms=5000):
        self.path, self.busy_timeout_ms = path, busy_timeout_ms
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mi-boti-db")
        self._database = None

    def _call(self, function):
        if self._database is None:
            self._database = Database(self.path, busy_timeout_ms=self.busy_timeout_ms)
        return function(self._database)

    async def call(self, function):
        return await asyncio.get_running_loop().run_in_executor(self.executor, self._call, function)

    async def close(self):
        if self._database is not None:
            await self.call(lambda db: db.close())
            self._database = None
        self.executor.shutdown(wait=True)
