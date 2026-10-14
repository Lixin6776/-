"""读取千川「投放管理 → 详情 → 日志」里的平台操作记录。

这块日志记录的是**在千川平台上真实发生的操作**（含人工操作和其他工具），
比我们自己的执行记录更完整，所以盯盘报表要把它一起读进来。
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

from app.execution.cdp.page_probe import validate_cdp_endpoint

DETAIL_PAGE_MARKER = "overall-prom/detail"
ENTRY_HEADER = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\S+)$")
NOISE_PREFIXES = (
    "操作内容",
    "操作时间",
    "操作类型",
    "操作人",
    "操作来源",
    "操作IP",
    "请选择",
)


def parse_plan_log_text(text: str, limit: int = 20) -> list[dict]:
    """把日志 tab 的正文解析成 [{time, type, summary, details}]。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries: list[dict] = []
    current: dict | None = None

    for line in lines:
        header = ENTRY_HEADER.match(line)
        if header:
            if current is not None:
                entries.append(current)
            current = {
                "time": header.group(1),
                "type": header.group(2),
                "details": [],
            }
            continue
        if current is None:
            continue
        if any(line.startswith(prefix) for prefix in NOISE_PREFIXES) and "：" not in line:
            continue
        if line == "日志" or line == "保障历史":
            continue
        # 操作人 / 来源行不算操作内容
        if "千川用户" in line or line.startswith("千川平台"):
            continue
        current["details"].append(line)

    if current is not None:
        entries.append(current)

    for entry in entries:
        parts = entry["details"]
        entry["summary"] = "；".join(parts[:4]) if parts else entry["type"]
    return entries[:limit]


class CdpPlanLogReader:
    def __init__(self, endpoint: str, timeout_seconds: float = 12) -> None:
        self.endpoint = validate_cdp_endpoint(endpoint)
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def with_date_range(url: str, day: str) -> str:
        """把详情页 URL 的日期筛选改成指定日期（保留其它参数）。"""
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["dateRange"] = f"{day},{day}"
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    async def read_recent(self, limit: int = 10, day: str | None = None) -> list[dict]:
        """读「详情 → 日志」。

        坑：日志 tab 的内容跟着页面上的**日期筛选**走。页面停在昨天，
        读到的就是昨天的操作——而且界面上只显示 HH:MM:SS，看着像今天的。
        所以读之前先强制把日期切到今天。
        """
        target_day = day or datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(self.endpoint)
            try:
                context = browser.contexts[0]
                page = next(
                    (
                        item
                        for item in context.pages
                        if DETAIL_PAGE_MARKER in (item.url or "")
                    ),
                    None,
                )
                if page is None:
                    return []
                # 页面不在今天 → 先切到今天，否则读到的是旧日期的日志
                if target_day not in (page.url or ""):
                    try:
                        await page.goto(
                            self.with_date_range(page.url, target_day),
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                        await page.wait_for_timeout(3500)
                    except Exception:  # noqa: BLE001
                        return []
                try:
                    await page.get_by_text("日志", exact=True).first.click(
                        timeout=int(self.timeout_seconds * 1000)
                    )
                    await page.wait_for_timeout(3500)
                except Exception:  # noqa: BLE001
                    return []
                text = await page.evaluate("() => document.body.innerText")
                entries = parse_plan_log_text(text, limit=limit)
                for entry in entries:
                    entry["day"] = str(entry.get("time") or "")[:10]
                return entries
            finally:
                await playwright.stop()
