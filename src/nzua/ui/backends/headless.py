"""Бекенд без вікна: для автотестів інтерфейсу й запуску на сервері.

    app = App(build, backend="headless"); app.run()      # перше малювання
    app.backend.click("save"); app.backend.type("login", "ivan"); app.backend.settle()
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

from ..app import Backend
from ..widgets import Button, Card, Cell, Chip, Dialog, Dropdown, Input, NavBar, Slider, Switch, Table, Text, Widget


class HeadlessBackend(Backend):
    name = "headless"

    def __init__(self) -> None:
        super().__init__()
        self._q: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._ui_thread = threading.get_ident()
        self.root: Widget | None = None
        self.dialog: Dialog | None = None
        self.toasts: list[str] = []
        self.mounts = 0

    # — життєвий цикл —
    def run(self, app) -> None:
        self._ui_thread = threading.get_ident()
        app._ready()
        self.settle()

    def quit(self) -> None:
        self._bridge.close()

    def call_soon(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)

    def settle(self, timeout: float = 5.0) -> None:
        """Виконує відкладені дії UI, поки не завершаться всі задачі (`app.task`)."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                self._q.get(timeout=0.01)()
                continue
            except queue.Empty:
                pass
            if not (self.app and self.app.busy) and self._q.empty():
                return
        raise TimeoutError("інтерфейс не заспокоївся за відведений час")

    # — малювання —
    def mount(self, root: Widget) -> None:
        self.root, self.mounts = root, self.mounts + 1

    def show_dialog(self, dialog: Dialog) -> None:
        self.dialog = dialog

    def close_dialog(self) -> None:
        self.dialog = None

    def toast(self, text: str) -> None:
        self.toasts.append(text)

    # — імітація дій користувача —
    def _need(self, id: str) -> Widget:
        for root in (self.dialog, self.root):
            w = root.find(id) if root else None
            if w is not None:
                return w
        raise LookupError(f"віджет #{id} не знайдено")

    def click(self, id: str, arg: Any = None) -> None:
        """Клік по Button/Text/Card/Chip з `id`; для Table передайте arg=індекс рядка; для NavBar — ключ."""
        w = self._need(id)
        if isinstance(w, Table):
            self.app.dispatch(w.on_row_click, arg)
        elif isinstance(w, NavBar):
            self.app.dispatch(w.on_change, arg)
        else:
            self.app.dispatch(getattr(w, "on_click", None))
        self.settle()

    def type(self, name: str, value: Any, *, submit: bool = False) -> None:
        w = next((x for r in (self.dialog, self.root) if r for x in r.walk()
                  if getattr(x, "name", None) == name and isinstance(x, (Input, Switch, Dropdown, Slider))), None)
        if w is None:
            raise LookupError(f"поле {name!r} не знайдено")
        self.app.values[name] = value
        self.app.dispatch(w.on_change, value)
        if submit and isinstance(w, Input):
            self.app.dispatch(w.on_submit, value)
        self.settle()

    def texts(self) -> list[str]:
        """Усі тексти на екрані (зручно для assert)."""
        out = []
        for root in (self.root, self.dialog):
            for w in (root.walk() if root else ()):
                if isinstance(w, (Text, Chip, Button)):
                    out.append(w.text)
                elif isinstance(w, Table):
                    out += [str(w.cell(c).text) for r in w.rows for c in r if not w.cell(c).widget]
        return out
