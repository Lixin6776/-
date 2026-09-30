from collections.abc import Awaitable, Callable
from pathlib import Path

from app.execution.cdp.browser import CdpBrowserGateway
from app.execution.cdp.page_adapter import QianchuanPageAdapter
from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.cdp.selector_config import SelectorConfig


async def create_cdp_execution_provider(
    endpoint: str,
    selector_path: Path,
) -> tuple[CdpExecutionProvider, Callable[[], Awaitable[None]]]:
    if not selector_path.exists():
        raise RuntimeError("selector calibration required")
    gateway = CdpBrowserGateway(endpoint)
    browser = await gateway.connect()
    context = browser.contexts[0]
    page = next((item for item in context.pages if "qianchuan" in item.url), context.pages[0])
    adapter = QianchuanPageAdapter(page, SelectorConfig.load(selector_path))

    async def close() -> None:
        await gateway.close()

    return CdpExecutionProvider(adapter), close