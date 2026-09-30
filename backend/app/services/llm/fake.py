from app.services.llm.base import LLMMessage, LLMResponse


class FakeLLMProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    async def complete(self, messages: list[LLMMessage], tools: list[dict]) -> LLMResponse:
        return LLMResponse(content=self.content)