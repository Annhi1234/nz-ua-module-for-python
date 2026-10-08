"""Бекенд Tkinter (входить до стандартної бібліотеки Python).

Обмеження Tk: немає заокруглених кутів (`radius` ігнорується) і SVG (графіки малюються на Canvas).
Кнопки зроблено з Label, щоб кольори однаково працювали на Windows, Linux і macOS.
"""
from __future__ import annotations

import queue
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Any, Callable

from ..app import Backend
from ..style import Style, Theme
from ..widgets import (Button, Card, Cell, Chart, Chip, Column, Dialog, Divider, Dropdown, ICONS, Image, Input,
                       NavBar, Progress, Row, Screen, Slider, Spacer, Switch, Table, Text, Widget)

_ANCHOR = {"start": "w", "center": "center", "end": "e"}
_CROSS_COL = {"start": "w", "center": "center", "end": "e"}
_CROSS_ROW = {"start": "n", "center": "center", "end": "s"}


class _Scroll(tk.Frame):
    """Прокручуваний контейнер: Canvas + внутрішній Frame."""

    def __init__(self, parent: tk.Misc, bg: str) -> None:
        super().__init__(parent, bg=bg, highlightthickness=0)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg, highlightthickness=0)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", self._bind_wheel)
            w.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _e: Any = None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))

    def _unbind_wheel(self, _e: Any = None) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(seq)

    def _wheel(self, e: Any) -> None:
        step = -1 if e.delta > 0 else 1
        if abs(e.delta) >= 120:
            step *= max(1, abs(e.delta) // 120)
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(step * 3, "units")


class _Flow(tk.Frame):
    """Рядок із переносом (як flex-wrap): діти розташовуються через place()."""

    def __init__(self, parent: tk.Misc, bg: str, gap: int) -> None:
        super().__init__(parent, bg=bg, highlightthickness=0)
        self.gap = gap
        self.kids: list[tk.Widget] = []
        self.bind("<Configure>", self._layout)

    def add(self, w: tk.Widget) -> None:
        self.kids.append(w)

    def _layout(self, _e: Any = None) -> None:
        width = max(self.winfo_width(), 1)
        x = y = row_h = 0
        for k in self.kids:
            kw, kh = k.winfo_reqwidth(), k.winfo_reqheight()
            if x and x + kw > width:
                x, y, row_h = 0, y + row_h + self.gap, 0
            k.place(x=x, y=y)
            x += kw + self.gap
            row_h = max(row_h, kh)
        h = y + row_h
        if self.winfo_reqheight() != h:
            self.configure(height=h)


class TkBackend(Backend):
    name = "tk"

    def __init__(self) -> None:
        super().__init__()
        self.win: tk.Tk | None = None
        self._q: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._content: tk.Widget | None = None
        self._dlg: tk.Toplevel | None = None
        self._toast: tk.Label | None = None
        self._fonts: dict[tuple, tkfont.Font] = {}
        self._focus_name: str | None = None
        self._vars: list[Any] = []  # тримаємо посилання на Tk-змінні (інакше їх збирає GC)

    # ───── життєвий цикл ─────
    @property
    def theme(self) -> Theme:
        return self.app.theme  # type: ignore[union-attr]

    def run(self, app) -> None:
        self.app = app
        self.win = tk.Tk()
        self.win.title(app.title)
        w, h = app.size
        self.win.geometry(f"{w}x{h}")
        self.win.minsize(320, 480)
        self._family = tkfont.nametofont("TkDefaultFont").actual("family")
        self.win.protocol("WM_DELETE_WINDOW", self.quit)
        self._resize_job: Any = None
        self.win.bind("<Configure>", self._on_configure, add="+")   # адаптивна розкладка
        self.win.after(25, self._poll)
        self.win.after(0, app._ready)
        try:
            self.win.mainloop()
        finally:
            self._bridge.close()

    def _on_configure(self, e: Any) -> None:
        """Повідомляє застосунок про новий розмір вікна (із затримкою, щоб не перемальовувати на кожен піксель)."""
        if e.widget is not self.win or self.win is None:
            return
        if self._resize_job is not None:
            self.win.after_cancel(self._resize_job)
        w, h = e.width, e.height
        self._resize_job = self.win.after(150, lambda: self.app.set_size(w, h) if self.app else None)

    def quit(self) -> None:
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
            self.win = None

    def call_soon(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)  # потокобезпечна черга; Tk опитує її з головного потоку

    def _poll(self) -> None:
        if self.win is None:
            return
        try:
            while True:
                self._q.get_nowait()()
        except queue.Empty:
            pass
        except Exception as e:  # noqa: BLE001 — помилка обробника не повинна зупиняти цикл
            self.app.handle_error(e)  # type: ignore[union-attr]
        if self.win is not None:
            self.win.after(25, self._poll)

    # ───── допоміжне ─────
    def _c(self, key: str | None, default: str | None = None) -> str | None:
        return self.theme.color(key) if key else default

    def _font(self, st: Style) -> tkfont.Font:
        key = (st.font_size or 14, bool(st.bold), bool(st.italic))
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(family=self._family, size=-key[0],
                                           weight="bold" if key[1] else "normal",
                                           slant="italic" if key[2] else "roman")
        return self._fonts[key]

    def _run(self, fn: Callable[..., Any] | None, *args: Any) -> None:
        self.app.dispatch(fn, *args)  # type: ignore[union-attr]

    def _bind_click(self, w: tk.Misc, fn: Callable[[Any], None]) -> None:
        w.bind("<Button-1>", fn, add="+")
        try:
            w.configure(cursor="hand2")
        except tk.TclError:
            pass
        for c in w.winfo_children():
            self._bind_click(c, fn)

    # ───── малювання ─────
    def mount(self, root: Widget) -> None:
        assert self.win is not None
        if self._content is not None:
            self._content.destroy()
        st = self.theme.resolve("screen", root.cls, root.style)
        self.win.configure(bg=self._c(st.bg, "#FFFFFF"))
        self._content = self._r(root, self.win, self._c(st.bg, "#FFFFFF"))
        self._content.pack(fill="both", expand=True)
        if self._focus_name:
            for w in root.walk():
                if isinstance(w, Input) and w.name == self._focus_name and hasattr(w, "_tk_entry"):
                    w._tk_entry.focus_set()  # type: ignore[attr-defined]
                    break

    def _r(self, w: Widget, parent: tk.Misc, bg: str) -> tk.Widget:
        """Створює Tk-віджет для опису `w`. `bg` — колір тла батька (для прозорих елементів)."""
        st = self.theme.resolve(w.kind, w.cls, w.style)
        fixed = (st.width or st.height) and isinstance(w, (Text, Chip, Button, Image))
        if not fixed:
            return self._build(w, parent, bg, st)
        # Tk міряє width у символах, тому точний розмір у пікселях робимо рамкою без розповсюдження розмірів
        holder = tk.Frame(parent, bg=bg, highlightthickness=0)
        inner = self._build(w, holder, bg, st)
        inner.pack(fill="both", expand=True)
        holder.update_idletasks()
        holder.configure(width=st.width or inner.winfo_reqwidth(), height=st.height or inner.winfo_reqheight())
        holder.pack_propagate(False)
        return holder

    def _build(self, w: Widget, parent: tk.Misc, bg: str, st: Style) -> tk.Widget:
        th = self.theme
        own_bg = self._c(st.bg) or bg
        if isinstance(w, Screen):
            return self._screen(w, parent, st, own_bg)
        if isinstance(w, (Row, Column, Card)):
            return self._container(w, parent, st, own_bg)
        if isinstance(w, Text):
            return self._text(w, parent, st, own_bg)
        if isinstance(w, Button):
            return self._button(w, parent, st, bg)
        if isinstance(w, Chip):
            lbl = tk.Label(parent, text=w.text, font=self._font(st), fg=self._c(st.color, "#FFFFFF"),
                           bg=self._c(w.color) or own_bg, padx=st.pad()[1], pady=st.pad()[0])
            return lbl
        if isinstance(w, Input):
            return self._input(w, parent, st, own_bg)
        if isinstance(w, Switch):
            return self._switch(w, parent, st, bg)
        if isinstance(w, Dropdown):
            return self._dropdown(w, parent, st, bg)
        if isinstance(w, Slider):
            return self._slider(w, parent, st, bg)
        if isinstance(w, Progress):
            pb = ttk.Progressbar(parent, mode="indeterminate" if w.value is None else "determinate", maximum=1)
            if w.value is None:
                pb.start(15)
            else:
                pb["value"] = w.value
            return pb
        if isinstance(w, Divider):
            return tk.Frame(parent, height=1, bg=self._c(st.bg, "#DDDDDD"))
        if isinstance(w, Spacer):
            return tk.Frame(parent, bg=bg, width=st.width or 0, height=st.height or 0)
        if isinstance(w, Image):
            return self._image(w, parent, st, bg)
        if isinstance(w, Chart):
            return self._chart(w, parent, st, own_bg)
        if isinstance(w, Table):
            return self._table(w, parent, st, own_bg)
        if isinstance(w, NavBar):
            return self._navbar(w, parent, st, own_bg)
        return tk.Label(parent, text=repr(w), bg=bg)

    # — контейнери —
    def _screen(self, w: Screen, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        frame = tk.Frame(parent, bg=bg, highlightthickness=0)
        if w.nav:
            self._r(w.nav, frame, bg).pack(side="bottom", fill="x")
        t, r, b, l = st.pad()
        if w.scroll:
            sc = _Scroll(frame, bg)
            sc.pack(side="top", fill="both", expand=True)
            host: tk.Misc = sc.inner
        else:
            host = frame
        self._r(w.body, host, bg).pack(side="top", fill="both", expand=True, padx=(l, r), pady=(t, b))
        return frame

    def _container(self, w: Widget, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        horizontal = isinstance(w, Row)
        bw = st.border_width or 0
        outer = tk.Frame(parent, bg=bg, highlightthickness=bw, highlightbackground=self._c(st.border, bg),
                         highlightcolor=self._c(st.border, bg))
        host: tk.Misc = outer
        if st.border_left:
            tk.Frame(outer, bg=self._c(st.border_left), width=4).pack(side="left", fill="y")
            inner = tk.Frame(outer, bg=bg, highlightthickness=0)
            inner.pack(side="left", fill="both", expand=True)
            host = inner
        if getattr(w, "scroll", False) and not horizontal:
            sc = _Scroll(host, bg)
            sc.pack(fill="both", expand=True)
            if st.height:
                sc.canvas.configure(height=st.height)
            host = sc.inner
        if st.width or st.height:
            if not getattr(w, "scroll", False):
                outer.configure(width=st.width or 0, height=st.height or 0)
                outer.pack_propagate(False if (st.width and st.height) else True)
        if st.wrap and horizontal:
            flow = _Flow(host, bg, st.gap or 0)
            t, r, b_, l = st.pad()
            flow.pack(fill="x", expand=True, padx=(l, r), pady=(t, b_))
            for c in w.children:
                flow.add(self._r(c, flow, bg))
            return outer
        kids = [(self._r(c, host, bg), self.theme.resolve(c.kind, c.cls, c.style)) for c in w.children]
        self._pack(host, kids, "row" if horizontal else "column", st, bg)
        return outer

    def _pack(self, host: tk.Misc, kids: list, direction: str, st: Style, bg: str) -> None:
        t, r, b, l = st.pad()
        gap = st.gap or 0
        just = st.justify or "start"
        items: list[tuple[tk.Widget | None, Style | None]] = []
        if just in ("center", "end"):
            items.append((None, None))
        for i, (cw, cst) in enumerate(kids):
            if i and just == "between":
                items.append((None, None))
            items.append((cw, cst))
        if just in ("center", "start") and kids:
            items.append((None, None))
        last_real = max((i for i, (cw, _) in enumerate(items) if cw is not None), default=-1)
        first_real = next((i for i, (cw, _) in enumerate(items) if cw is not None), -1)
        for i, (cw, cst) in enumerate(items):
            if cw is None:
                sp = tk.Frame(host, bg=bg, highlightthickness=0, width=0, height=0)
                sp.pack(side="top" if direction == "column" else "left", fill="both", expand=True)
                continue
            mt, mr, mb, ml = cst.mar()  # type: ignore[union-attr]
            lead = gap if i != first_real else 0
            expand = bool(cst.expand)  # type: ignore[union-attr]
            if direction == "column":
                align = st.align or "stretch"
                cw.pack(side="top", padx=(l + ml, r + mr),
                        pady=((t if i == first_real else 0) + mt + lead, (b if i == last_real else 0) + mb),
                        fill="both" if expand else ("x" if align == "stretch" else "none"), expand=expand,
                        anchor=_CROSS_COL.get(align, "w"))
            else:
                align = st.align or "center"
                cw.pack(side="left", padx=((l if i == first_real else 0) + ml + lead, (r if i == last_real else 0) + mr),
                        pady=(t + mt, b + mb), fill="both" if expand else ("y" if align == "stretch" else "none"),
                        expand=expand, anchor=_CROSS_ROW.get(align, "center"))

    # — прості віджети —
    def _text(self, w: Text, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        align = st.text_align or "start"
        lbl = tk.Label(parent, text=w.text, font=self._font(st), fg=self._c(st.color), bg=bg,
                       anchor=_ANCHOR.get(align, "w"), justify={"start": "left", "center": "center", "end": "right"}[align],
                       padx=st.pad()[1], pady=st.pad()[0], wraplength=0)
        lbl.bind("<Configure>", lambda e, l=lbl: l.configure(wraplength=max(e.width - 2 * st.pad()[1], 10))
                 if e.width > 20 else None)
        if getattr(w, "selectable", False):
            lbl.bind("<Button-1>", lambda e: lbl.focus_set())
        if w.on_click:
            self._bind_click(lbl, lambda e: self._run(w.on_click))
        return lbl

    def _button(self, w: Button, parent: tk.Misc, st: Style, parent_bg: str) -> tk.Widget:
        bg = self._c(st.bg) or parent_bg
        fg = self._c(st.color, "#000000")
        muted = self.theme.palette["muted"]
        label = ((ICONS.get(w.icon, "") + " ") if w.icon else "") + w.text
        bw = st.border_width or 0
        t, r, b, l = st.pad()
        lbl = tk.Label(parent, text=label.strip(), font=self._font(st), fg=muted if w.disabled else fg, bg=bg,
                       padx=max(l, 6), pady=max(t, 3), highlightthickness=bw,
                       highlightbackground=self._c(st.border, bg), highlightcolor=self._c(st.border, bg))
        if not w.disabled:
            lbl.configure(cursor="hand2")
            lbl.bind("<Button-1>", lambda e: self._run(w.on_click))
            lbl.bind("<Enter>", lambda e: lbl.configure(relief="raised" if bw else "flat"))
            lbl.bind("<Leave>", lambda e: lbl.configure(relief="flat"))
        return lbl

    def _label_for(self, parent: tk.Misc, text: str, bg: str) -> tk.Label | None:
        if not text:
            return None
        return tk.Label(parent, text=text, bg=bg, fg=self.theme.palette["muted"], anchor="w",
                        font=self._font(Style(font_size=12)))

    def _input(self, w: Input, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        app = self.app
        assert app is not None
        frame = tk.Frame(parent, bg=bg, highlightthickness=0)
        lab = self._label_for(frame, w.label, bg)
        if lab:
            lab.pack(fill="x")
        value = app.values.get(w.name, w.value) if w.name else w.value
        if w.name:
            app.values[w.name] = value
        box = tk.Frame(frame, bg=self._c(st.bg, "#FFFFFF"), highlightthickness=st.border_width or 1,
                       highlightbackground=self._c(st.border, "#CCCCCC"), highlightcolor=self.theme.palette["ink"])
        box.pack(fill="x", pady=(2, 0))
        t, r, b, l = st.pad()
        font = self._font(st)
        if w.multiline:
            ent: Any = tk.Text(box, height=w.lines, font=font, bg=self._c(st.bg, "#FFFFFF"), fg=self._c(st.color),
                               insertbackground=self._c(st.color), relief="flat", wrap="word", highlightthickness=0,
                               padx=l, pady=t)
            ent.insert("1.0", str(value))
            get = lambda: ent.get("1.0", "end-1c")  # noqa: E731
            ent.bind("<KeyRelease>", lambda e: changed())
        else:
            var = tk.StringVar(value=str(value))
            self._vars.append(var)
            ent = tk.Entry(box, textvariable=var, font=font, bg=self._c(st.bg, "#FFFFFF"), fg=self._c(st.color),
                           insertbackground=self._c(st.color), relief="flat", highlightthickness=0,
                           show="•" if w.password else "")
            ent.configure(disabledbackground=self._c(st.bg, "#FFFFFF"))
            get = var.get
            var.trace_add("write", lambda *_: changed())
        if w.disabled:
            ent.configure(state="disabled")

        def changed() -> None:
            v = get()
            if w.name:
                app.values[w.name] = v
            if w.on_change:
                self._run(w.on_change, v)

        ent.pack(fill="x", padx=l, pady=max(t, 4))
        ent.bind("<FocusIn>", lambda e: setattr(self, "_focus_name", w.name or None))
        if w.on_submit and not w.multiline:
            ent.bind("<Return>", lambda e: self._run(w.on_submit, get()))
        w._tk_entry = ent  # type: ignore[attr-defined]
        if w.autofocus and self.win:
            self.win.after(80, ent.focus_set)
        return frame

    def _switch(self, w: Switch, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        app = self.app
        assert app is not None
        val = bool(app.values.get(w.name, w.value)) if w.name else w.value
        if w.name:
            app.values[w.name] = val
        var = tk.BooleanVar(value=val)
        self._vars.append(var)

        def toggled() -> None:
            if w.name:
                app.values[w.name] = var.get()
            self._run(w.on_change, var.get())

        return tk.Checkbutton(parent, text=w.label, variable=var, command=toggled, bg=bg, activebackground=bg,
                              fg=self._c(st.color), selectcolor=bg, font=self._font(st), anchor="w",
                              highlightthickness=0)

    def _dropdown(self, w: Dropdown, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        app = self.app
        assert app is not None
        frame = tk.Frame(parent, bg=bg, highlightthickness=0)
        lab = self._label_for(frame, w.label, bg)
        if lab:
            lab.pack(fill="x")
        keys = [k for k, _ in w.options]
        texts = [t for _, t in w.options]
        cur = app.values.get(w.name, w.value) if w.name else w.value
        if w.name:
            app.values[w.name] = cur
        cb = ttk.Combobox(frame, values=texts, state="readonly")
        if cur in keys:
            cb.current(keys.index(cur))

        def picked(_e: Any = None) -> None:
            key = keys[cb.current()]
            if w.name:
                app.values[w.name] = key
            self._run(w.on_change, key)

        cb.bind("<<ComboboxSelected>>", picked)
        cb.pack(fill="x", pady=(2, 0))
        return frame

    def _slider(self, w: Slider, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        app = self.app
        assert app is not None
        cur = app.values.get(w.name, w.value) if w.name else w.value
        if w.name:
            app.values[w.name] = cur
        sc = tk.Scale(parent, from_=w.min, to=w.max, resolution=w.step, orient="horizontal", label=w.label,
                      bg=bg, fg=self._c(st.color), highlightthickness=0, troughcolor=self.theme.palette["line"],
                      font=self._font(Style(font_size=12)), showvalue=True)
        sc.set(cur)

        def released(_e: Any = None) -> None:  # реагуємо після відпускання, а не на кожен піксель
            v = sc.get()
            if w.name:
                app.values[w.name] = v
            self._run(w.on_change, v)

        sc.bind("<ButtonRelease-1>", released)
        return sc

    def _image(self, w: Image, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        if w.path:
            try:
                img = tk.PhotoImage(file=w.path)
                lbl = tk.Label(parent, image=img, bg=bg)
                lbl.image = img  # type: ignore[attr-defined]
                return lbl
            except tk.TclError:
                pass
        return tk.Label(parent, text="(зображення недоступне в Tk)", bg=bg, fg=self.theme.palette["muted"])

    def _chart(self, w: Chart, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        from ...charts import ChartStyle
        p = self.theme.palette
        height = st.height or 260
        pad = st.pad()
        frame = tk.Frame(parent, bg=bg, highlightthickness=0)
        cv = tk.Canvas(frame, height=height, bg=bg, highlightthickness=0)
        cv.pack(fill="x", padx=pad[3], pady=pad[0])
        cs = ChartStyle(colors=w.colors)
        font = self._font(Style(font_size=11))
        bold = self._font(Style(font_size=11, bold=True))

        def draw(_e: Any = None) -> None:
            cv.delete("all")
            W, H = max(cv.winfo_width(), 200), height
            x0, y0, x1, y1 = 34, 28 if w.title else 12, W - 10, H - 40
            if w.title:
                cv.create_text(W / 2, 12, text=w.title, font=bold, fill=p["fg"])
            for v in range(0, int(w.max_value) + 1, max(1, int(w.max_value) // 6)):
                y = y1 - v / w.max_value * (y1 - y0)
                cv.create_line(x0, y, x1, y, fill=p["line"])
                cv.create_text(x0 - 6, y, text=str(v), anchor="e", font=font, fill=p["fg"])
            n = len(w.labels)
            if not n:
                return
            if w.type == "line":
                vals = [v for v in w.values if v is not None]
                n = len(vals)
                xs = [x0 + (x1 - x0) * (0.5 if n == 1 else 0.04 + 0.92 * i / (n - 1)) for i in range(n)]
                ys = [y1 - min(max(v, 0), w.max_value) / w.max_value * (y1 - y0) for v in vals]
                if n > 1:
                    cv.create_line(*[c for pt in zip(xs, ys) for c in pt], fill=cs.color_for(0, vals[0]), width=3,
                                   smooth=False)
                for i, (x, y, v) in enumerate(zip(xs, ys, vals)):
                    cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=cs.color_for(i, v), outline="")
                    if w.show_values:
                        cv.create_text(x, y - 11, text=f"{v:g}", font=bold, fill=p["fg"])
                    cv.create_text(x, y1 + 12, text=w.labels[i][:10], font=font, fill=p["fg"], angle=30 if n > 5 else 0)
                return
            slot = (x1 - x0) / n
            bw = max(4, min(slot * 0.62, 80))
            for i, (lab, v) in enumerate(zip(w.labels, w.values)):
                cx = x0 + slot * (i + 0.5)
                if v is not None:
                    top = y1 - min(max(v, 0), w.max_value) / w.max_value * (y1 - y0)
                    cv.create_rectangle(cx - bw / 2, top, cx + bw / 2, y1, fill=cs.color_for(i, v), outline="")
                    if w.show_values:
                        cv.create_text(cx, top - 8, text=f"{v:g}", font=bold, fill=p["fg"])
                cv.create_text(cx, y1 + 14, text=lab if len(lab) <= 10 else lab[:9] + "…", font=font, fill=p["fg"],
                               angle=35 if n > 5 else 0, anchor="center")

        cv.bind("<Configure>", draw)
        return frame

    def _table(self, w: Table, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        th = self.theme
        bw = st.border_width or 0
        outer = tk.Frame(parent, bg=bg, highlightthickness=bw, highlightbackground=self._c(st.border, bg))
        grid = tk.Frame(outer, bg=bg, highlightthickness=0)
        grid.pack(fill="both", expand=True)
        for i, c in enumerate(w.columns):
            if c.width:
                grid.grid_columnconfigure(i, weight=0, minsize=c.width)
            else:
                grid.grid_columnconfigure(i, weight=c.flex, uniform="flex")
        head_st = th.resolve("text", "table-head")
        cell_st = th.resolve("text", "table-cell")
        zebra_bg = self._c(th.resolve("text", "table-zebra").bg)
        r0 = 0

        def make_cell(row: int, col: int, content: Any, cst: Style, cbg: str, align: str, on_click: Any = None) -> None:
            holder = tk.Frame(grid, bg=cbg, highlightthickness=0)
            holder.grid(row=row, column=col, sticky="nsew")
            if isinstance(content, Widget):
                inner = self._r(content, holder, cbg)
                inner.pack(padx=(cst.pad()[3], cst.pad()[1]), pady=(cst.pad()[0], cst.pad()[2]),
                           anchor=_ANCHOR.get(align, "w"))
            else:
                lbl = tk.Label(holder, text=str(content), font=self._font(cst), fg=self._c(cst.color), bg=cbg,
                               anchor=_ANCHOR.get(align, "w"), padx=cst.pad()[1], pady=cst.pad()[0],
                               justify={"start": "left", "center": "center", "end": "right"}[align])
                lbl.pack(fill="x")
                lbl.bind("<Configure>", lambda e, l=lbl: l.configure(wraplength=max(e.width - 2 * cst.pad()[1], 10))
                         if e.width > 20 else None)
            if on_click:
                self._bind_click(holder, lambda e, f=on_click: self._run(f))

        if w.header:
            for i, c in enumerate(w.columns):
                make_cell(0, i, c.title, head_st, self._c(head_st.bg, bg) or bg, c.align)
            r0 = 1
        for ri, row in enumerate(w.rows):
            rbg = zebra_bg if (w.zebra and ri % 2 and zebra_bg) else bg
            for ci, col in enumerate(w.columns):
                raw = row[ci] if ci < len(row) else ""
                cell: Cell = w.cell(raw)
                cst = cell_st.merge(th.resolve("text", cell.cls), cell.style)
                cbg = self._c(cell.style.bg) or rbg
                handler = cell.on_click or ((lambda i=ri: w.on_row_click(i)) if w.on_row_click else None)
                make_cell(r0 + ri, ci, cell.widget if cell.widget else ("" if cell.text is None else cell.text),
                          cst, cbg, col.align, handler)
        if not w.rows:
            lbl = tk.Label(grid, text=w.empty, bg=bg, fg=th.palette["muted"], pady=16)
            lbl.grid(row=r0, column=0, columnspan=max(1, len(w.columns)), sticky="ew")
        return outer

    def _navbar(self, w: NavBar, parent: tk.Misc, st: Style, bg: str) -> tk.Widget:
        p = self.theme.palette
        bar = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=self._c(st.border, bg))
        for it in w.items:
            sel = it.key == w.selected
            col = p["ink"] if sel else p["muted"]
            cell = tk.Frame(bar, bg=bg, highlightthickness=0)
            cell.pack(side="left", fill="x", expand=True, pady=4)
            tk.Label(cell, text=ICONS.get(it.icon, "•"), bg=bg, fg=col, font=self._font(Style(font_size=18))).pack()
            tk.Label(cell, text=it.label, bg=bg, fg=col,
                     font=self._font(Style(font_size=11, bold=sel))).pack()
            self._bind_click(cell, lambda e, k=it.key: self._run(w.on_change, k))
        return bar

    # ───── діалоги й тости ─────
    def show_dialog(self, dialog: Dialog) -> None:
        assert self.win is not None
        self.close_dialog()
        th = self.theme
        st = th.resolve("dialog", dialog.cls, dialog.style)
        bg = self._c(st.bg, "#FFFFFF")
        top = tk.Toplevel(self.win)
        top.title(dialog.title)
        top.configure(bg=bg)
        top.transient(self.win)
        top.protocol("WM_DELETE_WINDOW", lambda: self._run(self.app.close_dialog))  # type: ignore[union-attr]
        body = tk.Frame(top, bg=bg, padx=st.pad()[1], pady=st.pad()[0])
        body.pack(fill="both", expand=True)
        tk.Label(body, text=dialog.title, font=self._font(Style(font_size=18, bold=True)), bg=bg,
                 fg=th.palette["ink"], anchor="w").pack(fill="x", pady=(0, 8))
        if dialog.content is not None:
            c = self._r(dialog.content, body, bg)
            c.pack(fill="both", expand=True)
        if dialog.actions:
            row = tk.Frame(body, bg=bg)
            row.pack(fill="x", pady=(12, 0))
            for a in reversed(dialog.actions):
                self._r(a, row, bg).pack(side="right", padx=(8, 0))
        self.win.update_idletasks()
        width = max(dialog.style.width or 320, 280)
        top.geometry(f"{width}x{top.winfo_reqheight()}+{self.win.winfo_rootx() + 30}+{self.win.winfo_rooty() + 60}")
        self._dlg = top
        try:
            top.grab_set()
        except tk.TclError:
            pass

    def close_dialog(self) -> None:
        if self._dlg is not None:
            try:
                self._dlg.destroy()
            except tk.TclError:
                pass
            self._dlg = None

    def toast(self, text: str) -> None:
        if self.win is None:
            return
        if self._toast is not None:
            self._toast.destroy()
        lbl = tk.Label(self.win, text=text, bg="#222222", fg="#FFFFFF", padx=14, pady=8, wraplength=360,
                       font=self._font(Style(font_size=13)))
        lbl.place(relx=0.5, rely=0.9, anchor="center")
        self._toast = lbl
        self.win.after(2800, lambda: lbl.destroy() if lbl.winfo_exists() else None)
