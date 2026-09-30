export function ApiConnectionPanel({
  configured,
  providerPreference
}: {
  configured: boolean;
  providerPreference: "api" | "cdp";
}) {
  return (
    <section className="panel api-connection-panel">
      <div className="panel-heading">
        <p className="eyebrow">API connection</p>
        <h2>开放平台连接</h2>
      </div>
      <p>{configured ? "API 已配置" : "API 尚未配置"}</p>
      <p>API 凭据仅保存在本地，不会发送给模型或浏览器前端。</p>
      <p>
        {providerPreference === "api"
          ? "投放操作默认优先走 API，其他动作使用 CDP 回退。"
          : "当前使用 CDP 回退"}
      </p>
    </section>
  );
}
