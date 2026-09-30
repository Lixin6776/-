# Official API Migration Runbook

1. Create a Qianchuan/Ocean Engine developer application.
2. Request read-only account, plan, report, and material permissions first.
3. Configure OAuth callback and obtain access/refresh tokens.
4. Set local environment variables. Do not place secrets in Git.
5. Run read-only account and report checks.
6. Verify the API connection panel reports `API 已配置`.
7. Enable API-first routing for pause, enable, and budget actions.
8. Verify each mutation by API read-back before enabling more actions.
9. Keep CDP as fallback for unsupported actions only.
10. Never automatically retry a failed API mutation through CDP.
11. On authentication failure, pause and request user action.
12. Record every API migration test in the execution timeline.