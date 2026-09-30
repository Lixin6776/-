import pytest

from app.api.chat import get_llm_provider
from app.main import app
from app.services.llm.fake import FakeLLMProvider
from app.services.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_orchestrator_rejects_malformed_model_data(profile):
    llm = FakeLLMProvider(content="not-json")
    result = await Orchestrator(llm).handle("看看今天的ROI", profile)
    assert result.kind == "error"
    assert result.message == "模型返回格式无效，请重试。"


@pytest.mark.asyncio
async def test_orchestrator_returns_readonly_analysis(profile):
    llm = FakeLLMProvider(
        content='{"kind":"analysis","message":"当前策略要求在 ROI >= 2.5 下放量。"}'
    )
    result = await Orchestrator(llm).handle("当前策略是什么", profile)
    assert result.kind == "analysis"
    assert "ROI >= 2.5" in result.message

def test_chat_api_returns_schema_validated_result(client, profile):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        content='{"kind":"analysis","message":"API 已读取策略画像。"}'
    )
    response = client.post("/api/chat", json={"message": "当前策略是什么"})
    assert response.status_code == 200
    assert response.json() == {"kind": "analysis", "message": "API 已读取策略画像。"}

class FailingLLMProvider:
    async def complete(self, messages, tools):
        raise RuntimeError("provider down")


def test_chat_api_returns_safe_error_when_provider_fails(client, profile):
    app.dependency_overrides[get_llm_provider] = lambda: FailingLLMProvider()
    response = client.post("/api/chat", json={"message": "看看今天的ROI"})
    assert response.status_code == 200
    assert response.json() == {"kind": "error", "message": "模型服务不可用，请检查本地配置。"}


@pytest.mark.asyncio
async def test_orchestrator_includes_read_only_context(profile):
    from app.services.llm.base import LLMMessage, LLMResponse

    captured: list[LLMMessage] = []

    class CapturingProvider:
        async def complete(self, messages, tools):
            captured.extend(messages)
            return LLMResponse(content='{"kind":"analysis","message":"已读取计划快照。"}')

    await Orchestrator(CapturingProvider()).handle(
        "当前计划怎么样",
        profile,
        read_only_context={"plan": {"id": "plan-1", "roi": 1.87}},
    )

    assert any("read_only_context" in message.content for message in captured)
    assert any("plan-1" in message.content for message in captured)


def test_chat_api_includes_cached_read_only_context(client, profile):
    from app.api.chat import get_llm_provider
    from app.main import app
    from app.services.action_planner import PlanSnapshot
    from app.services.llm.base import LLMMessage, LLMResponse

    captured: list[LLMMessage] = []

    class CapturingProvider:
        async def complete(self, messages, tools):
            captured.extend(messages)
            return LLMResponse(content='{"kind":"analysis","message":"已读取计划。"}')

    app.dependency_overrides[get_llm_provider] = lambda: CapturingProvider()
    app.state.latest_plan_snapshot = PlanSnapshot(
        id="plan-1",
        name="计划 plan-1",
        status="active",
        budget=1000,
        roi_goal=2.6,
    )

    response = client.post("/api/chat", json={"message": "当前计划怎么样"})

    assert response.status_code == 200
    assert any("read_only_context" in message.content for message in captured)
    assert any("plan-1" in message.content for message in captured)


def test_chat_api_without_profile_still_answers(client):
    from app.api.chat import get_llm_provider
    from app.main import app
    from app.services.llm.fake import FakeLLMProvider

    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        content='{"kind":"analysis","message":"可以先进行只读分析。"}'
    )
    response = client.post("/api/chat", json={"message": "看看 ROI"})

    assert response.status_code == 200
    assert response.json()["kind"] == "analysis"
    assert "只读分析" in response.json()["message"]
