import { useEffect, useRef, useState } from "react";

import {
  connectCdp,
  getCdpConnection,
  getLiveWatchStatus,
  heartbeatLiveWatch,
  resumeLiveWatch,
  startLiveWatch,
  stopLiveWatch,
  tickLiveWatch,
  type CdpConnectionStatus,
  type LiveWatchStatus
} from "../lib/api";

/**
 * 直播盯盘：开关 + 状态 + 数据源连接。
 * 盯盘报表（数据 / 问题 / 调整方案 / 操作日志）每 5 分钟直接发到聊天框，不在这里重复展示。
 *
 * 断线恢复：
 *  - 关窗口、关机、后端重启都不算「停止盯盘」，只有点「停止盯盘」才算。
 *  - 重新打开工具时，如果发现之前是断的，会显示「恢复盯盘」，点一下就从断点接着跑并立刻补读一次。
 *  - 数据源（调试版 Chrome，9222 端口）掉线时，可以点「连接数据源」把它拉起来。
 */

function clockText(iso?: string | null): string {
  if (!iso) return "--";
  const time = new Date(iso);
  if (Number.isNaN(time.getTime())) return "--";
  return time.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function gapText(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return "--";
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return total + " 秒";
  const minutes = Math.floor(total / 60);
  if (minutes < 60) return minutes + " 分钟";
  return Math.floor(minutes / 60) + " 小时 " + (minutes % 60) + " 分钟";
}

export function LiveWatchPanel() {
  const [status, setStatus] = useState<LiveWatchStatus | null>(null);
  const [connection, setConnection] = useState<CdpConnectionStatus | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [busy, setBusy] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [notice, setNotice] = useState("");
  const intervalRef = useRef(300);

  // 打开直播盯盘 -> 立即开始 5 分钟一轮的盯盘
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const next = await startLiveWatch();
        if (cancelled) return;
        setStatus(next);
        intervalRef.current = next.interval_seconds || 300;
        setSecondsLeft(next.interval_seconds || 300);
      } catch {
        if (!cancelled) setStatus(null);
      }
    })();
    getCdpConnection().then(setConnection).catch(() => undefined);
    return () => {
      cancelled = true;
      // 关闭窗口不再停止盯盘：盯盘是常驻的，只有点「停止盯盘」才停
    };
  }, []);

  // 每 10 秒心跳一次：同步状态；只有「用户想跑但停了」时后端才会自动拉起来
  useEffect(() => {
    const timer = window.setInterval(() => {
      heartbeatLiveWatch().then(setStatus).catch(() => undefined);
    }, 10000);
    return () => window.clearInterval(timer);
  }, []);

  // 每 30 秒看一下数据源（9222）还在不在
  useEffect(() => {
    const timer = window.setInterval(() => {
      getCdpConnection().then(setConnection).catch(() => undefined);
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

  // 倒计时
  useEffect(() => {
    const timer = window.setInterval(() => {
      setSecondsLeft((value) => (value > 0 ? value - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  // 每轮结束后重置倒计时
  useEffect(() => {
    if (!status?.running) return;
    setSecondsLeft(intervalRef.current);
  }, [status?.running, status?.tick_count]);

  async function handleTick() {
    setBusy(true);
    setNotice("");
    try {
      await tickLiveWatch();
      setStatus(await getLiveWatchStatus());
      setSecondsLeft(intervalRef.current);
    } catch {
      setNotice("这次读取失败，先看下面数据源是不是断了");
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    setBusy(true);
    try {
      setStatus(await stopLiveWatch());
      setNotice("已停止盯盘。想继续时点「恢复盯盘」。");
    } finally {
      setBusy(false);
    }
  }

  async function handleResume() {
    setBusy(true);
    setNotice("");
    try {
      // 先确认数据源在线 + 把记住的千川页面开回来，再恢复盯盘
      try {
        setConnection(await connectCdp("auto"));
      } catch {
        // 连不上也继续尝试恢复：至少能把断点提示写出来
      }
      const next = await resumeLiveWatch();
      setStatus(next);
      intervalRef.current = next.interval_seconds || 300;
      setSecondsLeft(next.interval_seconds || 300);
      setNotice(next.resume_note ? "已恢复：" + next.resume_note : "已从断点恢复盯盘");
      const conn = await getCdpConnection();
      setConnection(conn);
    } catch {
      setNotice("恢复失败，先点「连接数据源」再试");
    } finally {
      setBusy(false);
    }
  }

  async function handleConnect(mode: "auto" | "default" | "assistant" = "auto") {
    setConnecting(true);
    setNotice("正在连接调试浏览器（第一次用独立浏览器可能要在弹出的窗口里登录千川）...");
    try {
      const next = await connectCdp(mode);
      setConnection(next);
      if (next.connected) {
        setNotice(
          (next.message || "数据源已连接") +
            (status?.interrupted ? "，可以点「恢复盯盘」接着跑" : "")
        );
      } else {
        setNotice(next.message || "还没连上");
      }
    } catch {
      setNotice("连接失败，确认本机装了 Chrome 再试");
    } finally {
      setConnecting(false);
    }
  }

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = String(secondsLeft % 60).padStart(2, "0");
  const interrupted = Boolean(status?.interrupted) || Boolean(status?.desired_running && !status?.running);
  const sourceDown = connection !== null && !connection.connected;

  return (
    <section className="panel live-watch-panel">
      <div className="panel-heading">
        <p className="eyebrow">Live watch · every 5 min</p>
        <h2>直播盯盘</h2>
      </div>

      <div className="monitor-meta">
        <span>{status?.running ? "盯盘中" : "未开始"}</span>
        <span>间隔：{Math.round((status?.interval_seconds ?? 300) / 60)} 分钟</span>
        <span>
          下一轮：{minutes}:{seconds}
        </span>
      </div>

      <div className="monitor-meta">
        <span>
          数据源：
          {connection === null
            ? "检测中"
            : connection.connected
              ? "已连接（千川页面 " + connection.qianchuan_pages + " 个）"
              : "未连接"}
        </span>
        <span>上次读取：{clockText(status?.last_report_at || status?.last_run)}</span>
        {interrupted ? <span>已断开：{gapText(status?.gap_seconds)}</span> : null}
      </div>

      {interrupted ? (
        <p className="monitor-signal">
          ⏱️ 盯盘断开了（{gapText(status?.gap_seconds)}）。点「恢复盯盘」会接着断点跑，
          并立刻补读一次；中断期间的 5 分钟报没法补生成。
        </p>
      ) : null}

      {sourceDown ? (
        <p className="monitor-signal">
          🔌 数据源（本机 9222 调试浏览器）没连上
          {connection?.error ? "：" + connection.error : ""}。
          点「连接数据源」会自动把它拉起来。
        </p>
      ) : null}

      {(status?.consecutive_failures ?? 0) >= 2 ? (
        <p className="monitor-signal">
          ⚠️ 已经连续 {status?.consecutive_failures} 轮读不到数据
          {status?.last_error ? "（" + status.last_error + "）" : ""}。
          先点「连接数据源」，再点「恢复盯盘」。
        </p>
      ) : null}

      <div className="live-watch-actions">
        <button className="button-outline" type="button" onClick={handleTick} disabled={busy}>
          {busy ? "读取中" : "立即读取一次"}
        </button>
        {status?.running ? (
          <button className="button-outline" type="button" onClick={handleStop} disabled={busy}>
            停止盯盘
          </button>
        ) : (
          <button className="button-outline" type="button" onClick={handleResume} disabled={busy}>
            恢复盯盘
          </button>
        )}
        <button
          className="button-outline"
          type="button"
          onClick={() => handleConnect("auto")}
          disabled={connecting}
        >
          {connecting ? "连接中" : sourceDown ? "连接数据源" : "重连数据源"}
        </button>
        {connection?.needs_chrome_restart ? (
          <button
            className="button-outline"
            type="button"
            onClick={() => handleConnect("assistant")}
            disabled={connecting}
          >
            用独立浏览器连接
          </button>
        ) : null}
      </div>

      {notice ? <p className="monitor-signal">{notice}</p> : null}

      <p className="monitor-signal">
        盯盘报表（实时数据 / 发现的问题 / 调整方案 / 操作日志）每 5 分钟自动发到左侧聊天框。
        关窗口、关机都不影响；下次打开这个工具点「恢复盯盘」就能接着跑。
      </p>
    </section>
  );
}
