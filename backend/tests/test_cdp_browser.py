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


@pytest.mark.asyncio
async def test_connect_login_tab_does_not_false_alarm(monkeypatch):
    """浏览器里留着一个 /login 标签，但千川页正常 → 不能误报「需要登录千川」。"""
    from app.services import cdp_connection as conn

    async def fake_probe(endpoint, timeout=4.0):
        return {
            "endpoint": endpoint,
            "connected": True,
            "browser": "Chrome/155",
            "pages": 3,
            "qianchuan_pages": 3,
            "login_pages": 1,
            "error": None,
        }

    async def fake_ensure(endpoint, urls=None):
        return []

    monkeypatch.setattr(conn, "probe", fake_probe)
    monkeypatch.setattr(conn, "ensure_pages", fake_ensure)

    status = await conn.connect("http://127.0.0.1:9222")
    assert status["needs_login"] is False


@pytest.mark.asyncio
async def test_connect_reports_login_when_no_qianchuan_pages(monkeypatch):
    """真没登录：只有登录页、一个千川页都没有 → 要提示登录。"""
    from app.services import cdp_connection as conn

    async def fake_probe(endpoint, timeout=4.0):
        return {
            "endpoint": endpoint,
            "connected": True,
            "browser": "Chrome/155",
            "pages": 1,
            "qianchuan_pages": 0,
            "login_pages": 1,
            "error": None,
        }

    async def fake_ensure(endpoint, urls=None):
        return []

    monkeypatch.setattr(conn, "probe", fake_probe)
    monkeypatch.setattr(conn, "ensure_pages", fake_ensure)

    status = await conn.connect("http://127.0.0.1:9222")
    assert status["needs_login"] is True
