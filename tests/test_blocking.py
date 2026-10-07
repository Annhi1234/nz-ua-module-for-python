import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from nzua import (AsyncNZClient, BlockedError, FileCache, NetworkError, Tokens, load_network_options,
                  save_network_options)
from nzua.cli import main
from test_client import DIARY

CF = ("<!DOCTYPE html><html lang=\"en-US\"><head><title>Just a moment...</title>"
      "<meta http-equiv=\"refresh\" content=\"390\"></head><body>cf-chl</body></html>")


def cf_response(code=403):
    return httpx.Response(code, text=CF, headers={"content-type": "text/html; charset=UTF-8"})


async def test_cloudflare_page_becomes_blocked_error_without_retries():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return cf_response()

    nz = AsyncNZClient(transport=httpx.MockTransport(h), retries=3)
    with pytest.raises(BlockedError) as e:
        await nz.login("u", "p")
    assert "diagnose" in str(e.value) and n["i"] == 1
    await nz.aclose()


async def test_blocked_503_not_retried_and_not_service_unavailable():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return cf_response(503)

    nz = AsyncNZClient(tokens=Tokens("A"), transport=httpx.MockTransport(h), retries=3)
    with pytest.raises(BlockedError):
        await nz.get_schedule()
    assert n["i"] == 1
    await nz.aclose()


async def test_plain_403_json_is_not_reported_as_cloudflare():
    nz = AsyncNZClient(tokens=Tokens("A"), retries=0,
                       transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"x": 1})))
    with pytest.raises(Exception) as e:
        await nz.get_schedule()
    assert not isinstance(e.value, BlockedError)
    await nz.aclose()


async def test_blocked_falls_back_to_cache(tmp_path):
    state = {"blocked": False}

    def h(req):
        return cf_response() if state["blocked"] else httpx.Response(200, json=DIARY)

    nz = AsyncNZClient(tokens=Tokens("A"), cache=FileCache(tmp_path / "c.json"),
                       transport=httpx.MockTransport(h), retries=0)
    await nz.get_schedule("2026-10-01", "2026-10-07")
    state["blocked"] = True
    assert (await nz.get_schedule("2026-10-01", "2026-10-07")).from_cache
    assert issubclass(BlockedError, NetworkError)
    await nz.aclose()


async def test_user_agent_presets_and_custom():
    seen = []

    def h(req):
        seen.append(req.headers["user-agent"])
        return httpx.Response(200, json="2ololo")

    for ua in ("okhttp", "MyAgent/1.0", None):
        nz = AsyncNZClient(user_agent=ua, transport=httpx.MockTransport(h))
        await nz.ping()
        await nz.aclose()
    assert seen == ["okhttp/4.12.0", "MyAgent/1.0", "IRC RESTClient"]


async def test_probe_results():
    for resp, want in [(httpx.Response(200, json="x"), "ok"), (cf_response(), "blocked"),
                       (httpx.Response(404), "http 404")]:
        nz = AsyncNZClient(transport=httpx.MockTransport(lambda r, resp=resp: resp), retries=0)
        assert await nz.probe() == want
        await nz.aclose()

    def boom(req):
        raise httpx.ConnectError("down")

    nz = AsyncNZClient(transport=httpx.MockTransport(boom), retries=0)
    assert (await nz.probe()).startswith("network:")
    await nz.aclose()


def test_network_options_roundtrip(tmp_path):
    assert load_network_options(tmp_path) == {}
    save_network_options({"user_agent": "okhttp", "http2": False, "junk": 1}, tmp_path)
    assert load_network_options(tmp_path) == {"user_agent": "okhttp"}
    save_network_options({"impersonate": False}, tmp_path)  # явне вимкнення TLS-відбитка зберігається
    assert load_network_options(tmp_path) == {"impersonate": False}


def test_cli_diagnose_finds_and_saves_working_option(tmp_path, capsys):
    def h(req):
        return httpx.Response(200, json="2ololo") if req.headers["user-agent"] == "okhttp/4.12.0" else cf_response()

    factory = lambda **o: AsyncNZClient(transport=httpx.MockTransport(h), retries=0, **o)
    assert main(["--home", str(tmp_path), "diagnose", "--save"], probe_factory=factory) == 0
    out = capsys.readouterr().out
    assert "заблоковано Cloudflare" in out and "okhttp" in out
    assert load_network_options(tmp_path) == {"impersonate": False, "user_agent": "okhttp"}


def test_cli_diagnose_nothing_works(tmp_path, capsys):
    factory = lambda **o: AsyncNZClient(transport=httpx.MockTransport(lambda r: cf_response()), retries=0, **o)
    assert main(["--home", str(tmp_path), "diagnose"], probe_factory=factory) == 1
    assert "Жоден спосіб не пройшов" in capsys.readouterr().out


async def test_curl_transport_against_local_server():
    pytest.importorskip("curl_cffi")

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.dumps({"echo": json.loads(self.rfile.read(int(self.headers["Content-Length"])))}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            body = b'"2ololo"'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        nz = AsyncNZClient(base_url=f"http://127.0.0.1:{srv.server_port}", impersonate="chrome", retries=0)
        assert await nz.probe() == "ok"
        data = await nz._call("POST", "/echo", body={"a": 1}, auth=False)
        assert data == {"echo": {"a": 1}}
        await nz.aclose()
    finally:
        srv.shutdown()


def test_tls_default_falls_back_with_warning_and_explicit_raises(monkeypatch):
    import builtins
    import warnings
    import nzua.client as c

    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("curl_cffi"):
            raise ImportError("no curl")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    monkeypatch.setattr(c, "_warned_no_curl", False)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        nz = AsyncNZClient()  # типовий режим: попередження, але працює
        nz2 = AsyncNZClient()  # друге попередження не дублюється
    assert [x.category for x in w] == [RuntimeWarning]
    with pytest.raises(ImportError):
        AsyncNZClient(impersonate="chrome")  # явний запит без curl_cffi — помилка
    AsyncNZClient(impersonate=False)  # вимкнено свідомо — тиша
