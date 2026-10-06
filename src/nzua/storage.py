"""Сховища токенів і кеш відповідей (підміняються власними реалізаціями)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from .models import Tokens

__all__ = ("TokenStore", "MemoryTokenStore", "FileTokenStore",
           "ResponseCache", "MemoryCache", "FileCache")


class TokenStore(Protocol):
    async def load(self) -> Tokens | None: ...
    async def save(self, tokens: Tokens) -> None: ...
    async def clear(self) -> None: ...


class MemoryTokenStore:
    def __init__(self) -> None:
        self._t: Tokens | None = None

    async def load(self) -> Tokens | None:
        return self._t

    async def save(self, tokens: Tokens) -> None:
        self._t = tokens

    async def clear(self) -> None:
        self._t = None


class FileTokenStore:
    """JSON-файл із правами 600. Для Android краще SecureStorage (див. app/)."""

    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)

    async def load(self) -> Tokens | None:
        try:
            return Tokens.from_dict(json.loads(self.path.read_text("utf-8")))
        except (OSError, ValueError, KeyError):
            return None

    async def save(self, tokens: Tokens) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(tokens.to_dict()), "utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    async def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class ResponseCache(Protocol):
    async def get(self, key: str) -> dict | None: ...
    async def set(self, key: str, value: dict) -> None: ...
    async def clear(self) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._d: dict[str, dict] = {}

    async def get(self, key: str) -> dict | None:
        return self._d.get(key)

    async def set(self, key: str, value: dict) -> None:
        self._d[key] = value

    async def clear(self) -> None:
        self._d.clear()


class FileCache(MemoryCache):
    """Кеш у JSON-файлі: дає змогу показувати дані без інтернету."""

    def __init__(self, path: str | os.PathLike) -> None:
        super().__init__()
        self.path = Path(path)
        try:
            self._d = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self._d = {}

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._d, ensure_ascii=False), "utf-8")

    async def set(self, key: str, value: Any) -> None:
        self._d[key] = value
        self._flush()

    async def clear(self) -> None:
        self._d.clear()
        self.path.unlink(missing_ok=True)
