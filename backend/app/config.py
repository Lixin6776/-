from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QCA_")
    database_url: str = "sqlite:///./qianchuan.db"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000


settings = Settings()