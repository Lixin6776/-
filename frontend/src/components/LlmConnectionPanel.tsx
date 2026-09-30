import { FormEvent, useEffect, useState } from "react";

import {
  getLlmConnectionStatus,
  saveLlmConnection,
  testLlmConnection
} from "../lib/api";

type LlmStatus = {
  configured: boolean;
  base_url: string;
  model: string;
  api_key_configured: boolean;
};

type Props = {
  load?: () => Promise<LlmStatus>;
  save?: (config: { base_url: string; model: string; api_key: string }) => Promise<LlmStatus>;
  test?: () => Promise<{ ok: boolean; message: string }>;
};

export function LlmConnectionPanel({
  load = getLlmConnectionStatus,
  save = saveLlmConnection,
  test = testLlmConnection
}: Props) {
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    load()
      .then((value) => {
        setStatus(value);
        setBaseUrl(value.base_url);
        setModel(value.model);
      })
      .catch(() => setMessage("无法读取大模型连接配置。"));
  }, []);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const updated = await save({ base_url: baseUrl, model, api_key: apiKey });
      setStatus(updated);
      setApiKey("");
      setMessage("配置已保存在本地。");
    } catch {
      setMessage("保存失败，请检查地址和模型名称。");
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
      setMessage("连接失败，请先保存配置并检查 API Key。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel llm-connection-panel">
      <div className="panel-heading">
        <p className="eyebrow">LLM connection</p>
        <h2>大模型连接</h2>
      </div>
      <p className="llm-connection-status">
        {status?.configured
          ? `已配置：${status.model}`
          : "尚未配置大模型 API"}
      </p>
      <form className="action-form" onSubmit={handleSave}>
        <label>
          API 地址
          <input
            aria-label="大模型 API 地址"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder="https://api.openai.com/v1"
            required
          />
        </label>
        <label>
          模型名称
          <input
            aria-label="大模型模型名称"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            placeholder="gpt-4.1-mini"
            required
          />
        </label>
        <label>
          API Key
          <input
            aria-label="大模型 API Key"
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={status?.api_key_configured ? "已配置，留空则不修改" : "仅保存在本地"}
          />
        </label>
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
