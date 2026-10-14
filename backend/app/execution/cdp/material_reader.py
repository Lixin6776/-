import asyncio
import inspect
import json
import re
from contextlib import suppress
from copy import deepcopy
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

from app.execution.cdp.page_probe import validate_cdp_endpoint
from app.services.material_analysis import MaterialMetric

MATERIAL_DATASET_KEY = "overall_roi_promotion_matrial_tab_video_live"
DETAIL_PAGE_MARKER = "overall-prom/detail"
MATERIAL_PAGE_URL_PATH = (
    Path(__file__).resolve().parents[4] / ".local" / "material_page_url.txt"
)
MATERIAL_PLAN_PATH = (
    Path(__file__).resolve().parents[4] / ".local" / "material_plan.json"
)
MATERIAL_LIST_PATH = (
    "/ad/api/pmc/v1/uni-promotion/material/list-required"
    "?reqFrom=uni-prom-creative-tab-list"
)
VIDEO_RADIO_PATTERN = re.compile(r"^视频$")

# 素材列表接口里与「基础 / 追投调控」拆分相关的指标。
# 基础：basic_*_v2；追投调控：additional_delivery_*_assist。
# 这些键是千川「素材」tab 数据集 overall_roi_promotion_matrial_tab_video_live 里
# 唯一支持 基础/追投 拆分的一组口径（已逐个探针验证）。
MATERIAL_SPLIT_METRICS = (
    "stat_cost_for_roi2",
    "basic_stat_cost_for_roi2_v2",
    "additional_delivery_stat_cost_for_roi2_assist",
    "total_pay_order_gmv_include_coupon_for_roi2",
    "additional_delivery_total_pay_order_gmv_include_coupon_for_roi2_assist",
    "total_pay_order_count_for_roi2",
    "additional_delivery_total_pay_order_count_for_roi2_assist",
    "total_prepay_and_pay_order_roi2",
    "additional_delivery_total_prepay_and_pay_order_roi2_assist",
)



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
    def __init__(
        self,
        endpoint: str,
        timeout_seconds: float = 12,
        fallback_ad_id=None,
        plan_room_name: str = "",
    ) -> None:
        self.endpoint = validate_cdp_endpoint(endpoint)
        self.timeout_seconds = timeout_seconds
        self.fallback_ad_id = fallback_ad_id
        self.plan_room_name = (plan_room_name or "").strip()

    # --- page recovery helpers -------------------------------------------------
    @staticmethod
    def _remember_page_url(url: str) -> None:
        """Persist the working 投放管理 detail URL so it can be re-opened later."""
        try:
            MATERIAL_PAGE_URL_PATH.parent.mkdir(parents=True, exist_ok=True)
            MATERIAL_PAGE_URL_PATH.write_text(url, encoding="utf-8")
        except OSError:
            return

    @staticmethod
    def _remembered_page_url() -> str | None:
        try:
            value = MATERIAL_PAGE_URL_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    @staticmethod
    def _build_detail_url(aavid: str, ad_id: str) -> str:
        return (
            "https://qianchuan.jinritemai.com/overall-prom/detail"
            f"?aavid={aavid}&campaignType=1&uniTab=ad&adId={ad_id}"
        )

    @staticmethod
    def _scan_open_pages(context) -> tuple[str | None, str | None, list[str]]:
        """Collect (aavid, adId, full-urls) from already open qianchuan tabs."""
        aavid: str | None = None
        ad_id: str | None = None
        urls: list[str] = []
        for item in context.pages:
            url = item.url or ""
            if "qianchuan.jinritemai.com" not in url:
                continue
            query = parse_qs(urlparse(url).query)
            page_aavid = (query.get("aavid") or [None])[0]
            page_ad = (query.get("adId") or [None])[0]
            if page_aavid and aavid is None:
                aavid = page_aavid
            if page_ad and ad_id is None:
                ad_id = page_ad
            if page_aavid and page_ad:
                urls.append(url)
        return aavid, ad_id, urls

    def _candidate_urls(self, context) -> list[str]:
        urls: list[str] = []

        def push(value: str | None) -> None:
            if value and value not in urls:
                urls.append(value)

        remembered = self._remembered_page_url()
        push(remembered)

        aavid, ad_id, open_urls = self._scan_open_pages(context)
        for url in open_urls:
            push(url)

        if aavid is None and remembered:
            query = parse_qs(urlparse(remembered).query)
            aavid = (query.get("aavid") or [None])[0] or None

        fallback_ad_id = None
        if self.fallback_ad_id is not None:
            try:
                fallback_ad_id = self.fallback_ad_id()
            except Exception:  # noqa: BLE001
                fallback_ad_id = None
        if fallback_ad_id and aavid:
            push(self._build_detail_url(str(aavid), str(fallback_ad_id)))
        return urls

    async def _ensure_page(self, context):
        """Return a 投放管理 detail page, re-opening it if it is not open."""
        for item in context.pages:
            if DETAIL_PAGE_MARKER in (item.url or ""):
                self._remember_page_url(item.url)
                return item

        last_error: Exception | None = None
        for url in self._candidate_urls(context):
            page = None
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(6000)
                await page.locator("#rc-tabs-0-tab-creative").wait_for(
                    state="attached",
                    timeout=int(self.timeout_seconds * 1000),
                )
                self._remember_page_url(page.url)
                return page
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if page is not None:
                    with suppress(Exception):
                        await page.close()

        raise RuntimeError(
            "千川投放管理详情页未打开且无法自动恢复，无法读取素材明细"
            + (f"：{last_error}" if last_error else "")
        )

    # --- target plan resolution ------------------------------------------------
    @staticmethod
    def _remember_plan(ad_id: str, room_name: str) -> None:
        try:
            MATERIAL_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
            MATERIAL_PLAN_PATH.write_text(
                json.dumps({"ad_id": ad_id, "room_name": room_name}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            return

    @staticmethod
    def _remembered_plan() -> dict:
        try:
            payload = json.loads(MATERIAL_PLAN_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _page_room_name(text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("抖音号："):
                return stripped.split("：", 1)[1].strip()
        return ""

    @staticmethod
    def _aavid_from_context(context) -> str:
        for item in context.pages:
            url = item.url or ""
            if "qianchuan.jinritemai.com" not in url:
                continue
            value = (parse_qs(urlparse(url).query).get("aavid") or [""])[0]
            if value:
                return value
        return ""

    @staticmethod
    def _plan_id_from_url(url: str) -> str:
        return (parse_qs(urlparse(url or "").query).get("adId") or [""])[0]

    @staticmethod
    def _detail_url(aavid: str, ad_id: str) -> str:
        return (
            "https://qianchuan.jinritemai.com/overall-prom/detail"
            f"?aavid={aavid}&campaignType=1&uniTab=ad&adId={ad_id}"
        )

    async def _open_detail(self, context, aavid: str, ad_id: str):
        page = await context.new_page()
        try:
            await page.goto(
                self._detail_url(aavid, ad_id),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(6000)
            await page.locator("#rc-tabs-0-tab-creative").wait_for(
                state="attached", timeout=int(self.timeout_seconds * 1000)
            )
        except Exception:  # noqa: BLE001
            with suppress(Exception):
                await page.close()
            return None
        return page

    async def _list_plans(self, context, aavid: str) -> list[dict]:
        """Return adInfos from the account plan-list API.

        The page fires several ``ad/list-required`` calls (some return an empty
        list first), so we collect every response for a few seconds and merge.
        """
        if not aavid:
            return []
        page = await context.new_page()
        collected: list[dict] = []

        async def on_response(response):
            if "ad/list-required" not in response.url:
                return
            if response.request.method != "POST":
                return
            try:
                payload = await response.json()
            except Exception:  # noqa: BLE001
                return
            for plan in ((payload.get("data") or {}).get("adInfos")) or []:
                if isinstance(plan, dict):
                    collected.append(plan)

        page.on("response", lambda response: asyncio.create_task(on_response(response)))
        try:
            await page.goto(
                "https://qianchuan.jinritemai.com/overall-prom"
                f"?aavid={aavid}&campaignType=1",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            for _ in range(12):
                await page.wait_for_timeout(1000)
                if collected:
                    break
            await page.wait_for_timeout(2000)
        except Exception:  # noqa: BLE001
            pass
        finally:
            with suppress(Exception):
                await page.close()

        merged: dict[str, dict] = {}
        for plan in collected:
            plan_id = str(plan.get("id") or "")
            if plan_id:
                merged.setdefault(plan_id, plan)
        return list(merged.values())

    async def _resolve_plan(self, context, aavid: str):
        """Find the detail page whose 抖音号 matches the configured live room."""
        room = self.plan_room_name
        if not room:
            return None

        candidates: list[tuple[str, str]] = []
        remembered = self._remembered_plan()
        if remembered.get("ad_id"):
            candidates.append((str(remembered["ad_id"]), "cached"))
        for plan in await self._list_plans(context, aavid):
            ad_id = str(plan.get("id") or "")
            if not ad_id:
                continue
            delivery = str(plan.get("adDeliveryName") or "")
            candidates.append((ad_id, delivery))

        seen: set[str] = set()
        for ad_id, _label in candidates:
            if ad_id in seen:
                continue
            seen.add(ad_id)
            page = await self._open_detail(context, aavid, ad_id)
            if page is None:
                continue
            text = await page.evaluate("() => document.body.innerText")
            if self._page_room_name(text) == room:
                self._remember_plan(ad_id, room)
                return page
            with suppress(Exception):
                await page.close()
        return None

    async def _ensure_target_page(self, context):
        """Open the detail page belonging to the configured live room.

        A single advertiser account can hold several 全域 plans (e.g. a paused
        flagship-store plan plus the live one). Reading whichever detail page
        happens to be open silently reports another room's materials, so when a
        room name is configured we resolve the matching plan first.
        """
        room = self.plan_room_name
        if not room:
            return await self._ensure_page(context)

        aavid = self._aavid_from_context(context)

        # 1) an already open detail page that matches the room
        for item in context.pages:
            if DETAIL_PAGE_MARKER not in (item.url or ""):
                continue
            try:
                text = await item.evaluate("() => document.body.innerText")
            except Exception:  # noqa: BLE001
                continue
            if self._page_room_name(text) == room:
                self._remember_page_url(item.url)
                self._remember_plan(self._plan_id_from_url(item.url), room)
                return item

        # 2) previously resolved plan
        remembered = self._remembered_plan()
        if remembered.get("ad_id") and aavid:
            page = await self._open_detail(context, aavid, str(remembered["ad_id"]))
            if page is not None:
                text = await page.evaluate("() => document.body.innerText")
                if self._page_room_name(text) == room:
                    self._remember_page_url(page.url)
                    return page
                with suppress(Exception):
                    await page.close()

        # 3) discover the plan that belongs to this room
        page = await self._resolve_plan(context, aavid)
        if page is not None:
            self._remember_page_url(page.url)
            return page

        raise RuntimeError(
            f"未找到「{room}」对应的投放管理计划，无法读取素材明细"
        )

    async def read(self, analysis_date: date, limit: int = 50) -> list[MaterialMetric]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(self.endpoint)
            try:
                context = browser.contexts[0]
                page = await self._ensure_target_page(context)
                try:
                    template = await self._capture_list_request(page)
                except Exception:  # noqa: BLE001
                    # page may be stale; reload once and retry
                    with suppress(Exception):
                        await page.reload(wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(6000)
                    template = await self._capture_list_request(page)
                self._remember_page_url(page.url)
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

    async def read_totals(
        self,
        analysis_date: date,
        window_start: str | None = None,
        window_end: str | None = None,
    ) -> dict:
        """账号口径的消耗汇总：整体 / 基础计划 / 追投调控。

        接口返回的 statsData.totals 是服务端聚合结果，不受分页限制。

        window_start / window_end（"YYYY-MM-DD HH:MM:SS"）用来把口径收敛到
        当前直播场次；不传则退回整天（analysis_date 00:00:00 ~ 23:59:59）。
        """
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(self.endpoint)
            try:
                context = browser.contexts[0]
                page = await self._ensure_target_page(context)
                try:
                    template = await self._capture_list_request(page)
                except Exception:  # noqa: BLE001
                    with suppress(Exception):
                        await page.reload(wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(6000)
                    template = await self._capture_list_request(page)
                body = build_material_query_body(template, analysis_date, limit=50)
                body["Metrics"] = list(MATERIAL_SPLIT_METRICS)
                if window_start:
                    body["StartTime"] = window_start
                if window_end:
                    body["EndTime"] = window_end
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
                stats = ((payload or {}).get("data") or {}).get("statsData") or {}
                totals = stats.get("totals") or {}

                def number(key: str) -> float | None:
                    value = totals.get(key)
                    if isinstance(value, dict):
                        value = value.get("value")
                    try:
                        return float(value) if value is not None else None
                    except (TypeError, ValueError):
                        return None

                total_spend = number("statCostForRoi2")
                basic_spend = number("basicStatCostForRoi2V2")
                assist_spend = number("additionalDeliveryStatCostForRoi2Assist")

                # --- 基础 / 追投调控 拆分（消耗 / ROI / 成交 / 订单）-------------
                total_gmv = number("totalPayOrderGmvIncludeCouponForRoi2")
                assist_gmv = number(
                    "additionalDeliveryTotalPayOrderGmvIncludeCouponForRoi2Assist"
                )
                total_orders = number("totalPayOrderCountForRoi2")
                assist_orders = number(
                    "additionalDeliveryTotalPayOrderCountForRoi2Assist"
                )
                # 基础口径 = 整体 - 追投调控（平台只给整体与追投两个绝对值）
                basic_gmv = (
                    total_gmv - assist_gmv
                    if total_gmv is not None and assist_gmv is not None
                    else None
                )
                basic_orders = (
                    total_orders - assist_orders
                    if total_orders is not None and assist_orders is not None
                    else None
                )
                basic_roi = (
                    basic_gmv / basic_spend
                    if basic_gmv is not None and basic_spend
                    else None
                )
                assist_roi = (
                    assist_gmv / assist_spend
                    if assist_gmv is not None and assist_spend
                    else None
                )
                total_roi = number("totalPrepayAndPayOrderRoi2")
                if total_roi is None and total_gmv is not None and total_spend:
                    total_roi = total_gmv / total_spend
                # 基础 + 追投 之外的第三块（一键调速 / 搜索抢首屏等其它调控）
                other_spend = (
                    total_spend - basic_spend - assist_spend
                    if None not in (total_spend, basic_spend, assist_spend)
                    else None
                )
                split = {
                    "basic_spend": basic_spend,
                    "assist_spend": assist_spend,
                    "total_spend": total_spend,
                    "other_spend": other_spend,
                    "basic_gmv": basic_gmv,
                    "assist_gmv": assist_gmv,
                    "total_gmv": total_gmv,
                    "basic_orders": basic_orders,
                    "assist_orders": assist_orders,
                    "total_orders": total_orders,
                    "basic_roi": basic_roi,
                    "assist_roi": assist_roi,
                    "total_roi": total_roi,
                    "split_window": {
                        "start": window_start or f"{analysis_date.isoformat()} 00:00:00",
                        "end": window_end or f"{analysis_date.isoformat()} 23:59:59",
                    },
                }
                split_complete = all(
                    split.get(key) is not None
                    for key in (
                        "basic_spend",
                        "assist_spend",
                        "total_spend",
                        "basic_gmv",
                        "assist_gmv",
                        "total_gmv",
                        "basic_roi",
                        "assist_roi",
                        "total_roi",
                    )
                )
                if not split_complete:
                    split["split_error"] = "基础/追投拆分指标不完整，本轮不展示拆分结论"
                try:
                    material_count = int(stats.get("totalCount") or 0)
                except (TypeError, ValueError):
                    material_count = 0
                materials = []
                for item in parse_material_list_response(payload):
                    materials.append(
                        {
                            "name": item.name,
                            "spend": item.spend,
                            "roi": item.roi,
                            "orders": item.orders,
                            "conversion_rate": item.conversion_rate,
                        }
                    )
                materials.sort(key=lambda row: row["spend"], reverse=True)
                return {
                    "total_spend": total_spend,
                    "basic_spend": basic_spend,
                    "assist_spend": assist_spend,
                    "material_count": material_count,
                    "materials": materials[:20],
                    "split": split,
                }
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