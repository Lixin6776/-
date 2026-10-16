# -*- coding: utf-8 -*-
"""数据源连接：检测千川调试浏览器（CDP）是否在线，并提供「一键连接 / 重连」。

背景：
    盯盘的数据都来自本机 9222 端口上的调试版 Chrome。电脑关机 / 浏览器被关掉后，
    这个端口就没了，盯盘会静默地读不到数据。这里负责：
      1) 探测端口是否在线（含开了几个千川页面）；
      2) 不在线时把调试版 Chrome 拉起来，并等它就绪；
      3) 返回「是否需要首次登录」等人话提示，给前端直接用。
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

QIANCHUAN_URL = "https://qianchuan.jinritemai.com/"

# 上次读成功过的页面 URL：重开浏览器后照着开回来，不然盯盘找不到大屏页面
LOCAL_DIR = Path(__file__).resolve().parents[3] / ".local"
REMEMBERED_PAGE_FILES = ("live_board_url.txt", "material_page_url.txt")


def remembered_pages() -> list[str]:
    urls: list[str] = []
    for name in REMEMBERED_PAGE_FILES:
        try:
            value = (LOCAL_DIR / name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value and "qianchuan.jinritemai.com" in value:
            urls.append(value)
    return urls


async def ensure_pages(endpoint: str, urls: list[str] | None = None) -> list[str]:
    """把记住的千川页面开回来（已经开着的不重复开）。返回实际打开的数量。"""
    wanted = urls if urls is not None else remembered_pages()
    if not wanted:
        return []
    opened: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            listing = await client.get(f"{endpoint}/json/list")
            existing = [
                str(item.get("url") or "")
                for item in (listing.json() if listing.status_code == 200 else [])
            ]
            for url in wanted:
                key = url.split("#")[0].split("?")[0]
                if any(key and key in page for page in existing):
                    continue
                try:
                    # Chrome 111+ 要求用 PUT 调 /json/new
                    await client.put(f"{endpoint}/json/new?{url}")
                    opened.append(url)
                    existing.append(url)
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        return opened
    return opened


def _chrome_executable():
    candidates = [
        Path(os.environ.get("PROGRAMFILES") or r"C:\Program Files")
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)") or r"C:\Program Files (x86)")
        / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA") or "")
        / "Google/Chrome/Application/chrome.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def default_profile_dir() -> Path:
    """用户平时那个 Chrome 的 user-data-dir（带千川登录态）。"""
    return Path(os.environ.get("LOCALAPPDATA") or "") / "Google/Chrome/User Data"


def assistant_profile_dir() -> Path:
    """助手专用 profile（和日常浏览互不影响，登录态持久保存）。"""
    return Path(os.environ.get("LOCALAPPDATA") or "") / "QianchuanAssistantChrome"


def port_of(endpoint: str) -> int:
    parsed = urlparse(endpoint)
    return parsed.port or 9222


def _profile_has_login(profile: Path) -> bool:
    return (profile / "Default" / "Cookies").is_file() or (
        profile / "Default" / "Network" / "Cookies"
    ).is_file()


def _chrome_running() -> bool:
    """有没有 chrome.exe 在跑（用默认 profile 的普通 Chrome 也算）。"""
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "chrome.exe" in (out or "").lower()


async def probe(endpoint: str, timeout: float = 4.0) -> dict:
    """探测 CDP 端口。永远返回结果，不抛异常。"""
    result = {
        "endpoint": endpoint,
        "connected": False,
        "browser": None,
        "pages": 0,
        "qianchuan_pages": 0,
        "login_pages": 0,
        "error": None,
    }
    try:
        # trust_env=False：本机 127.0.0.1 不走系统/环境里的代理，
        # 否则会被 Clash 之类的代理拦成 502，误判成「端口在线」。
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            version = await client.get(f"{endpoint}/json/version")
            version.raise_for_status()
            info = version.json()
            result["connected"] = True
            result["browser"] = str(info.get("Browser") or "")
            targets = await client.get(f"{endpoint}/json/list")
            targets.raise_for_status()
            pages = [item for item in targets.json() if item.get("type") == "page"]
            result["pages"] = len(pages)
            result["qianchuan_pages"] = sum(
                1
                for item in pages
                if "qianchuan.jinritemai.com" in str(item.get("url") or "")
            )
            # 落在登录页 = 这个浏览器还没登录千川，光连上端口读不到数据
            result["login_pages"] = sum(
                1
                for item in pages
                if "login" in str(item.get("url") or "").lower()
            )
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def connect(
    endpoint: str,
    url: str = QIANCHUAN_URL,
    wait_seconds: float = 25.0,
    mode: str = "auto",
) -> dict:
    """确保调试浏览器在线：已在线直接返回；否则拉起 Chrome 再等它就绪。

    mode:
        auto      没开 Chrome -> 用平时那个 profile（登录态直接复用）；
                  已经开着 Chrome -> 退回助手专用 profile（独立实例，能带调试端口）
        default   只用平时那个 profile。Chrome 已开着时没法补调试端口，
                  返回 needs_chrome_restart=True，让用户先关掉 Chrome
        assistant 只用助手专用 profile（和日常浏览互不影响）
    """
    status = await probe(endpoint)
    status.update(
        {
            "launched": False,
            "chrome_found": True,
            "profile": None,
            "profile_kind": None,
            "needs_login": False,
            "needs_chrome_restart": False,
            "mode_used": mode,
            "opened_pages": [],
            "message": "",
        }
    )
    if status["connected"]:
        status["opened_pages"] = await ensure_pages(endpoint)
        # 浏览器里可能同时留着一个 /login 标签（历史遗留），但千川页面是正常登录的。
        # 只有"有登录页 **且** 一个千川页都没有"时，才算真的没登录 —— 否则会误报"需要登录千川"。
        status["needs_login"] = bool(status.get("login_pages")) and not status.get(
            "qianchuan_pages"
        )
        status["message"] = (
            "数据源已连接"
            if not status["needs_login"]
            else "浏览器已连上，但还没登录千川：请在弹出的窗口里登录一次，"
            "登录后点「恢复盯盘」即可"
        )
        return status

    chrome = _chrome_executable()
    if chrome is None:
        status["chrome_found"] = False
        status["message"] = "没找到 Chrome（chrome.exe）。请先装 Google Chrome，再点连接。"
        return status

    running = await asyncio.to_thread(_chrome_running)
    if mode == "assistant":
        profile, kind = assistant_profile_dir(), "assistant"
    elif mode == "default":
        profile, kind = default_profile_dir(), "default"
    elif not running and default_profile_dir().is_dir():
        # Chrome 没在跑：直接用平时那个 profile 起，千川登录态直接复用
        profile, kind = default_profile_dir(), "default"
    else:
        # Chrome 已经开着（没法给它补调试端口）：用助手专用 profile 起独立实例
        profile, kind = assistant_profile_dir(), "assistant"
    status["mode_used"] = kind

    if kind == "default" and running:
        # 同一个 user-data-dir 已经有 Chrome 在跑，新进程只会把命令行转给它，
        # 调试端口不会打开——必须先完全退出 Chrome。
        status["needs_chrome_restart"] = True
        status["message"] = (
            "Chrome 正在运行，没法给它打开调试端口。"
            "要么先完全退出 Chrome（托盘也退掉）再点连接，"
            "要么点「用独立浏览器连接」（需要登录一次千川，之后一直有效）。"
        )
        return status

    profile.mkdir(parents=True, exist_ok=True)
    args = [
        chrome,
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port_of(endpoint)}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        subprocess.Popen(args, close_fds=True, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        status["message"] = f"拉起 Chrome 失败：{exc}"
        return status

    status["launched"] = True
    status["profile"] = str(profile)
    status["profile_kind"] = kind
    status["needs_login"] = kind == "assistant" and not _profile_has_login(profile)

    deadline = asyncio.get_event_loop().time() + wait_seconds
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(1.5)
        current = await probe(endpoint, timeout=3.0)
        if current["connected"]:
            status.update(current)
            status["launched"] = True
            status["profile"] = str(profile)
            status["profile_kind"] = kind
            status["opened_pages"] = await ensure_pages(endpoint)
            status["needs_login"] = bool(current.get("login_pages"))
            if not status["needs_login"] and kind == "assistant":
                status["needs_login"] = not _profile_has_login(profile)
            status["message"] = (
                "数据源已连接"
                if not status["needs_login"]
                else "浏览器已连上，但还没登录千川：请在弹出的窗口里登录一次，"
                "登录后点「恢复盯盘」即可"
            )
            return status

    status["message"] = (
        "已经拉起 Chrome，但 9222 端口还没就绪。"
        "如果弹出的窗口在等你登录千川，登录完成后点一次「连接数据源」即可。"
    )
    return status
