import json
from pathlib import Path

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


class FakeLarkRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, args, cwd=None, timeout=120):
        self.calls.append(list(args))
        if len(args) >= 2 and args[0] == "auth" and args[1] == "qrcode":
            output_index = args.index("--output") + 1
            output_path = (Path(cwd) if cwd else Path(".")) / args[output_index]
            output_path.write_bytes(b"fake-png")
            return {"ok": True}
        return self.run_json(args, cwd=cwd)

    def run_json(self, args, cwd=None, timeout=120):
        self.calls.append(list(args))
        if not self.responses:
            raise AssertionError(f"unexpected lark-cli call: {args}")
        return self.responses.pop(0)


def test_feishu_qr_login_starts_device_flow(tmp_path):
    from app.services.feishu import FeishuQrAuthService

    store = FeishuConfigStore(tmp_path / "feishu.json")
    runner = FakeLarkRunner(
        [
            {
                "device_code": "device-123",
                "verification_url": "https://accounts.feishu.cn/oauth/v1/device/verify?flow_id=x",
                "expires_in": 600,
            }
        ]
    )
    service = FeishuQrAuthService(store, runner=runner, qr_dir=tmp_path)

    state = service.start_login(start_polling=False)

    assert state["status"] == "pending"
    assert state["verification_url"].startswith("https://accounts.feishu.cn/")
    assert state["qr_data_url"].startswith("data:image/png;base64,")
    assert any(call[:2] == ["auth", "qrcode"] for call in runner.calls)
    auth_call = next(call for call in runner.calls if call[:2] == ["auth", "login"])
    assert "--scope" in auth_call
    assert "im:message.send_as_user" in auth_call[auth_call.index("--scope") + 1]


def test_feishu_qr_login_completion_creates_group(tmp_path):
    from app.services.feishu import FeishuQrAuthService

    store = FeishuConfigStore(tmp_path / "feishu.json")
    runner = FakeLarkRunner(
        [
            {
                "ok": True,
                "data": {
                    "chat_id": "oc_qianchuan",
                    "name": "千川 AI 投放助手",
                    "share_link": "https://applink.feishu.cn/client/chat/open?openChatId=oc_qianchuan",
                },
            }
        ]
    )
    service = FeishuQrAuthService(store, runner=runner, qr_dir=tmp_path)
    service.device_code = "device-123"

    state = service.complete_login(
        "device-123",
        auth_result={"ok": True, "data": {"open_id": "ou_user", "name": "李鑫"}},
    )

    assert state["status"] == "connected"
    assert state["chat_id"] == "oc_qianchuan"
    assert state["chat_name"] == "千川 AI 投放助手"
    saved = store.load()
    assert saved.connection_mode == "qr"
    assert saved.chat_id == "oc_qianchuan"
    assert saved.enabled is True
    assert any(call[:2] == ["im", "+chat-create"] for call in runner.calls)


def test_feishu_notifier_sends_qr_card_via_lark_cli(tmp_path):
    store = FeishuConfigStore(tmp_path / "feishu.json")
    store.save(
        FeishuConfig(
            connection_mode="qr",
            chat_id="oc_qianchuan",
            chat_name="千川 AI 投放助手",
            enabled=True,
            auto_send_live_review=True,
        )
    )
    runner = FakeLarkRunner([{"ok": True, "data": {"message_id": "om_1"}}])
    notifier = FeishuNotifier(store, sent_path=tmp_path / "sent.json", lark_runner=runner)

    assert notifier.send_live_review(
        {"id": "review-qr", "report_markdown": "## 直播复盘｜2026-10-05\n\n- 是否达标：达标"}
    ) is True
    assert runner.calls[0][:2] == ["im", "+messages-send"]
    assert "--chat-id" in runner.calls[0]


def test_feishu_qr_login_reuses_existing_group(tmp_path):
    from app.services.feishu import FeishuQrAuthService

    store = FeishuConfigStore(tmp_path / "feishu.json")
    store.save(
        FeishuConfig(
            connection_mode="qr",
            chat_id="oc_existing",
            chat_name="千川 AI 投放助手",
            enabled=True,
        )
    )
    runner = FakeLarkRunner([])
    service = FeishuQrAuthService(store, runner=runner, qr_dir=tmp_path)

    state = service.complete_login(
        "device-123",
        auth_result={"ok": True, "data": {"open_id": "ou_user", "name": "李鑫"}},
    )

    assert state["status"] == "connected"
    assert state["chat_id"] == "oc_existing"
    assert not any(call[:2] == ["im", "+chat-create"] for call in runner.calls)
