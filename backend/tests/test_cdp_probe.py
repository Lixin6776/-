from pathlib import Path

import pytest

from app.execution.cdp.page_probe import PageProbe, validate_cdp_endpoint


def test_cdp_endpoint_must_be_loopback():
    with pytest.raises(ValueError):
        validate_cdp_endpoint("http://0.0.0.0:9222")


def test_cdp_endpoint_accepts_loopback():
    assert validate_cdp_endpoint("http://127.0.0.1:9222") == "http://127.0.0.1:9222"


class FakePage:
    url = "https://qianchuan.jinritemai.com/dashboard"

    async def content(self):
        return "<html>qianchuan</html>"

    async def screenshot(self, path, full_page):
        assert full_page is True
        Path(path).write_bytes(b"png")


class FakeContext:
    pages = [FakePage()]


class FakeBrowser:
    contexts = [FakeContext()]


class FakeGateway:
    def __init__(self, endpoint):
        assert endpoint == "http://127.0.0.1:9222"
        self.closed = False

    async def connect(self):
        return FakeBrowser()

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_page_probe_captures_html_and_screenshot(tmp_path, monkeypatch):
    monkeypatch.setattr("app.execution.cdp.page_probe.CdpBrowserGateway", FakeGateway)
    artifact = await PageProbe("http://127.0.0.1:9222").capture("qianchuan", tmp_path)
    assert artifact.page_url.startswith("https://qianchuan.")
    assert artifact.html_path.read_text(encoding="utf-8") == "<html>qianchuan</html>"
    assert artifact.screenshot_path.read_bytes() == b"png"