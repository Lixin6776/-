from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.services.cdp_connection import connect as connect_cdp
from app.services.cdp_connection import probe as probe_cdp

router = APIRouter(prefix="/api/live-watch", tags=["live-watch"])


@router.get("/status")
def live_watch_status(request: Request) -> dict:
    return request.app.state.live_watch_service.status()


@router.post("/start")
async def start_live_watch(request: Request) -> dict:
    return await request.app.state.live_watch_service.start()


@router.post("/stop")
async def stop_live_watch(request: Request) -> dict:
    return await request.app.state.live_watch_service.stop()


@router.post("/resume")
async def resume_live_watch(request: Request) -> dict:
    """从断点恢复盯盘：接着跑 + 立刻补读一次（不用等 5 分钟）。"""
    return await request.app.state.live_watch_service.resume()


@router.post("/heartbeat")
async def heartbeat_live_watch(request: Request) -> dict:
    return await request.app.state.live_watch_service.heartbeat()


@router.post("/tick")
async def tick_live_watch(request: Request) -> dict:
    """手动立刻读一次。正在读的时候直接返回 423，不让请求挂在那儿。"""
    result = await request.app.state.live_watch_service.tick_once(wait=False)
    if isinstance(result, dict) and result.get("busy"):
        raise HTTPException(status_code=423, detail=str(result.get("message") or "正在读取中"))
    return result


@router.get("/connection")
async def live_watch_connection() -> dict:
    """数据源（调试版 Chrome）连接状态。"""
    return await probe_cdp(settings.cdp_endpoint)


@router.post("/connection/connect")
async def connect_live_watch_connection(mode: str = "auto") -> dict:
    """一键连接 / 重连数据源：端口不在线就把调试版 Chrome 拉起来。

    mode=auto（默认）/ default（用平时的 Chrome）/ assistant（用独立浏览器）。
    """
    return await connect_cdp(settings.cdp_endpoint, mode=mode)


@router.get("/logs")
def list_live_watch_logs(request: Request, limit: int = 30) -> list[dict]:
    return request.app.state.live_watch_service.store.list_logs(limit=limit)
