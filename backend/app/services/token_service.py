from app.config import Settings, settings


class TokenService:
    def __init__(
        self,
        expires_at: int | None = None,
        config: Settings | None = None,
    ) -> None:
        self.config = config or settings
        self.expires_at = (
            self.config.api_token_expires_at if expires_at is None else expires_at
        )

    def is_configured(self) -> bool:
        return self.config.api_configured

    def should_refresh(self, now: int) -> bool:
        return self.expires_at - now < 300