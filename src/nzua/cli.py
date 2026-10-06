"""Командний рядок: `nzua grades`, `nzua performance`, `nzua chart averages` тощо."""
from __future__ import annotations

import argparse
import asyncio
import csv
import getpass
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from . import __version__, analytics, charts
from .client import AsyncNZClient
from .errors import NZError, Unauthorized
from .storage import FileCache, FileTokenStore

Cols = list[tuple[str, str]]  # (ключ для json/csv, заголовок таблиці)


@dataclass
class Output:
    cols: Cols
    rows: list[list[Any]]
    footer: str = ""
    extra: dict = field(default_factory=dict)


def default_home() -> Path:
    return Path(os.getenv("NZUA_HOME") or Path.home() / ".nzua")


def make_client(home: Path, no_cache: bool) -> AsyncNZClient:
    return AsyncNZClient(token_store=FileTokenStore(home / "tokens.json"),
                         cache=None if no_cache else FileCache(home / "cache.json"))


# ───────────── період ─────────────
def _d(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"очікується дата РРРР-ММ-ДД, отримано {s!r}")


def resolve_period(a: argparse.Namespace) -> tuple[date | None, date | None]:
    if a.date_from or a.date_to:
        return a.date_from, a.date_to
    today = date.today()
    if a.period == "week":
        mon = today - timedelta(days=today.weekday())
        return mon, mon + timedelta(days=6)
    if a.period == "year":
        return date(today.year if today.month >= 9 else today.year - 1, 9, 1), today
    return None, None  # місяць: значення за замовчуванням бібліотеки


def _fmt_marks(marks) -> str:
    return " ".join(m.mark for m in marks)


# ───────────── команди ─────────────
async def c_grades(nz: AsyncNZClient, a) -> Output:
    s = await nz.get_schedule(*resolve_period(a))
    rows = [[str(d), name, g.mark, g.type, g.comment or ""] for d, name, g in s.grades()
            if not a.subject or a.subject.lower() in name.lower()]
    nums = [int(r[2]) for r in rows if r[2].isdigit()]
    avg = sum(nums) / len(nums) if nums else None
    return Output([("date", "Дата"), ("subject", "Предмет"), ("mark", "Оцінка"), ("type", "Тип"),
                   ("comment", "Коментар")], rows,
                  f"Середній бал: {avg:.2f}" if avg is not None else "Числових оцінок немає")


async def c_performance(nz, a) -> Output:
    p = await nz.get_student_performance(*resolve_period(a))
    rows = [[s.id, s.name, f"{s.average:.2f}" if s.average is not None else "—", _fmt_marks(s.marks)]
            for s in p.subjects]
    avg = f"{p.average:.2f}" if p.average is not None else "—"
    return Output([("id", "ID"), ("subject", "Предмет"), ("average", "Середній"), ("marks", "Оцінки")], rows,
                  f"Загальний середній: {avg}; пропущено днів: {p.missed_days}, уроків: {p.missed_lessons}")


async def c_subject(nz, a) -> Output:
    sp = await nz.get_subject_performance(a.subject_id, *resolve_period(a))
    rows = [[str(x.date), x.type, x.mark, x.comment or ""] for x in sp.lessons]
    avg = f"{sp.average:.2f}" if sp.average is not None else "—"
    return Output([("date", "Дата"), ("type", "Тип"), ("mark", "Оцінка"), ("comment", "Коментар")], rows,
                  f"Середній: {avg}; пропущено уроків: {sp.missed_lessons}")


async def c_schedule(nz, a) -> Output:
    s = await nz.get_schedule(*resolve_period(a))
    rows = []
    for day in s.days:
        for les in day.lessons:
            for sub in les.subjects:
                rows.append([str(day.date), les.number, f"{les.start:%H:%M}" if les.start else "", sub.name,
                             sub.room or "", sub.teacher.name if sub.teacher else "",
                             _fmt_marks(sub.grades), " ".join(sub.homework)])
    return Output([("date", "Дата"), ("number", "№"), ("start", "Початок"), ("subject", "Предмет"),
                   ("room", "Каб."), ("teacher", "Вчитель"), ("marks", "Оцінки"), ("homework", "Д/з")], rows)


async def c_timetable(nz, a) -> Output:
    t = await nz.get_timetable(*resolve_period(a))
    rows = [[str(day.date), les.number, f"{les.start:%H:%M}" if les.start else "", sub.name, sub.room or "",
             sub.teacher.name if sub.teacher else ""]
            for day in t.days for les in day.lessons for sub in les.subjects]
    return Output([("date", "Дата"), ("number", "№"), ("start", "Початок"), ("subject", "Предмет"),
                   ("room", "Каб."), ("teacher", "Вчитель")], rows)


