import { useEffect, useState } from "react";

import {
  connectCdp,
  getApiConnectionStatus,
  getCdpConnection,
  getLocalConfig,
  resumeLiveWatch,
  saveApiConnection,
  saveLocalConfig,
  testApiConnection,
  type ApiConnectionStatus,
  type CdpConnectionStatus
} from "../lib/api";

type ApiStatus = ApiConnectionStatus;

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
  // 开放平台凭据（保存在本机 .local/api_config.json；密钥留空 = 不改动已存的）
  const [apiForm, setApiForm] = useState({
    base_url: "https://api.oceanengine.com",
    app_id: "",
    app_secret: "",
    access_token: "",
    refresh_token: "",
    advertiser_id: ""
  });

  async function refresh() {
    try {
      setCdp(await getCdpConnection());
    } catch {
      setCdp(null);
    }
    try {
      const status = await getApiConnectionStatus();
      setApi(status);
      // 只把非密钥字段回填到表单；密钥不回显，留空表示不改
      setApiForm((current) => ({
        ...current,
        base_url: status.base_url || current.base_url,
        app_id: status.app_id || current.app_id,
        advertiser_id: status.advertiser_id ? String(status.advertiser_id) : current.advertiser_id
      }));
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

  async function handleSaveApi() {
    setBusy(true);
    setNotice("");
    try {
      const next = await saveApiConnection({
        base_url: apiForm.base_url.trim() || "https://api.oceanengine.com",
        app_id: apiForm.app_id.trim(),
        app_secret: apiForm.app_secret.trim(),
        access_token: apiForm.access_token.trim(),
        refresh_token: apiForm.refresh_token.trim(),
        advertiser_id: Number(apiForm.advertiser_id) || 0
      });
      setApi(next);
      setApiForm((current) => ({
        ...current,
        app_secret: "",
        access_token: "",
        refresh_token: ""
      }));
      setNotice("API 凭据已保存（存在本机 .local/api_config.json，不进仓库）。下一步点「测试连接」。");
    } catch {
      setNotice("保存失败，检查本地服务。");
    } finally {
      setBusy(false);
    }
  }

  async function handleTestApi() {
    setBusy(true);
    setNotice("正在测试开放平台连接（会去拉一次广告主信息）...");
    try {
      const result = await testApiConnection();
      setNotice(result.message || "API 连接成功");
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "API 连接测试失败");
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
          <div className="api-conn-form">
            <label>
              接口地址
              <input
                aria-label="API 接口地址"
                value={apiForm.base_url}
                onChange={(e) => setApiForm({ ...apiForm, base_url: e.target.value })}
              />
            </label>
            <label>
              App ID
              <input
                aria-label="App ID"
                placeholder="开放平台应用的 App ID"
                value={apiForm.app_id}
                onChange={(e) => setApiForm({ ...apiForm, app_id: e.target.value })}
              />
            </label>
            <label>
              App Secret
              <input
                aria-label="App Secret"
                type="password"
                placeholder={api?.has_secret ? "已保存（留空不改）" : "应用密钥"}
                value={apiForm.app_secret}
                onChange={(e) => setApiForm({ ...apiForm, app_secret: e.target.value })}
              />
            </label>
            <label>
              广告主 ID
              <input
                aria-label="广告主 ID"
                placeholder="advertiser_id（纯数字）"
                value={apiForm.advertiser_id}
                onChange={(e) => setApiForm({ ...apiForm, advertiser_id: e.target.value })}
              />
            </label>
            <label>
              Access Token
              <input
                aria-label="Access Token"
                type="password"
                placeholder={api?.has_access_token ? "已保存（留空不改）" : "授权后拿到的 access_token"}
                value={apiForm.access_token}
                onChange={(e) => setApiForm({ ...apiForm, access_token: e.target.value })}
              />
            </label>
            <label>
              Refresh Token
              <input
                aria-label="Refresh Token"
                type="password"
                placeholder={api?.has_refresh_token ? "已保存（留空不改）" : "可选：有它可自动续期"}
                value={apiForm.refresh_token}
                onChange={(e) => setApiForm({ ...apiForm, refresh_token: e.target.value })}
              />
            </label>
            <div className="live-watch-actions">
              <button className="button-outline" type="button" onClick={handleSaveApi} disabled={busy}>
                保存凭据
              </button>
              <button
                className="button-primary"
                type="button"
                onClick={handleTestApi}
                disabled={busy || !api?.configured}
              >
                测试连接
              </button>
            </div>
          </div>
          <p className="monitor-signal">
            怎么拿到凭据：去巨量引擎开放平台申请应用 → 拿到 <strong>App ID / Secret</strong>
            → 用应用完成<strong>广告主授权</strong> → 把 <strong>access_token</strong>
            （有 refresh_token 更好）填进来。填好点「测试连接」，通过后这里会显示"已配置"，
            系统会切到 <strong>API 优先</strong>；没配好时自动用 CDP，不影响正常盯盘。
          </p>
          <p className="monitor-signal">
            不会弄？
            <a
              href="https://github.com/Lixin6776/qianchuanzidongtoufang/blob/main/docs/开放平台API接入指南.md"
              target="_blank"
              rel="noreferrer"
            >
              看《开放平台 API 接入指南》
            </a>
            （注册应用 → 申请权限 → 配回调 → 生成授权链接 → 换 token）。
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
