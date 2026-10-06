"""Допоміжні функції для толерантного розбору JSON (API неофіційне)."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from html.parser import HTMLParser
from typing import Any


def to_int(v: Any, default: int | None = None) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def to_date(v: Any) -> date | None:
    if isinstance(v, str) and len(v) >= 10:
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def to_datetime(v: Any) -> datetime | None:
    """Приймає epoch (секунди) або 'YYYY-MM-DD HH:MM:SS'."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace(" ", "T"))
        except ValueError:
            return None
    return None


def to_time(v: Any) -> time | None:
    """'8:30' або '08:30:00' -> time."""
    if not isinstance(v, str):
        return None
    try:
        return time(*[int(p) for p in v.split(":")[:3]])
    except (ValueError, TypeError):
        return None


class _Stripper(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag == "li":
            self.out.append("• ")

    def handle_data(self, data):
        self.out.append(data)


def strip_html(text: str | None) -> str:
    """Прибирає HTML-теги із завдання/відповіді."""
    if not text:
        return ""
    p = _Stripper()
    p.feed(text)
    lines = [ln.strip() for ln in "".join(p.out).splitlines()]
    return "\n".join(ln for ln in lines if ln)
