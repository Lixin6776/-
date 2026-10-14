import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/events")
async def notification_events(request: Request):
    hub = request.app.state.notification_hub

    async def stream():
        queue = hub.subscribe()
        try:
            # 先发一个注释，让响应头立即下发，浏览器 EventSource 才会进入 open 状态
            yield {"comment": "connected"}
            while True:
                payload = await queue.get()
                yield {
                    "event": "notification",
                    "data": json.dumps(payload, ensure_ascii=False),
                }
        finally:
            hub.unsubscribe(queue)

    return EventSourceResponse(stream())
