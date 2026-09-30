import json
from typing import ClassVar

from pydantic import BaseModel, ValidationError

from app.models import StrategyProfile
from app.services.llm.base import LLMMessage, LLMProvider


class ChatResult(BaseModel):
    kind: str
    message: str
    preview: dict | None = None


class Orchestrator:
    ALLOWED_KINDS: ClassVar[set[str]] = {"analysis", "recommendation", "question", "error"}

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def handle(
        self,
        message: str,
        profile: StrategyProfile | None,
        learning_context: dict | None = None,
        read_only_context: dict | None = None,
    ) -> ChatResult:
        if profile is None:
            strategy_context = "当前投放策略：未配置；目标=未配置；约束={}"
        else:
            strategy_context = (
                f"当前投放策略 v{profile.version}: {profile.business_direction}; "
                f"{profile.primary_objective}; 约束={profile.hard_constraints}"
            )
        context = (
            f"{strategy_context}; "
            f"learning_context={json.dumps(learning_context, ensure_ascii=False, default=str)}; "
            f"read_only_context={json.dumps(read_only_context, ensure_ascii=False, default=str)}; "
            '请优先输出 JSON：{"kind":"analysis|recommendation|question|error",'
            '"message":"给用户看的中文回答","preview":null}。'
            "如果不方便输出 JSON，也可以直接输出自然语言分析。"
        )
        response = await self.llm.complete(
            [
                LLMMessage(role="system", content=context),
                LLMMessage(role="user", content=message),
            ],
            tools=[],
        )
        try:
            payload = json.loads(response.content)
            result = ChatResult.model_validate(payload)
        except (json.JSONDecodeError, ValidationError):
            text = response.content.strip()
            if text:
                return ChatResult(kind="analysis", message=text)
            return ChatResult(kind="error", message="模型返回格式无效，请重试。")
        if result.kind not in self.ALLOWED_KINDS:
            return ChatResult(kind="error", message="模型返回了不支持的操作类型。")
        return result