# -*- coding: utf-8 -*-
"""直播运营助手对话接口。

和 /api/chat（本场盯盘对话）分开：这里是跨场次保留、按天归档的运营对话。
"""

import base64
import re
import uuid
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.services.llm.deepseek import DeepSeekProvider
from app.services.ops_chat import (
    PERSONA,
    build_daily_briefing,
    collect_briefing_inputs,
    collect_ops_context,
)
from app.services.orchestrator import Orchestrator
from app.services.profiles import StrategyProfileService

router = APIRouter(prefix="/api/ops-chat", tags=["ops-chat"])
logger = structlog.get_logger()

# 聊天里发的图片存这里（本机，不进仓库）
CHAT_UPLOAD_DIR = Path(__file__).resolve().parents[3] / ".local" / "chat_uploads"
MAX_CHAT_IMAGES = 4
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_DATA_URL_RE = re.compile(
    r"^data:image/(png|jpe?g|webp|gif);base64,(.+)$", re.IGNORECASE | re.DOTALL
)


def _save_chat_image(data_url: str) -> str | None:
    """把 data URL 落成本机文件，返回可访问的地址；格式/大小不对就丢掉。"""
    match = _DATA_URL_RE.match(data_url or "")
    if not match:
        return None
    ext = "jpg" if match.group(1).lower() in {"jpeg", "jpg"} else match.group(1).lower()
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (ValueError, TypeError):
        return None
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        return None
    try:
        CHAT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{ext}"
        (CHAT_UPLOAD_DIR / name).write_bytes(raw)
    except OSError:
        return None
    return f"/api/ops-chat/uploads/{name}"


class OpsMessageRequest(BaseModel):
    message: str = ""
    # 图片以 data URL 传入（data:image/png;base64,...），避免引入 multipart 依赖
    images: list[str] = Field(default_factory=list)


def _llm_provider() -> DeepSeekProvider:
    return DeepSeekProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )


def _active_profile(db: Session):
    try:
        return StrategyProfileService(db).get_active()
    except LookupError:
        return None


@router.get("/messages")
def list_messages(request: Request, limit: int = 100) -> list[dict]:
    return request.app.state.ops_chat_store.list_messages(limit=limit)


@router.post("/messages")
async def send_message(
    payload: OpsMessageRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """用户对运营助手说一句话，拿回回答（两边都入库）。"""
    store = request.app.state.ops_chat_store
    hub = getattr(request.app.state, "notification_hub", None)
    profile = _active_profile(db)

    saved_images: list[str] = []
    llm_images: list[str] = []
    for data_url in payload.images[:MAX_CHAT_IMAGES]:
        url = _save_chat_image(data_url)
        if url is not None:
            saved_images.append(url)
            llm_images.append(data_url)

    store.append(
        "user",
        payload.message or "（图片）",
        kind="chat",
        meta={"images": saved_images} if saved_images else None,
    )

    context = collect_ops_context(request.app.state, profile=profile)
    answer = ""
    try:
        result = await Orchestrator(_llm_provider()).handle(
            payload.message,
            profile,
            read_only_context=context,
            persona=PERSONA,
            images=llm_images or None,
        )
        answer = result.message
    except Exception:  # noqa: BLE001
        logger.exception("ops_chat_llm_failed")
        answer = (
            "模型服务暂时不可用（可以先看「大模型」里的连接配置）。"
            "你的问题我已经记下来了，配置好了可以直接再问一次。"
        )

    message = store.append("assistant", answer, kind="chat")
    if hub is not None:
        await hub.publish(
            {
                "type": "ops_chat",
                "id": message["id"],
                "message": answer,
                "created_at": message["created_at"],
            }
        )
    return message


@router.post("/briefing")
async def generate_briefing_now(request: Request, day: str | None = None) -> dict:
    """手动补一次《每日运营汇报》（定时任务没跑到时用）。"""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    store = request.app.state.ops_chat_store
    hub = getattr(request.app.state, "notification_hub", None)
    target_day = (
        date.fromisoformat(day)
        if day
        else datetime.now(ZoneInfo("Asia/Shanghai")).date()
    )
    inputs = collect_briefing_inputs(request.app.state)
    content = build_daily_briefing(
        day=target_day,
        watch_reports=inputs["watch_reports"],
        reviews=inputs["reviews"],
        analyses=inputs["analyses"],
    )
    message = store.replace_daily_briefing(
        content, meta={"day": target_day.isoformat()}
    )
    if hub is not None:
        await hub.publish(
            {
                "type": "ops_chat",
                "id": message["id"],
                "message": content,
                "created_at": message["created_at"],
            }
        )
    return message


@router.get("/uploads/{name}")
def get_upload(name: str) -> FileResponse:
    """读取聊天里发过的图片（只允许访问上传目录内的文件）。"""
    path = CHAT_UPLOAD_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)
