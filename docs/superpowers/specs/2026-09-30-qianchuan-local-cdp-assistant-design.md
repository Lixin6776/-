# 千川本地 AI 投放助手设计规格

- 日期：2026-09-30
- 状态：待用户评审
- 项目形态：本地运行、单用户、单账户、Chatbot 驱动
- 第一版执行通道：Chrome DevTools Protocol
- 后续执行通道：巨量千川 Marketing API
- 核心原则：建议由 AI 生成，写操作由用户确认，执行由确定性工作流完成

## 1. 背景与目标

搭建一个本地运行的千川 AI 投放助手。用户通过 Chatbot 查询计划与直播间数据、分析投放表现、获得策略建议，并在确认后执行计划、预算、出价、定向、投放时间和已有素材绑定等投放操作。

系统需要长期保存账户级策略画像，并在每次输出中提醒当前大方向、主目标和硬约束。系统需要定时监控计划与直播间数据，识别有意义的变化，给出调整建议，但不得在未确认时修改真实账户。

第一版使用 CDP 连接已登录的 Chrome/Edge，以临时替代官方 API。业务层不得依赖 CDP 细节，后续应能切换到官方 API 而不重写策略、分析和 Chatbot 层。

## 2. 范围

### 2.1 第一版支持

- 单本地用户、单千川账户。
- Chatbot 自然语言交互。
- 计划与直播间数据采集。
- 账户、计划、直播间分析。
- 长期策略画像及版本管理。
- 5 至 10 分钟直播监控。
- 变化检测、异常分类和行动建议。
- 计划创建、复制、删除和编辑。
- 计划暂停和启用。
- 预算、出价、定向和投放时间修改。
- 已有素材绑定和解绑。
- 人工确认、CDP 执行、执行后校验和审计。
- 决策记录、结果归因和策略案例学习。
- 未来 API Execution Provider 的扩展接口。

### 2.2 第一版不支持

- 多账户、多用户、团队协作和 SaaS。
- 素材上传。
- 充值、转账、余额管理和资金划转。
- 绕过验证码、二次验证、平台风控或访问限制。
- 未确认的自动写操作。
- 自动修改并立即启用生产策略。
- 将生产数据默认上传到云端。

## 3. 成功标准

第一版完成后应满足：

1. 可以连接已登录且启用 CDP 的 Chrome/Edge。
2. 可以从页面读取计划与直播间核心数据。
3. 可以按 5 分钟或 10 分钟周期持续监控。
4. 可以检测 ROI、消耗、成交、GPM、在线人数等指标的有效变化。
5. 可以结合策略画像生成解释、建议、备选动作和置信度。
6. 每次输出都展示当前策略画像、数据时间和数据新鲜度。
7. 用户拒绝建议时，不产生写操作。
8. 用户确认后，系统可以执行预算、暂停、恢复等已注册动作。
9. 每次写操作均记录确认信息、执行前后状态、截图和结果。
10. 页面状态变化、登录失效或结果不确定时，系统停止并请求用户处理。
11. 后续增加 API Provider 时，不需要重写分析、策略和 Chatbot 模块。

## 4. 总体架构

```text
Chatbot Web UI
    |
    v
AI Orchestrator
    |-- Strategy Profile Service
    |-- Analytics Service
    |-- Live Monitor Service
    |-- Recommendation Engine
    |-- Action Planner
    |-- Confirmation and Audit Service
    |-- Learning Service
    |
    v
Execution Provider
    |-- CDP Provider
    |-- Future API Provider
    |
    v
Chrome/Edge -> 千川后台
```

基础设施：

```text
FastAPI -> SQLite -> SQLAlchemy/Alembic
         -> APScheduler/asyncio
         -> WebSocket or SSE
         -> Playwright connect_over_cdp
         -> LLM Adapter
```

### 4.1 核心约束

- 大模型只负责理解、分析、解释和生成结构化建议。
- 大模型不允许直接生成点击坐标、任意 DOM 修改或绕过校验的脚本。
- 写操作必须通过动作注册表和人工确认。
- 所有 CDP 写操作必须串行执行。
- 页面内容视为不可信输入，不能作为系统指令执行。
- CDP 调试端口只监听 127.0.0.1。

## 5. 模块设计

### 5.1 Chatbot UI

职责：

