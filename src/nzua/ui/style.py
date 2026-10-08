"""Стилі й теми. Стиль — звичайний набір необов'язкових полів, які зливаються за принципом CSS:

    тема[вид віджета] ← тема[клас] ← Style, переданий у віджет

    Text("Привіт", cls="h1 muted", style=Style(color="#c00"))
    Button("Ок", style=Style(radius=20, bg="#222"))
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any, Mapping

__all__ = ("Style", "Theme", "box", "subject_key", "lighten", "mix", "valid_hex", "NOTEBOOK", "DARK", "AMOLED", "mark_color", "make_theme", "ACCENTS",
           "MODES", "DENSITIES", "MARK_SCHEMES")

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
    shadow: int | None = None         # м'яка тінь, «висота» 0–4 (Flet; інші бекенди ігнорують)
    gradient: tuple | None = None     # (колір1, колір2) діагональний градієнт поверх bg (Flet)

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


def valid_hex(v: Any) -> bool:
    """`#RRGGBB` (регістр неважливий)."""
    return isinstance(v, str) and len(v) == 7 and v[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in v[1:])


def mix(a: str, b: str, t: float) -> str:
    """Змішує два кольори: t=0 → a, t=1 → b."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


def lighten(hex_: str, t: float = 0.4) -> str:
    return mix(hex_, "#FFFFFF", t)


# кольори предметів: 12 відтінків, окремо для світлих і темних тем (білий/темний текст на них читабельний)
_SUBJ_LIGHT = ("#3F51B5", "#00897B", "#E64A19", "#8E24AA", "#2E7D32", "#C2185B", "#0277BD", "#F57C00", "#5D4037",
               "#00838F", "#7B1FA2", "#546E7A")
_SUBJ_DARK = ("#8C9EFF", "#4DB6AC", "#FF8A65", "#CE93D8", "#81C784", "#F48FB1", "#4FC3F7", "#FFB74D", "#BCAAA4",
              "#4DD0E1", "#B39DDB", "#90A4AE")


def subject_key(name: str) -> str:
    """Ключ палітри (`subj0`…`subj11`) для предмета: той самий предмет завжди має той самий колір."""
    import zlib
    return f"subj{zlib.crc32((name or '').strip().lower().encode('utf-8')) % len(_SUBJ_LIGHT)}"


def _subject_palette(dark: bool) -> dict[str, str]:
    cols = _SUBJ_DARK if dark else _SUBJ_LIGHT
    return {**{f"subj{i}": c for i, c in enumerate(cols)}, "on_subj": "#101424" if dark else "#FFFFFF"}


@dataclass(frozen=True)
class Theme:
    """Палітра + іменовані стилі. Власну тему роблять через `NOTEBOOK.with_(...)`."""
    name: str
    palette: Mapping[str, str]
    styles: Mapping[str, Style]
    font_scale: float = 1.0    # множник розміру шрифту й ширин, що залежать від тексту (0.8–1.6)
    space_scale: float = 1.0   # множник відступів і проміжків («щільність»)
    dark: bool = False         # темна палітра (для системних елементів на кшталт Material)
    overrides: Mapping[str, Style] = field(default_factory=dict)  # власні стилі поверх базових
    derived: bool = False      # стилі виведені з палітри → при зміні палітри перераховуються

    def resolve(self, kind: str, cls: str = "", style: Style | Mapping[str, Any] | None = None) -> Style:
        out = self.styles.get(kind, Style())
        for c in cls.split():
            out = out.merge(self.styles.get("." + c))
        return self._scaled(out.merge(style))

    def _scaled(self, st: Style) -> Style:
        """Застосовує `font_scale` і `space_scale`; при 1.0 нічого не змінює."""
        fs, ss = self.font_scale, self.space_scale
        if fs == 1.0 and ss == 1.0:
            return st
        ch: dict[str, Any] = {}
        if fs != 1.0:
            if st.font_size:
                ch["font_size"] = max(8, round(st.font_size * fs))
            if st.width:
                ch["width"] = max(1, round(st.width * fs))
        if ss != 1.0:
            for f in ("padding", "margin"):
                v = getattr(st, f)
                if v is not None:
                    ch[f] = tuple(round(x * ss) for x in box(v))
            if st.gap:
                ch["gap"] = max(0, round(st.gap * ss))
        return replace(st, **ch) if ch else st

    def color(self, key_or_hex: str | None) -> str | None:
        """'ink' → '#26358F'; '#fff' залишається як є."""
        return self.palette.get(key_or_hex, key_or_hex) if key_or_hex else None

    def with_(self, *, palette: Mapping[str, str] | None = None,
              styles: Mapping[str, Style | Mapping[str, Any]] | None = None, name: str | None = None,
              font_scale: float | None = None, space_scale: float | None = None) -> "Theme":
        """Нова тема з перевизначеними кольорами, стилями або масштабом (`styles={".card": Style(radius=20)}`).

        Зміна палітри перефарбовує й похідні стилі (заголовки, кнопки…), а власні `styles` лишаються поверх них.
        """
        over = dict(self.overrides)
        for k, v in (styles or {}).items():
            over[k] = over.get(k, Style()).merge(v)
        pal = {**self.palette, **(palette or {})}
        if palette and "ink" in palette and "ink2" not in palette:   # похідний другий колір градієнта
            pal["ink2"] = mix(pal["ink"], "#FFFFFF" if self.dark else "#000000", 0.3)
        merged = _make_styles(pal) if (self.derived and palette) else dict(self.styles)
        for k, v in over.items():
            merged[k] = merged.get(k, Style()).merge(v)
        return Theme(name or self.name, pal, merged,
                     self.font_scale if font_scale is None else font_scale,
                     self.space_scale if space_scale is None else space_scale, self.dark, over, self.derived)


