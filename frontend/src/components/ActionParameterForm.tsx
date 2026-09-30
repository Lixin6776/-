import { FormEvent, useState } from "react";

type Field = { name: string; label: string; type?: string; required?: boolean };

const fieldsByAction: Record<string, Field[]> = {
  copy_plan: [{ name: "name", label: "目标计划名称", required: true }],
  create_plan: [
    { name: "source_product_id", label: "商品 ID", required: true },
    { name: "name", label: "计划名称", required: true },
    { name: "budget", label: "预算", type: "number", required: true },
    { name: "roi_goal", label: "ROI 目标", type: "number", required: true }
  ],
  delete_plan: [{ name: "reason", label: "删除原因", required: true }],
  edit_plan: [{ name: "fields_json", label: "允许字段 JSON", required: true }],
  update_plan_bid: [{ name: "bid", label: "出价", type: "number", required: true }],
  update_targeting: [{ name: "targeting_json", label: "定向 JSON", required: true }],
  update_schedule: [{ name: "schedule_json", label: "投放时间 JSON", required: true }],
  bind_existing_material: [{ name: "material_id", label: "素材 ID", required: true }],
  unbind_existing_material: [{ name: "material_id", label: "素材 ID", required: true }]
};

export function ActionParameterForm({
  actionName,
  onSubmit
}: {
  actionName: string;
  onSubmit: (params: Record<string, unknown>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const fields = fieldsByAction[actionName] ?? [];

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = Object.fromEntries(
      Object.entries(values).map(([key, value]) => [key.replace(/_json$/, ""), value])
    );
    onSubmit(params);
  }

  return (
    <form className="action-form" onSubmit={submit}>
      <h3>{actionName}</h3>
      {fields.map((field) => (
        <label key={field.name}>
          <span>{field.label}</span>
          <input
            aria-label={field.label}
            type={field.type ?? "text"}
            required={field.required}
            value={values[field.name] ?? ""}
            onChange={(event) =>
              setValues((current) => ({ ...current, [field.name]: event.target.value }))
            }
          />
        </label>
      ))}
      <button className="button-outline" type="submit">
        生成预览
      </button>
    </form>
  );
}