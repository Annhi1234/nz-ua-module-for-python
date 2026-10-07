"""Демо-дані без мережі: `python -m nzua.ui --demo` показує інтерфейс на вигаданому щоденнику."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .. import models as m

__all__ = ("DemoClient",)

_SUBJECTS = [("Алгебра", "Сидоренко О.І.", ["11", "10", "12"]), ("Фізика", "Мельник Т.П.", ["8", "9"]),
             ("Українська мова", "Бондар Н.В.", ["10", "Н"]), ("Історія України", "Ткачук В.М.", ["5"]),
             ("Англійська мова", "Коваль І.Р.", ["12", "11"]), ("Біологія", "Шевченко Л.А.", ["3", "7"])]


class DemoClient:
    """Підміняє AsyncNZClient: ті самі методи, але дані вигадані."""
    student = m.Student(id=1, full_name="Іваненко Іван", class_name="10-А", class_manager="Петренко П.П.")
    is_authenticated = True

    async def restore_session(self) -> bool:
        return True

    async def login(self, username: str, password: str, push_token: str = "") -> m.Student:
        return self.student

    async def logout(self, push_token: str = "") -> None:
        return None

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    @staticmethod
    def _days(start: date, end: date) -> list[date]:
        d, out = start, []
        while d <= end and len(out) < 7:
            if d.weekday() < 5:
                out.append(d)
            d += timedelta(days=1)
        return out

    def _day(self, d: date, grades: bool) -> dict:
        calls = []
        for i in range(4):
            name, teacher, marks = _SUBJECTS[(d.toordinal() + i) % len(_SUBJECTS)]
            sub: dict[str, Any] = {"subject_name": name, "room": str(10 + i), "teacher": {"id": i, "name": teacher}}
            if grades:
                sub["hometask"] = [f"§{d.day + i}"] if i % 2 == 0 else []
                sub["distance_hometask_id"] = 90 + i if i == 1 else None
                if (d.day + i) % 2 == 0:
                    sub["lesson"] = [{"type": "Урок", "mark": marks[(d.day + i) % len(marks)]}]
            calls.append({"call_id": i, "call_number": i + 1, "call_time_start": f"{8 + i}:30",
                          "call_time_end": f"{9 + i}:15", "time_start": f"{8 + i}:30", "time_end": f"{9 + i}:15",
                          "subjects": [sub]})
        return {"date": str(d), "calls": calls}

    async def get_schedule(self, start: Any = None, end: Any = None) -> m.Schedule:
        s, e = _range(start, end)
        return m.Schedule.from_api({"dates": [self._day(d, True) for d in self._days(s, e)]})

    async def get_timetable(self, start: Any = None, end: Any = None) -> m.Timetable:
        s, e = _range(start, end)
        return m.Timetable.from_api({"dates": [self._day(d, False) for d in self._days(s, e)]})

    async def get_student_performance(self, start: Any = None, end: Any = None) -> m.StudentPerformance:
        return m.StudentPerformance.from_api({"missed": {"days": 2, "lessons": 5}, "subjects": [
            {"subject_id": i + 1, "subject_name": n, "marks": [{"value": v} for v in marks * 2]}
            for i, (n, _, marks) in enumerate(_SUBJECTS)]})

    async def get_missed_lessons(self, start: Any = None, end: Any = None) -> m.MissedLessons:
        d = date.today() - timedelta(days=3)
        return m.MissedLessons.from_api({"missed_lessons": [
            {"lesson_id": 1, "lesson_number": 2, "subject": "Фізика", "lesson_date": str(d)}]})

    async def get_subject_performance(self, subject_id: Any, start: Any = None, end: Any = None) -> m.SubjectPerformance:
        name, _, marks = _SUBJECTS[(int(subject_id) - 1) % len(_SUBJECTS)]
        d = date.today()
        return m.SubjectPerformance.from_api({"number_missed_lessons": 1, "lessons": [
            {"lesson_id": i, "subject": name, "lesson_date": str(d - timedelta(days=i * 3)), "lesson_type": "Урок",
             "mark": v} for i, v in enumerate(marks * 2)]})

    async def get_hometask(self, hometask_id: Any) -> m.Hometask:
        return m.Hometask.from_api({"hometask": "<p>Виконати вправи 5–8.</p><p>Підготувати доповідь.</p>",
                                    "answer": None, "is_closed": False})

    async def answer_hometask(self, hometask_id: Any, text: str, delete_file_ids: Any = ()) -> m.HometaskAnswer:
        return m.HometaskAnswer.from_api({"answer": text})

    async def get_notifications(self) -> list[m.Notification]:
        return [m.Notification.from_api({"id": str(i), "body": f"Нова оцінка з предмета «{n}»", "sentAt": 1_760_000_000 + i * 3600,
                                         "data": {"markValue": marks[0]}})
                for i, (n, _, marks) in enumerate(_SUBJECTS[:4])]

    async def get_unread_count(self) -> int:
        return 2


def _range(start: Any, end: Any) -> tuple[date, date]:
    s = start if isinstance(start, date) else date.today() - timedelta(days=date.today().weekday())
    return s, end if isinstance(end, date) else s + timedelta(days=6)