def _make(name: str, p: dict[str, str]) -> Theme:
    dark = name in ("dark", "amoled")
    p = {**_subject_palette(dark), "ink2": mix(p["ink"], "#FFFFFF" if dark else "#000000", 0.3), **p}
    return Theme(name, p, _make_styles(p), derived=True)


def _make_styles(p: Mapping[str, str]) -> dict[str, Style]:
    S = Style
    return {
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
        ".primary": S(bg=p["ink"], color=p.get("on_ink", "#FFFFFF"), border=p["ink"]),
        ".outline": S(bg=p["card"], color=p["ink"], border=p["ink"], border_width=1),
        ".text": S(bg="", color=p["ink"], border_width=0),
        ".banner": S(bg=p["banner_bg"], color=p["banner_fg"], radius=8, padding=8, margin=(0, 0, 10, 0), font_size=13),
        ".flat": S(border_left="", border_width=0, padding=0, margin=0, bg=""),
        ".table-head": S(bg=p["bg"], color=p["ink"], bold=True, font_size=13, padding=(8, 10)),
        ".table-cell": S(font_size=14, padding=(8, 10)),
        ".table-zebra": S(bg=p["zebra"]),
        # «геройська» картка: градієнт від акценту; на бекендах без градієнтів лишається суцільний колір
        ".hero": S(bg=p["ink"], gradient=(p["ink"], p.get("ink2", p["ink"])), color=p.get("on_ink", "#FFFFFF"),
                   radius=20, padding=(16, 16), margin=(0, 0, 10, 0), shadow=2, border_left=""),
    }


NOTEBOOK = _make("notebook", {
    "bg": "#F4F6FB", "card": "#FFFFFF", "fg": "#1D2433", "graphite": "#1D2433", "ink": "#26358F",
    "margin": "#C8372D", "muted": "#6B7385", "line": "#DDE2EE", "zebra": "#F8F9FD",
    "good": "#2F855A", "mid": "#B7791F", "bad": "#C8372D",
    "banner_bg": "#FFF3D6", "banner_fg": "#7A4B00", "on_ink": "#FFFFFF"})

DARK = _make("dark", {
    "bg": "#12151F", "card": "#1C2130", "fg": "#E6E9F2", "graphite": "#E6E9F2", "ink": "#9DB0FF",
    "margin": "#E0685F", "muted": "#9AA3B8", "line": "#2B3247", "zebra": "#202637",
    "good": "#48BB78", "mid": "#ECC94B", "bad": "#F56565",
    "banner_bg": "#4A3B12", "banner_fg": "#F6E3A8", "on_ink": "#101424"})

