from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.monitor import router as monitor_router
from app.api.profiles import router as profiles_router
from app.api.recommendations import router as recommendations_router
from app.config import settings
from app.db import Base, engine
from app.services.confirmations import ConfirmationService
from app.services.monitor import MonitorService


@asynccontextmanager
async def lifespan(application: FastAPI):
    Base.metadata.create_all(bind=engine)
    application.state.monitor_service = MonitorService(Path(settings.monitor_fixture_path))
    application.state.confirmation_service = ConfirmationService()
    yield


app = FastAPI(title="Qianchuan Local Assistant", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(profiles_router)
app.include_router(chat_router)
app.include_router(monitor_router)
app.include_router(recommendations_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}