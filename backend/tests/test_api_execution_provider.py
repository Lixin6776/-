import pytest

from app.execution.api_provider import ApiExecutionProvider
from app.services.action_registry import ActionEnvelope, ActionName


class MockResponse:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class MockClient:
    def __init__(self):
        self.status = "active"

    def request(self, method, path, params=None, json=None):
        if "status/update" in path:
            self.status = "paused"
            return MockResponse({"code": 0, "data": {}})
        if "ad/get" in path:
            return MockResponse(
                {
                    "code": 0,
                    "data": {
                        "list": [
                            {
                                "ad_id": "plan-1",
                                "ad_name": "计划 A",
                                "status": self.status,
                                "budget": 1000,
                            }
                        ]
                    },
                }
            )
        raise AssertionError(path)


@pytest.mark.asyncio
async def test_api_provider_pause_verifies_readback():
    client = MockClient()
    provider = ApiExecutionProvider(client, advertiser_id=123)
    action = ActionEnvelope(
        action_name=ActionName.PAUSE_PLAN,
        target_id="plan-1",
        params={},
    )
    result = await provider.execute(action)
    verification = await provider.verify(action, result)
    assert verification.ok is True