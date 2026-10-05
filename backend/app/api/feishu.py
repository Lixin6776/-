from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.feishu import FeishuConfig

router = APIRouter(prefix="/api/feishu", tags=["feishu"])


class FeishuConfigRequest(BaseModel):
    webhook_url: str = ""
    secret: str = ""
    enabled: bool = False
    auto_send_live_review: bool = True
    auto_send_material_analysis: bool = True


@router.get("/status")
def feishu_status(request: Request) -> dict:
    return request.app.state.feishu_auth_service.status()


@router.post("/config")
def save_feishu_config(payload: FeishuConfigRequest, request: Request) -> dict:
    store = request.app.state.feishu_config_store
    current = store.load()
    config = FeishuConfig(
        webhook_url=payload.webhook_url or current.webhook_url,
        secret=payload.secret or current.secret,
        enabled=payload.enabled,
        auto_send_live_review=payload.auto_send_live_review,
        auto_send_material_analysis=payload.auto_send_material_analysis,
        last_sent_at=current.last_sent_at,
        last_error=current.last_error,
        connection_mode=current.connection_mode if current.chat_id else "webhook",
        chat_id=current.chat_id,
        chat_name=current.chat_name,
        chat_share_link=current.chat_share_link,
        auth_open_id=current.auth_open_id,
        auth_user_name=current.auth_user_name,
        auth_status=current.auth_status,
        auth_message=current.auth_message,
    )
    try:
        store.save(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return request.app.state.feishu_auth_service.status()


@router.post("/test")
def test_feishu_connection(request: Request) -> dict:
    ok, message = request.app.state.feishu_notifier.send_test()
    return {"ok": ok, "message": message}


@router.post("/login/start")
def start_feishu_login(request: Request) -> dict:
    try:
        return request.app.state.feishu_auth_service.start_login()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/login/status")
def feishu_login_status(request: Request) -> dict:
    return request.app.state.feishu_auth_service.status()


@router.post("/login/complete")
def complete_feishu_login(request: Request) -> dict:
    service = request.app.state.feishu_auth_service
    if not service.device_code:
        raise HTTPException(status_code=400, detail="没有待完成的飞书扫码授权。")
    return service.complete_login(service.device_code)
