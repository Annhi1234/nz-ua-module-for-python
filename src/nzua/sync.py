"""Синхронна обгортка над AsyncNZClient (власний event loop у потоці)."""
from __future__ import annotations

import asyncio
import functools
import inspect
import threading
from typing import Any

from .client import AsyncNZClient

__all__ = ("NZClient",)


class NZClient:
    """
    with NZClient() as nz:
        nz.login("user", "password")
        print(nz.get_schedule().average())

    Усі методи AsyncNZClient доступні без `await`.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="nzua-loop")
        self._thread.start()
        self._async = AsyncNZClient(*args, **kwargs)

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        attr = getattr(self._async, name)
        if inspect.iscoroutinefunction(attr):
            @functools.wraps(attr)
            def wrapper(*a: Any, **kw: Any):
                return self._run(attr(*a, **kw))
            return wrapper
        return attr

    def close(self) -> None:
        if self._loop.is_running():
            self._run(self._async.aclose())
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)

    def __enter__(self) -> "NZClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
