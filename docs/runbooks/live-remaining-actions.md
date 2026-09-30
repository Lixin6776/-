# Live Remaining Actions Calibration Runbook

All live write validation is disabled unless `QCA_RUN_LIVE_TESTS=1`.

## Preconditions

- Use a dedicated test account or a disposable test plan.
- Start the dedicated CDP browser and log in manually.
- Complete the selector calibration in `.local/selectors/qianchuan.json`.
- Back up the test plan's name, budget, bid, targeting, schedule, and bound materials.

## Live Acceptance Sequence

1. Run read-only preflight for every remaining action.
2. Create a temporary plan with a small budget.
3. Copy the temporary plan and verify the source is unchanged.
4. Edit only one allowlisted field at a time and verify the read-back value.
5. Change bid and verify the exact numeric value.
6. Change targeting and verify the normalized targeting object.
7. Change schedule and verify the normalized schedule object.
8. Bind one existing material. Do not upload a new material.
9. Unbind that material and verify it disappears.
10. Delete the copied plan and verify it is absent.
11. Inspect every execution timeline entry and artifact directory.
12. Stop immediately on `failed` or `unknown`.

## Safety Rules

- Never use production plans for destructive validation.
- Never bypass confirmation, CAPTCHA, secondary verification, or risk control.
- Batch validation must remain all-or-abort.
- Do not re-run a job whose state is `unknown`.
- Keep the CDP endpoint on `127.0.0.1`.