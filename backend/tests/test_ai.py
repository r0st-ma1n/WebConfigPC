"""Тесты слоя ИИ без реальных запросов к модели: провайдер подменяется фейковым."""
import pytest

from app.ai import service
from app.ai.base import LLMError
from app.ai.rules_parser import parse_budget, parse_query
from app.balance import Resolution
from app.models import Category
from app.recommender.params import Platform, Scenario
from app.seed import load_catalog

CATALOG = load_catalog(with_ids=True)
BY_NAME = {p.name: p for p in CATALOG}


class FakeProvider:
    """Фейковый LLM: возвращает заранее заданный ответ или бросает ошибку."""
    name = "fake"
    model = "fake-model"

    def __init__(self, json_answer=None, text_answer="", error=False, chunks=(), fail_after=None):
        self.json_answer, self.text_answer, self.error = json_answer, text_answer, error
        self.chunks, self.fail_after = chunks, fail_after  # fail_after: обрыв потока после N кусков
        self.prompts = []

    def generate_json(self, system, prompt, schema):
        self.prompts.append(prompt)
        if self.error:
            raise LLMError("недоступна")
        return self.json_answer

    def generate_text(self, system, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise LLMError("недоступна")
        return self.text_answer

    def stream_text(self, system, prompt):
        self.prompts.append(prompt)
        for i, chunk in enumerate(self.chunks):
            if i == self.fail_after:
                raise LLMError("оборвалась")
            yield chunk


@pytest.fixture
def use_provider(monkeypatch):
    def install(provider):
        monkeypatch.setattr(service, "get_provider", lambda: provider)
        return provider
    return install


# ---------- Разбор правилами (без LLM) ----------

@pytest.mark.parametrize(("text", "budget"), [
    ("до 120 тысяч", 120_000),
    ("бюджет 120к", 120_000),
    ("за 95 000 руб", 95_000),
    ("около 1,5 млн", 1_500_000),
    ("на 80000", 80_000),
    ("видеокарта RTX 5070 и 32 ГБ", None),  # 5070 и 32 — не бюджет
])
def test_parse_budget(text, budget):
    assert parse_budget(text) == budget


def test_parse_gaming_query_with_gpu():
    q = parse_query("Хочу играть в 1440p до 120 тысяч, видеокарта RTX 5070 Ti")
    assert q.budget == 120_000
    assert q.scenario == Scenario.GAMING  # слово «видеокарта» не путает с монтажом
    assert q.resolution == Resolution.QHD
    assert q.gpu_query.lower() == "rtx 5070 ti"


def test_parse_workstation_intel():
    q = parse_query("комп для монтажа видео и blender за 150к, хочу интел")
    assert q.scenario == Scenario.WORKSTATION
    assert q.platform == Platform.INTEL


def test_parse_office():
    q = parse_query("Компьютер для учёбы и офиса, 45 000 руб")
    assert (q.scenario, q.budget) == (Scenario.OFFICE, 45_000)


def test_find_part_by_name():
    assert service.find_part(CATALOG, Category.GPU, "rtx 5070").chip == "RTX 5070"
    assert service.find_part(CATALOG, Category.GPU, "RTX 5070 Ti").chip == "RTX 5070 Ti"
    assert service.find_part(CATALOG, Category.CPU, "Ryzen 7 7800X3D").name == "Ryzen 7 7800X3D"
    assert service.find_part(CATALOG, Category.GPU, "RTX 9999") is None


# ---------- Разбор через LLM ----------

def test_without_provider_rules_are_used(use_provider):
    use_provider(None)
    params, source, notes = service.parse_request("игры в 4k до 250 тысяч", CATALOG)
    assert source == "rules"
    assert (params.budget, params.scenario, params.resolution) == (250_000, Scenario.GAMING, Resolution.UHD)
    assert "Понял так" in notes


def test_llm_answer_is_used(use_provider):
    provider = use_provider(FakeProvider(json_answer={
        "budget": 130_000, "scenario": "gaming", "resolution": "1440p", "platform": None,
        "gpu_query": "RTX 5070", "cpu_query": None, "notes": "ok",
    }))
    params, source, _ = service.parse_request("что-то сложное про игры", CATALOG)
    assert source == "llm"
    assert params.budget == 130_000
    assert params.gpu_id == BY_NAME["GeForce RTX 5070 Infinity 3"].id
    assert provider.prompts == ["что-то сложное про игры"]


def test_invalid_llm_answer_falls_back_to_rules(use_provider):
    use_provider(FakeProvider(json_answer={"budget": "много", "scenario": "майнинг"}))
    params, source, _ = service.parse_request("офисный пк за 40000", CATALOG)
    assert source == "rules"
    assert params.scenario == Scenario.OFFICE


def test_llm_error_falls_back_to_rules(use_provider):
    use_provider(FakeProvider(error=True))
    params, source, _ = service.parse_request("игровой пк 90к", CATALOG)
    assert source == "rules" and params.budget == 90_000


def test_unknown_gpu_is_reported(use_provider):
    use_provider(None)
    params, _, notes = service.parse_request("игры, RTX 9090, бюджет 200к", CATALOG)
    assert params.gpu_id is None
    assert "нет в каталоге" in notes


# ---------- Объяснение ----------

FACTS = {
    "variant": "Оптимальная", "tier": "optimal", "scenario": "office", "scenario_title": "офис и учёба",
    "resolution": None, "budget_rub": 45000, "price_rub": 44200, "unused_rub": 800, "over_budget_rub": 0,
    "score": 70, "parts": {}, "price_share_pct": {},
    "cpu": {"title": "AMD Ryzen 5 7600", "cores": 6, "threads": 12, "has_igpu": True, "socket": "AM5",
            "current_platform": True},
    "gpu": None, "gaming_limiter": None,
    "ram": {"capacity_gb": 16, "type": "DDR5", "modules": 2, "speed_mhz": 6000},
    "storage": {"title": "Kingston NV3 1TB", "kind": "NVMe", "capacity_gb": 1000},
    "power_w": 146, "psu": {"title": "DeepCool PF450", "wattage": 450, "efficiency": "80+", "headroom_pct": 208},
    "warnings": [], "upgrades": [], "savings": [],
}


def test_explain_with_llm_gets_facts(use_provider):
    provider = use_provider(FakeProvider(text_answer="  Простое объяснение.  "))
    text, source = service.explain(FACTS)
    assert (text, source) == ("Простое объяснение.", "llm")
    assert "AMD Ryzen 5 7600" in provider.prompts[0]  # модель получила факты


def test_explain_falls_back_to_template(use_provider):
    use_provider(FakeProvider(error=True))
    text, source = service.explain(FACTS)
    assert source == "template"
    assert "встроенной графики" in text


def test_explain_stream_with_llm(use_provider):
    use_provider(FakeProvider(chunks=["Простое ", "объяснение."]))
    assert list(service.explain_stream(FACTS)) == [
        {"delta": "Простое "}, {"delta": "объяснение."}, {"done": True, "source": "llm"},
    ]


def test_explain_stream_broken_midway_falls_back_to_template(use_provider):
    use_provider(FakeProvider(chunks=["Начало ", "конец"], fail_after=1))
    *deltas, last = service.explain_stream(FACTS)
    assert deltas == [{"delta": "Начало "}]
    # Шаблон заменяет оборванный текст целиком
    assert last == {"done": True, "source": "template", "text": service.template_explanation(FACTS)}


def test_explain_stream_without_provider(use_provider):
    use_provider(None)
    events = list(service.explain_stream(FACTS))
    assert len(events) == 1 and events[0]["source"] == "template"


def test_factory_disabled_without_key(monkeypatch):
    from app.ai import factory
    factory.get_provider.cache_clear()
    monkeypatch.setattr(factory.settings, "llm_provider", "anthropic")
    monkeypatch.setattr(factory.settings, "llm_api_key", "")
    assert factory.get_provider() is None
    factory.get_provider.cache_clear()


# ---------- OpenAI-совместимый провайдер ----------

class FakeStream(list):
    """Поток чанков: итерируется и закрывается через with, как openai.Stream."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeCompletions:
    """Имитация chat.completions: принимает только форматы из accepted, иначе отвечает 400."""

    def __init__(self, accepted, answer):
        self.accepted, self.answer = accepted, answer
        self.formats = []

    def create(self, model, messages, response_format=None, stream=False):
        import httpx
        import openai
        if stream:  # ответ кусками по словам, как приходят чанки от API
            deltas = [type("D", (), {"content": w})() for w in self.answer.split(" ") if w] + [
                type("D", (), {"content": None})()]  # последний чанк без текста
            return FakeStream([type("Ch", (), {"choices": [type("C", (), {"delta": d})()]})() for d in deltas])
        kind = response_format["type"] if isinstance(response_format, dict) else "none"
        self.formats.append(kind)
        if kind not in self.accepted:
            response = httpx.Response(400, request=httpx.Request("POST", "http://test"))
            raise openai.BadRequestError("unsupported response_format", response=response, body=None)
        message = type("M", (), {"content": self.answer})
        return type("R", (), {"choices": [type("C", (), {"message": message})]})


def make_openai_provider(accepted, answer):
    from app.ai.openai_provider import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider("key", "model", "http://test/v1")
    completions = FakeCompletions(accepted, answer)
    provider.client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})})
    return provider, completions


def test_openai_falls_back_to_json_schema():
    # Как LM Studio: json_object даёт 400, json_schema работает; выбранный формат запоминается
    provider, completions = make_openai_provider({"json_schema"}, '{"a": 1}')
    assert provider.generate_json("sys", "q", {"type": "object"}) == {"a": 1}
    assert provider.generate_json("sys", "q", {"type": "object"}) == {"a": 1}
    assert completions.formats == ["json_object", "json_schema", "json_schema"]


def test_openai_without_response_format_strips_wrappers():
    provider, completions = make_openai_provider({"none"}, '<think>хм</think>\n```json\n{"a": 1}\n```')
    assert provider.generate_json("sys", "q", {"type": "object"}) == {"a": 1}
    assert completions.formats == ["json_object", "json_schema", "none"]


def test_openai_bad_json_is_llm_error():
    provider, _ = make_openai_provider({"json_object"}, "не json")
    with pytest.raises(LLMError):
        provider.generate_json("sys", "q", {"type": "object"})


def test_openai_stream_text():
    provider, _ = make_openai_provider(set(), "раз два три")
    assert list(provider.stream_text("sys", "q")) == ["раз", "два", "три"]


def test_openai_empty_stream_is_llm_error():
    provider, _ = make_openai_provider(set(), "")
    with pytest.raises(LLMError):
        list(provider.stream_text("sys", "q"))
