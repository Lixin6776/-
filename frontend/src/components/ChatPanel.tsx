import { FormEvent, useState } from "react";

export type ActionPreview = {
  action_name: string;
  target_name: string;
  diff: Record<string, unknown>;
  blockers: string[];
  strategy_profile_version: number;
  expires_at: string;
  requires_confirmation: boolean;
};

export type ChatReply = {
  message: string;
  preview?: ActionPreview;
};

type Message = {
  role: "system" | "user" | "assistant";
  content: string;
  preview?: ActionPreview;
};

export function ChatPanel({
  onSend,
  onOpenConfirmation
}: {
  onSend?: (message: string) => Promise<ChatReply>;
  onOpenConfirmation?: (preview: ActionPreview) => void;
}) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "system",
      content: "当前处于只读监控阶段。所有投放操作会先展示建议，等待你确认后执行。"
    }
  ]);
  const [pending, setPending] = useState(false);

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
            <span>{message.role === "user" ? "你" : message.role === "assistant" ? "助手" : "系统"}</span>
            <p>{message.content}</p>
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