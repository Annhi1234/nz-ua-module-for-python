# nzua — посібник користувача

Неофіційна бібліотека, консольна утиліта й Android-застосунок для електронного щоденника **nz.ua**
(API `api-mobile.nz.ua`, версія v2).

**Зміст:** [1. Встановлення](#1-встановлення) · [2. Швидкий старт](#2-швидкий-старт) ·
[3. Вхід і сесії](#3-вхід-і-сесії) · [4. Дати й періоди](#4-дати-й-періоди) ·
[5. Методи клієнта](#5-методи-клієнта) · [6. Моделі даних](#6-моделі-даних) ·
[7. Помилки](#7-помилки) · [8. Кеш і офлайн](#8-кеш-і-офлайн) ·
[9. Параметри клієнта](#9-параметри-клієнта) · [10. Графіки](#10-графіки) ·
[11. Аналітика](#11-аналітика) · [12. Командний рядок](#12-командний-рядок) ·
[13. Android-застосунок](#13-android-застосунок) · [14. Тестування](#14-тестування-власного-коду) ·
[15. Типові проблеми](#15-типові-проблеми) · [16. Міграція зі старої бібліотеки](#16-міграція-зі-старої-бібліотеки)

---

## 1. Встановлення

Потрібен Python 3.10 або новіший. Єдина залежність — `httpx`.

    pip install -e .            # з каталогу проєкту
    pip install -e ".[dev]"     # разом із pytest для тестів

Після встановлення з'являється команда `nzua` (також працює `python -m nzua`).

## 2. Швидкий старт

**Async** (основний варіант, його використовує застосунок):

```python
import asyncio
from nzua import AsyncNZClient

async def main():
    async with AsyncNZClient() as nz:
        student = await nz.login("логін", "пароль")
        print(student.full_name, student.class_name)

        schedule = await nz.get_schedule()            # від 1-го числа до сьогодні
        print("Середній бал:", schedule.average())
        for day, subject, grade in schedule.grades():
            print(day, subject, grade.mark)

asyncio.run(main())
```

**Sync** — ті самі методи без `await`. Усередині працює власний потік із event loop:

```python
from nzua import NZClient

with NZClient() as nz:
    nz.login("логін", "пароль")
    print(nz.get_student_performance().average)
```

Використовуйте `async with` / `with`, щоб з'єднання закрилось. Без менеджера контексту викличте
`await nz.aclose()` (або `nz.close()` у sync-версії).

## 3. Вхід і сесії

`login(username, password, push_token="")` повертає `Student` і зберігає токени в клієнті.
Токени доступні як `nz.tokens` (`Tokens`: `access_token`, `refresh_token`, `expires_at`).

**Автоматичне оновлення.** Перед кожним запитом клієнт перевіряє `expires_at` і за потреби оновлює токен.
Якщо сервер відповів 401, клієнт один раз оновлює токен і повторює запит. Одночасні запити не оновлюють
токен двічі. Якщо оновити не вдалося, сесія очищується й виникає `SessionExpired`: потрібен новий `login`.

**Збереження сесії між запусками** — через `token_store`:

```python
from pathlib import Path
from nzua import AsyncNZClient, FileTokenStore

async def connect() -> AsyncNZClient:
    store = FileTokenStore(Path.home() / ".nzua" / "tokens.json")
    nz = AsyncNZClient(token_store=store)
    if not await nz.restore_session():    # підхоплює збережені токени
        await nz.login("логін", "пароль")
    return nz
```

| Сховище | Призначення |
|---|---|
| `MemoryTokenStore` | типове, тільки в пам'яті |
| `FileTokenStore(path)` | JSON-файл із правами 600 |
| власне | будь-який клас з `async load()`, `async save(tokens)`, `async clear()` (застосунок використовує Android Keystore) |

Пароль бібліотека ніде не зберігає.

`logout()` повідомляє сервер, видаляє токени зі сховища й очищує кеш. Помилка мережі під час виходу
не заважає вийти локально. `refresh_token()` оновлює токен примусово. `ping()` перевіряє, чи працює API
(без авторизації).

## 4. Дати й періоди

Параметри `start_date`, `end_date` приймають `"2026-10-01"`, `date` або `datetime`.
Якщо не вказати, період — **від 1-го числа поточного місяця до сьогодні** (обчислюється в момент виклику).
Якщо початок пізніше за кінець, виникає `ValueError`.

```python
from datetime import date, timedelta
today = date.today()
week = await nz.get_timetable(today - timedelta(days=today.weekday()), today + timedelta(days=6))
```

## 5. Методи клієнта

Усі методи — `async` в `AsyncNZClient`. Методи читання, що повертають моделі верхнього рівня, використовують кеш.

| Метод | Параметри | Повертає |
|---|---|---|
| `login` | `username, password, push_token=""` | `Student` |
| `logout` | `push_token=""` | `None` |
| `refresh_token` | — | `Tokens` |
| `restore_session` | — | `bool` |
| `ping` | — | `bool` |
| `get_schedule` | `start_date, end_date` | `Schedule` (щоденник) |
| `get_timetable` | `start_date, end_date` | `Timetable` |
| `get_student_performance` | `start_date, end_date` | `StudentPerformance` |
| `get_subject_performance` | `subject_id, start_date, end_date` | `SubjectPerformance` |
| `get_missed_lessons` | `start_date, end_date` | `MissedLessons` |
| `get_hometask` | `hometask_id` | `Hometask` |
| `answer_hometask` | `hometask_id, text, delete_file_ids=()` | `HometaskAnswer` |
| `download_hometask_file` | `uuid, save_to=None` | `bytes` (і запис у файл, якщо задано `save_to`) |
| `get_notifications` | — | `list[Notification]` |
| `get_unread_count` | — | `int` |
| `get_mark_values` | — | `list[MarkValue]` (розділ для вчителів) |
| `create_temporary_link` | `url` | `str` |
| `get_temporary_link` | `link_hash` | `str` (HTML) |

`subject_id` беріть з `StudentPerformance.subjects[i].id`. `hometask_id` — з `ScheduleSubject.hometask_id`.

**Дистанційні завдання:**

```python
sub = next(s for d in schedule.days for l in d.lessons for s in l.subjects if s.hometask_id)
task = await nz.get_hometask(sub.hometask_id)
print(task.text)                       # текст без HTML
for f in task.files:
    await nz.download_hometask_file(f.uuid, save_to=f.name)
await nz.answer_hometask(sub.hometask_id, "Виконано, §5 № 12–15")
await nz.answer_hometask(sub.hometask_id, "Нова відповідь", delete_file_ids=[123])  # прибрати файл
```

Завантаження файлів у відповідь у документації API не описане, тому бібліотека його не підтримує.

## 6. Моделі даних

Моделі — незмінні `dataclass` (`frozen`, `slots`). Кожна має `from_api(dict)` та поле `raw` з оригінальним
JSON (не входить у порівняння й `repr`). Відсутні поля стають `None`/порожніми значеннями, а не помилкою.
Моделі верхнього рівня мають `from_cache: bool`.

| Модель | Поля й корисні члени |
|---|---|
| `Student` | `id, full_name, class_name, class_manager, avatar_url, email_hash, permissions` |
| `Schedule` | `days` → `ScheduleDay(date, lessons)` → `ScheduleLesson(number, start, end, subjects)` → `ScheduleSubject(name, room, teacher, homework, hometask_id, hometask_is_closed, grades)`. Методи: `grades()` (дата, предмет, `Grade`), `average()`, ітерація по днях, `len()` |
| `Grade` | `type, mark, comment`; `value` — число або `None` (для «Н», «зар» тощо) |
| `Timetable` | `days` → `TimetableDay` → `TimetableLesson` → `TimetableSubject(name, room, teacher)` |
| `StudentPerformance` | `missed_days, missed_lessons, subjects`; `average` |
| `PerformanceSubject` | `id, name, short_name, marks`; `average` |
| `PerformanceMark` | `mark, type`; `value` |
| `SubjectPerformance` | `missed_lessons, lessons` (`SubjectLesson`: `date, type, mark, comment, value`); `average` |
| `MissedLessons` | `lessons` (`MissedLesson`: `date, number, subject`); ітерація, `len()` |
| `Hometask` | `html, answer_html, is_closed, files, answer_files`; `text` і `answer` — без HTML |
| `HometaskFile` | `id, name, uuid, url, size, created_at` |
| `Notification` | `id, body, type, student_name, lesson_name, mark, comment, lesson_type, status, sent_at` |
| `Tokens` | `access_token, refresh_token, expires_at`; `is_expired()` |

Перетворення на словник: `dataclasses.asdict(obj)`.
Старі відповіді API, де оцінка — рядок, і нові, де це об'єкт `{value, type}`, обробляються однаково.

## 7. Помилки

Усі винятки успадковують `NZError`.

| Виняток | Коли |
|---|---|
| `IncorrectUsername`, `IncorrectPassword` | невірні дані під час входу (`IncorrectNickname` — синонім) |
| `HometaskNotFound` | завдання з таким id немає |
| `APIError` | інше повідомлення `error_message` від сервера (`.message`, `.response`) |
| `Unauthorized` | немає токена або він недійсний |
| `SessionExpired` | токен не вдалося оновити, потрібен новий `login` |
| `NetworkError` → `ConnectionTimedOut`, `ServiceUnavailable` | немає зв'язку, таймаут, 503/522 |
| `RateLimited` | HTTP 429 |
| `InternalServerError`, `UnknownError` | збій сервера або несподівана відповідь |

```python
from nzua import NZError, SessionExpired, NetworkError
try:
    perf = await nz.get_student_performance()
except SessionExpired:
    ...                      # показати екран входу
except NetworkError:
    ...                      # немає зв'язку і в кеші немає даних
except NZError as e:
    print(e)
```

## 8. Кеш і офлайн

Передайте `cache` у конструктор: після кожного успішного запиту відповідь запам'ятовується. Коли виникає
`NetworkError` (немає інтернету, таймаут, 503), клієнт повертає останню збережену відповідь для того самого
запиту з `from_cache=True`. Якщо в кеші нічого немає, помилка піднімається як звичайно.

```python
from nzua import AsyncNZClient, FileCache
nz = AsyncNZClient(cache=FileCache("cache.json"))
data = await nz.get_schedule("2026-10-01", "2026-10-07")
if data.from_cache:
    print("Показано збережені дані")
```

Ключ кешу — це шлях запиту плюс параметри, тож інший період не візьме чужі дані.
`MemoryCache` живе до закриття програми. `logout()` очищує кеш. Кеш зберігає оцінки у відкритому вигляді,
тримайте файл у приватному каталозі. Свій кеш — клас з `async get(key)`, `async set(key, value)`, `async clear()`.

## 9. Параметри клієнта

`AsyncNZClient(token=None, *, tokens=None, token_store=None, cache=None, base_url=..., timeout=15.0, retries=2, headers=None, transport=None)`

| Параметр | Значення |
|---|---|
| `token` / `tokens` | готовий access-токен або `Tokens` (наприклад, з попередньої сесії) |
| `token_store` | куди зберігати токени (розділ 3) |
| `cache` | офлайн-кеш (розділ 8) |
| `base_url` | адреса API, змінюйте лише для тестів |
| `timeout` | таймаут запиту, секунди |
| `retries` | скільки разів повторювати при 502/503/504/522 і мережевих збоях (пауза 0.5 с, 1 с, 2 с…). Для входу, виходу, відповіді на завдання повтори вимкнені |
| `headers` | додаткові заголовки |
| `transport` | `httpx`-транспорт, потрібен для тестів з `httpx.MockTransport` |

Sync-клієнт `NZClient(...)` приймає ті самі параметри.

## 10. Графіки

Модуль `nzua.charts` будує **SVG без залежностей**. Файл відкривається в браузері, редакторах і вставляється
в сайти. Застосунок показує ці ж графіки. Для PNG скористайтесь зовнішнім конвертером (Inkscape, `cairosvg`).

```python
from nzua import ChartStyle, averages_chart, marks_chart, distribution_chart, save_svg

perf = await nz.get_student_performance(period_start, today)
style = ChartStyle(width=800, height=420, colors="ocean", title="Середні бали")
save_svg("average.svg", averages_chart(perf, style))

sch = await nz.get_schedule()
save_svg("marks.svg", marks_chart(sch, ChartStyle(colors="#C8372D"), subject="алгебра"))
save_svg("dist.svg", distribution_chart([g.value for _, _, g in sch.grades()]))
```

Свої дані: `bar_chart(labels, values, style)` і `line_chart(labels, values, style)`.
`None` у значеннях стовпчикового графіка залишає порожнє місце.

### ChartStyle

| Поле | Типово | Що робить |
|---|---|---|
| `width`, `height` | 640, 360 | розмір у пікселях, від 120 до 4000 |
| `colors` | `"scale"` | назва палітри, список кольорів або рядок `"#c00,#0a0"` |
| `background`, `text_color`, `grid_color` | білий, графіт, світло-сірий | кольори фону, тексту й сітки |
| `font_size` | 13 | розмір шрифту |
| `title` | `None` | заголовок |
| `show_values` | `True` | підписи значень |
| `min_value`, `max_value` | 0, 12 | межі осі Y |
| `bar_radius` | 4 | заокруглення стовпчиків |
| `line_width`, `point_radius` | 3, 4 | товщина лінії, розмір точок |
| `responsive` | `False` | `True` — без фіксованої ширини й висоти, графік підлаштовується під контейнер |

**Палітри:** `scale` (колір за оцінкою: 1–3 червоний, 4–6 бурштиновий, 7–12 зелений), `ink`, `ocean`,
`forest`, `sunset`, `mono`. Якщо передати список кольорів, вони чергуються по стовпчиках; у лінійному
графіку перший колір — це колір лінії. Список доступних палітр: `nzua.PALETTES`.

Кольори перевіряються (`#rgb`, `#rrggbb` або назва на кшталт `red`); некоректний колір — `ValueError`.
Усі підписи екрануються, тож у назвах предметів безпечні будь-які символи.

### Графік у Flet

```python
import flet as ft
svg = averages_chart(perf, ChartStyle(width=640, height=300, responsive=True))
ft.Image(src=svg.encode("utf-8"), fit=ft.BoxFit.CONTAIN, height=300)
```

## 11. Аналітика

Чисті функції без мережі в `nzua.analytics` (також доступні як `nzua.needed_marks` тощо):

| Функція | Що робить |
|---|---|
| `needed_marks(marks, target, max_mark=12)` | скільки найвищих оцінок поспіль потрібно, щоб середнє досягло `target`. `0` — вже досягнуто, `None` — недосяжно |
| `rank_subjects(perf, best_first=True)` | предмети з середніми, відсортовані |
| `mark_distribution(values)` | `{1: кількість, …, 12: кількість}` |
| `trend(values)` | `"up"`, `"down"` або `"flat"` (друга половина проти першої) |

```python
needed_marks([8, 9, 10], 10.5)   # 3
```

## 12. Командний рядок

    nzua [--home КАТАЛОГ] [-f table|json|csv] [--no-cache] команда [параметри]

Сесія й кеш лежать у `~/.nzua` (змінна `NZUA_HOME` або `--home` змінює каталог). Спершу виконайте `nzua login`.

| Команда | Що робить |
|---|---|
| `login [-u ЛОГІН] [-p ПАРОЛЬ]` | вхід; пароль можна ввести прихованим запитом або взяти зі змінної `NZUA_PASSWORD` |
| `logout` | вихід, видалення сесії й кешу |
| `status` | чи працює сервер, чи є сесія |
| `grades [--subject ТЕКСТ]` | усі оцінки за період із середнім балом |
| `performance` | успішність по предметах: ID, середній, оцінки, пропуски |
| `subject ID` | оцінки з одного предмета (ID з `performance`) |
| `schedule` | щоденник: уроки, оцінки, домашні завдання |
| `timetable` | розклад |
| `missed` | пропущені уроки |
| `homework ID` | текст дистанційного завдання й файли |
| `answer ID "ТЕКСТ"` | надіслати відповідь |
| `notifications` | сповіщення й кількість непрочитаних |
| `chart averages\|marks\|distribution` | зберегти графік у SVG (див. нижче) |
| `need --marks 8,9,10 --target 10.5` | скільки «12» потрібно для середнього, без входу |

**Період** для команд читання: `--period week|month|year` (типово `month`; `year` — з 1 вересня) або
`--from РРРР-ММ-ДД --to РРРР-ММ-ДД`.

**Формати:** `-f table` (типово), `-f json`, `-f csv`. Ключі в JSON і заголовки CSV англійські та стабільні.

**Параметри `chart`:** `-o ФАЙЛ`, `--width`, `--height`, `--colors` (палітра або `"#c00,#0a0"`), `--title`,
`--subject` (для `marks` і `distribution`), `--no-values`, `--background`, `--text-color`.

Приклади:

    nzua login -u ivan
    nzua grades --period week
    nzua grades --subject алгебра --period year -f csv > algebra.csv
    nzua performance --period year
    nzua subject 12 --period year
    nzua chart averages -o avg.svg --width 900 --height 450 --colors sunset --title "Середні бали"
    nzua chart marks --subject фізика --colors "#26358F"
    nzua need --marks 8,9,10 --target 10.5

**Коди завершення:** `0` — успіх, `1` — помилка, `2` — потрібен вхід (`nzua login`).

## 13. Android-застосунок

Папка `app/` — застосунок «NZ Diary» на Flet 1.0.

**Збірка APK у GitHub (рекомендовано):** завантажте проєкт у репозиторій і запустіть
Actions → Build APK → Run workflow. Через 10–20 хвилин завантажте артефакт `nz-diary-apk`.
Для встановлення дозвольте інсталяцію з невідомих джерел.

**Локальна збірка:**

    sh scripts/sync_lib.sh     # копіює nzua у app/src (потрібно після змін бібліотеки)
    cd app
    pip install flet-cli==1.0.3
    flet build apk

**Запуск на комп'ютері:** `sh scripts/sync_lib.sh && cd app && flet run src/main.py`.

Вкладки: **Щоденник** і **Розклад** (по тижнях, стрілки змінюють тиждень), **Оцінки** (середній бал, графік,
середні по предметах, пропуски; дотик до предмета відкриває його оцінки), **Сповіщення**, **Профіль**.
Дотик до домашнього завдання відкриває його текст і поле відповіді.

**Налаштування графіка** (вкладка «Профіль»): набір кольорів, висота (160–420), підписи значень.
Зберігаються у файлі `settings.json` у каталозі застосунку.

Токени зберігаються в Android Keystore, пароль не зберігається. Без інтернету показуються останні збережені
дані з позначкою про це.

## 14. Тестування власного коду

Клієнту можна підставити фальшивий сервер, тоді мережа не потрібна:

```python
import httpx
from nzua import AsyncNZClient, Tokens

def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"dates": []})

nz = AsyncNZClient(tokens=Tokens("test"), transport=httpx.MockTransport(handler))
```

Тести проєкту запускаються командою `pytest`.

## 15. Типові проблеми

| Симптом | Причина й рішення |
|---|---|
| `Unauthorized: Невалідний токен` | не викликано `login()` і не відновлено сесію. Викличте `login()` або `restore_session()` |
| `SessionExpired` | refresh-токен більше не діє, увійдіть знову |
| `IncorrectPassword` / `IncorrectUsername` | перевірте дані; сервер відповідає українським повідомленням |
| `NetworkError` без даних | немає інтернету й нічого немає в кеші. Підключіть `cache=FileCache(...)` і хоч раз завантажте дані онлайн |
| Порожній `Schedule` | у вибраному періоді немає уроків. Вкажіть інші `start_date`/`end_date` |
| `Grade.value` дорівнює `None` | оцінка нечислова («Н», «зар»), у середнє вона не входить |
| Поле моделі порожнє, а в API воно є | API змінилось. Дивіться `obj.raw` і повідомте про розбіжність |
| Кирилиця «ламається» в консолі Windows | CLI сам перемикає вивід на UTF-8; у старих консолях виконайте `chcp 65001` |

API неофіційне, сервер може змінитись без попередження, а запити роблять від вашого імені. Не робіть їх
надто часто.

## 16. Міграція зі старої бібліотеки

| Було (`nz-ua`) | Стало (`nzua`) |
|---|---|
| `Client(token)` | `AsyncNZClient(token)` або sync `NZClient(token)` |
| `client.login(...)` повертав `Student` із токеном | повертає `Student`, токени в `client.tokens`, зберігаються у `token_store` |
| API `/v1/` | API `/v2/`, автооновлення токена |
| pydantic-моделі, `.dict()` | `dataclass`, `dataclasses.asdict(obj)` |
| `Schedule.dates[].calls[].subjects[]` | `Schedule.days[].lessons[].subjects[]` |
| `SubjectsPerformance` | `SubjectPerformance` |
| `delete_hometask_file(file_id)` | `answer_hometask(id, text, delete_file_ids=[file_id])` |
| `IncorrectNickname` | `IncorrectUsername` (старе ім'я залишилось синонімом) |
| `get_schedule`, `get_timetable`, `get_student_performance`, `get_subject_performance`, `get_hometask` | ті самі назви, нові параметри дат за замовчуванням |
