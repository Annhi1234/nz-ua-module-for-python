"""Невеликі підрахунки над оцінками (чисті функції, без мережі)."""
from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Sequence

from .models import StudentPerformance

__all__ = ("needed_marks", "rank_subjects", "mark_distribution", "trend")


def needed_marks(marks: Sequence[int], target: float, max_mark: int = 12) -> int | None:
    """Скільки оцінок `max_mark` треба отримати поспіль, щоб середнє стало >= target.

    0 — вже досягнуто; None — недосяжно (target >= max_mark при середньому нижче).
    """
    total, count = sum(marks), len(marks)
    if count and total / count >= target:
        return 0
    if target >= max_mark:
        return None
    n = math.ceil((target * count - total) / (max_mark - target) - 1e-9)
    return max(n, 1)


def rank_subjects(perf: StudentPerformance, *, best_first: bool = True) -> list[tuple[str, float]]:
    """Предмети з середнім балом, відсортовані за спаданням (або зростанням)."""
    rows = [(s.name, s.average) for s in perf.subjects if s.average is not None]
    return sorted(rows, key=lambda r: r[1], reverse=best_first)


def mark_distribution(values: Iterable[int | None], scale: int = 12) -> dict[int, int]:
    """Скільки разів зустрічалась кожна оцінка 1..scale (нулі включно)."""
    c = Counter(v for v in values if v is not None and 1 <= v <= scale)
    return {i: c.get(i, 0) for i in range(1, scale + 1)}


def trend(values: Sequence[int | float], threshold: float = 0.3) -> str:
    """'up' / 'down' / 'flat': порівнює середнє другої половини з першою."""
    if len(values) < 4:
        return "flat"
    half = len(values) // 2
    first = sum(values[:half]) / half
    second = sum(values[half:]) / (len(values) - half)
    diff = second - first
    return "up" if diff > threshold else "down" if diff < -threshold else "flat"