AMOLED = _make("amoled", {
    "bg": "#000000", "card": "#0F1117", "fg": "#E8EBF4", "graphite": "#E8EBF4", "ink": "#9DB0FF",
    "margin": "#E0685F", "muted": "#8E97AD", "line": "#232734", "zebra": "#0A0C11",
    "good": "#48BB78", "mid": "#ECC94B", "bad": "#F56565",
    "banner_bg": "#3A2E0C", "banner_fg": "#F6E3A8", "on_ink": "#101424"})
DARK = replace(DARK, dark=True)
AMOLED = replace(AMOLED, dark=True)

# ───────────────────────── налаштовувані теми ─────────────────────────
MODES = {"auto": "Як у системі", "light": "Світла", "dark": "Темна", "amoled": "Чорна (AMOLED)"}
DENSITIES = {"compact": "Щільно", "normal": "Звичайно", "roomy": "Просторо"}
_DENSITY = {"compact": 0.8, "normal": 1.0, "roomy": 1.25}
# акцент: (назва, колір для світлої теми, колір для темної)
ACCENTS: dict[str, tuple[str, str, str]] = {
    "indigo": ("Індиго", "#26358F", "#9DB0FF"), "blue": ("Синій", "#1565C0", "#7DB7FF"),
    "teal": ("Бірюзовий", "#00796B", "#5FD3C2"), "green": ("Зелений", "#2E7D32", "#7FD38A"),
    "orange": ("Помаранчевий", "#C75A00", "#FFB066"), "red": ("Червоний", "#C62828", "#FF8A80"),
    "pink": ("Рожевий", "#AD1457", "#FF8EC0"), "purple": ("Фіолетовий", "#6A1B9A", "#D1A3FF"),
    "graphite": ("Графіт", "#37474F", "#B0BEC5"),
}
# схеми кольорів оцінок: (назва, добре, середньо, погано); «для дальтоніків» — палітра Окабе—Іто
MARK_SCHEMES: dict[str, tuple[str, str, str, str]] = {
    "classic": ("Класична", "", "", ""),
    "colorblind": ("Для дальтоніків", "#0072B2", "#E69F00", "#D55E00"),
    "soft": ("М'яка", "#3C9D7A", "#D9A441", "#D9604F"),
}


def make_theme(mode: str = "light", accent: str = "indigo", *, font_scale: float = 1.0, density: str = "normal",
               radius: int | None = None, stripe: bool = True, mark_scheme: str = "classic",
               shadows: bool = True, accent_hex: str = "") -> Theme:
    """Збирає тему з налаштувань: режим, акцентний колір, масштаб тексту, щільність, заокруглення, тіні.

        make_theme("amoled", "teal", font_scale=1.2, density="compact", radius=20, stripe=False)
        make_theme("light", "custom", accent_hex="#FF5722")    # свій акцентний колір
    """
    base = {"dark": DARK, "amoled": AMOLED}.get(mode, NOTEBOOK)
    pal: dict[str, str] = {}
    ink = ""
    if accent == "custom" and valid_hex(accent_hex):
        ink = lighten(accent_hex.upper(), 0.35) if base.dark else accent_hex.upper()
    elif accent in ACCENTS:
        ink = ACCENTS[accent][2] if base.dark else ACCENTS[accent][1]
    if ink:
        pal["ink"] = ink
        pal["margin"] = ink if accent != "indigo" else base.palette["margin"]
    if mark_scheme in MARK_SCHEMES and MARK_SCHEMES[mark_scheme][1]:
        _, good, mid, bad = MARK_SCHEMES[mark_scheme]
        pal.update(good=good, mid=mid, bad=bad)
    styles: dict[str, Style] = {}
    if radius is not None:
        r = max(0, int(radius))
        for k in ("card", "button", "input", "table", "chart", "dialog", ".banner"):
            styles[k] = Style(radius=r)
        styles["chip"] = Style(radius=min(r, 14))
        styles[".hero"] = Style(radius=r + 8)
    card = styles.get("card", Style())
    if not stripe:
        card = card.merge(Style(border_left=""))
    if shadows and not base.dark:
        card = card.merge(Style(shadow=1))
    styles["card"] = card
    if not shadows:
        styles[".hero"] = styles.get(".hero", Style()).merge(Style(shadow=0))
    th = base.with_(palette=pal, styles=styles,
                    font_scale=min(max(float(font_scale), 0.8), 1.6),
                    space_scale=_DENSITY.get(density, 1.0))
    return replace(th, name=base.name)
