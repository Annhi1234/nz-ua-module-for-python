"""Статичний експорт дерева віджетів: у HTML (перегляд у браузері, скріншоти) і в текст (консоль, тести)."""
from __future__ import annotations

import unicodedata
from html import escape
from pathlib import Path
from typing import Any

from .style import NOTEBOOK, Style, Theme
from .widgets import (Button, Card, Cell, Chart, Chip, Column, Dialog, Divider, Dropdown, ICONS, Image,
                      Input, NavBar, Progress, Row, Screen, Slider, Spacer, Switch, Table, Text, Widget)

__all__ = ("to_html", "to_text", "save_html")


# ───────────────────────── HTML ─────────────────────────
def _css(st: Style, th: Theme, *, flex_child: bool = False) -> str:
    c = th.color
    out: list[str] = []
    add = out.append
    if st.color:
        add(f"color:{c(st.color)}")
    if st.bg:
        add(f"background:{c(st.bg)}")
    if st.font_size:
        add(f"font-size:{st.font_size}px")
    if st.bold is not None:
        add(f"font-weight:{'700' if st.bold else '400'}")
    if st.italic:
        add("font-style:italic")
    if st.text_align:
        add("text-align:" + {"start": "left", "end": "right"}.get(st.text_align, st.text_align))
    t, r, b, l = st.pad()
    if t or r or b or l:
        add(f"padding:{t}px {r}px {b}px {l}px")
    t, r, b, l = st.mar()
    if t or r or b or l:
        add(f"margin:{t}px {r}px {b}px {l}px")
    if st.radius:
        add(f"border-radius:{st.radius}px")
    if st.border and st.border_width:
        add(f"border:{st.border_width}px solid {c(st.border)}")
    if st.border_left:
        add(f"border-left:4px solid {c(st.border_left)}")
    if st.width:
        add(f"width:{st.width}px")
    if st.height:
        add(f"height:{st.height}px" if st.height < 4000 else "")
    if st.expand:
        add("flex:1 1 0;min-width:0")
    return ";".join(x for x in out if x)


_AL = {"start": "flex-start", "center": "center", "end": "flex-end", "stretch": "stretch", "between": "space-between"}


