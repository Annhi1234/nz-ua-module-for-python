"""Бекенд Flet (Android/iOS/desktop/web). Використовує лише ті виклики Flet 1.0, що вже є в застосунку.

Запитів у мережу виконуються у циклі подій самого Flet (це потрібно для `flet-secure-storage`),
тому тут `spawn` не створює окремий потік.

    from nzua.ui.backends.flet import FletBackend
    App(build, backend=FletBackend(setup=lambda page: page.services.append(my_service))).run()
"""
from __future__ import annotations

from typing import Any, Callable

import flet as ft

from ..app import Backend
from ..style import Style, Theme
from ..widgets import (Button, Card, Cell, Chart, Chip, Column, Dialog, Divider, Dropdown, Image, Input, NavBar,
                       Progress, Row, Screen, Slider, Spacer, Switch, Table, Text, Widget)

_ICONS = {
    "left": "CHEVRON_LEFT", "right": "CHEVRON_RIGHT", "refresh": "REFRESH", "logout": "LOGOUT", "book": "MENU_BOOK",
    "calendar": "CALENDAR_MONTH", "school": "SCHOOL", "bell": "NOTIFICATIONS", "person": "PERSON", "send": "SEND",
    "close": "CLOSE", "check": "CHECK", "home": "HOME", "settings": "SETTINGS", "chart": "BAR_CHART",
    "table": "TABLE_CHART", "search": "SEARCH", "more": "MORE_HORIZ",
}


def _icon(name: str | None) -> Any:
    return getattr(ft.Icons, _ICONS.get(name or "", ""), None) if name else None


