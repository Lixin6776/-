import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

FEISHU_CONFIG_PATH = Path(__file__).resolve().parents[3] / ".local" / "feishu_config.json"
FEISHU_SENT_PATH = Path(__file__).resolve().parents[3] / ".local" / "feishu_sent.json"


class FeishuConfig(BaseModel):
    webhook_url: str = ""
    secret: str = ""
    enabled: bool = False
    auto_send_live_review: bool = True
    auto_send_material_analysis: bool = True
    last_sent_at: str = ""
    last_error: str = ""


def _mask_webhook(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return "****"
    return f"{parsed.scheme}://{parsed.netloc}/.../hook/****"


def _report_title(markdown: str, report_type: str) -> str:
    for line in markdown.splitlines():
        candidate = line.strip()
        if candidate.startswith("## "):
            return candidate[3:].strip()
        if candidate.startswith("# "):
            return candidate[2:].strip()
    return "直播复盘" if report_type == "live_review" else "素材分析报告"


def _report_status(markdown: str) -> tuple[str, str]:
    if "是否达标：未达标" in markdown:
        return "red", "未达标"
    if "是否达标：达标" in markdown:
        return "green", "达标"
    return "blue", "观察"


def build_feishu_card(
    report_markdown: str,
    report_type: str,
    generated_at: datetime | None = None,
) -> dict:
    title = _report_title(report_markdown, report_type)
    template, status_text = _report_status(report_markdown)
    time_text = (generated_at or datetime.now(UTC)).astimezone().strftime("%Y-%m-%d %H:%M")
    panel_title = "查看完整直播复盘" if report_type == "live_review" else "查看完整素材分析"
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {"tag": "plain_text", "content": f"千川本地 AI 投放助手 · {time_text}"},
            "template": template,
            "text_tag_list": [
                {
                    "tag": "text_tag",
                    "text": {"tag": "plain_text", "content": status_text},
                    "color": template,
                }
            ],
        },
        "body": {
            "elements": [
                {
                    "tag": "collapsible_panel",
                    "expanded": False,
                    "header": {
                        "title": {"tag": "plain_text", "content": panel_title}
                    },
                    "elements": [
                        {"tag": "markdown", "content": report_markdown[:20000]}
                    ],
                },
                {"tag": "hr"},
                {
                    "tag": "markdown",
                    "content": "**执行提醒**\n所有预算、出价、计划和素材调整都必须人工确认后执行。",
                    "text_size": "notation",
                },
            ]
        },
    }


class FeishuConfigStore:
    def __init__(self, path: Path = FEISHU_CONFIG_PATH) -> None:
        self.path = path

    def load(self) -> FeishuConfig:
        if not self.path.exists():
            return FeishuConfig()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return FeishuConfig()
        try:
            return FeishuConfig.model_validate(payload)
        except ValueError:
            return FeishuConfig()

    def save(self, config: FeishuConfig) -> FeishuConfig:
        if config.webhook_url and not config.webhook_url.startswith(("http://", "https://")):
            raise ValueError("飞书 Webhook URL 必须以 http:// 或 https:// 开头")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            config.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return config

    def status(self) -> dict:
        config = self.load()
        return {
            "configured": bool(config.webhook_url),
            "enabled": config.enabled,
            "webhook_masked": _mask_webhook(config.webhook_url),
            "secret_configured": bool(config.secret),
            "auto_send_live_review": config.auto_send_live_review,
            "auto_send_material_analysis": config.auto_send_material_analysis,
            "last_sent_at": config.last_sent_at,
            "last_error": config.last_error,
        }

    def update_result(self, ok: bool, message: str = "") -> None:
        config = self.load()
        timestamp = datetime.now(UTC).isoformat() if ok else config.last_sent_at
        self.save(
            config.model_copy(
                update={
                    "last_sent_at": timestamp,
                    "last_error": "" if ok else message,
                }
            )
        )


class FeishuNotifier:
    def __init__(
        self,
        store: FeishuConfigStore,
        sent_path: Path = FEISHU_SENT_PATH,
        client: httpx.Client | None = None,
    ) -> None:
        self.store = store
        self.sent_path = sent_path
        self.client = client

    def send_test(self) -> tuple[bool, str]:
        config = self.store.load()
        if not config.webhook_url:
            return False, "请先保存飞书 Webhook URL。"
        card = build_feishu_card(
            "## 飞书连接测试\n\n- 状态：连接成功\n- 说明：千川本地 AI 投放助手已可以发送飞书卡片。",
            "test",
        )
        ok = self._send_payload(config, {"msg_type": "interactive", "card": card})
        return (True, "飞书测试卡片已发送。") if ok else (False, config.last_error or "飞书测试发送失败。")

    def send_live_review(self, review: dict) -> bool:
        config = self.store.load()
        if not config.enabled or not config.auto_send_live_review:
            return False
        key = f"live_review:{review.get('id', '')}"
        return self._send_report(config, key, str(review.get("report_markdown", "")), "live_review")

    def send_material_analysis(self, report: dict) -> bool:
        config = self.store.load()
        if not config.enabled or not config.auto_send_material_analysis:
            return False
        key = f"material_analysis:{report.get('id', '')}"
        return self._send_report(config, key, str(report.get("report_markdown", "")), "material_analysis")

    def _send_report(self, config: FeishuConfig, key: str, markdown: str, report_type: str) -> bool:
        if not markdown or self._already_sent(key):
            return False
        card = build_feishu_card(markdown, report_type)
        ok = self._send_payload(config, {"msg_type": "interactive", "card": card})
        if ok:
            self._mark_sent(key)
        return ok

    def _send_payload(self, config: FeishuConfig, payload: dict) -> bool:
        if not config.webhook_url:
            return False
        if config.secret:
            timestamp = str(int(time.time()))
            string_to_sign = f"{timestamp}\n{config.secret}"
            digest = hmac.new(
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            payload = {
                **payload,
                "timestamp": timestamp,
                "sign": base64.b64encode(digest).decode("utf-8"),
            }
        try:
            if self.client is not None:
                response = self.client.post(config.webhook_url, json=payload, timeout=10)
            else:
                response = httpx.post(config.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            body = response.json()
            if body.get("code") not in (None, 0):
                raise RuntimeError(str(body))
        except Exception as exc:  # noqa: BLE001
            self.store.update_result(False, str(exc))
            return False
        self.store.update_result(True)
        return True

    def _already_sent(self, key: str) -> bool:
        return key in self._read_sent()

    def _mark_sent(self, key: str) -> None:
        sent = self._read_sent()
        sent[key] = datetime.now(UTC).isoformat()
        self.sent_path.parent.mkdir(parents=True, exist_ok=True)
        self.sent_path.write_text(
            json.dumps(sent, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_sent(self) -> dict:
        if not self.sent_path.exists():
            return {}
        try:
            payload = json.loads(self.sent_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}
