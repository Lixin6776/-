import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.actions import router as actions_router
from app.api.api_connection import router as api_connection_router
from app.api.chat import router as chat_router
from app.api.feishu import router as feishu_router
from app.api.learning import router as learning_router
from app.api.live_reviews import router as live_reviews_router
from app.api.llm_connection import router as llm_connection_router
from app.api.material_analyses import router as material_analyses_router
from app.api.monitor import router as monitor_router
from app.api.notifications import router as notifications_router
from app.api.plans import router as plans_router
from app.api.profiles import router as profiles_router
from app.api.recommendations import router as recommendations_router
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.execution.api_provider import ApiExecutionProvider
from app.execution.cdp.factory import create_cdp_execution_provider
from app.execution.cdp.live_snapshot import LiveBoardSnapshotReader, unavailable_snapshot
from app.execution.cdp.material_reader import CdpMaterialReader
from app.execution.cdp.plan_reader import CdpPlanReader
from app.services.api_client import OceanEngineApiClient
from app.services.feishu import FeishuConfigStore, FeishuNotifier
from app.services.live_review import LiveReviewStore
from app.services.llm_config import load_llm_config
from app.services.material_analysis import (
    MaterialAnalysisStore,
    generate_and_publish_material_analysis,
)
from app.services.monitor import (
    AsyncMonitorService,
    MonitorProfile,
    MonitorService,
    SnapshotReading,
)
from app.services.notifications import NotificationHub
from app.services.profiles import StrategyProfileService
from app.services.provider_router import API_SUPPORTED_ACTIONS, ProviderRouter


async def refresh_plan_snapshot(application: FastAPI) -> None:
    try:
        application.state.latest_plan_snapshot = await asyncio.to_thread(
            CdpPlanReader(settings.cdp_endpoint).read_current
        )
    except Exception:  # noqa: BLE001
        return


async def run_material_analysis_job(application: FastAPI) -> dict:
    if getattr(application.state, "latest_plan_snapshot", None) is None:
        await refresh_plan_snapshot(application)
    local_today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    report = await generate_and_publish_material_analysis(
        application.state.monitor_service,
        lambda: getattr(application.state, "latest_plan_snapshot", None),
        application.state.material_analysis_store,
        application.state.notification_hub,
        material_reader=application.state.material_reader,
        analysis_date=local_today - timedelta(days=1),
    )
    feishu_notifier = getattr(application.state, "feishu_notifier", None)
    if feishu_notifier is not None:
        await asyncio.to_thread(feishu_notifier.send_material_analysis, report)
    return report


@asynccontextmanager
async def lifespan(application: FastAPI):
    review_store = LiveReviewStore()
    material_analysis_store = MaterialAnalysisStore()
    material_reader = CdpMaterialReader(settings.cdp_endpoint)
    feishu_config_store = FeishuConfigStore()
    feishu_notifier = FeishuNotifier(feishu_config_store)
    notification_hub = NotificationHub()
    load_llm_config(settings)
    Base.metadata.create_all(bind=engine)

    def current_profile() -> MonitorProfile:
        with SessionLocal() as session:
            try:
                profile = StrategyProfileService(session).get_active()
            except LookupError:
                version = 0
                business_direction = "未配置"
                primary_objective = "请先创建投放策略"
                hard_constraints: dict = {}
            else:
                version = profile.version
                business_direction = profile.business_direction
                primary_objective = profile.primary_objective
                hard_constraints = dict(profile.hard_constraints)

        plan = getattr(application.state, "latest_plan_snapshot", None)
        if plan is not None and plan.roi_goal is not None:
            hard_constraints = {**hard_constraints, "roi_target": plan.roi_goal}
        return MonitorProfile(
            version=version,
            business_direction=business_direction,
            primary_objective=primary_objective,
            hard_constraints=hard_constraints,
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

    def notify_live_review(review: dict) -> None:
        feishu_notifier.send_live_review(review)

    if settings.monitor_source == "fixture":
        application.state.monitor_service = MonitorService(
            Path(settings.monitor_fixture_path),
            interval_seconds=settings.monitor_interval_seconds,
            profile_provider=current_profile,
            review_store=review_store,
            review_notifier=notify_live_review,
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
            review_store=review_store,
            review_notifier=notify_live_review,
        )
    application.state.material_analysis_store = material_analysis_store
    application.state.material_reader = material_reader
    application.state.notification_hub = notification_hub
    application.state.feishu_config_store = feishu_config_store
    application.state.feishu_notifier = feishu_notifier

    application.state.material_analysis_runner = partial(run_material_analysis_job, application)

    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        application.state.material_analysis_runner,
        CronTrigger(hour=8, minute=0, timezone="Asia/Shanghai"),
        id="daily-material-analysis",
        replace_existing=True,
    )
    scheduler.start()
    application.state.scheduler = scheduler

    application.state.execution_provider_factory = execution_provider_factory
    application.state.plan_snapshot_provider = CdpPlanReader(settings.cdp_endpoint).read
    application.state.latest_plan_snapshot = None
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
app.include_router(feishu_router)
app.include_router(actions_router)
app.include_router(api_connection_router)
app.include_router(monitor_router)
app.include_router(plans_router)
app.include_router(learning_router)
app.include_router(live_reviews_router)
app.include_router(material_analyses_router)
app.include_router(notifications_router)
app.include_router(llm_connection_router)
app.include_router(recommendations_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}