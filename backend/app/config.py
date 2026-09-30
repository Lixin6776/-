from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QCA_")
    database_url: str = "sqlite:///./qianchuan.db"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    monitor_fixture_path: str = "tests/fixtures/plan_live_snapshot.json"
    cdp_endpoint: str = "http://127.0.0.1:9222"
    selector_config_path: str = ".local/selectors/qianchuan.json"


settings = Settings()