from collections.abc import Callable

import httpx

from app.config import Settings, settings
from app.services.token_service import TokenService


class ApiError(RuntimeError):
    pass


class ApiAuthenticationError(ApiError):
    pass


class ApiRateLimitError(ApiError):
    pass


class ApiRequestError(ApiError):
    pass


class OceanEngineApiClient:
    def __init__(
        self,
        config: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
        now: Callable[[], int] | None = None,
    ) -> None:
        self.config = config or settings
        self.now = now or (lambda: 0)
        self.access_token = self.config.api_access_token.get_secret_value()
        self.http = httpx.Client(
            base_url=self.config.api_base_url,
            timeout=30,
            transport=transport,
        )

    def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> httpx.Response:
        token_service = TokenService(
            expires_at=self.config.api_token_expires_at,
            config=self.config,
        )
        if token_service.should_refresh(self.now()):
            self.refresh_access_token()
        response = self.http.request(
            method,
            path,
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        self._raise_for_status(response)
        return response

    def refresh_access_token(self) -> None:
        refresh_token = self.config.api_refresh_token.get_secret_value()
        if not refresh_token:
            raise ApiAuthenticationError("API refresh token is not configured")
        response = self.http.post(
            "/open_api/oauth2/refresh_token/",
            json={
                "app_id": self.config.api_app_id,
                "secret": self.config.api_app_secret.get_secret_value(),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        if response.status_code == 401:
            raise ApiAuthenticationError("API token refresh failed")
        body = response.json()
        if response.status_code >= 400 or body.get("code", 0) != 0:
            raise ApiAuthenticationError(f"API token refresh failed: {body.get('message', '')}")
        self.access_token = body["data"]["access_token"]

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise ApiAuthenticationError("API authentication failed")
        if response.status_code == 429:
            raise ApiRateLimitError("API rate limit exceeded")
        if response.status_code >= 400:
            raise ApiRequestError(f"API request failed with {response.status_code}")