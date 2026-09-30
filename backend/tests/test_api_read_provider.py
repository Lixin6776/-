from app.execution.api_read_provider import ApiReadProvider


class MockResponse:
    def json(self):
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "ad_id": "plan-1",
                        "ad_name": "计划 A",
                        "status": "active",
                        "budget": 1000,
                    }
                ]
            },
        }


class MockClient:
    def request(self, method, path, params=None, json=None):
        return MockResponse()


def test_read_provider_normalizes_plan_snapshot():
    provider = ApiReadProvider(MockClient(), advertiser_id=123)
    snapshot = provider.get_plan("plan-1")
    assert snapshot.id == "plan-1"
    assert snapshot.status == "active"
    assert snapshot.budget == 1000