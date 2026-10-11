"""Проверка сборки целиком и фильтр совместимых вариантов для ручного режима."""
from dataclasses import dataclass

from app.compatibility.rules import COMPLETE_BUILD_RULES, RULES, Issue, Level, recommended_psu_w
from app.domain import Build
from app.models import Component


@dataclass
class CheckResult:
    issues: list[Issue]
    total_price: int
    estimated_power_w: int
    recommended_psu_w: int

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == Level.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == Level.WARNING]

    @property
    def is_compatible(self) -> bool:
        return not self.errors


def check_build(build: Build, complete: bool = False) -> CheckResult:
    """Прогоняет сборку через все правила.

    complete=True — сборка считается законченной, и дополнительно проверяется,
    что выбраны все обязательные детали, есть вывод изображения и охлаждение.
    """
    rules = RULES + (COMPLETE_BUILD_RULES if complete else [])
    issues = [issue for rule in rules for issue in rule(build)]
    return CheckResult(
        issues=issues,
        total_price=build.total_price,
        estimated_power_w=build.estimated_power_w,
        recommended_psu_w=recommended_psu_w(build),
    )


def candidate_errors(build: Build, candidate: Component) -> list[Issue]:
    """Ошибки, которые появятся, если поставить деталь candidate в сборку.

    Учитываются только ошибки, в которых участвует сам кандидат: если в сборке
    уже есть проблема между другими деталями, кандидат в ней не виноват.
    """
    result = check_build(build.with_part(candidate))
    return [e for e in result.errors if candidate.id in e.part_ids]


def filter_compatible(build: Build, candidates: list[Component]) -> list[Component]:
    """Оставляет только детали, которые можно поставить в текущую сборку."""
    return [c for c in candidates if not candidate_errors(build, c)]