- 接收自然语言指令。
- 展示计划、直播间和账户分析。
- 展示策略画像和版本。
- 展示监控提醒、建议和影响分析。
- 展示待确认动作的差异与风险。
- 提供确认、拒绝、继续观察和取消操作。
- 展示执行进度、结果和审计记录。

### 5.2 AI Orchestrator

职责：

- 调用所选模型提供商的 API。
- 维护会话上下文。
- 将用户意图转换为受控工具调用。
- 调用只读分析和策略服务。
- 生成结构化操作建议，但不执行写操作。
- 处理模型不可用、超时和输出格式错误。

接口要求：

- 模型提供商通过 LLM Adapter 抽象。
- 默认支持 OpenAI-compatible 接口。
- 可扩展 Anthropic、DeepSeek、通义千问等提供商。
- 模型输出必须使用 Pydantic 或等效 schema 校验。

### 5.3 Strategy Profile Service

职责：

- 保存账户级长期策略画像。
- 管理版本和生效时间。
- 展示策略差异。
- 校验建议和动作是否违反硬约束。
- 提供每次输出所需的策略提示信息。

### 5.4 Analytics Service

职责：

- 读取结构化计划、直播间和报表数据。
- 计算 ROI、消耗、成交、订单、GPM、在线人数、CTR、CVR、CPM、CPA 等指标。
- 计算时间窗口、趋势、方差和基线。
- 输出可审计的分析事实，不以模型猜测替代数据。

### 5.5 Live Monitor Service

职责：

- 管理监控会话和启停状态。
- 默认每 5 分钟采集一次，可由用户调整为 10 分钟或其他合理周期。
- 保存计划与直播间快照。
- 检查数据时间和新鲜度。
- 处理重复通知和观察窗口。

### 5.6 Change Detector

职责：

- 与上一周期、最近 30 分钟趋势和历史同时段基线比较。
- 使用绝对变化、相对变化、持续窗口和异常分数。
- 输出正常、观察和建议行动三种状态。
- 避免单个正常波动触发建议。

### 5.7 Recommendation Engine

职责：

- 结合策略画像、数据事实和变化状态生成建议。
- 给出继续观察、暂停、恢复、加预算、降预算、调价等候选动作。
- 给出理由、反证、置信度、有效期和备选动作。
- 不直接执行候选动作。

### 5.8 Action Planner

职责：

- 将建议转换为一个或多个结构化动作草案。
- 校验动作输入、前置条件、权限和硬约束。
- 生成用户可读的操作预览和机器可执行的参数。
- 生成幂等键和预览哈希。

### 5.9 Action Registry

每个动作必须声明：

```text
action_name
description
input_schema
preconditions
scope
expected_effect
confirmation_template
execution_steps
post_execution_verification
idempotency_rule
retry_policy
rollback_or_compensation
audit_fields
```

第一版动作：

```text
read_account
read_plans
read_live_room
create_plan
copy_plan
delete_plan
edit_plan
pause_plan
enable_plan
update_plan_budget
update_plan_bid
update_targeting
update_schedule
bind_existing_material
unbind_existing_material
```

### 5.10 Confirmation and Audit Service

职责：

- 管理待确认动作。
- 将确认绑定到策略版本、动作参数、预览哈希、过期时间和幂等键。
- 只允许当前用户确认。
- 记录操作前后状态、截图、页面结果和耗时。
- 禁止过期确认、参数变更后复用确认或重复执行。

### 5.11 Execution Provider

统一接口：

```text
preflight(action) -> preflight_result
execute(action, confirmation) -> execution_result
verify(action, execution_result) -> verification_result
cancel(job_id) -> cancel_result
```

实现：

- CDP Provider：第一版实现。
- API Provider：预留接口，后续增加。

### 5.12 CDP Provider

职责：

- 使用 Playwright connect_over_cdp 连接本地浏览器。
- 通过页面适配器读取和操作千川后台。
- 执行动作注册表中的固定工作流。
- 执行后读回页面数据校验结果。
- 保存截图、Trace、页面快照和错误信息。
- 处理登录失效、验证码、二次验证、页面改版和超时。

### 5.13 Learning Service

职责：

- 保存策略、建议、用户选择、执行动作和结果。
- 统计不同阈值和动作组合的实际效果。
- 检索相似历史案例。
- 比较不同策略版本效果。
- 接收用户“有帮助”或“误判”反馈。
- 生成新策略、新阈值和新动作组合建议。
- 不自动覆盖生产策略。

