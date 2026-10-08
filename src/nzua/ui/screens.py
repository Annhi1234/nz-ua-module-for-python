"""Готові блоки інтерфейсу для даних nzua: щоденник, таблиця оцінок, успішність, сповіщення, вхід.

Усі функції повертають звичайні віджети (див. widgets.py): їх можна вкладати в Column/Card,
міняти стилі через `cls=`/`style=` або збирати власні екрани з нуля.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from collections.abc import Mapping
from typing import Any, Callable, Sequence

from ..analytics import mark_distribution, needed_marks, rank_subjects, trend
from ..models import (Grade, MissedLessons, Notification, Schedule, Student, StudentPerformance,
                      SubjectPerformance, Timetable)
from .style import NOTEBOOK as _FALLBACK, Style, Theme, subject_key
from .widgets import (Button, Card, Cell, Chart, Chip, Col, Column, Dropdown, Image, Input, Progress, Row, Table,
                      Text, Widget)

__all__ = (
    "DAYS", "MONTHS", "SHORT_DAYS", "fmt_day", "fmt_time", "fmt_dt", "avg_text", "mark_key", "grade_chip", "banner",
    "empty", "week_bar", "day_strip", "segmented", "section", "hw_key", "diary_view", "homework_view",
    "timetable_view", "grades_table", "journal_table", "performance_table", "performance_view", "summary_card",
    "filter_subjects", "trend_arrow", "subject_view", "notifications_view", "profile_view", "login_form",
    "averages_chart_widget", "distribution_chart_widget", "TARGETS", "dashboard_view", "skeleton", "gauge_svg",
    "sparkline_svg", "greeting", "first_name", "homework_text",
)

DAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "Пʼятниця", "Субота", "Неділя"]
SHORT_DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня",
          "серпня", "вересня", "жовтня", "листопада", "грудня"]


# ── форматування ──
def fmt_day(d: date | None, today: date | None = None) -> str:
    """«Середа, 7 жовтня»; якщо `d` — сьогодні (`today`), додається « · сьогодні»."""
    if not d:
        return "—"
    return f"{DAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}" + (" · сьогодні" if today and d == today else "")


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


def empty(text: str, icon: str = "") -> Widget:
    """Порожній стан: за потреби з великим емодзі-«малюнком» над текстом."""
    t = Text(text, cls="muted", style=Style(text_align="center", padding=(40 if not icon else 8, 40), font_size=15))
    if not icon:
        return t
    return Column([Text(icon, style=Style(text_align="center", font_size=44, padding=(28, 0, 0, 0))), t], gap=0)


def skeleton(n: int = 3) -> list[Widget]:
    """Заглушки-«скелети» карток на час завантаження (приємніше за крутилку)."""
    def bar(w: int, h: int = 12) -> Widget:
        return Text(" ", style=Style(bg="line", width=w, height=h, radius=h // 2))
    return [Card([bar(150, 16), bar(250), bar(190)], gap=10, id=f"skeleton-{i}") for i in range(n)]


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


def gauge_svg(value: float | None, maximum: float = 12, *, size: int = 88, color: str = "#2E7D32",
              track: str = "#DDE1EC", text: str = "#1D2433") -> str:
    """Кільцевий індикатор (наприклад, середній бал) у вигляді SVG."""
    import math
    c, r = size / 2, size / 2 - 8
    circ = 2 * math.pi * r
    frac = 0.0 if value is None else max(0.0, min(1.0, value / maximum))
    label = "—" if value is None else f"{value:.1f}".rstrip("0").rstrip(".") if value % 1 else f"{value:.0f}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{track}" stroke-width="8"/>'
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{color}" stroke-width="8" stroke-linecap="round" '
            f'stroke-dasharray="{frac * circ:.1f} {circ:.1f}" transform="rotate(-90 {c} {c})"/>'
            f'<text x="{c}" y="{c + size * 0.1}" text-anchor="middle" font-family="sans-serif" font-weight="700" '
            f'font-size="{size * 0.3:.0f}" fill="{text}">{label}</text></svg>')


def sparkline_svg(values: Sequence[float], width: int = 120, height: int = 32, color: str = "#26358F") -> str:
    """Мініграфік динаміки оцінок за шкалою 1–12 (остання точка виділена)."""
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return ""
    pad = 5
    step = (width - 2 * pad) / (len(vals) - 1)
    pts = [(pad + i * step, height - pad - (min(max(v, 1), 12) - 1) / 11 * (height - 2 * pad))
           for i, v in enumerate(vals)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" '
            f'stroke-linejoin="round"/><circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{color}"/></svg>')


def greeting(now: time | None = None) -> str:
    h = (now or datetime.now().time()).hour
    return "Доброї ночі" if h < 5 else "Доброго ранку" if h < 12 else "Доброго дня" if h < 18 else "Доброго вечора"


def first_name(full_name: str | None) -> str:
    """З «Прізвище Ім'я По батькові» бере ім'я (друге слово); для одного слова — його ж."""
    parts = (full_name or "").split()
    return parts[1] if len(parts) >= 2 else (parts[0] if parts else "")


def day_strip(monday: date, selected: date | None, on_select: Callable[[date], Any], *, today: date | None = None,
              marked: Sequence[date] = ()) -> Widget:
    """Смуга днів тижня (Пн…Нд) для телефона: торкніться дня, щоб побачити лише його. `marked` — дні з крапкою."""
    items: list[Widget] = []
    for i in range(7):
        d = monday + timedelta(days=i)
        sel = d == selected
        items.append(Card([
            Text(SHORT_DAYS[i], cls="small", color="on_ink" if sel else "muted", text_align="center"),
            Text(str(d.day), cls="title", color="on_ink" if sel else ("ink" if d == today else None),
                 text_align="center"),
            Text("●" if d in marked else " ", font_size=7, color="on_ink" if sel else "ink", text_align="center"),
        ], cls="flat", gap=0, padding=(6, 0), radius=12, bg="ink" if sel else "",
            border="ink" if (d == today and not sel) else "", border_width=1 if (d == today and not sel) else 0,
            on_click=lambda dd=d: on_select(dd), expand=True, id=f"day-{d.isoformat()}"))
    return Row(items, gap=3, align="stretch")


def segmented(options: Sequence[tuple[str, str]], selected: str, on_change: Callable[[str], Any], *,
              id_prefix: str = "seg") -> Widget:
    """Перемикач розділів у вигляді рядка кнопок: `segmented([("lessons", "Уроки"), ("hw", "Д/з")], "lessons", f)`."""
    return Row([Button(label, (lambda k=key: on_change(k)), variant="primary" if key == selected else "outline",
                       id=f"{id_prefix}-{key}", expand=True) for key, label in options], gap=6)


def section(title: str, items: Sequence[Widget | None], *, gap: int = 10) -> Widget:
    """Картка-розділ із заголовком (для налаштувань і зведень)."""
    return Card([Text(title, cls="h3"), *[i for i in items if i is not None]], gap=gap)


def hw_key(day: date | None, sub: Any) -> str:
    """Стабільний ключ домашнього завдання (для позначки «виконано»)."""
    return f"{day.isoformat() if day else '?'}|{sub.name}|{' '.join(sub.homework)}|{sub.hometask_id or ''}"[:240]


# ── щоденник і розклад ──
def _lesson_head(number: int | None, name: str, bits: Sequence[str], live: bool = False,
                 colors: bool = True) -> Widget:
    title: list[Widget] = [Text(name, cls="title")]
    if live:
        title.append(Text("● зараз", cls="small", color="ink", bold=True))
    badge = (Text(str(number or "·"), bold=True, color="on_subj", bg=subject_key(name), width=28, height=28,
                  radius=14, text_align="center") if colors else
             Text(str(number or "·"), cls="h3", style=Style(width=28, text_align="center")))
    return Row([
        badge,
        Column([Row(title, gap=8, wrap=True), Text(", ".join(b for b in bits if b), cls="muted")], gap=1, expand=True)],
        align="start", gap=6)


def _bits(les, sub, *, time_: bool = True, room: bool = True, teacher: bool = True) -> list[str]:
    return [f"{fmt_time(les.start)}–{fmt_time(les.end)}" if (time_ and les.start) else "",
            f"каб. {sub.room}" if (room and sub.room) else "",
            sub.teacher.name if (teacher and sub.teacher) else ""]


def _is_live(day_date: date | None, les, today: date | None, now: time | None) -> bool:
    return bool(today and day_date == today and now and les.start and les.end and les.start <= now <= les.end)


def _pick_days(days: Sequence[Any], day: date | None) -> list[Any]:
    return [d for d in days if d.date == day] if day else list(days)


def diary_view(s: Schedule, on_hometask: Callable[[int, str], Any] | None = None, *, day: date | None = None,
               today: date | None = None, now: time | None = None, show_time: bool = True, show_room: bool = True,
               show_teacher: bool = True, done: Any = frozenset(), colors: bool = True) -> list[Widget]:
    """Щоденник: картка на кожен день, уроки з оцінками й домашніми завданнями.

    `day` — показати лише цей день; `today`/`now` — позначка «сьогодні» й «● зараз»; `done` — ключі виконаного Д/з
    (див. `hw_key`); `show_*` — які подробиці про урок показувати.
    """
    out = _stale(s)
    for d in _pick_days(s.days, day):
        rows: list[Widget] = [Text(fmt_day(d.date, today), cls="h3")]
        for les in d.lessons:
            for sub in les.subjects:
                rows.append(_lesson_head(les.number, sub.name, _bits(les, sub, time_=show_time, room=show_room,
                                                                      teacher=show_teacher),
                                         _is_live(d.date, les, today, now), colors))
                if sub.grades:
                    rows.append(Row([grade_chip(g.mark, g.value, g.comment or g.type) for g in sub.grades],
                                    wrap=True, gap=6, padding=(0, 0, 0, 34)))
                if sub.homework or sub.hometask_id:
                    ok = hw_key(d.date, sub) in done
                    hw = ("✓ " if ok else "") + ("Д/з: " + " ".join(sub.homework) if sub.homework
                                                 else "Дистанційне завдання")
                    tap = (lambda i=sub.hometask_id, n=sub.name: on_hometask(i, n)) if (sub.hometask_id and on_hometask) else None
                    rows.append(Text(hw, cls="small", on_click=tap, style=Style(
                        padding=(0, 0, 0, 34), color="muted" if ok else ("ink" if tap else None))))
        out.append(Card(rows, gap=8))
    return out or [empty("У цей день записів немає." if day else "На цей тиждень записів немає.", "🌿")]


def timetable_view(t: Timetable, *, day: date | None = None, today: date | None = None, now: time | None = None,
                   show_time: bool = True, show_room: bool = True, show_teacher: bool = True,
                   colors: bool = True) -> list[Widget]:
    out = _stale(t)
    for d in _pick_days(t.days, day):
        rows: list[Widget] = [Text(fmt_day(d.date, today), cls="h3")]
        for les in d.lessons:
            for sub in les.subjects:
                rows.append(_lesson_head(les.number, sub.name, _bits(les, sub, time_=show_time, room=show_room,
                                                                      teacher=show_teacher),
                                         _is_live(d.date, les, today, now), colors))
        out.append(Card(rows, gap=8))
    return out or [empty("У цей день уроків немає." if day else "Розкладу на цей тиждень немає.", "🌿")]


def homework_view(s: Schedule, on_hometask: Callable[[int, str], Any] | None = None, *, done: Any = frozenset(),
                  on_toggle: Callable[[str], Any] | None = None, only_open: bool = False,
                  today: date | None = None, query: str = "", colors: bool = True) -> list[Widget]:
    """Усі домашні завдання тижня одним списком із позначками «виконано» (торкніться картки — позначка)."""
    q = (query or "").strip().lower()
    items: list[tuple[date | None, Any]] = [
        (d.date, sub) for d in s.days for les in d.lessons for sub in les.subjects
        if (sub.homework or sub.hometask_id) and (not q or q in sub.name.lower() or q in " ".join(sub.homework).lower())]
    total = len(items)
    n_done = sum(1 for d, sub in items if hw_key(d, sub) in done)
    out = _stale(s)
    if not total:
        return out + [empty("Нічого не знайдено." if q else "Домашніх завдань на цей тиждень немає.", "🎉")]
    out.append(Card([Row([Text(f"Виконано {n_done} з {total}", cls="title", expand=True),
                          Text(f"{round(100 * n_done / total)}%", cls="h3")]),
                     Progress(n_done / total, id="hw-progress")], gap=6))
    last: date | None = None
    shown = 0
    for d, sub in items:
        key = hw_key(d, sub)
        ok = key in done
        if only_open and ok:
            continue
        if d != last:
            out.append(Text(fmt_day(d, today), cls="h3", style=Style(margin=(6, 0, 0, 0))))
            last = d
        text = " ".join(sub.homework) if sub.homework else "Дистанційне завдання"
        body: list[Widget] = [Row([
            Text("✓" if ok else "○", cls="h2", color="good" if ok else "muted", width=30, text_align="center"),
            Column([Row([Text("●", color=subject_key(sub.name), font_size=12) if colors else Text(""),
                         Text(sub.name, cls="title", color="muted" if ok else None)], gap=6),
                    Text(text, cls="small", color="muted" if ok else None)], gap=2, expand=True)], gap=8)]
        if sub.hometask_id and on_hometask:
            body.append(Button("Відкрити завдання", (lambda i=sub.hometask_id, n=sub.name: on_hometask(i, n)),
                               variant="outline", id=f"hw-open-{sub.hometask_id}"))
        out.append(Card(body, gap=6, on_click=(lambda k=key: on_toggle(k)) if on_toggle else None,
                        id=f"hw-{shown}"))
        shown += 1
    if only_open and not shown:
        out.append(empty("Усе виконано. Так тримати!", "🏆"))
    return out


# ── таблиці оцінок ──
def grades_table(s: Schedule, subject: str | None = None, *, compact: bool = False, **kw: Any) -> Table:
    """Плоска таблиця «дата · предмет · оцінка · тип»; підсвічує оцінки кольором.

        grades_table(schedule, zebra=True, on_row_click=…, style=Style(radius=0))

    `compact=True` — для телефона: три колонки, тип і коментар — другим рядком під назвою предмета.
    """
    rows = []
    for d, name, g in s.grades():
        if subject and subject.lower() not in name.lower():
            continue
        when = f"{d.day:02d}.{d.month:02d}" if d else ""
        if compact:
            sub = " · ".join(x for x in (g.type, g.comment or "") if x)
            rows.append([when, Column([Text(name, cls="title", font_size=14), Text(sub, cls="muted")] if sub
                                      else [Text(name, cls="title", font_size=14)], gap=1),
                         grade_chip(g.mark, g.value)])
        else:
            rows.append([when, name, grade_chip(g.mark, g.value), g.type, g.comment or ""])
    if compact:
        return Table([Col("Дата", width=54), Col("Предмет", flex=3), Col("Бал", width=52, align="center")],
                     rows, empty="Оцінок за цей період немає.", **kw)
    return Table([Col("Дата", width=64), Col("Предмет", flex=3), Col("Бал", width=56, align="center"),
                  Col("Тип", flex=2), Col("Коментар", flex=2)],
                 rows, empty="Оцінок за цей період немає.", **kw)


def journal_table(s: Schedule, **kw: Any) -> Table:
    """Журнал: предмети по рядках, дні по колонках; у кожній клітинці оцінки за той день.

    Таблиця широка, тому має `min_width`: на телефоні (Flet) вона прокручується вбік, а не стискається.
    """
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
    kw.setdefault("min_width", 150 + 58 * len(days))
    return Table(cols, rows, empty="Оцінок за цей період немає.", **kw)


# ── успішність ──
TARGETS = [("7", "7"), ("8", "8"), ("9", "9"), ("10", "10"), ("10.5", "10,5"), ("11", "11"), ("11.5", "11,5"),
           ("12", "12")]
_SORTS = {"name": "За назвою", "avg_desc": "Спершу високий бал", "avg_asc": "Спершу низький бал"}


def trend_arrow(values: Sequence[int | float]) -> str:
    """↗ росте, ↘ падає, → без змін (за `analytics.trend`)."""
    return {"up": "↗", "down": "↘"}.get(trend(list(values)), "→")


def filter_subjects(p: StudentPerformance, query: str = "", sort: str = "name") -> list[Any]:
    """Предмети успішності за частиною назви й порядком: `name` | `avg_desc` | `avg_asc`."""
    q = (query or "").strip().lower()
    subs = [x for x in p.subjects if not q or q in x.name.lower() or q in (x.short_name or "").lower()]
    if sort == "avg_desc":
        return sorted(subs, key=lambda x: (x.average is None, -(x.average or 0), x.name.lower()))
    if sort == "avg_asc":
        return sorted(subs, key=lambda x: (x.average is None, x.average or 0, x.name.lower()))
    return sorted(subs, key=lambda x: x.name.lower())


def _name_cell(name: str, colors: bool) -> Widget:
    t = Text(name, cls="title", font_size=14)
    return Row([Text("●", color=subject_key(name), font_size=12), t], gap=6) if colors else t


def performance_table(p: StudentPerformance, on_subject: Callable[[int, str], Any] | None = None, *,
                      subjects: Sequence[Any] | None = None, compact: bool = False,
                      goals: Mapping[str, float] | None = None, colors: bool = True, **kw: Any) -> Table:
    """Успішність: предмет, усі оцінки бейджами, середній бал. `compact` — дві колонки (оцінки під назвою)."""
    subs = list(subjects) if subjects is not None else list(p.subjects)
    rows = []
    for sub in subs:
        avg = sub.average
        goal = (goals or {}).get(sub.name)
        cell: Any = Cell(avg_text(avg), color=mark_key(round(avg) if avg else None), bold=True, text_align="center")
        if goal:
            reached = avg is not None and avg >= goal
            cell = Column([Text(avg_text(avg), color=mark_key(round(avg) if avg else None), bold=True,
                                text_align="center"),
                           Text(("✓ " if reached else "🎯 ") + f"{goal:g}", cls="small",
                                color="good" if reached else "muted", text_align="center")], gap=0)
        chips = Row([grade_chip(m.mark, m.value, m.type) for m in sub.marks], wrap=True, gap=4)
        head = _name_cell(sub.name, colors)
        if compact:
            rows.append([Column([head, chips] if sub.marks else [head], gap=4), cell])
        else:
            rows.append([head, chips, cell])
    handler = (lambda i: on_subject(subs[i].id, subs[i].name)) if on_subject else None
    cols = ([Col("Предмет", flex=1), Col("Серед.", width=60, align="center")] if compact
            else [Col("Предмет", flex=3), Col("Оцінки", flex=4), Col("Серед.", width=64, align="center")])
    return Table(cols, rows, on_row_click=handler, empty="Даних про успішність немає.", **kw)


def averages_chart_widget(p: StudentPerformance, colors: str = "scale", height: int = 260,
                          show_values: bool = True, chart_type: str = "bar",
                          subjects: Sequence[Any] | None = None) -> Widget | None:
    subs = [s for s in (subjects if subjects is not None else p.subjects) if s.average is not None]
    if not subs:
        return None
    return Chart([s.short_name or s.name for s in subs], [s.average for s in subs], colors=colors,
                 type="line" if chart_type == "line" else "bar", show_values=show_values, height=height,
                 title="Середній бал за предметами", cls="chart", id="averages-chart")


def distribution_chart_widget(p: StudentPerformance, height: int = 220, show_values: bool = True) -> Widget | None:
    """Скільки разів отримано кожну оцінку 1–12 (стовпчики пофарбовані за значенням оцінки)."""
    vals = [m.value for s in p.subjects for m in s.marks if m.value is not None]
    if not vals:
        return None
    dist = mark_distribution(vals)
    counts = list(dist.values())
    return Chart([str(k) for k in dist], counts, color_values=list(dist), show_values=show_values, height=height,
                 title="Розподіл оцінок", max_value=max(max(counts), 4), cls="chart", id="distribution-chart")




def summary_card(p: StudentPerformance, subjects: Sequence[Any] | None = None, *,
                 goals: Mapping[str, float] | None = None, theme: Theme | None = None) -> Widget:
    """Зведення: кільце середнього балу, тенденція, найкращий і найслабший предмет, пропуски, цілі."""
    avg = p.average
    vals = [m.value for s in p.subjects for m in s.marks if m.value is not None]
    ranked = rank_subjects(p)
    lines = [Text(f"Пропущено днів: {p.missed_days}, уроків: {p.missed_lessons}", cls="muted")]
    if len(ranked) >= 2:
        lines.append(Text(f"Найкращий: {ranked[0][0]} ({ranked[0][1]:.1f})", cls="small", color="good"))
        lines.append(Text(f"Найслабший: {ranked[-1][0]} ({ranked[-1][1]:.1f})", cls="small", color="bad"))
    if vals:
        lines.append(Text(f"Оцінок: {len(vals)} · тенденція {trend_arrow(vals)}", cls="muted"))
    if goals:
        mine = [(x, goals[x.name]) for x in p.subjects if x.name in goals]
        if mine:
            hit = sum(1 for x, g in mine if x.average is not None and x.average >= g)
            lines.append(Text(f"🎯 Цілей досягнуто: {hit} з {len(mine)}", cls="small"))
    th = theme or _FALLBACK
    mk = mark_key(round(avg) if avg else None)
    if avg is not None and getattr(th, "palette", None):
        left: Widget = Image(svg=gauge_svg(avg, 12, color=th.color(mk) or "#2E7D32", track=th.palette["line"],
                                           text=th.palette["fg"]), height=88)
    else:
        left = Text(avg_text(avg), cls="big", style=Style(color=mk if avg else "muted"))
    return Card([Row([left, Column([Text("Середній бал", cls="title"), *lines], gap=2, expand=True)], gap=16)],
                id="summary")


def performance_view(p: StudentPerformance, missed: MissedLessons | None = None,
                     on_subject: Callable[[int, str], Any] | None = None, chart: Widget | None = None,
                     as_table: bool = True, *, subjects: Sequence[Any] | None = None, compact: bool = False,
                     extras: Sequence[Widget | None] = (), goals: Mapping[str, float] | None = None,
                     colors: bool = True, theme: Theme | None = None) -> list[Widget]:
    out = _stale(p)
    out.append(summary_card(p, goals=goals, theme=theme))
    if chart is not None:
        out.append(chart)
    out += [w for w in extras if w is not None]
    subs = list(subjects) if subjects is not None else list(p.subjects)
    if as_table:
        out.append(performance_table(p, on_subject, subjects=subs, compact=compact, id="performance-table",
                                     margin=(0, 0, 10, 0), goals=goals, colors=colors))
    else:
        for sub in subs:
            marks = [m.value for m in sub.marks if m.value is not None]
            spark = sparkline_svg(marks, 84, 28, (theme or _FALLBACK).color(subject_key(sub.name)) or "#26358F") \
                if len(marks) >= 2 else ""
            head = Row([_name_cell(sub.name, colors), Text("", expand=True),
                        *([Image(svg=spark, height=28)] if spark else []),
                        Text((trend_arrow(marks) + " " if marks else "") + avg_text(sub.average), cls="h3")], gap=8)
            body = [head] + ([Row([grade_chip(m.mark, m.value, m.type) for m in sub.marks], wrap=True, gap=6)]
                             if sub.marks else [])
            goal = (goals or {}).get(sub.name)
            if goal and sub.average is not None:
                body.append(Progress(min(1.0, sub.average / goal), id=f"goal-{sub.id}"))
                body.append(Text(f"Ціль {goal:g}: " + ("досягнуто ✓" if sub.average >= goal else
                                                       f"ще {goal - sub.average:.1f} балів"), cls="small"))
            out.append(Card(body, on_click=(lambda i=sub.id, n=sub.name: on_subject(i, n)) if on_subject else None))
    if not subs and p.subjects:
        out.append(empty("Нічого не знайдено за цим пошуком.", "🔍"))
    if missed and len(missed):
        out.append(Text("Пропущені уроки", cls="h3"))
        out.append(Card([Text(f"{fmt_day(x.date)}: {x.subject}", cls="small") for x in missed.lessons], gap=4))
    return out


def subject_view(sp: SubjectPerformance, target: float | None = None,
                 on_target: Callable[[str], Any] | None = None, *, extra: Sequence[int] = (),
                 on_extra: Callable[[int], Any] | None = None, goal: float | None = None,
                 on_goal: Callable[[float], Any] | None = None, line_color: str = "#26358F") -> Widget:
    """Оцінки одного предмета: мініграфік, калькулятор цілі, «що, якщо?» і збереження цілі.

    `on_target` вмикає калькулятор «скільки «12» потрібно»; `on_extra(v)` — кнопки гіпотетичних оцінок
    (`v=0` — скинути); `on_goal(t)` — кнопка «зробити ціллю».
    """
    real = [x.value for x in sp.lessons if x.value is not None]
    vals = real + [int(v) for v in extra]
    rows: list[Widget] = [Text(f"Середній бал: {avg_text(sp.average)}, пропущено уроків: {sp.missed_lessons}",
                               cls="muted")]
    if len(real) >= 2:
        rows.append(Image(svg=sparkline_svg(list(reversed(real)), 280, 56, line_color), height=56, id="sparkline"))
    if real:
        rows.append(Text(f"Оцінок: {len(real)} · тенденція {trend_arrow(list(reversed(real)))}", cls="muted"))
    if goal:
        rows.append(Text(f"🎯 Ваша ціль: {goal:g}", cls="title", id="goal-text"))
    if real and on_extra:
        shown = sum(vals) / len(vals)
        rows.append(Text("Що, якщо отримати…", cls="small"))
        rows.append(Row([Button(f"+{v}", (lambda v=v: on_extra(v)), variant="outline", id=f"wi-{v}")
                         for v in (12, 10, 8, 6, 4)] + [Button("↺", (lambda: on_extra(0)), variant="text",
                                                               id="wi-reset")], wrap=True, gap=4))
        if extra:
            rows.append(Text(f"З оцінками {', '.join(str(v) for v in extra)}: середній {shown:.2f}".replace(".", ","),
                             cls="title", id="whatif-result"))
    if real and on_target:
        t = target if target is not None else 10.0
        n = needed_marks(vals, t)
        msg = ("Ціль уже досягнуто 🎉" if n == 0 else
               "Цього балу не досягти без усіх «12»" if n is None else
               f"Потрібно ще {n} × «12», щоб середній бал став {t:g}")
        rows += [Dropdown("target", "Цільовий бал", TARGETS, f"{t:g}", on_change=on_target, id="target"),
                 Text(msg, cls="title", id="target-result")]
        if on_goal:
            rows.append(Button("🎯 Зробити ціллю" if goal != t else "✓ Це ваша ціль", (lambda: on_goal(t)),
                               variant="outline", id="set-goal"))
    for x in sp.lessons:
        rows.append(Row([Text(f"{x.date.day:02d}.{x.date.month:02d}" if x.date else "", cls="small", width=44),
                         grade_chip(x.mark, x.value), Text(x.comment or x.type, cls="muted", expand=True)], gap=8))
    return Column(rows, gap=8, scroll=True, height=440)


def homework_text(s: Schedule, done: Any = frozenset(), *, only_open: bool = True) -> str:
    """Д/з тижня простим текстом (щоб надіслати в чат): за днями, із позначкою виконаного."""
    lines: list[str] = []
    for d in s.days:
        part = []
        for les in d.lessons:
            for sub in les.subjects:
                if sub.homework or sub.hometask_id:
                    ok = hw_key(d.date, sub) in done
                    if only_open and ok:
                        continue
                    part.append(f"{'✓' if ok else '•'} {sub.name}: " + (" ".join(sub.homework) or "дистанційне завдання"))
        if part:
            lines += [fmt_day(d.date), *part, ""]
    return "\n".join(lines).strip() or "Невиконаних домашніх завдань немає."


def dashboard_view(s: Schedule, *, name: str = "", today: date | None = None, now: time | None = None,
                   done: Any = frozenset(), on_toggle: Callable[[str], Any] | None = None,
                   on_goto: Callable[[str], Any] | None = None, theme: Theme | None = None,
                   colors: bool = True) -> list[Widget]:
    """Екран «Сьогодні»: привітання, поточний/наступний урок, лічильники, найближче Д/з, останні оцінки, кільце тижня."""
    today = today or date.today()
    now = now or datetime.now().time()
    th = theme or _FALLBACK
    out = _stale(s)
    day = next((d for d in s.days if d.date == today), None)
    lessons = [(les, sub) for les in (day.lessons if day else ()) for sub in les.subjects]
    week_grades = sorted(s.grades(), key=lambda x: x[0] or date.min, reverse=True)
    wvals = [g.value for _, _, g in week_grades if g.value is not None]
    wavg = sum(wvals) / len(wvals) if wvals else None

    # 1. привітання
    if lessons:
        first = next((les.start for les, _ in lessons if les.start), None)
        last = max((les.end for les, _ in lessons if les.end), default=None)
        summary = f"Сьогодні уроків: {len(lessons)}" + (f" · {fmt_time(first)}–{fmt_time(last)}" if first and last else "")
    else:
        summary = "Сьогодні уроків немає — відпочивайте 🎉" if today.weekday() >= 5 else "Сьогодні записів немає"
    out.append(Card([Text(f"{greeting(now)}{', ' + name if name else ''}!", cls="h2", color="on_ink"),
                     Text(fmt_day(today), font_size=14, color="on_ink"),
                     Text(summary, font_size=14, color="on_ink")], cls="hero", gap=3, id="hero"))

    # 2. зараз / далі
    def at(t: time) -> datetime:
        return datetime.combine(today, t)

    cur = next(((l, sub) for l, sub in lessons if l.start and l.end and l.start <= now <= l.end), None)
    nxt = next(((l, sub) for l, sub in lessons if l.start and l.start > now), None)
    if cur:
        l, sub = cur
        total = max(1.0, (at(l.end) - at(l.start)).total_seconds())
        passed = (at(now) - at(l.start)).total_seconds()
        left = max(0, round((at(l.end) - at(now)).total_seconds() / 60))
        out.append(Card([Text("● Зараз", cls="small", color="ink", bold=True),
                         Text(sub.name, cls="h3", color=subject_key(sub.name) if colors else None),
                         Text(", ".join(x for x in (f"каб. {sub.room}" if sub.room else "",
                                                    sub.teacher.name if sub.teacher else "",
                                                    f"до кінця {left} хв") if x), cls="muted"),
                         Progress(min(1.0, passed / total), id="lesson-progress")], gap=6, id="now-card"))
    elif nxt:
        l, sub = nxt
        mins = round((at(l.start) - at(now)).total_seconds() / 60)
        when = f"через {mins} хв" if mins < 90 else f"о {fmt_time(l.start)}"
        out.append(Card([Text("Далі", cls="small", color="muted", bold=True),
                         Text(sub.name, cls="h3", color=subject_key(sub.name) if colors else None),
                         Text(", ".join(x for x in (f"{fmt_time(l.start)} ({when})",
                                                    f"каб. {sub.room}" if sub.room else "",
                                                    sub.teacher.name if sub.teacher else "") if x), cls="muted")],
                        gap=4, id="next-card"))
    elif lessons:
        out.append(Card([Text("Уроки на сьогодні закінчились ✔", cls="title")], id="done-card"))

    # 3. лічильники
    hw = [(d.date, sub) for d in s.days for les in d.lessons for sub in les.subjects if sub.homework or sub.hometask_id]
    open_hw = [(d, sub) for d, sub in hw if hw_key(d, sub) not in done]

    def stat(value: Any, label: str, goto: str | None = None) -> Widget:
        return Card([Text(str(value), cls="h2", text_align="center"), Text(label, cls="muted", text_align="center")],
                    gap=0, expand=True, on_click=(lambda: on_goto(goto)) if (on_goto and goto) else None,
                    id=f"stat-{goto or label}")

    out.append(Row([stat(len(lessons), "уроків", "lessons"), stat(len(open_hw), "Д/з лишилось", "homework"),
                    stat(len(wvals), "оцінок за тиждень", "marks")], gap=8, align="stretch"))

    # 4. кільце середнього тижня
    if wavg is not None:
        mk = mark_key(round(wavg))
        out.append(Card([Row([
            Image(svg=gauge_svg(wavg, 12, color=th.color(mk) or "#2E7D32", track=th.palette["line"],
                                text=th.palette["fg"]), height=88),
            Column([Text("Середній бал тижня", cls="title"),
                    Text(f"{len(wvals)} оцінок · тенденція {trend_arrow(list(reversed(wvals)))}", cls="muted")],
                   gap=2, expand=True)], gap=14)], id="week-gauge"))

    # 5. найближче Д/з
    upcoming = [(d, sub) for d, sub in open_hw if d is None or d >= today][:4]
    rows: list[Widget] = [Row([Text("Найближче Д/з", cls="h3", expand=True),
                               Button("Усе", (lambda: on_goto("homework")), variant="text", id="goto-hw")
                               if on_goto else Text("")])]
    if upcoming:
        for d, sub in upcoming:
            key = hw_key(d, sub)
            rows.append(Row([Text("○", cls="h3", color="muted", width=26, text_align="center",
                                  on_click=(lambda k=key: on_toggle(k)) if on_toggle else None, id=f"dash-hw-{len(rows)}"),
                             Column([Text(sub.name, cls="title", color=subject_key(sub.name) if colors else None),
                                     Text(" ".join(sub.homework) or "Дистанційне завдання", cls="small")],
                                    gap=1, expand=True)], gap=8, align="start"))
    else:
        rows.append(Text("Невиконаного Д/з немає 🎉" if hw else "Домашніх завдань немає", cls="muted"))
    out.append(Card(rows, gap=8, id="dash-hw"))

    # 6. останні оцінки
    if week_grades:
        gr: list[Widget] = [Row([Text("Останні оцінки", cls="h3", expand=True),
                                 Button("Усе", (lambda: on_goto("marks")), variant="text", id="goto-marks")
                                 if on_goto else Text("")])]
        for d, subj, g in week_grades[:5]:
            gr.append(Row([Text(f"{d.day:02d}.{d.month:02d}" if d else "", cls="small", width=44),
                           Text(subj, cls="title", expand=True), grade_chip(g.mark, g.value, g.comment or g.type)],
                          gap=8))
        out.append(Card(gr, gap=8, id="dash-grades"))
    return out


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
                 extra: Sequence[Widget] = (), on_settings: Callable | None = None) -> list[Widget]:
    lines = [x for x in [f"Клас: {st.class_name}" if st and st.class_name else "",
                         f"Класний керівник: {st.class_manager}" if st and st.class_manager else ""] if x]
    out: list[Widget] = [
        Card([Text(st.full_name if st else "Учень", cls="h2"), *[Text(x) for x in lines]], gap=4),
        Card([Text("Сервер nz.ua працює" if api_ok else "Сервер nz.ua не відповідає", cls="good" if api_ok else "bad")]),
    ]
    if on_settings:
        out.append(Button("Налаштування вигляду й функцій", on_settings, icon="settings", variant="primary",
                          id="open-settings"))
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
