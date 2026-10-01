import asyncio
import json
import re
from datetime import UTC, datetime

import httpx
from websockets.asyncio.client import connect

from app.execution.cdp.fixture_adapter import MetricSnapshot
from app.execution.cdp.page_probe import validate_cdp_endpoint

_NUMBER_PATTERN = r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)"


def _number_after(text: str, label: str) -> float:
    start = text.find(label)
    if start < 0:
        raise ValueError(f"Missing required metric: {label}")
    tail = text[start + len(label) : start + len(label) + 200]
    match = re.search(_NUMBER_PATTERN, tail)
    if match is None:
        raise ValueError(f"Missing required metric: {label}")
    return float(match.group(1).replace(",", ""))


def _optional_number_after(text: str, label: str) -> float | None:
    start = text.find(label)
    if start < 0:
        return None
    tail = text[start + len(label) : start + len(label) + 200]
    match = re.search(_NUMBER_PATTERN, tail)
    if match is None:
        return None
    return float(match.group(1).replace(",", ""))


def parse_live_board_text(
    text: str,
    captured_at: datetime | None = None,
) -> MetricSnapshot:
    return MetricSnapshot(
        captured_at=captured_at or datetime.now(UTC),
        freshness="fresh",
        plan_status="ended" if "已结束" in text else "active",
        plan_budget=0.0,
        spend=_number_after(text, "综合成本(元)"),
        gmv=_number_after(text, "净成交金额(元)"),
        orders=int(_number_after(text, "整体成交订单数")),
        views=int(_number_after(text, "直播间整体观看人数")),
        online_viewers=int(_number_after(text, "实时在线人数")),
        roi=_number_after(text, "综合营销ROI"),
        gpm=_number_after(text, "GPM(元)"),
        exposure_count=(
            int(value)
            if (value := _optional_number_after(text, "直播间整体曝光次数")) is not None
            else None
        ),
        view_count=(
            int(value)
            if (value := _optional_number_after(text, "直播间观看次数")) is not None
            else None
        ),
        product_clicks=(
            int(value)
            if (value := _optional_number_after(text, "商品点击次数")) is not None
            else None
        ),
        view_conversion_rate=_optional_number_after(text, "观看成交转化率"),
        exposure_view_rate=_optional_number_after(text, "曝光观看率(次数)"),
    )


class LiveBoardSnapshotReader:
    def __init__(
        self,
        endpoint: str,
        page_marker: str = "board-next",
        timeout_seconds: float = 10,
    ) -> None:
        self.endpoint = validate_cdp_endpoint(endpoint)
        self.page_marker = page_marker
        self.timeout_seconds = timeout_seconds

    async def read(self) -> MetricSnapshot:
        text = await self._read_body_text()
        return parse_live_board_text(text)

    async def _read_body_text(self) -> str:
        target = await self._find_target()
        try:
            async with connect(
                str(target["webSocketDebuggerUrl"]),
                open_timeout=self.timeout_seconds,
                close_timeout=3,
                max_size=20_000_000,
            ) as websocket:
                await websocket.send(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "Runtime.evaluate",
                            "params": {
                                "expression": "document.body.innerText",
                                "returnByValue": True,
                            },
                        }
                    )
                )
                while True:
                    raw = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=self.timeout_seconds,
                    )
                    message = json.loads(raw)
                    if message.get("id") != 1:
                        continue
                    if "error" in message:
                        raise RuntimeError(str(message["error"]))
                    value = message.get("result", {}).get("result", {}).get("value")
                    if not isinstance(value, str):
                        raise TypeError("CDP returned a non-string page body")
                    return value
        except (OSError, TimeoutError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"CDP live board read failed: {exc}") from exc

    async def _find_target(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.endpoint}/json/list")
                response.raise_for_status()
                targets = response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise RuntimeError(f"CDP target discovery failed: {exc}") from exc

        for target in targets:
            if (
                target.get("type") == "page"
                and self.page_marker in str(target.get("url", ""))
                and target.get("webSocketDebuggerUrl")
            ):
                return target
        raise RuntimeError(f"CDP page not found for marker: {self.page_marker}")


def unavailable_snapshot() -> MetricSnapshot:
    return MetricSnapshot(
        captured_at=datetime.now(UTC),
        freshness="stale",
        plan_status="unknown",
        plan_budget=0.0,
        spend=0.0,
        gmv=0.0,
        orders=0,
        views=0,
        online_viewers=0,
        roi=None,
        gpm=None,
        exposure_count=None,
        view_count=None,
        product_clicks=None,
        view_conversion_rate=None,
        exposure_view_rate=None,
    )
