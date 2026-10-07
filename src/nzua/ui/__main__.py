"""`python -m nzua.ui [--backend tk|qt|flet] [--demo] [--dark]` — запуск готового застосунку."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nzua.ui", description="Графічний щоденник nz.ua")
    ap.add_argument("--backend", default="auto", choices=("auto", "tk", "qt", "flet"))
    ap.add_argument("--demo", action="store_true", help="вигадані дані, без входу в акаунт")
    ap.add_argument("--dark", action="store_true", help="темна тема")
    ap.add_argument("--home", type=Path, default=None, help="каталог сесії та кешу (типово ~/.nzua)")
    a = ap.parse_args(argv)

    from .diary import DiaryApp, Settings

    home = a.home or Path(os.getenv("NZUA_HOME") or Path.home() / ".nzua")
    settings = Settings.load(home / "ui.json")
    if a.dark:
        settings.dark = True
    if a.demo:
        from .demo import DemoClient
        client = DemoClient()
        settings.path = ""  # демо не чіпає налаштування
    else:
        from ..cli import make_client
        client = make_client(home, False)
    DiaryApp(client, backend=a.backend, settings=settings).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
