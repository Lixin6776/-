from typing import Protocol

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str
    # 纯文本时是 str；带图片时是 OpenAI 风格的多模态 parts：
    # [{"type": "text", "text": ...}, {"type": "image_url", "image_url": {"url": "data:..."}}]
    content: str | list[dict]


class LLMResponse(BaseModel):
    content: str


class LLMProvider(Protocol):
    async def complete(self, messages: list[LLMMessage], tools: list[dict]) -> LLMResponse:
        ...