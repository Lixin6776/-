from playwright.async_api import Browser, Playwright, async_playwright


class CdpBrowserGateway:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self._playwright: Playwright | None = None
        self.browser: Browser | None = None

    async def connect(self) -> Browser:
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.connect_over_cdp(self.endpoint)
        return self.browser

    async def close(self) -> None:
        if self.browser is not None:
            await self.browser.close()
        if self._playwright is not None:
            await self._playwright.stop()