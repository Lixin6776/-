# Local Development Runbook

1. Install backend dependencies with `pip install -e ".[dev]"`.
2. Install frontend dependencies with `pnpm install --dir frontend`.
3. Start the stack with `scripts/start-dev.ps1`.
4. Start the dedicated browser with `scripts/start-chrome-cdp.ps1` in its own terminal and keep that terminal open while using CDP.
5. Log in to Qianchuan manually in that browser.
6. Run the CDP page probe and inspect `page.html` and `page.png`.
7. Use fixture mode until selectors are calibrated against the captured page.
8. Open `http://127.0.0.1:5173`.
9. Confirm the strategy banner, data time, freshness, direction, objective, and constraints are visible before reviewing monitor events.
10. No write action is available in this phase. The only output is analysis, recommendations, monitor events, and pending confirmation records.

## Safety Notes

- The backend and frontend bind only to `127.0.0.1`.
- The CDP debug port binds only to `127.0.0.1`.
- Do not expose the CDP port through a tunnel, reverse proxy, or public firewall rule.
- Do not use a personal Chrome profile for automation.
- Do not run write actions in this phase.