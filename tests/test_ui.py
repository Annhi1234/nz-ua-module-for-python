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
    assert d.app.state["diary_view"] == "today" and b.root.find("hero") is not None   # стартує «Сьогодні»
    b.click("dv-lessons")
    assert any(sc.fmt_day(d.selected_day()) in t for t in b.texts())
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


# ── адаптивність, теми й нові функції ──
def test_theme_scaling_and_make_theme():
    from nzua.ui import ACCENTS, make_theme
    th = make_theme("amoled", "teal", font_scale=1.5, density="compact", radius=20, stripe=False,
                    mark_scheme="colorblind")
    assert th.dark and th.palette["bg"] == "#000000" and th.palette["ink"] == ACCENTS["teal"][2]
    assert th.resolve("text", "h1").color == th.palette["ink"]      # похідні стилі перефарбовано
    assert th.resolve("text", "h1").font_size == round(NOTEBOOK.resolve("text", "h1").font_size * 1.5)
    assert th.resolve("card").radius == 20 and th.resolve("card").border_left == ""
    assert th.palette["good"] == "#0072B2"
    assert NOTEBOOK.resolve("text", "h1").font_size == 34   # оригінал не чіпається
    assert make_theme(font_scale=9).font_scale == 1.6


def test_app_layout_classes():
    a = App(lambda app: Text("x"), backend="headless", size=(400, 800))
    assert a.layout == "compact" and a.compact
    a.set_size(800, 600)
    assert a.layout == "medium"
    a.set_size(1400, 900)
    assert a.layout == "wide" and not a.compact


def test_settings_validation_and_migration(tmp_path):
    p = tmp_path / "ui.json"
    p.write_text(json.dumps({"dark": True, "font_scale": 9, "radius": "x", "accent": "nope", "done": [1, "a"]}))
    s = Settings.load(p)
    assert s.mode == "dark" and s.dark and s.font_scale == 1.6 and s.radius == 12 and s.accent == "indigo"
    assert s.done == ["a"]
    s.dark = False
    s.reset()
    assert s.mode == "light" and s.done == ["a"]


def test_period_range():
    from datetime import date
    from nzua.ui.diary import period_range
    t = date(2026, 10, 8)
    assert period_range("week", t)[0] == date(2026, 10, 5)
    assert period_range("month", t)[0] == date(2026, 10, 1)
    assert period_range("semester", t)[0] == date(2026, 9, 1)
    assert period_range("semester", date(2026, 3, 1))[0] == date(2026, 1, 1)
    assert period_range("year", date(2026, 3, 1))[0] == date(2025, 9, 1)


@pytest.mark.parametrize("width", [360, 800, 1400])
def test_diary_adaptive_flow(tmp_path, width):
    st = Settings.load(tmp_path / "ui.json")
    d = DiaryApp(DemoClient(), backend="headless", settings=st)
    d.app.width = width
    d.app.run()
    b = d.app.backend
    # Д/з: список, позначка «виконано», збереження
    assert b.root.find("hero") is not None and b.root.find("week-gauge") is not None
    b.click("dv-homework")
    assert any("Виконано 0 з" in t for t in b.texts())
    b.click("hw-0")
    assert len(st.done) == 1 and any("Виконано 1 з" in t for t in b.texts())
    assert Settings.load(tmp_path / "ui.json").done == st.done
    b.type("only_open", True)
    b.click("dv-marks")
    b.click("dv-lessons")
    # оцінки: калькулятор цілі, пошук, сортування, період
    b.click("nav", "grades")
    b.click("performance-table", 0)
    assert any("Ціль" in w.text or "Потрібно" in w.text or "досягти" in w.text
               for w in b.dialog.walk() if hasattr(w, "text"))
    b.type("target", "12")
    assert b.dialog is not None
    b.click("wi-4")   # «що, якщо»
    assert b.dialog.find("whatif-result") is not None
    b.click("wi-reset")
    assert b.dialog.find("whatif-result") is None
    b.type("target", "9")
    b.click("set-goal")   # зберегти ціль
    assert list(st.goals.values()) == [9.0]
    b.click("dlg-close")
    b.type("grades_sort", "avg_desc")
    b.type("grades_period", "month")
    assert st.grades_sort == "avg_desc" and st.grades_period == "month"
    b.type("subject_q", "Ал", submit=True)
    assert d.app.state["query"] == "Ал"
    # налаштування: тема, масштаб, кнопка «назад», скидання
    b.click("nav", "profile")
    b.click("open-settings")
    b.type("mode", "amoled")
    b.type("font_scale", 1.4)
    b.click("accent-teal")
    assert d.app.theme.dark and d.app.theme.font_scale == 1.4 and st.accent == "teal"
    assert d.app.back()
    b.settle()
    assert d.app.state["sub"] == ""
    b.click("open-settings")
    b.click("reset-settings")
    b.click("dlg-reset")
    assert st.mode == "light" and st.font_scale == 1.0 and not d.app.theme.dark


