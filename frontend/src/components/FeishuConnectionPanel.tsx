import { FormEvent, useEffect, useState } from "react";

import {
  getFeishuLoginStatus,
  getFeishuStatus,
  saveFeishuConfig,
  startFeishuLogin,
  testFeishuConnection
} from "../lib/api";

export type FeishuStatus = {
  configured: boolean;
  enabled: boolean;
  connection_mode: string;
  webhook_masked: string;
  secret_configured: boolean;
  chat_id: string;
  chat_name: string;
  chat_share_link: string;
  auth_status: string;
  auth_message: string;
  auth_user_name: string;
  auto_send_live_review: boolean;
  auto_send_material_analysis: boolean;
  last_sent_at: string;
  last_error: string;
  status?: string;
  message?: string;
  verification_url?: string;
  qr_data_url?: string;
};

type FeishuConfigInput = {
  webhook_url: string;
  secret: string;
  enabled: boolean;
  auto_send_live_review: boolean;
  auto_send_material_analysis: boolean;
};

type Props = {
  load?: () => Promise<FeishuStatus>;
  start?: () => Promise<FeishuStatus>;
  poll?: () => Promise<FeishuStatus>;
  save?: (config: FeishuConfigInput) => Promise<FeishuStatus>;
  test?: () => Promise<{ ok: boolean; message: string }>;
};

export function FeishuConnectionPanel({
  load = getFeishuStatus,
  start = startFeishuLogin,
  poll = getFeishuLoginStatus,
  save = saveFeishuConfig,
  test = testFeishuConnection
}: Props) {
  const [status, setStatus] = useState<FeishuStatus | null>(null);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [autoLive, setAutoLive] = useState(true);
  const [autoMaterial, setAutoMaterial] = useState(true);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  function applyStatus(value: FeishuStatus) {
    setStatus(value);
    setEnabled(value.enabled);
    setAutoLive(value.auto_send_live_review);
    setAutoMaterial(value.auto_send_material_analysis);
  }

  useEffect(() => {
    load()
      .then(applyStatus)
      .catch(() => setMessage("无法读取飞书连接配置。"));
  }, []);

  useEffect(() => {
    if (status?.status !== "pending") return;
    const timer = window.setInterval(() => {
      poll().then(applyStatus).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [status?.status]);

  async function handleStart() {
    setBusy(true);
    setMessage("");
    try {
      const value = await start();
      applyStatus(value);
      setMessage(value.message || "请使用飞书扫码并完成授权。");
    } catch {
      setMessage("启动飞书扫码失败，请检查 lark-cli 状态。");
    } finally {
      setBusy(false);
    }
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const updated = await save({
        webhook_url: webhookUrl,
        secret,
        enabled,
        auto_send_live_review: autoLive,
        auto_send_material_analysis: autoMaterial
      });
      applyStatus(updated);
      setWebhookUrl("");
      setSecret("");
      setMessage("飞书发送设置已保存。");
    } catch {
      setMessage("保存失败，请检查飞书配置。");
    } finally {
      setBusy(false);
    }
  }

  async function handleTest() {
    setBusy(true);
    setMessage("");
    try {
      const result = await test();
      setMessage(result.message);
    } catch {
      setMessage("飞书测试失败，请先完成扫码连接。");
    } finally {
      setBusy(false);
    }
  }

  const connected = Boolean(status?.chat_id || status?.status === "connected");
  const pending = status?.status === "pending";

  return (
    <section className="panel feishu-connection-panel">
      <div className="panel-heading">
        <p className="eyebrow">Feishu connection</p>
        <h2>飞书</h2>
      </div>
      <p className="llm-connection-status">
        {connected
          ? "已连接飞书助手群" + (status?.chat_name ? "：" + status.chat_name : "")
          : pending
            ? "等待扫码授权"
            : "尚未连接飞书"}
      </p>

      {!connected ? (
        <div className="feishu-login-box">
          <button className="button-primary" type="button" onClick={handleStart} disabled={busy}>
            {busy ? "处理中" : "开始扫码连接"}
          </button>
          {status?.qr_data_url ? (
            <img className="feishu-qr" src={status.qr_data_url} alt="飞书扫码连接" />
          ) : null}
          {status?.verification_url ? (
            <a href={status.verification_url} target="_blank" rel="noreferrer">
              打开飞书授权链接
            </a>
          ) : null}
          <p className="empty-state">
            扫码后授权 IM 权限，系统会自动创建“千川 AI 投放助手”私有群。
          </p>
        </div>
      ) : null}

      {connected ? (
        <form className="action-form" onSubmit={handleSave}>
          <label className="check-line">
            <input
              aria-label="启用飞书发送"
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            启用飞书发送
          </label>
          <label className="check-line">
            <input
              aria-label="直播复盘自动发送"
              type="checkbox"
              checked={autoLive}
              onChange={(event) => setAutoLive(event.target.checked)}
            />
            直播复盘自动发送
          </label>
          <label className="check-line">
            <input
              aria-label="素材日报自动发送"
              type="checkbox"
              checked={autoMaterial}
              onChange={(event) => setAutoMaterial(event.target.checked)}
            />
            素材日报自动发送
          </label>
          {status?.chat_share_link ? (
            <a href={status.chat_share_link} target="_blank" rel="noreferrer">
              打开飞书助手群
            </a>
          ) : null}
          <div className="llm-actions">
            <button className="button-primary" type="submit" disabled={busy}>
              保存配置
            </button>
            <button className="button-outline" type="button" onClick={handleTest} disabled={busy}>
              发送测试卡片
            </button>
          </div>
        </form>
      ) : null}

      <details className="feishu-webhook-fallback">
        <summary>高级：使用 Webhook 兼容</summary>
        <form className="action-form" onSubmit={handleSave}>
          <label>
            飞书 Webhook URL
            <input
              aria-label="飞书 Webhook URL"
              type="url"
              value={webhookUrl}
              onChange={(event) => setWebhookUrl(event.target.value)}
              placeholder={status?.webhook_masked || "可选，粘贴群机器人 Webhook"}
            />
          </label>
          <label>
            飞书签名密钥
            <input
              aria-label="飞书签名密钥"
              type="password"
              value={secret}
              onChange={(event) => setSecret(event.target.value)}
              placeholder={status?.secret_configured ? "已配置，留空则不修改" : "可选"}
            />
          </label>
          <button className="button-outline" type="submit" disabled={busy}>
            保存 Webhook 配置
          </button>
        </form>
      </details>

      {message ? <p className="monitor-signal">{message}</p> : null}
      {status?.auth_message ? <p className="empty-state">{status.auth_message}</p> : null}
      {status?.last_error ? (
        <p className="monitor-signal">最近发送错误：{status.last_error}</p>
      ) : null}
    </section>
  );
}
