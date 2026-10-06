"""Адаптери сховищ для Flet: токени в Android Keystore, кеш у каталозі застосунку."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
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


PALETTES = {"scale": "За оцінкою", "ink": "Синя", "ocean": "Океан", "forest": "Ліс",
            "sunset": "Захід", "mono": "Графіт"}


@dataclass
class Settings:
    """Вигляд графіка; зберігається у settings.json поруч із кешем."""
    palette: str = "scale"
    chart_height: int = 260
    show_values: bool = True

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads((data_dir() / "settings.json").read_text("utf-8"))
            s = cls(**{k: raw[k] for k in ("palette", "chart_height", "show_values") if k in raw})
        except (OSError, ValueError, TypeError):
            return cls()
        if s.palette not in PALETTES:
            s.palette = "scale"
        s.chart_height = min(max(int(s.chart_height), 160), 420)
        return s

    def save(self) -> None:
        try:
            (data_dir() / "settings.json").write_text(json.dumps(asdict(self)), "utf-8")
        except OSError:
            pass
