import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
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
from app.api.live_watch import router as live_watch_router
from app.api.local_config import router as local_config_router
from app.api.live_reviews import router as live_reviews_router
from app.api.llm_connection import router as llm_connection_router
from app.api.material_analyses import router as material_analyses_router
from app.api.monitor import router as monitor_router
from app.api.notifications import router as notifications_router
from app.api.ops_outcome import router as ops_outcome_router
from app.api.ops_chat import router as ops_chat_router
from app.api.plans import router as plans_router
from app.api.profiles import router as profiles_router
from app.api.recommendations import router as recommendations_router
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.execution.api_provider import ApiExecutionProvider
from app.execution.cdp.factory import create_cdp_execution_provider
from app.execution.cdp.live_snapshot import LiveBoardSnapshotReader, unavailable_snapshot
from app.execution.cdp.material_reader import CdpMaterialReader
from app.execution.cdp.plan_log_reader import CdpPlanLogReader
from app.execution.cdp.plan_reader import CdpPlanReader
from app.execution.cdp.plan_split_reader import CdpPlanSplitReader
from app.services.analytics import ComputedMetrics
from app.services.api_client import OceanEngineApiClient
from app.services.api_config import load_api_config
from app.services.cdp_connection import connect as cdp_connect
from app.services.feishu import FeishuConfigStore, FeishuNotifier, FeishuQrAuthService
from app.services.live_review import (
    LiveReviewStore,
    append_review_items,
    build_site_change_section,
    build_spend_structure,
    insert_sections,
)
from app.services.site_changes import SiteChangeStore
from app.services.live_watch import (
    LiveWatchLogStore,
    LiveWatchService,
    compute_baselines,
)
from app.services.review_backfill import (
    build_catch_up_review,
    group_sessions,
    missing_sessions,
    review_date_of,
)
from app.services.watch_log_store import SqliteWatchLogStore
from app.services import local_config
from app.services.ops_chat import (
    OpsChatStore,
    build_daily_briefing,
    collect_briefing_inputs,
)
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


MATERIAL_ANALYSIS_HOUR = 8
MATERIAL_ANALYSIS_CATCH_UP_DAYS = 3


