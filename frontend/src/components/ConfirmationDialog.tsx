import { useState } from "react";

import type { ActionPreview } from "./ChatPanel";

type PreviewWithConstraints = ActionPreview & {
  constraints?: Record<string, unknown>;
  destructive?: boolean;
};

function isExpired(expiresAt: string): boolean {
  return new Date(expiresAt).getTime() <= Date.now();
}

export function ConfirmationDialog({
  preview,
  onConfirm,
  onCancel
}: {
  preview: PreviewWithConstraints;
  onConfirm: (preview: PreviewWithConstraints) => void;
  onCancel: () => void;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  const disabled =
    preview.blockers.length > 0 ||
    isExpired(preview.expires_at) ||
    (preview.destructive === true && !acknowledged);

  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="confirmation-dialog" role="dialog" aria-modal="true" aria-label="操作确认">
        <p className="eyebrow">确认执行</p>
        <h2>{preview.target_name}</h2>
        <p>动作：{preview.action_name}</p>
        <pre>{JSON.stringify(preview.diff, null, 2)}</pre>
        <dl>
          <div><dt>策略画像</dt><dd>策略画像 v{preview.strategy_profile_version}</dd></div>
          <div><dt>硬约束</dt><dd>{JSON.stringify(preview.constraints ?? {})}</dd></div>
          <div><dt>有效期</dt><dd>{new Date(preview.expires_at).toLocaleString("zh-CN")}</dd></div>
        </dl>
        {preview.destructive ? (
          <label className="acknowledgement">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            我了解此操作不可逆
          </label>
        ) : null}
        {preview.blockers.length > 0 ? (
          <ul className="blocker-list">
            {preview.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
          </ul>
        ) : null}
        <div className="decision-actions">
          <button className="button-outline" type="button" onClick={onCancel}>取消</button>
          <button className="button-primary" type="button" disabled={disabled} onClick={() => onConfirm(preview)}>
            确认执行
          </button>
        </div>
      </section>
    </div>
  );
}