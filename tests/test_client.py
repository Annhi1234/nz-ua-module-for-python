import json
import time
from datetime import date

import httpx
import pytest

import nzua
from nzua import (AsyncNZClient, FileCache, IncorrectPassword, MemoryCache, MemoryTokenStore,
                  NetworkError, NZClient, SessionExpired, Tokens, Unauthorized)
from nzua._parse import strip_html

LOGIN = {"access_token": "A1", "refresh_token": "R1", "expires_token": int(time.time()) + 3600,
         "student_id": "7", "FIO": "Іваненко Іван", "class_name": "10-А",
         "class_manager_fio": "Петренко П.П.", "avatar": {"image_url": "", "datetime": None},
         "permissions": {"diary": True}}
DIARY = {"dates": [{"date": "2026-10-05", "calls": [{
    "call_id": 1, "call_number": 1, "call_time_start": "8:30", "call_time_end": "9:15",
    "subjects": [{"subject_name": "Математика", "room": "12", "teacher": {"id": 3, "name": "Сидоренко"},
                  "hometask": ["§5"], "distance_hometask_id": 99,
                  "lesson": [{"type": "Тематична", "mark": "10"}, {"type": "Урок", "mark": "Н"}]}]}]}]}


def client(handler, **kw):
    return AsyncNZClient(transport=httpx.MockTransport(handler), retries=1, **kw)


def ok(data, code=200):
    return httpx.Response(code, json=data)


async def test_login_and_schedule():
    seen = {}

    def h(req):
        if req.url.path == "/v2/user/login":
            seen["body"] = json.loads(req.content)
            return ok(LOGIN)
        assert req.headers["authorization"] == "Bearer A1"
        return ok(DIARY)

    store = MemoryTokenStore()
    async with client(h, token_store=store) as nz:
        st = await nz.login("u", "p")
        assert seen["body"]["exponentPushToken"] == "" and st.full_name == "Іваненко Іван"
        sch = await nz.get_schedule("2026-10-01", "2026-10-07")
        subj = sch.days[0].lessons[0].subjects[0]
        assert subj.teacher.name == "Сидоренко" and subj.hometask_id == 99
        assert [g.value for g in subj.grades] == [10, None]
        assert sch.average() == 10
        assert (await store.load()).access_token == "A1"


async def test_auto_refresh_on_401():
    calls = []

    def h(req):
        calls.append(req.url.path)
        if req.url.path == "/v2/user/refresh-token":
            return ok({"access_token": "A2", "error_message": ""})
        if req.headers["authorization"] == "Bearer A1":
            return httpx.Response(401)
        return ok(DIARY)

    store = MemoryTokenStore()
    async with client(h, tokens=Tokens("A1", "R1"), token_store=store) as nz:
        await nz.get_schedule()
        assert nz.tokens.access_token == "A2" and nz.tokens.refresh_token == "R1"
        assert (await store.load()).access_token == "A2"
    assert calls.count("/v2/user/refresh-token") == 1


async def test_refresh_when_expired_and_failure_logs_out():
    def h(req):
        return httpx.Response(401)

    store = MemoryTokenStore()
    await store.save(Tokens("A", "R", int(time.time()) - 10))
    async with client(h, token_store=store) as nz:
        with pytest.raises(SessionExpired):
            await nz.get_schedule()
        assert not nz.is_authenticated and await store.load() is None


async def test_no_token_raises():
    async with client(lambda r: ok({})) as nz:
        with pytest.raises(Unauthorized):
            await nz.get_schedule()


async def test_wrong_password():
    def h(req):
        return ok({"error_message": "Введено невірний логін або пароль."})

    async with client(h) as nz:
        with pytest.raises(IncorrectPassword):
            await nz.login("u", "bad")


async def test_retry_on_503_then_success():
    n = {"i": 0}

    def h(req):
        n["i"] += 1
        return httpx.Response(503) if n["i"] == 1 else ok(DIARY)

    async with client(h, tokens=Tokens("A1")) as nz:
        assert len((await nz.get_schedule()).days) == 1
    assert n["i"] == 2


