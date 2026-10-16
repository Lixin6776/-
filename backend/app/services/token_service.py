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
        # expires_at == 0 = 没记录过期时间。这时不能瞎刷新 ——
        # 否则只有 access_token（没 refresh_token）的用户每次都会走到刷新分支直接报错。
        if not self.expires_at:
            return False
        return self.expires_at - now < 300