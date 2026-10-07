"""Транспорт із TLS-відбитком браузера (потрібен `pip install curl_cffi`).

Це типовий режим бібліотеки: Cloudflare блокує звичайні Python-клієнти (httpx/requests),
а відбиток Chrome проходить. На Android пакет `curl_cffi` є серед бінарних пакетів Flet.
"""
from __future__ import annotations

import httpx

_DROP = {"user-agent", "accept-encoding", "connection", "host", "content-length"}
_SKIP_RESPONSE = ("content-encoding", "content-length", "transfer-encoding")


class CurlTransport(httpx.AsyncBaseTransport):
    def __init__(self, impersonate: str = "chrome", *, timeout: float = 15.0, proxy: str | None = None) -> None:
        try:
            import curl_cffi.requests  # noqa: F401  (перевірка наявності одразу, а не при першому запиті)
        except ImportError as e:
            raise ImportError("Для TLS-відбитка встановіть: pip install curl_cffi") from e
        self._impersonate, self._timeout, self._proxy = impersonate, timeout, proxy
        self._session = None  # створюється ліниво в тому event loop, де йдуть запити

    def _get_session(self):
        if self._session is None:
            from curl_cffi.requests import AsyncSession
            kw = {"proxies": {"http": self._proxy, "https": self._proxy}} if self._proxy else {}
            self._session = AsyncSession(impersonate=self._impersonate, timeout=self._timeout, **kw)
        return self._session

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        from curl_cffi.requests import exceptions as cx

        headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP}
        body = await request.aread()
        try:
            r = await self._get_session().request(
                request.method, str(request.url), headers=headers,
                data=body or None, allow_redirects=False)
        except cx.Timeout as e:
            raise httpx.ReadTimeout(str(e), request=request) from e
        except cx.RequestException as e:
            raise httpx.ConnectError(str(e), request=request) from e
        out = [(k, v) for k, v in r.headers.items() if k.lower() not in _SKIP_RESPONSE]
        return httpx.Response(r.status_code, headers=out, content=r.content, request=request)

    async def aclose(self) -> None:
        if self._session is not None:
            session, self._session = self._session, None
            await session.close()
