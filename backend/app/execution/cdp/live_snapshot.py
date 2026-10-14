import asyncio
import json
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
from websockets.asyncio.client import connect

from pathlib import Path

from app.execution.cdp.fixture_adapter import MetricSnapshot
from app.execution.cdp.page_probe import validate_cdp_endpoint

# 记住上次读成功的大屏 URL：电脑重启 / 浏览器重开后，可以照着把这一页自动开回来
LIVE_BOARD_URL_PATH = Path(__file__).resolve().parents[3] / ".local" / "live_board_url.txt"
LIVE_BOARD_ROOM_PATH = (
    Path(__file__).resolve().parents[3] / ".local" / "live_board_room.txt"
)

_NUMBER_PATTERN = r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)"


def _optional_datetime_after(text: str, label: str, timezone: ZoneInfo) -> datetime | None:
    start = text.find(label)
    if start < 0:
        return None
    tail = text[start + len(label) : start + len(label) + 100]
    match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", tail)
    if match is None:
        return None
    parsed = datetime.fromisoformat(match.group(1))
    return parsed.replace(tzinfo=timezone)


def _apply_unit(value: float, tail: str, end: int) -> float:
    """大屏对 >=100 万的数字会缩写成「112万」，这里把单位补回去。"""
    follow = tail[end : end + 2]
    if follow.startswith("亿"):
        return value * 100_000_000
    if follow.startswith("万"):
        return value * 10_000
    return value


def _number_after(text: str, label: str) -> float:
    start = text.find(label)
    if start < 0:
        raise ValueError(f"Missing required metric: {label}")
    tail = text[start + len(label) : start + len(label) + 200]
    match = re.search(_NUMBER_PATTERN, tail)
    if match is None:
        raise ValueError(f"Missing required metric: {label}")
    value = float(match.group(1).replace(",", ""))
    return _apply_unit(value, tail, match.end())


def _optional_number_after(text: str, label: str) -> float | None:
    start = text.find(label)
    if start < 0:
        return None
    tail = text[start + len(label) : start + len(label) + 200]
    match = re.search(_NUMBER_PATTERN, tail)
    if match is None:
        return None
    value = float(match.group(1).replace(",", ""))
    return _apply_unit(value, tail, match.end())


CHANNEL_PATTERN = re.compile(r"^(.+?)\s*([0-9]+(?:\.[0-9]+)?)%$")


