import { FormEvent, useEffect, useState } from "react";

import {
  getFeishuStatus,
  saveFeishuConfig,
  testFeishuConnection
} from "../lib/api";

export type FeishuStatus = {
  configured: boolean;
  enabled: boolean;
  webhook_masked: string;
  secret_configured: boolean;
  auto_send_live_review: boolean;
  auto_send_material_analysis: boolean;
  last_sent_at: string;
  last_error: string;
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
  save?: (config: FeishuConfigInput) => Promise<FeishuStatus>;
  test?: () => Promise<{ ok: boolean; message: string }>;
};

export function FeishuConnectionPanel({
  load = getFeishuStatus,
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

  useEffect(() => {
    load()
      .then((value) => {
        setStatus(value);
        setEnabled(value.enabled);
        setAutoLive(value.auto_send_live_review);
        setAutoMaterial(value.auto_send_material_analysis);
      })
      .catch(() => setMessage("无法读取飞书连接配置。"));
  }, []);

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
      setStatus(updated);
      setWebhookUrl("");
      setSecret("");
      setMessage("飞书配置已保存在本地。");
    } catch {
      setMessage("保存失败，请检查 Webhook URL。");
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
      setMessage("飞书测试失败，请先保存 Webhook URL。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel feishu-connection-panel">
      <div className="panel-heading">
        <p className="eyebrow">Feishu connection</p>
        <h2>飞书</h2>
      </div>
      <p className="llm-connection-status">
        {status?.configured
          ? `飞书已连接${status.enabled ? "，自动发送已开启" : "，自动发送已关闭"}`
          : "尚未配置飞书 Webhook"}
      </p>
      <form className="action-form" onSubmit={handleSave}>
        <label>
          飞书 Webhook URL
          <input
            aria-label="飞书 Webhook URL"
            type="url"
            value={webhookUrl}
            onChange={(event) => setWebhookUrl(event.target.value)}
            placeholder={status?.webhook_masked || "粘贴飞书群机器人 Webhook"}
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
        <div className="llm-actions">
          <button className="button-primary" type="submit" disabled={busy}>
            {busy ? "处理中" : "保存配置"}
          </button>
          <button className="button-outline" type="button" onClick={handleTest} disabled={busy}>
            发送测试卡片
          </button>
        </div>
      </form>
      {message ? <p className="monitor-signal">{message}</p> : null}
      {status?.last_error ? (
        <p className="monitor-signal">最近发送错误：{status.last_error}</p>
      ) : null}
      {status?.last_sent_at ? (
        <p className="empty-state">最近发送：{new Date(status.last_sent_at).toLocaleString("zh-CN")}</p>
      ) : null}
      <p className="empty-state">
        直播复盘和素材日报会统一转换为飞书交互卡片发送；所有投放操作仍需人工确认。
      </p>
    </section>
  );
}
