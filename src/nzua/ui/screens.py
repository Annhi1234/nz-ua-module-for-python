"""Готові блоки інтерфейсу для даних nzua: щоденник, таблиця оцінок, успішність, сповіщення, вхід.

Усі функції повертають звичайні віджети (див. widgets.py): їх можна вкладати в Column/Card,
міняти стилі через `cls=`/`style=` або збирати власні екрани з нуля.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Sequence

from ..models import (Grade, MissedLessons, Notification, Schedule, Student, StudentPerformance,
                      SubjectPerformance, Timetable)
from .style import Style
from .widgets import (Button, Card, Cell, Chart, Chip, Col, Column, Divider, Input, Row, Table, Text, Widget)

__all__ = (
    "DAYS", "MONTHS", "fmt_day", "fmt_time", "fmt_dt", "avg_text", "mark_key", "grade_chip", "banner", "empty",
    "week_bar", "diary_view", "timetable_view", "grades_table", "journal_table", "performance_table",
    "performance_view", "subject_view", "notifications_view", "profile_view", "login_form", "averages_chart_widget",
)

DAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "Пʼятниця", "Субота", "Неділя"]
SHORT_DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня",
          "серпня", "вересня", "жовтня", "листопада", "грудня"]


# ── форматування ──
def fmt_day(d: date | None) -> str:
    return f"{DAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}" if d else "—"


def fmt_time(t: time | None) -> str:
    return t.strftime("%H:%M") if t else ""


def fmt_dt(d: datetime | None) -> str:
    """Дата й час у місцевому часовому поясі (API віддає UTC-мітки)."""
    if d is None:
        return ""
    if d.tzinfo is not None:
        d = d.astimezone()
    return d.strftime("%d.%m.%Y %H:%M")


def avg_text(v: float | None) -> str:
    return f"{v:.1f}" if v is not None else "—"


def mark_key(value: int | None) -> str:
    """Ключ кольору палітри для оцінки (12-бальна шкала)."""
    return "muted" if value is None else "bad" if value <= 3 else "mid" if value <= 6 else "good"


def grade_chip(mark: Any, value: int | None = None, tooltip: str | None = None, **kw: Any) -> Chip:
    """Кольоровий бейдж оцінки. `value` — числове значення (якщо None, береться з тексту)."""
    text = str(mark)
    if value is None and text.strip().isdigit():
        value = int(text)
    return Chip(text, mark_key(value), tooltip=tooltip, **kw)


def banner(text: str) -> Widget:
    return Text(text, cls="banner")


def empty(text: str) -> Widget:
    return Text(text, cls="muted", style=Style(text_align="center", padding=40, font_size=15))


def _stale(res: Any) -> list[Widget]:
    return [banner("Немає зв’язку. Показано збережені дані.")] if getattr(res, "from_cache", False) else []


# ── навігація по тижнях ──
def week_bar(monday: date, *, on_prev: Callable, on_today: Callable, on_next: Callable,
             on_refresh: Callable | None = None) -> Widget:
    sunday = monday + timedelta(days=6)
    label = f"{monday.day} {MONTHS[monday.month - 1]} – {sunday.day} {MONTHS[sunday.month - 1]}"
    items: list[Widget] = [Button("", on_prev, icon="left", variant="text", id="week-prev"),
                           Button(label, on_today, variant="text", id="week-today"),
                           Button("", on_next, icon="right", variant="text", id="week-next")]
    if on_refresh:
        items.append(Button("", on_refresh, icon="refresh", variant="text", id="refresh"))
    return Row(items, justify="center", gap=2)


# ── щоденник і розклад ──
def _lesson_head(number: int | None, name: str, bits: Sequence[str]) -> Widget:
    return Row([
        Text(str(number or "·"), cls="h3", style=Style(width=28, text_align="center")),
        Column([Text(name, cls="title"), Text(", ".join(b for b in bits if b), cls="muted")], gap=1, expand=True)],
        align="start", gap=6)


def _bits(les, sub) -> list[str]:
    return [f"{fmt_time(les.start)}–{fmt_time(les.end)}" if les.start else "",
            f"каб. {sub.room}" if sub.room else "", sub.teacher.name if sub.teacher else ""]


def diary_view(s: Schedule, on_hometask: Callable[[int, str], Any] | None = None) -> list[Widget]:
    """Щоденник: картка на кожен день, уроки з оцінками й домашніми завданнями."""
    out = _stale(s)
    for day in s.days:
        rows: list[Widget] = [Text(fmt_day(day.date), cls="h3")]
        for les in day.lessons:
            for sub in les.subjects:
                rows.append(_lesson_head(les.number, sub.name, _bits(les, sub)))
                if sub.grades:
                    rows.append(Row([grade_chip(g.mark, g.value, g.comment or g.type) for g in sub.grades],
                                    wrap=True, gap=6, padding=(0, 0, 0, 34)))
                if sub.homework or sub.hometask_id:
                    hw = "Д/з: " + " ".join(sub.homework) if sub.homework else "Дистанційне завдання"
                    tap = (lambda i=sub.hometask_id, n=sub.name: on_hometask(i, n)) if (sub.hometask_id and on_hometask) else None
                    rows.append(Text(hw, cls="small", on_click=tap, style=Style(
                        padding=(0, 0, 0, 34), color="ink" if tap else None)))
        out.append(Card(rows, gap=8))
    return out or [empty("На цей тиждень записів немає.")]


def timetable_view(t: Timetable) -> list[Widget]:
    out = _stale(t)
    for day in t.days:
        rows: list[Widget] = [Text(fmt_day(day.date), cls="h3")]
        for les in day.lessons:
            for sub in les.subjects:
                rows.append(_lesson_head(les.number, sub.name, _bits(les, sub)))
        out.append(Card(rows, gap=8))
    return out or [empty("Розкладу на цей тиждень немає.")]


# ── таблиці оцінок ──
def grades_table(s: Schedule, subject: str | None = None, **kw: Any) -> Table:
    """Плоска таблиця «дата · предмет · оцінка · тип»; підсвічує оцінки кольором.

        grades_table(schedule, zebra=True, on_row_click=…, style=Style(radius=0))
    """
    rows = []
    for d, name, g in s.grades():
        if subject and subject.lower() not in name.lower():
            continue
        rows.append([f"{d.day:02d}.{d.month:02d}" if d else "", name, grade_chip(g.mark, g.value), g.type, g.comment or ""])
    return Table([Col("Дата", width=64), Col("Предмет", flex=3), Col("Бал", width=56, align="center"),
                  Col("Тип", flex=2), Col("Коментар", flex=2)],
                 rows, empty="Оцінок за цей період немає.", **kw)


def journal_table(s: Schedule, **kw: Any) -> Table:
    """Журнал: предмети по рядках, дні по колонках; у кожній клітинці оцінки за той день."""
    days = [d for d in s.days if d.date]
    subjects: dict[str, dict[date, list[Grade]]] = {}
    for d, name, g in s.grades():
        if d:
            subjects.setdefault(name, {}).setdefault(d, []).append(g)
    cols = [Col("Предмет", flex=3)] + [Col(f"{SHORT_DAYS[d.date.weekday()]} {d.date.day}", width=58, align="center")
                                       for d in days]
    rows = []
    for name, by_day in sorted(subjects.items()):
        cells: list[Any] = [name]
        for d in days:
            gs = by_day.get(d.date, [])
            cells.append(Row([grade_chip(g.mark, g.value) for g in gs], gap=3, justify="center", wrap=True)
                         if gs else Cell(""))
        rows.append(cells)
    return Table(cols, rows, empty="Оцінок за цей період немає.", **kw)


def performance_table(p: StudentPerformance, on_subject: Callable[[int, str], Any] | None = None, **kw: Any) -> Table:
    """Успішність: предмет, усі оцінки бейджами, середній бал."""
    rows = []
    for sub in p.subjects:
        avg = sub.average
        rows.append([sub.name,
                     Row([grade_chip(m.mark, m.value, m.type) for m in sub.marks], wrap=True, gap=4),
                     Cell(avg_text(avg), color=mark_key(round(avg) if avg else None), bold=True, text_align="center")])
    handler = (lambda i: on_subject(p.subjects[i].id, p.subjects[i].name)) if on_subject else None
    return Table([Col("Предмет", flex=3), Col("Оцінки", flex=4), Col("Серед.", width=64, align="center")],
                 rows, on_row_click=handler, empty="Даних про успішність немає.", **kw)


def averages_chart_widget(p: StudentPerformance, colors: str = "scale", height: int = 260,
                          show_values: bool = True) -> Widget | None:
    subs = [s for s in p.subjects if s.average is not None]
    if not subs:
        return None
    return Chart([s.short_name or s.name for s in subs], [s.average for s in subs], colors=colors,
                 show_values=show_values, height=height, cls="chart", id="averages-chart")


def performance_view(p: StudentPerformance, missed: MissedLessons | None = None,
                     on_subject: Callable[[int, str], Any] | None = None, chart: Widget | None = None,
                     as_table: bool = True) -> list[Widget]:
    out = _stale(p)
    avg = p.average
    out.append(Card([Row([
        Text(avg_text(avg), cls="big", style=Style(color=mark_key(round(avg)) if avg else "muted")),
        Column([Text("Середній бал", cls="title"),
                Text(f"Пропущено днів: {p.missed_days}, уроків: {p.missed_lessons}", cls="muted")], gap=2)],
        gap=16)]))
    if chart is not None:
        out.append(chart)
    if as_table:
        out.append(performance_table(p, on_subject, id="performance-table", margin=(0, 0, 10, 0)))
    else:
        for sub in p.subjects:
            head = Row([Text(sub.name, cls="title", expand=True), Text(avg_text(sub.average), cls="h3")])
            body = [head] + ([Row([grade_chip(m.mark, m.value, m.type) for m in sub.marks], wrap=True, gap=6)] if sub.marks else [])
            out.append(Card(body, on_click=(lambda i=sub.id, n=sub.name: on_subject(i, n)) if on_subject else None))
    if missed and len(missed):
        out.append(Text("Пропущені уроки", cls="h3"))
        out.append(Card([Text(f"{fmt_day(x.date)}: {x.subject}", cls="small") for x in missed.lessons], gap=4))
    return out


def subject_view(sp: SubjectPerformance) -> Widget:
    rows: list[Widget] = [Text(f"Середній бал: {avg_text(sp.average)}, пропущено уроків: {sp.missed_lessons}", cls="muted")]
    for x in sp.lessons:
        rows.append(Row([Text(f"{x.date.day:02d}.{x.date.month:02d}" if x.date else "", cls="small", width=44),
                         grade_chip(x.mark, x.value), Text(x.comment or x.type, cls="muted", expand=True)], gap=8))
    return Column(rows, gap=8, scroll=True, height=380)


# ── решта екранів ──
def notifications_view(items: Sequence[Notification], unread: int = 0) -> list[Widget]:
    if not items:
        return [empty("Сповіщень поки немає.")]
    out: list[Widget] = [Text(f"Непрочитаних: {unread}", cls="muted")]
    for n in items:
        row: list[Widget] = [Column([Text(n.body, cls="title", style=Style(font_size=14)),
                                     Text(fmt_dt(n.sent_at), cls="muted")], gap=2, expand=True)]
        if n.mark:
            row.append(grade_chip(n.mark))
        out.append(Card([Row(row, gap=8)]))
    return out


def profile_view(st: Student | None, api_ok: bool, on_logout: Callable | None = None,
                 extra: Sequence[Widget] = ()) -> list[Widget]:
    lines = [x for x in [f"Клас: {st.class_name}" if st and st.class_name else "",
                         f"Класний керівник: {st.class_manager}" if st and st.class_manager else ""] if x]
    out: list[Widget] = [
        Card([Text(st.full_name if st else "Учень", cls="h2"), *[Text(x) for x in lines]], gap=4),
        Card([Text("Сервер nz.ua працює" if api_ok else "Сервер nz.ua не відповідає", cls="good" if api_ok else "bad")]),
    ]
    if extra:
        out.append(Card(list(extra), gap=10))
    if on_logout:
        out.append(Button("Вийти з акаунта", on_logout, icon="logout", variant="outline", id="logout"))
    return out


def login_form(app: Any, on_submit: Callable[[str, str], Any], message: str = "", busy: bool = False) -> Widget:
    """Екран входу. Значення полів зберігаються в `app.values["username"]` / `["password"]`."""
    def submit(*_: Any) -> Any:
        return on_submit(str(app.value("username")).strip(), str(app.value("password")))

    return Column([
        Text("Щоденник", cls="h1"),
        Text("Увійдіть у свій акаунт nz.ua", cls="muted", style=Style(font_size=15)),
        Text("", height=12),
        Input("username", "Логін", id="username", autofocus=True),
        Input("password", "Пароль", password=True, id="password", on_submit=submit),
        Text(message, cls="error", id="login-error"),
        Button("Вхід…" if busy else "Увійти", submit, variant="primary", disabled=busy, id="login"),
    ], gap=10, padding=24, justify="center", expand=True)
