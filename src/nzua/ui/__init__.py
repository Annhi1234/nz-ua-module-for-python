"""nzua.ui — конструктор інтерфейсу: один опис, кілька графічних бібліотек.

    from nzua.ui import App, Screen, Column, Text, Table, Button, Chip, Style

    def build(app):
        return Screen(Column([
            Text("Оцінки", cls="h2"),
            Table(["Предмет", "Бал"], [["Алгебра", Chip(11, "good")]]),
            Button("Оновити", on_click=lambda: app.toast("Готово"), variant="primary"),
        ], gap=10))

    App(build, backend="tk").run()     # tk | qt (PyQt5) | flet | headless
"""
from .app import App, AsyncBridge, Backend, get_backend
from .export import save_html, to_html, to_text
from . import screens
from .style import DARK, NOTEBOOK, Style, Theme, box, mark_color
from .widgets import *  # noqa: F401,F403
from .widgets import __all__ as _w

__all__ = ["App", "AsyncBridge", "Backend", "get_backend", "Style", "Theme", "NOTEBOOK", "DARK", "box",
           "mark_color", "to_html", "to_text", "save_html", *_w]
