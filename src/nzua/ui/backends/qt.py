"""Бекенд PyQt5 (`pip install PyQt5`). Стилі застосовуються через Qt Style Sheets, тож працюють
заокруглення, рамки й кольори. Графіки показуються як SVG (потрібен модуль QtSvg, він є в PyQt5)."""
from __future__ import annotations

import sys
from typing import Any, Callable

from PyQt5 import QtCore, QtGui, QtWidgets

try:  # QtSvg входить до PyQt5, але в деяких дистрибутивах — окремий пакет
    from PyQt5 import QtSvg
except ImportError:  # pragma: no cover
    QtSvg = None  # type: ignore[assignment]

from ..app import Backend
from ..style import Style, Theme
from ..widgets import (Button, Card, Cell, Chart, Chip, Column, Dialog, Divider, Dropdown, ICONS, Image, Input,
                       NavBar, Progress, Row, Screen, Slider, Spacer, Switch, Table, Text, Widget)

Qt = QtCore.Qt
_ALIGN_H = {"start": Qt.AlignLeft, "center": Qt.AlignHCenter, "end": Qt.AlignRight}
_ALIGN_V = {"start": Qt.AlignTop, "center": Qt.AlignVCenter, "end": Qt.AlignBottom}


class _FlowLayout(QtWidgets.QLayout):
    """Розкладка з переносом рядків (для стрічки оцінок)."""

    def __init__(self, parent: QtWidgets.QWidget | None = None, hspace: int = 6, vspace: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
        self._h, self._v = hspace, vspace

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int) -> QtWidgets.QLayoutItem | None:  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int) -> QtWidgets.QLayoutItem | None:  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self) -> Any:  # noqa: N802
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QtCore.QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:  # noqa: N802
        size = QtCore.QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect: QtCore.QRect, test: bool) -> int:
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > r.right() + 1 and line_h > 0:
                x, y, line_h = r.x(), y + line_h + self._v, 0
            if not test:
                it.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x += hint.width() + self._h
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


class _ClickFilter(QtCore.QObject):
    def __init__(self, target: QtWidgets.QWidget, fn: Callable[[], None]) -> None:
        super().__init__(target)
        self.fn = fn
        target.installEventFilter(self)
        target.setCursor(Qt.PointingHandCursor)

    def eventFilter(self, obj: QtCore.QObject, ev: QtCore.QEvent) -> bool:  # noqa: N802
        if ev.type() == QtCore.QEvent.MouseButtonRelease and ev.button() == Qt.LeftButton:
            self.fn()
        return False


class _Invoker(QtCore.QObject):
    """Передає виклики з будь-якого потоку в потік Qt (через чергу подій)."""
    call = QtCore.pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.call.connect(self._run)

    def _run(self, fn: Callable[[], None]) -> None:
        fn()


