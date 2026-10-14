"""读取投放管理页的「基础 vs 整体」拆分数据。

官方页面把每条计划分成：
  整体（含调控/追投） vs 基础（仅基础投放）
这是判断"调控/追投是否拖累账户"的最硬证据。
"""
import re

PLAN_BLOCK = re.compile(
    r"(?P<room>[^\n\t]{2,40})\n修改直播规划\n素材\n(?P<status>投放中|已暂停|审核中|已删除)",
)

NUMBER = r"([0-9][0-9,]*(?:\.[0-9]+)?)"


def parse_plan_splits(text: str) -> list[dict]:
    """从投放管理页正文里解析每条计划的 基础/整体 指标。"""
    lines = [l.strip() for l in text.splitlines()]
    results: list[dict] = []
    for i, line in enumerate(lines):
        if line != "乘方投放" and line != "全域投放":
            continue
        # 往前找抖音号
        room = None
        for j in range(i - 1, max(0, i - 80), -1):
            if lines[j] == "修改直播规划":
                room = lines[j - 1]
                break
        if not room:
            continue
        tail = lines[i + 1 : i + 40]
        def pick(offset: int) -> float | None:
            try:
                return float(tail[offset].replace(",", ""))
            except (IndexError, ValueError):
                return None
        def pick_base(offset: int) -> float | None:
            try:
                raw = tail[offset]
                raw = raw.replace("基础 ", "").replace(",", "")
                return float(raw)
            except (IndexError, ValueError):
                return None
        block = tail[:30]
        entry = {"room": room, "type": line}
        # 找 "基础 x" 的行，取它前面那个数值作为整体值
        for k, v in enumerate(block):
            if v.startswith("基础 ") and k > 0:
                try:
                    overall = float(block[k - 1].replace(",", ""))
                    base = float(v.replace("基础 ", "").replace(",", ""))
                except ValueError:
                    continue
                if "roi" not in entry:
                    entry["roi"] = overall
                    entry["base_roi"] = base
                elif "spend" not in entry:
                    entry["spend"] = overall
                    entry["base_spend"] = base
                elif "gmv" not in entry:
                    entry["gmv"] = overall
                    entry["base_gmv"] = base
        if entry.get("roi") is not None:
            results.append(entry)
    return results


class CdpPlanSplitReader:
    """从千川「投放管理页」读取每条计划的基础/整体拆分。"""

    LIST_PAGE_MARKER = "overall-prom"

    def __init__(
        self,
        endpoint: str,
        aavid: str | None = None,
        timeout_seconds: float = 12,
    ) -> None:
        from app.config import settings
        from app.execution.cdp.page_probe import validate_cdp_endpoint

        self.endpoint = validate_cdp_endpoint(endpoint)
        self.aavid = aavid or settings.aavid or self._remembered_aavid()
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _remembered_aavid() -> str:
        """从上次记住的投放管理页 URL 里取出账户 ID（没有就不带，避免写死账号）。"""
        from urllib.parse import parse_qs, urlparse

        from app.execution.cdp.material_reader import MATERIAL_PAGE_URL_PATH

        try:
            url = MATERIAL_PAGE_URL_PATH.read_text(encoding="utf-8")
        except OSError:
            return ""
        return str((parse_qs(urlparse(url).query).get("aavid") or [""])[0])

    async def read(self) -> list[dict]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(self.endpoint)
            try:
                context = browser.contexts[0]
                page = next(
                    (
                        item
                        for item in context.pages
                        if self.LIST_PAGE_MARKER in (item.url or "")
                        and "detail" not in (item.url or "")
                    ),
                    None,
                )
                if page is None:
                    page = await context.new_page()
                    await page.goto(
                        "https://qianchuan.jinritemai.com/overall-prom"
                        f"?aavid={self.aavid}&campaignType=1",
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                await page.wait_for_timeout(6000)
                text = await page.evaluate("() => document.body.innerText")
                return parse_plan_splits(text)
            finally:
                await playwright.stop()