async def c_missed(nz, a) -> Output:
    ml = await nz.get_missed_lessons(*resolve_period(a))
    return Output([("date", "Дата"), ("number", "№"), ("subject", "Предмет")],
                  [[str(x.date), x.number, x.subject] for x in ml.lessons], f"Всього: {len(ml)}")


async def c_homework(nz, a) -> Output:
    h = await nz.get_hometask(a.hometask_id)
    rows = [["text", "Завдання", h.text], ["answer", "Відповідь", h.answer or ""],
            ["closed", "Закрите", "так" if h.is_closed else "ні"],
            ["files", "Файли", ", ".join(f"{f.name} [{f.uuid}]" for f in h.files)]]
    return Output([("key", "Ключ"), ("field", "Поле"), ("value", "Значення")], rows)


async def c_answer(nz, a) -> Output:
    await nz.answer_hometask(a.hometask_id, a.text)
    return Output([("status", "Статус")], [["Відповідь надіслано"]])


async def c_notifications(nz, a) -> Output:
    items = await nz.get_notifications()
    unread = await nz.get_unread_count()
    return Output([("sent", "Час"), ("body", "Сповіщення"), ("mark", "Оцінка")],
                  [[f"{n.sent_at:%Y-%m-%d %H:%M}" if n.sent_at else "", n.body, n.mark or ""] for n in items],
                  f"Непрочитаних: {unread}")


async def c_status(nz, a) -> Output:
    ok = await nz.ping()
    await nz.restore_session()
    return Output([("item", "Пункт"), ("state", "Стан")],
                  [["Сервер nz.ua", "працює" if ok else "не відповідає"],
                   ["Сесія", "є збережена" if nz.is_authenticated else "немає (nzua login)"]])


async def c_chart(nz, a) -> Output:
    style = charts.ChartStyle(
        width=a.width, height=a.height, colors=a.colors, title=a.title, show_values=not a.no_values,
        background=a.background, text_color=a.text_color)
    if a.kind == "averages":
        svg = charts.averages_chart(await nz.get_student_performance(*resolve_period(a)), style)
    else:
        sch = await nz.get_schedule(*resolve_period(a))
        if a.kind == "marks":
            svg = charts.marks_chart(sch, style, a.subject)
        else:
            vals = [g.value for _, name, g in sch.grades() if not a.subject or a.subject.lower() in name.lower()]
            svg = charts.distribution_chart(vals, style)
    path = charts.save_svg(a.output or f"chart-{a.kind}.svg", svg)
    return Output([("file", "Файл")], [[str(path)]])


COMMANDS: dict[str, Callable] = {
    "grades": c_grades, "performance": c_performance, "subject": c_subject, "schedule": c_schedule,
    "timetable": c_timetable, "missed": c_missed, "homework": c_homework, "answer": c_answer,
    "notifications": c_notifications, "status": c_status, "chart": c_chart}


# ───────────── вивід ─────────────
def emit(out: Output, fmt: str, file=None) -> None:
    file = file or sys.stdout
    keys = [k for k, _ in out.cols]
    if fmt == "json":
        print(json.dumps({"rows": [dict(zip(keys, r)) for r in out.rows], "summary": out.footer},
                         ensure_ascii=False, indent=2, default=str), file=file)
    elif fmt == "csv":
        w = csv.writer(file)
        w.writerow(keys)
        w.writerows(out.rows)
    else:
        titles = [t for _, t in out.cols]
        cells = [[_cell(c) for c in r] for r in out.rows]
        widths = [max([len(t)] + [len(r[i]) for r in cells]) for i, t in enumerate(titles)]
        line = lambda r: "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
        print(line(titles), file=file)
        print(line(["─" * w for w in widths]), file=file)
        for r in cells:
            print(line(r), file=file)
        if not cells:
            print("(порожньо)", file=file)
        if out.footer:
            print(f"\n{out.footer}", file=file)


