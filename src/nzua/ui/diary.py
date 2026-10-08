"""Готовий застосунок «Щоденник» на nzua.ui: один код для Tkinter, PyQt5 і Flet.

    from nzua import AsyncNZClient
    from nzua.ui.diary import DiaryApp
    DiaryApp(AsyncNZClient(token_store=...), backend="tk").run()

Інтерфейс адаптивний: на телефоні — нижня панель вкладок і щоденник «по днях» (смуга Пн…Нд, свайп), на планшеті
й комп'ютері — бокова панель і тиждень цілком. Вигляд налаштовується (`Settings`): тема й акцентний колір,
розмір тексту, щільність, заокруглення, схема кольорів оцінок, що показувати в уроках, періоди й сортування оцінок.

Власний інтерфейс простіше збирати з нуля з `nzua.ui.screens`; цей клас — приклад і готовий варіант.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..errors import Unauthorized
from . import screens as sc
from .app import App, Backend
from .style import ACCENTS, DENSITIES, MARK_SCHEMES, MODES, Theme, make_theme, subject_key, valid_hex
from .widgets import (Button, Column, Dialog, Dropdown, Input, NavBar, NavItem, Progress, Row, Screen, Slider,
                      Switch, Text)

__all__ = ("DiaryApp", "Settings", "school_year_start", "period_range", "TABS", "PALETTES")

TABS = [("diary", "Щоденник", "book"), ("timetable", "Розклад", "calendar"), ("grades", "Оцінки", "school"),
        ("notes", "Сповіщення", "bell"), ("profile", "Профіль", "person")]
TITLES = {k: v for k, v, _ in TABS}
PALETTES = {"scale": "За оцінкою", "ink": "Синя", "ocean": "Океан", "forest": "Ліс", "sunset": "Захід",
            "mono": "Графіт"}
PERIODS = {"week": "Тиждень", "month": "Місяць", "semester": "Семестр", "year": "Навчальний рік"}
SORTS = {"name": "За назвою", "avg_desc": "Високий бал спершу", "avg_asc": "Низький бал спершу"}
DIARY_MODES = {"auto": "Авто (день — на телефоні)", "week": "Увесь тиждень", "day": "По днях"}
DIARY_VIEWS = [("today", "Сьогодні"), ("lessons", "Уроки"), ("homework", "Д/з"), ("marks", "Оцінки")]
DIARY_STARTS = dict(DIARY_VIEWS)
CHART_TYPES = {"bar": "Стовпчики", "line": "Лінія"}


def school_year_start(today: date | None = None) -> date:
    t = today or date.today()
    return date(t.year if t.month >= 9 else t.year - 1, 9, 1)


def period_range(period: str, today: date | None = None) -> tuple[date, date]:
    """Межі періоду оцінок: `week` | `month` | `semester` | `year` (навчальний рік від 1 вересня)."""
    t = today or date.today()
    if period == "week":
        return t - timedelta(days=t.weekday()), t
    if period == "month":
        return t.replace(day=1), t
    if period == "semester":  # І семестр — вересень–грудень, ІІ — з січня
        return (date(t.year, 9, 1) if t.month >= 9 else date(t.year, 1, 1)), t
    return school_year_start(t), t


def _clamp(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        return min(max(float(v), lo), hi)
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    """Вигляд і поведінка застосунку; зберігається у ui.json. Невідомі чи зіпсовані значення виправляються."""
    # тема
    mode: str = "light"            # auto | light | dark | amoled
    accent: str = "indigo"         # ключ із style.ACCENTS
    mark_scheme: str = "classic"   # classic | colorblind | soft
    font_scale: float = 1.0        # 0.8–1.6
    density: str = "normal"        # compact | normal | roomy
    radius: int = 12               # заокруглення карток і кнопок, 0–28
    card_stripe: bool = True       # кольорова смужка зліва на картках
    shadows: bool = True           # м'які тіні карток
    subject_colors: bool = True    # власний колір для кожного предмета
    animations: bool = True        # плавна поява екранів (вимкніть, якщо заважає)
    accent_hex: str = ""           # свій акцентний колір #RRGGBB (діє, коли accent == "custom")
    # щоденник
    diary_start: str = "today"     # з якого розділу відкривається щоденник
    default_tab: str = "diary"
    diary_mode: str = "auto"       # auto | week | day
    show_time: bool = True
    show_room: bool = True
    show_teacher: bool = True
    # оцінки
    grades_period: str = "year"    # week | month | semester | year
    grades_sort: str = "name"      # name | avg_desc | avg_asc
    palette: str = "scale"         # кольори графіка
    chart_type: str = "bar"
    chart_height: int = 260
    show_values: bool = True
    show_distribution: bool = True
    table_view: bool = True
    # службове
    done: list = field(default_factory=list)   # ключі виконаного Д/з (sc.hw_key)
    goals: dict = field(default_factory=dict)  # цілі: {"Алгебра": 10.5}
    path: str = ""

    _ENUMS = {"mode": MODES, "mark_scheme": MARK_SCHEMES, "density": DENSITIES,
              "default_tab": TITLES, "diary_mode": DIARY_MODES, "diary_start": DIARY_STARTS, "grades_period": PERIODS, "grades_sort": SORTS,
              "palette": PALETTES, "chart_type": CHART_TYPES}

    # сумісність зі старою версією, де була лише світла/темна тема
    @property
    def dark(self) -> bool:
        return self.mode in ("dark", "amoled")

    @dark.setter
    def dark(self, value: bool) -> None:
        self.mode = "dark" if value else "light"

    def validate(self) -> "Settings":
        defaults = Settings()
        for k, allowed in self._ENUMS.items():
            if getattr(self, k) not in allowed:
                setattr(self, k, getattr(defaults, k))
        self.accent_hex = self.accent_hex.upper() if valid_hex(self.accent_hex) else ""
        if not (self.accent in ACCENTS or (self.accent == "custom" and self.accent_hex)):
            self.accent = defaults.accent
        self.font_scale = round(_clamp(self.font_scale, 0.8, 1.6, 1.0), 2)
        self.radius = int(_clamp(self.radius, 0, 28, 12))
        self.chart_height = int(_clamp(self.chart_height, 160, 420, 260))
        for k in ("card_stripe", "shadows", "subject_colors", "animations", "show_time", "show_room", "show_teacher", "show_values", "show_distribution",
                  "table_view"):
            setattr(self, k, bool(getattr(self, k)))
        self.done = [x for x in (self.done if isinstance(self.done, list) else []) if isinstance(x, str)][-400:]
        goals = self.goals if isinstance(self.goals, dict) else {}
        self.goals = {str(k): round(_clamp(v, 1, 12, 10), 1) for k, v in list(goals.items())[:80]}
        return self

    def reset(self) -> None:
        """Повертає типові значення (позначки виконаного Д/з і шлях файлу лишаються)."""
        for f in fields(self):
            if f.name not in ("done", "path", "goals"):
                setattr(self, f.name, getattr(Settings(), f.name))

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Settings":
        base = Path(path) if path else Path(os.getenv("FLET_APP_STORAGE_DATA") or os.getenv("NZUA_HOME")
                                            or Path.home() / ".nzua") / "ui.json"
        s = cls(path=str(base))
        try:
            raw = json.loads(base.read_text("utf-8"))
            if isinstance(raw, dict):
                if "mode" not in raw and raw.get("dark"):   # файл зі старої версії
                    raw["mode"] = "dark"
                for f in fields(cls):
                    if f.name != "path" and f.name in raw:
                        setattr(s, f.name, raw[f.name])
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return s.validate()

    def save(self) -> None:
        if not self.path:
            return
        try:
            p = Path(self.path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({k: v for k, v in asdict(self).items() if k != "path"}, ensure_ascii=False),
                         "utf-8")
        except OSError:
            pass


class DiaryApp:
    """Екрани: вхід → вкладки (щоденник, розклад, оцінки, сповіщення, профіль) → налаштування."""

    def __init__(self, client: Any, *, backend: "str | Backend" = "auto", settings: Settings | None = None,
                 theme: Theme | None = None, title: str = "Щоденник") -> None:
        self.client = client
        self.settings = (settings or Settings.load()).validate()
        self._fixed_theme = theme            # власна тема: налаштування теми не застосовуються, лише масштаб
        self._theme_key: tuple | None = None
        self._subject_cache: dict[int, Any] = {}
        self._ticket = 0
        self.app = App(self.build, backend=backend, title=title,
                       state=dict(screen="loading", tab=self.settings.default_tab, week=0, day=None,
                                  diary_view=self.settings.diary_start, sub="", only_open=False, query="", hw_query="",
                                  data={},
                                  loading=False, error="", login_error="", logging_in=False, unread=0))
        self._sync_theme()
        self.app.on_unauthorized = lambda: self.to_login("Сесія завершилась. Увійдіть знову.")
        self.app.on_start = lambda app: app.task(self._start(), refresh=False)
        self.app.on_back = self.on_back

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

    # ── тема з налаштувань ──
    def _sync_theme(self) -> None:
        """Перебудовує тему, якщо змінилися налаштування або системна темна тема (викликається з `build`)."""
        st = self.settings
        mode = ("dark" if self.app.system_dark else "light") if st.mode == "auto" else st.mode
        key = (mode, st.accent, st.accent_hex, st.mark_scheme, st.font_scale, st.density, st.radius, st.card_stripe,
               st.shadows)
        if key == self._theme_key:
            return
        self._theme_key = key
        if self._fixed_theme is not None:
            self.app.theme = self._fixed_theme.with_(font_scale=st.font_scale,
                                                     space_scale=make_theme(density=st.density).space_scale)
        else:
            self.app.theme = make_theme(mode, st.accent, font_scale=st.font_scale, density=st.density,
                                        radius=st.radius, stripe=st.card_stripe, mark_scheme=st.mark_scheme,
                                        shadows=st.shadows, accent_hex=st.accent_hex)

    # ── потік входу ──
    async def _start(self) -> None:
        ok = await self.client.restore_session()
        self.app.update(screen="main" if ok else "login")
        if ok:
            self.load()
            self._load_unread()

    def to_login(self, message: str = "") -> None:
        self._ticket += 1
        self._subject_cache.clear()
        self.app.update(screen="login", login_error=message, logging_in=False, data={}, unread=0, sub="")

    def login(self, username: str, password: str) -> None:
        if not username or not password:
            self.app.update(login_error="Введіть логін і пароль.")
            return
        self.app.update(logging_in=True, login_error="")

        def done(_st: Any) -> None:
            self.app.update(screen="main", logging_in=False, login_error="", tab=self.settings.default_tab,
                            week=0, day=None, sub="", diary_view=self.settings.diary_start)
            self.load()
            self._load_unread()

        def fail(e: BaseException) -> None:
            self.app.update(logging_in=False, login_error=str(e) or type(e).__name__)

        self.app.task(self.client.login(username, password), done, fail, refresh=False)

    def logout(self) -> None:
        async def go() -> None:
            await self.client.logout()

        self.app.task(go(), lambda _: self.to_login(), lambda e: self.to_login(), refresh=False)

    def _load_unread(self) -> None:
        """Лічильник непрочитаних для значка на вкладці «Сповіщення» (помилки мовчки ігноруються)."""
        getter = getattr(self.client, "get_unread_count", None)
        if getter is None:
            return
        self.app.task(getter(), lambda n: self.app.state.update(unread=int(n or 0)), lambda e: None)

    # ── дати ──
    def monday(self) -> date:
        t = date.today()
        return t - timedelta(days=t.weekday()) + timedelta(weeks=self.app.state["week"])

    def selected_day(self) -> date:
        """Вибраний день у межах поточного тижня; типово сьогодні (на вихідних — п'ятниця)."""
        mon, d = self.monday(), self.app.state.get("day")
        if isinstance(d, date) and mon <= d <= mon + timedelta(days=6):
            return d
        t = date.today()
        if mon <= t <= mon + timedelta(days=6):
            return t if t.weekday() < 5 else mon + timedelta(days=4)
        return mon

    def day_mode(self) -> bool:
        m = self.settings.diary_mode
        return m == "day" or (m == "auto" and self.app.compact)

    # ── завантаження даних вкладки ──
    def load(self) -> None:
        s = self.app.state
        tab, mon = s["tab"], self.monday()
        sun = mon + timedelta(days=6)
        start, end = period_range(self.settings.grades_period)
        self._ticket += 1
        ticket = self._ticket
        c = self.client

        async def fetch() -> Any:
            if tab == "diary":
                return await c.get_schedule(mon, sun)
            if tab == "timetable":
                return await c.get_timetable(mon, sun)
            if tab == "grades":
                p = await c.get_student_performance(start, end)
                m = await c.get_missed_lessons(start, end)
                return p, m
            if tab == "notes":
                return await c.get_notifications(), await c.get_unread_count()
            return await c.ping()

        def done(res: Any) -> None:
            if ticket == self._ticket:  # відповідь на застарілий запит ігноруємо
                s["data"][tab] = res
                if tab == "notes":
                    s["unread"] = int(res[1] or 0)
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
        self.app.state.update(tab=key, sub="")
        self.load()

    def move_week(self, delta: int) -> None:
        s = self.app.state
        if delta == 0:
            s["week"], s["day"] = 0, None
        else:
            s["day"] = self.selected_day() + timedelta(weeks=delta)
            s["week"] += delta
        self.load()

    def select_day(self, d: date) -> None:
        self.app.update(day=d)

    def set_diary_view(self, view: str) -> None:
        """Розділ щоденника: сьогодні | уроки | Д/з | оцінки. «Сьогодні» завжди про поточний тиждень."""
        s = self.app.state
        if view == "today" and s["week"] != 0:
            s.update(diary_view=view, week=0, day=None)
            self.load()
        else:
            self.app.update(diary_view=view)

    def shift_day(self, delta: int) -> None:
        """Наступний/попередній день (у режимі «тиждень» — тиждень); за межею тижня завантажує сусідній."""
        if not self.day_mode():
            self.move_week(delta)
            return
        d = self.selected_day() + timedelta(days=delta)
        t = date.today()
        week = ((d - timedelta(days=d.weekday())) - (t - timedelta(days=t.weekday()))).days // 7
        s = self.app.state
        s["day"] = d
        if week != s["week"]:
            s["week"] = week
            self.load()
        else:
            self.app.refresh()

    def on_swipe(self, direction: str) -> None:
        s = self.app.state
        if s["tab"] == "timetable" or (s["tab"] == "diary" and s["diary_view"] == "lessons"):
            self.shift_day(1 if direction == "left" else -1)

    def on_back(self) -> bool:
        """Системна кнопка «назад»: налаштування → профіль; інша вкладка → стартова."""
        s = self.app.state
        if s["screen"] != "main":
            return False
        if s["sub"]:
            self.app.update(sub="")
            return True
        if s["tab"] != self.settings.default_tab:
            self.set_tab(self.settings.default_tab)
            return True
        return False

    # ── виконане Д/з ──
    def toggle_done(self, key: str) -> None:
        done = self.settings.done
        if key in done:
            done.remove(key)
        else:
            done.append(key)
        del done[:-400]
        self.settings.save()
        self.app.refresh()

    # ── діалоги ──
    def _dialog_width(self) -> int:
        return int(max(280, min(self.app.width - 40, 480)))

    def open_subject(self, subject_id: int, name: str) -> None:
        start, end = period_range(self.settings.grades_period)

        def got(sp: Any) -> None:
            self._subject_cache[subject_id] = sp
            self._show_subject(subject_id, name, 10.0)

        self.app.task(self.client.get_subject_performance(subject_id, start, end), got)

    def _show_subject(self, subject_id: int, name: str, target: float, extra: tuple = ()) -> None:
        sp = self._subject_cache[subject_id]
        self.app.values["target"] = f"{target:g}"

        def set_goal(t: float) -> None:
            self.settings.goals[name] = float(t)
            self.settings.validate()
            self.settings.save()
            self._show_subject(subject_id, name, target, extra)
            self.app.refresh()

        def what_if(v: int) -> None:
            self._show_subject(subject_id, name, target, () if v == 0 else (*extra, int(v)))

        self.app.show_dialog(Dialog(name, sc.subject_view(
            sp, target, lambda v: self._show_subject(subject_id, name, float(v), extra), extra=extra,
            on_extra=what_if, goal=self.settings.goals.get(name), on_goal=set_goal,
            line_color=self.app.theme.color(subject_key(name)) or "#26358F"), [
            Button("Закрити", self.app.close_dialog, variant="text", id="dlg-close")], width=self._dialog_width()))

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
            self.app.show_dialog(Dialog(name, Column(parts, gap=12, scroll=True), actions,
                                        width=self._dialog_width()))

        self.app.task(self.client.get_hometask(hid), show)

    def share_homework(self) -> None:
        """Д/з тижня текстом: виділіть і скопіюйте, щоб надіслати в чат."""
        data = self.app.state["data"].get("diary")
        if data is None:
            return
        text = sc.homework_text(data, set(self.settings.done))
        self.app.show_dialog(Dialog("Д/з тижня", Column([Text(text, selectable=True, id="share-text")], scroll=True,
                                                         height=320),
                                    [Button("Закрити", self.app.close_dialog, variant="text", id="dlg-close")],
                                    width=self._dialog_width()))

    def open_backup(self) -> None:
        """Резервна копія налаштувань: показати JSON для копіювання або вставити свій і застосувати."""
        payload = {k: v for k, v in asdict(self.settings).items() if k not in ("path", "done")}
        self.app.values["backup_in"] = ""

        def apply() -> None:
            try:
                raw = json.loads(str(self.app.value("backup_in")))
                assert isinstance(raw, dict)
            except (ValueError, AssertionError):
                self.app.toast("Це не схоже на копію налаштувань")
                return
            for f in fields(self.settings):
                if f.name not in ("path", "done") and f.name in raw:
                    setattr(self.settings, f.name, raw[f.name])
            self.settings.validate()
            self.settings.save()
            self.app.close_dialog()
            self.app.toast("Налаштування застосовано")
            self.app.refresh()

        self.app.show_dialog(Dialog("Резервна копія налаштувань", Column([
            Text("Скопіюйте цей текст, щоб перенести вигляд на інший пристрій:", cls="small"),
            Text(json.dumps(payload, ensure_ascii=False), selectable=True, cls="muted", id="backup-json"),
            Input("backup_in", "Вставте копію сюди", multiline=True, id="backup-in")], gap=10, scroll=True),
            [Button("Закрити", self.app.close_dialog, variant="text", id="dlg-close"),
             Button("Застосувати", apply, variant="primary", id="dlg-apply")], width=self._dialog_width()))

    def set_accent_hex(self, value: str) -> None:
        v = ("#" + value.strip().lstrip("#")).upper()
        if not valid_hex(v):
            self.app.toast("Вкажіть колір у форматі #RRGGBB")
            return
        self.settings.accent_hex, self.settings.accent = v, "custom"
        self.settings.save()
        self.app.refresh()

    def confirm_reset(self) -> None:
        def do() -> None:
            self.settings.reset()
            self.settings.save()
            self.app.close_dialog()
            self.app.toast("Налаштування скинуто")
            self.app.refresh()

        self.app.show_dialog(Dialog("Скинути налаштування?", Text("Вигляд і поведінка повернуться до типових."), [
            Button("Скасувати", self.app.close_dialog, variant="text", id="dlg-cancel"),
            Button("Скинути", do, variant="primary", id="dlg-reset")], width=self._dialog_width()))

    # ── налаштування ──
    def _set(self, attr: str, cast: Any = lambda v: v, *, reload: bool = False) -> Any:
        def handler(v: Any) -> None:
            setattr(self.settings, attr, cast(v))
            self.settings.validate()
            self.settings.save()
            if reload:
                self.app.state["data"].pop("grades", None)
                self.load()
            else:
                self.app.refresh()
        return handler

    def _swatches(self) -> Any:
        """Рядок кольорових кружечків для вибору акценту."""
        dark = self.app.theme.dark
        items = []
        for key, (_label, light, night) in ACCENTS.items():
            sel = self.settings.accent == key
            items.append(Text("✓" if sel else "", color="#101424" if dark else "#FFFFFF", text_align="center",
                              bold=True, bg=night if dark else light, width=40, height=40, radius=20,
                              on_click=(lambda k=key: self._set("accent")(k)), id=f"accent-{key}"))
        if self.settings.accent_hex:
            sel = self.settings.accent == "custom"
            items.append(Text("✓" if sel else "", color="#101424" if dark else "#FFFFFF", text_align="center",
                              bold=True, bg=self.settings.accent_hex, width=40, height=40, radius=20,
                              on_click=lambda: self._set("accent")("custom"), id="accent-custom"))
        return Row(items, wrap=True, gap=10)

    def settings_view(self) -> list[Any]:
        st, set_ = self.settings, self._set
        return [
            Row([Button("Назад", lambda: self.app.update(sub=""), icon="left", variant="text", id="settings-back"),
                 Text("Налаштування", cls="h2")], gap=4),
            sc.section("Тема й кольори", [
                Dropdown("mode", "Тема", list(MODES.items()), st.mode, on_change=set_("mode"), id="mode"),
                Text("Акцентний колір", cls="small"), self._swatches(),
                Input("accent_hex", "Свій колір (#RRGGBB)", st.accent_hex, on_submit=self.set_accent_hex,
                      id="accent-hex"),
                Dropdown("mark_scheme", "Кольори оцінок", [(k, v[0]) for k, v in MARK_SCHEMES.items()],
                         st.mark_scheme, on_change=set_("mark_scheme"), id="mark_scheme")]),
            sc.section("Розмір і щільність", [
                Slider("font_scale", "Розмір тексту (×)", 0.8, 1.6, st.font_scale, step=0.1,
                       on_change=set_("font_scale", float), id="font_scale"),
                Dropdown("density", "Щільність", list(DENSITIES.items()), st.density, on_change=set_("density"),
                         id="density"),
                Slider("radius", "Заокруглення", 0, 28, st.radius, step=2,
                       on_change=set_("radius", lambda v: int(round(float(v)))), id="radius"),
                Switch("card_stripe", "Кольорова смужка на картках", st.card_stripe,
                       on_change=set_("card_stripe", bool), id="card_stripe"),
                Switch("shadows", "М'які тіні карток", st.shadows, on_change=set_("shadows", bool), id="shadows"),
                Switch("subject_colors", "Власний колір для кожного предмета", st.subject_colors,
                       on_change=set_("subject_colors", bool), id="subject_colors"),
                Switch("animations", "Плавні переходи", st.animations, on_change=set_("animations", bool),
                       id="animations")]),
            sc.section("Щоденник і розклад", [
                Dropdown("diary_mode", "Подання тижня", list(DIARY_MODES.items()), st.diary_mode,
                         on_change=set_("diary_mode"), id="diary_mode"),
                Dropdown("diary_start", "Щоденник відкривається з", list(DIARY_STARTS.items()), st.diary_start,
                         on_change=set_("diary_start"), id="diary_start"),
                Dropdown("default_tab", "Стартова вкладка", [(k, v) for k, v, _ in TABS], st.default_tab,
                         on_change=set_("default_tab"), id="default_tab"),
                Switch("show_time", "Час уроків", st.show_time, on_change=set_("show_time", bool), id="show_time"),
                Switch("show_room", "Кабінет", st.show_room, on_change=set_("show_room", bool), id="show_room"),
                Switch("show_teacher", "Вчитель", st.show_teacher, on_change=set_("show_teacher", bool),
                       id="show_teacher")]),
            sc.section("Оцінки", [
                Dropdown("grades_period", "Період", list(PERIODS.items()), st.grades_period,
                         on_change=set_("grades_period", reload=True), id="grades_period"),
                Dropdown("grades_sort", "Порядок предметів", list(SORTS.items()), st.grades_sort,
                         on_change=set_("grades_sort"), id="grades_sort"),
                Switch("table_view", "Таблицею (а не картками)", st.table_view, on_change=set_("table_view", bool),
                       id="table_view"),
                Dropdown("palette", "Кольори графіка", list(PALETTES.items()), st.palette,
                         on_change=set_("palette"), id="palette"),
                Dropdown("chart_type", "Вид графіка", list(CHART_TYPES.items()), st.chart_type,
                         on_change=set_("chart_type"), id="chart_type"),
                Slider("height", "Висота графіка", 160, 420, st.chart_height, step=20,
                       on_change=set_("chart_height", lambda v: int(round(float(v)))), id="chart_height"),
                Switch("values", "Підписувати значення", st.show_values, on_change=set_("show_values", bool),
                       id="show_values"),
                Switch("distribution", "Розподіл оцінок", st.show_distribution,
                       on_change=set_("show_distribution", bool), id="show_distribution")]),
            Button("Резервна копія налаштувань", self.open_backup, variant="outline", id="backup-settings"),
            Button("Скинути налаштування", self.confirm_reset, variant="outline", id="reset-settings"),
        ]

    # ── побудова інтерфейсу ──
    def _page_key(self) -> str:
        """Ідентифікатор «сторінки»: коли він змінюється, Flet програє плавну появу екрана."""
        s = self.app.state
        return f"{s['screen']}|{s['tab']}|{s['sub']}|{s['diary_view'] if s['tab'] == 'diary' else ''}|{s['week']}"

    def build(self, app: App) -> Screen:
        self._sync_theme()
        app.animations = self.settings.animations
        s = app.state
        if s["screen"] == "loading":
            return Screen(Column([Progress()], align="center", justify="center", expand=True, padding=40),
                          scroll=False)
        if s["screen"] == "login":
            return Screen(sc.login_form(app, self.login, s["login_error"], s["logging_in"]), scroll=False,
                          padding=0, max_width=460)
        tab = s["tab"]
        wide = not app.compact
        items = [NavItem(k, label, icon, badge=(s["unread"] or None) if k == "notes" else None)
                 for k, label, icon in TABS]
        nav = NavBar(items, tab, on_change=self.set_tab, rail=wide, id="nav")
        max_width = None if not wide else (720 if app.layout == "medium" else 880)
        if s["sub"] == "settings" and tab == "profile":
            return Screen(Column(self.settings_view(), gap=10), nav=nav, max_width=max_width, key=self._page_key())
        body: list[Any] = []
        data = s["data"].get(tab)
        if tab in ("diary", "timetable"):
            body += self._week_header(tab)
        elif tab != "profile":
            body.append(Row([Text(TITLES[tab], cls="h2", expand=True),
                             Button("", self.load, icon="refresh", variant="text", id="refresh")]))
        if s["loading"] and data is None:
            body += sc.skeleton(3)
        elif data is None:
            msg = s["error"] or "Не вдалося завантажити дані."
            body += [sc.empty(msg), Button("Спробувати ще", self.load, icon="refresh", variant="outline",
                                           id="retry")]
        else:
            if s["loading"]:
                body.append(Progress())
            if s["error"]:
                body.append(sc.banner(s["error"]))
            body += self._tab_view(tab, data)
        swipe = self.on_swipe if tab in ("diary", "timetable") else None
        return Screen(Column(body), nav=nav, max_width=max_width, on_swipe=swipe, key=self._page_key())

    def _week_header(self, tab: str) -> list[Any]:
        s = self.app.state
        out: list[Any] = []
        view = s["diary_view"] if tab == "diary" else ""
        if tab == "diary":
            out.append(sc.segmented(DIARY_VIEWS, view, self.set_diary_view, id_prefix="dv"))
        if view != "today":
            out.append(sc.week_bar(self.monday(), on_prev=lambda: self.move_week(-1),
                                   on_today=lambda: self.move_week(0), on_next=lambda: self.move_week(1),
                                   on_refresh=self.load))
        else:
            out.append(Row([Text("", expand=True), Button("", self.load, icon="refresh", variant="text",
                                                           id="refresh")]))
        if self._shows_day_strip():
            data = s["data"].get(tab)
            marked = []
            if data is not None and tab == "diary":
                marked = [d.date for d in data.days if d.date and
                          any(sub.grades for les in d.lessons for sub in les.subjects)]
            out.append(sc.day_strip(self.monday(), self.selected_day(), self.select_day, today=date.today(),
                                    marked=marked))
        return out

    def _shows_day_strip(self) -> bool:
        s = self.app.state
        return self.day_mode() and (s["tab"] == "timetable" or (s["tab"] == "diary" and s["diary_view"] == "lessons"))

    def _tab_view(self, tab: str, data: Any) -> list[Any]:
        st, s = self.settings, self.app.state
        today, now = date.today(), datetime.now().time()
        flags = dict(show_time=st.show_time, show_room=st.show_room, show_teacher=st.show_teacher,
                     colors=st.subject_colors)
        day = self.selected_day() if self._shows_day_strip() else None
        if tab == "diary":
            view = s["diary_view"]
            if view == "today":
                student = getattr(self.client, "student", None)
                return sc.dashboard_view(data, name=sc.first_name(getattr(student, "full_name", "")), today=today,
                                         now=now, done=set(st.done), on_toggle=self.toggle_done,
                                         on_goto=self.set_diary_view, theme=self.app.theme,
                                         colors=st.subject_colors)
            if view == "homework":
                def hw_search(*_: Any) -> None:
                    self.app.update(hw_query=str(self.app.value("hw_q")).strip())

                return [Row([Input("hw_q", "Пошук у Д/з", s["hw_query"], on_submit=hw_search, expand=True,
                                   id="hw-q"),
                             Button("", hw_search, icon="search", variant="text", id="hw-search")], gap=4),
                        Row([Switch("only_open", "Лише невиконані", s["only_open"],
                                    on_change=lambda v: self.app.update(only_open=bool(v)), id="only-open"),
                             Button("Поділитися", self.share_homework, variant="text", id="share-hw")],
                            justify="between"),
                        *sc.homework_view(data, self.open_hometask, done=set(st.done), on_toggle=self.toggle_done,
                                          only_open=s["only_open"], today=today, query=s["hw_query"],
                                          colors=st.subject_colors)]
            if view == "marks":
                out: list[Any] = [sc.grades_table(data, compact=self.app.compact, id="week-grades",
                                                  margin=(0, 0, 10, 0))]
                if not self.app.compact:
                    out.insert(0, sc.journal_table(data, id="week-journal", margin=(0, 0, 10, 0)))
                return out
            return sc.diary_view(data, self.open_hometask, day=day, today=today, now=now, done=set(st.done),
                                 **flags)
        if tab == "timetable":
            return sc.timetable_view(data, day=day, today=today, now=now, **flags)
        if tab == "grades":
            return self._grades_view(*data)
        if tab == "notes":
            n, unread = data
            return sc.notifications_view(n, unread)
        return sc.profile_view(getattr(self.client, "student", None), bool(data), self.logout,
                               on_settings=lambda: self.app.update(sub="settings"))

    def _grades_view(self, p: Any, m: Any) -> list[Any]:
        st, s = self.settings, self.app.state
        subs = sc.filter_subjects(p, s["query"], st.grades_sort)

        def apply(*_: Any) -> None:
            self.app.update(query=str(self.app.value("subject_q")).strip())

        controls = [
            Row([Dropdown("grades_period", "Період", list(PERIODS.items()), st.grades_period,
                          on_change=self._set("grades_period", reload=True), expand=True, id="grades-period"),
                 Dropdown("grades_sort", "Порядок", list(SORTS.items()), st.grades_sort,
                          on_change=self._set("grades_sort"), expand=True, id="grades-sort")], gap=8, align="start"),
            Row([Input("subject_q", "Пошук предмета", s["query"], on_submit=apply, expand=True, id="subject-q"),
                 Button("", apply, icon="search", variant="text", id="subject-search")], gap=4),
        ]
        chart = sc.averages_chart_widget(p, st.palette, st.chart_height, st.show_values, st.chart_type, subs)
        extras = [sc.distribution_chart_widget(p, max(160, st.chart_height - 40), st.show_values)
                  if st.show_distribution else None]
        return controls + sc.performance_view(p, m, self.open_subject, chart, as_table=st.table_view, subjects=subs,
                                              compact=self.app.compact, extras=extras, goals=st.goals,
                                              colors=st.subject_colors, theme=self.app.theme)
