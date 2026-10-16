# 巨量开放平台 API 接入指南（给自己用）

> 这个工具默认走 **CDP**（读你浏览器里的千川页面），不用配 API 也能跑。
> **API 是"更稳"的可选路径**：不依赖页面结构、也不怕千川改版。想用就得先拿一套开放平台凭据。
>
> 本指南只讲"怎么拿到那套凭据 + 填进工具"。具体页面字段以**官方文档为准**（文末有链接）。

---

## 0. 先搞清楚要准备什么

| 要拿到的东西 | 在哪拿 | 填到工具的哪 |
| --- | --- | --- |
| **App ID** | 开放平台「APPID 管理」 | 数据源 → API 连接 → App ID |
| **App Secret** | 同上（应用基本信息） | 数据源 → API 连接 → App Secret |
| **advertiser_id**（广告主 ID） | 你要读的千川账户 ID | 数据源 → API 连接 → 广告主 ID |
| **access_token** | 广告主**授权**后用 auth_code 换 | 数据源 → API 连接 → Access Token |
| **refresh_token**（可选但强烈建议） | 同上（一起返回） | 数据源 → API 连接 → Refresh Token |

> 工具**只需要读权限**（账户信息 / 计划 / 报表 / 素材），不需要任何写权限。

---

## 1. 注册开放平台开发者 + 创建应用

1. 打开[巨量引擎开放平台](https://open.oceanengine.com/) → 注册 / 登录。
2. 完成**开发者认证**（一般要企业主体；个人主体权限通常不够）。
3. 进入**控制台 → APPID 管理 → 创建应用**。
   - 应用类型选 Marketing API（广告投放类）。
   - 记下 **App ID** 和 **App Secret**。

---

## 2. 申请接口权限（Scope）

在应用的**「接口权限 / 权限申请」**页面，勾选**千川（Qianchuan）相关的读取接口**，至少包括：

- 广告主 / 账户信息
- 广告计划列表
- 报表（计划维度、直播间维度）
- 素材相关（如果要用素材分析）

> 提交后**可能需要审核**。审核通过前，调接口会报权限不足。

---

## 3. 配置回调地址（redirect_uri）

在应用基本信息里设置**回调地址**（`redirect_uri`）。官方原文：

> redirect_uri：即回调链接，由开发者自行提供和定义，**需与 APPID 设置的回调链接一致**，用于授权成功跳转并接收回调信息。

用本机工具的话，回调地址随便填一个**你自己能打开的地址**即可（例如 `https://localhost/callback`），
只要**和后面生成授权链接时用的完全一致**就行。

---

## 4. 生成授权链接，让广告主账号去授权

官方原文：

> Step1：在「APPID 管理」页面选择要使用的应用程序，点击进入基本信息页面即可查看到**授权URL**，
> 该页面展示的为默认申请所有权限的示例，可直接使用或自定义拼装。
> Step2：将拼接完的授权URL发送给客户，引导客户访问……

要点：

1. 在 **APPID 管理 → 你的应用 → 基本信息** 里能看到**授权 URL**（已带默认参数）。
2. 按需拼上／确认这几个参数：
   - `app_id`：你的 App ID
   - `redirect_uri`：第 3 步配的、**完全一致**的回调地址
   - `state`：随便一个字符串（防 CSRF，可留空）
   - `scope`：要申请的权限范围（按第 2 步勾的来）
3. **用要读数据的那个千川广告主账号**（或它的管理员）去访问这个链接并**同意授权**。
4. 同意后会跳到 `redirect_uri`，**地址栏里带 `auth_code=...`** —— 复制它。

> ⚠️ 授权是**广告主账号**做的，不是你开发者账号做的。这就是为什么必须让"账户的人"点一次。

---

## 5. 用 auth_code 换 access_token / refresh_token

官方原文：

> 获取到客户授权返回的 auth_code 后，可通过【**获取 Access Token**】接口获取授权客户对应的
> AccessToken 和 RefreshToken。

调用「获取 Access Token」接口，用 `app_id` + `secret` + `auth_code` 换回：

- `access_token`（有效期短，会过期）
- `refresh_token`（有效期长，用来续期）

> 具体请求地址、参数名以官方文档为准（见文末）。很多语言的官方 SDK 里都有一行封装，比如：
> <https://github.com/oceanengine/ad_open_sdk_java>

---

## 6. 填进本工具

1. 打开工具 → 左侧 **「数据源」** → **API 连接（开放平台）** 卡片；
2. 依次填：接口地址（默认即可）、**App ID**、**App Secret**、**广告主 ID**、**Access Token**、（可选）**Refresh Token**；
3. 点 **「保存凭据」**（存在本机 `.local/api_config.json`，不进仓库、不外传）；
4. 点 **「测试连接」** —— 会去拉一次广告主信息：
   - 成功 → 显示"已配置"，系统切到 **API 优先**；
   - 失败 → 会给出具体报错（权限没申请 / token 过期 / 回调不一致等）。

> 没配好之前**完全不影响盯盘**：系统自动继续用 CDP。

---

## 7. 常见问题

| 现象 | 多半是 |
| --- | --- |
| 测试连接报**权限不足 / 无权限** | 第 2 步的接口权限还没审核通过 |
| 报**认证失败 / 401** | access_token 过期了；填个 refresh_token 让它自动续期 |
| 报**回调地址不一致** | 第 3 步配的和授权链接里的 `redirect_uri` 不一样 |
| 报 **refresh token is not configured** | 只填了 access_token 且没填 refresh_token（本工具已兼容：`expires_at=0` 时直接用 access_token） |
| 不知道 `advertiser_id` 填什么 | 就是千川后台 URL 里 `aavid=` 后面那串数字 |
| 授权页打不开 / 账号无权 | 要用**该广告主账号的管理员**去授权 |

---

## 8. 官方文档（以它为准）

- 入门指南：<https://open.oceanengine.com/labels/13>
- 接入全流程 / APPID 管理：<https://open.oceanengine.com/labels/34>
- 如何申请授权 & 生成授权链接：<https://open.oceanengine.com/labels/7/docs/1803016515293203>
- 官方 SDK（Java 等）：<https://github.com/oceanengine/ad_open_sdk_java>

> 本指南里引用的官方原话都标了"官方原文"。**具体页面字段、接口地址以官方文档当前版本为准** ——
> 开放平台改版比较勤，工具这边只要你能拿到 `App ID / Secret / advertiser_id / access_token` 就能接上。
