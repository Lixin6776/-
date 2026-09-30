import httpx

from app.services.llm.base import LLMMessage, LLMResponse


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def complete(self, messages: list[LLMMessage], tools: list[dict]) -> LLMResponse:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [message.model_dump() for message in messages],
                    "tools": tools,
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            data = response.json()
            return LLMResponse(content=data["choices"][0]["message"]["content"])