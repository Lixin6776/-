# 自检清单（每次改完代码跑一遍）

> 这份是**实际跑过**的清单，不是理论模板。按顺序执行，每一步都要看到预期结果再往下。
> 环境：Windows / PowerShell；仓库根目录 `D:\qianchuan-ai-assistant`。

## 0. 前置

```powershell
cd D:\qianchuan-ai-assistant
$venv = ".worktrees\qianchuan-foundation\backend\.venv\Scripts\python.exe"
```

> ⚠️ **后端测试必须在 `backend/` 目录下跑**，否则会假失败（fixture 找不到）。

## 1. 服务健康

```powershell
# 后端
Invoke-RestMethod http://127.0.0.1:8000/api/live-watch/status | Select running,desired_running,live_started_at,last_report_at,consecutive_failures
# 前端
(Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing).StatusCode   # 期望 200
# 数据源
(Invoke-WebRequest http://127.0.0.1:9222/json/version -UseBasicParsing).Content
```

**预期**：后端 200、`consecutive_failures=0`；前端 200；CDP 返回 `Chrome/...`。

## 2. 数据资产

```powershell
$rev = Invoke-RestMethod http://127.0.0.1:8000/api/reviews
"复盘 $($rev.Count) 份，最新 $($rev[0].date)"
$mat = Invoke-RestMethod http://127.0.0.1:8000/api/material-analyses
"素材分析 $($mat.Count) 份，最新 $($mat[0].date)"
Invoke-RestMethod http://127.0.0.1:8000/api/ops-outcome | Select baseline,operations,velocity_strata
```

**预期**：
- 复盘 / 素材分析的最新日期 = **昨天**（每天 08:00 自动出）；
- 操作反馈的 `baseline.n > 0`，`operations` / `velocity_strata` 非空。

## 3. 后端测试

```powershell
Push-Location backend
& $venv -m pytest -q "D:\qianchuan-ai-assistant\backend\tests" -p no:cacheprovider
Pop-Location
```

**预期**：全绿（允许 1 个 `s` 跳过）。当前基线：**241 passed, 1 skipped**。

## 4. 前端测试 + 类型检查

```powershell
pnpm --dir frontend exec vitest run
Push-Location frontend; & node_modules\.bin\tsc.cmd --noEmit; "tsc exit=$LASTEXITCODE"; Pop-Location
```

**预期**：23 文件 / 43 测试全过；`tsc exit=0`。

## 5. 全接口冒烟（抓 500）

```powershell
$spec = Invoke-RestMethod http://127.0.0.1:8000/openapi.json
# 逐个 GET 打一遍；跳过 SSE 长连接：
#   /api/notifications/events  /api/monitor/events   ← 这两个会一直挂着，超时属正常
```

**预期**：**没有 5xx**。路径参数用 `none` 占位，404 属正常。

## 6. 日志

```powershell
Get-Content .local\logs\backend.err.log -Tail 20
Get-Content .local\logs\backend.out.log -Tail 50 | Select-String 'HTTP/1.1" (4|5)'
```

**预期**：无 `Traceback` / `Exception`；4xx 只应来自手动测试的假 ID。

## 7. 仓库同步

```powershell
git status --porcelain          # 期望为空
git rev-parse --short HEAD; git rev-parse --short origin/main   # 两个要一致
```

## 8. 盯盘专属检查（改了盯盘/复盘相关代码时必跑）

```powershell
# 最近 100 条记录的有效率
$py = @"
import json,sqlite3,collections
c=sqlite3.connect(r'D:\qianchuan-ai-assistant\.local\live_watch_logs.sqlite3')
rows=[json.loads(x[0]) for x in c.execute('select payload from watch_reports order by created_at desc limit 100')]
print(collections.Counter(r.get('source') for r in rows))
"@
$py | & $venv -
```

**要看的三件事**：

1. **`cdp-error` 占比**：持续 >30% 说明数据源不稳（重连 / 走 API），不是代码问题；
2. **本场结束有没有停**：直播结束后 `running` 应该变成 `False`，且当天复盘已生成；
3. **新场次有没有识别**：`live_started_at` 应该是**最新一场**的开播时间，不能是昨天的。

## 已知的"假失败"（别被误导）

| 现象 | 真正原因 |
|---|---|
| 测试大量失败，报 fixture 找不到 | 在仓库根目录跑了 pytest —— 要 `cd backend` |
| `/api/monitor/events` 超时 | 它是 SSE 长连接，超时正常 |
| `/api/plans/current` 要 5~8 秒 | 正常，它要读 CDP |
| `cdp-error` 里写「本场已结束」 | 这是**结束判定**的产物，不一定是 CDP 故障 |

## 改完必做的收尾

1. 后端测试 + 前端测试 + tsc 全绿；
2. **重启后端**（`启动直播运营助手.cmd` 或 kill 8000 后重跑 `start.ps1`）—— 代码不会热加载；
3. 前端改动让用户**硬刷新**（`Ctrl+Shift+R`）；
4. 提交并推送，确认 `HEAD == origin/main`。
