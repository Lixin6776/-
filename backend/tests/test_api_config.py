# -*- coding: utf-8 -*-
"""开放平台 API 凭据的本地保存/加载 + 连接测试的护栏。"""

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.api_config import load_api_config, save_api_config


def test_api_config_saves_and_reloads(tmp_path):
    settings = Settings()
    save_api_config(
        settings,
        base_url="https://api.example.com",
        app_id="app1",
        app_secret="sec",
        access_token="tok",
        refresh_token="ref",
        advertiser_id=123,
        path=tmp_path / "api.json",
    )
    assert settings.api_app_id == "app1"
    assert settings.api_configured is True

    fresh = Settings()
    load_api_config(fresh, path=tmp_path / "api.json")
    assert fresh.api_app_id == "app1"
    assert fresh.api_app_secret.get_secret_value() == "sec"
    assert fresh.api_access_token.get_secret_value() == "tok"
    assert fresh.api_advertiser_id == 123
    assert fresh.api_configured is True


def test_api_config_blank_secret_keeps_existing(tmp_path):
    """密钥留空 = 不改动已存的值（避免不小心清空 token）。"""
    settings = Settings()
    settings.api_access_token = SecretStr("keep-me")
    save_api_config(
        settings,
        base_url="https://api.oceanengine.com",
        app_id="a",
        access_token="",
        path=tmp_path / "api.json",
    )
    assert settings.api_access_token.get_secret_value() == "keep-me"


def test_api_config_missing_file_is_noop(tmp_path):
    settings = Settings()
    before = settings.api_app_id
    load_api_config(settings, path=tmp_path / "nope.json")
    assert settings.api_app_id == before


def test_api_test_endpoint_blocks_when_not_configured(monkeypatch):
    from fastapi import HTTPException

    from app.api import api_connection

    monkeypatch.setattr(api_connection, "settings", Settings())
    with pytest.raises(HTTPException) as exc:
        api_connection.test_api_connection()
    assert exc.value.status_code == 400
