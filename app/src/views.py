"""Чисті функції, що будують контролі зі моделей nzua (без стану й мережі)."""
from __future__ import annotations

from datetime import date, time
from typing import Callable

import flet as ft

from nzua import (ChartStyle, Grade, averages_chart, MissedLessons, Notification, Schedule, Student, StudentPerformance,
                  SubjectPerformance, Timetable)

INK = "#26358F"      # синє чорнило
PAPER = "#F4F6FB"    # аркуш у клітинку
MARGIN = "#C8372D"   # червоне поле зошита
GRAPHITE = "#1D2433"
MUTED = "#6B7385"
CARD = "#FFFFFF"
GOOD, MID, BAD = "#2F855A", "#B7791F", "#C8372D"

DAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "Пʼятниця", "Субота", "Неділя"]
MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня",
          "серпня", "вересня", "жовтня", "листопада", "грудня"]


def fmt_day(d: date | None) -> str:
    return f"{DAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}" if d else "—"


def fmt_time(t: time | None) -> str:
    return t.strftime("%H:%M") if t else ""


def mark_color(value: int | None) -> str:
    """12-бальна шкала: 1–6 червоний/бурштиновий, 7–12 зелений."""
    if value is None:
        return MUTED
    return BAD if value <= 3 else MID if value <= 6 else GOOD


def mark_chip(text: str, value: int | None, tooltip: str | None = None) -> ft.Control:
    return ft.Container(
        content=ft.Text(text, color="#FFFFFF", weight=ft.FontWeight.BOLD, size=15),
        bgcolor=mark_color(value), border_radius=8, tooltip=tooltip,
        padding=ft.Padding.symmetric(vertical=3, horizontal=9))


def avg_text(v: float | None) -> str:
    return f"{v:.1f}" if v is not None else "—"


def _card(content: ft.Control, on_click=None) -> ft.Control:
    return ft.Container(
        content=content, bgcolor=CARD, border_radius=12, on_click=on_click, ink=bool(on_click),
        padding=ft.Padding.all(12), margin=ft.Margin.only(bottom=10),
        border=ft.Border(left=ft.BorderSide(4, MARGIN)))


def empty(text: str) -> ft.Control:
    return ft.Container(ft.Text(text, color=MUTED, size=15, text_align=ft.TextAlign.CENTER),
                        alignment=ft.Alignment.CENTER, padding=ft.Padding.all(40))


def stale_banner(from_cache: bool) -> list[ft.Control]:
    if not from_cache:
        return []
    return [ft.Container(
        ft.Text("Немає зв’язку. Показано збережені дані.", color="#7A4B00", size=13),
        bgcolor="#FFF3D6", border_radius=8, padding=ft.Padding.all(8),
        margin=ft.Margin.only(bottom=10))]


def _lesson_head(number: int | None, name: str, bits: list[str]) -> ft.Control:
    return ft.Row([
        ft.Container(ft.Text(str(number or "·"), color=INK, weight=ft.FontWeight.BOLD, size=16),
                     width=28, alignment=ft.Alignment.CENTER),
        ft.Column([ft.Text(name, size=16, weight=ft.FontWeight.W_600, color=GRAPHITE),
                   ft.Text(", ".join(b for b in bits if b), size=12, color=MUTED)],
                  spacing=1, expand=True)],
        vertical_alignment=ft.CrossAxisAlignment.START)


def schedule_view(s: Schedule, on_hometask: Callable[[int, str], None]) -> list[ft.Control]:
    out = stale_banner(s.from_cache)
    for day in s.days:
        rows: list[ft.Control] = [ft.Text(fmt_day(day.date), size=17, weight=ft.FontWeight.BOLD, color=INK)]
        for les in day.lessons:
            for sub in les.subjects:
                bits = [f"{fmt_time(les.start)}–{fmt_time(les.end)}" if les.start else "",
                        f"каб. {sub.room}" if sub.room else "", sub.teacher.name if sub.teacher else ""]
                rows.append(_lesson_head(les.number, sub.name, bits))
                if sub.grades:
                    rows.append(ft.Row([mark_chip(g.mark, g.value, g.comment or g.type) for g in sub.grades],
                                       spacing=6, wrap=True))
                if sub.homework or sub.hometask_id:
                    hw = "Д/з: " + " ".join(sub.homework) if sub.homework else "Дистанційне завдання"
                    tap = (lambda e, i=sub.hometask_id, n=sub.name: on_hometask(i, n)) if sub.hometask_id else None
                    rows.append(ft.Container(ft.Text(hw, size=13, color=INK if tap else GRAPHITE),
                                             on_click=tap, padding=ft.Padding.only(left=28)))
        out.append(_card(ft.Column(rows, spacing=8)))
    return out or [empty("На цей тиждень записів немає.")]


def timetable_view(t: Timetable) -> list[ft.Control]:
    out = stale_banner(t.from_cache)
    for day in t.days:
        rows: list[ft.Control] = [ft.Text(fmt_day(day.date), size=17, weight=ft.FontWeight.BOLD, color=INK)]
        for les in day.lessons:
            for sub in les.subjects:
                bits = [f"{fmt_time(les.start)}–{fmt_time(les.end)}" if les.start else "",
                        f"каб. {sub.room}" if sub.room else "", sub.teacher.name if sub.teacher else ""]
                rows.append(_lesson_head(les.number, sub.name, bits))
        out.append(_card(ft.Column(rows, spacing=8)))
    return out or [empty("Розкладу на цей тиждень немає.")]


