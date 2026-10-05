import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from pydantic import BaseModel

FEISHU_CONFIG_PATH = Path(__file__).resolve().parents[3] / ".local" / "feishu_config.json"
FEISHU_SENT_PATH = Path(__file__).resolve().parents[3] / ".local" / "feishu_sent.json"
FEISHU_GROUP_NAME = "千川 AI 投放助手"
FEISHU_GROUP_DESCRIPTION = "千川本地 AI 投放助手 · 直播复盘与素材日报"


class FeishuConfig(BaseModel):
    connection_mode: str = "webhook"
    webhook_url: str = ""
    secret: str = ""
    enabled: bool = False
    auto_send_live_review: bool = True
    auto_send_material_analysis: bool = True
    chat_id: str = ""
    chat_name: str = ""
    chat_share_link: str = ""
    auth_open_id: str = ""
    auth_user_name: str = ""
    auth_status: str = "idle"
    auth_message: str = ""
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
            "configured": bool(config.chat_id or config.webhook_url),
            "enabled": config.enabled,
            "connection_mode": config.connection_mode,
            "webhook_masked": _mask_webhook(config.webhook_url),
            "secret_configured": bool(config.secret),
            "chat_id": config.chat_id,
            "chat_name": config.chat_name,
            "chat_share_link": config.chat_share_link,
            "auth_status": config.auth_status,
            "auth_message": config.auth_message,
            "auth_user_name": config.auth_user_name,
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