def _day_account_metrics(application: FastAPI, analysis_date: "date") -> ComputedMetrics | None:
    """目标日最后一条有效盯盘读数 → 当天的账户口径。

    素材报告里的「综合成本 / ROI / 净成交 / 订单 / GPM」应该是**目标那天**的，
    不能拿"最近一次盯盘读数"（那是今天那一刻的）。这里和复盘同源：都用盯盘记录。
    """
    service = getattr(application.state, "live_watch_service", None)
    store = getattr(service, "store", None)
    if store is None:
        return None
    target = analysis_date.isoformat()
    try:
        logs = store.list_logs(limit=800)
    except Exception:  # noqa: BLE001
        return None
    best = None
    best_ts = None
    for report in logs:
        if report.get("source") == "cdp-error":
            continue
        try:
            ts = datetime.fromisoformat(str(report.get("created_at")))
        except (TypeError, ValueError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        if ts.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d") != target:
            continue
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best = report
    if best is None:
        return None
    return ComputedMetrics(
        roi=best.get("roi"),
        gpm=best.get("gpm"),
        spend=float(best.get("spend") or 0.0),
        gmv=float(best.get("gmv") or 0.0),
        orders=int(best.get("orders") or 0),
        online_viewers=int(best.get("online_viewers") or 0),
        views=int(best.get("views") or 0),
        exposure_view_rate=best.get("exposure_view_rate"),
        view_conversion_rate=best.get("view_conversion_rate"),
        room_name=best.get("room_name"),
        live_room_id=best.get("live_room_id"),
    )


async def run_material_analysis_job(
    application: FastAPI,
    analysis_date: "date | None" = None,
) -> dict:
    """Generate the material analysis report.

    Default target is **yesterday** (Asia/Shanghai): the 08:00 run on day D
    reports on day D-1, and compares it against D-2.
    """
    if getattr(application.state, "latest_plan_snapshot", None) is None:
        await refresh_plan_snapshot(application)
    local_today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    target_date = analysis_date or (local_today - timedelta(days=1))
    store = application.state.material_analysis_store
    existing = next(
        (item for item in store.list_analyses() if item.get("date") == target_date.isoformat()),
        None,
    )
    existing_metrics = (existing.get("metrics") or {}) if existing is not None else {}
    # 老版本报告（report_schema != 2）用的是"前 N 条明细求和当总消耗"+"最近一次盯盘读数当账户口径"，
    # 命中就重算一次，用上服务端精确总额 + 目标日读数，算完自愈。
    existing_is_stale = existing is not None and existing_metrics.get("report_schema") != 3
    if (
        existing is not None
        and int(existing_metrics.get("material_count", 0) or 0) > 0
        and not existing_is_stale
    ):
        return existing
    day_metrics = _day_account_metrics(application, target_date)
    report = await generate_and_publish_material_analysis(
        application.state.monitor_service,
        lambda: getattr(application.state, "latest_plan_snapshot", None),
        store,
        application.state.notification_hub,
        material_reader=application.state.material_reader,
        analysis_date=target_date,
        day_metrics=day_metrics,
        # 历史某天没有有效盯盘数据时，账户口径只能退回"最近一次读数" —— 得如实说明
        account_note=(
            "当天没有有效盯盘数据，下面的账户口径（综合成本 / ROI 等）取自最近一次读数，仅供参考"
            if target_date < local_today and day_metrics is None
            else None
        ),
    )
    feishu_notifier = getattr(application.state, "feishu_notifier", None)
    if feishu_notifier is not None:
        await asyncio.to_thread(feishu_notifier.send_material_analysis, report)
    return report


async def catch_up_material_analysis(application: FastAPI) -> None:
    """Backfill a missed 08:00 run (e.g. the PC/backend was off overnight).

    Runs shortly after startup, only when the local time is already past the
    scheduled hour and yesterday's report is still missing. Covers up to
    ``MATERIAL_ANALYSIS_CATCH_UP_DAYS`` consecutive missed days.
    """
    try:
        today = datetime.now(ZoneInfo("Asia/Shanghai"))
        if today.hour < MATERIAL_ANALYSIS_HOUR:
            return
        store = application.state.material_analysis_store
        have = {
            item.get("date")
            for item in store.list_analyses()
            if int((item.get("metrics") or {}).get("material_count", 0) or 0) > 0
            # 老版本报告（report_schema != 2）不算"已有"，让它重算一次
            and (item.get("metrics") or {}).get("report_schema") == 3
        }
        for offset in range(1, MATERIAL_ANALYSIS_CATCH_UP_DAYS + 1):
            target = today.date() - timedelta(days=offset)
            if target.isoformat() in have:
                continue
            await application.state.material_analysis_runner(analysis_date=target)
    except Exception:  # noqa: BLE001
        return


@asynccontextmanager
async def lifespan(application: FastAPI):
    review_store = LiveReviewStore()
    material_analysis_store = MaterialAnalysisStore()
    def material_detail_fallback_ad_id() -> str | None:
        """Latest known plan id, used to re-open the 投放管理 detail page."""
        plan = getattr(application.state, "latest_plan_snapshot", None)
        plan_id = getattr(plan, "id", None)
        return str(plan_id) if plan_id else None

    material_reader = CdpMaterialReader(
        settings.cdp_endpoint,
        fallback_ad_id=material_detail_fallback_ad_id,
        plan_room_name=local_config.room_name(settings.live_board_room_name),
    )
    feishu_config_store = FeishuConfigStore()
    feishu_notifier = FeishuNotifier(feishu_config_store)
    feishu_auth_service = FeishuQrAuthService(feishu_config_store)
    notification_hub = NotificationHub()
    live_watch_store = SqliteWatchLogStore()
    ops_chat_store = OpsChatStore()
    site_change_store = SiteChangeStore()
    load_llm_config(settings)
    load_api_config(settings)
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

    async def enrich_and_send_review(review: dict) -> None:
        """复盘生成后补上素材口径的消耗结构（基础/追投），再发送。"""
        try:
            today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            split = await application.state.material_reader.read_totals(today)
            section, extra_problems, extra_fixes = build_spend_structure(split)
            # 人货场变更及影响
            day = str(review.get("date") or "")
            changes = site_change_store.list(day=day) if day else []
            session_logs = live_watch_store.list_logs(limit=400)
            if session_logs and session_logs[0].get("live_started_at"):
                cur_session = session_logs[0]["live_started_at"]
                session_logs = [
                    x for x in session_logs if x.get("live_started_at") == cur_session
                ]
            change_section = build_site_change_section(changes, session_logs)
            markdown = insert_sections(
                str(review.get("report_markdown") or ""), [section, change_section]
            )
            markdown = append_review_items(markdown, extra_problems, extra_fixes)
            review["report_markdown"] = markdown
            review["spend_structure"] = split
            review_store.upsert(review)
        except Exception:  # noqa: BLE001
            pass
        # 复盘同时沉淀到「直播运营助手」对话里，方便之后追问
        try:
            room = str(review.get("room") or "")
            date_text = str(review.get("date") or "")
            content = (
                f"**{date_text} 直播复盘已生成**"
                + (f"（{room}）" if room else "")
                + "\n\n"
                + str(review.get("report_markdown") or "")
            )
            message = ops_chat_store.append(
                "assistant", content, kind="review", meta={"date": date_text}
            )
            await notification_hub.publish(
                {
                    "type": "ops_chat",
                    "id": message["id"],
                    "message": message["content"],
                    "created_at": message["created_at"],
                }
            )
        except Exception:  # noqa: BLE001
            pass
        await asyncio.to_thread(feishu_notifier.send_live_review, review)

    async def run_daily_ops_briefing(application: FastAPI, day=None) -> dict:
        """生成《每日运营汇报》并推给运营助手对话（+ 飞书文档）。"""
        from datetime import date as _date

        target_day = day or datetime.now(ZoneInfo("Asia/Shanghai")).date()
        inputs = collect_briefing_inputs(application.state)
        content = build_daily_briefing(
            day=target_day,
            watch_reports=inputs["watch_reports"],
            reviews=inputs["reviews"],
            analyses=inputs["analyses"],
        )
        message = ops_chat_store.replace_daily_briefing(
            content, meta={"day": target_day.isoformat()}
        )
        await notification_hub.publish(
            {
                "type": "ops_chat",
                "id": message["id"],
                "message": content,
                "created_at": message["created_at"],
            }
        )
        # 汇报也发一份飞书文档
        try:
            await asyncio.to_thread(
                feishu_notifier.send_live_review,
                {"id": f"daily-briefing-{target_day.isoformat()}", "report_markdown": content},
            )
        except Exception:  # noqa: BLE001
            pass
        return message

    async def on_session_ended(room: str | None, started) -> None:
        """本场一结束就把复盘做出来（不等 30 分钟的补跑），并发出去。"""
        try:
            logs = live_watch_store.list_logs(limit=400)
            sessions = group_sessions(logs)
            key = started.isoformat() if started is not None else None
            target = next(
                (item for item in sessions if item.get("live_started_at") == key),
                sessions[-1] if sessions else None,
            )
            if target is None or not target.get("reports"):
                return
            day = review_date_of(target)
            if not day:
                return
            if any(str(i.get("date")) == day for i in review_store.list_reviews()):
                return  # 已经有复盘了
            review = build_catch_up_review({**target, "date": day}, current_profile())
            review_store.add_if_absent(review)
            content = (
                f"**{day} 直播复盘**"
                + (f"（{room}）" if room else "")
                + "\n\n"
                + str(review.get("report_markdown") or "")
            )
            message = ops_chat_store.append(
                "assistant", content, kind="review", meta={"date": day}
            )
            await notification_hub.publish(
                {
                    "type": "ops_chat",
                    "id": message["id"],
                    "message": message["content"],
                    "created_at": message["created_at"],
                }
            )
            await asyncio.to_thread(feishu_notifier.send_live_review, review)
        except Exception:  # noqa: BLE001
            pass

    async def run_review_backfill(application: FastAPI, allow_latest: bool = False) -> dict:
        """补跑漏掉的直播复盘。

        复盘原本只在「读到 已结束 的那一次盯盘」触发，那一刻后端不在跑就永远丢了
        （10-09 那场就是这么没的）。这里保守处理：只在日志里已经出现**更新的场次**
        时，才给旧场次补复盘。
        """
        created: list[str] = []
        try:
            logs = live_watch_store.list_logs(limit=400)
            existing = {
                str(item.get("date")) for item in review_store.list_reviews()
            }
            # 最新一场只有在"外部确认当前没在播"时才允许补
            if allow_latest:
                allow_latest = await session_state_provider() == "not-live"
            pending = missing_sessions(logs, existing, allow_latest=allow_latest)
        except Exception:  # noqa: BLE001
            return {"created": [], "error": "读取盯盘记录失败"}
        for session in pending:
            try:
                review = build_catch_up_review(session, current_profile())
                review_store.add_if_absent(review)
                created.append(str(review.get("date")))
                day = str(review.get("date") or "")
                room = str(review.get("room") or "")
                content = (
                    f"**{day} 直播复盘（补跑生成）**"
                    + (f"（{room}）" if room else "")
                    + "\n\n"
                    + str(review.get("report_markdown") or "")
                )
                message = ops_chat_store.append(
                    "assistant", content, kind="review", meta={"date": day, "caught_up": True}
                )
                await notification_hub.publish(
                    {
                        "type": "ops_chat",
                        "id": message["id"],
                        "message": message["content"],
                        "created_at": message["created_at"],
                    }
                )
                await asyncio.to_thread(feishu_notifier.send_live_review, review)
            except Exception:  # noqa: BLE001
                continue
        return {"created": created, "checked": len(pending)}

    async def catch_up_ops_briefing(application: FastAPI) -> None:
        """错过 08:05 的汇报（关机/后端没开）时补一次。"""
        try:
            now = datetime.now(ZoneInfo("Asia/Shanghai"))
            if now.hour < MATERIAL_ANALYSIS_HOUR:
                return
            if ops_chat_store.has_today("briefing"):
                return
            await run_daily_ops_briefing(application, now.date())
        except Exception:  # noqa: BLE001
            return

    def account_baselines() -> dict | None:
        """本账户历史分位 —— 复盘判断阈值优先用它（其次是你在决策窗口设的值）。

        这里**不带 session**：要的是"这个账户历史上大概什么水平"，
        不是"本场刚才多少"，所以走同直播间的全量历史。
        """
        try:
            logs = live_watch_store.list_logs(limit=400)
        except Exception:  # noqa: BLE001
            return None
        try:
            return compute_baselines(
                logs, room_name=local_config.room_name(settings.live_board_room_name) or None
            )
        except Exception:  # noqa: BLE001
            return None

    def plan_roi_target() -> float | None:
        """计划里实际的「综合营销ROI目标」——盯盘和复盘都用它，保证同一场只有一个目标。"""
        plan = getattr(application.state, "latest_plan_snapshot", None)
        value = getattr(plan, "roi_goal", None)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def avg_online_provider() -> tuple[float | None, int]:
        """本场平均在线人数：只统计「当前场次」非 0 的采样。

        场次用 live_started_at 识别（同一天可能有多场，不能按日期切）。
        """
        try:
            logs = live_watch_store.list_logs(limit=400)
        except Exception:  # noqa: BLE001
            return None, 0
        latest = logs[0] if logs else {}
        session = latest.get("live_started_at")
        values = []
        for item in logs:
            if session is not None and item.get("live_started_at") != session:
                continue
            v = item.get("online_viewers")
            if isinstance(v, (int, float)) and v > 0:
                values.append(float(v))
        if len(values) < 3:
            return None, len(values)
        return sum(values) / len(values), len(values)

    def notify_live_review(review: dict) -> None:
        try:
            asyncio.create_task(enrich_and_send_review(review))
        except RuntimeError:
            feishu_notifier.send_live_review(review)

    if settings.monitor_source == "fixture":
        application.state.monitor_service = MonitorService(
            Path(settings.monitor_fixture_path),
            interval_seconds=settings.monitor_interval_seconds,
            profile_provider=current_profile,
            review_store=review_store,
            review_notifier=notify_live_review,
            avg_online_provider=avg_online_provider,
            roi_target_provider=plan_roi_target,
            baselines_provider=account_baselines,
        )
    else:

        async def read_live_snapshot() -> SnapshotReading:
            try:
                snapshot = await LiveBoardSnapshotReader(
                    settings.cdp_endpoint,
                    page_marker=settings.live_board_page_marker,
                    room_name=local_config.room_name(settings.live_board_room_name),
                    room_id=settings.live_board_room_id,
                ).read(refresh=True)
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
            avg_online_provider=avg_online_provider,
            roi_target_provider=plan_roi_target,
            baselines_provider=account_baselines,
        )
    async def session_state_provider() -> str:
        """确认「当前有没有在播的场次」。

        大屏页面头部经常不渲染，读不到「已结束」；投放管理页（今天）上有没有
        「直播大屏」入口，是更可靠的信号：有=在播，没有=当前没播。
        """
        from app.execution.cdp.live_snapshot import LiveBoardSnapshotReader

        try:
            reader = LiveBoardSnapshotReader(
                settings.cdp_endpoint,
                page_marker=settings.live_board_page_marker,
                room_name=local_config.room_name(settings.live_board_room_name),
                room_id=settings.live_board_room_id,
            )
            url = await reader._discover_board_url()
        except Exception:  # noqa: BLE001
            return "unknown"
        return "live" if url else "not-live"

    async def snapshot_refresher():
        """自检用：忽略缓存，重新读一次大屏（会点「刷新数据」）。"""
        reading = await read_live_snapshot()
        return reading.snapshot

    async def spend_split_provider(session_start=None) -> dict | None:
        """素材口径的消耗构成：基础计划 / 追投调控 的消耗、ROI、成交、订单拆分。

        传 session_start 时把口径收敛到当前直播场次（和直播大屏同一时间窗），
        避免拿整天数据和场次数据混在一张表里。
        """
        try:
            now = datetime.now(ZoneInfo("Asia/Shanghai"))
            today = now.date()
            start_text = None
            if session_start is not None:
                try:
                    start_text = session_start.astimezone(
                        ZoneInfo("Asia/Shanghai")
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:  # noqa: BLE001
                    start_text = None
            end_text = now.strftime("%Y-%m-%d %H:%M:%S")
            return await application.state.material_reader.read_totals(
                today,
                window_start=start_text,
                window_end=end_text if start_text else None,
            )
        except Exception:  # noqa: BLE001
            return None

    plan_log_reader = CdpPlanLogReader(settings.cdp_endpoint)

    async def platform_log_provider() -> list[dict]:
        """读取千川「详情 → 日志」里的平台操作记录。"""
        try:
            return await plan_log_reader.read_recent(limit=10)
        except Exception:  # noqa: BLE001
            return []

    async def notify_watch_alert(title: str, body: str) -> None:
        """盯盘异常：进运营助手对话 + 推飞书，别让用户自己去面板上发现。"""
        content = f"**{title}**\n\n{body}"
        try:
            message = ops_chat_store.append("assistant", content, kind="alert")
            await notification_hub.publish(
                {
                    "type": "ops_chat",
                    "id": message["id"],
                    "message": message["content"],
                    "created_at": message["created_at"],
                }
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            await asyncio.to_thread(feishu_notifier.send_alert, title, body)
        except Exception:  # noqa: BLE001
            pass

    application.state.live_watch_service = LiveWatchService(
        application.state.monitor_service,
        notification_hub,
        store=live_watch_store,
        interval_seconds=settings.monitor_interval_seconds,
        plan_provider=lambda: getattr(application.state, "latest_plan_snapshot", None),
        plan_refresher=partial(refresh_plan_snapshot, application),
        spend_split_provider=spend_split_provider,
        platform_log_provider=platform_log_provider,
        plan_split_provider=CdpPlanSplitReader(settings.cdp_endpoint).read,
        snapshot_refresher=snapshot_refresher,
        session_state_provider=session_state_provider,
        profile_provider=current_profile,
        session_end_handler=on_session_ended,
        alert_notifier=notify_watch_alert,
        # CDP 断了（浏览器被关/电脑休眠）自动重连，不用人再点「连接数据源」
        cdp_reconnector=partial(cdp_connect, settings.cdp_endpoint, mode="auto"),
    )
    if settings.enable_background_jobs:
        await application.state.live_watch_service.resume_if_needed()
    application.state.material_analysis_store = material_analysis_store
    application.state.live_review_store = review_store
    application.state.ops_chat_store = ops_chat_store
    application.state.material_reader = material_reader
    application.state.notification_hub = notification_hub
    application.state.feishu_config_store = feishu_config_store
    application.state.feishu_notifier = feishu_notifier
    application.state.feishu_auth_service = feishu_auth_service

    application.state.material_analysis_runner = partial(run_material_analysis_job, application)
    application.state.ops_briefing_runner = partial(run_daily_ops_briefing, application)

    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    if not settings.enable_background_jobs:
        # 测试 / 纯查接口时：不挂定时任务、不自动恢复盯盘
        application.state.scheduler = scheduler
        application.state.execution_provider_factory = execution_provider_factory
        application.state.plan_snapshot_provider = CdpPlanReader(
            settings.cdp_endpoint
        ).read
        application.state.latest_plan_snapshot = None
        yield
        return
    scheduler.add_job(
        application.state.material_analysis_runner,
        CronTrigger(
            hour=MATERIAL_ANALYSIS_HOUR,
            minute=0,
            timezone="Asia/Shanghai",
        ),
        id="daily-material-analysis",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=6 * 60 * 60,
    )
    # 08:05 出《每日运营汇报》：等 08:00 的素材分析先落地
    scheduler.add_job(
        application.state.ops_briefing_runner,
        CronTrigger(
            hour=MATERIAL_ANALYSIS_HOUR,
            minute=5,
            timezone="Asia/Shanghai",
        ),
        id="daily-ops-briefing",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=6 * 60 * 60,
    )
    scheduler.start()
    application.state.scheduler = scheduler
    application.state.material_analysis_catch_up = asyncio.create_task(
        catch_up_material_analysis(application)
    )
    application.state.ops_briefing_catch_up = asyncio.create_task(
        catch_up_ops_briefing(application)
    )
    application.state.review_backfill_runner = partial(
        run_review_backfill, application, allow_latest=True
    )
    scheduler.add_job(
        application.state.review_backfill_runner,
        CronTrigger(minute="*/30", timezone="Asia/Shanghai"),
        id="review-backfill",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=30 * 60,
    )
    application.state.review_backfill_catch_up = asyncio.create_task(
        run_review_backfill(application, allow_latest=True)
    )

    application.state.execution_provider_factory = execution_provider_factory
    application.state.plan_snapshot_provider = CdpPlanReader(settings.cdp_endpoint).read
    application.state.latest_plan_snapshot = None
    yield

    # ---- 关停收尾 ----
    # 不做收尾的话，进程退出时这些后台任务不会被干净取消，
    # Starlette TestClient 的 __exit__ 会一直等（实测整个测试套件挂死），
    # 真实重启时也会拖时间。
    for attr in (
        "review_backfill_catch_up",
        "ops_briefing_catch_up",
        "material_analysis_catch_up",
    ):
        task = getattr(application.state, attr, None)
        if task is not None and not task.done():
            task.cancel()
    service = getattr(application.state, "live_watch_service", None)
    if service is not None:
        try:
            await asyncio.wait_for(service.stop(), timeout=8)
        except Exception:  # noqa: BLE001
            pass
    scheduler = getattr(application.state, "scheduler", None)
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass


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
app.include_router(live_watch_router)
app.include_router(live_reviews_router)
app.include_router(ops_outcome_router)
app.include_router(material_analyses_router)
app.include_router(notifications_router)
app.include_router(ops_chat_router)
app.include_router(local_config_router)
app.include_router(llm_connection_router)
app.include_router(recommendations_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}