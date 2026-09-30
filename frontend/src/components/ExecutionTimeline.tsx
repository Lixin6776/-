type ExecutionJob = {
  id: string;
  action_name: string;
  status: string;
  created_at: string;
};

const actionLabels: Record<string, string> = {
  pause_plan: "暂停计划",
  enable_plan: "启用计划",
  update_plan_budget: "修改预算"
};

const statusLabels: Record<string, string> = {
  pending: "待执行",
  preflight: "预检中",
  executing: "执行中",
  verifying: "验证中",
  succeeded: "成功",
  failed: "失败",
  unknown: "状态未知",
  cancelled: "已取消"
};

export function ExecutionTimeline({ jobs }: { jobs: ExecutionJob[] }) {
  return (
    <section className="panel execution-timeline">
      <div className="panel-heading">
        <p className="eyebrow">Execution audit</p>
        <h2>执行轨迹</h2>
      </div>
      {jobs.length === 0 ? (
        <p className="empty-state">暂无执行记录。</p>
      ) : (
        <ol>
          {jobs.map((job) => (
            <li key={job.id}>
              <strong>{actionLabels[job.action_name] ?? job.action_name}</strong>
              <span>{statusLabels[job.status] ?? job.status}</span>
              <time dateTime={job.created_at}>
                {new Date(job.created_at).toLocaleString("zh-CN")}
              </time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}