def _traffic_sources(text: str) -> dict:
    """解析「成交渠道构成」里各渠道的占比（默认按观看次数）。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    try:
        start = lines.index("成交渠道构成")
    except ValueError:
        return {}
    result: dict[str, float] = {}
    for line in lines[start + 1 : start + 20]:
        if line in ("观看次数", "成交金额"):
            continue
        match = CHANNEL_PATTERN.match(line)
        if match:
            result[match.group(1)] = float(match.group(2))
            continue
        if result:
            break
    return result


# 大屏页面上的工具条 / 公告 / 提示文案，都不是直播间名字
_ROOM_NOISE_EXACT = {
    "刷新数据",
    "全屏",
    "公告",
    "查看详情",
    "我知道了",
    "数据口径说明",
    "整体趋势",
    "素材表现",
    "新建调控",
    "乘方投放期间",
    # 大屏的指标标签（页面不渲染标题时，这些会排在最前面）
    "综合成本(元)",
    "综合营销ROI",
    "净成交金额(元)",
    "整体成交订单数",
    "GPM(元)",
    "观看成交转化率",
    "整体成交订单成本(元)",
    "实时在线人数",
    "曝光观看率(次数)",
    "直播间整体观看人数",
    "直播间核心漏斗",
    "直播间整体曝光次数",
    "直播间观看次数",
    "商品点击次数",
    "成交订单数",
    "成交渠道构成",
    "观看次数",
    "成交金额",
    "直播实时评论",
    "直播画面",
    # 「整体趋势」图表的图例
    "综合成本",
    "净成交金额",
    "综合ROI",
    "消耗",
    "整体成交金额",
    "整体支付ROI",
}
# 「XX(元)」「XX率」「XX人数」「XX订单数」这类都算指标标签，不是直播间名
_ROOM_NOISE_PATTERN = re.compile(
    r"^[\u4e00-\u9fa5A-Za-z0-9]{2,12}(?:\(元\)|率|人数|订单数|ROI)$"
)
_ROOM_NOISE_PARTS = ("开播时间", "大屏全面升级", "点击查看详情", "数据刷新", "正在刷新")


def _is_room_noise(line: str) -> bool:
    line = line.strip()
    if not line:
        return True
    if line in _ROOM_NOISE_EXACT:
        return True
    if any(part in line for part in _ROOM_NOISE_PARTS):
        return True
    # 纯数字 / 「1 / 2」这类分页控件 / 金额、百分比
    if line.replace("/", "").replace(" ", "").isdigit():
        return True
    if re.fullmatch(r"[¥￥]?[0-9][0-9,]*(\.[0-9]+)?%?", line):
        return True
    if _ROOM_NOISE_PATTERN.match(line):
        return True
    # 纯符号（比如单独一行的「%」）也不是名字
    if not re.search(r"[0-9A-Za-z\u4e00-\u9fa5]", line):
        return True
    # 渠道占比行，如「短视频及图文引流46.99%」
    if re.search(r"[0-9]+(?:\.[0-9]+)?%$", line):
        return True
    return False


def _looks_like_room_name(name: str | None) -> bool:
    """粗判这串字像不像直播间名字（用于决定要不要记住它）。"""
    if not name:
        return False
    name = str(name).strip()
    if not (2 <= len(name) <= 30):
        return False
    if _is_room_noise(name):
        return False
    # 名字里不会有百分比 / 冒号（那些是渠道占比、评论、标签）
    if any(token in name for token in ("%", "：", ":")):
        return False
    return bool(re.search(r"[\u4e00-\u9fa5A-Za-z]", name))


def _is_live_status(line: str) -> bool:
    line = line.strip()
    return (
        line.startswith("直播中")
        or line.startswith("已结束")
        or line.startswith("未开播")
    )


def _room_name(text: str) -> str | None:
    """取直播间名字。

    大屏的文字顺序会变（有时第一行是「刷新数据」这种工具条），
    所以不能盲取第一行：优先取「直播中 X 小时」上一行，再退回第一个非噪声行。
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if not _is_live_status(line):
            continue
        for back in range(index - 1, max(-1, index - 6), -1):
            candidate = lines[back]
            if not _is_room_noise(candidate):
                return candidate
        break
    for line in lines:
        if not _is_room_noise(line):
            return line
    return None