def _h(w: Widget, th: Theme) -> str:
    st = th.resolve(w.kind, w.cls, w.style)
    if isinstance(w, (Row, Column, Card)):
        direction = "row" if isinstance(w, Row) else "column"
        flex = (f"display:flex;flex-direction:{direction};box-sizing:border-box;"
                f"gap:{st.gap or 0}px;align-items:{_AL.get(st.align or ('center' if direction == 'row' else 'stretch'), 'stretch')};"
                f"justify-content:{_AL.get(st.justify or 'start', 'flex-start')};"
                f"{'flex-wrap:wrap;' if st.wrap else ''}{'overflow:auto;' if getattr(w, 'scroll', False) else ''}")
        onclick = " style='cursor:pointer'" if getattr(w, "on_click", None) else ""
        return f"<div{onclick} style=\"{flex}{_css(st, th)}\">{''.join(_h(c, th) for c in w.children)}</div>"
    if isinstance(w, Text):
        return f"<div style=\"white-space:pre-wrap;{_css(st, th)}\">{escape(w.text)}</div>"
    if isinstance(w, Button):
        label = (ICONS.get(w.icon, "") + " " if w.icon else "") + escape(w.text)
        return f"<button {'disabled ' if w.disabled else ''}style=\"cursor:pointer;font-family:inherit;{_css(st, th)}\">{label.strip()}</button>"
    if isinstance(w, Chip):
        bg = th.color(w.color) or th.color(st.bg)
        return f"<span style=\"display:inline-block;{_css(st, th)};background:{bg}\">{escape(w.text)}</span>"
    if isinstance(w, Input):
        v = escape(w.value or "")
        lab = f"<label style='font-size:12px;opacity:.7'>{escape(w.label)}</label>" if w.label else ""
        if w.multiline:
            return f"{lab}<textarea rows={w.lines} style=\"font-family:inherit;{_css(st, th)}\">{v}</textarea>"
        return f"{lab}<input type=\"{'password' if w.password else 'text'}\" value=\"{v}\" style=\"font-family:inherit;{_css(st, th)}\">"
    if isinstance(w, Switch):
        return f"<label><input type=checkbox {'checked' if w.value else ''}> {escape(w.label)}</label>"
    if isinstance(w, Dropdown):
        opts = "".join(f"<option value=\"{escape(k)}\" {'selected' if k == w.value else ''}>{escape(t)}</option>" for k, t in w.options)
        return f"<label>{escape(w.label)} <select>{opts}</select></label>"
    if isinstance(w, Slider):
        return (f"<label>{escape(w.label)} <input type=range min={w.min} max={w.max} step={w.step} "
                f"value={w.value}></label>")
    if isinstance(w, Progress):
        return f"<progress {'value=' + str(w.value) if w.value is not None else ''} max=1 style='width:100%'></progress>"
    if isinstance(w, Divider):
        return f"<div style=\"height:1px;margin:6px 0;{_css(st, th)}\"></div>"
    if isinstance(w, Spacer):
        return f"<div style=\"{_css(st, th)}\"></div>"
    if isinstance(w, Image):
        return w.svg or f"<img src=\"{escape(w.path or '')}\">"
    if isinstance(w, Chart):
        return f"<div style=\"{_css(st, th)}\">{w.svg(th)}</div>"
    if isinstance(w, Table):
        return _table_html(w, th, st)
    if isinstance(w, NavBar):
        items = "".join(
            f"<div style=\"flex:1;text-align:center;font-size:12px;"
            f"color:{th.color('ink') if i.key == w.selected else th.color('muted')};"
            f"font-weight:{'700' if i.key == w.selected else '400'}\"><div style='font-size:20px'>"
            f"{ICONS.get(i.icon, '•')}</div>{escape(i.label)}</div>" for i in w.items)
        return f"<div style=\"display:flex;{_css(st, th)}\">{items}</div>"
    if isinstance(w, Screen):
        nav = _h(w.nav, th) if w.nav else ""
        return (f"<div style=\"display:flex;flex-direction:column;min-height:100vh;{_css(st, th)}\">"
                f"<div style=\"flex:1;box-sizing:border-box\">{_h(w.body, th)}</div>{nav}</div>")
    if isinstance(w, Dialog):
        body = _h(w.content, th) if w.content else ""
        acts = "".join(_h(a, th) for a in w.actions)
        return (f"<div style=\"box-shadow:0 8px 30px #0004;{_css(st, th)}\"><h3>{escape(w.title)}</h3>{body}"
                f"<div style='display:flex;gap:8px;justify-content:flex-end;margin-top:12px'>{acts}</div></div>")
    return f"<div>{escape(repr(w))}</div>"


def _table_html(w: Table, th: Theme, st: Style) -> str:
    def col_style(c) -> str:
        return f"width:{c.width}px" if c.width else f"width:{100 * c.flex // max(1, sum(x.flex for x in w.columns if not x.width))}%"

    head_st = th.resolve("text", "table-head")
    cell_st = th.resolve("text", "table-cell")
    zebra = th.resolve("text", "table-zebra")
    rows_html = []
    for i, row in enumerate(w.rows):
        tds = []
        for c, raw in zip(w.columns, row):
            cell: Cell = w.cell(raw)
            cst = cell_st.merge(zebra if w.zebra and i % 2 else None, th.resolve("text", cell.cls), cell.style)
            inner = _h(cell.widget, th) if cell.widget else escape(str(cell.text))
            tds.append(f"<td style=\"text-align:{ {'start': 'left', 'end': 'right'}.get(c.align, c.align) };"
                       f"{_css(cst, th)}\">{inner}</td>")
        rows_html.append(f"<tr>{''.join(tds)}</tr>")
    if not w.rows:
        rows_html.append(f"<tr><td colspan={len(w.columns)} style='padding:16px;text-align:center;opacity:.6'>{escape(w.empty)}</td></tr>")
    head = ""
    if w.header:
        ths = "".join(f"<th style=\"text-align:{ {'start': 'left', 'end': 'right'}.get(c.align, c.align) };{col_style(c)};{_css(head_st, th)}\">{escape(c.title)}</th>" for c in w.columns)
        head = f"<thead><tr>{ths}</tr></thead>"
    return (f"<table style=\"border-collapse:collapse;width:100%;overflow:hidden;{_css(st, th)}\">"
            f"{head}<tbody>{''.join(rows_html)}</tbody></table>")


