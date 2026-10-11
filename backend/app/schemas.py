"""Pydantic-схемы запросов и ответов API."""
from pydantic import BaseModel, Field

from app.balance import Resolution
from app.compatibility import CheckResult, Issue
from app.models import Category, Component
from app.recommender import Recommendation, RecommendRequest
from app.recommender.alternatives import Alternative
from app.recommender.params import Platform, Scenario

# ---------- Комплектующие ----------


class ComponentOut(BaseModel):
    id: int
    category: Category
    brand: str
    name: str
    title: str
    price_rub: int
    perf_score: int
    power_w: int
    # Характеристики конкретной категории: socket, vram_gb, length_mm и т.д.
    specs: dict

    @classmethod
    def from_model(cls, part: Component) -> "ComponentOut":
        # Колонки дочерней таблицы (cpus, gpus, ...) кроме id — это и есть характеристики
        columns = [c.name for c in type(part).__table__.columns if c.name != "id"]
        return cls(
            id=part.id, category=part.category, brand=part.brand, name=part.name, title=part.title,
            price_rub=part.price_rub, perf_score=part.perf_score, power_w=part.power_w,
            specs={name: getattr(part, name) for name in columns},
        )


# ---------- Совместимость и ручной режим ----------


class IssueOut(BaseModel):
    level: str
    code: str
    message: str
    part_ids: list[int]

    @classmethod
    def from_issue(cls, issue: Issue) -> "IssueOut":
        return cls(level=issue.level, code=issue.code, message=issue.message, part_ids=issue.part_ids)


class CheckIn(BaseModel):
    part_ids: list[int]
    complete: bool = False
    # Разрешение для проверки баланса CPU/GPU; null — не проверять баланс
    resolution: Resolution | None = Resolution.QHD


class CheckOut(BaseModel):
    is_compatible: bool
    issues: list[IssueOut]
    total_price: int
    estimated_power_w: int
    recommended_psu_w: int

    @classmethod
    def from_result(cls, result: CheckResult) -> "CheckOut":
        return cls(
            is_compatible=result.is_compatible,
            issues=[IssueOut.from_issue(i) for i in result.issues],
            total_price=result.total_price,
            estimated_power_w=result.estimated_power_w,
            recommended_psu_w=result.recommended_psu_w,
        )


class OptionsIn(BaseModel):
    part_ids: list[int] = Field(description="Уже выбранные детали (кроме той, что выбирается сейчас)")
    category: Category


class OptionOut(BaseModel):
    component: ComponentOut
    compatible: bool
    reasons: list[str]  # почему деталь не подходит


# ---------- Рекомендации ----------


class RecommendIn(BaseModel):
    budget: int = Field(gt=0, le=2_000_000, description="Бюджет, ₽")
    scenario: Scenario
    resolution: Resolution = Resolution.QHD
    platform: Platform | None = None
    cpu_id: int | None = None
    gpu_id: int | None = None

    def to_request(self) -> RecommendRequest:
        # Берём только поля запроса подбора (у наследников есть ещё part_ids, tier)
        return RecommendRequest(**self.model_dump(include=set(RecommendIn.model_fields)))


class EvaluateIn(RecommendIn):
    """Оценить конкретную сборку (например, после применения замены)."""
    part_ids: list[int]


class AlternativeOut(BaseModel):
    kind: str
    category: Category
    text: str
    price_delta: int
    score_delta_pct: float
    worth_it: bool
    new_part: ComponentOut
    # Детали, которые меняются вынужденно (например, плата при смене процессора на другой сокет)
    also_changed: list[ComponentOut]
    part_ids: list[int]  # детали сборки после замены — чтобы применить её одним запросом

    @classmethod
    def from_alt(cls, alt: Alternative) -> "AlternativeOut":
        return cls(
            kind=alt.kind, category=alt.category, text=alt.text, price_delta=alt.price_delta,
            score_delta_pct=alt.score_delta_pct, worth_it=alt.worth_it,
            new_part=ComponentOut.from_model(alt.new_part),
            also_changed=[ComponentOut.from_model(after) for _, after in alt.extra_changes],
            part_ids=alt.build.part_ids,
        )


class RecommendationOut(BaseModel):
    tier: str | None
    title: str
    parts: list[ComponentOut]
    total_price: int
    score: float
    score_breakdown: dict[str, float]
    check: CheckOut
    upgrades: list[AlternativeOut]
    savings: list[AlternativeOut]
    explanation: str
    explanation_source: str = "template"  # "template" или "llm"
    facts: dict

    @classmethod
    def from_rec(cls, rec: Recommendation) -> "RecommendationOut":
        return cls(
            tier=rec.tier.value if rec.tier else None,
            title=rec.title,
            parts=[ComponentOut.from_model(p) for p in rec.build.parts],
            total_price=rec.build.total_price,
            score=round(rec.score, 1),
            score_breakdown={k: round(v, 2) for k, v in rec.breakdown.contributions.items()},
            check=CheckOut.from_result(rec.check),
            upgrades=[AlternativeOut.from_alt(a) for a in rec.upgrades],
            savings=[AlternativeOut.from_alt(a) for a in rec.savings],
            explanation=rec.explanation,
            facts=rec.facts,
        )


class RecommendOut(BaseModel):
    allocation: dict[str, int]  # плановое распределение бюджета по категориям, ₽
    recommendations: list[RecommendationOut]


# ---------- ИИ ----------


class AiStatusOut(BaseModel):
    enabled: bool
    provider: str
    model: str


class ParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)


class ParseOut(BaseModel):
    params: RecommendIn | None  # None — из текста не удалось понять бюджет
    source: str  # "llm" или "rules"
    notes: str  # пояснение для пользователя: что понято и что нет


class ExplainIn(RecommendIn):
    part_ids: list[int]
    tier: str | None = None


class ExplainOut(BaseModel):
    text: str
    source: str  # "llm" или "template"
