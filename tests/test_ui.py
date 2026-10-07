import json
import xml.dom.minidom as xml

import pytest

from nzua import Schedule
from nzua.ui import (App, Button, Card, Cell, Chart, Chip, Col, Column, DARK, Input, NOTEBOOK, NavBar, Row, Screen,
                     Style, Table, Text, to_html, to_text)
from nzua.ui import screens as sc
from nzua.ui.demo import DemoClient
from nzua.ui.diary import DiaryApp, Settings
from test_client import DIARY


# ── стилі ──
def test_style_merge_and_theme_resolution():
    a = Style(color="#111", padding=4).merge(Style(color=None, bg="#222"), {"padding": 8})
    assert (a.color, a.bg, a.padding) == ("#111", "#222", 8)
    st = NOTEBOOK.resolve("text", "h1 muted", Style(bold=False))
    assert st.font_size == 12 and st.bold is False  # клас .muted перекриває .h1, власний стиль — усе
    custom = NOTEBOOK.with_(styles={"card": Style(radius=30)}, palette={"ink": "#000000"})
    assert custom.resolve("card").radius == 30 and custom.palette["ink"] == "#000000"
    assert NOTEBOOK.palette["ink"] != "#000000"  # оригінал не змінився


def test_widget_shortcuts_and_find():
    r = Row(["a", Text("b", id="b")], gap=4, padding=(1, 2), expand=True)
    assert r.style.gap == 4 and r.style.expand and r.find("b").text == "b"
    assert [type(c).__name__ for c in r.children] == ["Text", "Text"]
    b = Button("x", variant="primary")
    assert "primary" in b.cls


# ── таблиця ──
def test_table_text_html_and_cells():
    t = Table(["Предмет", Col("Бал", width=60, align="end")],
              [["Алгебра", Chip(11, "good")], ["Фізика", Cell(5, color="bad", bold=True)], ["Хімія"]])
    txt = to_text(t)
    assert "Алгебра" in txt and "‹11›" in txt and "Хімія" in txt
    html = to_html(Screen(t))
    assert "<table" in html and "Фізика" in html and "#C8372D" in html
    assert "Немає" in to_text(Table(["А"], []))


def test_html_escapes_user_text():
    assert "<script>" not in to_html(Screen(Text("<script>alert(1)</script>")))


def test_chart_widget_svg_valid():
    xml.parseString(Chart(["А", "Б"], [10, 3], colors="ocean").svg(DARK))
    xml.parseString(Chart(["1", "2", "3"], [8, 10, None], type="line").svg())


# ── екрани за даними ──
def schedule():
    return Schedule.from_api(DIARY)


def test_grades_and_journal_tables():
    s = schedule()
    t = sc.grades_table(s)
    assert len(t.rows) == 2 and "Математика" in to_text(t)
    j = sc.journal_table(s)
    assert [c.title for c in j.columns][0] == "Предмет" and len(j.rows) == 1


def test_diary_view_hometask_callback():
    got = []
    cards = sc.diary_view(schedule(), lambda i, n: got.append((i, n)))
    texts = [w for c in cards for w in c.walk() if isinstance(w, Text) and w.on_click]
    texts[0].on_click()
    assert got == [(99, "Математика")]


# ── застосунок (headless) ──
def counter_app():
    def build(app):
        return Screen(Column([Text(f"n={app.state['n']}", id="t"),
                              Button("+", lambda: app.update(n=app.state["n"] + 1), id="b"),
                              Input("name", "Ім'я", id="in", on_change=lambda v: app.state.update(last=v))]))
    app = App(build, backend="headless", state={"n": 0})
    app.run()
    return app


def test_headless_click_input_and_refresh():
    app = counter_app()
    b = app.backend
    b.click("b")
    b.click("b")
    assert "n=2" in b.texts()
    b.type("name", "Ліда")
    assert app.value("name") == "Ліда" and app.state["last"] == "Ліда"


def test_async_task_and_errors_toast():
    app = counter_app()

    async def ok():
        return 5

    async def boom():
        raise RuntimeError("збій")

    app.task(ok(), lambda r: app.update(n=r))
    app.backend.settle()
    assert app.state["n"] == 5
    app.task(boom())
    app.backend.settle()
    assert app.backend.toasts == ["збій"]


