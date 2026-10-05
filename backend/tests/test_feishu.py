import json

import httpx

from app.services.feishu import (
    FeishuConfig,
    FeishuConfigStore,
    FeishuNotifier,
    build_feishu_card,
)


def test_feishu_config_store_masks_secret(tmp_path):
    store = FeishuConfigStore(tmp_path / "feishu.json")
    store.save(
        FeishuConfig(
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/abcdef123456",
            secret="super-secret",
            enabled=True,
        )
    )

    status = store.status()

    assert status["configured"] is True
    assert status["enabled"] is True
    assert status["secret_configured"] is True
    assert "secret" not in status
    assert "super-secret" not in json.dumps(status, ensure_ascii=False)
    assert "abcdef123456" not in json.dumps(status, ensure_ascii=False)


def test_build_feishu_card_uses_report_header_and_content():
    card = build_feishu_card(
        "## 直播复盘｜2026-10-05\n\n### 一、核心结果\n\n- 综合成本：¥100.00\n"
        "- 是否达标：未达标",
        report_type="live_review",
    )

    assert card["header"]["title"]["content"] == "直播复盘｜2026-10-05"
    assert card["header"]["template"] == "red"
    assert "未达标" in json.dumps(card, ensure_ascii=False)
    assert any(element.get("tag") == "collapsible_panel" for element in card["body"]["elements"])


def test_feishu_notifier_sends_card_once(tmp_path):
    received = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    store = FeishuConfigStore(tmp_path / "feishu.json")
    store.save(
        FeishuConfig(
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test",
            enabled=True,
            auto_send_live_review=True,
        )
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        notifier = FeishuNotifier(
            store,
            sent_path=tmp_path / "feishu_sent.json",
            client=client,
        )
        review = {
            "id": "review-1",
            "report_markdown": "## 直播复盘｜2026-10-05\n\n- 是否达标：达标",
        }

        assert notifier.send_live_review(review) is True
        assert notifier.send_live_review(review) is False

    assert len(received) == 1
    assert received[0]["msg_type"] == "interactive"
    assert received[0]["card"]["header"]["template"] == "green"
