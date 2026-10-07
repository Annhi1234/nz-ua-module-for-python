"""Стилі й теми. Стиль — звичайний набір необов'язкових полів, які зливаються за принципом CSS:

    тема[вид віджета] ← тема[клас] ← Style, переданий у віджет

    Text("Привіт", cls="h1 muted", style=Style(color="#c00"))
    Button("Ок", style=Style(radius=20, bg="#222"))
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Mapping

__all__ = ("Style", "Theme", "box", "NOTEBOOK", "DARK", "mark_color")

Box = int | tuple[int, int] | tuple[int, int, int, int]


def box(v: Box | None) -> tuple[int, int, int, int]:
    """Відступи: число, (вертикальний, горизонтальний) або (верх, право, низ, ліво)."""
    if v is None:
        return 0, 0, 0, 0
    if isinstance(v, (int, float)):
        n = int(v)
        return n, n, n, n
    if len(v) == 2:
        return v[0], v[1], v[0], v[1]
    if len(v) == 4:
        return tuple(int(x) for x in v)  # type: ignore[return-value]
    raise ValueError("відступ: число, (верт, гор) або (верх, право, низ, ліво)")


@dataclass(frozen=True)
class Style:
    """Усі поля необов'язкові: None — «не задано, візьми з теми»."""
    color: str | None = None          # колір тексту, "#RRGGBB"
    bg: str | None = None             # колір тла
    font_size: int | None = None
    bold: bool | None = None
    italic: bool | None = None
    text_align: str | None = None     # start | center | end
    align: str | None = None          # поперечне вирівнювання дітей: start | center | end | stretch
    justify: str | None = None        # поздовжнє: start | center | end | between
    padding: Box | None = None
    margin: Box | None = None
    radius: int | None = None         # заокруглення (Tk його не підтримує)
    border: str | None = None         # колір рамки
    border_width: int | None = None
    border_left: str | None = None    # «поле зошита»: кольорова смужка зліва
    width: int | None = None
    height: int | None = None
    expand: bool | None = None        # зайняти вільне місце в батьківському Row/Column
    gap: int | None = None            # проміжок між дітьми
    wrap: bool | None = None          # Row: переносити на новий рядок

    def merge(self, *others: "Style | Mapping[str, Any] | None") -> "Style":
        """Праві значення перекривають ліві, якщо не None."""
        out = self
        for o in others:
            if o is None:
                continue
            o = Style(**o) if isinstance(o, Mapping) else o
            out = replace(out, **{f.name: getattr(o, f.name) for f in fields(o)
                                  if getattr(o, f.name) is not None})
        return out

    __or__ = merge

    def pad(self) -> tuple[int, int, int, int]:
        return box(self.padding)

    def mar(self) -> tuple[int, int, int, int]:
        return box(self.margin)


def mark_color(value: int | None, theme: "Theme | None" = None) -> str:
    """12-бальна шкала: 1–3 червоний, 4–6 бурштиновий, 7–12 зелений; нечислова — сірий."""
    p = (theme or NOTEBOOK).palette
    if value is None:
        return p["muted"]
    return p["bad"] if value <= 3 else p["mid"] if value <= 6 else p["good"]


@dataclass(frozen=True)
class Theme:
    """Палітра + іменовані стилі. Власну тему роблять через `NOTEBOOK.with_(...)`."""
    name: str
    palette: Mapping[str, str]
    styles: Mapping[str, Style]

    def resolve(self, kind: str, cls: str = "", style: Style | Mapping[str, Any] | None = None) -> Style:
        out = self.styles.get(kind, Style())
        for c in cls.split():
            out = out.merge(self.styles.get("." + c))
        return out.merge(style)

    def color(self, key_or_hex: str | None) -> str | None:
        """'ink' → '#26358F'; '#fff' залишається як є."""
        return self.palette.get(key_or_hex, key_or_hex) if key_or_hex else None

    def with_(self, *, palette: Mapping[str, str] | None = None,
              styles: Mapping[str, Style | Mapping[str, Any]] | None = None, name: str | None = None) -> "Theme":
        """Нова тема з перевизначеними кольорами або стилями (`styles={".card": Style(radius=20)}`)."""
        merged = dict(self.styles)
        for k, v in (styles or {}).items():
            merged[k] = merged.get(k, Style()).merge(v)
        return Theme(name or self.name, {**self.palette, **(palette or {})}, merged)


