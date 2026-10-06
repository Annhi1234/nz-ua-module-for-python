"""Електронний щоденник nz.ua — Flet-застосунок (Android/desktop)."""
from __future__ import annotations

from datetime import date, timedelta

import flet as ft
from flet_secure_storage import SecureStorage

import views as v
from nzua import AsyncNZClient, FileCache, NZError, Unauthorized
from storage import PALETTES, SecureTokenStore, Settings, data_dir

TABS = [("Щоденник", ft.Icons.MENU_BOOK), ("Розклад", ft.Icons.CALENDAR_MONTH),
        ("Оцінки", ft.Icons.SCHOOL), ("Сповіщення", ft.Icons.NOTIFICATIONS),
        ("Профіль", ft.Icons.PERSON)]


def school_year_start() -> date:
    t = date.today()
    return date(t.year if t.month >= 9 else t.year - 1, 9, 1)


class App:
    def __init__(self, page: ft.Page, store: SecureTokenStore) -> None:
        self.page, self.store = page, store
        self.client: AsyncNZClient | None = None
        self.week = 0
        self.tab = 0
        self.settings = Settings.load()
        self.body = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=0)

    # ── допоміжне ──
    def toast(self, text: str) -> None:
        self.page.show_dialog(ft.SnackBar(content=ft.Text(text)))

    def new_client(self) -> AsyncNZClient:
        return AsyncNZClient(token_store=self.store, cache=FileCache(data_dir() / "cache.json"))

    async def guard(self, coro):
        """Виконує запит; помилки показує користувачу, а не падає."""
        try:
            return await coro
        except Unauthorized:
            await self.show_login("Сесія завершилась. Увійдіть знову.")
        except NZError as e:
            self.toast(str(e))
        return None

    def set_root(self, *controls: ft.Control) -> None:
        self.page.controls.clear()
        self.page.add(ft.SafeArea(content=ft.Column(list(controls), expand=True, spacing=0), expand=True))

    # ── старт і вхід ──
    async def start(self) -> None:
        self.client = self.new_client()
        if await self.client.restore_session():
            await self.show_main()
        else:
            await self.show_login()

    async def show_login(self, message: str = "") -> None:
        self.page.navigation_bar = None
        user = ft.TextField(label="Логін", autofocus=True, border_radius=10)
        pwd = ft.TextField(label="Пароль", password=True, can_reveal_password=True, border_radius=10)
        err = ft.Text(message, color=v.BAD, size=13)
        btn = ft.FilledButton(content="Увійти")

        async def submit(e) -> None:
            if not user.value or not pwd.value:
                err.value = "Введіть логін і пароль."
                self.page.update()
                return
            btn.disabled, err.value = True, ""
            self.page.update()
            try:
                assert self.client
                await self.client.login(user.value.strip(), pwd.value)
            except NZError as ex:
                err.value, btn.disabled = str(ex), False
                self.page.update()
                return
            await self.show_main()

        btn.on_click = pwd.on_submit = submit
        self.set_root(ft.Container(ft.Column([
            ft.Text("Щоденник", size=34, weight=ft.FontWeight.BOLD, color=v.INK),
            ft.Text("Увійдіть у свій акаунт nz.ua", size=15, color=v.MUTED),
            ft.Container(height=12), user, pwd, err, btn], spacing=10),
            padding=ft.Padding.all(24), expand=True, alignment=ft.Alignment.CENTER))
        self.page.update()

    # ── головний екран ──
    async def show_main(self) -> None:
        self.page.navigation_bar = ft.NavigationBar(
            destinations=[ft.NavigationBarDestination(icon=i, label=t) for t, i in TABS],
            selected_index=self.tab, on_change=self.on_tab)
        self.set_root(ft.Container(self.body, padding=ft.Padding.symmetric(horizontal=14, vertical=8), expand=True))
        await self.render()

    async def on_tab(self, e) -> None:
        self.tab = e.control.selected_index
        await self.render()

    def week_bar(self) -> ft.Control:
        monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(weeks=self.week)
        sunday = monday + timedelta(days=6)

        async def move(delta: int) -> None:
            self.week = 0 if delta == 0 else self.week + delta
            await self.render()

        return ft.Row([
            ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=lambda e: self.page.run_task(move, -1)),
            ft.TextButton(content=f"{monday.day} {v.MONTHS[monday.month - 1]} – {sunday.day} {v.MONTHS[sunday.month - 1]}",
                          on_click=lambda e: self.page.run_task(move, 0)),
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=lambda e: self.page.run_task(move, 1)),
            ft.IconButton(ft.Icons.REFRESH, tooltip="Оновити", on_click=lambda e: self.page.run_task(self.render))],
            alignment=ft.MainAxisAlignment.CENTER)

    async def render(self) -> None:
        c = self.client
        assert c
        self.body.controls = [ft.Container(ft.ProgressRing(), alignment=ft.Alignment.CENTER, padding=40)]
        self.page.update()
        monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(weeks=self.week)
        sunday = monday + timedelta(days=6)
        items: list[ft.Control] | None = None

        if self.tab == 0:
            s = await self.guard(c.get_schedule(monday, sunday))
            items = [self.week_bar(), *v.schedule_view(s, self.open_hometask)] if s else None
        elif self.tab == 1:
            t = await self.guard(c.get_timetable(monday, sunday))
            items = [self.week_bar(), *v.timetable_view(t)] if t else None
        elif self.tab == 2:
            start = school_year_start()
            p = await self.guard(c.get_student_performance(start, date.today()))
            m = await self.guard(c.get_missed_lessons(start, date.today())) if p else None
            chart = v.chart_view(p, self.settings.palette, self.settings.chart_height,
                                 self.settings.show_values) if p else None
            items = v.performance_view(p, m, self.open_subject, chart) if p else None
        elif self.tab == 3:
            n = await self.guard(c.get_notifications())
            u = await self.guard(c.get_unread_count()) if n is not None else None
            items = v.notifications_view(n, u or 0) if n is not None else None
        else:
            ok = await c.ping()
            items = v.profile_view(c.student, ok, self.logout, self.settings_controls())

        if items is not None:
            self.body.controls = items
            self.page.update()
        elif self.client and self.client.is_authenticated:
            self.body.controls = [v.empty("Не вдалося завантажити дані. Потягніть ↻ та спробуйте ще раз."),
                                  ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: self.page.run_task(self.render))]
            self.page.update()

    def settings_controls(self) -> list[ft.Control]:
        """Налаштування графіка: колір, висота, підписи значень."""
        st = self.settings

        def changed(e) -> None:
            st.save()

        def set_palette(e) -> None:
            st.palette = e.control.value or "scale"
            st.save()

        def set_height(e) -> None:
            st.chart_height = int(e.control.value)
            st.save()

        def set_values(e) -> None:
            st.show_values = bool(e.control.value)
            st.save()

        return [
            ft.Text("Вигляд графіка", size=16, weight=ft.FontWeight.W_600, color=v.INK),
            ft.Dropdown(label="Кольори", value=st.palette, on_select=set_palette,
                        options=[ft.DropdownOption(key=k, text=t) for k, t in PALETTES.items()]),
            ft.Text("Висота графіка", size=13, color=v.MUTED),
            ft.Slider(min=160, max=420, divisions=13, value=st.chart_height, label="{value}",
                      on_change_end=set_height),
            ft.Switch(label="Підписувати значення", value=st.show_values, on_change=set_values),
        ]

    # ── діалоги ──
    def close_dialog(self, e=None) -> None:
        self.page.pop_dialog()

    async def open_subject(self, subject_id: int, name: str) -> None:
        assert self.client
        sp = await self.guard(self.client.get_subject_performance(subject_id, school_year_start(), date.today()))
        if sp:
            self.page.show_dialog(ft.AlertDialog(
                title=ft.Text(name), content=v.subject_view(sp),
                actions=[ft.TextButton(content="Закрити", on_click=self.close_dialog)]))

    async def open_hometask(self, hometask_id: int, name: str) -> None:
        assert self.client
        ht = await self.guard(self.client.get_hometask(hometask_id))
        if not ht:
            return
        answer = ft.TextField(label="Ваша відповідь", multiline=True, min_lines=3, value=ht.answer or "",
                              disabled=ht.is_closed, border_radius=10)
        parts: list[ft.Control] = [ft.Text(ht.text or "Текст завдання відсутній.", selectable=True, size=14)]
        if ht.files:
            parts.append(ft.Text("Файли: " + ", ".join(f.name for f in ht.files), size=12, color=v.MUTED))
        if ht.is_closed:
            parts.append(ft.Text("Завдання закрите для відповідей.", size=12, color=v.MUTED))
        parts.append(answer)

        async def send(e) -> None:
            assert self.client
            if await self.guard(self.client.answer_hometask(hometask_id, answer.value or "")):
                self.close_dialog()
                self.toast("Відповідь надіслано")

        actions = [ft.TextButton(content="Закрити", on_click=self.close_dialog)]
        if not ht.is_closed:
            actions.append(ft.FilledButton(content="Надіслати", on_click=send))
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text(name), actions=actions,
            content=ft.Column(parts, spacing=12, tight=True, scroll=ft.ScrollMode.AUTO, width=320)))

    async def logout(self, e) -> None:
        assert self.client
        await self.client.logout()
        self.tab, self.week = 0, 0
        await self.show_login()


async def main(page: ft.Page) -> None:
    page.title = "Щоденник"
    page.theme = ft.Theme(color_scheme_seed=v.INK, use_material3=True)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = v.PAPER
    page.padding = 0
    secure = SecureStorage()
    page.services.append(secure)
    page.update()
    await App(page, SecureTokenStore(secure)).start()


ft.run(main)
