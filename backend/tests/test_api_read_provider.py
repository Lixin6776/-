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

def test_read_provider_preserves_extended_plan_fields():
    class ExtendedClient:
        def request(self, method, path, params=None, json=None):
            return MockResponseWithExtendedFields()

    provider = ApiReadProvider(ExtendedClient(), advertiser_id=123)
    snapshot = provider.get_plan("plan-1")
    assert snapshot.bid == 2.5
    assert snapshot.targeting == {"gender": "female"}
    assert snapshot.schedule == {"days": ["mon"]}
    assert snapshot.materials == ["material-1"]


class MockResponseWithExtendedFields:
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
                        "bid": 2.5,
                        "targeting": {"gender": "female"},
                        "schedule": {"days": ["mon"]},
                        "materials": ["material-1"],
                    }
                ]
            },
        }
