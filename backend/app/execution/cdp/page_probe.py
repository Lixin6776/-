from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.execution.cdp.browser import CdpBrowserGateway


def validate_cdp_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("CDP endpoint must use loopback host")
    return endpoint.rstrip("/")


@dataclass(frozen=True)
class ProbeArtifact:
    page_url: str
    html_path: Path
    screenshot_path: Path


class PageProbe:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = validate_cdp_endpoint(endpoint)

    async def capture(self, page_url: str, output_dir: Path) -> ProbeArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        gateway = CdpBrowserGateway(self.endpoint)
        try:
            browser = await gateway.connect()
            context = browser.contexts[0]
            page = next((item for item in context.pages if page_url in item.url), context.pages[0])
            html_path = output_dir / "page.html"
            screenshot_path = output_dir / "page.png"
            html_path.write_text(await page.content(), encoding="utf-8")
            await page.screenshot(path=str(screenshot_path), full_page=True)
            return ProbeArtifact(page.url, html_path, screenshot_path)
        finally:
            await gateway.close()