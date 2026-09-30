import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("/events")
async def monitor_events(request: Request):
    service = request.app.state.monitor_service

    async def stream():
        while True:
            event = service.tick()
            yield {"event": "monitor", "data": event.model_dump_json()}
            await asyncio.sleep(service.interval_seconds)

    return EventSourceResponse(stream())