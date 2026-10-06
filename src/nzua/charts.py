"""SVG-графіки без залежностей: стовпчикові й лінійні, з налаштуванням кольорів і розмірів.

    svg = bar_chart(["Алгебра", "Фізика"], [10.5, 8], ChartStyle(width=500, height=300, colors="ocean"))
    save_svg("avg.svg", svg)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence
from xml.sax.saxutils import escape, quoteattr

from .analytics import mark_distribution
from .models import Schedule, StudentPerformance

__all__ = ("ChartStyle", "PALETTES", "bar_chart", "line_chart", "averages_chart",
           "marks_chart", "distribution_chart", "save_svg", "scale_color")

PALETTES: dict[str, tuple[str, ...] | None] = {
    "scale": None,  # колір залежить від оцінки: червоний → бурштиновий → зелений
    "ink": ("#26358F",),
    "ocean": ("#0B6E99", "#2BA3C4", "#5CC8D7", "#1B4F72"),
    "forest": ("#2F855A", "#68A357", "#9BC53D", "#1E5F46"),
    "sunset": ("#C8372D", "#E8743B", "#F2A541", "#8E2C48"),
    "mono": ("#1D2433", "#4A5468", "#7B8499", "#A9B0C0"),
}
_COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20})$")


def scale_color(value: float | None) -> str:
    """Колір за 12-бальною шкалою (як у застосунку)."""
    if value is None:
        return "#6B7385"
    return "#C8372D" if value <= 3 else "#B7791F" if value <= 6 else "#2F855A"


@dataclass(frozen=True, slots=True)
class ChartStyle:
    """Вигляд графіка. `colors` — назва палітри, список або рядок "#aaa,#bbb"."""
    width: int = 640
    height: int = 360
    colors: str | Sequence[str] | None = "scale"
    background: str = "#FFFFFF"
    text_color: str = "#1D2433"
    grid_color: str = "#E3E7F0"
    font_size: int = 13
    title: str | None = None
    show_values: bool = True
    min_value: float = 0
    max_value: float = 12
    bar_radius: int = 4
    line_width: float = 3
    point_radius: float = 4
    responsive: bool = False  # true: без width/height — масштабується під контейнер

    def __post_init__(self) -> None:
        if not (120 <= self.width <= 4000 and 120 <= self.height <= 4000):
            raise ValueError("width і height мають бути в межах 120–4000")
        if self.max_value <= self.min_value:
            raise ValueError("max_value має бути більшим за min_value")
        for c in (self.background, self.text_color, self.grid_color, *self.palette()):
            if not _COLOR.match(c):
                raise ValueError(f"Некоректний колір: {c!r}")

    def palette(self) -> tuple[str, ...]:
        """Список кольорів; порожній — режим 'за оцінкою'."""
        spec = self.colors
        if spec is None:
            return ()
        if isinstance(spec, str):
            if spec in PALETTES:
                return PALETTES[spec] or ()
            spec = [p.strip() for p in spec.split(",") if p.strip()]
        return tuple(spec)

    def color_for(self, index: int, value: float | None) -> str:
        pal = self.palette()
        return pal[index % len(pal)] if pal else scale_color(value)


def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _open(style: ChartStyle) -> list[str]:
    size = "" if style.responsive else f' width="{style.width}" height="{style.height}"'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {style.width} {style.height}"{size} '
           f'font-family="Roboto, Arial, sans-serif" font-size="{style.font_size}">',
           f'<rect width="100%" height="100%" fill={quoteattr(style.background)}/>']
    if style.title:
        out.append(f'<text x="{style.width / 2}" y="{style.font_size + 8}" text-anchor="middle" '
                   f'font-size="{style.font_size + 3}" font-weight="bold" fill={quoteattr(style.text_color)}>'
                   f'{escape(style.title)}</text>')
    return out


def _frame(style: ChartStyle, labels_h: int) -> tuple[float, float, float, float]:
    top = 44 if style.title else 20
    return 44, top, style.width - 16, style.height - labels_h


def _grid(style: ChartStyle, box: tuple[float, float, float, float]) -> list[str]:
    x0, y0, x1, y1 = box
    span = style.max_value - style.min_value
    step = 1 if span <= 12 else 2 if span <= 24 else max(1, round(span / 6))
    out, v = [], style.min_value
    while v <= style.max_value + 1e-9:
        y = y1 - (v - style.min_value) / span * (y1 - y0)
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" stroke={quoteattr(style.grid_color)}/>')
        out.append(f'<text x="{x0 - 6}" y="{y + 4:.1f}" text-anchor="end" fill={quoteattr(style.text_color)}>{_fmt(v)}</text>')
        v += step
    return out


def _y(style: ChartStyle, box: tuple[float, float, float, float], value: float) -> float:
    x0, y0, x1, y1 = box
    value = min(max(value, style.min_value), style.max_value)
    return y1 - (value - style.min_value) / (style.max_value - style.min_value) * (y1 - y0)


def bar_chart(labels: Sequence[str], values: Sequence[float | None], style: ChartStyle | None = None) -> str:
    """Стовпчики: по одному на підпис. `None` малюється як порожнє місце."""
    style = style or ChartStyle()
    if len(labels) != len(values):
        raise ValueError("labels і values різної довжини")
    n = len(labels)
    slot_h = 64 if n > 5 else 30
    box = _frame(style, slot_h)
    x0, y0, x1, y1 = box
    out = _open(style) + _grid(style, box)
    if n:
        slot = (x1 - x0) / n
        bw = max(4.0, min(slot * 0.62, 90.0))
        limit = 14 if n > 5 else 20
        for i, (lab, val) in enumerate(zip(labels, values)):
            cx = x0 + slot * (i + 0.5)
            if val is not None:
                top = _y(style, box, val)
                out.append(f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(y1 - top, 0):.1f}" '
                           f'rx="{style.bar_radius}" fill={quoteattr(style.color_for(i, val))}/>')
                if style.show_values:
                    out.append(f'<text x="{cx:.1f}" y="{top - 5:.1f}" text-anchor="middle" font-weight="bold" '
                               f'fill={quoteattr(style.text_color)}>{_fmt(val)}</text>')
            txt = escape(_short(lab, limit))
            if n > 5:
                out.append(f'<text transform="translate({cx:.1f} {y1 + 14}) rotate(-35)" text-anchor="end" '
                           f'fill={quoteattr(style.text_color)}>{txt}</text>')
            else:
                out.append(f'<text x="{cx:.1f}" y="{y1 + 20}" text-anchor="middle" fill={quoteattr(style.text_color)}>{txt}</text>')
    out.append("</svg>")
    return "\n".join(out)


def line_chart(labels: Sequence[str], values: Sequence[float], style: ChartStyle | None = None) -> str:
    """Лінія з точками (наприклад, оцінки в часі). Колір лінії — перший колір палітри."""
    style = style or ChartStyle()
    if len(labels) != len(values):
        raise ValueError("labels і values різної довжини")
    n = len(values)
    box = _frame(style, 54)
    x0, y0, x1, y1 = box
    out = _open(style) + _grid(style, box)
    pal = style.palette()
    line_color = pal[0] if pal else "#26358F"
    if n:
        xs = [x0 + (x1 - x0) * (0.5 if n == 1 else 0.04 + 0.92 * i / (n - 1)) for i in range(n)]
        ys = [_y(style, box, v) for v in values]
        if n > 1:
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
            out.append(f'<polyline points="{pts}" fill="none" stroke={quoteattr(line_color)} '
                       f'stroke-width="{style.line_width}" stroke-linejoin="round" stroke-linecap="round"/>')
        step = max(1, n // 8)
        for i, (x, y, v) in enumerate(zip(xs, ys, values)):
            dot = style.color_for(i, v) if len(pal) > 1 or not pal else line_color
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{style.point_radius}" fill={quoteattr(dot)}/>')
            if style.show_values and (n <= 14 or i % step == 0):
                out.append(f'<text x="{x:.1f}" y="{y - 9:.1f}" text-anchor="middle" font-weight="bold" '
                           f'fill={quoteattr(style.text_color)}>{_fmt(v)}</text>')
            if i % step == 0 or i == n - 1:
                out.append(f'<text transform="translate({x:.1f} {y1 + 14}) rotate(-35)" text-anchor="end" '
                           f'fill={quoteattr(style.text_color)}>{escape(_short(labels[i], 10))}</text>')
    out.append("</svg>")
    return "\n".join(out)


# ── побудова з моделей ──
def averages_chart(perf: StudentPerformance, style: ChartStyle | None = None) -> str:
    """Середній бал по предметах."""
    subs = [s for s in perf.subjects if s.average is not None]
    return bar_chart([s.short_name or s.name for s in subs], [s.average for s in subs], style)


def marks_chart(schedule: Schedule, style: ChartStyle | None = None, subject: str | None = None) -> str:
    """Оцінки в часі (лише числові). `subject` — частина назви предмета."""
    rows: list[tuple[date | None, int]] = [
        (d, g.value) for d, name, g in schedule.grades()
        if g.value is not None and (not subject or subject.lower() in name.lower())]
    labels = [f"{d.day:02d}.{d.month:02d}" if d else "?" for d, _ in rows]
    return line_chart(labels, [v for _, v in rows], style)


def distribution_chart(values: Sequence[int | None], style: ChartStyle | None = None) -> str:
    """Скільки разів отримано кожну оцінку 1–12."""
    dist = mark_distribution(values)
    top = max(dist.values(), default=0)
    base = style or ChartStyle()
    from dataclasses import replace
    style = replace(base, max_value=max(top, 4), show_values=base.show_values,
                    colors=base.colors if base.colors != "scale" else "ink")
    return bar_chart([str(k) for k in dist], list(dist.values()), style)


def save_svg(path: str | Path, svg: str) -> Path:
    p = Path(path)
    p.write_text(svg, "utf-8")
    return p