def parse_live_board_text(
    text: str,
    captured_at: datetime | None = None,
) -> MetricSnapshot:
    return MetricSnapshot(
        captured_at=captured_at or datetime.now(UTC),
        room_name=_room_name(text),
        traffic_sources=_traffic_sources(text),
        live_started_at=_optional_datetime_after(
            text,
            "开播时间：",
            ZoneInfo("Asia/Shanghai"),
        ),
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
    """Read the live board (直播大屏) for one specific live room.

    Several ``board-next`` tabs can be open at once (e.g. today's live session
    plus yesterday's ended one, or a different account). Picking "the first
    page" therefore silently reads the wrong room. This reader scores the
    candidates by configured room id / room name and by whether the session is
    currently live, and only then reads metrics.
    """

    def __init__(
        self,
        endpoint: str,
        page_marker: str = "board-next",
        room_name: str = "",
        room_id: str = "",
        timeout_seconds: float = 10,
    ) -> None:
        self.endpoint = validate_cdp_endpoint(endpoint)
        self.page_marker = page_marker
        self.room_name = (room_name or "").strip()
        self.room_id = (room_id or "").strip()
        self.timeout_seconds = timeout_seconds

    async def refresh_board(self, target: dict) -> None:
        """点一次大屏的「刷新数据」，避免读到未更新的缓存。"""
        try:
            await self._evaluate(
                target,
                """(() => {
                    const els = [...document.querySelectorAll('*')]
                      .filter(e => (e.innerText || '').trim() === '刷新数据' && e.children.length === 0);
                    if (els.length) { els[0].click(); return 'clicked'; }
                    return 'not-found';
                })()""",
            )
        except Exception:  # noqa: BLE001
            return

    def _remember_board_url(self, url: str) -> None:
        if not url:
            return
        try:
            LIVE_BOARD_URL_PATH.parent.mkdir(parents=True, exist_ok=True)
            LIVE_BOARD_URL_PATH.write_text(url, encoding="utf-8")
        except OSError:
            return

    @staticmethod
    def _remember_room_name(name: str) -> None:
        try:
            LIVE_BOARD_ROOM_PATH.parent.mkdir(parents=True, exist_ok=True)
            LIVE_BOARD_ROOM_PATH.write_text(str(name).strip(), encoding="utf-8")
        except OSError:
            return

    @staticmethod
    def remembered_room_name() -> str | None:
        try:
            value = LIVE_BOARD_ROOM_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    @staticmethod
    def remembered_board_url() -> str | None:
        try:
            value = LIVE_BOARD_URL_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    async def read(self, refresh: bool = False) -> MetricSnapshot:
        target = await self._find_target()
        self._remember_board_url(str(target.get("url") or ""))
        if refresh:
            await self.refresh_board(target)
        text = await self._read_text(target)
        snapshot = parse_live_board_text(text)
        # 大屏页面有时不渲染直播间标题（工具条会跑到最前面），这时别抓瞎，
        # 也不要用「刷新数据」这种工具条文案顶替——沿用上次读到的名字。
        parsed = snapshot.room_name
        if _looks_like_room_name(parsed):
            self._remember_room_name(str(parsed).strip())
        # 配置里点名的直播间 = 用户指定的真相，优先用它；
        # 页面解析只作兜底（大屏有时根本不渲染标题，会抓到「刷新数据」这类工具条）。
        resolved = self.room_name or self.remembered_room_name()
        if not _looks_like_room_name(resolved):
            resolved = parsed if _looks_like_room_name(parsed) else None
        snapshot.room_name = resolved
        # 记录是哪个场次（live_room_id 每场不同）
        query = parse_qs(urlparse(str(target.get("url", ""))).query)
        snapshot.live_room_id = (query.get("live_room_id") or [None])[0]
        return snapshot

    # --- target discovery -----------------------------------------------------
    async def _candidates(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(f"{self.endpoint}/json/list")
                response.raise_for_status()
                targets = response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise RuntimeError(f"CDP target discovery failed: {exc}") from exc

        return [
            target
            for target in targets
            if target.get("type") == "page"
            and self.page_marker in str(target.get("url", ""))
            and target.get("webSocketDebuggerUrl")
        ]

    @staticmethod
    def _room_id_of(target: dict) -> str:
        query = parse_qs(urlparse(str(target.get("url", ""))).query)
        return (query.get("live_room_id") or [""])[0]

    @staticmethod
    def _headline(text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return ""

    def _score(self, target: dict, text: str) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []
        if self.room_id and self._room_id_of(target) == self.room_id:
            score += 8
            reasons.append("room_id")
        if self.room_name:
            headline = self._headline(text)
            if headline == self.room_name:
                score += 4
                reasons.append("room_name")
            elif self.room_name in text[:200]:
                score += 3
                reasons.append("room_name_partial")
        # 场次是不是还在播，比「名字对不对」更重要：
        # 名字相同的上一场大概率还开着，读到它就等于一直看冻结数据。
        opening = text[:600]
        if "直播中" in opening:
            score += 6
            reasons.append("live")
        if "已结束" in opening:
            score -= 20
            reasons.append("ended")
        return score, reasons

    @staticmethod
    def _room_id_of_url(url: str | None) -> str:
        if not url:
            return ""
        return (parse_qs(urlparse(str(url)).query).get("live_room_id") or [""])[0]

    async def _has_live_candidate(self, candidates: list[dict]) -> bool:
        """候选里有没有「正在直播」的那一场。"""
        for target in candidates:
            try:
                text = await self._read_text(target)
            except Exception:  # noqa: BLE001
                continue
            opening = text[:600]
            if "直播中" in opening and "已结束" not in opening:
                return True
        return False

    async def _open_url(self, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                await client.put(f"{self.endpoint}/json/new?{url}")
        except Exception:  # noqa: BLE001
            return False
        await asyncio.sleep(4)
        return True

    async def _open_current_board_page(self) -> bool:
        """去投放管理页点「直播大屏」，把【今天】那一场的页面开出来。"""
        url = await self._discover_board_url()
        if not url:
            return False
        target_id = self._room_id_of_url(url)
        for candidate in await self._candidates():
            if target_id and self._room_id_of(candidate) == target_id:
                return False  # 已经开着
        return await self._open_url(url)

    async def _open_board_page(self) -> bool:
        """大屏页没开着时把它开回来。

        注意顺序：**先去找当前场次**，再退回"上次记住的 URL"。
        上一场结束后如果先开记住的那个 URL，就会一直盯着已结束的场次读。
        """
        if await self._open_current_board_page():
            return True
        url = self.remembered_board_url()
        if not url:
            return False
        return await self._open_url(url)

    async def _discover_board_url(self) -> str | None:
        """拿到【当前场次】的大屏 URL。

        坑：投放管理页上的「直播大屏」按钮，打开的场次取决于那张表停在**哪一天**。
        如果它停在昨天，点出来就是昨天那场【已结束】的大屏——之前盯盘就是这么
        一直读上一场冻结数据的。所以这里先把页面切到今天，再点按钮。
        """
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _Zone

        aavid = ""
        try:
            from app.execution.cdp.material_reader import MATERIAL_PAGE_URL_PATH

            remembered = MATERIAL_PAGE_URL_PATH.read_text(encoding="utf-8").strip()
            aavid = (parse_qs(urlparse(remembered).query).get("aavid") or [""])[0]
        except (OSError, Exception):  # noqa: BLE001
            aavid = ""
        today = _dt.now(_Zone("Asia/Shanghai")).strftime("%Y-%m-%d")
        target = "https://qianchuan.jinritemai.com/overall-prom?campaignType=1"
        if aavid:
            target += f"&aavid={aavid}"
        # 只要日期，别带了一堆旧的筛选参数
        target += f"&dateRange={today}%2C{today}"
        try:
            from playwright.async_api import async_playwright
        except Exception:  # noqa: BLE001
            return None
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(self.endpoint)
                try:
                    context = browser.contexts[0]
                    page = next(
                        (
                            item
                            for item in context.pages
                            if "overall-prom" in (item.url or "")
                            and "detail" not in (item.url or "")
                        ),
                        None,
                    )
                    if page is None:
                        page = await context.new_page()
                    # 切到今天，否则点出来的还是旧场次
                    if today not in (page.url or ""):
                        await page.goto(target, wait_until="domcontentloaded", timeout=60000)
                    # 表格要等接口回来才渲染出「直播大屏」标签，给足时间
                    try:
                        await page.wait_for_selector("text=直播大屏", timeout=25000)
                    except Exception:  # noqa: BLE001
                        return None
                    # 这个标签有时被加载遮罩挡住，Playwright 的 click 会等超时；
                    # 直接用 JS 触发点击（React 的 onClick 照样会响应）。
                    async with page.expect_popup(timeout=20000) as popup_info:
                        clicked = await page.evaluate(
                            """() => {
                                const nodes = [...document.querySelectorAll('span,div,a')];
                                const hit = nodes.find(
                                  (e) => (e.innerText || '').trim() === '直播大屏'
                                );
                                if (!hit) return false;
                                hit.click();
                                return true;
                            }"""
                        )
                    if not clicked:
                        return None
                    popup = await popup_info.value
                    await popup.wait_for_load_state("domcontentloaded")
                    await popup.wait_for_timeout(2500)
                    url = popup.url or ""
                    if "board-next" in url and "live_room_id" in url:
                        return url
                    return None
                finally:
                    await playwright.stop()
        except Exception:  # noqa: BLE001
            return None

    async def _find_target(self) -> dict:
        candidates = await self._candidates()
        # 手上有大屏页，但全是「已结束」的上一场 → 去把今天这场开出来
        if candidates and not await self._has_live_candidate(candidates):
            if await self._open_current_board_page():
                fresh = await self._candidates()
                if fresh:
                    candidates = fresh
        if not candidates and await self._open_board_page():
            candidates = await self._candidates()
        if not candidates:
            raise RuntimeError(f"CDP page not found for marker: {self.page_marker}")
        if len(candidates) == 1:
            return candidates[0]

        best = candidates[0]
        best_score: float | None = None
        for target in candidates:
            try:
                text = await self._read_text(target)
            except Exception:  # noqa: BLE001
                text = ""
            score, _ = self._score(target, text)
            if best_score is None or score > best_score:
                best, best_score = target, score
        return best

    # --- CDP plumbing ---------------------------------------------------------
    async def _evaluate(self, target: dict, expression: str) -> str:
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
                                "expression": expression,
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

    async def _read_text(self, target: dict) -> str:
        return await self._evaluate(target, "document.body.innerText")


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
