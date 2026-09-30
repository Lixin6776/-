from app.config import Settings
from app.services.token_service import TokenService


def test_api_is_disabled_without_credentials():
    settings = Settings(api_app_id="", api_app_secret="", api_access_token="")
    assert settings.api_configured is False


def test_api_configured_hides_secret_from_repr():
    settings = Settings(
        api_app_id="123",
        api_app_secret="super-secret",
        api_access_token="token-1",
    )
    assert settings.api_configured is True
    assert "super-secret" not in repr(settings)
    assert "token-1" not in repr(settings)


def test_token_refresh_window_is_five_minutes():
    service = TokenService(expires_at=1000)
    assert service.should_refresh(now=701) is True
    assert service.should_refresh(now=700) is False