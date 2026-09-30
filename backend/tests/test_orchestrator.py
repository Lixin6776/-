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