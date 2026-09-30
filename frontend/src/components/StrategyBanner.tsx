export type StrategyBannerProfile = {
  version: number;
  business_direction: string;
  primary_objective: string;
  hard_constraints: Record<string, unknown>;
  data_time: string;
  freshness: "fresh" | "stale";
};

export function StrategyBanner({ profile }: { profile: StrategyBannerProfile }) {
  return (
    <header className="strategy-banner">
      <strong>投放策略 v{profile.version}</strong>
      <span>{profile.business_direction}</span>
      <span>{profile.primary_objective}</span>
      <span>约束：{JSON.stringify(profile.hard_constraints)}</span>
      <span>{profile.freshness === "fresh" ? "数据最新" : "数据未刷新"}</span>
      <time dateTime={profile.data_time}>{new Date(profile.data_time).toLocaleString("zh-CN")}</time>
    </header>
  );
}