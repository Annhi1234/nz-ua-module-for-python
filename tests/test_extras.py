import json
import xml.dom.minidom as xml

import httpx
import pytest

from nzua import (AsyncNZClient, ChartStyle, MemoryTokenStore, StudentPerformance, Tokens, bar_chart,
                  distribution_chart, line_chart, mark_distribution, needed_marks, rank_subjects, trend)
from nzua.cli import main
from test_client import DIARY, LOGIN

PERF = {"missed": {"days": 1, "lessons": 2}, "subjects": [
    {"subject_id": 1, "subject_name": "Алгебра", "marks": [{"value": "10"}, {"value": "12"}]},
    {"subject_id": 2, "subject_name": "Фізика", "marks": [{"value": "5"}]}]}


# ── аналітика ──
def test_needed_marks():
    assert needed_marks([8, 9, 10], 10.5) == 3
    assert needed_marks([12], 11) == 0
    assert needed_marks([8], 12) is None
    assert needed_marks([], 10) == 1


def test_rank_distribution_trend():
    p = StudentPerformance.from_api(PERF)
    assert [n for n, _ in rank_subjects(p)] == ["Алгебра", "Фізика"]
    assert [n for n, _ in rank_subjects(p, best_first=False)] == ["Фізика", "Алгебра"]
    d = mark_distribution([10, 10, 5, None, 20])
    assert d[10] == 2 and d[5] == 1 and len(d) == 12
    assert trend([5, 5, 9, 10]) == "up" and trend([10, 10, 5, 5]) == "down" and trend([7, 7]) == "flat"


# ── графіки ──
def test_charts_are_valid_svg_and_respect_style():
    svg = bar_chart(["А", "Б"], [10, 3], ChartStyle(width=500, height=250, colors="#ff0000,#00ff00", title="T<>"))
    xml.parseString(svg)
    assert 'width="500"' in svg and 'height="250"' in svg and "#ff0000" in svg and "T&lt;&gt;" in svg
    scale = bar_chart(["А", "Б"], [10, 2])  # режим "за оцінкою"
    assert "#2F855A" in scale and "#C8372D" in scale
    assert 'width="' not in bar_chart(["А"], [5], ChartStyle(responsive=True)).split(">")[0]
    xml.parseString(line_chart(["1", "2", "3"], [8, 10, 11], ChartStyle(colors="ocean")))
    xml.parseString(line_chart([], []))
    xml.parseString(distribution_chart([10, 10, 5]))
    xml.parseString(bar_chart([f"Предмет {i}" for i in range(9)], [i + 1 for i in range(9)]))


@pytest.mark.parametrize("kw", [dict(width=10), dict(colors="red;x"), dict(max_value=0)])
def test_chart_style_validation(kw):
    with pytest.raises(ValueError):
        ChartStyle(**kw)


def test_bar_chart_length_mismatch():
    with pytest.raises(ValueError):
        bar_chart(["a"], [1, 2])


# ── CLI ──
def handler(req):
    p = req.url.path
    if p.endswith("/login"):
        return httpx.Response(200, json=LOGIN)
    if p.endswith("/diary"):
        return httpx.Response(200, json=DIARY)
    if p.endswith("student-performance"):
        return httpx.Response(200, json=PERF)
    if p.endswith("/test"):
        return httpx.Response(200, json="2ololo")
    return httpx.Response(404)


def factory(tokens=Tokens("A")):
    return lambda home, no_cache: AsyncNZClient(
        tokens=tokens, token_store=MemoryTokenStore(), transport=httpx.MockTransport(handler), retries=0)


def test_cli_grades_table_and_json(capsys):
    assert main(["grades", "--period", "week"], client_factory=factory()) == 0
    out = capsys.readouterr().out
    assert "Математика" in out and "Середній бал: 10.00" in out
    assert main(["-f", "json", "grades", "--subject", "матем"], client_factory=factory()) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rows"][0]["mark"] == "10" and len(data["rows"]) == 2
    assert main(["-f", "csv", "grades"], client_factory=factory()) == 0
    assert capsys.readouterr().out.startswith("date,subject,mark")


def test_cli_performance_and_chart(tmp_path, capsys):
    assert main(["performance"], client_factory=factory()) == 0
    assert "Алгебра" in capsys.readouterr().out
    svg = tmp_path / "a.svg"
    assert main(["chart", "averages", "-o", str(svg), "--width", "400", "--height", "300",
                 "--colors", "sunset", "--title", "Середні"], client_factory=factory()) == 0
    xml.parseString(svg.read_text("utf-8"))
    assert 'width="400"' in svg.read_text("utf-8")
    assert main(["chart", "marks", "-o", str(tmp_path / "m.svg")], client_factory=factory()) == 0
    assert main(["chart", "distribution", "-o", str(tmp_path / "d.svg")], client_factory=factory()) == 0


def test_cli_login_unauthorized_and_need(capsys):
    assert main(["grades"], client_factory=factory(tokens=None)) == 2
    assert "nzua login" in capsys.readouterr().err
    assert main(["login", "-u", "u", "-p", "p"], client_factory=factory(tokens=None)) == 0
    assert "Іваненко Іван" in capsys.readouterr().out
    assert main(["need", "--marks", "8,9,10", "--target", "10.5"]) == 0
    assert "3" in capsys.readouterr().out
    assert main(["need", "--marks", "a,b", "--target", "10"]) == 1
    assert main(["status"], client_factory=factory()) == 0
    assert "працює" in capsys.readouterr().out