def _cell(v: Any, limit: int = 48) -> str:
    s = " ".join(str(v).split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ───────────── парсер ─────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nzua", description="Консольний клієнт електронного щоденника nz.ua")
    p.add_argument("--version", action="version", version=f"nzua {__version__}")
    p.add_argument("--home", type=Path, default=None, help="каталог сесії та кешу (за замовчуванням ~/.nzua)")
    p.add_argument("-f", "--format", choices=("table", "json", "csv"), default="table", help="формат виводу")
    p.add_argument("--no-cache", action="store_true", help="не використовувати офлайн-кеш")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="команда")

    period = argparse.ArgumentParser(add_help=False)
    period.add_argument("--from", dest="date_from", type=_d, metavar="РРРР-ММ-ДД")
    period.add_argument("--to", dest="date_to", type=_d, metavar="РРРР-ММ-ДД")
    period.add_argument("--period", choices=("week", "month", "year"), default="month",
                        help="week — поточний тиждень, month — місяць (типово), year — навчальний рік")

    sub.add_parser("login", help="увійти й зберегти сесію").add_argument("-u", "--username")
    sub.choices["login"].add_argument("-p", "--password", help="або змінна NZUA_PASSWORD")
    sub.add_parser("logout", help="вийти й видалити сесію та кеш")
    sub.add_parser("status", help="перевірити сервер і сесію")
    g = sub.add_parser("grades", parents=[period], help="оцінки за період")
    g.add_argument("--subject", help="частина назви предмета")
    sub.add_parser("performance", parents=[period], help="успішність по предметах")
    s = sub.add_parser("subject", parents=[period], help="оцінки з одного предмета")
    s.add_argument("subject_id", help="ID предмета (колонка ID у `performance`)")
    sub.add_parser("schedule", parents=[period], help="щоденник: уроки, оцінки, домашні завдання")
    sub.add_parser("timetable", parents=[period], help="розклад")
    sub.add_parser("missed", parents=[period], help="пропущені уроки")
    h = sub.add_parser("homework", help="дистанційне завдання")
    h.add_argument("hometask_id")
    ans = sub.add_parser("answer", help="надіслати відповідь на завдання")
    ans.add_argument("hometask_id")
    ans.add_argument("text")
    sub.add_parser("notifications", help="сповіщення")

    c = sub.add_parser("chart", parents=[period], help="намалювати графік у SVG")
    c.add_argument("kind", choices=("averages", "marks", "distribution"),
                   help="averages — середні по предметах, marks — оцінки в часі, distribution — скільки яких оцінок")
    c.add_argument("-o", "--output", help="файл (типово chart-<вид>.svg)")
    c.add_argument("--width", type=int, default=640)
    c.add_argument("--height", type=int, default=360)
    c.add_argument("--colors", default="scale",
                   help=f"палітра ({', '.join(charts.PALETTES)}) або кольори через кому: '#c00,#0a0'")
    c.add_argument("--title")
    c.add_argument("--subject", help="фільтр за предметом (marks, distribution)")
    c.add_argument("--no-values", action="store_true", help="не підписувати значення")
    c.add_argument("--background", default="#FFFFFF")
    c.add_argument("--text-color", default="#1D2433")

    n = sub.add_parser("need", help="скільки найвищих оцінок потрібно для бажаного середнього (офлайн)")
    n.add_argument("--marks", required=True, help="поточні оцінки через кому: 8,9,10")
    n.add_argument("--target", type=float, required=True, help="бажаний середній бал")
    n.add_argument("--max", type=int, default=12, dest="max_mark")
    return p


# ───────────── запуск ─────────────
async def _run(a, factory) -> int:
    home = a.home or default_home()
    nz = factory(home, a.no_cache)
    try:
        if a.cmd == "login":
            user = a.username or input("Логін: ")
            pwd = a.password or os.getenv("NZUA_PASSWORD") or getpass.getpass("Пароль: ")
            st = await nz.login(user, pwd)
            print(f"Вхід виконано: {st.full_name}" + (f", {st.class_name}" if st.class_name else ""))
            return 0
        if a.cmd == "logout":
            await nz.restore_session()
            await nz.logout()
            print("Сесію й кеш видалено.")
            return 0
        out = await COMMANDS[a.cmd](nz, a)
        emit(out, a.format)
        return 0
    except Unauthorized:
        print("Потрібен вхід: виконайте `nzua login`.", file=sys.stderr)
        return 2
    except (NZError, ValueError) as e:
        print(f"Помилка: {e}", file=sys.stderr)
        return 1
    finally:
        await nz.aclose()


def main(argv: list[str] | None = None, *, client_factory: Callable = make_client) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    a = build_parser().parse_args(argv)
    if a.cmd == "need":
        try:
            marks = [int(x) for x in a.marks.replace(" ", "").split(",") if x]
        except ValueError:
            print("Помилка: --marks має бути списком цілих чисел через кому.", file=sys.stderr)
            return 1
        n = analytics.needed_marks(marks, a.target, a.max_mark)
        print("Бажаний середній недосяжний." if n is None else
              "Ціль уже досягнуто." if n == 0 else f"Потрібно отримати поспіль «{a.max_mark}»: {n} раз(и).")
        return 0
    return asyncio.run(_run(a, client_factory))
