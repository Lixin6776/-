# -*- coding: utf-8 -*-
r"""巨量开放平台 API 凭据的本地持久化。

和 llm_config 一样：存 \.local/api_config.json（.local 已被 gitignore），
启动时覆盖 settings，这样用户在界面上填一次就行，不用改 .env。
"""

import json
from pathlib import Path

from pydantic import SecretStr

from app.config import Settings

CONFIG_PATH = Path(__file__).resolve().parents[3] / ".local" / "api_config.json"

# 界面字段 -> settings 属性
_SECRET_FIELDS = {
    "app_secret": "api_app_secret",
    "access_token": "api_access_token",
    "refresh_token": "api_refresh_token",
}
_INT_FIELDS = {
    "advertiser_id": "api_advertiser_id",
    "token_expires_at": "api_token_expires_at",
}
_STR_FIELDS = {"base_url": "api_base_url", "app_id": "api_app_id"}


def load_api_config(settings: Settings, path: Path = CONFIG_PATH) -> None:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    for key, attr in _STR_FIELDS.items():
        value = payload.get(key)
        if isinstance(value, str) and value:
            setattr(settings, attr, value)
    for key, attr in _SECRET_FIELDS.items():
        value = payload.get(key)
        if isinstance(value, str) and value:
            setattr(settings, attr, SecretStr(value))
    for key, attr in _INT_FIELDS.items():
        value = payload.get(key)
        try:
            setattr(settings, attr, int(value))
        except (TypeError, ValueError):
            continue


def save_api_config(
    settings: Settings,
    *,
    base_url: str,
    app_id: str,
    app_secret: str = "",
    access_token: str = "",
    refresh_token: str = "",
    advertiser_id: int = 0,
    path: Path = CONFIG_PATH,
) -> None:
    """空字符串表示"保留原值"（和 LLM 配置一致，避免不小心清空已有 token）。"""
    settings.api_base_url = base_url or settings.api_base_url
    settings.api_app_id = app_id or settings.api_app_id
    if app_secret:
        settings.api_app_secret = SecretStr(app_secret)
    if access_token:
        settings.api_access_token = SecretStr(access_token)
    if refresh_token:
        settings.api_refresh_token = SecretStr(refresh_token)
    if advertiser_id:
        settings.api_advertiser_id = advertiser_id

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "base_url": settings.api_base_url,
                "app_id": settings.api_app_id,
                "app_secret": settings.api_app_secret.get_secret_value(),
                "access_token": settings.api_access_token.get_secret_value(),
                "refresh_token": settings.api_refresh_token.get_secret_value(),
                "advertiser_id": settings.api_advertiser_id,
                "token_expires_at": settings.api_token_expires_at,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