def test_handler_exceptions_and_async_handlers_are_contained():
    def build(app):
        async def slow():
            app.state["done"] = True
        def bad():
            raise ValueError("клік зламався")
        return Screen(Column([Button("a", bad, id="bad"), Button("b", slow, id="slow")]))
    app = App(build, backend="headless")
    app.run()
    app.backend.click("bad")
    assert app.backend.toasts == ["клік зламався"]
    app.backend.click("slow")
    assert app.state["done"]


def test_build_error_does_not_crash():
    calls = {"n": 0}

    def build(app):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyError("x")
        return Text("ok")
    app = App(build, backend="headless")
    app.run()
    app.refresh()
    app.backend.settle()
    assert app.backend.toasts


def test_dialog_flow():
    from nzua.ui import Dialog
    app = counter_app()
    app.show_dialog(Dialog("Тест", Text("зміст"), [Button("Закрити", app.close_dialog, id="x")]))
    app.backend.settle()
    assert app.backend.dialog is not None and "зміст" in app.backend.texts()
    app.backend.click("x")
    assert app.backend.dialog is None


# ── готовий щоденник на демо-даних ──
def test_diary_app_full_flow(tmp_path):
    d = DiaryApp(DemoClient(), backend="headless", settings=Settings.load(tmp_path / "ui.json"))
    d.app.run()
    b = d.app.backend
    assert any("жовтня" in t or "Понеділок" in t for t in b.texts())
    for tab in ("timetable", "grades", "notes", "profile", "diary"):
        b.click("nav", tab)
        assert d.app.state["error"] == ""
    b.click("nav", "grades")
    assert b.root.find("performance-table") is not None and b.root.find("averages-chart") is not None
    b.click("performance-table", 0)  # діалог предмета
    assert b.dialog is not None
    b.click("dlg-close")
    b.click("nav", "diary")
    b.click("week-next")
    assert d.app.state["week"] == 1
    b.click("week-today")
    assert d.app.state["week"] == 0


def test_diary_login_logout_and_validation(tmp_path):
    class Client(DemoClient):
        async def restore_session(self):
            return False

        async def login(self, u, p, push_token=""):
            if p != "ok":
                from nzua import IncorrectPassword
                raise IncorrectPassword("Невірний пароль")
            return self.student

    d = DiaryApp(Client(), backend="headless", settings=Settings.load(tmp_path / "ui.json"))
    d.app.run()
    b = d.app.backend
    assert d.app.state["screen"] == "login"
    b.click("login")
    assert "Введіть логін і пароль." in b.texts()
    b.type("username", "ivan")
    b.type("password", "bad")
    b.click("login")
    assert "Невірний пароль" in b.texts()
    b.type("password", "ok")
    b.click("login")
    assert d.app.state["screen"] == "main"
    b.click("nav", "profile")
    b.click("logout")
    assert d.app.state["screen"] == "login"


def test_diary_ignores_stale_response_and_handles_failure(tmp_path):
    import asyncio

    class Slow(DemoClient):
        async def get_notifications(self):
            await asyncio.sleep(0.2)
            return await super().get_notifications()

        async def get_timetable(self, *a):
            raise RuntimeError("сервер впав")

    d = DiaryApp(Slow(), backend="headless", settings=Settings.load(tmp_path / "ui.json"))
    d.app.run()
    b = d.app.backend
    d.set_tab("notes")      # повільний запит...
    d.set_tab("timetable")  # ...перебито новим, який падає
    b.settle()
    assert "notes" not in d.app.state["data"] and d.app.state["error"] == "сервер впав"
    assert "Спробувати ще" in b.texts()


def test_settings_roundtrip_and_clamp(tmp_path):
    p = tmp_path / "ui.json"
    s = Settings.load(p)
    s.palette, s.chart_height, s.dark = "ocean", 300, True
    s.save()
    t = Settings.load(p)
    assert (t.palette, t.chart_height, t.dark) == ("ocean", 300, True)
    p.write_text(json.dumps({"palette": "nope", "chart_height": 9999}))
    t = Settings.load(p)
    assert t.palette == "scale" and t.chart_height == 420
    p.write_text("{битий json")
    assert Settings.load(p).palette == "scale"


def test_unknown_backend_and_auto_error():
    from nzua.ui import get_backend
    with pytest.raises(ValueError):
        get_backend("nope")
