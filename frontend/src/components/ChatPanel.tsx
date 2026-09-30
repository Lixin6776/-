import { FormEvent, useState } from "react";

type Message = {
  role: "system" | "user" | "assistant";
  content: string;
};

export function ChatPanel({ onSend }: { onSend?: (message: string) => Promise<string> }) {
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
      const response = await onSend(message);
      setMessages((current) => [...current, { role: "assistant", content: response }]);
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