def to_html(root: Widget, theme: Theme = NOTEBOOK, *, title: str = "nzua", phone: bool = True) -> str:
    """Повна HTML-сторінка. `phone=True` — вузька колонка, як на телефоні."""
    bg = theme.palette["bg"]
    frame = "max-width:420px;margin:0 auto;box-shadow:0 0 30px #0002;" if phone else ""
    return (f"<!doctype html><html lang=uk><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{escape(title)}</title><body style=\"margin:0;background:{bg};font-family:Roboto,Arial,sans-serif\">"
            f"<div style=\"{frame}\">{_h(root, theme)}</div></body></html>")


def save_html(root: Widget, path: str | Path, theme: Theme = NOTEBOOK, **kw: Any) -> Path:
    p = Path(path)
    p.write_text(to_html(root, theme, **kw), "utf-8")
    return p


# ───────────────────────── текст ─────────────────────────
def _w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _pad(s: str, n: int, align: str = "start") -> str:
    gap = max(0, n - _w(s))
    return " " * gap + s if align == "end" else s + " " * gap if align == "start" else " " * (gap // 2) + s + " " * (gap - gap // 2)


def to_text(w: Widget, theme: Theme = NOTEBOOK, indent: str = "") -> str:
    """Просте текстове подання (консоль, юніт-тести інтерфейсу)."""
    t = lambda x: to_text(x, theme, indent)  # noqa: E731
    if isinstance(w, Screen):
        return "\n".join(filter(None, [t(w.body), "─" * 30 if w.nav else "", t(w.nav) if w.nav else ""]))
    if isinstance(w, Row):
        return "  ".join(x for x in (t(c) for c in w.children) if x)
    if isinstance(w, (Column, Card)):
        body = "\n".join(x for x in (t(c) for c in w.children) if x)
        return "\n".join("│ " + ln for ln in body.splitlines()) if isinstance(w, Card) else body
    if isinstance(w, Text):
        return w.text
    if isinstance(w, Button):
        return f"[ {(ICONS.get(w.icon, '') + ' ') if w.icon else ''}{w.text} ]"
    if isinstance(w, Chip):
        return f"‹{w.text}›"
    if isinstance(w, Input):
        shown = "•" * len(w.value or "") if w.password else (w.value or "")
        return f"{w.label}: [{shown}]"
    if isinstance(w, Switch):
        return f"[{'x' if w.value else ' '}] {w.label}"
    if isinstance(w, Dropdown):
        cur = dict(w.options).get(w.value or "", w.value or "")
        return f"{w.label}: ‹{cur}▾›"
    if isinstance(w, Slider):
        return f"{w.label}: {w.value}"
    if isinstance(w, Progress):
        return "…" if w.value is None else f"[{'█' * int(w.value * 20):<20}]"
    if isinstance(w, Divider):
        return "─" * 30
    if isinstance(w, Chart):
        pairs = [(l, v) for l, v in zip(w.labels, w.values) if v is not None]
        width = max((_w(str(l)) for l, _ in pairs), default=0)
        return "\n".join(f"{_pad(str(l), width)} {'█' * int(round(v / w.max_value * 24))} {v:g}" for l, v in pairs)
    if isinstance(w, Table):
        cells = [[(w.cell(c).widget and to_text(w.cell(c).widget, theme)) or str(w.cell(c).text) for c in r] for r in w.rows]
        widths = [max([_w(c.title)] + [_w(r[i]) for r in cells if i < len(r)]) for i, c in enumerate(w.columns)]
        line = lambda r: "  ".join(_pad(x, wd, c.align) for x, wd, c in zip(r, widths, w.columns)).rstrip()  # noqa: E731
        out = [line([c.title for c in w.columns]), "  ".join("─" * x for x in widths)] if w.header else []
        out += [line(r) for r in cells] or [f"({w.empty})"]
        return "\n".join(out)
    if isinstance(w, NavBar):
        return "  ".join(f"{'▶' if i.key == w.selected else ' '}{ICONS.get(i.icon, '')}{i.label}" for i in w.items)
    if isinstance(w, Dialog):
        return "\n".join([f"╔ {w.title}", *(("║ " + ln) for ln in (t(w.content).splitlines() if w.content else [])),
                          "╚ " + " ".join(t(a) for a in w.actions)])
    return ""
