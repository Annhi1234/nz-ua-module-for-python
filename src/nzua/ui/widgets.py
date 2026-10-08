"""Декларативні віджети. Це лише опис (дерево); малюють його бекенди Tkinter / PyQt5 / Flet / HTML.

    Column([
        Text("Оцінки", cls="h2"),
        Table(["Предмет", "Бал"], [["Алгебра", Chip("11")], ["Фізика", Chip("8")]]),
        Button("Оновити", on_click=lambda: print("клік"), kind="primary"),
    ], gap=8, padding=16)

Обробники подій — звичайні функції без аргументів (для Input/Switch/Dropdown/Slider — з одним:
новим значенням). Обробник може бути й `async def`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Sequence

from .style import Style, box  # noqa: F401

__all__ = (
    "Widget", "Text", "Button", "Chip", "Input", "Switch", "Dropdown", "Slider", "Progress",
    "Divider", "Spacer", "Image", "Row", "Column", "Card", "Table", "Col", "Cell", "Chart",
    "NavBar", "NavItem", "Screen", "Dialog", "ICONS",
)

Callback = Callable[..., Any]

# Назви значків → символи (лише з BMP, щоб працювало в старих Tk); Flet бере власні значки.
ICONS: dict[str, str] = {
    "book": "✎", "calendar": "▦", "school": "★", "bell": "✉", "person": "☺", "refresh": "↻",
    "logout": "⎋", "left": "‹", "right": "›", "send": "➤", "close": "✕", "check": "✓", "home": "⌂",
    "settings": "⚙", "chart": "▮", "table": "▦", "search": "⌕", "more": "☰",
}


class Widget:
    """Базовий клас. `style` — Style або dict; `cls` — імена класів теми через пробіл; `id` — для пошуку."""
    kind = "widget"

    def __init__(self, *, style: Style | dict | None = None, cls: str = "", id: str | None = None,
                 width: int | None = None, height: int | None = None, expand: bool | None = None,
                 padding: Any = None, margin: Any = None, **style_kw: Any) -> None:
        # Зручність: Row(gap=8, padding=12, bg="#fff") без окремого Style(...)
        extra = {k: v for k, v in dict(width=width, height=height, expand=expand,
                                       padding=padding, margin=margin, **style_kw).items() if v is not None}
        base = style if isinstance(style, Style) else Style(**style) if isinstance(style, dict) else Style()
        self.style = base.merge(Style(**extra)) if extra else base
        self.cls, self.id = cls, id

    @property
    def children(self) -> list["Widget"]:
        return []

    def walk(self) -> Iterator["Widget"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def find(self, id: str) -> "Widget | None":
        return next((w for w in self.walk() if w.id == id), None)

    def __repr__(self) -> str:
        return f"<{type(self).__name__}{' #' + self.id if self.id else ''}>"


def _kids(items: Sequence[Any] | Any) -> list[Widget]:
    if isinstance(items, Widget):
        return [items]
    return [Text(i) if isinstance(i, str) else i for i in (items or []) if i is not None]


class _Container(Widget):
    def __init__(self, children: Sequence[Widget | str | None] | Widget = (), *,
                 gap: int | None = None, scroll: bool = False, align: str | None = None,
                 justify: str | None = None, wrap: bool | None = None, **kw: Any) -> None:
        super().__init__(gap=gap, align=align, justify=justify, wrap=wrap, **kw)
        self._children = _kids(children)
        self.scroll = scroll

    @property
    def children(self) -> list[Widget]:
        return self._children

    def add(self, *items: Widget | str) -> "_Container":
        self._children.extend(_kids(list(items)))
        return self


class Column(_Container):
    """Діти зверху вниз. `scroll=True` — прокрутка. `align`: start|center|end|stretch (типово stretch)."""
    kind = "column"


class Row(_Container):
    """Діти зліва направо. `wrap=True` — переносити на новий рядок (стрічка оцінок)."""
    kind = "row"


class Card(_Container):
    """Картка з тлом, заокругленням і кольоровою смужкою зліва (стиль «поле зошита»)."""
    kind = "card"

    def __init__(self, children: Sequence[Widget | str | None] | Widget = (), *, on_click: Callback | None = None,
                 gap: int | None = 8, **kw: Any) -> None:
        super().__init__(children, gap=gap, **kw)
        self.on_click = on_click


class Text(Widget):
    kind = "text"

    def __init__(self, text: Any = "", *, selectable: bool = False, on_click: Callback | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.text, self.selectable, self.on_click = str(text), selectable, on_click


class Button(Widget):
    """kind="primary" (залита) | "outline" | "text" | "default"; `icon` — назва з ICONS."""
    kind = "button"

    def __init__(self, text: str = "", on_click: Callback | None = None, *, variant: str = "default",
                 icon: str | None = None, disabled: bool = False, tooltip: str | None = None, **kw: Any) -> None:
        kw["cls"] = (kw.get("cls", "") + ("" if variant == "default" else f" {variant}")).strip()
        super().__init__(**kw)
        self.text, self.on_click, self.variant = text, on_click, variant
        self.icon, self.disabled, self.tooltip = icon, disabled, tooltip


class Chip(Widget):
    """Кольоровий «бейдж» (оцінка). `color` — колір тла: hex або ключ палітри (good/mid/bad/ink)."""
    kind = "chip"

    def __init__(self, text: Any = "", color: str | None = None, *, tooltip: str | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.text, self.color, self.tooltip = str(text), color, tooltip


class Input(Widget):
    """Поле вводу. `name` — ключ у `app.values`; значення переживає перемальовування."""
    kind = "input"

    def __init__(self, name: str = "", label: str = "", value: str = "", *, password: bool = False,
                 multiline: bool = False, lines: int = 3, disabled: bool = False,
                 on_change: Callback | None = None, on_submit: Callback | None = None,
                 autofocus: bool = False, **kw: Any) -> None:
        super().__init__(**kw)
        self.name, self.label, self.value = name, label, value
        self.password, self.multiline, self.lines, self.disabled = password, multiline, lines, disabled
        self.on_change, self.on_submit, self.autofocus = on_change, on_submit, autofocus


class Switch(Widget):
    kind = "switch"

    def __init__(self, name: str = "", label: str = "", value: bool = False, *,
                 on_change: Callback | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.name, self.label, self.value, self.on_change = name, label, bool(value), on_change


class Dropdown(Widget):
    """`options`: список (ключ, підпис) або просто рядків."""
    kind = "dropdown"

    def __init__(self, name: str = "", label: str = "", options: Sequence[Any] = (), value: str | None = None, *,
                 on_change: Callback | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.name, self.label, self.value, self.on_change = name, label, value, on_change
        self.options: list[tuple[str, str]] = [
            (str(o[0]), str(o[1])) if isinstance(o, (tuple, list)) else (str(o), str(o)) for o in options]


class Slider(Widget):
    kind = "slider"

    def __init__(self, name: str = "", label: str = "", min: float = 0, max: float = 100, value: float = 0, *,
                 step: float = 1, on_change: Callback | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.name, self.label, self.min, self.max, self.value = name, label, min, max, value
        self.step, self.on_change = step, on_change


class Progress(Widget):
    """value=None — індикатор «завантаження» без відсотків; інакше 0..1."""
    kind = "progress"

    def __init__(self, value: float | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.value = value


class Divider(Widget):
    kind = "divider"


class Spacer(Widget):
    """Порожнє місце: Spacer(12) — фіксоване, Spacer() — розтягується (expand)."""
    kind = "spacer"

    def __init__(self, size: int | None = None, **kw: Any) -> None:
        super().__init__(**({"expand": True} if size is None else {"height": size, "width": size}), **kw)


class Image(Widget):
    """SVG-розмітка або шлях до файлу PNG/JPG (`svg=` чи `path=`)."""
    kind = "image"

    def __init__(self, svg: str | None = None, path: str | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.svg, self.path = svg, path


# ───────────────────────── таблиця ─────────────────────────
@dataclass
class Col:
    """Колонка таблиці. `width` — пікселі; без неї колонка бере частку `flex` вільного місця."""
    title: str = ""
    width: int | None = None
    flex: int = 1
    align: str = "start"  # start | center | end


class Cell:
    """Комірка з власним стилем: Cell("Н", color="bad", bold=True, on_click=…). Може містити віджет."""

    def __init__(self, text: Any = "", *, widget: Widget | None = None, style: Style | dict | None = None,
                 cls: str = "", on_click: Callback | None = None, **style_kw: Any) -> None:
        base = style if isinstance(style, Style) else Style(**style) if isinstance(style, dict) else Style()
        self.text, self.widget, self.cls, self.on_click = text, widget, cls, on_click
        self.style = base.merge(Style(**style_kw)) if style_kw else base


class Table(Widget):
    """Таблиця з різними стилями комірок. `min_width` — мінімальна ширина, щоб на телефоні таблиця не стискалась.

        Table(["Предмет", Col("Бал", width=60, align="center")],
              [["Алгебра", Cell(11, color="good", bold=True)], ["Фізика", Chip(8)]],
              on_row_click=lambda i: print("рядок", i))

    Колонки: рядки або Col. Комірка: значення, Cell, або будь-який віджет.
    """
    kind = "table"

    def __init__(self, columns: Sequence[Col | str], rows: Sequence[Sequence[Any]] = (), *,
                 zebra: bool = True, header: bool = True, empty: str = "Немає даних",
                 on_row_click: Callable[[int], Any] | None = None, min_width: int | None = None,
                 **kw: Any) -> None:
        super().__init__(**kw)
        self.columns = [c if isinstance(c, Col) else Col(str(c)) for c in columns]
        self.rows = [list(r) for r in rows]
        self.zebra, self.header, self.empty, self.on_row_click = zebra, header, empty, on_row_click
        self.min_width = min_width   # вужчий екран → таблиця прокручується вбік (Flet)

    @property
    def children(self) -> list[Widget]:
        return [c.widget if isinstance(c, Cell) else c for r in self.rows for c in r
                if isinstance(c, Widget) or (isinstance(c, Cell) and c.widget)]

    def cell(self, value: Any) -> Cell:
        """Нормалізує значення комірки до Cell."""
        if isinstance(value, Cell):
            return value
        if isinstance(value, Widget):
            return Cell(widget=value)
        return Cell("" if value is None else value)


# ───────────────────────── графік ─────────────────────────
class Chart(Widget):
    """Стовпчики або лінія. `colors`: "scale" (за оцінкою) | назва палітри | список hex."""
    kind = "chart"

    def __init__(self, labels: Sequence[str], values: Sequence[float | None], *, type: str = "bar",
                 colors: str | Sequence[str] = "scale", show_values: bool = True, title: str | None = None,
                 max_value: float = 12, color_values: Sequence[float | None] | None = None, **kw: Any) -> None:
        kw.setdefault("height", 260)
        super().__init__(**kw)
        self.labels, self.values, self.type, self.colors = list(labels), list(values), type, colors
        self.show_values, self.title, self.max_value = show_values, title, max_value
        self.color_values = list(color_values) if color_values is not None else None  # за якими числами красити «scale»

    def svg(self, theme: Any = None, width: int = 640) -> str:
        from ..charts import ChartStyle, bar_chart, line_chart
        p = theme.palette if theme else {"card": "#FFFFFF", "fg": "#1D2433", "line": "#E3E7F0"}
        colors = self.colors
        if colors == "scale" and theme is not None and self.type == "bar":  # кольори оцінок беруться з теми
            from .style import mark_color
            src = self.color_values if self.color_values is not None else self.values
            colors = [mark_color(None if v is None else round(v), theme) for v in src] or "scale"
        st = ChartStyle(width=width, height=max(120, min(self.style.height or 260, 4000)), colors=colors,
                        background=p["card"], text_color=p["fg"], grid_color=p["line"],
                        show_values=self.show_values, title=self.title, max_value=self.max_value, responsive=True)
        if self.type == "line":
            pts = [(l, v) for l, v in zip(self.labels, self.values) if v is not None]
            return line_chart([l for l, _ in pts], [v for _, v in pts], st)
        return bar_chart(self.labels, self.values, st)


# ───────────────────────── навігація, екран, діалог ─────────────────────────
@dataclass
class NavItem:
    key: str
    label: str
    icon: str = "home"
    badge: str | int | None = None   # лічильник на значку (напр. непрочитані); 0/None — без бейджа


class NavBar(Widget):
    """Панель вкладок. `items`: NavItem або (ключ, підпис, значок).

    `rail=True` — бокова панель для планшета/комп'ютера (Flet малює NavigationRail; інші бекенди — нижню панель).
    """
    kind = "navbar"

    def __init__(self, items: Sequence[NavItem | tuple], selected: str | None = None, *,
                 on_change: Callable[[str], Any] | None = None, rail: bool = False, **kw: Any) -> None:
        super().__init__(**kw)
        self.items = [i if isinstance(i, NavItem) else NavItem(*i) for i in items]
        self.selected = selected if selected is not None else (self.items[0].key if self.items else None)
        self.on_change, self.rail = on_change, rail


class Screen(Widget):
    """Корінь інтерфейсу: тіло (прокручується) + необов'язкова панель вкладок.

    `max_width` — на широких екранах тіло центрується й не розтягується далі цієї ширини;
    `on_swipe("left" | "right")` — жест пальцем по екрану (Flet); `key` — ідентифікатор «сторінки» для анімації переходу.
    """
    kind = "screen"

    def __init__(self, body: Widget | Sequence[Widget], nav: NavBar | None = None, *, scroll: bool = True,
                 title: str = "", max_width: int | None = None, on_swipe: Callable[[str], Any] | None = None,
                 key: str = "", **kw: Any) -> None:
        kw.setdefault("padding", (8, 14))
        super().__init__(**kw)
        self.body = body if isinstance(body, Widget) else Column(body)
        self.nav, self.scroll, self.title = nav, scroll, title
        self.max_width, self.on_swipe = max_width, on_swipe
        self.key = key   # зміна ключа між перемальовуваннями = «перехід» (Flet програє м'яку анімацію появи)

    @property
    def children(self) -> list[Widget]:
        return [self.body, *([self.nav] if self.nav else [])]


class Dialog(Widget):
    """Модальне вікно: `app.show_dialog(Dialog("Заголовок", content, actions=[Button("Ок", app.close_dialog)]))`."""
    kind = "dialog"

    def __init__(self, title: str = "", content: Widget | None = None, actions: Sequence[Button] = (), *,
                 width: int | None = 320, **kw: Any) -> None:
        super().__init__(width=width, **kw)
        self.title, self.content, self.actions = title, content, list(actions)

    @property
    def children(self) -> list[Widget]:
        return [*([self.content] if self.content else []), *self.actions]
