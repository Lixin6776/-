import { useState } from "react";

type Preview = {
  target_id: string;
  target_name: string;
  allowed: boolean;
  blockers: string[];
};

export function BatchConfirmationDialog({
  previews,
  onConfirm,
  onCancel
}: {
  previews: Preview[];
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  const blocked = previews.some((preview) => !preview.allowed);

  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="confirmation-dialog" role="dialog" aria-modal="true" aria-label="批量操作确认">
        <p className="eyebrow">Batch confirmation</p>
        <h2>批量操作确认</h2>
        <ul>
          {previews.map((preview) => (
            <li key={preview.target_id}>
              <strong>{preview.target_name}</strong>
              {preview.blockers.length > 0 ? <span>：{preview.blockers.join("；")}</span> : null}
            </li>
          ))}
        </ul>
        <label className="acknowledgement">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
          />
          我了解批量操作影响
        </label>
        <div className="decision-actions">
          <button className="button-outline" type="button" onClick={onCancel}>
            取消
          </button>
          <button
            className="button-primary"
            type="button"
            disabled={blocked || !acknowledged}
            onClick={onConfirm}
          >
            确认执行批量操作
          </button>
        </div>
      </section>
    </div>
  );
}