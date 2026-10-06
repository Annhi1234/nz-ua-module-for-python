"""Асинхронний клієнт API api-mobile.nz.ua (v2)."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from . import models as m
from .errors import (
    APIError, BlockedError, ConnectionTimedOut, HometaskNotFound, IncorrectPassword,
    IncorrectUsername, InternalServerError, NetworkError, RateLimited,
    ServiceUnavailable, SessionExpired, Unauthorized, UnknownError,
)
from .storage import MemoryTokenStore, ResponseCache, TokenStore

__all__ = ("AsyncNZClient", "BASE_URL", "USER_AGENTS")

BASE_URL = "https://api-mobile.nz.ua"
_V = "/v2"
# Заголовки повторюють офіційні запити мобільного клієнта (як у старій бібліотеці).
_HEADERS = {"User-Agent": "IRC RESTClient", "Accept": "application/json",
            "Accept-Charset": "utf-8, *;q=0.8", "Accept-Encoding": "gzip"}
USER_AGENTS = {
    "legacy": "IRC RESTClient",
    "okhttp": "okhttp/4.12.0",
    "android-chrome": ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"),
}

_KNOWN_ERRORS: dict[str, type[APIError]] = {
    "користувач не знайдений": IncorrectUsername,
    "введено невірний логін або пароль": IncorrectPassword,
    "завдання не знайдене": HometaskNotFound,
}
_Date = str | date | datetime


def _is_blocked(resp: httpx.Response) -> bool:
    """Сторінка-перевірка Cloudflare/WAF замість відповіді API."""
    if resp.status_code not in (403, 429, 503):
        return False
    if resp.headers.get("cf-mitigated"):
        return True
    if "html" in resp.headers.get("content-type", "").lower():
        head = resp.text[:4000].lower()
        return any(x in head for x in ("just a moment", "cf-chl", "challenge-platform",
                                       "attention required", "cloudflare"))
    return False


def _check_id(value: int | str, name: str = "id") -> int | str:
    if isinstance(value, bool) or not isinstance(value, (int, str)) or str(value) in ("", "0"):
        raise ValueError(f"{name} має бути ненульовим числом або рядком")
    return value


def _period(start: _Date | None, end: _Date | None) -> dict[str, str]:
    """Дати за замовчуванням обчислюються під час виклику, а не імпорту."""
    today = date.today()
    s = start if start is not None else today.replace(day=1)
    e = end if end is not None else today
    s, e = (x.date() if isinstance(x, datetime) else x for x in (s, e))
    s, e = str(s), str(e)
    if s > e:
        raise ValueError("start_date пізніше за end_date")
    return {"start_date": s, "end_date": e}


class AsyncNZClient:
    """
    async with AsyncNZClient() as nz:
        await nz.login("user", "password")
        schedule = await nz.get_schedule()

    Токен оновлюється автоматично (за `expires_token` та після 401).
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        tokens: m.Tokens | None = None,
        token_store: TokenStore | None = None,
        cache: ResponseCache | None = None,
        base_url: str = BASE_URL,
        timeout: float = 15.0,
        retries: int = 2,
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        user_agent: str | None = None,
        http2: bool = False,
        proxy: str | None = None,
        impersonate: str | None = None,
    ) -> None:
        self._tokens = tokens or (m.Tokens(token) if token else None)
        self._store: TokenStore = token_store or MemoryTokenStore()
        self._cache = cache
        self._retries = max(0, retries)
        self._lock = asyncio.Lock()
        self.student: m.Student | None = None
        ua = USER_AGENTS.get(user_agent or "", user_agent)
        extra: dict[str, Any] = {}
        if impersonate and transport is None:
            from ._curl import CurlTransport  # потрібен `pip install curl_cffi`
            transport = CurlTransport(impersonate, timeout=timeout, proxy=proxy)
        elif proxy:
            extra["proxy"] = proxy
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, transport=transport, http2=http2 and transport is None,
            headers={**_HEADERS, **({"User-Agent": ua} if ua else {}), **(headers or {})},
            follow_redirects=True, **extra)

    # ── життєвий цикл ──
    async def __aenter__(self) -> "AsyncNZClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def tokens(self) -> m.Tokens | None:
        return self._tokens

    @property
    def is_authenticated(self) -> bool:
        return self._tokens is not None

    async def restore_session(self) -> bool:
        """Підхоплює збережені токени зі `token_store`."""
        if self._tokens is None:
            self._tokens = await self._store.load()
        return self._tokens is not None

    # ── транспорт ──
    async def _send(self, method: str, path: str, *, body: Any, params: Any,
                    auth: bool, retry: bool) -> httpx.Response:
        attempts = (self._retries if retry else 0) + 1
        headers = {"Authorization": f"Bearer {self._tokens.access_token}"} if auth and self._tokens else None
        for i in range(attempts):
            last = i == attempts - 1
            try:
                resp = await self._http.request(method, path, json=body, params=params, headers=headers)
            except httpx.TimeoutException as e:
                if last:
                    raise ConnectionTimedOut(str(e) or "timeout") from e
            except httpx.TransportError as e:
                if last:
                    raise NetworkError(str(e) or "network error") from e
            else:
                if resp.status_code not in (502, 503, 504, 522) or last or _is_blocked(resp):
                    return resp
            await asyncio.sleep(0.5 * 2 ** i)
        raise NetworkError("unreachable")  # pragma: no cover

    @staticmethod
    def _handle(resp: httpx.Response, expect: str) -> Any:
        code = resp.status_code
        if _is_blocked(resp):
            raise BlockedError(code)
        if code == 204:
            return None
        if code == 401:
            raise Unauthorized
        if code == 429:
            raise RateLimited("Забагато запитів. Спробуйте пізніше.")
        if code == 503:
            raise ServiceUnavailable
        if code == 522:
            raise ConnectionTimedOut("Сервер не відповів вчасно.")
        if code not in (200, 201, 500):
            raise UnknownError(f"HTTP {code}: {resp.text[:200]}")
        if code == 200 and expect == "bytes":
            return resp.content
        if code == 200 and expect == "text":
            return resp.text
        try:
            data = resp.json()
        except ValueError as e:
            raise UnknownError(f"HTTP {code}: невалідний JSON") from e
        if code == 500 and isinstance(data, dict) and data.get("name") == "Internal Server Error":
            raise InternalServerError(data.get("message", ""))
        if isinstance(data, dict) and (msg := data.get("error_message")):
            cls = _KNOWN_ERRORS.get(str(msg).strip().rstrip(".").lower(), APIError)
            raise cls(str(msg), data)
        return data

    async def _call(self, method: str, path: str, *, body: Any = None, params: Any = None,
                    auth: bool = True, retry: bool = True, expect: str = "json") -> Any:
        if auth:
            await self._ensure_fresh()
        resp = await self._send(method, _V + path, body=body, params=params, auth=auth, retry=retry)
        if resp.status_code == 401 and auth:
            await self._refresh(failed=self._tokens.access_token if self._tokens else None)
            resp = await self._send(method, _V + path, body=body, params=params, auth=auth, retry=retry)
            if resp.status_code == 401:
                raise SessionExpired
        return self._handle(resp, expect)

    async def _ensure_fresh(self) -> None:
        if self._tokens is None:
            await self.restore_session()
        if self._tokens is None:
            raise Unauthorized
        if self._tokens.is_expired() and self._tokens.refresh_token:
            await self._refresh(failed=self._tokens.access_token)

    async def _refresh(self, failed: str | None) -> None:
        async with self._lock:
            cur = self._tokens
            if cur is None or not cur.refresh_token:
                raise SessionExpired
            if failed is not None and cur.access_token != failed:
                return  # інша корутина вже оновила токен
            try:
                data = await self._call("POST", "/user/refresh-token", auth=False,
                                        body={"refresh_token": cur.refresh_token})
            except (Unauthorized, APIError) as e:
                await self._drop_session()
                raise SessionExpired from e
            if not isinstance(data, dict) or not data.get("access_token"):
                await self._drop_session()
                raise SessionExpired
            await self._set_tokens(m.Tokens(
                data["access_token"], data.get("refresh_token") or cur.refresh_token,
                self._int(data.get("expires_token")) or cur.expires_at))

    @staticmethod
    def _int(v: Any) -> int | None:
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    async def _set_tokens(self, tokens: m.Tokens) -> None:
        self._tokens = tokens
        await self._store.save(tokens)

    async def _drop_session(self) -> None:
        self._tokens = None
        self.student = None
        await self._store.clear()

    async def _cached(self, path: str, body: dict, parser: Callable[[dict], Any]) -> Any:
        key = f"{path}|{json.dumps(body, sort_keys=True)}"
        try:
            data = await self._call("POST", path, body=body)
        except NetworkError:
            hit = await self._cache.get(key) if self._cache else None
            if hit is None:
                raise
            return replace(parser(hit), from_cache=True)
        if self._cache:
            await self._cache.set(key, data)
        return parser(data)

    # ── сервісні ──
    async def probe(self) -> str:
        """Один пробний запит без авторизації: 'ok', 'blocked', 'http 404' або 'network: …'."""
        try:
            resp = await self._send("GET", _V + "/user/test", body=None, params=None, auth=False, retry=False)
        except NetworkError as e:
            return f"network: {e}"
        if _is_blocked(resp):
            return "blocked"
        return "ok" if resp.status_code == 200 else f"http {resp.status_code}"

    async def ping(self) -> bool:
        """Перевірка доступності API (без авторизації)."""
        try:
            await self._call("GET", "/user/test", auth=False, retry=False)
            return True
        except (NetworkError, UnknownError, InternalServerError):  # BlockedError ⊂ NetworkError
            return False

    # ── авторизація ──
    async def login(self, username: str, password: str, push_token: str = "") -> m.Student:
        data = await self._call("POST", "/user/login", auth=False, retry=False, body={
            "username": username, "password": password, "exponentPushToken": push_token})
        await self._set_tokens(m.Tokens(
            data["access_token"], data.get("refresh_token"), self._int(data.get("expires_token"))))
        self.student = m.Student.from_api(data)
        return self.student

    async def refresh_token(self) -> m.Tokens:
        """Примусове оновлення токена."""
        await self.restore_session()
        await self._refresh(failed=None)
        return self._tokens  # type: ignore[return-value]

    async def logout(self, push_token: str = "") -> None:
        try:
            if self._tokens:
                await self._call("POST", "/user/logout", body={"exponentPushToken": push_token}, retry=False)
        except (Unauthorized, NetworkError):
            pass  # локально все одно виходимо
        finally:
            await self._drop_session()
            if self._cache:
                await self._cache.clear()

    # ── щоденник, розклад, оцінки ──
    async def get_schedule(self, start_date: _Date | None = None, end_date: _Date | None = None) -> m.Schedule:
        return await self._cached("/schedule/diary", _period(start_date, end_date), m.Schedule.from_api)

    async def get_timetable(self, start_date: _Date | None = None, end_date: _Date | None = None) -> m.Timetable:
        return await self._cached("/schedule/timetable", _period(start_date, end_date), m.Timetable.from_api)

    async def get_student_performance(self, start_date: _Date | None = None,
                                      end_date: _Date | None = None) -> m.StudentPerformance:
        return await self._cached("/schedule/student-performance", _period(start_date, end_date),
                                  m.StudentPerformance.from_api)

    async def get_subject_performance(self, subject_id: int | str, start_date: _Date | None = None,
                                      end_date: _Date | None = None) -> m.SubjectPerformance:
        body = {**_period(start_date, end_date), "subject_id": str(_check_id(subject_id, "subject_id"))}
        return await self._cached("/schedule/subject-grades", body, m.SubjectPerformance.from_api)

    async def get_missed_lessons(self, start_date: _Date | None = None,
                                 end_date: _Date | None = None) -> m.MissedLessons:
        return await self._cached("/schedule/missed-lessons", _period(start_date, end_date),
                                  m.MissedLessons.from_api)

    # ── дистанційні завдання ──
    async def get_hometask(self, hometask_id: int | str) -> m.Hometask:
        body = {"distance_hometask_id": _check_id(hometask_id, "hometask_id")}
        return await self._cached("/schedule/distance-hometask", body, m.Hometask.from_api)

    async def answer_hometask(self, hometask_id: int | str, text: str,
                              delete_file_ids: tuple[int, ...] | list[int] = ()) -> m.HometaskAnswer:
        data = await self._call("POST", "/schedule/student-answer", retry=False, body={
            "hometask_id": _check_id(hometask_id, "hometask_id"),
            "hometask_text": text, "deleteFilesIdList": list(delete_file_ids)})
        return m.HometaskAnswer.from_api(data)

    async def download_hometask_file(self, uuid: str, save_to: str | Path | None = None) -> bytes:
        data: bytes = await self._call("GET", "/schedule/get-hometask-file",
                                       params={"uuid": uuid}, expect="bytes")
        if save_to is not None:
            Path(save_to).write_bytes(data)
        return data

    # ── сповіщення ──
    async def get_notifications(self) -> list[m.Notification]:
        data = await self._call("GET", "/notification/")
        return [m.Notification.from_api(x) for x in data.get("data", []) if isinstance(x, dict)]

    async def get_unread_count(self) -> int:
        data = await self._call("GET", "/notification/unread-qty")
        return self._int(data.get("qty")) or 0

    # ── вчителям та службові ──
    async def get_mark_values(self) -> list[m.MarkValue]:
        data = await self._call("POST", "/personnel-journal/mark-list", body={})
        return [m.MarkValue.from_api(x) for x in data.get("data", []) if isinstance(x, dict)]

    async def create_temporary_link(self, url: str) -> str:
        data = await self._call("POST", "/link/generate-temporary-link", body={"url": url}, retry=False)
        return data.get("response", "")

    async def get_temporary_link(self, link_hash: str) -> str:
        return await self._call("GET", "/link/get-temporary-link",
                                params={"hash": link_hash}, expect="text")
