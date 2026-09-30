# Live CDP Write Calibration Runbook

Live write tests are disabled by default. Use this runbook only with a known test plan and explicit opt-in.

## Preconditions

- The backend tests pass on the current commit.
- The desktop is using a dedicated Chrome/Edge profile.
- `scripts/start-chrome-cdp.ps1` is running in its own terminal.
- The browser is logged in to the intended Qianchuan account.
- The test plan is visible and none of its current settings are needed for an active campaign.

## Calibration Steps

1. Start the dedicated CDP browser with `scripts/start-chrome-cdp.ps1`.
2. Log in to Qianchuan manually in that browser.
3. Open one known test plan and leave the list page visible.
4. Run `scripts/calibrate-qianchuan-selectors.ps1`.
5. Inspect `.local/selector-probe/page.html` and `page.png`.
6. Create `.local/selectors/qianchuan.json` using the required keys:
   - `plan_rows`
   - `plan_id`
   - `plan_name`
   - `plan_status`
   - `plan_status_toggle`
   - `budget_value`
   - `budget_edit_button`
   - `budget_input`
   - `budget_save_button`
   - `confirmation_dialog`
   - `confirmation_submit`
7. Run the live config test:

```powershell
$env:QCA_RUN_LIVE_TESTS="1"
.\.venv\Scripts\python -m pytest tests/test_live_execution_acceptance.py -v
```

8. In the local UI, preview `pause_plan` for the test plan.
9. Confirm the preview shows the correct target, status diff, strategy profile, and expiry.
10. Click `确认执行` and wait for `succeeded`.
11. Verify the status in Qianchuan.
12. Preview and execute `enable_plan`, then verify status.
13. Preview and execute `update_plan_budget` with a small change inside the profile limit.
14. Verify the new budget and restore the original budget through the same confirmation flow.
15. Inspect `.local/artifacts/<job_id>/` and the execution timeline.

## Stop Conditions

Stop immediately if:

- The target is not the intended test plan.
- The page shows unexpected state or a different account.
- A CAPTCHA, secondary verification, or risk-control page appears.
- The result is `failed` or `unknown`.
- The preview does not show the strategy profile and hard constraints.

Do not bypass verification, repeat unknown actions, or operate a production plan during calibration.