def test_day_navigation_and_day_strip(tmp_path):
    from datetime import timedelta
    d = DiaryApp(DemoClient(), backend="headless", settings=Settings.load(tmp_path / "ui.json"))
    d.app.run()
    b = d.app.backend
    b.click("dv-lessons")
    assert d.day_mode()                      # телефон → по днях
    d0 = d.selected_day()
    b.click(f"day-{(d.monday()).isoformat()}")
    assert d.selected_day() == d.monday()
    d.shift_day(-1)                          # за межу тижня → попередній тиждень
    b.settle()
    assert d.app.state["week"] == -1 and d.selected_day() == d.monday() + timedelta(days=6)
    d.move_week(0)
    b.settle()
    assert d.selected_day() == d0
    d.settings.diary_mode = "week"
    assert not d.day_mode()


def test_screens_helpers():
    from datetime import date
    strip = sc.day_strip(date(2026, 10, 5), date(2026, 10, 7), lambda d: None, today=date(2026, 10, 7))
    assert len(strip.children) == 7 and strip.find("day-2026-10-07") is not None
    seg = sc.segmented([("a", "A"), ("b", "B")], "a", lambda k: None, id_prefix="s")
    assert seg.find("s-a").variant == "primary" and seg.find("s-b").variant == "outline"
    assert sc.trend_arrow([5, 6, 8, 10, 12]) == "↗" and sc.trend_arrow([12, 10, 8, 6, 4]) == "↘"
    j = sc.journal_table(Schedule.model_validate(DIARY) if hasattr(Schedule, "model_validate") else Schedule.from_api(DIARY))
    assert j.min_width and j.min_width >= 150


def test_new_helpers_gauge_sparkline_text_skeleton():
    g = sc.gauge_svg(9.5, 12, color="#2E7D32")
    assert g.startswith("<svg") and "9.5" in g and sc.gauge_svg(None).count("—") == 1
    xml.parseString(g)
    sp = sc.sparkline_svg([5, 7, 9, 12], 120, 32)
    xml.parseString(sp)
    assert sc.sparkline_svg([5]) == ""
    assert sc.first_name("Іваненко Петро Олегович") == "Петро" and sc.first_name("Петро") == "Петро"
    assert sc.greeting(__import__("datetime").time(8)) == "Доброго ранку"
    assert len(sc.skeleton(2)) == 2
    sched = Schedule.model_validate(DIARY) if hasattr(Schedule, "model_validate") else Schedule.from_api(DIARY)
    txt = sc.homework_text(sched)
    assert isinstance(txt, str) and txt


def test_subject_colors_and_custom_accent():
    from nzua.ui import make_theme
    from nzua.ui.style import subject_key
    assert subject_key("Алгебра") == subject_key(" алгебра ") and subject_key("Алгебра") in NOTEBOOK.palette
    assert NOTEBOOK.palette["subj0"] != DARK.palette["subj0"]
    th = make_theme("light", "custom", accent_hex="#FF5722", shadows=False)
    assert th.palette["ink"] == "#FF5722" and th.resolve("card").shadow is None
    assert make_theme("light").resolve("card").shadow == 1


def test_settings_backup_and_custom_accent_flow(tmp_path):
    st = Settings.load(tmp_path / "ui.json")
    d = DiaryApp(DemoClient(), backend="headless", settings=st)
    d.app.run()
    b = d.app.backend
    b.click("nav", "profile")
    b.click("open-settings")
    b.type("accent_hex", "#00AA88", submit=True)
    assert st.accent == "custom" and st.accent_hex == "#00AA88" and d.app.theme.palette["ink"] == "#00AA88"
    b.click("backup-settings")
    assert b.dialog.find("backup-json") is not None
    b.type("backup_in", '{"font_scale": 1.2, "mode": "dark"}')
    b.click("dlg-apply")
    assert st.font_scale == 1.2 and st.mode == "dark"
