"""Ядро інтерфейсу, не залежне від графічної бібліотеки: стан, асинхронні запити, діалоги.

    from nzua.ui import App, Screen, Text, Button

    def build(app):
        return Screen([Text(f"Кліків: {app.state.get('n', 0)}", cls="h2"),
                       Button("+1", lambda: app.update(n=app.state.get("n", 0) + 1))])

    App(build, backend="tk").run()        # або "qt", "flet", "headless"

`build(app)` викликається щоразу, коли треба перемалювати інтерфейс (`app.refresh()` / `app.update(...)`).
"""
from __future__ import annotations

import asyncio
import inspect
import threading
from typing import Any, Awaitable, Callable

from .style import NOTEBOOK, Theme
from .widgets import Dialog, Screen, Widget

__all__ = ("App", "Backend", "AsyncBridge", "get_backend")


class AsyncBridge:
    """Власний event loop у фоновому потоці: у ньому виконуються мережеві запити,
    а результат повертається в потік інтерфейсу через `call_soon`."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._ready = threading.Event()

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()

                def run() -> None:
                    asyncio.set_event_loop(loop)
                    loop.call_soon(self._ready.set)
                    loop.run_forever()

                threading.Thread(target=run, daemon=True, name="nzua-ui-loop").start()
                self._loop = loop
                self._ready.wait(5)
            return self._loop

    def submit(self, coro: Awaitable, done: Callable[[Any], None], fail: Callable[[BaseException], None]) -> None:
        loop = self._ensure()

        async def runner() -> None:
            try:
                res = await coro
            except BaseException as e:  # noqa: BLE001 — помилку передаємо в UI
                fail(e)
            else:
                done(res)

        asyncio.run_coroutine_threadsafe(runner(), loop)

    def close(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = None


class Backend:
    """Інтерфейс графічного бекенда. Реалізації: tk, qt, flet, headless."""
    name = "base"

    def __init__(self) -> None:
        self.app: "App | None" = None
        self._bridge = AsyncBridge()

    # — життєвий цикл —
    def run(self, app: "App") -> None:
        raise NotImplementedError

    def quit(self) -> None:
        raise NotImplementedError

    def call_soon(self, fn: Callable[[], None]) -> None:
        """Виконати `fn` у потоці інтерфейсу; безпечно викликати з будь-якого потоку."""
        raise NotImplementedError

    # — малювання —
    def mount(self, root: Widget) -> None:
        raise NotImplementedError

    def show_dialog(self, dialog: Dialog) -> None:
        raise NotImplementedError

    def close_dialog(self) -> None:
        raise NotImplementedError

    def toast(self, text: str) -> None:
        raise NotImplementedError

    # — асинхронність —
    def spawn(self, coro: Awaitable, done: Callable[[Any], None], fail: Callable[[BaseException], None]) -> None:
        """Запускає корутину поза потоком UI; `done`/`fail` викликаються вже в потоці UI."""
        self._bridge.submit(coro, lambda r: self.call_soon(lambda: done(r)),
                            lambda e: self.call_soon(lambda: fail(e)))


def get_backend(name: "str | Backend") -> Backend:
    if isinstance(name, Backend):
        return name
    name = (name or "auto").lower()
    if name == "auto":
        for cand in ("flet", "qt", "tk"):
            try:
                return get_backend(cand)
            except ImportError:
                continue
        raise ImportError("Не знайдено жодної графічної бібліотеки: встановіть PyQt5, Flet або Tkinter.")
    if name == "tk":
        from .backends.tk import TkBackend
        return TkBackend()
    if name in ("qt", "pyqt5"):
        from .backends.qt import QtBackend
        return QtBackend()
    if name == "flet":
        from .backends.flet import FletBackend
        return FletBackend()
    if name == "headless":
        from .backends.headless import HeadlessBackend
        return HeadlessBackend()
    raise ValueError(f"Невідомий бекенд {name!r}: tk | qt | flet | headless")


class App:
    """Застосунок: тримає стан, тему й зв'язок із бекендом."""

    def __init__(self, build: Callable[["App"], Widget], *, backend: "str | Backend" = "auto",
                 theme: Theme = NOTEBOOK, title: str = "Щоденник", size: tuple[int, int] = (420, 780),
                 state: dict | None = None, on_error: Callable[[BaseException], None] | None = None) -> None:
        self.build, self.theme, self.title, self.size = build, theme, title, size
        self.state: dict[str, Any] = dict(state or {})
        self.values: dict[str, Any] = {}      # значення Input/Switch/Dropdown/Slider за `name`
        self.backend = get_backend(backend)
        self.backend.app = self
        self.on_error = on_error
        self.on_unauthorized: Callable[[], None] | None = None
        self._dirty = False
        self._busy = 0
        self.root: Widget | None = None
        self.dialog: Dialog | None = None
        self.on_start: Callable[["App"], None] | None = None  # викликається, коли вікно готове

    # — запуск —
    def run(self) -> None:
        """Показує вікно й блокується до закриття (для Flet — до завершення сесії)."""
        self.backend.run(self)

    def quit(self) -> None:
        self.backend.quit()

    def _ready(self) -> None:
        """Бекенд викликає це, коли вікно створено: стартовий хук і перше малювання."""
        if self.on_start:
            try:
                self.on_start(self)
            except Exception as e:  # noqa: BLE001
                self.handle_error(e)
        self.refresh()

    # — стан —
    def update(self, **changes: Any) -> None:
        """Змінює `app.state` і перемальовує інтерфейс."""
        self.state.update(changes)
        self.refresh()

    def value(self, name: str, default: Any = "") -> Any:
        return self.values.get(name, default)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.refresh()

    # — малювання —
    def refresh(self) -> None:
        """Перебудовує інтерфейс (можна викликати з будь-якого потоку; злиті виклики об'єднуються)."""
        if self._dirty:
            return
        self._dirty = True
        self.backend.call_soon(self._do_refresh)

    def _do_refresh(self) -> None:
        self._dirty = False
        try:
            root = self.build(self)
        except Exception as e:  # помилка в build не має валити вікно
            self.handle_error(e)
            return
        self.root = root if isinstance(root, Screen) else Screen(root)
        self.backend.mount(self.root)

    def find(self, id: str) -> Widget | None:
        return self.root.find(id) if self.root else None

    def toast(self, text: str) -> None:
        self.backend.call_soon(lambda: self.backend.toast(text))

    def show_dialog(self, dialog: Dialog) -> None:
        self.dialog = dialog
        self.backend.call_soon(lambda: self.backend.show_dialog(dialog))

    def close_dialog(self) -> None:
        self.dialog = None
        self.backend.call_soon(self.backend.close_dialog)

    # — асинхронні задачі —
    @property
    def busy(self) -> bool:
        return self._busy > 0

    def task(self, work: "Awaitable | Callable[[], Awaitable]", on_done: Callable[[Any], None] | None = None,
             on_error: Callable[[BaseException], None] | None = None, *, refresh: bool = True) -> None:
        """Виконує корутину (або функцію, що її повертає) без блокування інтерфейсу.

            app.task(client.get_schedule(), on_done=lambda s: app.update(schedule=s))

        `on_done(result)` викликається в потоці інтерфейсу. Помилки йдуть в `on_error`, інакше —
        в `app.handle_error` (повідомлення-тост; `Unauthorized` → `app.on_unauthorized`).
        """
        coro = work() if callable(work) and not inspect.isawaitable(work) else work
        self._busy += 1

        def done(res: Any) -> None:
            self._busy -= 1
            try:
                if on_done:
                    r = on_done(res)
                    if inspect.isawaitable(r):
                        self.task(r, refresh=refresh)
            except Exception as e:  # noqa: BLE001
                self.handle_error(e)
            if refresh:
                self.refresh()

        def fail(err: BaseException) -> None:
            self._busy -= 1
            (on_error or self.handle_error)(err)
            if refresh:
                self.refresh()

        self.backend.spawn(coro, done, fail)

    def handle_error(self, err: BaseException) -> None:
        """Типова обробка помилок: власний `on_error` → вихід на екран входу → тост."""
        from ..errors import Unauthorized
        if self.on_error:
            self.on_error(err)
        elif isinstance(err, Unauthorized) and self.on_unauthorized:
            self.on_unauthorized()
        else:
            self.backend.toast(str(err) or type(err).__name__)

    # — виклик обробників подій —
    def dispatch(self, fn: Callable[..., Any] | None, *args: Any) -> None:
        """Викликає обробник події; `async def` запускається як задача. Помилки обробників не падають у GUI."""
        if fn is None:
            return
        try:
            r = fn(*args)
            if inspect.isawaitable(r):
                self.task(r)
        except Exception as e:  # noqa: BLE001
            self.handle_error(e)
