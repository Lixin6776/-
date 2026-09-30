import httpx
import pytest

from app.config import Settings
from app.execution.api_provider import ApiExecutionProvider
from app.services.action_registry import ActionEnvelope, ActionName
from app.services.api_client import OceanEngineApiClient
from app.services.provider_router import ProviderRouter


class ApiState:
    def __init__(self):
        self.status = "active"


def test_api_migration_acceptance_uses_mock_transport():
    state = ApiState()

    def handler(request: httpx.Request) -> httpx.Response:
        if "status/update" in request.url.path:
            state.status = "paused"
            return httpx.Response(200, json={"code": 0, "data": {}})
        if "ad/get" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "list": [
                            {
                                "ad_id": "plan-1",
                                "ad_name": "计划 A",
                                "status": state.status,
                                "budget": 1000,
                            }
                        ]
                    },
                },
            )
        return httpx.Response(404, json={"code": 404})

    config = Settings(
        api_app_id="123",
        api_app_secret="secret",
        api_access_token="token-1",
        api_token_expires_at=10_000,
    )
    client = OceanEngineApiClient(
        config=config,
        transport=httpx.MockTransport(handler),
        now=lambda: 1,
    )
    provider = ApiExecutionProvider(client, advertiser_id=123)
    action = ActionEnvelope(
        action_name=ActionName.PAUSE_PLAN,
        target_id="plan-1",
        params={},
    )
    result = provider_adapter_execute(provider, action)
    assert provider_adapter_verify(provider, action, result).ok is True


def provider_adapter_execute(provider, action):
    import asyncio

    return asyncio.run(provider.execute(action))


def provider_adapter_verify(provider, action, result):
    import asyncio

    return asyncio.run(provider.verify(action, result))


def test_mutation_started_disables_cdp_fallback():
    router = ProviderRouter(
        api_provider=object(),
        cdp_provider=object(),
        api_configured=True,
        api_actions={ActionName.PAUSE_PLAN},
    )
    assert router.can_fallback(mutation_started=False) is True
    assert router.can_fallback(mutation_started=True) is False

@pytest.mark.asyncio
async def test_api_mutation_failure_is_unknown_not_retried():
    from app.execution.api_provider import ApiExecutionProvider
    from app.execution.base import UnknownExecutionState
    from app.services.action_registry import ActionEnvelope, ActionName
    from app.services.api_client import ApiAuthenticationError

    class FailingClient:
        def request(self, method, path, params=None, json=None):
            raise ApiAuthenticationError("refresh failed")

    provider = ApiExecutionProvider(FailingClient(), advertiser_id=123)
    action = ActionEnvelope(
        action_name=ActionName.PAUSE_PLAN,
        target_id="plan-1",
        params={},
    )
    with pytest.raises(UnknownExecutionState):
        await provider.execute(action)
