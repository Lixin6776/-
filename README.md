# 直播运营助手

千川全域直播的**本机运营工具**：直播盯盘 + 直播复盘 + 素材分析 + 运营助手对话。

**默认只读**：只出数据、结论和建议；任何预算 / 出价 / 计划 / 素材的改动都要人工确认后才执行。

> 第一次用、只是想赶紧跑起来？看 **[三步上手.md](三步上手.md)**（装环境 → 填直播间 → 连数据源出报表）。

---

## 前置依赖

| 依赖 | 说明 |
| --- | --- |
| Windows | 启动脚本是 PowerShell / cmd |
| Google Chrome | 工具通过**调试端口(9222)**读千川页面，需要在本机装 Chrome |
| Python 3.11+ | 后端 |
| Node 18+ / pnpm | 前端 |

---

## 第一次在新电脑上跑起来

**最简单：双击 `安装依赖.cmd`** —— 它会检测 Python / Node / pnpm（缺了提示去哪装，
能用 winget 就自动装），然后装好后端和前端依赖，并生成 `backend/.env`。
装完双击 `启动直播运营助手.cmd` 即可。

想手动装、或者安装脚本跑不通，看下面的手写步骤：

```powershell
# 1) 拉代码（仓库名就是个短横线，建议指定目录名）
git clone https://github.com/Lixin6776/-.git qianchuan-ai-assistant
cd qianchuan-ai-assistant

# 2) 后端依赖
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -e .

# 3) 前端依赖
cd ..\frontend
pnpm install
cd ..

# 4) 本地配置（.env 不进仓库，要从模板建）
copy backend\.env.example backend\.env
#   然后编辑 backend\.env，填直播间名称和账户 ID

# 5) 启动（后端 8000 + 前端 5173 + 数据源浏览器）
#    直接双击：启动直播运营助手.cmd
```

启动后打开 <http://127.0.0.1:5173>。
第一次连数据源时，如果弹出的 Chrome 停在千川登录页，**登录一次**即可（登录态会保留）。

---

## 换电脑时，哪些东西**不会**跟着仓库走

仓库里只有**代码 / 测试 / 文档**。下面这些都在本机、已被 `.gitignore` 忽略：

| 内容 | 位置 | 不搬的后果 |
| --- | --- | --- |
| 盯盘记录 / 复盘 / 运营对话 / 网站变更 | `.local/` | 新机器没有历史，从零开始 |
| 策略库（投放策略版本） | `backend/qianchuan.db` | 要重新建一次投放策略 |
| 本地配置（盯哪个直播间、账户 ID） | `backend/.env` | 不知道读哪个账户 |
| 大模型 Key | `.local/llm_config.json` | 运营助手对话不可用 |
| 飞书授权 | `.local/feishu_config.json` | 复盘 / 日报发不到飞书 |
| 飞书已发送记录、文档地址 | `.local/feishu_sent.json`、`.local/feishu_doc_urls.json` | 可能重复发送 |
| 千川登录态 | Chrome 用户目录 | 要重新登录一次 |

**想连历史一起搬**：把 `backend/.env`、`backend/qianchuan.db`、整个 `.local/` 三个复制到新电脑对应位置即可。
（`.local/` 里含账户数据，只能自己拷，不要提交到仓库。）

---

## 一键启动脚本做了什么

`启动直播运营助手.cmd` → 调 `start.ps1`：

1. 后端 8000：没起就起，并等端口就绪
2. 前端 5173：没起就起
3. 数据源（调试浏览器 9222）：交给后端「连接数据源」逻辑（需要时会拉起 Chrome）
4. 检查盯盘状态：发现断开且"本该在跑"就自动恢复

已在跑的部分会跳过，可以重复双击。
日志在 `.local/logs/`。

---

## 常用排查

| 现象 | 处理 |
| --- | --- |
| 面板显示「数据源：未连接」 | 点「连接数据源」；提示要登录就在弹出的窗口登录千川 |
| 数据不动 | 工具会**自动刷新大屏并复查**；确认真停了会提示 |
| 复盘 / 日报没收到 | 检查飞书是否授权（「飞书」窗口） |
| 运营助手不回答 | 检查「大模型」窗口的 Key 配置 |

---

## 目录结构（简述）

```
backend/app/
  api/            HTTP 接口（chat / live_watch / ops_chat / reviews ...）
  execution/cdp/  读千川页面（大屏、素材、平台日志）
  services/       盯盘、复盘、素材分析、诊断引擎、自检、运营助手
frontend/src/     界面（直播盯盘、运营助手对话、复盘、素材分析）
docs/knowledge/   官方规则 / 运营手册 / 方法论（抓取整理）
.local/           本机数据与配置（不进仓库）
```
