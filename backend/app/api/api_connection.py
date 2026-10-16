# -*- coding: utf-8 -*-
"""巨量开放平台 API 连接：状态 / 保存凭据 / 测试连接。"""

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.execution.api_read_provider import ApiReadProvider
from app.services.api_client import OceanEngineApiClient
from app.services.api_config import save_api_config

router = APIRouter(prefix="/api/api-connection", tags=["api-connection"])
logger = structlog.get_logger()


class ApiConfigRequest(BaseModel):
    base_url: str = "https://api.oceanengine.com"
    app_id: str = ""
    app_secret: str = ""
    access_token: str = ""
    refresh_token: str = ""
    advertiser_id: int = 0


def _status() -> dict:
    return {
        "configured": settings.api_configured,
        "provider_preference": (
            "api" if settings.api_configured and settings.api_advertiser_id else "cdp"
        ),
        "base_url": settings.api_base_url,
        "app_id": settings.api_app_id,
        "advertiser_id": settings.api_advertiser_id,
        "token_expires_at": settings.api_token_expires_at,
        "has_secret": bool(settings.api_app_secret.get_secret_value()),
        "has_access_token": bool(settings.api_access_token.get_secret_value()),
        "has_refresh_token": bool(settings.api_refresh_token.get_secret_value()),
    }


@router.get("/status")
def api_connection_status() -> dict:
    return _status()


@router.post("/config")
def save_api_connection(payload: ApiConfigRequest) -> dict:
    save_api_config(
        settings,
        base_url=payload.base_url.strip(),
        app_id=payload.app_id.strip(),
        app_secret=payload.app_secret.strip(),
        access_token=payload.access_token.strip(),
        refresh_token=payload.refresh_token.strip(),
        advertiser_id=payload.advertiser_id,
    )
    return _status()


@router.post("/test")
def test_api_connection() -> dict:
    """拿广告主信息验一次 —— 通了说明 App 凭据 + 授权 + 账户都对。"""
    if not settings.api_app_id or not settings.api_app_secret.get_secret_value():
        raise HTTPException(status_code=400, detail="请先填 App ID 和 App Secret")
    if not settings.api_advertiser_id:
        raise HTTPException(status_code=400, detail="请先填广告主 ID（advertiser_id）")
    if not (
        settings.api_access_token.get_secret_value()
        or settings.api_refresh_token.get_secret_value()
    ):
        raise HTTPException(status_code=400, detail="请先填 Access Token 或 Refresh Token")

    client = OceanEngineApiClient(config=settings)
    try:
        account = ApiReadProvider(client, settings.api_advertiser_id).get_account()
    except Exception as exc:  # noqa: BLE001
        logger.warning("api_connection_test_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"API 连接失败：{type(exc).__name__}: {exc}",
        ) from exc
    name = ""
    if isinstance(account, dict):
        name = str(account.get("name") or account.get("advertiser_name") or "")
    return {"ok": True, "message": f"API 连接成功{'：' + name if name else ''}"}