def chart_view(p: StudentPerformance, palette: str, height: int, show_values: bool) -> ft.Control | None:
    """Стовпчики середніх балів (SVG із бібліотеки). Висота й палітра — з налаштувань."""
    if not any(s.average is not None for s in p.subjects):
        return None
    svg = averages_chart(p, ChartStyle(width=640, height=height, colors=palette, show_values=show_values,
                                       background=CARD, responsive=True))
    return ft.Container(ft.Image(src=svg.encode("utf-8"), fit=ft.BoxFit.CONTAIN, height=height),
                        bgcolor=CARD, border_radius=12, padding=ft.Padding.all(8),
                        margin=ft.Margin.only(bottom=10))


def performance_view(p: StudentPerformance, missed: MissedLessons | None,
                     on_subject: Callable[[int, str], None],
                     chart: ft.Control | None = None) -> list[ft.Control]:
    out = stale_banner(p.from_cache)
    avg = p.average
    out.append(_card(ft.Row([
        ft.Text(avg_text(avg), size=44, weight=ft.FontWeight.BOLD, color=mark_color(round(avg)) if avg else MUTED),
        ft.Column([ft.Text("Середній бал", size=16, weight=ft.FontWeight.W_600),
                   ft.Text(f"Пропущено днів: {p.missed_days}, уроків: {p.missed_lessons}",
                           size=13, color=MUTED)], spacing=2)],
        spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER)))
    if chart is not None:
        out.append(chart)
    for sub in p.subjects:
        head = ft.Row([ft.Text(sub.name, size=15, weight=ft.FontWeight.W_600, expand=True),
                       ft.Text(avg_text(sub.average), size=18, weight=ft.FontWeight.BOLD,
                               color=mark_color(round(sub.average)) if sub.average else MUTED)])
        marks = ft.Row([mark_chip(x.mark, x.value, x.type) for x in sub.marks], spacing=6, wrap=True)
        out.append(_card(ft.Column([head, marks], spacing=8) if sub.marks else head,
                         on_click=lambda e, i=sub.id, n=sub.name: on_subject(i, n)))
    if missed and len(missed):
        out.append(ft.Text("Пропущені уроки", size=17, weight=ft.FontWeight.BOLD, color=INK))
        out.append(_card(ft.Column([ft.Text(f"{fmt_day(x.date)}: {x.subject}", size=13)
                                    for x in missed.lessons], spacing=4)))
    return out


def subject_view(sp: SubjectPerformance) -> ft.Control:
    rows: list[ft.Control] = [ft.Text(f"Середній бал: {avg_text(sp.average)}, пропущено уроків: {sp.missed_lessons}",
                                      size=13, color=MUTED)]
    for x in sp.lessons:
        rows.append(ft.Row([ft.Text(f"{x.date.day:02d}.{x.date.month:02d}" if x.date else "", size=13, width=44),
                            mark_chip(x.mark, x.value),
                            ft.Text(x.comment or x.type, size=12, color=MUTED, expand=True)]))
    return ft.Column(rows, spacing=8, scroll=ft.ScrollMode.AUTO, tight=True, width=320, height=420)


def notifications_view(items: list[Notification], unread: int) -> list[ft.Control]:
    if not items:
        return [empty("Сповіщень поки немає.")]
    out: list[ft.Control] = [ft.Text(f"Непрочитаних: {unread}", size=13, color=MUTED)]
    for n in items:
        row: list[ft.Control] = [ft.Column([
            ft.Text(n.body, size=14, weight=ft.FontWeight.W_600),
            ft.Text(n.sent_at.strftime("%d.%m.%Y %H:%M") if n.sent_at else "", size=12, color=MUTED)],
            spacing=2, expand=True)]
        if n.mark:
            row.append(mark_chip(n.mark, Grade(type="", mark=n.mark).value))
        out.append(_card(ft.Row(row, vertical_alignment=ft.CrossAxisAlignment.CENTER)))
    return out


def profile_view(st: Student | None, api_ok: bool, on_logout,
                 settings: list[ft.Control] | None = None) -> list[ft.Control]:
    name = st.full_name if st else "Учень"
    lines = [x for x in [f"Клас: {st.class_name}" if st and st.class_name else "",
                         f"Класний керівник: {st.class_manager}" if st and st.class_manager else ""] if x]
    return [
        _card(ft.Column([ft.Text(name, size=20, weight=ft.FontWeight.BOLD, color=INK),
                         *[ft.Text(x, size=14, color=GRAPHITE) for x in lines]], spacing=4)),
        _card(ft.Text("Сервер nz.ua працює" if api_ok else "Сервер nz.ua не відповідає",
                      size=14, color=GOOD if api_ok else BAD)),
        *([_card(ft.Column(settings, spacing=10))] if settings else []),
        ft.OutlinedButton(content="Вийти з акаунта", icon=ft.Icons.LOGOUT, on_click=on_logout),
    ]
