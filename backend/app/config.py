from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QCA_")
    database_url: str = "sqlite:///./qianchuan.db"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    monitor_fixture_path: str = "tests/fixtures/plan_live_snapshot.json"
    monitor_source: str = "cdp"
    monitor_interval_seconds: int = 300
    live_board_page_marker: str = "board-next"
    read_only_mode: bool = False
    cdp_endpoint: str = "http://127.0.0.1:9222"
    selector_config_path: str = ".local/selectors/qianchuan.json"
    api_base_url: str = "https://api.oceanengine.com"
    api_app_id: str = ""
    api_app_secret: SecretStr = SecretStr("")
    api_access_token: SecretStr = SecretStr("")
    api_refresh_token: SecretStr = SecretStr("")
    api_token_expires_at: int = 0
    api_advertiser_id: int = 0

    @property
    def api_configured(self) -> bool:
        return bool(
            self.api_app_id
            and self.api_app_secret.get_secret_value()
            and self.api_access_token.get_secret_value()
        )


settings = Settings()