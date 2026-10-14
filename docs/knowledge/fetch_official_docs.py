# -*- coding: utf-8 -*-
"""自动抓取巨量千川帮助中心官方文档（经飞书 iframe 渲染后读取）。

原理：帮助中心把正文放在 bytedance.larkoffice.com 的跨域 iframe 里，
Playwright 可以跨域访问 frame，等飞书文档渲染完成后直接读 innerText。
"""
import asyncio, io, json, re, sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TARGETS = [
    ("142504", "全域投放数据指标说明"),
    ("140157", "直播全域投放GMV最大化逻辑"),
    ("140639", "全域投放-推直播间问题自查SOP"),
    ("140638", "直播全域投放有问题怎么调整"),
    ("192107", "净成交出价-素材评估思路"),
    ("142518", "推商品投放问题自查SOP"),
]
TEMPLATE = "https://support.oceanengine.com/support/content/{id}?pageId=221&spaceId=122"
OUT = Path(r"D:\qianchuan-ai-assistant\.local\official_docs")
OUT.mkdir(parents=True, exist_ok=True)


async def grab(ctx, doc_id: str, name: str) -> str:
    page = await ctx.new_page()
    best = ""
    try:
        await page.goto(TEMPLATE.format(id=doc_id), wait_until="domcontentloaded", timeout=90000)
        stagnant = 0
        for _ in range(16):
            await page.wait_for_timeout(4000)
            for fr in page.frames:
                if "larkoffice.com" not in (fr.url or ""):
                    continue
                try:
                    t = await fr.evaluate("() => document.body ? document.body.innerText : ''")
                except Exception:
                    continue
                if t and len(t) > len(best):
                    best = t
            if len(best) > 500:
                if stagnant >= 2:
                    break
                stagnant += 1
            if len(best) > 20000:
                break
        text = re.sub(r"\n{3,}", "\n\n", best).strip()
        (OUT / f"{doc_id}_{name}.txt").write_text(text, encoding="utf-8")
        print(f"{doc_id} {name}: {len(text)} 字", flush=True)
        return text
    finally:
        await page.close()


async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = b.contexts[0]
        for doc_id, name in TARGETS:
            try:
                await grab(ctx, doc_id, name)
            except Exception as exc:
                print(f"{doc_id} {name}: FAIL {str(exc)[:80]}", flush=True)
            await asyncio.sleep(2)
        await b.close()

asyncio.run(main())
