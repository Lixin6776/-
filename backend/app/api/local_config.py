# -*- coding: utf-8 -*-
"""本机配置读写（界面用）。改的是 .local/config.json，不进仓库。"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import local_config

router = APIRouter(prefix="/api/local-config", tags=["local-config"])


class LocalConfigPatch(BaseModel):
    room_name: str | None = None
    aavid: str | None = None
    api_base_url: str | None = None
    api_advertiser_id: str | None = None


@router.get("")
def read_local_config() -> dict:
    """当前生效的配置 + 它是从哪来的（界面 / .env 默认）。"""
    from app.config import settings

    saved = local_config.load()
    return {
        "saved": saved,
        "effective": {
            "room_name": local_config.room_name(settings.live_board_room_name),
            "aavid": local_config.aavid(settings.aavid),
        },
    }


@router.put("")
def update_local_config(payload: LocalConfigPatch) -> dict:
    saved = local_config.save(payload.model_dump(exclude_none=True))
    return {"saved": saved, "message": "已保存（下一次读取生效，不用重启）"}
