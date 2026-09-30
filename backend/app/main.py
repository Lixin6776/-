from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.actions import router as actions_router
from app.api.api_connection import router as api_connection_router
from app.api.chat import router as chat_router
from app.api.learning import router as learning_router
from app.api.monitor import router as monitor_router
from app.api.profiles import router as profiles_router
from app.api.recommendations import router as recommendations_router
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.execution.api_provider import ApiExecutionProvider
from app.execution.cdp.factory import create_cdp_execution_provider
from app.execution.cdp.live_snapshot import LiveBoardSnapshotReader, unavailable_snapshot
from app.execution.cdp.plan_reader import CdpPlanReader
from app.services.api_client import OceanEngineApiClient
from app.services.monitor import (
    AsyncMonitorService,
    MonitorProfile,
    MonitorService,
    SnapshotReading,
)
from app.services.profiles import StrategyProfileService
from app.services.provider_router import API_SUPPORTED_ACTIONS, ProviderRouter


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

    async def execution_provider_factory(action_name: str | None = None):
        async def close_noop():
            return None

        api_actions = API_SUPPORTED_ACTIONS
        if settings.api_configured and settings.api_advertiser_id:
            router = ProviderRouter(
                api_provider=ApiExecutionProvider(
                    OceanEngineApiClient(config=settings),
                    advertiser_id=settings.api_advertiser_id,
                ),
                cdp_provider=None,
                api_configured=True,
                api_actions=api_actions,
            )
            if action_name in {action.value for action in api_actions}:
                return router.choose(action_name).provider, close_noop

        provider, close = await create_cdp_execution_provider(
            settings.cdp_endpoint,
            Path(settings.selector_config_path),
        )
        return provider, close

    if settings.monitor_source == "fixture":
        application.state.monitor_service = MonitorService(
            Path(settings.monitor_fixture_path),
            interval_seconds=settings.monitor_interval_seconds,
            profile_provider=current_profile,
        )
    else:

        async def read_live_snapshot() -> SnapshotReading:
            try:
                snapshot = await LiveBoardSnapshotReader(
                    settings.cdp_endpoint,
                    page_marker=settings.live_board_page_marker,
                ).read()
                return SnapshotReading(snapshot=snapshot, source="cdp")
            except Exception as exc:  # noqa: BLE001
                return SnapshotReading(
                    snapshot=unavailable_snapshot(),
                    source="cdp-error",
                    error=str(exc),
                )

        application.state.monitor_service = AsyncMonitorService(
            read_live_snapshot,
            interval_seconds=settings.monitor_interval_seconds,
            profile_provider=current_profile,
        )
    application.state.execution_provider_factory = execution_provider_factory
    application.state.plan_snapshot_provider = CdpPlanReader(settings.cdp_endpoint).read
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
app.include_router(api_connection_router)
app.include_router(monitor_router)
app.include_router(learning_router)
app.include_router(recommendations_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}