def _make(name: str, p: dict[str, str]) -> Theme:
    S = Style
    return Theme(name, p, {
        # види віджетів
        "text": S(color=p["fg"], font_size=14),
        "button": S(color=p["ink"], bg=p["card"], font_size=14, bold=True, radius=10, padding=(8, 14),
                    border=p["ink"], border_width=1, text_align="center"),
        "chip": S(color="#FFFFFF", bg=p["muted"], font_size=15, bold=True, radius=8, padding=(3, 9)),
        "input": S(color=p["fg"], bg=p["card"], font_size=14, radius=10, border=p["line"], border_width=1,
                   padding=(8, 10)),
        "card": S(bg=p["card"], radius=12, padding=12, margin=(0, 0, 10, 0), border_left=p["margin"]),
        "screen": S(bg=p["bg"]),
        "navbar": S(bg=p["card"], border=p["line"], padding=(6, 0)),
        "table": S(bg=p["card"], radius=12, border=p["line"], border_width=1),
        "chart": S(bg=p["card"], radius=12, padding=8, margin=(0, 0, 10, 0)),
        "dialog": S(bg=p["card"], padding=16, radius=14),
        "divider": S(bg=p["line"]),
        # класи (cls="…")
        ".h1": S(font_size=34, bold=True, color=p["ink"]),
        ".h2": S(font_size=20, bold=True, color=p["ink"]),
        ".h3": S(font_size=17, bold=True, color=p["ink"]),
        ".title": S(font_size=16, bold=True, color=p["graphite"]),
        ".muted": S(color=p["muted"], font_size=12),
        ".small": S(font_size=12),
        ".big": S(font_size=44, bold=True),
        ".error": S(color=p["bad"], font_size=13),
        ".good": S(color=p["good"]),
        ".bad": S(color=p["bad"]),
        ".primary": S(bg=p["ink"], color="#FFFFFF", border=p["ink"]),
        ".outline": S(bg=p["card"], color=p["ink"], border=p["ink"], border_width=1),
        ".text": S(bg="", color=p["ink"], border_width=0),
        ".banner": S(bg=p["banner_bg"], color=p["banner_fg"], radius=8, padding=8, margin=(0, 0, 10, 0), font_size=13),
        ".flat": S(border_left="", border_width=0, padding=0, margin=0, bg=""),
        ".table-head": S(bg=p["bg"], color=p["ink"], bold=True, font_size=13, padding=(8, 10)),
        ".table-cell": S(font_size=14, padding=(8, 10)),
        ".table-zebra": S(bg=p["zebra"]),
    })


NOTEBOOK = _make("notebook", {
    "bg": "#F4F6FB", "card": "#FFFFFF", "fg": "#1D2433", "graphite": "#1D2433", "ink": "#26358F",
    "margin": "#C8372D", "muted": "#6B7385", "line": "#DDE2EE", "zebra": "#F8F9FD",
    "good": "#2F855A", "mid": "#B7791F", "bad": "#C8372D",
    "banner_bg": "#FFF3D6", "banner_fg": "#7A4B00"})

DARK = _make("dark", {
    "bg": "#12151F", "card": "#1C2130", "fg": "#E6E9F2", "graphite": "#E6E9F2", "ink": "#9DB0FF",
    "margin": "#E0685F", "muted": "#9AA3B8", "line": "#2B3247", "zebra": "#202637",
    "good": "#48BB78", "mid": "#ECC94B", "bad": "#F56565",
    "banner_bg": "#4A3B12", "banner_fg": "#F6E3A8"})