class QtBackend(Backend):
    name = "qt"

    def __init__(self) -> None:
        super().__init__()
        self.qapp: QtWidgets.QApplication | None = None
        self.win: QtWidgets.QWidget | None = None
        self._layout: QtWidgets.QVBoxLayout | None = None
        self._content: QtWidgets.QWidget | None = None
        self._dlg: QtWidgets.QDialog | None = None
        self._toast: QtWidgets.QLabel | None = None
        self._n = 0
        self._inputs: dict[str, QtWidgets.QWidget] = {}
        self._focus_name: str | None = None
        self._inv: _Invoker | None = None
        self._pending: list[Callable[[], None]] = []
        self._keep: list[Any] = []

    @property
    def theme(self) -> Theme:
        return self.app.theme  # type: ignore[union-attr]

    # ───── життєвий цикл ─────
    def run(self, app) -> None:
        self.app = app
        self.qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self._inv = _Invoker()
        self.win = QtWidgets.QWidget()
        self.win.setWindowTitle(app.title)
        self.win.resize(*app.size)
        self._layout = QtWidgets.QVBoxLayout(self.win)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.win.show()
        QtCore.QTimer.singleShot(0, app._ready)
        for fn in self._pending:  # виклики, зроблені до запуску вікна
            QtCore.QTimer.singleShot(0, fn)
        self._pending.clear()
        try:
            self.qapp.exec_()
        finally:
            self._bridge.close()

    def quit(self) -> None:
        if self.qapp is not None:
            self.qapp.quit()

    def call_soon(self, fn: Callable[[], None]) -> None:
        if self._inv is None:  # ще до запуску вікна — виконаємо одразу після старту
            self._pending.append(fn)
        else:
            self._inv.call.emit(fn)

    # ───── допоміжне ─────
    def _c(self, key: str | None, default: str | None = None) -> str | None:
        return self.theme.color(key) if key else default

    def _name(self, w: QtWidgets.QWidget) -> str:
        self._n += 1
        w.setObjectName(f"w{self._n}")
        return f"w{self._n}"

    def _qss(self, w: QtWidgets.QWidget, st: Style, selector: str = "QFrame", *, text: bool = False,
             padding: bool = False, extra: str = "") -> None:
        """Переводить Style у Qt Style Sheet для одного віджета."""
        name = self._name(w)
        css: list[str] = []
        if st.bg:
            css.append(f"background-color:{self._c(st.bg)}")
        elif selector != "QPushButton":
            css.append("background:transparent")
        if st.color:
            css.append(f"color:{self._c(st.color)}")
        if st.font_size:
            css.append(f"font-size:{st.font_size}px")
        if st.bold is not None:
            css.append(f"font-weight:{'bold' if st.bold else 'normal'}")
        if st.italic:
            css.append("font-style:italic")
        if st.radius:
            css.append(f"border-radius:{st.radius}px")
        if st.border and st.border_width:
            css.append(f"border:{st.border_width}px solid {self._c(st.border)}")
        elif not st.border_left:
            css.append("border:none")
        if st.border_left:
            css.append(f"border:none;border-left:4px solid {self._c(st.border_left)}")
        if padding:
            t, r, b, l = st.pad()
            css.append(f"padding:{t}px {r}px {b}px {l}px")
        w.setStyleSheet(f"{selector}#{name}{{{';'.join(css)}}}{extra.replace('#NAME', '#' + name)}")

    def _transparent(self, w: QtWidgets.QWidget) -> None:
        """Прозоре тло лише для цього віджета (стиль без селектора діяв би й на всіх нащадків)."""
        w.setStyleSheet(f"QWidget#{self._name(w)}{{background:transparent}}")

    def _run(self, fn: Callable[..., Any] | None, *args: Any) -> None:
        self.app.dispatch(fn, *args)  # type: ignore[union-attr]

    def _click(self, w: QtWidgets.QWidget, fn: Callable[..., Any] | None, *args: Any) -> None:
        if fn is not None:
            self._keep.append(_ClickFilter(w, lambda: self._run(fn, *args)))

    # ───── малювання ─────
    def mount(self, root: Widget) -> None:
        assert self._layout is not None and self.win is not None
        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.deleteLater()
        self._keep.clear()
        self._inputs.clear()
        st = self.theme.resolve("screen", root.cls, root.style)
        self.win.setStyleSheet(f"QWidget#root{{background-color:{self._c(st.bg, '#FFFFFF')}}}")
        self.win.setObjectName("root")
        self._content = self._r(root)
        self._layout.addWidget(self._content)
        w = self._inputs.get(self._focus_name or "")
        if w is not None:
            w.setFocus()

    def _r(self, w: Widget) -> QtWidgets.QWidget:
        st = self.theme.resolve(w.kind, w.cls, w.style)
        if isinstance(w, Screen):
            return self._screen(w, st)
        if isinstance(w, (Row, Column, Card)):
            return self._container(w, st)
        if isinstance(w, Text):
            lbl = QtWidgets.QLabel(w.text)
            lbl.setWordWrap(True)
            lbl.setAlignment(_ALIGN_H.get(st.text_align or "start", Qt.AlignLeft) | Qt.AlignVCenter)
            self._qss(lbl, st, "QLabel", padding=True)
            if w.selectable:
                lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._click(lbl, w.on_click)
            return self._fixed(lbl, st)
        if isinstance(w, Button):
            return self._button(w, st)
        if isinstance(w, Chip):
            lbl = QtWidgets.QLabel(w.text)
            lbl.setAlignment(Qt.AlignCenter)
            self._qss(lbl, st.merge(Style(bg=w.color or st.bg)), "QLabel", padding=True)
            if w.tooltip:
                lbl.setToolTip(w.tooltip)
            lbl.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
            return lbl
        if isinstance(w, Input):
            return self._input(w, st)
        if isinstance(w, Switch):
            return self._switch(w, st)
        if isinstance(w, Dropdown):
            return self._dropdown(w, st)
        if isinstance(w, Slider):
            return self._slider(w, st)
        if isinstance(w, Progress):
            pb = QtWidgets.QProgressBar()
            pb.setTextVisible(False)
            pb.setMaximumHeight(8)
            if w.value is None:
                pb.setRange(0, 0)
            else:
                pb.setRange(0, 100)
                pb.setValue(int(w.value * 100))
            return pb
        if isinstance(w, Divider):
            f = QtWidgets.QFrame()
            f.setFixedHeight(1)
            self._qss(f, st)
            return f
        if isinstance(w, Spacer):
            s = QtWidgets.QWidget()
            if st.expand:
                s.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            else:
                s.setFixedSize(st.width or 0, st.height or 0)
            return s
        if isinstance(w, Image):
            return self._image(w, st)
        if isinstance(w, Chart):
            return self._chart(w, st)
        if isinstance(w, Table):
            return self._table(w, st)
        if isinstance(w, NavBar):
            return self._navbar(w, st)
        return QtWidgets.QLabel(repr(w))

    def _fixed(self, widget: QtWidgets.QWidget, st: Style) -> QtWidgets.QWidget:
        if st.width:
            widget.setFixedWidth(st.width)
        if st.height:
            widget.setFixedHeight(st.height)
        return widget

    def _margin(self, widget: QtWidgets.QWidget, st: Style) -> QtWidgets.QWidget:
        """Зовнішні відступи (margin) — обгорткою з полями."""
        t, r, b, l = st.mar()
        if not (t or r or b or l):
            return widget
        holder = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(holder)
        lay.setContentsMargins(l, t, r, b)
        lay.addWidget(widget)
        self._transparent(holder)
        return holder

    # — контейнери —
    def _screen(self, w: Screen, st: Style) -> QtWidgets.QWidget:
        root = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        body = self._r(w.body)
        t, r, b, l = st.pad()
        holder = QtWidgets.QWidget()
        hl = QtWidgets.QVBoxLayout(holder)
        hl.setContentsMargins(l, t, r, b)
        hl.addWidget(body)
        if w.scroll:
            hl.addStretch(1)
            area = QtWidgets.QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QtWidgets.QFrame.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._transparent(holder)
            page_bg = self._c(self.theme.resolve("screen").bg, "#FFFFFF")
            area.setStyleSheet(f"QScrollArea{{border:none;background:{page_bg}}}"
                               f"QScrollArea > QWidget > QWidget{{background:{page_bg}}}")
            area.setWidget(holder)
            lay.addWidget(area, 1)
        else:
            lay.addWidget(holder, 1)
        if w.nav:
            lay.addWidget(self._r(w.nav))
        return root

    def _container(self, w: Widget, st: Style) -> QtWidgets.QWidget:
        horizontal = isinstance(w, Row)
        frame = QtWidgets.QFrame()
        self._qss(frame, st)
        t, r, b, l = st.pad()
        gap = st.gap or 0
        if st.wrap and horizontal:
            lay: QtWidgets.QLayout = _FlowLayout(frame, gap, gap)
            lay.setContentsMargins(l, t, r, b)
            for c in w.children:
                lay.addWidget(self._r(c))
            return self._margin(self._fixed(frame, st), st)
        lay = QtWidgets.QHBoxLayout(frame) if horizontal else QtWidgets.QVBoxLayout(frame)
        lay.setContentsMargins(l, t, r, b)
        lay.setSpacing(gap)
        just = st.justify or "start"
        if just in ("center", "end"):
            lay.addStretch(1)
        cross = st.align or ("center" if horizontal else "stretch")
        for i, c in enumerate(w.children):
            if i and just == "between":
                lay.addStretch(1)
            cst = self.theme.resolve(c.kind, c.cls, c.style)
            child = self._r(c)
            if not horizontal and not cst.expand:  # у колонці картки не розтягуються по висоті
                child.setSizePolicy(child.sizePolicy().horizontalPolicy(), QtWidgets.QSizePolicy.Maximum
                                    if not isinstance(c, (Text,)) else QtWidgets.QSizePolicy.Preferred)
            align = Qt.Alignment()
            if cross != "stretch":
                align = _ALIGN_V.get(cross, Qt.AlignVCenter) if horizontal else _ALIGN_H.get(cross, Qt.AlignLeft)
            lay.addWidget(child, 1 if cst.expand else 0, align)
        if just in ("start", "center") and not any(
                self.theme.resolve(c.kind, c.cls, c.style).expand for c in w.children):
            lay.addStretch(1)
        out: QtWidgets.QWidget = frame
        if getattr(w, "scroll", False) and not horizontal:
            area = QtWidgets.QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QtWidgets.QFrame.NoFrame)
            area.setWidget(frame)
            if st.height:
                area.setFixedHeight(st.height)
            out = area
        else:
            self._fixed(frame, st)
        if isinstance(w, Card) and w.on_click:
            self._click(frame, w.on_click)
        return self._margin(out, st)

    # — прості віджети —
    def _button(self, w: Button, st: Style) -> QtWidgets.QWidget:
        label = ((ICONS.get(w.icon, "") + " ") if w.icon else "") + w.text
        b = QtWidgets.QPushButton(label.strip())
        self._qss(b, st, "QPushButton", padding=True,
                  extra=f"QPushButton#NAME:disabled{{color:{self.theme.palette['muted']}}}"
                        f"QPushButton#NAME:hover{{border-color:{self.theme.palette['ink']}}}")
        b.setEnabled(not w.disabled)
        b.setCursor(Qt.PointingHandCursor)
        if w.tooltip:
            b.setToolTip(w.tooltip)
        b.clicked.connect(lambda _=False: self._run(w.on_click))
        return self._fixed(b, st)

    def _labeled(self, label: str, inner: QtWidgets.QWidget) -> QtWidgets.QWidget:
        if not label:
            return inner
        box = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        cap = QtWidgets.QLabel(label)
        cap.setStyleSheet(f"color:{self.theme.palette['muted']};font-size:12px;background:transparent")
        lay.addWidget(cap)
        lay.addWidget(inner)
        return box

    def _input(self, w: Input, st: Style) -> QtWidgets.QWidget:
        app = self.app
        assert app is not None
        value = str(app.values.get(w.name, w.value)) if w.name else w.value
        if w.name:
            app.values[w.name] = value

        def changed(v: str) -> None:
            if w.name:
                app.values[w.name] = v
            self._run(w.on_change, v)

        if w.multiline:
            ed: Any = QtWidgets.QPlainTextEdit(value)
            ed.setFixedHeight(w.lines * 24 + 16)
            ed.textChanged.connect(lambda: changed(ed.toPlainText()))
            selector = "QPlainTextEdit"
        else:
            ed = QtWidgets.QLineEdit(value)
            if w.password:
                ed.setEchoMode(QtWidgets.QLineEdit.Password)
            ed.textChanged.connect(changed)
            if w.on_submit:
                ed.returnPressed.connect(lambda: self._run(w.on_submit, ed.text()))
            selector = "QLineEdit"
        self._qss(ed, st, selector, padding=True,
                  extra=f"{selector}#NAME:focus{{border:1px solid {self.theme.palette['ink']}}}")
        ed.setEnabled(not w.disabled)
        if w.name:
            self._inputs[w.name] = ed
            ed.installEventFilter(_FocusTracker(ed, self, w.name))
        if w.autofocus:
            QtCore.QTimer.singleShot(80, ed.setFocus)
        return self._labeled(w.label, ed)

    def _switch(self, w: Switch, st: Style) -> QtWidgets.QWidget:
        app = self.app
        assert app is not None
        val = bool(app.values.get(w.name, w.value)) if w.name else w.value
        if w.name:
            app.values[w.name] = val
        cb = QtWidgets.QCheckBox(w.label)
        cb.setChecked(val)
        self._qss(cb, st, "QCheckBox")

        def toggled(v: bool) -> None:
            if w.name:
                app.values[w.name] = bool(v)
            self._run(w.on_change, bool(v))

        cb.toggled.connect(toggled)
        return cb

    def _dropdown(self, w: Dropdown, st: Style) -> QtWidgets.QWidget:
        app = self.app
        assert app is not None
        cur = app.values.get(w.name, w.value) if w.name else w.value
        if w.name:
            app.values[w.name] = cur
        combo = QtWidgets.QComboBox()
        for k, t in w.options:
            combo.addItem(t, k)
        idx = combo.findData(cur)
        if idx >= 0:
            combo.setCurrentIndex(idx)

        def picked(i: int) -> None:
            key = combo.itemData(i)
            if w.name:
                app.values[w.name] = key
            self._run(w.on_change, key)

        combo.activated.connect(picked)
        return self._labeled(w.label, combo)

    def _slider(self, w: Slider, st: Style) -> QtWidgets.QWidget:
        app = self.app
        assert app is not None
        cur = app.values.get(w.name, w.value) if w.name else w.value
        if w.name:
            app.values[w.name] = cur
        steps = max(1, int(round((w.max - w.min) / w.step)))
        sl = QtWidgets.QSlider(Qt.Horizontal)
        sl.setRange(0, steps)
        sl.setValue(int(round((cur - w.min) / w.step)))
        shown = QtWidgets.QLabel(f"{cur:g}")
        shown.setStyleSheet("background:transparent")

        def value() -> float:
            return w.min + sl.value() * w.step

        def commit() -> None:
            v = value()
            if w.name:
                app.values[w.name] = v
            self._run(w.on_change, v)

        sl.valueChanged.connect(lambda _=0: shown.setText(f"{value():g}"))
        sl.sliderReleased.connect(commit)
        sl.actionTriggered.connect(lambda a: QtCore.QTimer.singleShot(0, commit) if not sl.isSliderDown() else None)
        row = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(sl, 1)
        lay.addWidget(shown)
        return self._labeled(w.label, row)

    def _image(self, w: Image, st: Style) -> QtWidgets.QWidget:
        if w.svg and QtSvg is not None:
            sv = QtSvg.QSvgWidget()
            sv.load(QtCore.QByteArray(w.svg.encode("utf-8")))
            return self._fixed(sv, st)
        lbl = QtWidgets.QLabel()
        if w.path:
            lbl.setPixmap(QtGui.QPixmap(w.path))
        return lbl

    def _chart(self, w: Chart, st: Style) -> QtWidgets.QWidget:
        frame = QtWidgets.QFrame()
        self._qss(frame, st)
        lay = QtWidgets.QVBoxLayout(frame)
        t, r, b, l = st.pad()
        lay.setContentsMargins(l, t, r, b)
        if QtSvg is None:
            lay.addWidget(QtWidgets.QLabel("Для графіків потрібен PyQt5.QtSvg"))
            return self._margin(frame, st)
        sv = QtSvg.QSvgWidget()
        sv.load(QtCore.QByteArray(w.svg(self.theme).encode("utf-8")))
        sv.setMinimumHeight(st.height or 260)
        sv.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        lay.addWidget(sv)
        frame.setMinimumHeight((st.height or 260) + t + b)
        return self._margin(frame, st)

    def _table(self, w: Table, st: Style) -> QtWidgets.QWidget:
        th = self.theme
        frame = QtWidgets.QFrame()
        self._qss(frame, st)
        grid = QtWidgets.QGridLayout(frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        for i, c in enumerate(w.columns):
            if c.width:
                grid.setColumnMinimumWidth(i, c.width)
                grid.setColumnStretch(i, 0)
            else:
                grid.setColumnStretch(i, c.flex)
        head_st = th.resolve("text", "table-head")
        cell_st = th.resolve("text", "table-cell")
        zebra_bg = th.resolve("text", "table-zebra").bg

        def put(row: int, col: int, content: Any, cst: Style, bg: str | None, align: str, width: int | None,
                on_click: Callable[[], Any] | None) -> None:
            holder = QtWidgets.QFrame()
            self._qss(holder, Style(bg=bg))
            lay = QtWidgets.QHBoxLayout(holder)
            t, r, b, l = cst.pad()
            lay.setContentsMargins(l, t, r, b)
            if isinstance(content, Widget):
                lay.addWidget(self._r(content), 0, _ALIGN_H.get(align, Qt.AlignLeft))
                lay.addStretch(1) if align == "start" else None
            else:
                lbl = QtWidgets.QLabel(str(content))
                lbl.setWordWrap(True)
                lbl.setAlignment(_ALIGN_H.get(align, Qt.AlignLeft) | Qt.AlignVCenter)
                self._qss(lbl, cst, "QLabel")
                lay.addWidget(lbl)
            if width:
                holder.setFixedWidth(width)
            if on_click:
                self._click(holder, on_click)
            grid.addWidget(holder, row, col)

        r0 = 0
        if w.header:
            for i, c in enumerate(w.columns):
                put(0, i, c.title, head_st, head_st.bg, c.align, c.width, None)
            r0 = 1
        for ri, row in enumerate(w.rows):
            rbg = zebra_bg if (w.zebra and ri % 2) else None
            for ci, col in enumerate(w.columns):
                cell: Cell = w.cell(row[ci] if ci < len(row) else "")
                cst = cell_st.merge(th.resolve("text", cell.cls), cell.style)
                handler = cell.on_click or ((lambda i=ri: w.on_row_click(i)) if w.on_row_click else None)
                put(r0 + ri, ci, cell.widget if cell.widget else ("" if cell.text is None else cell.text), cst,
                    cell.style.bg or rbg, col.align, col.width, handler)
        if not w.rows:
            lbl = QtWidgets.QLabel(w.empty)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"color:{th.palette['muted']};padding:16px;background:transparent")
            grid.addWidget(lbl, r0, 0, 1, max(1, len(w.columns)))
        return self._margin(frame, st)

    def _navbar(self, w: NavBar, st: Style) -> QtWidgets.QWidget:
        p = self.theme.palette
        bar = QtWidgets.QFrame()
        self._qss(bar, st)
        lay = QtWidgets.QHBoxLayout(bar)
        lay.setContentsMargins(0, 4, 0, 4)
        for it in w.items:
            sel = it.key == w.selected
            b = QtWidgets.QPushButton(f"{ICONS.get(it.icon, '•')}\n{it.label}")
            b.setFlat(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{border:none;background:transparent;color:{p['ink'] if sel else p['muted']};"
                            f"font-size:12px;font-weight:{'bold' if sel else 'normal'};padding:4px}}")
            b.clicked.connect(lambda _=False, k=it.key: self._run(w.on_change, k))
            lay.addWidget(b, 1)
        return bar

    # ───── діалоги й тости ─────
    def show_dialog(self, dialog: Dialog) -> None:
        assert self.win is not None
        self.close_dialog()
        th = self.theme
        st = th.resolve("dialog", dialog.cls, dialog.style)
        dlg = QtWidgets.QDialog(self.win)
        dlg.setWindowTitle(dialog.title)
        dlg.setModal(True)
        dlg.setStyleSheet(f"QDialog{{background:{self._c(st.bg, '#FFFFFF')}}}")
        lay = QtWidgets.QVBoxLayout(dlg)
        t, r, b, l = st.pad()
        lay.setContentsMargins(l, t, r, b)
        title = QtWidgets.QLabel(dialog.title)
        title.setStyleSheet(f"font-size:18px;font-weight:bold;color:{th.palette['ink']};background:transparent")
        lay.addWidget(title)
        if dialog.content is not None:
            lay.addWidget(self._r(dialog.content), 1)
        if dialog.actions:
            row = QtWidgets.QHBoxLayout()
            row.addStretch(1)
            for a in dialog.actions:
                row.addWidget(self._r(a))
            lay.addLayout(row)
        dlg.setMinimumWidth(dialog.style.width or 320)
        dlg.finished.connect(lambda _=0: self._dialog_closed(dlg))
        self._dlg = dlg
        dlg.show()

    def _dialog_closed(self, dlg: QtWidgets.QDialog) -> None:
        if self._dlg is dlg:
            self._dlg = None
            if self.app is not None:
                self.app.dialog = None

    def close_dialog(self) -> None:
        if self._dlg is not None:
            dlg, self._dlg = self._dlg, None
            dlg.close()
            dlg.deleteLater()

    def toast(self, text: str) -> None:
        if self.win is None:
            return
        if self._toast is not None:
            self._toast.deleteLater()
        lbl = QtWidgets.QLabel(text, self.win)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("background:#222;color:#fff;padding:8px 14px;border-radius:8px;font-size:13px")
        lbl.setMaximumWidth(max(200, self.win.width() - 40))
        lbl.adjustSize()
        lbl.move((self.win.width() - lbl.width()) // 2, self.win.height() - lbl.height() - 70)
        lbl.show()
        lbl.raise_()
        self._toast = lbl
        QtCore.QTimer.singleShot(2800, lbl.deleteLater)


class _FocusTracker(QtCore.QObject):
    def __init__(self, target: QtWidgets.QWidget, backend: QtBackend, name: str) -> None:
        super().__init__(target)
        self._b, self._name = backend, name

    def eventFilter(self, obj: QtCore.QObject, ev: QtCore.QEvent) -> bool:  # noqa: N802
        if ev.type() == QtCore.QEvent.FocusIn:
            self._b._focus_name = self._name
        return False
