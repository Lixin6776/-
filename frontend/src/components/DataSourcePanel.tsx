import { useEffect, useState } from "react";

import {
  connectCdp,
  getApiConnectionStatus,
  getCdpConnection,
  getLocalConfig,
  resumeLiveWatch,
  saveLocalConfig,
  type CdpConnectionStatus
} from "../lib/api";

type ApiStatus = {
  configured: boolean;
  provider_preference: "api" | "cdp";
  base_url?: string;
  advertiser_id?: number;
  token_expires_at?: number;
};

/**
 * 数据源：一个窗口管两条读取链路。
 *   CDP：通过本机 Chrome 读千川页面（现在实际在用）
 *   API：走巨量开放平台接口（更稳，但需要凭据 + 授权）
 * 谁生效由后端 provider_preference 决定（API 配好了优先，否则 CDP）。
 */
export function DataSourcePanel() {
  const [cdp, setCdp] = useState<CdpConnectionStatus | null>(null);
  const [api, setApi] = useState<ApiStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  // 本机配置：盯哪个直播间 / 哪个账户（不用改 .env）
  const [form, setForm] = useState({ room_name: "", aavid: "" });
  const [effective, setEffective] = useState({ room_name: "", aavid: "" });

  async function refresh() {
    try {
      setCdp(await getCdpConnection());
    } catch {
      setCdp(null);
    }
    try {
      setApi(await getApiConnectionStatus());
    } catch {
      setApi(null);
    }
    try {
      const cfg = await getLocalConfig();
      setForm({
        room_name: cfg.saved?.room_name || "",
        aavid: cfg.saved?.aavid || ""
      });
      setEffective({
        room_name: cfg.effective?.room_name || "",
        aavid: cfg.effective?.aavid || ""
      });
    } catch {
      // ignore
    }
  }

  async function handleSaveConfig() {
    setBusy(true);
    setNotice("");
    try {
      await saveLocalConfig(form);
      const cfg = await getLocalConfig();
      setEffective({
        room_name: cfg.effective?.room_name || "",
        aavid: cfg.effective?.aavid || ""
      });
      setNotice("已保存。留空 = 用 backend/.env 里的值；保存后下次读取即生效，不用重启。");
    } catch {
      setNotice("保存失败，检查本地服务。");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 20000);
    return () => window.clearInterval(timer);
  }, []);

  async function handleConnect() {
    setBusy(true);
    setNotice("正在连接调试浏览器（第一次可能要在弹出的窗口里登录千川）...");
    try {
      const next = await connectCdp("auto");
      setCdp(next);
      setNotice(next.message || (next.connected ? "数据源已连接" : "还没连上"));
    } catch {
      setNotice("连接失败，确认本机装了 Chrome 再试");
    } finally {
      setBusy(false);
    }
  }

  async function handleResume() {
    setBusy(true);
    try {
      const status = await resumeLiveWatch();
      setNotice(status.resume_note || "已从断点恢复盯盘");
      await refresh();
    } catch {
      setNotice("恢复失败，先点「连接数据源」再试");
    } finally {
      setBusy(false);
    }
  }

  const activeSource = api?.configured && api.provider_preference === "api" ? "API（开放平台）" : "CDP（本机浏览器）";
  const cdpReady = Boolean(cdp?.connected);

  return (
    <section className="data-source-panel">
      <p className="eyebrow">Data source</p>
      <h3>数据源</h3>
      <p className="ops-role-desc">
        工具读千川数据有两条链路，任一时刻只用一条。当前生效：
        <strong>{activeSource}</strong>
      </p>

      <section className="data-source-config">
        <h4>盯哪个直播间 / 账户</h4>
        <p className="monitor-signal">
          填在这里就不用改 backend/.env 了。**留空 = 用 .env 里的值**。
          {effective.room_name ? ` 当前生效：${effective.room_name}` : ""}
          {effective.aavid ? `（账户 ${effective.aavid}）` : ""}
        </p>
        <div className="data-source-config-row">
          <label>
            直播间名称
            <input
              aria-label="直播间名称"
              placeholder="例如：质润官方旗舰店"
              value={form.room_name}
              onChange={(e) => setForm({ ...form, room_name: e.target.value })}
            />
          </label>
          <label>
            账户 ID（可选）
            <input
              aria-label="账户 ID"
              placeholder="巨量千川账户 aavid"
              value={form.aavid}
              onChange={(e) => setForm({ ...form, aavid: e.target.value })}
            />
          </label>
          <button className="button-outline" type="button" onClick={handleSaveConfig} disabled={busy}>
            保存
          </button>
        </div>
      </section>

      <div className="data-source-grid">
        <section className={`data-source-card${cdpReady ? " is-active" : ""}`}>
          <header>
            <h4>CDP 连接（读页面）</h4>
            <span>{cdpReady ? "已连接" : "未连接"}</span>
          </header>
          <ul>
            <li>方式：本机 Chrome 调试端口读千川页面</li>
            <li>依赖：Chrome + 在浏览器里登录千川</li>
            <li>状态：{cdp === null ? "检测中" : cdpReady ? `千川页面 ${cdp.qianchuan_pages} 个` : cdp.error || "未连接"}</li>
          </ul>
          <div className="live-watch-actions">
            <button className="button-outline" type="button" onClick={handleConnect} disabled={busy}>
              {busy ? "处理中" : cdpReady ? "重连数据源" : "连接数据源"}
            </button>
            <button className="button-outline" type="button" onClick={handleResume} disabled={busy}>
              恢复盯盘
            </button>
          </div>
        </section>

        <section className={`data-source-card${!cdpReady && api?.configured ? " is-active" : ""}`}>
          <header>
            <h4>API 连接（开放平台）</h4>
            <span>{api?.configured ? "已配置" : "未配置"}</span>
          </header>
          <ul>
            <li>方式：调巨量开放平台接口，不依赖浏览器</li>
            <li>依赖：App ID / Secret + 广告主授权</li>
            <li>
              状态：
              {api === null
                ? "读取失败"
                : api.configured
                  ? `广告主 ${api.advertiser_id || "--"}`
                  : "还没配置凭据"}
            </li>
          </ul>
          <p className="monitor-signal">
            尚未开放：需要先在巨量引擎开放平台申请应用并获得授权。
            配好后这里会显示「测试连接」，届时可切换为 API 优先。
          </p>
        </section>
      </div>

      {notice ? <p className="monitor-signal">{notice}</p> : null}
      <p className="monitor-signal">
        两条链路的差别：CDP 现在就能用、但依赖页面结构（页面改版就可能读错，需要自检兜底）；
        API 更稳定、也更符合平台要求，是后续产品化的前提。
      </p>
    </section>
  );
}
