"""Власний інтерфейс на nzua.ui: таблиця оцінок зі своїми стилями.

    python examples/custom_ui.py tk        # або qt / flet
Працює на демо-даних; для справжніх замініть DemoClient() на AsyncNZClient з токенами.
"""
import sys

from nzua.ui import (App, Button, Card, Cell, Col, Column, Row, Screen, Style, Table, Text, NOTEBOOK)
from nzua.ui import screens as sc
from nzua.ui.demo import DemoClient

client = DemoClient()
THEME = NOTEBOOK.with_(
    palette={"ink": "#7B2CBF", "margin": "#7B2CBF"},          # свої кольори
    styles={"card": Style(radius=20), ".h2": Style(font_size=26)})  # свій вигляд карток і заголовків


def build(app):
    perf = app.state.get("perf")
    if perf is None:
        return Screen(Text("Завантаження…", cls="muted"))
    rows = [[s.name, Cell(f"{s.average:.1f}" if s.average else "—", bold=True, color=sc.mark_key(round(s.average or 0)))]
            for s in perf.subjects]
    return Screen(Column([
        Text("Мої оцінки", cls="h2"),
        Table([Col("Предмет", flex=3), Col("Середній", width=90, align="center")], rows,
              on_row_click=lambda i: app.toast(f"Вибрано: {perf.subjects[i].name}")),
        sc.performance_table(perf, zebra=False),
        Row([Button("Оновити", load, variant="primary", icon="refresh"),
             Button("Вийти", app.quit, variant="outline")], gap=8),
    ], gap=12))


def load():
    app.task(client.get_student_performance(), lambda p: app.state.update(perf=p))


app = App(build, backend=sys.argv[1] if len(sys.argv) > 1 else "auto", theme=THEME, title="Оцінки")
app.on_start = lambda a: load()
app.run()