class FletBackend(Backend):
    name = "flet"

    def __init__(self, setup: Callable[[Any], None] | None = None, **run_kwargs: Any) -> None:
        super().__init__()
        self.page: Any = None
        self.setup = setup            # хук: підключити сервіси сторінки (SecureStorage тощо)
        self.run_kwargs = run_kwargs  # напр. view=ft.AppView.WEB_BROWSER
        self._pending: list[Callable[[], None]] = []
        self._root: Widget | None = None   # останній змонтований корінь (для перемальовування при зміні розміру)
        self._inner_w: int | None = None
        self._dialog_shown = False
        self._last_key: str | None = None

    @property
    def theme(self) -> Theme:
        return self.app.theme  # type: ignore[union-attr]

    # ───── життєвий цикл ─────
    def run(self, app) -> None:
        self.app = app

        async def main(page: Any) -> None:
            self.page = page
            page.title = app.title
            page.padding = 0
            try:  # на комп'ютері не даємо вікну стати вужчим за телефон
                page.window.min_width, page.window.min_height = 340, 480
            except Exception:  # noqa: BLE001
                pass
            app.system_dark = page.platform_brightness == ft.Brightness.DARK
            if page.width:
                app.width, app.height = int(page.width), int(page.height or app.height)
            page.on_resize = self._on_resize
            page.on_platform_brightness_change = lambda e: app.set_system_dark(
                page.platform_brightness == ft.Brightness.DARK)
            page.on_keyboard_event = self._on_key
            self._apply_theme()
            if self.setup:
                self.setup(page)
            page.update()
            for fn in self._pending:
                self.call_soon(fn)
            self._pending.clear()
            app._ready()

        ft.run(main, **self.run_kwargs)

    def _on_resize(self, e: Any) -> None:
        """Зміна розміру/повертання екрана: оновлюємо адаптивну розкладку (і ширину колонки з max_width)."""
        w, h = int(getattr(e, "width", 0) or self.page.width or 0), int(getattr(e, "height", 0) or self.page.height or 0)
        if not w:
            return
        app = self.app
        app.set_size(w, h)  # type: ignore[union-attr]
        root = self._root
        if root is not None and root.max_width and self._inner_w != self._column_width(root):
            self.mount(root)  # межа колонки змінилась — перемалювати без перебудови стану

    def _on_key(self, e: Any) -> None:
        if getattr(e, "key", "") in ("Escape", "Go Back", "Browser Back"):
            self.app.back()  # type: ignore[union-attr]

    def _apply_theme(self) -> None:
        p = self.theme.palette
        self.page.theme = ft.Theme(color_scheme_seed=p["ink"], use_material3=True)
        self.page.theme_mode = ft.ThemeMode.DARK if self.theme.dark else ft.ThemeMode.LIGHT
        self.page.bgcolor = p["bg"]

    def _fs(self, size: float) -> int:
        """Розмір шрифту рідних контролів Flet з урахуванням масштабу тексту з теми."""
        return max(9, round(size * self.theme.font_scale))

    def quit(self) -> None:
        if self.page is not None:
            self.page.run_task(self._close)

    async def _close(self) -> None:
        await self.page.window.close()

    def call_soon(self, fn: Callable[[], None]) -> None:
        if self.page is None:
            self._pending.append(fn)
            return

        async def runner() -> None:
            fn()

        self.page.run_task(runner)

    def spawn(self, coro, done, fail) -> None:
        async def runner() -> None:
            try:
                res = await coro
            except BaseException as e:  # noqa: BLE001
                fail(e)
                return
            done(res)

        if self.page is None:
            self._pending.append(lambda: self.page.run_task(runner))
        else:
            self.page.run_task(runner)

    # ───── допоміжне ─────
    def _c(self, key: str | None, default: str | None = None) -> str | None:
        return self.theme.color(key) if key else default

    def _h(self, fn: Callable[..., Any] | None, *args: Any) -> Callable[[Any], None]:
        return lambda e: self.app.dispatch(fn, *args)  # type: ignore[union-attr]

    @staticmethod
    def _pad(st: Style) -> Any:
        t, r, b, l = st.pad()
        return ft.Padding.only(left=l, top=t, right=r, bottom=b) if (t or r or b or l) else None

    @staticmethod
    def _mar(st: Style) -> Any:
        t, r, b, l = st.mar()
        return ft.Margin.only(left=l, top=t, right=r, bottom=b) if (t or r or b or l) else None

    def _border(self, st: Style) -> Any:
        if st.border_left:
            return ft.Border(left=ft.BorderSide(4, self._c(st.border_left)))
        if st.border and st.border_width:
            side = ft.BorderSide(st.border_width, self._c(st.border))
            return ft.Border(left=side, top=side, right=side, bottom=side)
        return None

    def _shadow(self, level: int | None) -> Any:
        """М'яка тінь за рівнем 1–4 (на темних темах тіней немає — там їх задає тема нулем)."""
        if not level or level < 1:
            return None
        return ft.BoxShadow(blur_radius=6 + 6 * level, spread_radius=0, color="#26000000",
                            offset=ft.Offset(0, 2 * level))

    def _gradient(self, pair: Any) -> Any:
        if not pair or len(pair) < 2:
            return None
        return ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                 colors=[self._c(pair[0]), self._c(pair[1])])

    def _deco(self, control: Any, st: Style, *, padding: bool = True, on_click: Callable | None = None,
              bg: bool = True, center: bool = False) -> Any:
        """Загортає контрол у Container, якщо стиль має тло, рамку, відступи, розмір чи обробник кліку."""
        pad = self._pad(st) if padding else None
        mar = self._mar(st)
        border = self._border(st)
        needs = any([bg and st.bg, st.radius, border, pad, mar, st.width, st.height, on_click, st.shadow,
                     st.gradient])
        if not needs:
            if st.expand:
                control.expand = True
            return control
        return ft.Container(content=control, bgcolor=self._c(st.bg) if bg and st.bg else None,
                            shadow=self._shadow(st.shadow), gradient=self._gradient(st.gradient),
                            border_radius=st.radius or None, padding=pad, margin=mar, border=border,
                            width=st.width, height=st.height if (st.height and st.height < 4000) else None,
                            on_click=on_click, ink=bool(on_click), expand=bool(st.expand) or None,
                            alignment=ft.Alignment.CENTER if center else None)

    # ───── малювання ─────
    def _rail_w(self, root: Screen) -> int:
        return 88 if (root.nav and root.nav.rail) else 0

    def _column_width(self, root: Screen) -> int | None:
        """Ширина центральної колонки на широких екранах (`Screen.max_width`), але не більша за доступну."""
        if not root.max_width:
            return None
        return int(max(280, min(root.max_width, self.app.width - self._rail_w(root))))  # type: ignore[union-attr]

    def mount(self, root: Widget) -> None:
        page = self.page
        self._apply_theme()
        self._root = root  # type: ignore[assignment]
        st = self.theme.resolve("screen", root.cls, root.style)
        body = self._r(root.body)
        column: Any = ft.Column([body], expand=True, spacing=0,
                                scroll=ft.ScrollMode.AUTO if root.scroll else None,
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        if root.on_swipe:
            handler = root.on_swipe

            def swiped(e: Any) -> None:
                v = float(getattr(e, "primary_velocity", 0) or 0)
                if abs(v) > 350:   # швидкий горизонтальний жест
                    self.app.dispatch(handler, "right" if v > 0 else "left")  # type: ignore[union-attr]

            column = ft.GestureDetector(content=column, on_horizontal_drag_end=swiped, expand=True)
        t, r, b, l = st.pad()
        content: Any = ft.Container(column, padding=ft.Padding.only(left=l, top=t, right=r, bottom=b), expand=True)
        self._inner_w = self._column_width(root)  # type: ignore[arg-type]
        if self._inner_w:
            content = ft.Container(ft.Container(content, width=self._inner_w), alignment=ft.Alignment.TOP_CENTER,
                                   expand=True)
        page.controls.clear()
        nav = root.nav  # type: ignore[attr-defined]
        if nav is not None and nav.rail:
            page.navigation_bar = None
            content = ft.Row([self._rail(nav), ft.VerticalDivider(width=1), content], expand=True, spacing=0)
        else:
            page.navigation_bar = self._navbar(nav) if nav else None
        key = getattr(root, "key", "")
        fade = bool(self.app.animations and key and key != self._last_key and self._last_key is not None)  # type: ignore[union-attr]
        self._last_key = key
        if fade:   # м'яка поява нового екрана: прозорість 0 → 1 і легкий зсув угору
            content = ft.Container(content, expand=True, opacity=0, offset=ft.Offset(0, 0.015),
                                   animate_opacity=ft.Animation(260, ft.AnimationCurve.EASE_OUT),
                                   animate_offset=ft.Animation(260, ft.AnimationCurve.EASE_OUT))
        page.add(ft.SafeArea(content=content, expand=True))
        page.update()
        if fade:
            content.opacity, content.offset = 1, ft.Offset(0, 0)
            page.update()

    def _r(self, w: Widget) -> Any:
        th = self.theme
        st = th.resolve(w.kind, w.cls, w.style)
        if isinstance(w, (Row, Column, Card)):
            return self._container(w, st)
        if isinstance(w, Text):
            txt = ft.Text(w.text, size=st.font_size, color=self._c(st.color), selectable=w.selectable or None,
                          weight=ft.FontWeight.BOLD if st.bold else None, italic=bool(st.italic) or None,
                          text_align={"center": ft.TextAlign.CENTER, "end": ft.TextAlign.RIGHT}.get(st.text_align or ""))
            return self._deco(txt, st, on_click=self._h(w.on_click) if w.on_click else None,
                              center=(st.text_align == "center" and bool(st.width or st.height)))
        if isinstance(w, Button):
            return self._button(w, st)
        if isinstance(w, Chip):
            label = ft.Text(w.text, color=self._c(st.color, "#FFFFFF"), weight=ft.FontWeight.BOLD, size=st.font_size)
            return ft.Container(label, bgcolor=self._c(w.color) or self._c(st.bg), border_radius=st.radius,
                                tooltip=w.tooltip, padding=self._pad(st))
        if isinstance(w, Input):
            return self._input(w, st)
        if isinstance(w, Switch):
            return self._switch(w)
        if isinstance(w, Dropdown):
            return self._dropdown(w, st)
        if isinstance(w, Slider):
            return self._slider(w)
        if isinstance(w, Progress):
            return ft.ProgressRing() if w.value is None else ft.ProgressBar(value=w.value)
        if isinstance(w, Divider):
            return ft.Divider(height=1)
        if isinstance(w, Spacer):
            return ft.Container(width=st.width, height=st.height, expand=bool(st.expand) or None)
        if isinstance(w, Image):
            if w.svg:
                return ft.Image(src=w.svg.encode("utf-8"), fit=ft.BoxFit.CONTAIN, height=st.height)
            return ft.Image(src=w.path or "", fit=ft.BoxFit.CONTAIN, height=st.height)
        if isinstance(w, Chart):
            height = st.height or 260
            img = ft.Image(src=w.svg(th).encode("utf-8"), fit=ft.BoxFit.CONTAIN, height=height)
            return ft.Container(img, bgcolor=self._c(st.bg), border_radius=st.radius, padding=self._pad(st),
                                margin=self._mar(st))
        if isinstance(w, Table):
            return self._table(w, st)
        if isinstance(w, NavBar):
            return self._navbar(w)
        return ft.Text(repr(w))

    # — контейнери —
    _MAIN = {"start": ft.MainAxisAlignment.START, "center": ft.MainAxisAlignment.CENTER,
             "end": ft.MainAxisAlignment.END, "between": ft.MainAxisAlignment.SPACE_BETWEEN}
    _CROSS = {"start": ft.CrossAxisAlignment.START, "center": ft.CrossAxisAlignment.CENTER,
              "end": ft.CrossAxisAlignment.END, "stretch": ft.CrossAxisAlignment.STRETCH}

    def _container(self, w: Widget, st: Style) -> Any:
        kids = [self._r(c) for c in w.children]
        main = self._MAIN.get(st.justify or "start")
        if isinstance(w, Row):
            ctrl: Any = ft.Row(kids, spacing=st.gap or 0, wrap=bool(st.wrap), alignment=main,
                               vertical_alignment=self._CROSS.get(st.align or "center"))
        else:
            ctrl = ft.Column(kids, spacing=st.gap or 0, alignment=main,
                             horizontal_alignment=self._CROSS.get(st.align or "stretch"),
                             scroll=ft.ScrollMode.AUTO if getattr(w, "scroll", False) else None,
                             tight=not st.expand, expand=bool(st.expand) or None)
        click = self._h(w.on_click) if isinstance(w, Card) and w.on_click else None
        return self._deco(ctrl, st, on_click=click)

    # — прості віджети —
    def _button(self, w: Button, st: Style) -> Any:
        handler = self._h(w.on_click)
        if not w.text and w.icon:
            return ft.IconButton(_icon(w.icon), on_click=handler, tooltip=w.tooltip, disabled=w.disabled,
                                 icon_size=self._fs(24))
        style = ft.ButtonStyle(text_style=ft.TextStyle(size=self._fs(14)),
                               padding=ft.Padding.symmetric(horizontal=8 if st.expand else 16,
                                                            vertical=max(8, round(10 * self.theme.space_scale))),
                               shape=ft.RoundedRectangleBorder(radius=st.radius if st.radius is not None else 10))
        kw: dict[str, Any] = dict(content=w.text, on_click=handler, disabled=w.disabled, style=style)
        if w.variant == "primary":
            ctrl: Any = ft.FilledButton(**kw)
        elif w.variant == "text":
            ctrl = ft.TextButton(**kw)
        else:
            icon = _icon(w.icon)
            if icon is not None:
                kw["icon"] = icon
            ctrl = ft.OutlinedButton(**kw)
        if st.expand:
            ctrl.expand = True
        return ctrl

    def _input(self, w: Input, st: Style) -> Any:
        app = self.app
        assert app is not None
        value = str(app.values.get(w.name, w.value)) if w.name else w.value
        if w.name:
            app.values[w.name] = value

        def changed(e: Any) -> None:
            v = e.control.value
            if w.name:
                app.values[w.name] = v
            app.dispatch(w.on_change, v)

        tf = ft.TextField(label=w.label or None, value=value, password=w.password,
                          can_reveal_password=w.password or None, multiline=w.multiline,
                          min_lines=w.lines if w.multiline else None, disabled=w.disabled,
                          autofocus=w.autofocus or None, border_radius=st.radius or 10, on_change=changed,
                          text_size=self._fs(15))
        if st.expand:
            tf.expand = True
        if w.on_submit:
            tf.on_submit = lambda e: app.dispatch(w.on_submit, e.control.value)
        return tf

    def _switch(self, w: Switch) -> Any:
        app = self.app
        assert app is not None
        val = bool(app.values.get(w.name, w.value)) if w.name else w.value
        if w.name:
            app.values[w.name] = val

        def toggled(e: Any) -> None:
            if w.name:
                app.values[w.name] = bool(e.control.value)
            app.dispatch(w.on_change, bool(e.control.value))

        return ft.Switch(label=ft.Text(w.label, size=self._fs(14)) if w.label else None, value=val,
                         on_change=toggled)

    def _dropdown(self, w: Dropdown, st: Style) -> Any:
        app = self.app
        assert app is not None
        cur = app.values.get(w.name, w.value) if w.name else w.value
        if w.name:
            app.values[w.name] = cur

        def picked(e: Any) -> None:
            if w.name:
                app.values[w.name] = e.control.value
            app.dispatch(w.on_change, e.control.value)

        dd = ft.Dropdown(label=w.label or None, value=cur, on_select=picked, text_size=self._fs(14),
                         border_radius=st.radius or 10,
                         options=[ft.DropdownOption(key=k, text=t) for k, t in w.options])
        if st.expand:
            dd.expand = True
        return dd

    def _slider(self, w: Slider) -> Any:
        app = self.app
        assert app is not None
        cur = app.values.get(w.name, w.value) if w.name else w.value
        if w.name:
            app.values[w.name] = cur

        def committed(e: Any) -> None:
            v = float(e.control.value)
            if w.name:
                app.values[w.name] = v
            app.dispatch(w.on_change, v)

        sl = ft.Slider(min=w.min, max=w.max, divisions=max(1, int(round((w.max - w.min) / w.step))), value=cur,
                       label="{value}", on_change_end=committed)
        return ft.Column([ft.Text(w.label, size=self._fs(13)), sl], spacing=0, tight=True) if w.label else sl

    def _table(self, w: Table, st: Style) -> Any:
        th = self.theme
        head_st = th.resolve("text", "table-head")
        cell_st = th.resolve("text", "table-cell")
        zebra_bg = self._c(th.resolve("text", "table-zebra").bg)
        align = {"start": ft.MainAxisAlignment.START, "center": ft.MainAxisAlignment.CENTER,
                 "end": ft.MainAxisAlignment.END}

        def cell(content: Any, cst: Style, col, bg: str | None) -> Any:
            inner = self._r(content) if isinstance(content, Widget) else ft.Text(
                str(content), size=cst.font_size, color=self._c(cst.color),
                weight=ft.FontWeight.BOLD if cst.bold else None,
                text_align={"center": ft.TextAlign.CENTER, "end": ft.TextAlign.RIGHT}.get(col.align))
            holder = ft.Row([inner], alignment=align.get(col.align, ft.MainAxisAlignment.START), wrap=False)
            return ft.Container(holder, padding=self._pad(cst), bgcolor=bg,
                                width=round(col.width * th.font_scale) if col.width else None,
                                expand=None if col.width else col.flex)

        rows: list[Any] = []
        if w.header:
            rows.append(ft.Row([cell(c.title, head_st, c, self._c(head_st.bg)) for c in w.columns], spacing=0))
        for ri, row in enumerate(w.rows):
            rbg = zebra_bg if (w.zebra and ri % 2) else None
            cells = []
            for ci, col in enumerate(w.columns):
                c: Cell = w.cell(row[ci] if ci < len(row) else "")
                cst = cell_st.merge(th.resolve("text", c.cls), c.style)
                cc = cell(c.widget if c.widget else ("" if c.text is None else c.text), cst, col,
                          self._c(c.style.bg) or rbg)
                if c.on_click:
                    cc.on_click, cc.ink = self._h(c.on_click), True
                cells.append(cc)
            line: Any = ft.Row(cells, spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            if w.on_row_click:
                line = ft.Container(line, on_click=self._h(w.on_row_click, ri), ink=True)
            rows.append(line)
        if not w.rows:
            rows.append(ft.Container(ft.Text(w.empty, color=th.palette["muted"]), padding=16,
                                     alignment=ft.Alignment.CENTER))
        body: Any = ft.Column(rows, spacing=0, tight=True)
        root = self._root
        avail = self.app.width - 28 - (self._rail_w(root) if isinstance(root, Screen) else 0)  # type: ignore[union-attr]
        if w.min_width and avail < w.min_width * th.font_scale:   # вузький екран — таблиця прокручується вбік
            body = ft.Row([ft.Container(body, width=round(w.min_width * th.font_scale))], scroll=ft.ScrollMode.AUTO,
                          vertical_alignment=ft.CrossAxisAlignment.START)
        return ft.Container(body, bgcolor=self._c(st.bg), border_radius=st.radius, border=self._border(st),
                            margin=self._mar(st), clip_behavior=ft.ClipBehavior.ANTI_ALIAS)

    def _nav_icon(self, i: Any) -> Any:
        ic = _icon(i.icon) or ft.Icons.CIRCLE
        return ft.Icon(ic, badge=str(i.badge)) if i.badge else ic

    def _navbar(self, w: NavBar) -> Any:
        keys = [i.key for i in w.items]
        sel = keys.index(w.selected) if w.selected in keys else 0
        return ft.NavigationBar(
            destinations=[ft.NavigationBarDestination(icon=self._nav_icon(i), label=i.label) for i in w.items],
            selected_index=sel,
            on_change=lambda e: self.app.dispatch(w.on_change, keys[e.control.selected_index]))  # type: ignore[union-attr]

    def _rail(self, w: NavBar) -> Any:
        """Бокова панель для планшета/комп'ютера."""
        keys = [i.key for i in w.items]
        sel = keys.index(w.selected) if w.selected in keys else 0
        return ft.NavigationRail(
            destinations=[ft.NavigationRailDestination(icon=self._nav_icon(i), label=i.label) for i in w.items],
            selected_index=sel, label_type=ft.NavigationRailLabelType.ALL, min_width=80,
            on_change=lambda e: self.app.dispatch(w.on_change, keys[e.control.selected_index]))  # type: ignore[union-attr]

    # ───── діалоги й тости ─────
    def show_dialog(self, dialog: Dialog) -> None:
        content = None
        if dialog.content is not None:
            width = dialog.style.width or 320
            content = ft.Container(ft.Column([self._r(dialog.content)], tight=True, scroll=ft.ScrollMode.AUTO),
                                   width=min(width, max(240, self.app.width - 48)))  # type: ignore[union-attr]

        def dismissed(_e: Any = None) -> None:
            self._dialog_shown = False
            if self.app is not None and self.app.dialog is dialog:
                self.app.dialog = None

        if self._dialog_shown:   # заміна відкритого діалогу (напр. новий цільовий бал) — без нашарування
            self._dialog_shown = False
            self.page.pop_dialog()
        self._dialog_shown = True
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text(dialog.title, size=self._fs(20)), content=content, scrollable=False,
            inset_padding=ft.Padding.symmetric(horizontal=16, vertical=24),
            actions=[self._r(a) for a in dialog.actions], on_dismiss=dismissed))

    def close_dialog(self) -> None:
        self._dialog_shown = False
        self.page.pop_dialog()

    def toast(self, text: str) -> None:
        self.page.show_dialog(ft.SnackBar(content=ft.Text(text)))
