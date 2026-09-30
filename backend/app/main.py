from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.actions import router as actions_router
from app.api.chat import router as chat_router
from app.api.learning import router as learning_router
from app.api.monitor import router as monitor_router
from app.api.profiles import router as profiles_router
from app.api.recommendations import router as recommendations_router
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.execution.cdp.factory import create_cdp_execution_provider
from app.services.monitor import MonitorProfile, MonitorService
from app.services.profiles import StrategyProfileService


@asynccontextmanager
async def lifespan(application: FastAPI):
    Base.metadata.create_all(bind=engine)

    def current_profile() -> MonitorProfile:
        with SessionLocal() as session:
            try:
                profile = StrategyProfileService(session).get_active()
            except LookupError:
                return MonitorProfile(
                    version=0,
                    business_direction="未配置",
                    primary_objective="请先创建策略画像",
                    hard_constraints={},
                )
            return MonitorProfile(
                version=profile.version,
                business_direction=profile.business_direction,
                primary_objective=profile.primary_objective,
                hard_constraints=profile.hard_constraints,
            )

    application.state.monitor_service = MonitorService(
        Path(settings.monitor_fixture_path),
        profile_provider=current_profile,
    )
    application.state.execution_provider_factory = lambda: create_cdp_execution_provider(
        settings.cdp_endpoint,
        Path(settings.selector_config_path),
    )
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
app.include_router(actions_router)
app.include_router(monitor_router)
app.include_router(learning_router)
app.include_router(recommendations_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}