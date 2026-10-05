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
    return request.app.state.feishu_config_store.status()


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
    )
    try:
        store.save(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return store.status()


@router.post("/test")
def test_feishu_connection(request: Request) -> dict:
    ok, message = request.app.state.feishu_notifier.send_test()
    return {"ok": ok, "message": message}
