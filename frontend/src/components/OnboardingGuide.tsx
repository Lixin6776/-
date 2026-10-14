import { useEffect, useState } from "react";

import {
  connectCdp,
  getCdpConnection,
  getLiveWatchLogs,
  getLlmConnectionStatus,
  getLocalConfig
} from "../lib/api";

type Step = {
  key: string;
  title: string;
  done: boolean;
  hint: string;
  optional?: boolean;
  action?: { label: string; kind: "connect" | "open" | "tick"; target?: string };
};

/**
 * 新手上路：把"能出第一份报表"要做的几件事串成一个清单。
 * 每项自动检测状态；全部完成就自动隐藏（也可手动关掉）。
 *
 * 说明：给朋友/同行用的时候，他们最容易漏的就是「配直播间」和「连数据源」，
 * 这里显式列出来，省得对着文档一步步找。
 */
export function OnboardingGuide({
  onOpenWindow,
  onTick
}: {
  onOpenWindow?: (windowId: string) => void;
  onTick?: () => void;
}) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [busy, setBusy] = useState(false);
  const [hidden, setHidden] = useState(
    () => window.localStorage.getItem("qca_onboarding_hidden") === "1"
  );

  async function refresh() {
    const [cfg, cdp, llm, logs] = await Promise.all([
      getLocalConfig().catch(() => null),
      getCdpConnection().catch(() => null),
      getLlmConnectionStatus().catch(() => null),
      getLiveWatchLogs(1).catch(() => [])
    ]);
    const roomName = (cfg as { effective?: { room_name?: string } } | null)?.effective?.room_name || "";
    const cdpOn = Boolean((cdp as { connected?: boolean } | null)?.connected);
    const llmOn = Boolean(
      (llm as { configured?: boolean; api_key_configured?: boolean } | null)?.configured ||
        (llm as { api_key_configured?: boolean } | null)?.api_key_configured
    );
    const hasReport = Array.isArray(logs) && logs.length > 0;

    setSteps([
      {
        key: "config",
        title: "填写直播间名称（和账户 ID）",
        done: Boolean(roomName),
        hint: roomName ? `当前：${roomName}` : "在「数据源」里填，不用改配置文件",
        action: { label: "去填写", kind: "open", target: "advanced" }
      },
      {
        key: "cdp",
        title: "连接数据源（本机 Chrome）",
        done: cdpOn,
        hint: cdpOn ? "已连接" : "点这里自动拉起调试浏览器；第一次要在弹出的窗口登录千川",
        action: { label: cdpOn ? "重连" : "连接数据源", kind: "connect" }
      },
      {
        key: "llm",
        title: "填大模型 Key（运营助手对话要用）",
        done: llmOn,
        optional: true,
        hint: llmOn ? "已配置" : "可选：不填也能盯盘 / 复盘，只是运营助手聊不了天",
        action: { label: "去配置", kind: "open", target: "llm" }
      },
      {
        key: "report",
        title: "跑出第一份盯盘报表",
        done: hasReport,
        hint: hasReport ? "已有报表，报表会发到左侧聊天框" : "点这里立刻读一次",
        action: { label: "立即读取", kind: "tick" }
      }
    ]);
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 20000);
    return () => window.clearInterval(timer);
  }, []);

  if (hidden || steps.length === 0) return null;
  // 可选的步骤（大模型 Key）不算"必做"，全做完必做项就自动隐藏
  const required = steps.filter((s) => !s.optional);
  if (required.length === 0 || required.every((s) => s.done)) return null;

  const doneCount = required.filter((s) => s.done).length;

  async function run(step: Step) {
    if (!step.action) return;
    if (step.action.kind === "open") {
      onOpenWindow?.(step.action.target || "");
      return;
    }
    if (step.action.kind === "tick") {
      onTick?.();
      return;
    }
    setBusy(true);
    try {
      await connectCdp("auto");
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="onboarding-guide">
      <header>
        <strong>新手上路（{doneCount}/{required.length}）</strong>
        <button
          className="button-outline"
          type="button"
          onClick={() => {
            window.localStorage.setItem("qca_onboarding_hidden", "1");
            setHidden(true);
          }}
        >
          我知道了
        </button>
      </header>
      <ol>
        {steps.map((step) => (
          <li key={step.key} className={step.done ? "is-done" : ""}>
            <span className="onboarding-mark">{step.done ? "✓" : "○"}</span>
            <span className="onboarding-title">
              {step.title}
              {step.optional ? "（可选）" : ""}
            </span>
            <span className="onboarding-hint">{step.hint}</span>
            {!step.done && step.action ? (
              <button className="button-outline" type="button" onClick={() => run(step)} disabled={busy}>
                {step.action.label}
              </button>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
