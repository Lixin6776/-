type LearningCase = {
  id: string;
  action_name: string;
  status: string;
  strategy_profile_version: number;
  context: Record<string, unknown>;
};

const actionLabels: Record<string, string> = {
  pause_plan: "暂停计划",
  enable_plan: "启用计划",
  update_plan_budget: "修改预算",
  create_plan: "新建计划",
  copy_plan: "复制计划",
  delete_plan: "删除计划",
  edit_plan: "编辑计划",
  update_plan_bid: "修改出价",
  update_targeting: "修改定向",
  update_schedule: "修改投放时间",
  bind_existing_material: "绑定素材",
  unbind_existing_material: "解绑素材"
};

export function LearningCaseList({ cases }: { cases: LearningCase[] }) {
  return (
    <section className="panel learning-case-list">
      <div className="panel-heading">
        <p className="eyebrow">Learning cases</p>
        <h2>策略案例</h2>
      </div>
      {cases.length === 0 ? (
        <p className="empty-state">暂无可学习的决策案例。</p>
      ) : (
        <ul>
          {cases.map((item) => (
            <li key={item.id}>
              <strong>{actionLabels[item.action_name] ?? item.action_name}</strong>
              <span>策略 v{item.strategy_profile_version}</span>
              <span>{item.status}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}