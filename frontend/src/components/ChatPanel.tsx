export function ChatPanel() {
  return (
    <section className="panel chat-panel">
      <div className="panel-heading">
        <p className="eyebrow">Chatbot</p>
        <h1>千川本地 AI 投放助手</h1>
      </div>
      <div className="chat-stream">
        <article className="message message-system">
          <span>系统</span>
          <p>当前处于只读监控阶段。所有投放操作会先展示建议，等待你确认后执行。</p>
        </article>
      </div>
      <form className="composer" onSubmit={(event) => event.preventDefault()}>
        <input aria-label="输入投放问题" placeholder="询问 ROI、消耗、成交或直播表现" />
        <button className="button-primary" type="submit">发送</button>
      </form>
    </section>
  );
}