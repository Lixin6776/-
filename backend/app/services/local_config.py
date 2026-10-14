# -*- coding: utf-8 -*-
"""本机配置（界面可改）。

以前"盯哪个直播间 / 哪个账户"只能改 backend/.env —— 对给别人用来说太重了
（要碰命令行、要重启）。现在统一放 .local/config.json，由工具界面读写，
读取时**优先用这里的值，没有才回落到 .env / 默认值**。

放 .local/ 是为了跟其它本机数据一起被 gitignore（不进仓库）。
"""

import json
from pathlib import Path

LOCAL_CONFIG_PATH = Path(__file__).resolve().parents[3] / ".local" / "config.json"

# 允许界面改的键（别的键不接受，避免写脏）
EDITABLE_KEYS = ("room_name", "aavid", "api_base_url", "api_advertiser_id")


def load() -> dict:
    if not LOCAL_CONFIG_PATH.exists():
        return {}
    try:
        payload = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save(patch: dict) -> dict:
    current = load()
    for key in EDITABLE_KEYS:
        if key not in patch:
            continue
        value = patch[key]
        text = "" if value is None else str(value).strip()
        if text:
            current[key] = text
        else:
            current.pop(key, None)  # 清空 = 恢复回落
    LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_CONFIG_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return current


def room_name(default: str = "") -> str:
    """盯哪个直播间：界面设了就用界面的，否则用 .env 的。"""
    return str(load().get("room_name") or default or "").strip()


def aavid(default: str = "") -> str:
    """账户 ID：界面设了就用界面的，否则用 .env 的。"""
    return str(load().get("aavid") or default or "").strip()
