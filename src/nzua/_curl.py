"""Необов'язковий транспорт із TLS-відбитком браузера (потрібен `pip install curl_cffi`).

Допомагає, коли Cloudflare блокує звичайні Python-клієнти. На Android не підтримується.
"""
from __future__ import annotations

import httpx

_DROP = {"user-agent", "accept-encoding", "connection", "host", "content-length"}


class CurlTransport(httpx.AsyncBaseTransport):
    def __init__(self, impersonate: str = "chrome", *, timeout: float = 15.0, proxy: str | None = None) -> None:
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError as e:  # pragma: no cover
            raise ImportError("Для impersonate встановіть: pip install curl_cffi") from e
        kw = {"proxies": {"http": proxy, "https": proxy}} if proxy else {}
        self._session = AsyncSession(impersonate=impersonate, timeout=timeout, **kw)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        from curl_cffi.requests import exceptions as cx

        headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP}
        try:
            r = await self._session.request(
                request.method, str(request.url), headers=headers,
                data=await request.aread() or None, allow_redirects=False)
        except cx.Timeout as e:
            raise httpx.ReadTimeout(str(e), request=request) from e
        except cx.RequestException as e:
            raise httpx.ConnectError(str(e), request=request) from e
        out = [(k, v) for k, v in r.headers.items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
        return httpx.Response(r.status_code, headers=out, content=r.content, request=request)

    async def aclose(self) -> None:
        await self._session.close()
