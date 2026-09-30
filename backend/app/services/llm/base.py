from typing import Protocol

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMResponse(BaseModel):
    content: str


class LLMProvider(Protocol):
    async def complete(self, messages: list[LLMMessage], tools: list[dict]) -> LLMResponse:
        ...