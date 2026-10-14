import { FormEvent, useEffect, useRef, useState } from "react";

import { ExecutionTimeline } from "./ExecutionTimeline";
import { ReportMessage } from "./ReportMessage";
import {
  generateOpsBriefing,
  getOpsChatMessages,
  sendOpsChat,
  type OpsChatMessage
} from "../lib/api";

type Job = {
  id: string;
  action_name: string;
  status: string;
  created_at: string;
};

const INTRO =
  "我是直播运营助手。每天 8:05 我会发一份《每日运营汇报》（昨日复盘要点 + 素材情况 + 待处理问题 + 今日建议），每场直播结束我会把复盘发在这里。有想聊的直接问就行。";

/**
 * 直播运营助手：跨场次保留的运营对话。
 * 和主聊天框分工：主聊天框只讲「本场」，每场开播清空；这里留历史、按天归档。
 */
export function OpsChatPanel({
  incomingMessage,
  jobs = []
}: {
  incomingMessage?: { id: string; content: string } | null;
  jobs?: Job[];
}) {
  const [messages, setMessages] = useState<OpsChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [briefing, setBriefing] = useState(false);
  const [error, setError] = useState("");
  const seenIncomingId = useRef("");
  const seenIds = useRef<Set<string>>(new Set());
  const streamRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getOpsChatMessages(100)
      .then((items) => {
        seenIds.current = new Set(items.map((item) => item.id));
        setMessages(items);
      })
      .catch(() => setError("读取运营对话失败，检查本地服务是否在跑。"));
  }, []);

  useEffect(() => {
    if (!incomingMessage || seenIncomingId.current === incomingMessage.id) return;
    seenIncomingId.current = incomingMessage.id;
    if (seenIds.current.has(incomingMessage.id)) return;
    seenIds.current.add(incomingMessage.id);
    setMessages((current) => [
      ...current,
      {
        id: incomingMessage.id,
        created_at: new Date().toISOString(),
        role: "assistant",
        kind: "chat",
        content: incomingMessage.content
      }
    ]);
  }, [incomingMessage]);

  useEffect(() => {
    const node = streamRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages.length]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || pending) return;
    setInput("");
    setError("");
    setPending(true);
    // 先把我的话显示出来，等服务端返回再补助手的回答
    const localId = `local-${Date.now()}`;
    setMessages((current) => [
      ...current,
      { id: localId, created_at: new Date().toISOString(), role: "user", content: text }
    ]);
    try {
      const reply = await sendOpsChat(text);
      setMessages((current) => [...current, reply]);
      seenIds.current.add(reply.id);
    } catch {
      setError("发送失败，检查本地服务和「大模型」连接配置。");
    } finally {
      setPending(false);
    }
  }

  async function handleBriefing() {
    setBriefing(true);
    setError("");
    try {
      const message = await generateOpsBriefing();
      if (!seenIds.current.has(message.id)) {
        seenIds.current.add(message.id);
        setMessages((current) => [...current, message]);
      }
    } catch {
      setError("生成汇报失败，检查本地服务是否在跑。");
    } finally {
      setBriefing(false);
    }
  }

  return (
    <section className="ops-chat-panel">
      <div className="ops-chat-intro">
        <p className="eyebrow">Senior Live Ops · chatbot</p>
        <h3>直播运营助手</h3>
        <p className="ops-role-desc">
          资深直播运营专家，负责本账号的盯盘、复盘、素材与沟通。
          所有判断都带数据依据；数据没过校验就不出结论；写操作必须你确认后才执行。
        </p>
      </div>

      <div className="ops-chat-head">
        <span>跨场次保留 · 每天 8:05 自动汇报</span>
        <button className="button-outline" type="button" onClick={handleBriefing} disabled={briefing}>
          {briefing ? "生成中" : "立即生成今日汇报"}
        </button>
      </div>

      <div className="ops-chat-stream" ref={streamRef} aria-live="polite">
        <article className="message message-assistant">
          <div className="chat-avatar" aria-hidden="true">助</div>
          <div className="message-body">
            <span className="message-role">助手</span>
            <p className="message-text">{INTRO}</p>
          </div>
        </article>

        {messages.map((message) => (
          <article className={`message message-${message.role}`} key={message.id}>
            <div className="chat-avatar" aria-hidden="true">
              {message.role === "user" ? "我" : "助"}
            </div>
            <div className="message-body">
              <span className="message-role">{message.role === "user" ? "你" : "助手"}</span>
              {message.kind === "briefing" || message.kind === "review" ? (
                <span className="ops-message-tag">
                  {message.kind === "briefing" ? "每日运营汇报" : "直播复盘"}
                </span>
              ) : null}
              {/^#{2,3}\s/.test(message.content) ? (
                <ReportMessage content={message.content} />
              ) : (
                <p className="message-text">{message.content}</p>
              )}
            </div>
          </article>
        ))}
      </div>

      {error ? <p className="monitor-signal">{error}</p> : null}

      <form className="composer" onSubmit={submit}>
        <input
          aria-label="和直播运营助手对话"
          placeholder="问它：今天有什么问题？昨天那场为什么 ROI 掉了？"
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
        <button className="button-primary" type="submit" disabled={pending}>
          {pending ? "思考中" : "发送"}
        </button>
      </form>

      <details className="ops-jobs">
        <summary>执行记录（{jobs.length}）</summary>
        <ExecutionTimeline jobs={jobs} />
      </details>
    </section>
  );
}