## 6. 策略画像

### 6.1 必备字段

```text
profile_id
version
name
business_direction
primary_objective
secondary_objectives
hard_constraints
monitoring_config
allowed_actions
notification_policy
created_at
effective_at
updated_at
```

### 6.2 示例

```text
大方向：稳定放量
主目标：在 ROI >= 2.5 的前提下提升成交额
次目标：控制 GPM 下滑，保持直播间在线人数
硬约束：日预算 <= 5000，单计划最大加价 20%
监控频率：5 分钟
允许动作：暂停、启用、改预算、改出价、修改定向、创建/复制计划
```

### 6.3 输出提醒

每次 Chatbot 输出、监控提醒和确认页面必须显示：

```text
当前策略画像 vX
大方向
主目标
硬约束
数据时间
数据新鲜度
```

### 6.4 变更规则

```text
提出策略变更
-> 展示旧版本与新版本差异
-> 用户确认
-> 生成新版本
-> 记录生效时间
```

Chatbot 不能静默修改策略。

## 7. 直播监控

### 7.1 监控对象

- 计划数据。
- 直播间数据。

### 7.2 核心指标

- ROI
- 消耗
- 成交额
- 成交订单数
- GPM
- 在线人数
- 计划状态和预算

### 7.3 辅助诊断指标

- CTR
- CVR
- CPM
- CPA
- 预算消耗速度
- 流量变化

### 7.4 周期流程

```text
采集计划与直播间快照
-> 检查数据时间和新鲜度
-> 与上一周期比较
-> 与最近 30 分钟趋势比较
-> 与历史同时段基线和策略硬约束比较
-> 判断变化
-> 生成解释和建议
-> 等待用户决策
```

### 7.5 状态

```text
正常：只记录，不推送
观察：下一周期继续验证
建议行动：推送用户决策
```

## 8. 操作确认与执行

### 8.1 操作预览

每个写操作先展示：

- 计划 ID 和名称
- 修改前后差异
- 修改原因
- 当前策略画像版本
- 预计影响
- 风险和不确定性
- 确认有效期
- 操作参数哈希

### 8.2 确认绑定

确认记录必须绑定：

```text
strategy_profile_version
target_ids
action_parameters
preview_hash
expires_at
idempotency_key
```

### 8.3 状态机

```text
待分析 -> 待确认 -> 执行中 -> 已成功
                     -> 部分成功
                     -> 页面状态变化，已中止
                     -> 登录失效，等待处理
                     -> 平台拒绝，记录原因
                     -> 未知状态，禁止自动重试
```

### 8.4 执行后校验

所有写操作必须重新读取页面或接口结果，确认实际状态与目标一致。点击成功不等于操作成功。

## 9. CDP 安全与错误处理

- CDP 只监听 127.0.0.1。
- 使用专用 Chrome/Edge Profile。
- 写操作串行执行，并使用计划级锁。
- 页面状态在确认后发生变化时中止执行。
- 登录失效、验证码、二次验证或风控页面出现时暂停并请求用户处理。
- 不实现绕过验证码、风控或隐藏自动化行为的功能。
- 未知执行状态禁止自动重试。
- 每个动作保存截图、页面快照、日志和耗时。
- 支持紧急停止、暂停监控和取消待执行任务。
- 页面内容视为不可信数据。

## 10. 数据模型

第一版表：

```text
strategy_profiles
strategy_change_logs
conversation_sessions
chat_messages
plan_snapshots
live_room_snapshots
metric_samples
monitor_sessions
change_events
recommendations
pending_confirmations
execution_jobs
execution_logs
browser_artifacts
learning_cases
action_definitions
system_settings
```

数据保留策略可配置。原始页面快照默认保留 30 天，结构化指标和执行记录默认长期保留。默认不上传生产数据到云端。

## 11. Chatbot 与 UI

界面应包含：

1. 对话区。
2. 实时监控区。
3. 建议决策区。
4. 策略画像区。
5. 任务执行区。
6. 审计区。

推荐技术栈：

