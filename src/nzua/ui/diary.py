"""Готовий застосунок «Щоденник» на nzua.ui: один код для Tkinter, PyQt5 і Flet.

    from nzua import AsyncNZClient
    from nzua.ui.diary import DiaryApp
    DiaryApp(AsyncNZClient(token_store=...), backend="tk").run()

Власний інтерфейс простіше збирати з нуля з `nzua.ui.screens`; цей клас — приклад і готовий варіант.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..errors import Unauthorized
from . import screens as sc
from .app import App, Backend
from .style import DARK, NOTEBOOK, Style, Theme
from .widgets import (Button, Column, Dialog, Dropdown, Input, NavBar, Progress, Screen, Slider, Switch, Text)

__all__ = ("DiaryApp", "Settings", "school_year_start")

TABS = [("diary", "Щоденник", "book"), ("timetable", "Розклад", "calendar"), ("grades", "Оцінки", "school"),
        ("notes", "Сповіщення", "bell"), ("profile", "Профіль", "person")]
PALETTES = {"scale": "За оцінкою", "ink": "Синя", "ocean": "Океан", "forest": "Ліс", "sunset": "Захід",
            "mono": "Графіт"}


def school_year_start(today: date | None = None) -> date:
    t = today or date.today()
    return date(t.year if t.month >= 9 else t.year - 1, 9, 1)


@dataclass
class Settings:
    """Вигляд застосунку; зберігається у ui.json."""
    palette: str = "scale"
    chart_height: int = 260
    show_values: bool = True
    dark: bool = False
    table_view: bool = True
    path: str = ""

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Settings":
        base = Path(path) if path else Path(os.getenv("FLET_APP_STORAGE_DATA") or os.getenv("NZUA_HOME")
                                            or Path.home() / ".nzua") / "ui.json"
        s = cls(path=str(base))
        try:
            raw = json.loads(base.read_text("utf-8"))
            for k in ("palette", "chart_height", "show_values", "dark", "table_view"):
                if k in raw:
                    setattr(s, k, raw[k])
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        if s.palette not in PALETTES:
            s.palette = "scale"
        try:
            s.chart_height = min(max(int(s.chart_height), 160), 420)
        except (TypeError, ValueError):
            s.chart_height = 260
        return s

    def save(self) -> None:
        if not self.path:
            return
        try:
            p = Path(self.path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({k: v for k, v in asdict(self).items() if k != "path"}), "utf-8")
        except OSError:
            pass


class DiaryApp:
    """Екрани: вхід → вкладки (щоденник, розклад, оцінки, сповіщення, профіль)."""

    def __init__(self, client: Any, *, backend: "str | Backend" = "auto", settings: Settings | None = None,
                 theme: Theme | None = None, title: str = "Щоденник") -> None:
        self.client = client
        self.settings = settings or Settings.load()
        self.app = App(self.build, backend=backend, title=title,
                       theme=theme or (DARK if self.settings.dark else NOTEBOOK),
                       state=dict(screen="loading", tab="diary", week=0, data={}, loading=False,
                                  error="", login_error="", logging_in=False))
        self.app.on_unauthorized = lambda: self.to_login("Сесія завершилась. Увійдіть знову.")
        self.app.on_start = lambda app: app.task(self._start(), refresh=False)
        self._ticket = 0

    def run(self) -> None:
        try:
            self.app.run()
        finally:
            close = getattr(self.client, "aclose", None)
            if close:
                try:
                    import asyncio
                    asyncio.run(close())
                except Exception:  # noqa: BLE001
                    pass

    # ── потік входу ──
    async def _start(self) -> None:
        ok = await self.client.restore_session()
        self.app.update(screen="main" if ok else "login")
        if ok:
            self.load()

    def to_login(self, message: str = "") -> None:
        self._ticket += 1
        self.app.update(screen="login", login_error=message, logging_in=False, data={})

    def login(self, username: str, password: str) -> None:
        s = self.app.state
        if not username or not password:
            self.app.update(login_error="Введіть логін і пароль.")
            return
        self.app.update(logging_in=True, login_error="")

        def done(_st: Any) -> None:
            self.app.update(screen="main", logging_in=False, login_error="", tab="diary", week=0)
            self.load()

        def fail(e: BaseException) -> None:
            self.app.update(logging_in=False, login_error=str(e) or type(e).__name__)

        self.app.task(self.client.login(username, password), done, fail, refresh=False)

    def logout(self) -> None:
        async def go() -> None:
            await self.client.logout()

        self.app.task(go(), lambda _: self.to_login(), lambda e: self.to_login(), refresh=False)

    # ── завантаження даних вкладки ──
    def monday(self) -> date:
        t = date.today()
        return t - timedelta(days=t.weekday()) + timedelta(weeks=self.app.state["week"])

    def load(self) -> None:
        s = self.app.state
        tab, mon = s["tab"], self.monday()
        sun = mon + timedelta(days=6)
        self._ticket += 1
        ticket = self._ticket
        c = self.client

        async def fetch() -> Any:
            if tab == "diary":
                return await c.get_schedule(mon, sun)
            if tab == "timetable":
                return await c.get_timetable(mon, sun)
            if tab == "grades":
                start = school_year_start()
                p = await c.get_student_performance(start, date.today())
                m = await c.get_missed_lessons(start, date.today())
                return p, m
            if tab == "notes":
                return await c.get_notifications(), await c.get_unread_count()
            return await c.ping()

        def done(res: Any) -> None:
            if ticket == self._ticket:  # відповідь на застарілий запит ігноруємо
                s["data"][tab] = res
                s.update(loading=False, error="")

        def fail(e: BaseException) -> None:
            if ticket != self._ticket:
                return
            s.update(loading=False)
            if isinstance(e, Unauthorized):
                self.to_login("Сесія завершилась. Увійдіть знову.")
            else:
                s["error"] = str(e) or type(e).__name__

        s["loading"], s["error"] = True, ""
        self.app.refresh()
        self.app.task(fetch(), done, fail)

    def set_tab(self, key: str) -> None:
        self.app.state["tab"] = key
        self.load()

    def move_week(self, delta: int) -> None:
        s = self.app.state
        s["week"] = 0 if delta == 0 else s["week"] + delta
        self.load()

    # ── діалоги ──
    def open_subject(self, subject_id: int, name: str) -> None:
        self.app.task(self.client.get_subject_performance(subject_id, school_year_start(), date.today()),
                      lambda sp: self.app.show_dialog(Dialog(name, sc.subject_view(sp), [
                          Button("Закрити", self.app.close_dialog, variant="text", id="dlg-close")])))

    def open_hometask(self, hid: int, name: str) -> None:
        def show(ht: Any) -> None:
            self.app.values["answer"] = ht.answer or ""
            parts: list[Any] = [Text(ht.text or "Текст завдання відсутній.", selectable=True)]
            if ht.files:
                parts.append(Text("Файли: " + ", ".join(f.name for f in ht.files), cls="muted"))
            if ht.is_closed:
                parts.append(Text("Завдання закрите для відповідей.", cls="muted"))
            parts.append(Input("answer", "Ваша відповідь", multiline=True, disabled=ht.is_closed, id="answer"))

            def send() -> None:
                self.app.task(self.client.answer_hometask(hid, str(self.app.value("answer"))),
                              lambda _: (self.app.close_dialog(), self.app.toast("Відповідь надіслано")))

            actions = [Button("Закрити", self.app.close_dialog, variant="text", id="dlg-close")]
            if not ht.is_closed:
                actions.append(Button("Надіслати", send, variant="primary", id="dlg-send"))
            self.app.show_dialog(Dialog(name, Column(parts, gap=12, scroll=True), actions))

        self.app.task(self.client.get_hometask(hid), show)

    # ── налаштування ──
    def _settings_controls(self) -> list[Any]:
        st = self.settings

        def set_(attr: str, cast: Any = lambda v: v, relayout: bool = True) -> Any:
            def h(v: Any) -> None:
                setattr(st, attr, cast(v))
                st.save()
                if attr == "dark":
                    self.app.set_theme(DARK if st.dark else NOTEBOOK)
                else:
                    self.app.refresh()
            return h

        return [Text("Вигляд", cls="h3"),
                Dropdown("palette", "Кольори графіка", list(PALETTES.items()), st.palette, on_change=set_("palette")),
                Slider("height", "Висота графіка", 160, 420, st.chart_height, step=20,
                       on_change=set_("chart_height", int)),
                Switch("values", "Підписувати значення", st.show_values, on_change=set_("show_values", bool)),
                Switch("table", "Оцінки таблицею (а не картками)", st.table_view, on_change=set_("table_view", bool)),
                Switch("dark", "Темна тема", st.dark, on_change=set_("dark", bool))]

    # ── побудова інтерфейсу ──
    def build(self, app: App) -> Screen:
        s = app.state
        if s["screen"] == "loading":
            return Screen(Column([Progress()], align="center", justify="center", expand=True, padding=40), scroll=False)
        if s["screen"] == "login":
            return Screen(sc.login_form(app, self.login, s["login_error"], s["logging_in"]), scroll=False, padding=0)
        tab = s["tab"]
        nav = NavBar(TABS, tab, on_change=self.set_tab, id="nav")
        body: list[Any] = []
        data = s["data"].get(tab)
        if tab in ("diary", "timetable"):
            body.append(sc.week_bar(self.monday(), on_prev=lambda: self.move_week(-1), on_today=lambda: self.move_week(0),
                                    on_next=lambda: self.move_week(1), on_refresh=self.load))
        if s["loading"] and data is None:
            body.append(Column([Progress()], align="center", padding=40))
        elif data is None:
            msg = s["error"] or "Не вдалося завантажити дані."
            body += [sc.empty(msg), Button("Спробувати ще", self.load, icon="refresh", variant="outline", id="retry")]
        else:
            if s["loading"]:
                body.append(Progress())
            if s["error"]:
                body.append(sc.banner(s["error"]))
            body += self._tab_view(tab, data)
        return Screen(Column(body), nav=nav)

    def _tab_view(self, tab: str, data: Any) -> list[Any]:
        st = self.settings
        if tab == "diary":
            return sc.diary_view(data, self.open_hometask)
        if tab == "timetable":
            return sc.timetable_view(data)
        if tab == "grades":
            p, m = data
            chart = sc.averages_chart_widget(p, st.palette, st.chart_height, st.show_values)
            return sc.performance_view(p, m, self.open_subject, chart, as_table=st.table_view)
        if tab == "notes":
            n, unread = data
            return sc.notifications_view(n, unread)
        return sc.profile_view(getattr(self.client, "student", None), bool(data), self.logout,
                               self._settings_controls())
