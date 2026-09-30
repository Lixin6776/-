import { FormEvent, useEffect, useState } from "react";

import {
  getLlmConnectionStatus,
  saveLlmConnection,
  testLlmConnection
} from "../lib/api";

type LlmStatus = {
  configured: boolean;
  provider?: string;
  base_url: string;
  model: string;
  api_key_configured: boolean;
};

type Props = {
  load?: () => Promise<LlmStatus>;
  save?: (config: { base_url: string; model: string; api_key: string }) => Promise<LlmStatus>;
  test?: () => Promise<{ ok: boolean; message: string }>;
};

const DEEPSEEK_BASE_URL = "https://api.deepseek.com";

export function LlmConnectionPanel({
  load = getLlmConnectionStatus,
  save = saveLlmConnection,
  test = testLlmConnection
}: Props) {
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [model, setModel] = useState("deepseek-chat");
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    load()
      .then((value) => {
        setStatus(value);
        setModel(value.model || "deepseek-chat");
      })
      .catch(() => setMessage("无法读取 DeepSeek 连接配置。"));
  }, []);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const updated = await save({
        base_url: DEEPSEEK_BASE_URL,
        model,
        api_key: apiKey
      });
      setStatus(updated);
      setApiKey("");
      setMessage("DeepSeek 配置已保存在本地。");
    } catch {
      setMessage("保存失败，请检查 API Key 和模型名称。");
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
      setMessage("连接失败，请先保存 DeepSeek API Key。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel llm-connection-panel">
      <div className="panel-heading">
        <p className="eyebrow">DeepSeek connection</p>
        <h2>DeepSeek 大模型</h2>
      </div>
      <p className="llm-connection-status">
        {status?.configured
          ? `已配置：${status.model}`
          : "尚未配置 DeepSeek API Key"}
      </p>
      <form className="action-form" onSubmit={handleSave}>
        <label>
          模型
          <select
            aria-label="DeepSeek 模型"
            value={model}
            onChange={(event) => setModel(event.target.value)}
          >
            <option value="deepseek-chat">deepseek-chat</option>
            <option value="deepseek-reasoner">deepseek-reasoner</option>
            <option value="deepseek-v4-flash">deepseek-v4-flash</option>
            <option value="deepseek-v4-pro">deepseek-v4-pro</option>
          </select>
        </label>
        <label>
          API Key
          <input
            aria-label="DeepSeek API Key"
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={status?.api_key_configured ? "已配置，留空则不修改" : "仅保存在本地"}
          />
        </label>
        <p className="llm-connection-status">API 地址：{DEEPSEEK_BASE_URL}</p>
        <div className="llm-actions">
          <button className="button-primary" type="submit" disabled={busy}>
            {busy ? "处理中" : "保存配置"}
          </button>
          <button className="button-outline" type="button" onClick={handleTest} disabled={busy}>
            测试连接
          </button>
        </div>
      </form>
      {message ? <p className="monitor-signal">{message}</p> : null}
    </section>
  );
}
