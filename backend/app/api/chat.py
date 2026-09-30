from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.services.llm.openai_compatible import OpenAICompatibleProvider
from app.services.orchestrator import ChatResult, Orchestrator
from app.services.profiles import StrategyProfileService

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


def get_llm_provider():
    return OpenAICompatibleProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )


@router.post("", response_model=ChatResult)
async def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    llm=Depends(get_llm_provider),
) -> ChatResult:
    profile = StrategyProfileService(db).get_active()
    return await Orchestrator(llm).handle(payload.message, profile)