```text
前端：Next.js 或 React
后端：Python 3.11 + FastAPI
数据：SQLite + SQLAlchemy + Alembic
调度：APScheduler 或 asyncio
推送：WebSocket 或 SSE
浏览器：Playwright + CDP
模型：OpenAI-compatible Adapter + 其他提供商扩展
校验：Pydantic
日志：structlog 或 JSON structured logging
```

本地服务只监听 127.0.0.1。

## 12. 安全与隐私

- 密钥保存在 Windows Credential Manager 或本地加密存储。
- 不提交 App Secret、Token、Cookie、截图和真实业务数据到 Git。
- 模型调用前进行必要脱敏。
- 日志屏蔽敏感字段。
- 支持数据库备份、恢复和清理。
- 提供本地数据导出。

## 13. 测试与验收

### 13.1 测试类型

- 指标计算单元测试。
- 策略画像版本测试。
- 变化检测边界测试。
- 动作注册表 schema 测试。
- CDP 工作流模拟页面测试。
- 执行前不写入测试。
- 执行后读回校验测试。
- 幂等和重复提交测试。
- 登录失效和页面改版测试。
- 数据库迁移测试。
- 模型切换测试。
- WebSocket/SSE 推送测试。

### 13.2 验收场景

1. 连接已登录浏览器。
2. 读取计划和直播间数据。
3. 运行 5 分钟和 10 分钟监控。
4. 检测 ROI、消耗、成交、GPM、在线人数变化。
5. 生成解释、建议和置信度。
6. 用户拒绝后不执行。
7. 用户确认后修改预算。
8. 用户确认后暂停或启用计划。
9. 执行失败时保存证据并停止。
10. 每次输出显示策略画像和硬约束。
11. 策略变更生成新版本。
12. API Provider 替换测试通过。

## 14. 开发阶段

### 第一阶段：基础设施

- 本地前后端。
- SQLite、迁移、策略画像、日志和模型适配层。
- CDP 连接和只读数据采集。
- Chatbot 基础对话。

### 第二阶段：分析监控

- 计划与直播间指标采集。
- 5 至 10 分钟监控。
- 变化检测、建议生成和用户决策面板。

### 第三阶段：写操作

- 暂停、启用和预算修改。
- 出价、定向、投放时间和计划编辑。
- 创建、复制、删除计划。
- 已有素材绑定和解绑。
- 每个动作独立测试和审计。

### 第四阶段：学习

- 决策日志、结果归因、策略版本评估和案例库。
- 用户反馈和优化建议。

### 第五阶段：API 迁移

- 实现 API Execution Provider。
- 保持动作注册表和业务层不变。
- 根据权限逐步从 CDP 切换到官方 API。

## 15. 主要风险与缓解措施

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 千川页面改版 | CDP 工作流失效 | 页面适配器隔离、选择器测试、失败截图、快速停用动作 |
| 数据延迟 | 5 分钟监控误判 | 显示数据时间和新鲜度，对未刷新数据标记延迟 |
| 误操作预算或计划 | 直接经济损失 | 人工确认、动作预览、硬约束、幂等、执行后校验 |
| 登录失效或验证码 | 监控中断 | 暂停任务并要求用户处理，不实现绕过 |
| 模型输出不稳定 | 建议或参数错误 | 结构化 schema、确定性校验、禁止模型直接执行 |
| 历史样本不足 | 学习结论不可靠 | 显示置信度，只有达到样本门槛才形成策略建议 |
| 敏感数据泄露 | 账户风险 | 本地存储、脱敏、本地端口、密钥加密 |
| 重复提交 | 重复修改账户 | 幂等键、计划锁、执行前重读、未知状态不重试 |

## 16. 关键设计决策

1. 使用 Chatbot 作为唯一主入口。
2. 采用 Human-in-the-loop，所有写操作必须确认。
3. 第一版采用 CDP，后续以 API Provider 替换。
4. 使用动作注册表，不允许模型自由控制浏览器。
5. 策略画像长期保存并每次输出提醒。
6. 每次监控反馈展示数据时间、变化、依据、建议、置信度和有效期。
7. “持续学习”通过数据积累、案例检索、统计评估和用户反馈实现，不自动覆盖生产策略。
8. 本地优先，默认不上传生产数据。

## 17. 非目标

- 建立通用广告投放平台。
- 支持所有广告平台。
- 在第一版构建训练或微调模型能力。
- 自动决策并直接修改账户。
- 替代千川官方后台的全部功能。