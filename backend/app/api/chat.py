from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.dependencies import get_plan_snapshot
from app.models import LearningCase, StrategyEvaluation, StrategySuggestion
from app.services.action_planner import ActionPlanner, PlanSnapshot
from app.services.action_registry import ActionEnvelope, ActionName
from app.services.llm.base import LLMProvider
from app.services.llm.deepseek import DeepSeekProvider
from app.services.orchestrator import ChatResult, Orchestrator
from app.services.profiles import StrategyProfileService
from app.services.strategy_card import format_strategy_card

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = structlog.get_logger()


class ChatRequest(BaseModel):
    message: str
    proposed_action: ActionEnvelope | None = None
    include_learning_context: bool = False


def get_llm_provider():
    return DeepSeekProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )


def _plan_snapshot(request: Request, action: ActionEnvelope) -> PlanSnapshot:
    if action.action_name == ActionName.CREATE_PLAN:
        return PlanSnapshot(
            id=action.target_id,
            name=str(action.params.get("name", "新计划")),
            status="new",
            budget=0,
        )
    return get_plan_snapshot(request, action.target_id)


def _read_only_context(request: Request) -> dict:
    monitor_service = getattr(request.app.state, "monitor_service", None)
    monitor_event = (
        monitor_service.latest_event()
        if monitor_service is not None and hasattr(monitor_service, "latest_event")
        else None
    )
    plan_snapshot = getattr(request.app.state, "latest_plan_snapshot", None)
    return {
        "plan": (
            plan_snapshot.model_dump(mode="json")
            if plan_snapshot is not None
            else None
        ),
        "monitor": (
            monitor_event.model_dump(mode="json")
            if monitor_event is not None
            else None
        ),
        "strategy_card": format_strategy_card(plan_snapshot, monitor_event),
    }


def _wants_strategy_card(message: str) -> bool:
    keywords = ("策略卡", "策略", "投放", "计划", "ROI", "消耗", "直播", "分析", "怎么样", "情况")
    return any(keyword in message for keyword in keywords)


def _learning_context(db: Session) -> dict:
    cases = list(db.scalars(select(LearningCase).limit(5)))
    evaluations = list(db.scalars(select(StrategyEvaluation).limit(5)))
    suggestions = list(db.scalars(select(StrategySuggestion).limit(5)))
    return {
        "cases": [case.context for case in cases],
        "evaluations": [
            {
                "sample_size": item.sample_size,
                "confidence": item.confidence,
                "verdict": item.verdict,
                "evidence": item.evidence,
            }
            for item in evaluations
        ],
        "suggestions": [
            {
                "type": item.suggestion_type,
                "change": item.proposed_change,
                "confidence": item.confidence,
                "status": item.status,
            }
            for item in suggestions
        ],
    }


@router.post("", response_model=ChatResult, response_model_exclude_none=True)
async def chat(
    payload: ChatRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> ChatResult:
    try:
        profile = StrategyProfileService(db).get_active()
    except LookupError:
        profile = None
    if payload.proposed_action is not None:
        if profile is None:
            return ChatResult(
                kind="error",
                message="请先创建并激活投放策略，再生成操作预览。",
            )
        snapshot = _plan_snapshot(request, payload.proposed_action)
        preview = ActionPlanner().preflight(payload.proposed_action, profile, snapshot)
        kind = "recommendation" if preview.allowed else "error"
        message = (
            "已生成操作预览，必须由用户确认后才能执行。"
            if preview.allowed
            else "操作预览被策略或参数校验阻断。"
        )
        return ChatResult(kind=kind, message=message, preview=preview.model_dump(mode="json"))
    read_only_context = _read_only_context(request)
    if _wants_strategy_card(payload.message):
        return ChatResult(
            kind="analysis",
            message=str(read_only_context["strategy_card"]),
        )
    learning_context = _learning_context(db) if payload.include_learning_context else None
    try:
        return await Orchestrator(llm).handle(
            payload.message,
            profile,
            learning_context,
            read_only_context=read_only_context,
        )
    except Exception:
        logger.exception("llm_provider_failed")
        return ChatResult(kind="error", message="模型服务不可用，请检查本地配置。")