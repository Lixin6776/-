import json
import re
from copy import deepcopy
from datetime import date
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

from app.execution.cdp.page_probe import validate_cdp_endpoint
from app.services.material_analysis import MaterialMetric

MATERIAL_DATASET_KEY = "overall_roi_promotion_matrial_tab_video_live"
MATERIAL_LIST_PATH = (
    "/ad/api/pmc/v1/uni-promotion/material/list-required"
    "?reqFrom=uni-prom-creative-tab-list"
)
VIDEO_RADIO_PATTERN = re.compile(r"^视频$")


def _number(container: dict, key: str) -> float | None:
    item = container.get(key)
    value = item.get("value") if isinstance(item, dict) else item
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(container: dict, key: str) -> str:
    item = container.get(key)
    if isinstance(item, dict):
        value = item.get("valueStr", item.get("value", ""))
    else:
        value = item
    return str(value or "").strip()


def _tags(container: dict) -> tuple[str, ...]:
    raw = _text(container, "materialTagList")
    if not raw:
        return ()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return (raw,)
    if not isinstance(value, list):
        return (raw,)
    return tuple(str(item) for item in value if str(item).strip())


def parse_material_list_response(payload: dict) -> list[MaterialMetric]:
    stats = payload.get("data", {}).get("statsData", {})
    rows = stats.get("rows", []) if isinstance(stats, dict) else []
    materials: list[MaterialMetric] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        dimensions = row.get("dimensions", {})
        metrics = row.get("metrics", {})
        if not isinstance(dimensions, dict) or not isinstance(metrics, dict):
            continue
        material_id = _text(dimensions, "materialId")
        name = _text(dimensions, "roi2MaterialVideoName")
        if not material_id or not name:
            continue
        materials.append(
            MaterialMetric(
                material_id=material_id,
                name=name,
                spend=_number(metrics, "statCostForRoi2")
                or _number(metrics, "statCostForOverallRoi2")
                or 0.0,
                roi=_number(metrics, "totalPrepayAndPaySettleOverallRoi21H")
                or _number(metrics, "totalPrepayAndPayOrderRoi2"),
                gmv=_number(metrics, "totalPayOrderGmvIncludeCouponForRoi2") or 0.0,
                orders=int(_number(metrics, "totalPayOrderCountForRoi2") or 0),
                order_cost=_number(metrics, "totalCostPerPayOrderForRoi2"),
                ctr=_number(metrics, "liveCvrRateForRoi2V2"),
                conversion_rate=_number(metrics, "liveConvertRateForRoi2V2"),
                created_at=_text(dimensions, "roi2MaterialUploadTime"),
                tags=_tags(dimensions),
            )
        )
    return materials


def build_material_query_body(
    template: dict,
    analysis_date: date,
    limit: int = 50,
) -> dict:
    body = deepcopy(template)
    body["StartTime"] = f"{analysis_date.isoformat()} 00:00:00"
    body["EndTime"] = f"{analysis_date.isoformat()} 23:59:59"
    body["PageParams"] = {"Limit": max(1, min(limit, 100)), "Offset": 0}
    return body


class CdpMaterialReader:
    def __init__(self, endpoint: str, timeout_seconds: float = 12) -> None:
        self.endpoint = validate_cdp_endpoint(endpoint)
        self.timeout_seconds = timeout_seconds

    async def read(self, analysis_date: date, limit: int = 50) -> list[MaterialMetric]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(self.endpoint)
            try:
                context = browser.contexts[0]
                page = next(
                    (
                        item
                        for item in context.pages
                        if "overall-prom/detail" in item.url
                    ),
                    None,
                )
                if page is None:
                    raise RuntimeError("千川投放管理页面未打开，无法读取素材明细")
                template = await self._capture_list_request(page)
                body = build_material_query_body(template, analysis_date, limit=limit)
                advertiser_id = self._advertiser_id(page.url)
                payload = await page.evaluate(
                    """async ({url, body}) => {
                      const response = await fetch(url, {
                        method: "POST",
                        credentials: "include",
                        headers: {
                          "Content-Type": "application/json",
                          "Accept": "application/json, text/plain, */*"
                        },
                        body: JSON.stringify(body)
                      });
                      return await response.json();
                    }""",
                    {
                        "url": f"{MATERIAL_LIST_PATH}&aavid={advertiser_id}",
                        "body": body,
                    },
                )
                if not isinstance(payload, dict) or payload.get("status_code") != 0:
                    message = payload.get("message") if isinstance(payload, dict) else payload
                    raise RuntimeError(f"素材接口返回失败：{message}")
                return parse_material_list_response(payload)
            finally:
                await playwright.stop()

    async def _capture_list_request(self, page) -> dict:
        await page.locator("#rc-tabs-0-tab-data").click(timeout=int(self.timeout_seconds * 1000))
        await page.wait_for_timeout(400)
        try:
            async with page.expect_request(
                lambda request: "material/list-required" in request.url
                and request.method == "POST",
                timeout=int(self.timeout_seconds * 1000),
            ) as request_info:
                await page.locator("#rc-tabs-0-tab-creative").click(
                    timeout=int(self.timeout_seconds * 1000)
                )
                await page.wait_for_timeout(600)
                video = page.locator(".main-vmok-plugin-radio-item").filter(
                    has_text=VIDEO_RADIO_PATTERN
                )
                await video.first.click(timeout=int(self.timeout_seconds * 1000))
            request = await request_info.value
            template = json.loads(request.post_data or "{}")
        except Exception as exc:
            raise RuntimeError(f"无法捕获千川素材列表请求：{exc}") from exc
        if not isinstance(template, dict) or not template.get("Filters"):
            raise RuntimeError("千川素材列表请求体不完整")
        return template

    @staticmethod
    def _advertiser_id(page_url: str) -> str:
        query = parse_qs(urlparse(page_url).query)
        advertiser_id = query.get("aavid", [None])[0]
        if not advertiser_id:
            raise RuntimeError("当前投放管理页面缺少广告主 ID")
        return str(advertiser_id)