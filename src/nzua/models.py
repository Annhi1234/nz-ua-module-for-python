"""Типізовані моделі відповідей (stdlib dataclasses, без pydantic).

Кожна модель має `from_api(dict)` і зберігає оригінальний JSON у `raw`,
тож нові поля API не ламають розбір.
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Iterable, Iterator

from ._parse import strip_html, to_date, to_datetime, to_int, to_time

__all__ = (
    "Tokens", "Student", "Teacher", "Grade", "Schedule", "ScheduleDay",
    "ScheduleLesson", "ScheduleSubject", "Timetable", "TimetableDay",
    "TimetableLesson", "TimetableSubject", "StudentPerformance",
    "PerformanceSubject", "PerformanceMark", "SubjectPerformance",
    "SubjectLesson", "MissedLesson", "MissedLessons", "Hometask",
    "HometaskFile", "HometaskAnswer", "Notification", "MarkValue", "average",
)

_M = dict(frozen=True, slots=True, kw_only=True)


def average(values: Iterable[int | None]) -> float | None:
    nums = [v for v in values if v is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def _mark_value(mark: str | None) -> int | None:
    """'8' -> 8; 'Н', 'зар' та інші нечислові -> None."""
    return int(mark) if mark and mark.strip().isdigit() else None


def _tuple(items, fn) -> tuple:
    return tuple(fn(i) for i in (items or []) if isinstance(i, dict))


@dataclass(frozen=True, slots=True)
class Tokens:
    access_token: str
    refresh_token: str | None = None
    expires_at: int | None = None  # epoch, секунди

    def is_expired(self, skew: int = 60) -> bool:
        if self.expires_at is None:
            return False
        at = self.expires_at / 1000 if self.expires_at > 10**11 else self.expires_at  # мс → с
        return _time.time() >= at - skew

    def to_dict(self) -> dict:
        return {"access_token": self.access_token,
                "refresh_token": self.refresh_token, "expires_at": self.expires_at}

    @classmethod
    def from_dict(cls, d: dict) -> "Tokens":
        return cls(d["access_token"], d.get("refresh_token"), d.get("expires_at"))


@dataclass(**_M)
class _Base:
    raw: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass(**_M)
class _Result(_Base):
    """Базовий клас для відповідей верхнього рівня."""
    from_cache: bool = field(default=False, compare=False)


# ───────────────────────── профіль ─────────────────────────
@dataclass(**_M)
class Student(_Base):
    id: int
    full_name: str
    class_name: str | None = None
    class_manager: str | None = None
    avatar_url: str | None = None
    avatar_updated_at: datetime | None = None
    email_hash: str | None = None
    permissions: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict) -> "Student":
        av = d.get("avatar") or {}
        return cls(
            id=to_int(d.get("student_id"), 0), full_name=d.get("FIO", ""),
            class_name=d.get("class_name"), class_manager=d.get("class_manager_fio"),
            avatar_url=av.get("image_url") or None,
            avatar_updated_at=to_datetime(av.get("datetime")),
            email_hash=d.get("email_hash"), permissions=d.get("permissions") or {},
            raw=d)


@dataclass(**_M)
class Teacher(_Base):
    id: int | None
    name: str

    @classmethod
    def from_api(cls, d: dict | None) -> "Teacher | None":
        if not isinstance(d, dict):
            return None
        return cls(id=to_int(d.get("id")), name=d.get("name", ""), raw=d)


# ───────────────────────── щоденник ─────────────────────────
@dataclass(**_M)
class Grade(_Base):
    type: str
    mark: str
    comment: str | None = None

    @property
    def value(self) -> int | None:
        return _mark_value(self.mark)

    @classmethod
    def from_api(cls, d: dict) -> "Grade":
        return cls(type=d.get("type", ""), mark=str(d.get("mark", "")),
                   comment=d.get("comment") or None, raw=d)


@dataclass(**_M)
class ScheduleSubject(_Base):
    name: str
    room: str | None = None
    teacher: Teacher | None = None
    homework: tuple[str, ...] = ()
    hometask_id: int | None = None
    hometask_is_closed: bool | None = None
    grades: tuple[Grade, ...] = ()

    @classmethod
    def from_api(cls, d: dict) -> "ScheduleSubject":
        hw = d.get("hometask") or []
        return cls(
            name=d.get("subject_name", ""), room=d.get("room"),
            teacher=Teacher.from_api(d.get("teacher")),
            homework=tuple(hw) if isinstance(hw, list) else (str(hw),),
            hometask_id=to_int(d.get("distance_hometask_id")),
            hometask_is_closed=d.get("distance_hometask_is_closed"),
            grades=_tuple(d.get("lesson"), Grade.from_api), raw=d)


@dataclass(**_M)
class ScheduleLesson(_Base):
    id: int | None
    number: int | None
    start: time | None = None
    end: time | None = None
    subjects: tuple[ScheduleSubject, ...] = ()

    @classmethod
    def from_api(cls, d: dict) -> "ScheduleLesson":
        return cls(
            id=to_int(d.get("call_id")), number=to_int(d.get("call_number")),
            start=to_time(d.get("call_time_start")), end=to_time(d.get("call_time_end")),
            subjects=_tuple(d.get("subjects"), ScheduleSubject.from_api), raw=d)


@dataclass(**_M)
class ScheduleDay(_Base):
    date: date | None
    lessons: tuple[ScheduleLesson, ...] = ()

    @classmethod
    def from_api(cls, d: dict) -> "ScheduleDay":
        return cls(date=to_date(d.get("date")),
                   lessons=_tuple(d.get("calls"), ScheduleLesson.from_api), raw=d)


@dataclass(**_M)
class Schedule(_Result):
    days: tuple[ScheduleDay, ...] = ()

    def __len__(self) -> int:
        return len(self.days)

    def __iter__(self) -> Iterator[ScheduleDay]:
        return iter(self.days)

    def grades(self) -> Iterator[tuple[date | None, str, Grade]]:
        """(дата, предмет, оцінка) для кожної оцінки за період."""
        for day in self.days:
            for lesson in day.lessons:
                for s in lesson.subjects:
                    for g in s.grades:
                        yield day.date, s.name, g

    def average(self) -> float | None:
        return average(g.value for _, _, g in self.grades())

    @classmethod
    def from_api(cls, d: dict) -> "Schedule":
        return cls(days=_tuple(d.get("dates"), ScheduleDay.from_api), raw=d)


# ───────────────────────── розклад ─────────────────────────
@dataclass(**_M)
class TimetableSubject(_Base):
    name: str
    room: str | None = None
    teacher: Teacher | None = None

    @classmethod
    def from_api(cls, d: dict) -> "TimetableSubject":
        return cls(name=d.get("subject_name", ""), room=d.get("room"),
                   teacher=Teacher.from_api(d.get("teacher")), raw=d)


@dataclass(**_M)
class TimetableLesson(_Base):
    id: int | None
    number: int | None
    start: time | None = None
    end: time | None = None
    subjects: tuple[TimetableSubject, ...] = ()

    @classmethod
    def from_api(cls, d: dict) -> "TimetableLesson":
        return cls(
            id=to_int(d.get("call_id")), number=to_int(d.get("call_number")),
            start=to_time(d.get("time_start")), end=to_time(d.get("time_end")),
            subjects=_tuple(d.get("subjects"), TimetableSubject.from_api), raw=d)


@dataclass(**_M)
class TimetableDay(_Base):
    date: date | None
    lessons: tuple[TimetableLesson, ...] = ()

    @classmethod
    def from_api(cls, d: dict) -> "TimetableDay":
        return cls(date=to_date(d.get("date")),
                   lessons=_tuple(d.get("calls"), TimetableLesson.from_api), raw=d)


@dataclass(**_M)
class Timetable(_Result):
    days: tuple[TimetableDay, ...] = ()

    def __len__(self) -> int:
        return len(self.days)

    def __iter__(self) -> Iterator[TimetableDay]:
        return iter(self.days)

    @classmethod
    def from_api(cls, d: dict) -> "Timetable":
        return cls(days=_tuple(d.get("dates"), TimetableDay.from_api), raw=d)


# ───────────────────────── успішність ─────────────────────────
@dataclass(**_M)
class PerformanceMark(_Base):
    mark: str
    type: str | None = None

    @property
    def value(self) -> int | None:
        return _mark_value(self.mark)

    @classmethod
    def from_api(cls, d: Any) -> "PerformanceMark":
        if isinstance(d, dict):  # v2: {"value": "8", "type": "..."}
            return cls(mark=str(d.get("value", "")), type=d.get("type"), raw=d)
        return cls(mark=str(d))  # v1: просто рядок


@dataclass(**_M)
class PerformanceSubject(_Base):
    id: int
    name: str
    short_name: str | None = None
    marks: tuple[PerformanceMark, ...] = ()

    @property
    def average(self) -> float | None:
        return average(m.value for m in self.marks)

    @classmethod
    def from_api(cls, d: dict) -> "PerformanceSubject":
        return cls(
            id=to_int(d.get("subject_id"), 0), name=d.get("subject_name", ""),
            short_name=d.get("subject_shortname"),
            marks=tuple(PerformanceMark.from_api(m) for m in d.get("marks") or []),
            raw=d)


@dataclass(**_M)
class StudentPerformance(_Result):
    missed_days: int = 0
    missed_lessons: int = 0
    subjects: tuple[PerformanceSubject, ...] = ()

    @property
    def average(self) -> float | None:
        return average(m.value for s in self.subjects for m in s.marks)

    @classmethod
    def from_api(cls, d: dict) -> "StudentPerformance":
        missed = d.get("missed") or {}
        return cls(missed_days=to_int(missed.get("days"), 0),
                   missed_lessons=to_int(missed.get("lessons"), 0),
                   subjects=_tuple(d.get("subjects"), PerformanceSubject.from_api),
                   raw=d)


@dataclass(**_M)
class SubjectLesson(_Base):
    id: int | None
    subject: str
    date: date | None
    type: str
    mark: str
    comment: str | None = None

    @property
    def value(self) -> int | None:
        return _mark_value(self.mark)

    @classmethod
    def from_api(cls, d: dict) -> "SubjectLesson":
        return cls(id=to_int(d.get("lesson_id")), subject=d.get("subject", ""),
                   date=to_date(d.get("lesson_date")), type=d.get("lesson_type", ""),
                   mark=str(d.get("mark", "")), comment=d.get("comment") or None, raw=d)


@dataclass(**_M)
class SubjectPerformance(_Result):
    missed_lessons: int = 0
    lessons: tuple[SubjectLesson, ...] = ()

    @property
    def average(self) -> float | None:
        return average(x.value for x in self.lessons)

    @classmethod
    def from_api(cls, d: dict) -> "SubjectPerformance":
        return cls(missed_lessons=to_int(d.get("number_missed_lessons"), 0),
                   lessons=_tuple(d.get("lessons"), SubjectLesson.from_api), raw=d)


@dataclass(**_M)
class MissedLesson(_Base):
    id: int | None
    number: int | None
    subject: str
    date: date | None

    @classmethod
    def from_api(cls, d: dict) -> "MissedLesson":
        return cls(id=to_int(d.get("lesson_id")), number=to_int(d.get("lesson_number")),
                   subject=d.get("subject", ""), date=to_date(d.get("lesson_date")), raw=d)


@dataclass(**_M)
class MissedLessons(_Result):
    lessons: tuple[MissedLesson, ...] = ()

    def __len__(self) -> int:
        return len(self.lessons)

    def __iter__(self) -> Iterator[MissedLesson]:
        return iter(self.lessons)

    @classmethod
    def from_api(cls, d: dict) -> "MissedLessons":
        return cls(lessons=_tuple(d.get("missed_lessons"), MissedLesson.from_api), raw=d)


# ───────────────────────── дистанційні завдання ─────────────────────────
@dataclass(**_M)
class HometaskFile(_Base):
    id: int | None
    name: str
    uuid: str | None = None
    url: str | None = None
    size: int | None = None
    created_at: datetime | None = None

    @classmethod
    def from_api(cls, d: dict) -> "HometaskFile":
        return cls(id=to_int(d.get("id")), name=d.get("name", ""), uuid=d.get("uuid"),
                   url=d.get("url"), size=to_int(d.get("size")),
                   created_at=to_datetime(d.get("created_at")), raw=d)


@dataclass(**_M)
class Hometask(_Result):
    html: str = ""
    answer_html: str | None = None
    is_closed: bool = False
    answer_files: tuple[HometaskFile, ...] = ()
    files: tuple[HometaskFile, ...] = ()

    @property
    def text(self) -> str:
        return strip_html(self.html)

    @property
    def answer(self) -> str | None:
        return strip_html(self.answer_html) if self.answer_html else None

    @classmethod
    def from_api(cls, d: dict) -> "Hometask":
        return cls(html=d.get("hometask") or "", answer_html=d.get("answer"),
                   is_closed=bool(d.get("is_closed")),
                   answer_files=_tuple(d.get("answer_files"), HometaskFile.from_api),
                   files=_tuple(d.get("hometask_files"), HometaskFile.from_api), raw=d)


@dataclass(**_M)
class HometaskAnswer(_Base):
    text: str | None
    files: tuple[HometaskFile, ...] = ()

    @classmethod
    def from_api(cls, d: dict) -> "HometaskAnswer":
        return cls(text=d.get("answer"),
                   files=_tuple(d.get("answer_files"), HometaskFile.from_api), raw=d)


# ───────────────────────── сповіщення, довідники ─────────────────────────
@dataclass(**_M)
class Notification(_Base):
    id: str
    body: str
    type: str | None = None  # напр. "add-mark"
    student_name: str | None = None
    lesson_name: str | None = None
    mark: str | None = None
    comment: str | None = None
    lesson_type: str | None = None
    status: int | None = None
    sent_at: datetime | None = None

    @classmethod
    def from_api(cls, d: dict) -> "Notification":
        x = d.get("data") or {}
        return cls(
            id=str(d.get("id", "")), body=d.get("body", ""), type=x.get("type"),
            student_name=x.get("studentName"), lesson_name=x.get("lessonName"),
            mark=x.get("markValue"), comment=x.get("comment") or None,
            lesson_type=x.get("lessonType"), status=to_int(d.get("status")),
            sent_at=to_datetime(d.get("sentAt")), raw=d)


@dataclass(**_M)
class MarkValue(_Base):
    """Варіант оцінки для виставлення (розділ для вчителів)."""
    id: int
    code: int
    value: str
    description: str
    max_value: int | None = None
    html_class: str | None = None

    @classmethod
    def from_api(cls, d: dict) -> "MarkValue":
        return cls(id=to_int(d.get("mark_value_id"), 0), code=to_int(d.get("code"), 0),
                   value=str(d.get("value", "")), description=d.get("description", ""),
                   max_value=to_int(d.get("max_value")), html_class=d.get("html_class"),
                   raw=d)