async def test_offline_cache_fallback(tmp_path):
    online = {"v": True}

    def h(req):
        if not online["v"]:
            raise httpx.ConnectError("down")
        return ok(DIARY)

    async with client(h, tokens=Tokens("A1"), cache=FileCache(tmp_path / "c.json")) as nz:
        fresh = await nz.get_schedule("2026-10-01", "2026-10-07")
        assert not fresh.from_cache
        online["v"] = False
        stale = await nz.get_schedule("2026-10-01", "2026-10-07")
        assert stale.from_cache and stale.days == fresh.days
        with pytest.raises(NetworkError):  # іншого періоду в кеші нема
            await nz.get_schedule("2026-09-01", "2026-09-07")
    assert (tmp_path / "c.json").exists()


async def test_default_period_is_computed_at_call_time():
    seen = {}

    def h(req):
        seen.update(json.loads(req.content))
        return ok({"dates": []})

    async with client(h, tokens=Tokens("A")) as nz:
        await nz.get_timetable()
    today = date.today()
    assert seen == {"start_date": str(today.replace(day=1)), "end_date": str(today)}


async def test_validation():
    async with client(lambda r: ok({}), tokens=Tokens("A")) as nz:
        with pytest.raises(ValueError):
            await nz.get_schedule("2026-10-10", "2026-10-01")
        with pytest.raises(ValueError):
            await nz.get_hometask(0)


async def test_performance_v1_and_v2_marks():
    data = {"missed": {"days": "2", "lessons": "5"}, "subjects": [
        {"subject_id": 1, "subject_name": "Алгебра", "subject_shortname": "Алг",
         "marks": [{"value": "10", "type": "x"}, "8", {"value": "Н"}]}]}
    p = nzua.StudentPerformance.from_api(data)
    assert p.missed_days == 2 and p.subjects[0].average == 9 and p.average == 9


async def test_hometask_and_files():
    def h(req):
        if req.url.path.endswith("distance-hometask"):
            return ok({"hometask": "<p>Вивчити <b>§5</b></p><ul><li>a</li></ul>", "is_closed": False,
                       "answer": None, "hometask_files": [{"id": 1, "name": "f.pdf", "uuid": "u-1"}]})
        if req.url.path.endswith("get-hometask-file"):
            assert req.url.params["uuid"] == "u-1"
            return httpx.Response(200, content=b"PDF")
        return ok({"answer": "готово", "answer_files": []})

    async with client(h, tokens=Tokens("A")) as nz:
        ht = await nz.get_hometask(5)
        assert ht.text == "Вивчити §5\n• a" and ht.files[0].uuid == "u-1"
        assert await nz.download_hometask_file("u-1") == b"PDF"
        assert (await nz.answer_hometask(5, "готово")).text == "готово"


async def test_notifications_and_unread():
    def h(req):
        if req.url.path.endswith("unread-qty"):
            return ok({"qty": "3"})
        return ok({"data": [{"id": "n1", "body": "Нова оцінка", "status": 0, "sentAt": 1759000000,
                             "data": {"type": "add-mark", "lessonName": "Фізика", "markValue": "11"}}]})

    async with client(h, tokens=Tokens("A")) as nz:
        assert await nz.get_unread_count() == 3
        n = (await nz.get_notifications())[0]
        assert n.type == "add-mark" and n.mark == "11" and n.sent_at is not None


def test_strip_html_and_tokens():
    assert strip_html("<div>a&nbsp;b<br>c</div>") == "a\xa0b\nc"
    assert Tokens("a", "b", 1).is_expired() and not Tokens("a").is_expired()


def test_sync_client():
    def h(req):
        return ok(LOGIN) if req.url.path.endswith("login") else ok(DIARY)

    with NZClient(transport=httpx.MockTransport(h)) as nz:
        assert nz.login("u", "p").class_name == "10-А"
        assert nz.get_schedule().average() == 10
