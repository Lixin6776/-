# -*- coding: utf-8 -*-
"""直播运营助手对话接口。

和 /api/chat（本场盯盘对话）分开：这里是跨场次保留、按天归档的运营对话。
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
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


class OpsMessageRequest(BaseModel):
    message: str


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

    store.append("user", payload.message, kind="chat")

    context = collect_ops_context(request.app.state, profile=profile)
    answer = ""
    try:
        result = await Orchestrator(_llm_provider()).handle(
            payload.message,
            profile,
            read_only_context=context,
            persona=PERSONA,
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
