"""Модуль проверки совместимости комплектующих."""

from app.compatibility.checker import CheckResult, candidate_errors, check_build, filter_compatible
from app.compatibility.rules import Issue, Level, recommended_psu_w

__all__ = [
    "CheckResult",
    "Issue",
    "Level",
    "candidate_errors",
    "check_build",
    "filter_compatible",
    "recommended_psu_w",
]
