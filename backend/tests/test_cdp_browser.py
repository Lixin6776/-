import pytest

from app.execution.cdp.browser import CdpBrowserGateway


class FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakePlaywright:
    def __init__(self) -> None:
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_cdp_gateway_close_disconnects_without_closing_browser():
    gateway = CdpBrowserGateway("http://127.0.0.1:9222")
    browser = FakeBrowser()
    playwright = FakePlaywright()
    gateway.browser = browser
    gateway._playwright = playwright

    await gateway.close()

    assert browser.closed is False
    assert playwright.stopped is True
    assert gateway.browser is None
