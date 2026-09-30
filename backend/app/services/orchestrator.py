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
        profile: StrategyProfile,
        learning_context: dict | None = None,
        read_only_context: dict | None = None,
    ) -> ChatResult:
        context = (
            f"当前策略画像 v{profile.version}: {profile.business_direction}; "
            f"{profile.primary_objective}; 约束={profile.hard_constraints}; "
            f"learning_context={json.dumps(learning_context, ensure_ascii=False, default=str)}; "
            f"read_only_context={json.dumps(read_only_context, ensure_ascii=False, default=str)}"
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
            return ChatResult(kind="error", message="模型返回格式无效，请重试。")
        if result.kind not in self.ALLOWED_KINDS:
            return ChatResult(kind="error", message="模型返回了不支持的操作类型。")
        return result