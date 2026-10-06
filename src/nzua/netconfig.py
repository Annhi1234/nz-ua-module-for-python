"""Збережені мережеві налаштування (`nzua diagnose --save`), щоб підбирати їх один раз."""
from __future__ import annotations

import json
import os
from pathlib import Path

__all__ = ("load_network_options", "save_network_options")

_KEYS = ("user_agent", "http2", "proxy", "impersonate")


def _file(home: str | os.PathLike | None) -> Path:
    base = Path(home) if home else Path(os.getenv("NZUA_HOME") or Path.home() / ".nzua")
    return base / "network.json"


def load_network_options(home: str | os.PathLike | None = None) -> dict:
    """Параметри для клієнта: `NZClient(**load_network_options())`. Порожній словник, якщо не збережено."""
    try:
        raw = json.loads(_file(home).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: raw[k] for k in _KEYS if raw.get(k)}


def save_network_options(options: dict, home: str | os.PathLike | None = None) -> Path:
    p = _file(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({k: options[k] for k in _KEYS if options.get(k)}, ensure_ascii=False), "utf-8")
    return p
