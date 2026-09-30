import httpx
import pytest

from app.config import Settings
from app.services.api_client import ApiAuthenticationError, OceanEngineApiClient


def test_client_sends_bearer_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token-1"
        return httpx.Response(200, json={"code": 0, "data": {"ok": True}})

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
    response = client.request("GET", "/open_api/v1.0/ad/get/", params={"advertiser_id": 1})
    assert response.status_code == 200
    assert response.json()["data"]["ok"] is True


def test_refresh_failure_raises_authentication_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 401, "message": "expired"})

    config = Settings(
        api_app_id="123",
        api_app_secret="secret",
        api_access_token="expired",
        api_refresh_token="refresh",
        api_token_expires_at=0,
    )
    client = OceanEngineApiClient(
        config=config,
        transport=httpx.MockTransport(handler),
        now=lambda: 1,
    )
    with pytest.raises(ApiAuthenticationError):
        client.request("GET", "/open_api/v1.0/ad/get/")