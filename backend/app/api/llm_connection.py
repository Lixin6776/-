from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.llm.base import LLMMessage
from app.services.llm.deepseek import DeepSeekProvider
from app.services.llm_config import save_llm_config

router = APIRouter(prefix="/api/llm-connection", tags=["llm-connection"])


class LlmConfigRequest(BaseModel):
    base_url: str = Field(default="https://api.deepseek.com", min_length=1)
    model: str = Field(default="deepseek-chat", min_length=1)
    api_key: str = ""


def _status() -> dict:
    return {
        "provider": "deepseek",
        "configured": bool(settings.llm_api_key and settings.llm_base_url and settings.llm_model),
        "base_url": settings.llm_base_url,
        "model": settings.llm_model,
        "api_key_configured": bool(settings.llm_api_key),
    }


@router.get("/status")
def llm_connection_status() -> dict:
    return _status()


@router.post("/config")
def save_llm_connection(payload: LlmConfigRequest) -> dict:
    save_llm_config(
        settings,
        base_url=payload.base_url.strip(),
        model=payload.model.strip(),
        api_key=payload.api_key.strip(),
    )
    return _status()


@router.post("/test")
async def test_llm_connection() -> dict:
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="请先配置大模型 API Key")
    provider = DeepSeekProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
    try:
        await provider.complete(
            [LLMMessage(role="user", content="只回复 OK")],
            tools=[],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="大模型连接失败，请检查地址、模型和 API Key") from exc
    return {"ok": True, "message": "大模型连接成功"}
