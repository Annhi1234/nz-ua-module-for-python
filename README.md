# nzua

Неофіційна бібліотека для електронного щоденника **nz.ua** (API `api-mobile.nz.ua`, версія **v2**)
і Android-застосунок на Flet. Наступник бібліотеки `MrPandir/nz-ua`.

- `src/nzua` — бібліотека (`httpx` + `curl_cffi`), команда `nzua`, SVG-графіки, аналітика
- `src/nzua/ui` — **конструктор інтерфейсу**: віджети, таблиці, стилі й теми для Tkinter / PyQt5 / Flet
- `docs/GUIDE.md` — **повний посібник** (методи, моделі, помилки, CLI, графіки, збірка APK)
- `app/` — Flet-застосунок «NZ Diary» (увесь UI — з `nzua.ui`)
- `examples/` — приклад власного інтерфейсу
- `tests/` — тести на моках (`pytest`)

## Встановлення

    pip install -e ".[dev]"
    pytest

## Використання

Async (основний варіант):

    import asyncio
    from nzua import AsyncNZClient

    async def main():
        async with AsyncNZClient() as nz:
            await nz.login("логін", "пароль")
            schedule = await nz.get_schedule()          # поточний місяць
            print(schedule.average())
            for day, subject, grade in schedule.grades():
                print(day, subject, grade.mark)

    asyncio.run(main())

Sync (ті самі методи, без `await`):

    from nzua import NZClient
    with NZClient() as nz:
        nz.login("логін", "пароль")
        print(nz.get_student_performance().average)

### Методи

| Метод | Що повертає |
|---|---|
| `login`, `logout`, `refresh_token`, `restore_session`, `ping` | авторизація, перевірка API |
| `get_schedule(start, end)` | щоденник: уроки, оцінки, домашні завдання |
| `get_timetable(start, end)` | розклад із вчителями |
| `get_student_performance(start, end)` | успішність по предметах, пропуски |
| `get_subject_performance(subject_id, start, end)` | оцінки з одного предмета |
| `get_missed_lessons(start, end)` | пропущені уроки |
| `get_hometask(id)`, `answer_hometask(id, text, delete_file_ids)` | дистанційні завдання |
| `download_hometask_file(uuid, save_to)` | файл завдання |
| `get_notifications()`, `get_unread_count()` | сповіщення |
| `get_mark_values()` | довідник оцінок (розділ вчителів) |
| `create_temporary_link(url)`, `get_temporary_link(hash)` | тимчасові посилання |

Дати: `str` (`"2026-10-01"`), `date` або `datetime`. За замовчуванням — від 1-го числа
поточного місяця до сьогодні (обчислюється під час виклику).

### Що нового порівняно зі старою бібліотекою

- API **v2** (було v1); нові поля: клас, класний керівник, вчитель, час дзвінків.
- **Автооновлення токена** (за `expires_token` і після 401), збереження через `TokenStore`.
- Повтори запитів із паузою при 502/503/504/522 та мережевих помилках.
- **Офлайн-кеш**: `AsyncNZClient(cache=FileCache("cache.json"))` — без інтернету
  повертаються останні дані, `result.from_cache == True`.
- Звичайні `dataclass` замість pydantic (менше залежностей, простіше зібрати під Android).
- Помилки з `error_message` перетворюються на винятки (`IncorrectPassword` тощо).
- Текст завдань очищується від HTML (`hometask.text`), є `average()` по оцінках.
- Виправлено: дати за замовчуванням, змінні аргументи за замовчуванням, `token` без `return`.
- Кожна модель зберігає оригінальний JSON у `.raw`.
- Команда `nzua`, графіки (кольори й розміри налаштовуються), аналітика (`needed_marks`, `rank_subjects`).

## TLS-відбиток (Cloudflare)

Клієнт **типово** ходить на `api-mobile.nz.ua` із TLS-відбитком Chrome (`curl_cffi`) — звичайні заголовки
httpx Cloudflare блокує. Якщо `curl_cffi` не встановлено, з'являється попередження й працює звичайний httpx.
Вимкнути: `AsyncNZClient(impersonate=False)`. Деталі — GUIDE, розділи 9 і 15.

## Свій інтерфейс (nzua.ui)

    from nzua.ui import App, Screen, Column, Text, Table, Button
    App(lambda app: Screen(Column([Text("Оцінки", cls="h2"), Table(["Предмет", "Бал"], [["Алгебра", 11]])])),
        backend="tk").run()        # tk | qt | flet

Таблиці зі стилями комірок, кнопки, картки, графіки, теми, діалоги, готові блоки для даних nzua
(`screens.grades_table`, `journal_table` …). Повний опис — GUIDE, розділ 17.

## Командний рядок і графіки

    nzua login -u ivan
    nzua grades --period week              # оцінки
    nzua performance --period year         # успішність
    nzua chart averages -o avg.svg --width 900 --height 450 --colors sunset
    nzua need --marks 8,9,10 --target 10.5 # скільки «12» треба для середнього
    nzua diagnose --save                   # якщо 403 / «Just a moment...» (Cloudflare)
    nzua gui --demo                        # графічний щоденник (Tkinter / PyQt5 / Flet)

Усі команди: `nzua --help`, детально — у [docs/GUIDE.md](docs/GUIDE.md). Формати виводу: `-f table|json|csv`.

## Android-застосунок

APK у цьому середовищі не збирався (немає доступу до Android SDK), тому збірка — у GitHub Actions:

1. Завантажте проєкт у репозиторій GitHub.
2. **Actions → Build APK → Run workflow**.
3. Через 10–20 хвилин завантажте артефакт `nz-diary-apk` і встановіть `.apk` на телефон
   (дозвольте встановлення з невідомих джерел).

Локально (потрібні Flutter та Android SDK, їх `flet build` підтягне сам):

    sh scripts/sync_lib.sh
    cd app
    pip install flet-cli==1.0.3
    flet build apk

Запуск на комп'ютері для розробки: `sh scripts/sync_lib.sh && cd app && flet run src/main.py`.

Той самий інтерфейс працює на комп'ютері (`nzua gui`). У застосунку: щоденник і розклад по тижнях, оцінки з середніми балами та пропусками,
дистанційні завдання з відповіддю, сповіщення, офлайн-режим, графік середніх, розподіл оцінок, екран «Сьогодні» з відліком до уроку, кольори предметів, цілі та «що, якщо?», список Д/з з пошуком і позначками, калькулятор цілі, пошук і періоди оцінок; адаптивний інтерфейс (телефон/планшет/комп'ютер) і багато налаштувань вигляду: теми світла/темна/AMOLED/системна, акцентний колір, розмір тексту, щільність. Токени зберігаються в
зашифрованому сховищі системи; пароль не зберігається.

## Обмеження

- API неофіційне й може змінитися. Документація v2 написана спільнотою; відповіді на реальному
  сервері мною не перевірялись, лише на моках за документацією. Парсер толерантний до відсутніх полів.
- Завантаження файлів у відповідь на завдання в документації не описане, тому не реалізоване.
- Застосунок і бекенди Tkinter/PyQt5/Flet не перевірялися на реальних вікнах і пристрої (лише автотести й заглушки).
