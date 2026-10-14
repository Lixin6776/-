<#
依赖安装（只跑一次）：检测 Python / Node / pnpm → 装后端和前端依赖 → 准备 .env
用法：
  双击同目录的「安装依赖.cmd」
  或：powershell -ExecutionPolicy Bypass -File install.ps1
  只想看检测结果、不装任何东西：加 -DryRun
#>
[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Have($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Say($text) { Write-Host $text }
function Try-Winget($id, $label) {
    if (-not (Have winget)) { Say ("  [×] 没装 winget，装不了 " + $label + "，请去官网手动装"); return $false }
    if ($DryRun) { Say ("  [dry] 会执行：winget install " + $id); return $false }
    Say ("  [+] 正在用 winget 安装 " + $label + " ...")
    try { winget install --id $id --accept-source-agreements --accept-package-agreements --silent; return $true }
    catch { Say ("  [×] 安装失败：" + $label); return $false }
}

Say ""
Say "=== 直播运营助手 · 安装依赖 ==="
Say ""
if ($DryRun) { Say "（DryRun：只检测，不安装）" }
Say ""

# ---------- 1) Python ----------
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
# 注意：Windows 有个「应用商店占位」的 python.exe —— Get-Command 能找到，但根本跑不了。
# 所以必须真的执行一次 --version 才算"装了"。
$pythonOk = $false
if (Have python) {
    try {
        $ver = (& python --version 2>&1 | Out-String).Trim()
        if ($ver -match "Python 3\.(\d+)") {
            if ([int]$Matches[1] -ge 11) { $pythonOk = $true; Say ("[=] Python 已装：" + $ver) }
            else { Say ("[!] Python 版本偏低（" + $ver + "），需要 3.11 或更高") }
        } else {
            Say "[!] 检测到 python 命令但跑不起来（可能是 Windows 应用商店的占位程序）"
        }
    } catch {
        Say "[!] python 命令不可用"
    }
} else {
    Say "[!] 没找到 Python（需要 3.11 或更高）"
}
if (-not $pythonOk) {
    Say "    建议：去 python.org 装 3.11+（安装时勾选 Add to PATH）"
    Try-Winget "Python.Python.3.12" "Python 3.12" | Out-Null
}

# ---------- 2) Node ----------
$nodeOk = $false
if (Have node) {
    try {
        $nv = (& node --version 2>&1 | Out-String).Trim()
        if ($nv -match "v(\d+)") { $nodeOk = $true; Say ("[=] Node 已装：" + $nv) }
    } catch { }
}
if (-not $nodeOk) {
    Say "[!] 没找到可用的 Node（需要 18 或更高）"
    Try-Winget "OpenJS.NodeJS.LTS" "Node.js LTS" | Out-Null
}

# ---------- 3) pnpm ----------
$pnpm = (Get-Command pnpm.cmd -ErrorAction SilentlyContinue).Source
if (-not $pnpm -and (Have corepack)) {
    if ($DryRun) { Say "  [dry] 会执行：corepack enable pnpm" } else {
        Say "[+] 用 corepack 启用 pnpm ..."
        try { corepack enable pnpm } catch { }
        $pnpm = (Get-Command pnpm.cmd -ErrorAction SilentlyContinue).Source
    }
}
if (-not $pnpm -and (Have npm)) {
    if ($DryRun) { Say "  [dry] 会执行：npm install -g pnpm" } else {
        Say "[+] 用 npm 安装 pnpm ..."
        try { npm install -g pnpm; $pnpm = (Get-Command pnpm.cmd -ErrorAction SilentlyContinue).Source } catch { }
    }
}
if ($pnpm) { Say "[=] pnpm 可用" } else { Say "[!] pnpm 不可用，前端依赖装不了" }

# ---------- 4) 后端依赖 ----------
$backend = Join-Path $root "backend"
if (Test-Path $python) {
    Say "[=] 后端虚拟环境已存在，跳过创建"
} elseif ($DryRun) {
    Say "  [dry] 会在 backend 建 .venv 并 pip install -e ."
} else {
    Say "[+] 创建后端虚拟环境 ..."
    Push-Location $backend
    python -m venv .venv
    Pop-Location
}
if (-not $DryRun) {
    if (Test-Path $python) {
        Say "[+] 安装后端依赖 ..."
        Push-Location $backend
        & $python -m pip install -q -U pip
        & $python -m pip install -q -e .
        Pop-Location
        Say "[=] 后端依赖完成"
    }
}

# ---------- 5) 前端依赖 ----------
$frontend = Join-Path $root "frontend"
$modules = Join-Path $frontend "node_modules"
if (Test-Path $modules) {
    Say "[=] 前端依赖已存在，跳过"
} elseif ($DryRun) {
    Say "  [dry] 会在 frontend 执行 pnpm install"
} elseif ($pnpm) {
    Say "[+] 安装前端依赖（第一次会慢一点）..."
    Push-Location $frontend
    & $pnpm install
    Pop-Location
    Say "[=] 前端依赖完成"
}

# ---------- 6) 本地配置模板 ----------
$envFile = Join-Path $backend ".env"
if (Test-Path $envFile) {
    Say "[=] backend/.env 已存在"
} elseif ($DryRun) {
    Say "  [dry] 会从 .env.example 复制出 backend/.env"
} else {
    Copy-Item -LiteralPath (Join-Path $backend ".env.example") -Destination $envFile -Force
    Say "[+] 已生成 backend/.env（直播间/账户也可以之后在工具「数据源」里填）"
}

Say ""
Say "=== 完成 ==="
Say "下一步：双击 启动直播运营助手.cmd"
Say "（第一次打开工具后，去「数据源」填直播间名称、点「连接数据源」；要登录就在弹出的 Chrome 里登录千川）"
Say ""
