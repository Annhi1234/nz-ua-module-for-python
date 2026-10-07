"""Адаптери сховищ для Flet: токени в Android Keystore, кеш у каталозі застосунку."""
from __future__ import annotations

import json
import os
from pathlib import Path

from flet_secure_storage import SecureStorage

from nzua import Tokens

_KEY = "nzua_tokens"


class SecureTokenStore:
    """Токени (не пароль!) зберігаються у зашифрованому сховищі системи."""

    def __init__(self, storage: SecureStorage) -> None:
        self._s = storage

    async def load(self) -> Tokens | None:
        try:
            raw = await self._s.get(_KEY)
            return Tokens.from_dict(json.loads(raw)) if raw else None
        except Exception:
            return None

    async def save(self, tokens: Tokens) -> None:
        await self._s.set(_KEY, json.dumps(tokens.to_dict()))

    async def clear(self) -> None:
        try:
            await self._s.remove(_KEY)
        except Exception:
            pass


def data_dir() -> Path:
    base = os.getenv("FLET_APP_STORAGE_DATA") or str(Path.home() / ".nzua")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p
