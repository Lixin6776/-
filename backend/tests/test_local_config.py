# -*- coding: utf-8 -*-
"""本机配置：界面改的值要能覆盖 .env，且清空要能回落。"""

import json

import pytest
from fastapi.testclient import TestClient

from app.services import local_config


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(local_config, "LOCAL_CONFIG_PATH", path)
    return path


def test_save_then_load(isolated):
    local_config.save({"room_name": "质润官方旗舰店", "aavid": "123"})
    assert local_config.room_name() == "质润官方旗舰店"
    assert local_config.aavid() == "123"


def test_local_value_overrides_default(isolated):
    local_config.save({"room_name": "直播间A"})
    # 界面设了 → 用界面的；没设的 → 回落默认（这里是 .env 的值）
    assert local_config.room_name("来自env") == "直播间A"
    assert local_config.aavid("来自env") == "来自env"


def test_clearing_falls_back(isolated):
    local_config.save({"room_name": "直播间A"})
    local_config.save({"room_name": ""})   # 清空 = 恢复回落
    assert local_config.room_name("来自env") == "来自env"


def test_unknown_keys_are_ignored(isolated):
    local_config.save({"room_name": "A", "token": "不该被写进去"})
    payload = json.loads(isolated.read_text(encoding="utf-8"))
    assert "token" not in payload


def test_api_reads_and_writes(isolated):
    from app.main import app

    with TestClient(app) as client:
        got = client.get("/api/local-config").json()
        assert "effective" in got
        resp = client.put("/api/local-config", json={"room_name": "质润二硫化硒洗发水官方直播间"})
        assert resp.status_code == 200
        again = client.get("/api/local-config").json()
        assert again["effective"]["room_name"] == "质润二硫化硒洗发水官方直播间"
