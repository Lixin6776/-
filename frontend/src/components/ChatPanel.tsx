import { FormEvent, useEffect, useRef, useState } from "react";

export type ActionPreview = {
  action_name: string;
  target_id: string;
  normalized_params: Record<string, unknown>;
  constraints?: Record<string, unknown>;
  target_name: string;
  diff: Record<string, unknown>;
  blockers: string[];
  strategy_profile_version: number;
  expires_at: string;
  requires_confirmation: boolean;
  destructive?: boolean;
};

export type ChatReply = {
  message: string;
  preview?: ActionPreview;
};

type StrategyCard = {
  title: string;
  plan: string;
  items: string[];
};

function parseStrategyCard(content: string): StrategyCard | null {
  const lines = content.split("\n").map((line) => line.trim()).filter(Boolean);
  const title = lines.find((line) => line.startsWith("### 全域投放策略卡"));
  const plan = lines.find((line) => line.startsWith("**计划："));
  const items = lines.filter((line) => line.startsWith("- "));
  if (!title || !plan || items.length === 0) return null;
  return {
    title: title.slice(4),
    plan: plan.replaceAll("**", ""),
    items: items.map((item) => item.slice(2))
  };
}

function recoverRawJsonMessage(content: string): string | null {
  const match = /"message"\s*:\s*"([\s\S]*?)"\s*[,}]/.exec(content);
  if (!match) return null;
  return match[1]
    .replace(/\\n/g, "\n")
    .replace(/\\r/g, "\r")
    .replace(/\\t/g, "\t")
    .replace(/\\\"/g, '"');
}

function unwrapJsonMessage(content: string): string {
  const trimmed = content.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("```")) return content;
  const withoutFence = trimmed
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "");
  try {
    const parsed = JSON.parse(withoutFence) as unknown;
    if (typeof parsed === "string") return unwrapJsonMessage(parsed);
    if (parsed && typeof parsed === "object" && "message" in parsed) {
      const message = (parsed as { message?: unknown }).message;
      if (typeof message === "string") return unwrapJsonMessage(message);
    }
  } catch {
    const recovered = recoverRawJsonMessage(withoutFence);
    return recovered === null ? content : unwrapJsonMessage(recovered);
  }
  return content;
}

function MessageContent({ content }: { content: string }) {
  const displayContent = unwrapJsonMessage(content);
  if (displayContent.startsWith("## 直播复盘") || displayContent.startsWith("## 素材分析报告")) {
    return <pre className="review-message">{displayContent}</pre>;
  }
  const card = parseStrategyCard(displayContent);
  if (!card) return <p className="message-text">{displayContent}</p>;
  return (
    <div className="strategy-card-message">
      <h3>{card.title}</h3>
      <strong>{card.plan}</strong>
      <ul>
        {card.items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

type Message = {
  role: "system" | "user" | "assistant";
  content: string;
  preview?: ActionPreview;
};

export function ChatPanel({
  onSend,
  onOpenConfirmation,
  incomingMessage
}: {
  onSend?: (message: string) => Promise<ChatReply>;
  onOpenConfirmation?: (preview: ActionPreview) => void;
  incomingMessage?: { id: string; content: string } | null;
}) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "system",
      content: "当前处于只读监控阶段。所有投放操作会先展示建议，等待你确认后执行。"
    }
  ]);
  const [pending, setPending] = useState(false);
  const seenIncomingId = useRef("");

  useEffect(() => {
    if (!incomingMessage || seenIncomingId.current === incomingMessage.id) return;
    seenIncomingId.current = incomingMessage.id;
    setMessages((current) => [
      ...current,
      { role: "assistant", content: incomingMessage.content }
    ]);
  }, [incomingMessage]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
    if (!message || !onSend || pending) return;
    setInput("");
    setMessages((current) => [...current, { role: "user", content: message }]);
    setPending(true);
    try {
      const reply = await onSend(message);
      setMessages((current) => [
        ...current,
        { role: "assistant", content: reply.message, preview: reply.preview }
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        { role: "assistant", content: "请求失败，请检查本地服务和模型配置。" }
      ]);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="panel chat-panel">
      <div className="panel-heading">
        <p className="eyebrow">Chatbot</p>
        <h1>千川本地 AI 投放助手</h1>
      </div>
      <div className="chat-stream" aria-live="polite">
        {messages.map((message, index) => (
          <article className={`message message-${message.role}`} key={`${message.role}-${index}`}>
            {message.role !== "system" ? (
              <div className="chat-avatar" aria-hidden="true">
                {message.role === "user" ? "我" : "助"}
              </div>
            ) : null}
            <div className="message-body">
              <span className={message.role === "system" ? "message-role-system" : "message-role"}>
                {message.role === "user" ? "你" : message.role === "assistant" ? "助手" : "系统"}
              </span>
              <MessageContent content={message.content} />
              {message.preview ? (
                <div className="action-preview-card">
                  <strong>{message.preview.target_name}</strong>
                  <span>{message.preview.action_name}</span>
                  <pre>{JSON.stringify(message.preview.diff, null, 2)}</pre>
                  <button
                    className="button-outline"
                    type="button"
                    onClick={() => onOpenConfirmation?.(message.preview!)}
                  >
                    查看并确认
                  </button>
                </div>
              ) : null}
            </div>
          </article>
        ))}
      </div>
      <form className="composer" onSubmit={submit}>
        <input
          aria-label="输入投放问题"
          placeholder="询问 ROI、消耗、成交或直播表现"
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
        <button className="button-primary" type="submit" disabled={pending || !onSend}>
          {pending ? "分析中" : "发送"}
        </button>
      </form>
    </section>
  );
}
