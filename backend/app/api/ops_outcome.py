# -*- coding: utf-8 -*-
"""操作净效应 API。"""

from fastapi import APIRouter, Request

from app.services.ops_outcome import compute_ops_outcome

router = APIRouter(prefix="/api/ops-outcome", tags=["ops-outcome"])


@router.get("")
def ops_outcome(request: Request, limit: int = 1500) -> dict:
    """算《操作反馈表》：哪些操作被数据正向反馈（观察性相关，非因果）。"""
    logs = request.app.state.live_watch_service.store.list_logs(limit=limit)
    return compute_ops_outcome(logs)