class LarkCliRunner:
    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or os.environ.get("LARK_CLI") or shutil.which("lark-cli") or "lark-cli"
        self.node_script = self._find_node_script()

    @staticmethod
    def _find_node_script() -> Path | None:
        candidates = [
            shutil.which("lark-cli.cmd"),
            shutil.which("lark-cli"),
            shutil.which("lark-cli.ps1"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            script = (
                Path(candidate).parent
                / "node_modules"
                / "@larksuite"
                / "cli"
                / "scripts"
                / "run.js"
            )
            if script.exists():
                return script
        return None

    def run(self, args: list[str], cwd: Path | None = None, timeout: int = 120) -> dict:
        if self.node_script is not None:
            command = [shutil.which("node") or "node", str(self.node_script), *args]
            process = subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        elif os.name == "nt":
            command = [self.executable, *args]
            command_line = subprocess.list2cmdline(command)
            process = subprocess.run(
                ["cmd.exe", "/d", "/s", "/c", command_line],
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        else:
            command = [self.executable, *args]
            process = subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        output = process.stdout.strip()
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or output or f"lark-cli exit {process.returncode}")
        if not output:
            return {"ok": True}
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"ok": True, "stdout": output}

    def run_json(self, args: list[str], cwd: Path | None = None, timeout: int = 120) -> dict:
        return self.run(args, cwd=cwd, timeout=timeout)


class FeishuQrAuthService:
    def __init__(
        self,
        store: FeishuConfigStore,
        runner: LarkCliRunner | None = None,
        qr_dir: Path | None = None,
    ) -> None:
        self.store = store
        self.runner = runner or LarkCliRunner()
        self.qr_dir = qr_dir or store.path.parent
        self.device_code = ""
        self._state = {
            "status": "idle",
            "message": "尚未开始扫码连接。",
            "verification_url": "",
            "qr_data_url": "",
            "chat_id": "",
            "chat_name": "",
            "chat_share_link": "",
        }

    def start_login(self, start_polling: bool = True) -> dict:
        result = self.runner.run_json(["auth", "login", "--no-wait", "--json", "--domain", "im"])
        if result.get("ok") is False:
            self._state.update({"status": "failed", "message": str(result.get("error") or result)})
            return dict(self._state)
        verification_url = str(result.get("verification_url") or "")
        device_code = str(result.get("device_code") or "")
        if not verification_url or not device_code:
            self._state.update({"status": "failed", "message": "飞书未返回设备授权信息。"})
            return dict(self._state)
        self.device_code = device_code
        self.qr_dir.mkdir(parents=True, exist_ok=True)
        qr_name = f"feishu_qr_{uuid4().hex}.png"
        qr_path = self.qr_dir / qr_name
        self.runner.run(
            ["auth", "qrcode", verification_url, "--output", qr_name, "--size", "320"],
            cwd=self.qr_dir,
        )
        qr_data_url = ""
        if qr_path.exists():
            qr_data_url = "data:image/png;base64," + base64.b64encode(qr_path.read_bytes()).decode("ascii")
        self._state.update(
            {
                "status": "pending",
                "message": "请使用飞书扫码并完成授权。",
                "verification_url": verification_url,
                "qr_data_url": qr_data_url,
            }
        )
        if start_polling:
            threading.Thread(
                target=self._poll_and_complete,
                args=(device_code,),
                daemon=True,
            ).start()
        return dict(self._state)

    def _poll_and_complete(self, device_code: str) -> None:
        try:
            auth_result = self.runner.run_json(
                ["auth", "login", "--device-code", device_code, "--json"],
                timeout=600,
            )
            if auth_result.get("ok") is False:
                self._state.update(
                    {
                        "status": "failed",
                        "message": str(auth_result.get("error") or "飞书授权失败。"),
                    }
                )
                return
            self.complete_login(device_code, auth_result=auth_result)
        except Exception as exc:  # noqa: BLE001
            self._state.update({"status": "failed", "message": str(exc)})

    def complete_login(self, device_code: str, auth_result: dict | None = None) -> dict:
        result = auth_result or self.runner.run_json(
            ["auth", "login", "--device-code", device_code, "--json"],
            timeout=600,
        )
        if result.get("ok") is False:
            self._state.update({"status": "failed", "message": str(result.get("error") or result)})
            return dict(self._state)
        group_result = self.runner.run_json(
            [
                "im",
                "+chat-create",
                "--name",
                FEISHU_GROUP_NAME,
                "--description",
                FEISHU_GROUP_DESCRIPTION,
                "--as",
                "user",
                "--format",
                "json",
            ],
            timeout=120,
        )
        if group_result.get("ok") is False:
            self._state.update(
                {
                    "status": "failed",
                    "message": str(group_result.get("error") or "创建飞书助手群失败。"),
                }
            )
            return dict(self._state)
        data_raw = group_result.get("data")
        data: dict = data_raw if isinstance(data_raw, dict) else group_result
        chat_id = str(data.get("chat_id") or data.get("chatId") or "")
        chat_name = str(data.get("name") or FEISHU_GROUP_NAME)
        chat_share_link = str(data.get("share_link") or data.get("shareLink") or "")
        if not chat_id:
            self._state.update({"status": "failed", "message": "飞书没有返回群 ID。"})
            return dict(self._state)
        identity_raw = result.get("data")
        identity: dict = identity_raw if isinstance(identity_raw, dict) else result
        config = self.store.load().model_copy(
            update={
                "connection_mode": "qr",
                "enabled": True,
                "chat_id": chat_id,
                "chat_name": chat_name,
                "chat_share_link": chat_share_link,
                "auth_open_id": str(identity.get("open_id") or identity.get("openId") or ""),
                "auth_user_name": str(identity.get("name") or identity.get("user_name") or ""),
                "auth_status": "connected",
                "auth_message": "飞书扫码连接成功。",
                "last_error": "",
            }
        )
        self.store.save(config)
        self._state.update(
            {
                "status": "connected",
                "message": "飞书助手群已创建并连接。",
                "chat_id": chat_id,
                "chat_name": chat_name,
                "chat_share_link": chat_share_link,
            }
        )
        return dict(self._state)

    def status(self) -> dict:
        return {**self.store.status(), **self._state}


class FeishuNotifier:
    def __init__(
        self,
        store: FeishuConfigStore,
        sent_path: Path = FEISHU_SENT_PATH,
        client: httpx.Client | None = None,
        lark_runner: LarkCliRunner | None = None,
    ) -> None:
        self.store = store
        self.sent_path = sent_path
        self.client = client
        self.lark_runner = lark_runner or LarkCliRunner()

    def send_test(self) -> tuple[bool, str]:
        config = self.store.load()
        card = build_feishu_card(
            "## 飞书连接测试\n\n- 状态：连接成功\n- 说明：千川本地 AI 投放助手已可以发送飞书卡片。",
            "test",
        )
        ok = self._send_card(config, card)
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
        ok = self._send_card(config, card)
        if ok:
            self._mark_sent(key)
        return ok

    def _send_card(self, config: FeishuConfig, card: dict) -> bool:
        if config.connection_mode == "qr" and config.chat_id:
            return self._send_via_lark_cli(config, card)
        return self._send_via_webhook(config, card)

    def _send_via_lark_cli(self, config: FeishuConfig, card: dict) -> bool:
        try:
            result = self.lark_runner.run_json(
                [
                    "im",
                    "+messages-send",
                    "--chat-id",
                    config.chat_id,
                    "--msg-type",
                    "interactive",
                    "--content",
                    json.dumps(card, ensure_ascii=False),
                    "--as",
                    "user",
                    "--format",
                    "json",
                ]
            )
            if result.get("ok") is False:
                raise RuntimeError(str(result.get("error") or result))
        except Exception as exc:  # noqa: BLE001
            self.store.update_result(False, str(exc))
            return False
        self.store.update_result(True)
        return True

    def _send_via_webhook(self, config: FeishuConfig, card: dict) -> bool:
        if not config.webhook_url:
            return False
        payload = {"msg_type": "interactive", "card": card}
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
