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
        # The debug browser belongs to the user. Stopping Playwright disconnects
        # from it without terminating the user's Chrome/Edge process.
        if self._playwright is not None:
            await self._playwright.stop()
        self.browser = None
        self._playwright = None
